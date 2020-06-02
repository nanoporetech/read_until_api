"""Simple example to read data from read until and send responses to server"""

import argparse
import functools
import logging
import time
from collections import defaultdict, Counter

import numpy as np

from read_until import AccumulatingCache, ReadUntilClient
from pyguppy_client_lib.pyclient import PyGuppyClient
from pyguppy_client_lib.helper_functions import package_read
from read_until.examples.example_utils import run_workflow


def basecall(
    Caller: PyGuppyClient, reads: list, dtype: "np.dtype", daq_values: dict,
):
    """Generator that sends and receives data from guppy

    :param caller: pyguppy_client_lib.pyclient.PyGuppyClient
    :param reads: List of reads from read_until
    :type reads: Iterable
    :param dtype:
    :param daq_values:

    :returns:
        - read_info (:py:class:`tuple`) - channel (int), read number (int)
        - read_data (:py:class:`dict`) - Data returned from Guppy
    :rtype: Iterator[tuple[tuple, dict]]
    """

    # with Caller as caller:
    caller = Caller
    done = 0
    hold = {}
    sent = 0

    for channel, read in reads:
        hold[read.id] = (channel, read.number)
        t0 = time.time()
        success = caller.pass_read(
            package_read(
                read_id=read.id,
                raw_data=np.frombuffer(read.raw_data, dtype),
                daq_offset=daq_values[channel].offset,
                daq_scaling=daq_values[channel].scaling,
            )
        )
        if not success:
            logging.warning("Skipped a read: {}".format(read.id))
            hold.pop(read.id)
            continue

        t = time.time() - t0
        # 1/100th second
        if t < caller.throttle:
            time.sleep(caller.throttle - t)
        sent += 1

    while done < sent:
        t0 = time.time()
        results = caller.get_completed_reads()

        if not results:
            time.sleep(caller.throttle)

        for read in results:
            yield hold.pop(read["metadata"]["read_id"]), read
            done += 1
            t = time.time() - t0
            if t < caller.throttle:
                time.sleep(caller.throttle - t)


def get_parser():
    """Build argument parser for example"""
    parser = argparse.ArgumentParser(
        prog="Enrichment/Depletion demo ({})".format(__file__),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--enrich",
        help="Enrich targets in the index or, if specified, the bed file",
        action="store_true",
    )
    group.add_argument(
        "--deplete",
        help="Deplete targets in the index or, if specified, the bed file",
        action="store_true",
    )

    parser.add_argument("--alignment-index-file", type=str, required=True)
    parser.add_argument("--bed-file", type=str, default="")

    parser.add_argument(
        "--host", default="127.0.0.1", help="MinKNOW server host address"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="MinKNOW gRPC server port"
    )

    parser.add_argument(
        "--guppy-host",
        default="127.0.0.1",
        help="Guppy server host address",
        # required=True,
    )
    parser.add_argument(
        "--guppy-port", type=int, default=5555, help="Guppy server port", required=True,
    )
    parser.add_argument(
        "--guppy-config",
        default="dna_r9.4.1_450bps_fast",
        help="Guppy server config",
        # required=True,
    )

    parser.add_argument("--workers", default=1, type=int, help="worker threads")
    parser.add_argument(
        "--analysis_delay",
        type=int,
        default=0,
        help="Period to wait before starting analysis",
    )
    parser.add_argument(
        "--run_time", type=int, default=30, help="Period to run the analysis"
    )
    parser.add_argument(
        "--unblock_duration",
        type=float,
        default=0.1,
        help="Time (in seconds) to apply unblock voltage",
    )
    parser.add_argument(
        "--one_chunk", action="store_true", help="Minimum read chunk size to receive",
    )
    parser.add_argument(
        "--batch-size",
        default=None,
        type=int,
        help="Number of reads to get from ReadCache each iteration. If not set uses number of channels on device",
    )
    parser.add_argument(
        "--throttle",
        default=0.1,
        type=float,
        help="Time to wait between requesting successive read batches from the ReadCache",
    )
    parser.add_argument(
        "--min-chunks",
        default=0,
        type=int,
        help="The minimum number of chunks to consider before unblocking",
    )
    parser.add_argument(
        "--max-chunks",
        default=2,
        type=int,
        help="The maximum number of chunks to consider before unblocking",
    )
    return parser


def analysis(
    client: ReadUntilClient,
    caller: PyGuppyClient,
    enrich: bool,
    deplete: bool,
    batch_size: int,
    throttle: float = 0.1,
    unblock_duration: float = 0.1,
    min_chunks: int = 0,
    max_chunks: int = 2,
):
    """

    :param client: an instance of a `ReadUntilClient` object.
    :param caller: PyGuppyClient
    :param enrich: Enrich targets in the index or bed file
    :param deplete: Deplete targets in the index or bed file
    :param batch_size: number of reads to pull from `client` at a time.
    :param delay: number of seconds to wait before starting analysis.
    :param throttle: minimum interval between requests to `client`.
    :param unblock_duration: time in seconds to apply unblock voltage.

    """
    logger = logging.getLogger("Analysis")
    # Get whether a bed file is in use from the pyguppy caller
    bed_file = bool(caller.params.get("bed_file", False))
    action = ""

    action_funcs = {
        "stop_receiving": client.stop_receiving_read,
        "unblock": lambda c, n: client.unblock_read(c, n, unblock_duration),
    }

    # Count how many times we've seen a read
    read_counter = defaultdict(Counter)

    while client.is_running:
        time_begin = time.time()
        # get the most recent read chunks from the client
        called_batch = basecall(
            Caller=caller,
            reads=client.get_read_chunks(batch_size=50, last=True),
            dtype=client.signal_dtype,
            daq_values=client.calibration_values,
        )

        i = 0
        t0 = time.time()
        # for (c, n), r in called_batch:
        #     i += 1

        # for channel, read in client.get_read_chunks(batch_size=batch_size, last=True):
        for (channel, read_number), read in called_batch:

            # Count the number of times a read is seen
            if read_number not in read_counter[channel]:
                read_counter[channel].clear()
            read_counter[channel][read_number] += 1
            i += 1

            if enrich:
                if bed_file:
                    # Check for bed file associated keys
                    hits = read.get("metadata", {}).get("alignment_bed_hits", 0)
                    if hits > 0:
                        # Hits in bed file
                        client.stop_receiving_read(channel, read_number)
                        action = "stop_receiving"
                    else:
                        # Probably don't want to instantly unblock if the read
                        #   didn't hit a bed line
                        client.unblock_read(
                            channel, read_number, duration=unblock_duration
                        )
                        action = "unblock"
                else:
                    # No bed file, check if alignments
                    hits = read.get("metadata", {}).get("alignment_genome", False)
                    if hits and hits != "*":
                        # Hits in alignment index file
                        client.stop_receiving_read(channel, read_number)
                        action = "stop_receiving"
                    else:
                        # Probably don't want to instantly unblock...
                        client.unblock_read(channel, read_number)
                        action = "unblock"
            elif deplete:
                if bed_file:
                    # Check for bed file associated keys
                    hits = read.get("metadata", {}).get("alignment_bed_hits", 0)
                    if hits > 0:
                        client.unblock_read(channel, read_number)
                        action = "unblock"
                    else:
                        client.stop_receiving_read(channel, read_number)
                        action = "stop_receiving"
                else:
                    # No bed file, check if alignments
                    hits = read.get("metadata", {}).get("alignment_genome", False)
                    if hits and hits != "*":
                        client.unblock_read(channel, read_number)
                        action = "unblock"
                    else:
                        client.stop_receiving_read(channel, read_number)
                        action = "stop_receiving"
            else:
                raise ValueError("Somehow both enrich/deplete are False!")

            # TODO: Evaluate the number of times a read is seen
            #       e.g. above or below chunk thresholds before
            #       sending unblock/stop_receiving
            action_func = action_funcs[action]
            action_func(channel, read_number)
            # logger.info("{}:{}".format(action, read["metadata"]["read_id"]))

        if i:
            logger.info("{i:>3} - {t:.6f}".format(i=i, t=time.time() - t0))

        # limit the rate at which we make requests
        time_end = time.time()
        if time_begin + throttle > time_end:
            time.sleep(throttle + time_begin - time_end)

    else:
        caller.disconnect()

    caller.disconnect()
    return


def main(argv=None):
    """simple example main cli entrypoint"""
    args = get_parser().parse_args(argv)

    print(args)

    logging.basicConfig(
        format="[%(asctime)s - %(name)s] %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )

    read_until_client = ReadUntilClient(
        mk_host=args.host,
        mk_port=args.port,
        cache_type=AccumulatingCache,
        one_chunk=False,
        filter_strands=True,
        # Request uncalibrated, int16, signal
        calibrated_signal=False,
    )

    # Handle arg cases:
    if args.batch_size is None:
        args.batch_size = read_until_client.channel_count

    caller = PyGuppyClient(
        address="{}:{}".format(args.guppy_host, args.guppy_port),
        config="dna_r9.4.1_450bps_fast",
        # daq_values=read_until_client.calibration_values,
        # TODO: Check that provided file exists on this disk?
        alignment_index_file=args.alignment_index_file,
        # FIXME: A little bit hacky, need to determine exactly what the
        #   guppy server can/cannot accept as a bed file. Bools doesn't
        #   play too nicely and cause the alignment file to get dropped
        bed_file=args.bed_file if args.bed_file else "",
        # TODO: Change hardcoded timeout
        server_file_load_timeout=180,  # 180 == 3 minutes, should be enough?
    )

    # This will block until the guppy server has loaded the model, index,
    #   and bed file to get around this, we could init pyguppy in another
    #   thread
    caller.connect()
    # caller.disconnect()

    analysis_worker = functools.partial(
        analysis,
        client=read_until_client,
        caller=caller,
        enrich=args.enrich,
        deplete=args.deplete,
        batch_size=args.batch_size,
        # delay=args.analysis_delay,
        unblock_duration=args.unblock_duration,
        min_chunks=args.min_chunks,
        max_chunks=args.max_chunks,
    )

    run_workflow(read_until_client, analysis_worker, args.workers, args.run_time)


if __name__ == "__main__":
    main()
