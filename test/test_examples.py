"""Testing for example code"""

import logging
from minknow_api import data_pb2
import numpy
import random
import sys
from threading import Thread
import time

import read_until.examples.simple
from .read_until_test_server import ReadUntilTestServer


def test_example_simple():
    """Test simple example runs and produces actions on all reads"""
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    test_server = ReadUntilTestServer()
    test_server.start()

    def example_main(test_server):

        read_until.examples.simple.main(
            [
                "--host",
                "localhost",
                "--port",
                str(test_server.port),
                "--ca-cert",
                str(test_server.ca_cert_path),
                "--run_time",
                "30",
            ]
        )

    run_thread = Thread(target=example_main, args=(test_server,))
    run_thread.start()

    read_number = 1
    sample_number = 0

    # Create ReadData objects that populate a queue in the ReadUntilTestServer,
    #   specifically ReadUntilTestServer.data_service.live_reads_responses_to_send.
    #   This queue of objects is simultaneously consumed by the run_thread which is
    #   running the simple read until example.
    channel_count = 512
    read_count = channel_count
    for channel in range(channel_count):
        sample_length = random.randint(1000, 3000)
        input_read_response = data_pb2.GetLiveReadsResponse.ReadData(
            id="test-read-" + str(read_number),
            start_sample=sample_number,
            chunk_start_sample=sample_number,
            chunk_length=sample_length,
            chunk_classifications=[83],
            raw_data=numpy.random.random(sample_length).astype(dtype="f4").tobytes(),
            median_before=random.uniform(
                200, 250
            ),  # guarantee > 60 pa delta - simple treats this as a read.
            median=random.uniform(100, 120),
        )
        read_number += random.randint(1, 4)
        sample_number += random.randint(1, 10000)

        test_server.data_service.add_response(
            data_pb2.GetLiveReadsResponse(channels={channel: input_read_response})
        )
        time.sleep(0.01)

    # Wait for server to deal with input
    time.sleep(1)

    logging.info("Kill get_live_reads calls and wait for example to terminate")
    test_server.data_service.terminate_live_reads()
    run_thread.join()

    unblock_count = 0
    stop_count = 0
    for resp in test_server.data_service.live_reads_requests:
        for action in resp.actions.actions:
            if action.HasField("unblock"):
                unblock_count += 1
            elif action.HasField("stop_further_data"):
                stop_count += 1

    # As we dont overlap reads on the same channel and we always guarantee good deltas we expect
    # all reads to get unblocked and stopped.
    logging.info("Stops: %s, Unblocks: %s", stop_count, unblock_count)
    assert unblock_count == read_count
    assert stop_count == read_count
    test_server.stop(0)


def test_example_simple_random():
    """Test simple example runs and produces actions on all reads"""
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    test_server = ReadUntilTestServer()
    test_server.start()

    def example_main(test_server):
        read_until.examples.simple.main(
            [
                "--host",
                "localhost",
                "--port",
                str(test_server.port),
                "--ca-cert",
                str(test_server.ca_cert_path),
                "--run_time",
                "60",
            ]
        )

    run_thread = Thread(target=example_main, args=(test_server,))
    run_thread.start()

    read_number = 1
    sample_number = 0

    read_count = 2000
    for _ in range(read_count):
        sample_length = random.randint(1000, 3000)
        input_read_response = data_pb2.GetLiveReadsResponse.ReadData(
            id="test-read-" + str(read_number),
            start_sample=sample_number,
            chunk_start_sample=sample_number,
            chunk_length=sample_length,
            chunk_classifications=[83],
            raw_data=numpy.random.random(sample_length).astype(dtype="f4").tobytes(),
            median_before=random.uniform(
                200, 250
            ),  # guarantee > 60 pa delta - simple treats this as a read.
            median=random.uniform(100, 120),
        )
        read_number += random.randint(1, 4)
        sample_number += random.randint(1, 10000)

        test_server.data_service.add_response(
            data_pb2.GetLiveReadsResponse(
                channels={random.randint(1, 512): input_read_response}
            )
        )
        time.sleep(0.01)

    # Wait for server to deal with input
    time.sleep(1)

    logging.info("Kill get_live_reads calls and wait for example to terminate")
    test_server.data_service.terminate_live_reads()
    run_thread.join()

    unblock_count = 0
    stop_count = 0
    for resp in test_server.data_service.live_reads_requests:
        for action in resp.actions.actions:
            if action.HasField("unblock"):
                unblock_count += 1
            elif action.HasField("stop_further_data"):
                stop_count += 1

    # As we dont overlap reads on the same channel and we always guarantee good deltas we expect
    # all reads to get unblocked and stopped.
    logging.info("Stops: %s, Unblocks: %s", stop_count, unblock_count)
    assert unblock_count > 0.8 * read_count
    assert stop_count == unblock_count

    resp_times = sorted(test_server.data_service.find_response_times())
    resp_time_count = len(resp_times)
    pct10_resp_time = resp_times[int(resp_time_count * 0.1)]
    pct50_resp_time = resp_times[int(resp_time_count * 0.5)]
    pct90_resp_time = resp_times[int(resp_time_count * 0.9)]
    logging.info(
        "Response times %s %s %s %s %s %s",
        resp_time_count,
        resp_times[0],
        pct10_resp_time,
        pct50_resp_time,
        pct90_resp_time,
        resp_times[-1],
    )

    assert pct50_resp_time < 0.2
    assert pct90_resp_time < 1
    test_server.stop(0)


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    test_example_simple_random()
