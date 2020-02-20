import argparse
import concurrent.futures
import functools
import logging
from multiprocessing.pool import ThreadPool
from multiprocessing import TimeoutError
import signal
import sys
import traceback
import time

import numpy

import read_until


class ThreadPoolExecutorStackTraced(concurrent.futures.ThreadPoolExecutor):
    """ThreadPoolExecutor records only the text of an exception,
    this class will give back a bit more."""

    def submit(self, fn, *args, **kwargs):
        """Submits the wrapped function instead of `fn`"""
        return super(ThreadPoolExecutorStackTraced, self).submit(
            self._function_wrapper, fn, *args, **kwargs
        )

    def _function_wrapper(self, fn, *args, **kwargs):
        """Wraps `fn` in order to preserve the traceback of any kind of
        raised exception

        """
        try:
            return fn(*args, **kwargs)
        except Exception:
            raise sys.exc_info()[0](traceback.format_exc())


def ignore_sigint():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _get_parser():
    parser = argparse.ArgumentParser("Read until API demonstration..")
    parser.add_argument("--host", default="127.0.0.1", help="MinKNOW server host.")
    parser.add_argument(
        "--port", type=int, default=8000, help="MinKNOW gRPC server port."
    )
    parser.add_argument("--workers", default=1, type=int, help="worker threads.")
    parser.add_argument(
        "--analysis_delay",
        type=int,
        default=1,
        help="Period to wait before starting analysis.",
    )
    parser.add_argument(
        "--run_time", type=int, default=30, help="Period to run the analysis."
    )
    parser.add_argument(
        "--unblock_duration",
        type=float,
        default=0.1,
        help="Time (in seconds) to apply unblock voltage.",
    )
    parser.add_argument(
        "--one_chunk",
        default=False,
        action="store_true",
        help="Minimum read chunk size to receive.",
    )
    parser.add_argument(
        "--min_chunk_size",
        type=int,
        default=2000,
        help="Minimum read chunk size to receive. NOTE: this functionality "
        "is currently disabled; read chunks received will be unfiltered.",
    )
    parser.add_argument(
        "--debug",
        help="Print all debugging information",
        action="store_const",
        dest="log_level",
        const=logging.DEBUG,
        default=logging.WARNING,
    )
    parser.add_argument(
        "--verbose",
        help="Print verbose messaging.",
        action="store_const",
        dest="log_level",
        const=logging.INFO,
    )
    return parser


def simple_analysis(client, batch_size=10, delay=1, throttle=0.1, unblock_duration=0.1):
    """A simple demo analysis leveraging a `ReadUntilClient` to manage
    queuing and expiry of read data.

    :param client: an instance of a `ReadUntilClient` object.
    :param batch_size: number of reads to pull from `client` at a time.
    :param delay: number of seconds to wait before starting analysis.
    :param throttle: minimum interval between requests to `client`.
    :param unblock_duration: time in seconds to apply unblock voltage.

    """

    logger = logging.getLogger("Analysis")
    logger.warn(
        "Initialising simple analysis. "
        "This will likely not achieve anything useful. "
        "Enable --verbose or --debug logging to see more."
    )
    # we sleep a little simply to ensure the client has started initialised
    logger.info("Starting analysis of reads in {}s.".format(delay))
    time.sleep(delay)

    while client.is_running:
        t0 = time.time()
        # get the most recent read chunks from the client
        read_batch = client.get_read_chunks(batch_size=batch_size, last=True)
        for channel, read in read_batch:
            # convert the read data into a numpy array of correct type
            raw_data = numpy.fromstring(read.raw_data, client.signal_dtype)
            read.raw_data = bytes("", "utf8")

            # make a decision that the read is good at we don't need more data?
            if (
                read.median_before > read.median
                and read.median_before - read.median > 60
            ):
                client.stop_receiving_read(channel, read.number)
            # we can also call the following for reads we don't like
            client.unblock_read(channel, read.number, duration=unblock_duration)

        # limit the rate at which we make requests
        t1 = time.time()
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)
    else:
        logger.info("Finished analysis of reads as client stopped.")


def run_workflow(client, analysis_worker, n_workers, run_time, runner_kwargs=dict()):
    """Run an analysis function against a ReadUntilClient.

    :param client: `ReadUntilClient` instance.
    :param analysis worker: a function to process reads. It should exit in
        response to `client.is_running == False`.
    :param n_workers: number of incarnations of `analysis_worker` to run.
    :param run_time: time (in seconds) to run workflow.
    :param runner_kwargs: keyword arguments for `client.run()`. 

    :returns: a list of results, on item per worker.

    """
    logger = logging.getLogger("Manager")

    results = []
    pool = ThreadPool(n_workers)  # initializer=ignore_sigint)
    logger.info("Creating {} workers".format(n_workers))
    try:
        # start the client
        client.run(**runner_kwargs)
        # start a pool of workers
        for _ in range(n_workers):
            results.append(pool.apply_async(analysis_worker))
        pool.close()
        # wait a bit before closing down
        time.sleep(run_time)
        logger.info("Sending reset")
        client.reset()
        pool.join()
    except KeyboardInterrupt:
        logger.info("Caught ctrl-c, terminating workflow.")
        client.reset()

    # collect results (if any)
    collected = []
    for result in results:
        try:
            res = result.get(3)
        except TimeoutError:
            logger.warn("Worker function did not exit successfully.")
            collected.append(None)
        except Exception as e:
            logger.warn("Worker raise exception: {}".format(repr(e)))
        else:
            logger.info("Worker exited successfully.")
            collected.append(res)
    pool.terminate()
    return collected


def main():
    args = _get_parser().parse_args()

    logging.basicConfig(
        format="[%(asctime)s - %(name)s] %(message)s",
        datefmt="%H:%M:%S",
        level=args.log_level,
    )

    read_until_client = read_until.ReadUntilClient(
        mk_host=args.host,
        mk_port=args.port,
        one_chunk=args.one_chunk,
        filter_strands=True,
    )

    analysis_worker = functools.partial(
        simple_analysis,
        read_until_client,
        delay=args.analysis_delay,
        unblock_duration=args.unblock_duration,
    )

    results = run_workflow(
        read_until_client,
        analysis_worker,
        args.workers,
        args.run_time,
        runner_kwargs={"min_chunk_size": args.min_chunk_size},
    )
    # simple analysis doesn't return results
