import argparse
import concurrent.futures
import logging
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
            self._function_wrapper, fn, *args, **kwargs)


    def _function_wrapper(self, fn, *args, **kwargs):
        """Wraps `fn` in order to preserve the traceback of any kind of
        raised exception

        """
        try:
            return fn(*args, **kwargs)
        except Exception:
            raise sys.exc_info()[0](traceback.format_exc())


def _get_parser():
    parser = argparse.ArgumentParser('Read until API demonstration..')
    parser.add_argument('--port', type=int, default=8000,
        help='MinKNOW server port.')
    parser.add_argument('--workers', default=1, type=int,
        help='worker threads.')
    parser.add_argument('--analysis_delay', type=int, default=1,
        help='Period to wait before starting analysis.')
    parser.add_argument('--run_time', type=int, default=30,
        help='Period to run the analysis.')
    parser.add_argument('--one_chunk', default=False, action='store_true',
        help='Minimum read chunk size to receive.')
    parser.add_argument('--min_chunk_size', type=int, default=2000,
        help='Minimum read chunk size to receive.')
    parser.add_argument(
        '--debug', help="Print all debugging information",
        action="store_const", dest="log_level",
        const=logging.DEBUG, default=logging.WARNING,
    )
    parser.add_argument(
        '--verbose', help="Print verbose messaging.",
        action="store_const", dest="log_level",
        const=logging.INFO,
    )
    return parser


def simple_analysis(client, batch_size=10, delay=1, throttle=0.1):
    """A simple demo analysis leveraging a `ReadUntilClient` to manage
    queuing and expiry of read data.

    :param client: an instance of a `ReadUntilClient` object.
    :param batch_size: number of reads to pull from `client` at a time.
    :param delay: number of seconds to wait before starting analysis.
    :param throttle: minimum interval between requests to `client`.
    """

    logger = logging.getLogger('Analysis')
    logger.warn(
        'Initialising simple analysis. '
        'This will likely not achieve anything useful. '
        'Enable --verbose or --debug logging to see more.'
    )
    # we sleep a little simply to ensure the client has started initialised
    logger.info('Starting analysis of reads in {}s.'.format(delay))
    time.sleep(delay)

    while client.is_running:
        t0 = time.time()
        # get the most recent read chunks from the client
        read_batch = client.get_read_chunks(batch_size=batch_size, last=True)
        for channel, read in read_batch:
            # convert the read data into a numpy array of correct type
            raw_data = numpy.fromstring(read.raw_data, client.signal_dtype)
            read.raw_data = read_until.NullRaw

            # make a decision that the read is good at we don't need more data?
            if read.median_before > read.median and \
               read.median_before - read.median > 60:
                client.stop_receiving_read(channel, read.number)
            # we can also call the following for reads we don't like
            #client.unblock_read(channel, read.number)

        # limit the rate at which we make requests            
        t1 = time.time()
        if t0 + throttle > t1:
            time.sleep(throttle + t0 - t1)
 
    logger.info('Finished analysis of reads.')


def main():
    args = _get_parser().parse_args() 

    logging.basicConfig(format='[%(asctime)s - %(name)s] %(message)s',
        datefmt='%H:%M:%S', level=args.log_level)
    logger = logging.getLogger('Manager')

    read_until_client = read_until.ReadUntilClient(
        mk_port=args.port, one_chunk=args.one_chunk, filter_strands=True)

    # this somewhat assumes we get at least two threads ;)
    with ThreadPoolExecutorStackTraced() as executor:
        futures = list()
        futures.append(executor.submit(
            read_until_client.run, runner_kwargs={
                'run_time':args.run_time, 'min_chunk_size':args.min_chunk_size
            }
        ))
        for _ in range(args.workers):
            futures.append(executor.submit(
                simple_analysis, read_until_client, delay=args.analysis_delay
            ))

        for f in concurrent.futures.as_completed(futures):
            if f.exception() is not None:
                logger.warning(f.exception())
