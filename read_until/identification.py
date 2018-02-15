from collections import defaultdict, Counter
import concurrent
import functools
import logging
import random
import sys
import time

import numpy

try:
    import mappy
    import scrappy
except ImportError:
    raise ImportError("'mappy' and 'scrappy' must be installed to use this functionality.")

import read_until
import read_until.simple as read_until_extras


def basecall_data(raw):
    seq, score, pos, start, end, base_probs = scrappy.basecall_raw(raw)
    if sys.version_info[0] < 3:
        seq = seq.encode()
    return seq, score


def divide_analysis(client, map_index, genome_cut=2200000, batch_size=10, delay=1, throttle=0.1):
    """Analysis using scrappy and mappy to accept/reject reads based on
    channel and identity as determined by alignment of basecall to
    reference. Channels are split into three groups (by division modulo 3
    of the channel number): the first group is left to proceed "naturally",
    for the second (third) attempts are made to sequence only reads from
    before (after) a reference locus.

    :param client: an instance of a `ReadUntilClient` object.
    :param map_index: a minimap2 index file.
    :param genome_cut: reference locus for determining read acceptance
        in the two filtered channel groups.
    :param batch_size: number of reads to pull from `client` at a time.
    :param delay: number of seconds to wait before starting analysis.
    :param throttle: minimum interval between requests to `client`.

    :returns: a dictionary of Counters of actions taken per channel group.

    """
    logger = logging.getLogger('Analysis')
    logger.info('Starting analysis of reads in {}s.'.format(delay))
    time.sleep(delay)

    logger.info('Loading index')
    mapper = mappy.Aligner(map_index, preset='map_ont')

    action_counters = defaultdict(Counter)
    max_pos = 0
    while client.is_running:
        t0 = time.time()
        read_batch = client.get_read_chunks(batch_size=batch_size, last=True)
        for channel, read in read_batch:
            channel_group = (channel % 3)
            if channel_group == 0:
                # leave these channels alone
                logger.debug('Skipping channel {}({}).'.format(channel, 0))
                action_counters[channel_group]['skipped'] += 1
                client.stop_receiving_read(channel, read.number)
            else:
                # convert the read data into a numpy array of correct type
                raw_data = numpy.fromstring(read.raw_data, client.signal_dtype)
                read.raw_data = read_until.NullRaw
                basecall, score = basecall_data(raw_data)
                aligns = list(mapper.map(basecall))
                if len(aligns) == 0:
                    # Defer decision for another time
                    action_counters[channel_group]['unaligned'] += 1
                    logger.debug("read_{}_{} doesn't align.".format(channel, read.number))
                else:
                    # choose a random alignment as surrugate for detecting a best
                    align = random.choice(aligns)
                    logger.debug('{}:{}-{}, read_{}_{}:{}-{}, blen:{}, class:{}'.format(
                        align.ctg, align.r_st, align.r_en, channel, read.number, align.q_st, align.q_en, align.blen,
                        [client.read_classes[x] for x in read.chunk_classifications]
                    ))
                    first_half = align.r_st < genome_cut
                    action_counters[channel_group]['section_{}'.format(int(first_half))] += 1
                    unblock = (
                        (channel_group == 1 and first_half) or
                        (not channel_group == 1 and not first_half)
                    )
                    if unblock:
                        # Bad read for channel
                        action_counters[channel_group]['unblock'] += 1
                        logger.debug('Unblocking channel {}({}) ref:{}.'.format(channel, channel_group, align.r_st))
                        client.unblock_read(channel, read.number)
                    else:
                        # Good read for channel
                        action_counters[channel_group]['stop'] += 1
                        logger.debug('Good channel {}({}) ref:{}.'.format(channel, channel_group, align.r_st))
                        if not client.one_chunk:
                            client.stop_receiving_read(channel, read.number)

        t1 = time.time()
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)

    logger.info('Finished analysis of reads.')

    return action_counters


def filter_targets(client, mapper, targets, batch_size=10, delay=1, throttle=0.1, control_group=16):
    """Analysis using scrappy and mappy to accept/reject reads based on
    channel and identity as determined by alignment of basecall to
    reference. Channels are split into two groups (by division modulo
    `control_group` of the channel number): the first group is left to proceed
    "naturally", the second rejects reads not aligning to target sequences.

    :param client: an instance of a `ReadUntilClient` object.
    :param mapper: an instance of `mappy.Aligner`.
    :param targets: a list of acceptable reference targets (chr, start, end).
    :param batch_size: number of reads to pull from `client` at a time.
    :param delay: number of seconds to wait before starting analysis.
    :param throttle: minimum interval between requests to `client`.
    :param control_group: channels for which (channel %% control_group) == 0
        will form the control group.

    :returns: a dictionary of Counters of actions taken per channel group.

    """
    logger = logging.getLogger('Analysis')
    logger.info('Starting analysis of reads in {}s.'.format(delay))
    time.sleep(delay)

    action_counters = defaultdict(Counter)
    max_pos = 0
    while client.is_running:
        t0 = time.time()
        read_batch = client.get_read_chunks(batch_size=batch_size, last=True)
        for channel, read in read_batch:
            channel_group = 'control' if (channel % control_group) else 'test'
            if channel_group == 'test':
                # leave these channels alone
                logger.debug('Skipping channel {}({}).'.format(channel, 0))
                action_counters[channel_group]['skipped'] += 1
                client.stop_receiving_read(channel, read.number)
            else:
                # convert the read data into a numpy array of correct type
                raw_data = numpy.fromstring(read.raw_data, client.signal_dtype)
                read.raw_data = read_until.NullRaw
                basecall, score = basecall_data(raw_data)
                aligns = list(mapper.map(basecall))
                if len(aligns) == 0:
                    # Defer decision for another time
                    action_counters[channel_group]['unaligned'] += 1
                    logger.debug("read_{}_{} doesn't align.".format(channel, read.number))
                else:
                    # choose a random alignment as surrugate for detecting a best
                    align = random.choice(aligns)
                    logger.debug('{}:{}-{}, read_{}_{}:{}-{}, blen:{}, class:{}'.format(
                        align.ctg, align.r_st, align.r_en, channel, read.number, align.q_st, align.q_en, align.blen,
                        [client.read_classes[x] for x in read.chunk_classifications]
                    ))
                    unblock = True
                    hit = 'off_target'
                    for target in targets:
                        if align.ctg == target[0]:
                            # This could be a little more permissive
                            if (align.r_st > target[1] and align.r_st < target[2]) or \
                               (align.r_en > target[1] and align.r_en < target[2]):
                                unblock = False
                                hit = '{}:{}-{}'.format(*target)

                    # store on target
                    action_counters[channel_group][hit] += 1
                    if unblock:
                        logger.debug('Unblocking channel {}:{}:{}.'.format(channel, read.number, read.chunk_start_sample))
                        client.unblock_read(channel, read.number)
                    else:
                        logger.debug('Good channel {}:{}:{}, aligns to {}.'.format(channel, read.number, read.chunk_start_sample, hit))
                        if not client.one_chunk:
                            client.stop_receiving_read(channel, read.number)

        t1 = time.time()
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)

    logger.info('Finished analysis of reads.')

    return action_counters


def main():
    parser = read_until_extras._get_parser()
    parser.description = 'Read until with basecall-alignment filter.'
    parser.add_argument('map_index', help='minimap alignment index.')
    parser.add_argument('--targets', default=None, nargs='+',
        help='list of target regions chr:start-end.')
    parser.add_argument('--control_group', default=16, type=int,
        help='Inverse proportion of channels in control group.')
    args = parser.parse_args()

    logging.basicConfig(format='[%(asctime)s - %(name)s] %(message)s',
        datefmt='%H:%M:%S', level=args.log_level)
    logger = logging.getLogger('Manager')

    read_until_client = read_until.ReadUntilClient(
        mk_port=args.port, one_chunk=args.one_chunk, filter_strands=True
    )

    if args.targets is None:
        analysis_function = functools.partial(
            divide_analysis, read_until_client, args.map_index,
            delay=args.analysis_delay
        )
    else:
        logger.info('Loading index')
        mapper = mappy.Aligner(args.map_index, preset='map_ont')
        regions = list()
        for target in args.targets:
            ref, coords = target.split(':')
            start, stop = (int(x) for x in coords.split('-'))
            regions.append((ref, start, stop))
        analysis_function = functools.partial(
            filter_targets, read_until_client, mapper, regions,
            delay=args.analysis_delay
        )

    with read_until_extras.ThreadPoolExecutorStackTraced() as executor:
        futures = list()
        futures.append(executor.submit(
            read_until_client.run, runner_kwargs={
                'run_time':args.run_time, 'min_chunk_size':args.min_chunk_size
            }
        ))
        # Launch several incarnations of the worker, this is a rather inelegant
        #    form of parallelism, not least as each worker will create its own
        #    mapping index (which might be large).
        for _ in range(args.workers):
            futures.append(executor.submit(analysis_function))

        total_counters = defaultdict(Counter)
        for f in concurrent.futures.as_completed(futures):
            if f.exception() is not None:
                logger.warning(f.exception())
            elif isinstance(f.result(), defaultdict):
                new_counts = f.result()
                all_keys = set(total_counters.keys()) | set(new_counts.keys())
                for key in all_keys:
                    total_counters[key] += new_counts[key]

        groups = list(total_counters.keys())
        actions = set()
        for group in groups:
            actions |= set(total_counters[group].keys())
        
        msg = ['Action summary:', '\t'.join(('group', 'action'.ljust(9), 'count'))]
        for group in groups:
            for action in actions:
                msg.append(
                    '\t'.join((str(x) for x in (
                        group, str(action).ljust(9), total_counters[group][action]
                    )))
                )
        msg = '\n'.join(msg)
        logger.info(msg)
