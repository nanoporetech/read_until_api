import logging
import queue
import sys
import time
import uuid

import numpy

import minknow


class ReadUntil(object):

    def __init__(self, mk_rpc_port=8004):
        self.logger = logging.getLogger('ReadUntil')

        self.connection = minknow.rpc.Connection(port=8004)
        self.msgs = self.connection.data._pb
        self.device = minknow.Device(self.connection)

        self.signal_dtype = self.device.numpy_data_types.calibrated_signal
        self.action_queue = None


    def run(self, run_time=30):
        self.logger.info("Running for {} seconds.".format(time))
        self.action_queue = queue.Queue()
        reads = self.connection.data.get_live_reads(
            self._runner(run_time)
        )
        self._process_reads(reads)
        self.action_queue = None
        logging.info("Finished run.")


    def aquisition_progress(self):
        return self.connection.acquisition.get_progress()


    def _put_action(self, read_channel, read_number, action):
        action_id = str(uuid.uuid4())
        my_action = action
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
        
        action = self.msgs.GetLiveReadsRequest.Action(**action_kwargs)
        action_group = self.msgs.GetLiveReadsRequest(
            actions=self.msgs.GetLiveReadsRequest.Actions(actions=[action])
        )
        self.action_queue.put(action_group)
        self.logger.debug('Action {} on channel {}, read {} : {}'.format(
            action_id, read_channel, read_number, my_action
        ))


    def _runner(self, run_time, first_channel=1, last_channel=512, min_chunk_size=1000):
        timeout_pt = time.time() + run_time

        self.logger.info("Sending init command")
        yield self.msgs.GetLiveReadsRequest(
            setup=self.msgs.GetLiveReadsRequest.StreamSetup(
                first_channel=first_channel,
                last_channel=last_channel,
                raw_data_type=self.msgs.GetLiveReadsRequest.CALIBRATED,
                sample_minimum_chunk_size=min_chunk_size
            )
        )

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
        """
        Iterate reads in queue 
        Construct action + send action request
        """    

        read_count = 0
        samples_behind = 0
        unique_reads = set()
        raw_data_bytes = 0
        strand_like = 0

        last_msg_time = time.time()
        for reads_chunk in reads:
            
            progress = self.aquisition_progress()
                
            for read_channel in reads_chunk.channels:
                read = reads_chunk.channels[read_channel]

                typed_data = numpy.fromstring(read.raw_data, self.signal_dtype)
                raw_data_bytes += len(read.raw_data)
                read.raw_data = bytes("", 'utf-8')
                logging.info("Got live read data for channel {}-{}: {} samples behind head, {} processed"
                     .format(read_channel, read.number, progress.raw_per_channel.acquired-read.chunk_start_sample, progress.raw_per_channel.processed))

                read_count += 1
                samples_behind += (progress.raw_per_channel.acquired - read.chunk_start_sample)
                unique_reads.add(read.id)

                if read.median_before > read.median and (read.median_before - read.median) > 60:
                    strand_like += 1
                    #Process read, ReadRequest 
                    logging.info("raw {}".format(typed_data[0:5]))

                if read_channel % 2 == 0:
                    self._unblock_read(read_channel, read.number)
                else:
                    self._stop_receiving_read(read_channel, read.number)

            now = time.time()
            if last_msg_time + 1 < now:
                logging.info("Seen {} read sections total {} unqiue reads, {} strand like reads, average of {} samples behind acquisition. {:.2f} MB raw data"
                    .format(read_count, len(unique_reads), strand_like, samples_behind/read_count, float(raw_data_bytes)/1000/1000))

                raw_data_bytes = 0
                last_msg_time = now

            if len(reads_chunk.action_reponses):
                logging.info("Got responses {}".format(reads_chunk.action_reponses))
                for response in reads_chunk.action_reponses:
                    print(response.response)


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    read_until_client = ReadUntil()
    read_until_client.run()


if __name__ == "__main__":
    main()

