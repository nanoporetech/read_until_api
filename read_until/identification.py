from collections import defaultdict, Counter
import concurrent
import functools
import logging
import os
import random
import sys
import time
from uuid import uuid4

import numpy

try:
    import mappy
    import scrappy
except ImportError:
    raise ImportError(
        "'mappy' and 'scrappy' must be installed to use this functionality."
    )

import read_until
import read_until.simple as read_until_extras


def basecall_data(raw):
    seq, score, pos, start, end, base_probs = scrappy.basecall_raw(raw)
    if sys.version_info[0] < 3:
        seq = seq.encode()
    return seq, score


def divide_analysis(
    client,
    map_index,
    genome_cut=2200000,
    batch_size=10,
    delay=1,
    throttle=0.1,
    unblock_duration=0.1,
):
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
    :param unblock_duration: time in seconds to apply unblock voltage.

    :returns: a dictionary of Counters of actions taken per channel group.

    """
    logger = logging.getLogger("Analysis")
    logger.info("Starting analysis of reads in {}s.".format(delay))
    time.sleep(delay)

    logger.info("Loading index")
    mapper = mappy.Aligner(map_index, preset="map_ont")

    action_counters = defaultdict(Counter)
    max_pos = 0
    while client.is_running:
        t0 = time.time()
        read_batch = client.get_read_chunks(batch_size=batch_size, last=True)
        for channel, read in read_batch:
            channel_group = channel % 3
            if channel_group == 0:
                # leave these channels alone
                logger.debug("Skipping channel {}({}).".format(channel, 0))
                action_counters[channel_group]["skipped"] += 1
                client.stop_receiving_read(channel, read.number)
            else:
                # convert the read data into a numpy array of correct type
                raw_data = numpy.fromstring(read.raw_data, client.signal_dtype)
                read.raw_data = read_until.NullRaw
                basecall, score = basecall_data(raw_data)
                aligns = list(mapper.map(basecall))
                if len(aligns) == 0:
                    # Defer decision for another time
                    action_counters[channel_group]["unaligned"] += 1
                    logger.debug(
                        "read_{}_{} doesn't align.".format(channel, read.number)
                    )
                else:
                    # choose a random alignment as surrugate for detecting a best
                    align = random.choice(aligns)
                    logger.debug(
                        "{}:{}-{}, read_{}_{}:{}-{}, blen:{}, class:{}".format(
                            align.ctg,
                            align.r_st,
                            align.r_en,
                            channel,
                            read.number,
                            align.q_st,
                            align.q_en,
                            align.blen,
                            [
                                client.read_classes[x]
                                for x in read.chunk_classifications
                            ],
                        )
                    )
                    first_half = align.r_st < genome_cut
                    action_counters[channel_group][
                        "section_{}".format(int(first_half))
                    ] += 1
                    unblock = (channel_group == 1 and first_half) or (
                        not channel_group == 1 and not first_half
                    )
                    if unblock:
                        # Bad read for channel
                        action_counters[channel_group]["unblock"] += 1
                        logger.debug(
                            "Unblocking channel {}({}) ref:{}.".format(
                                channel, channel_group, align.r_st
                            )
                        )
                        client.unblock_read(
                            channel, read.number, duration=unblock_duration
                        )
                    else:
                        # Good read for channel
                        action_counters[channel_group]["stop"] += 1
                        logger.debug(
                            "Good channel {}({}) ref:{}.".format(
                                channel, channel_group, align.r_st
                            )
                        )
                        if not client.one_chunk:
                            client.stop_receiving_read(channel, read.number)

        t1 = time.time()
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)

    # end while loop
    logger.info("Received client stop signal.")

    return action_counters


def filter_targets(
    client,
    mapper,
    targets,
    batch_size=10,
    delay=1,
    throttle=0.1,
    control_group=16,
    unblock_unknown=False,
    basecalls_output=None,
    unblock_duration=0.1,
):
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
    :param unblock_unknown: whether or not to unblock reads which cannot be
        positively identified (i.e. show no alignment to reference whether
        on or off target).
    :param basecalls_output: filename prefix for writing basecalls.
    :param unblock_duration: time in seconds to apply unblock voltage.

    :returns: a dictionary of Counters of actions taken per channel group.

    """
    logger = logging.getLogger("Analysis")
    logger.info("Starting analysis of reads in {}s.".format(delay))
    time.sleep(delay)
    thread_id = str(uuid4())
    if basecalls_output is None:
        basecalls_output = os.devnull
    else:
        basecalls_output = "{}_{}.fa".format(basecalls_output, thread_id)

    with open(basecalls_output, "w") as fasta:
        action_counters = defaultdict(Counter)
        max_pos = 0
        while client.is_running:
            t0 = time.time()
            read_batch = client.get_read_chunks(batch_size=batch_size, last=True)
            for channel, read in read_batch:
                channel_group = "test" if (channel % control_group) else "control"
                if channel_group == "control":
                    # leave these channels alone
                    logger.debug("Skipping channel {}({}).".format(channel, 0))
                    action_counters[channel_group]["skipped"] += 1
                    client.stop_receiving_read(channel, read.number)
                else:
                    # convert the read data into a numpy array of correct type
                    raw_data = numpy.fromstring(read.raw_data, client.signal_dtype)
                    read.raw_data = read_until.NullRaw
                    basecall, score = basecall_data(raw_data)
                    aligns = list(mapper.map(basecall))
                    fasta_action = ""
                    if len(aligns) == 0:
                        action_counters[channel_group]["unaligned"] += 1
                        if unblock_unknown:
                            logger.debug(
                                "Unblocking unidentified channel {}:{}:{}.".format(
                                    channel, read.number, read.chunk_start_sample
                                )
                            )
                            client.unblock_read(channel, read.number)
                            fasta_action = "unaligned/unblocked"
                        else:
                            # Defer decision for another time (if client is setup
                            #   to show us more).
                            logger.debug(
                                "Leaving unidentified channel {}:{}:{}".format(
                                    channel, read.number, read.chunk_start_sample
                                )
                            )
                            fasta_action = "unaligned/left"
                    else:
                        # choose a random alignment as surrugate for detecting a best
                        align = random.choice(aligns)
                        logger.debug(
                            "{}:{}-{}, read_{}_{}:{}-{}, blen:{}, class:{}".format(
                                align.ctg,
                                align.r_st,
                                align.r_en,
                                channel,
                                read.number,
                                align.q_st,
                                align.q_en,
                                align.blen,
                                [
                                    client.read_classes[x]
                                    for x in read.chunk_classifications
                                ],
                            )
                        )
                        unblock = True
                        hit = "off_target"
                        for target in targets:
                            if align.ctg == target[0]:
                                # This could be a little more permissive
                                if (
                                    align.r_st > target[1] and align.r_st < target[2]
                                ) or (
                                    align.r_en > target[1] and align.r_en < target[2]
                                ):
                                    unblock = False
                                    hit = "{}:{}-{}".format(*target)

                        # store on target
                        action_counters[channel_group][hit] += 1
                        if unblock:
                            logger.debug(
                                "Unblocking channel {}:{}:{}.".format(
                                    channel, read.number, read.chunk_start_sample
                                )
                            )
                            client.unblock_read(
                                channel, read.number, duration=unblock_duration
                            )
                            fasta_action = "{}/unblocked".format(hit)
                        else:
                            logger.debug(
                                "Good channel {}:{}:{}, aligns to {}.".format(
                                    channel, read.number, read.chunk_start_sample, hit
                                )
                            )
                            if not client.one_chunk:
                                client.stop_receiving_read(channel, read.number)
                            fasta_action = "{}/stopped".format(hit)
                        fasta_action += " {}:{}-{}".format(
                            align.ctg, align.r_st, align.r_en
                        )

                    fasta.write(
                        ">{} {} {} {} {}\n{}\n".format(
                            read.id, score, channel, read.number, fasta_action, basecall
                        )
                    )

            t1 = time.time()
            if t0 + throttle > t1:
                time.sleep(throttle + t0 - t1)

        # end while loop
        logger.info("Received client stop signal.")

    return action_counters


def main():
    parser = read_until_extras._get_parser()
    parser.description = "Read until with basecall-alignment filter."
    parser.add_argument("map_index", help="minimap alignment index.")
    parser.add_argument(
        "--targets",
        default=None,
        nargs="+",
        help="list of target regions chr:start-end.",
    )
    parser.add_argument(
        "--control_group",
        default=16,
        type=int,
        help="Inverse proportion of channels in control group.",
    )
    parser.add_argument(
        "--unblock_unknown",
        default=False,
        action="store_true",
        help="Inverse proportion of channels in control group.",
    )
    parser.add_argument(
        "--basecalls_output", help="Filename prefix for on-the-fly basecalls."
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="[%(asctime)s - %(name)s] %(message)s",
        datefmt="%H:%M:%S",
        level=args.log_level,
    )
    logger = logging.getLogger("Manager")

    read_until_client = read_until.ReadUntilClient(
        mk_host=args.host,
        mk_port=args.port,
        one_chunk=args.one_chunk,
        filter_strands=True,
    )

    if args.targets is None:
        analysis_function = functools.partial(
            divide_analysis,
            read_until_client,
            args.map_index,
            delay=args.analysis_delay,
            unblock_duration=args.unblock_duration,
        )
    else:
        logger.info("Loading index")
        mapper = mappy.Aligner(args.map_index, preset="map_ont")
        regions = list()
        for target in args.targets:
            ref, coords = target.split(":")
            start, stop = (int(x) for x in coords.split("-"))
            regions.append((ref, start, stop))
        analysis_function = functools.partial(
            filter_targets,
            read_until_client,
            mapper,
            regions,
            delay=args.analysis_delay,
            control_group=args.control_group,
            unblock_unknown=args.unblock_unknown,
            basecalls_output=args.basecalls_output,
            unblock_duration=args.unblock_duration,
        )

    # run read until, and capture statistics
    action_counters = read_until_extras.run_workflow(
        read_until_client,
        analysis_function,
        args.workers,
        args.run_time,
        runner_kwargs={"min_chunk_size": args.min_chunk_size},
    )

    # summarise statatistics
    total_counters = defaultdict(Counter)
    for worker_counts in action_counters:
        if worker_counts is None:
            logger.warn("A worker failed to return data.")
        else:
            all_keys = set(total_counters.keys()) | set(worker_counts.keys())
            for key in all_keys:
                total_counters[key] += worker_counts[key]

    groups = list(total_counters.keys())
    actions = set()
    for group in groups:
        actions |= set(total_counters[group].keys())

    msg = ["Action summary:", "\t".join(("group", "action".ljust(9), "count"))]
    for group in groups:
        for action in actions:
            msg.append(
                "\t".join(
                    (
                        str(x)
                        for x in (
                            group,
                            str(action).ljust(9),
                            total_counters[group][action],
                        )
                    )
                )
            )
    msg = "\n".join(msg)
    logger.info(msg)
