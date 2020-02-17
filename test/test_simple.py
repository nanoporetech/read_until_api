"""Test simple read until functionality"""

import numpy

import read_until
from read_until.minknow_grpc_api import data_pb2

from read_until_test_server import ReadUntilTestServer
from test_utils import wait_until


def test_setup():
    """Test client setup messages"""
    test_server = ReadUntilTestServer()
    client = read_until.ReadUntilClient(mk_host="localhost", mk_port=test_server.port)

    try:
        client.run(first_channel=4, last_channel=100)

        wait_until(lambda: len(test_server.data_service.live_reads_requests) > 0)
        assert test_server.data_service.live_reads_requests
        assert test_server.data_service.live_reads_requests[0].setup.first_channel == 4
        assert test_server.data_service.live_reads_requests[0].setup.last_channel == 100

    finally:
        client.reset()


def test_response():
    """Test client response"""
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
    test_server.data_service.add_response(
        data_pb2.GetLiveReadsResponse(channels={4: input_read_response})
    )

    client = read_until.ReadUntilClient(mk_host="localhost", mk_port=test_server.port)

    try:
        client.run(first_channel=4, last_channel=100)

        wait_until(lambda: len(test_server.data_service.live_reads_requests) > 0)

        read_count = 0
        for channel, read in client.get_read_chunks():
            assert channel == 4
            assert read.SerializeToString() == input_read_response.SerializeToString()
            read_count += 1
            break

        assert read_count == 1
    finally:
        client.reset()
