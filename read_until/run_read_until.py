import logging
import numpy
#import Queue
import queue
import sys
import time
import uuid

import minknow

action_queue = queue.Queue()

action_requests = {
    'unblock': 'UnblockAction',
    'stop_further_data': 'StopFurtherData'
}


def run_read_until(device, connection, run_time):

    msgs = connection.data._pb
    reads = connection.data.get_live_reads(read_until_instructions(msgs, run_time))
    process_reads(connection, device, msgs, reads)


def read_until_instructions(msgs, run_time):
    """ 
        Manage action queue + read requests instructions for MinKNOW 
    """

    timeout_pt = time.time() + run_time
    logging.info("Sending init command")
    yield msgs.GetLiveReadsRequest(
        setup=msgs.GetLiveReadsRequest.StreamSetup(
            first_channel=1,
            last_channel=512,
            raw_data_type=msgs.GetLiveReadsRequest.CALIBRATED,
            sample_minimum_chunk_size=1000
        )
    )

    while time.time() < timeout_pt:
        try:
            action = action_queue.get()
        except queue.Empty:
            continue

        logging.debug("Sending action {}".format(action.Action.channel))
        yield action

    logging.info("Done reading actions")



def process_reads(connection, device, msgs, reads):
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
    signal_dtype = device.numpy_data_types.calibrated_signal
    for reads_chunk in reads:
        
        progress = connection.acquisition.get_progress() #Info on how much data has been acquired, processed and written.
            
        for read_channel in reads_chunk.channels:
            read = reads_chunk.channels[read_channel]

            typed_data = numpy.fromstring(read.raw_data, signal_dtype)
            raw_data_bytes += len(read.raw_data)
            read.raw_data = ""
            #logging.info("Got live read data for channel {}-{}: {} samples behind head, {} processed"
            #     .format(read_channel, read.number, progress.raw_per_channel.acquired-read.chunk_start_sample, progress.raw_per_channel.processed))

            read_count += 1
            samples_behind += (progress.raw_per_channel.acquired - read.chunk_start_sample)
            unique_reads.add(read.id)

            if is_strand(read): 
                strand_like += 1
                #Process read, ReadRequest 
                logging.info("raw {}".format(typed_data[0:5]))

            #stop_request(msgs, read_channel, read)
            if read_channel % 2 == 0:
                unblock_request(msgs, read_channel, read)

        now = time.time()
        if last_msg_time + 1 < now:
            logging.info("Seen {} read sections total {} unqiue reads, {} strand like reads, average of {} samples behind acquisition. {:.2f} MB raw data"
                .format(read_count, len(unique_reads), strand_like, samples_behind/read_count, float(raw_data_bytes)/1000/1000))

            raw_data_bytes = 0
            last_msg_time = now

        #if len(reads_chunk.action_reponses):
        #    logging.info("Got responses {}".format(reads_chunk.action_reponses))



def stop_request(msgs, read_channel, read):

    # /Applications/MinKNOW.app/Contents/Resources/ont-python/lib/python2.7/site-packages/minknow/rpc/data_pb2.py  
    action = msgs.GetLiveReadsRequest.Action(
    action_id=str(uuid.uuid4()),
    channel=read_channel,
    number=read.number,
    stop_further_data=msgs.GetLiveReadsRequest.StopFurtherData()
    )

    action_group = msgs.GetLiveReadsRequest(
        actions=msgs.GetLiveReadsRequest.Actions(actions=[action])
    )
    action_queue.put(action_group)

    
def unblock_request(msgs, read_channel, read):

    action = msgs.GetLiveReadsRequest.Action(
    action_id=str(uuid.uuid4()),
    channel=read_channel,
    number=read.number,
    unblock=msgs.GetLiveReadsRequest.UnblockAction()
    )

    action_group = msgs.GetLiveReadsRequest(
        actions=msgs.GetLiveReadsRequest.Actions(actions=[action])
    )
    action_queue.put(action_group)



def is_strand(read):
    if read.median_before > read.median and (read.median_before - read.median) > 60:
        return True
    else:
        return False
    


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    # setting of environment var MINKNOW_RPC_PORT required for port to be found during run_time. For now hardcode/set on command line
    connection = minknow.rpc.Connection(port=8004) #connection to MinKNOW via RPC
    device = minknow.Device(connection) #info about and control the attached device

    logging.info("Starting Read Until")
    run_read_until(device, connection, 10)
    logging.info("Finished Read Until")


if __name__ == "__main__":
    main()

