from collections import defaultdict, Counter
import concurrent
import logging
import random
import time

import numpy

try:
    import mappy
    import scrappy
except ImportError:
    raise ImportError("'mappy' and 'scrappy' must be installed to use this functionality.")

from read_until import read_until

def id_analysis(client, map_index, genome_cut=2200000, batch_size=10, delay=1, throttle=0.1):
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

    """
    logger = logging.getLogger('Analysis')
    logger.info('Starting analysis of reads in {}s.'.format(delay))
    time.sleep(delay)

    logger.info('Loading index')
    mapper = mappy.Aligner(map_index, preset='map_ont')

    def basecall_data(raw):
        seq, score, pos, start, end, base_probs = scrappy.basecall_raw(raw)
        return seq, score

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
                read.raw_data = bytes('', 'utf-8') # we don't need this now
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
                        client.stop_receiving_read(channel, read.number) 

        t1 = time.time()
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)

    logger.info('Finished analysis of reads.')

    print('\t'.join(('chan', 'choice', 'count')))
    for chan in (0, 1, 2):
        for thing in ('skipped', 'unaligned', 'section_0', 'section_1', 'unblock', 'stop'):
            print('\t'.join((str(x) for x in (chan, thing, action_counters[chan][thing]))))
        print("-------------")


def main():
    parser = read_until._get_parser()
    parser.add_argument('map_index', help='minimap alignment index.')
    parser.add_argument('--workers', default=1, type=int, help='worker threads.')
    args = parser.parse_args()

    logging.basicConfig(format='[%(asctime)s - %(name)s] %(message)s',
        datefmt='%H:%M:%S', level=args.log_level)

    read_until_client = read_until.ReadUntilClient(mk_port=args.port, one_chunk=False, filter_strands=True)
    with read_until.ThreadPoolExecutorStackTraced() as executor:
        futures = list()
        futures.append(executor.submit(read_until_client.run, runner_kwargs={'run_time':args.run_time}))
        for _ in range(args.workers):
            futures.append(executor.submit(id_analysis, read_until_client, args.map_index, delay=args.analysis_delay))

        for f in concurrent.futures.as_completed(futures):
            if f.exception() is not None:
                print(f.exception())

