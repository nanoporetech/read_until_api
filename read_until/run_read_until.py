import argparse
from collections import Counter
import logging
import queue
import sys
import time
import uuid

import numpy

import minknow


class ReadUntil(object):
    ALLOWED_MIN_CHUNK_SIZE = 4000

    def __init__(self, mk_rpc_port=8004):
        """A basic Read Until client.

        :param mk_rpc_port: MinKNOW gRPC port.

        """
        self.logger = logging.getLogger('ReadUntil')

        self.logger.info('Creating rpc connection on port {}.'.format(mk_rpc_port))
        self.connection = minknow.rpc.Connection(port=mk_rpc_port)
        self.logger.info('Got rpc connection.')
        self.msgs = self.connection.data._pb
        self.device = minknow.Device(self.connection)

        self.signal_dtype = self.device.numpy_data_types.calibrated_signal
        self.action_queue = None


    def run(self, runner_kwargs={'run_time':30}):
        """Run Read Until analysis.

        :param runner_kwargs: kwargs for ._runner() method.

        """

        # the action_queue is used to store unblock/stop_receiving_data
        #    requests before they are put on the gRPC stream.
        self.action_queue = queue.Queue()

        # .get_live_reads() takes an iterable of requests and generates
        #    raw data chunks and responses to our requests: the iterable
        #    thereby controls the lifetime of the stream. ._runner() as
        #    implemented below initialises the stream then transfers
        #    action requests from the action_queue to the stream.
        reads = self.connection.data.get_live_reads(
            self._runner(**runner_kwargs)
        )

        # ._process_reads() as implemented below is responsible for
        #    placing action requests on the queue and logging the responses
        self._process_reads(reads)

        self.action_queue = None
        logging.info("Finished run.")


    def aquisition_progress(self):
        """Get MinKNOW data acquisition progress.

        :returns: a structure with attributes .acquired and .processed.
        """
        return self.connection.acquisition.get_progress().raw_per_channel


    def _put_action(self, read_channel, read_number, action):
        """Stores an action requests on the queue ready to be placed on the
        gRPC stream.

        :param read_channel: a read's channel number.
        :param read_number: a read's read number (the nth read per channel).
        :param action: either 'stop_further_data' or 'unblock'.

        """
        #TODO: refactor this to allow placing multiple actions simultaneously
        action_id = str(uuid.uuid4())
        action_kwargs = {
            'action_id': action_id,
            'channel': read_channel,
            'number': read_number,
        }
        if action == 'stop_further_data':
            action_kwargs[action] = self.msgs.GetLiveReadsRequest.StopFurtherData()
        elif action == 'unblock':
            action_kwargs[action] = self.msgs.GetLiveReadsRequest.UnblockAction()
        else:
            raise ValueError("'action' parameter must must be 'stop_further_data' or 'unblock'.")
        
        action_request = self.msgs.GetLiveReadsRequest.Action(**action_kwargs)
        action_group = self.msgs.GetLiveReadsRequest(
            actions=self.msgs.GetLiveReadsRequest.Actions(actions=[action_request])
        )
        self.action_queue.put(action_group)
        self.logger.debug('Action {} on channel {}, read {} : {}'.format(
            action_id, read_channel, read_number, action
        ))


    def _runner(self, run_time, first_channel=1, last_channel=512, min_chunk_size=1000):
        """Yield the stream initializer request followed by action requests
        placed into the action_queue.


        :param run_time: maximum time for which to yield actions.
        :param first_channel: lowest channel for which to receive raw data.
        :param last_channel: highest channel (inclusive) for which to receive data.
        :param min_chunk_size: minimum number of raw samples in an raw data chunk.
        """
        timeout_pt = time.time() + run_time

        if min_chunk_size > self.ALLOWED_MIN_CHUNK_SIZE:
            self.logger.info("Reducing min_chunk_size to {}".format(self.ALLOWED_MIN_CHUNK_SIZE))
            min_chunk_size = self.ALLOWED_MIN_CHUNK_SIZE

        self.logger.info("Sending init command")
        yield self.msgs.GetLiveReadsRequest(
            setup=self.msgs.GetLiveReadsRequest.StreamSetup(
                first_channel=first_channel,
                last_channel=last_channel,
                raw_data_type=self.msgs.GetLiveReadsRequest.CALIBRATED,
                sample_minimum_chunk_size=min_chunk_size
            )
        )

        self.logger.info("Running Read Until for {} seconds.".format(run_time))
        while time.time() < timeout_pt:
            try:
                action = self.action_queue.get()
            except queue.Empty:
                continue
            else:
                yield action

        self.logger.info("Stream finished after timeout.")


    def _unblock_read(self, read_channel, read_number):
        self._put_action(read_channel, read_number, 'unblock')


    def _stop_receiving_read(self, read_channel, read_number):
        self._put_action(read_channel, read_number, 'stop_further_data')


    def _process_reads(self, reads):
        """Process the gRPC stream data.

        :param reads: gRPC data stream iterable as produced by get_live_reads().
        
        .. note:: This serves as an example only. 
        """

        response_counter = Counter()

        read_count = 0
        samples_behind = 0
        unique_reads = set()
        raw_data_bytes = 0
        strand_like = 0

        last_msg_time = time.time()
        for reads_chunk in reads:

            # In each iteration, we get:
            #   i) responses to our previous actions (success/fail)
            #  ii) raw data for current reads

            # record a count of success and fails            
            if len(reads_chunk.action_reponses):
                for response in reads_chunk.action_reponses:
                    response_counter[response.response] += 1

            progress = self.aquisition_progress()

            for read_channel in reads_chunk.channels:
                read_count += 1
                read = reads_chunk.channels[read_channel]
                unique_reads.add(read.id)
                read_samples_behind = progress.acquired - read.chunk_start_sample
                samples_behind += read_samples_behind

                # convert the read data into a numpy array of correct type
                raw_data_bytes += len(read.raw_data)
                typed_data = numpy.fromstring(read.raw_data, self.signal_dtype)
                read.raw_data = bytes('', 'utf-8') # we don't need this now
                logging.debug("Got live read data for channel {}-{}: {} samples behind head, {} processed".format(
                     read_channel, read.number, read_samples_behind, progress.processed
                ))

                # make a decision to:
                #   i) stop recieving data for a read (leaves the read unaffected)
                #  ii) unblock read, or
                # iii) by implication do nothing (may receive more data in future)
                if read.median_before > read.median and (read.median_before - read.median) > 60:
                    # record a strand and queue request to stop recieving data
                    strand_like += 1
                    self._stop_receiving_read(read_channel, read.number)
                else:
                    # queue request to unblock read
                    #self._unblock_read(read_channel, read.number)
                    pass

            now = time.time()
            if last_msg_time + 1 < now:
                self.logger.info(
                    "Seen {} read sections total {} unique reads, "
                    "{} strand like reads, average of {} samples "
                    "behind acquisition. {:.2f} MB raw data"
                    .format(
                        read_count, len(unique_reads), strand_like,
                        samples_behind/read_count, float(raw_data_bytes)/1000/1000
                    )
                )
                self.logger.info("Response summary: {}".format(response_counter))

                raw_data_bytes = 0
                last_msg_time = now


def _get_parser():
    parser = argparse.ArgumentParser('Read until with alignment filter.')
    parser.add_argument('--port', type=int, default=8004,
        help='MinKNOW server gRPC port.')
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


def main():
    args = _get_parser().parse_args() 

    logging.basicConfig(format='[%(asctime)s - %(name)s] %(message)s',
        datefmt='%H:%M:%S', level=args.log_level)

    read_until_client = ReadUntil(mk_rpc_port=args.port)
    read_until_client.run()


if __name__ == "__main__":
    main()

