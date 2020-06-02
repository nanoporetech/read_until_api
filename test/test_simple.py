"""Test simple read until functionality"""

import numpy
import pytest

import read_until
from minknow_api import data_pb2

from .read_until_test_server import ReadUntilTestServer
from .test_utils import wait_until


def test_bad_setup():
    """Test setup fails correctly with bad input"""
    test_server = ReadUntilTestServer()

    with test_server:
        # Bad port
        with pytest.raises(Exception):
            read_until.ReadUntilClient(
                mk_host="localhost", mk_port=test_server.port + 1
            )

        # Bad prefilter_classes input
        with pytest.raises(ValueError):
            read_until.ReadUntilClient(
                mk_host="localhost",
                mk_port=test_server.port,
                filter_strands=True,
                prefilter_classes=4,
            )


def test_setup():
    """Test client setup messages"""
    test_server = ReadUntilTestServer()
    test_server.start()
    client = read_until.ReadUntilClient(mk_host="localhost", mk_port=test_server.port)

    try:
        client.run(first_channel=4, last_channel=100)

        wait_until(lambda: len(test_server.data_service.live_reads_requests) > 0)
        assert test_server.data_service.live_reads_requests
        assert test_server.data_service.live_reads_requests[0].setup.first_channel == 4
        assert test_server.data_service.live_reads_requests[0].setup.last_channel == 100

    finally:
        client.reset()
        test_server.stop(0)


def test_response():
    """Test client response"""
    input_channel = 4
    input_read_response = data_pb2.GetLiveReadsResponse.ReadData(
        id="test-read",
        number=1,
        start_sample=0,
        chunk_start_sample=0,
        chunk_length=100,
        chunk_classifications=[83],
        raw_data=numpy.random.random(100).astype(dtype="f4").tobytes(),
        median_before=100,
        median=150,
    )

    test_server = ReadUntilTestServer()
    test_server.start()
    test_server.data_service.add_response(
        data_pb2.GetLiveReadsResponse(channels={input_channel: input_read_response})
    )

    client = read_until.ReadUntilClient(mk_host="localhost", mk_port=test_server.port)

    try:
        client.run(first_channel=4, last_channel=100)

        wait_until(lambda: len(test_server.data_service.live_reads_requests) >= 1)

        read_count = 0
        for channel, read in client.get_read_chunks():
            assert channel == input_channel
            assert read.SerializeToString() == input_read_response.SerializeToString()
            read_count += 1
            client.unblock_read(channel, read.number)

            wait_until(lambda: len(test_server.data_service.live_reads_requests) >= 2)
            break
        assert read_count == 1

        unblock_request = test_server.data_service.live_reads_requests[-1]
        assert len(unblock_request.actions.actions) == 1
        assert unblock_request.actions.actions[0].channel == input_channel
        assert unblock_request.actions.actions[0].number == input_read_response.number

    finally:
        client.reset()

    assert test_server.data_service.find_response_times()[0] < 0.05  # 50ms round trip
    test_server.stop(0)
