"""Test grpc server for read until"""

import argparse
from concurrent import futures
from contextlib import closing
import logging
from queue import Queue, Empty
import socket
import sys
from threading import Thread
import time

import grpc
from read_until.minknow_grpc_api import (
    acquisition_pb2,
    acquisition_pb2_grpc,
    data_pb2,
    data_pb2_grpc,
)

LOGGER = logging.getLogger(__name__)


class DataService(data_pb2_grpc.DataServiceServicer):
    """
    Test server implementation of DataService.

    Contains useful methods for testing responses to get_live_reads
    """

    def __init__(self):
        self.live_reads_responses_to_send = Queue()
        self._live_reads_terminate = Queue()
        self.live_reads_requests = []

    def add_response(self, response: data_pb2.GetLiveReadsResponse):
        """
        Add a response to be sent to any live_reads readers.

        If no readers exist, it will be send as soon as one connects.
        """
        self.live_reads_responses_to_send.put(response)

    def terminate_live_reads(self):
        """Terminate one open live reads stream."""
        self._live_reads_terminate.put(None)

    def get_data_types(self, request: data_pb2.GetDataTypesRequest, context):
        """Get the data types available from this service"""
        return data_pb2.GetDataTypesResponse(
            calibrated_signal=data_pb2.GetDataTypesResponse.DataType(
                type=data_pb2.GetDataTypesResponse.DataType.FLOATING_POINT,
                big_endian=False,
                size=4,
            ),
            uncalibrated_signal=data_pb2.GetDataTypesResponse.DataType(
                type=data_pb2.GetDataTypesResponse.DataType.SIGNED_INTEGER,
                big_endian=False,
                size=2,
            ),
        )

    def get_live_reads(self, request_iterator, _context):
        """Start streaming live reads"""

        def request_handler(self, request_iterator):
            for request in request_iterator:
                LOGGER.info("Server received request: %s", request)
                self.live_reads_requests.append(request)

        request_thread = Thread(target=request_handler, args=(self, request_iterator,))
        request_thread.start()

        while request_thread.is_alive():
            # If we have been asked to exit then abort
            try:
                self._live_reads_terminate.get(block=False)
                return
            except Empty:
                pass

            try:
                # Send responses as the queue is filled.
                resp = self.live_reads_responses_to_send.get(timeout=0.1)
                yield resp
            except Empty:
                continue


class AcquisitionService(acquisition_pb2_grpc.AcquisitionServiceServicer):
    """
    Test server implementation of AcquisitionService.
    """

    def __init__(self):
        self.progress = acquisition_pb2.GetProgressResponse()

    def get_progress(
        self, request: acquisition_pb2.GetProgressRequest, _context
    ) -> acquisition_pb2.GetProgressResponse:
        """Find current acquisition progress"""
        return self.progress


def get_free_network_port() -> int:
    """Find a free port number"""
    with closing(socket.socket()) as temp_socket:
        temp_socket.bind(("", 0))
        return temp_socket.getsockname()[1]


class ReadUntilTestServer:
    """
    Test server runs grpc read until service on a port.
    """

    def __init__(self, port=None):
        self.port = port
        if not self.port:
            self.port = get_free_network_port()
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

        self.data_service = DataService()
        data_pb2_grpc.add_DataServiceServicer_to_server(self.data_service, self.server)

        self.acquisition_service = AcquisitionService()
        acquisition_pb2_grpc.add_AcquisitionServiceServicer_to_server(
            self.acquisition_service, self.server
        )

        LOGGER.info("Starting server. Listening on port %s.", self.port)
        self.server.add_insecure_port("[::]:%s" % self.port)
        self.server.start()

    def stop(self):
        """Stop grpc server"""
        self.server.stop(0)


def main():
    """Cli entrypoint for test server"""
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    parser = argparse.ArgumentParser(description="Testing grpc read until server")
    parser.add_argument(
        "--port", default=8800, type=int, help="Port to run grpc server on"
    )
    parser.add_argument("--client", action="store_true")

    args = parser.parse_args()
    if args.client:

        def config_stream():
            while True:
                request = data_pb2.GetLiveReadsRequest(
                    setup=data_pb2.GetLiveReadsRequest.StreamSetup(
                        first_channel=1,
                        last_channel=512,
                        raw_data_type=data_pb2.GetLiveReadsRequest.CALIBRATED,
                    )
                )
                yield request
                time.sleep(60)

        LOGGER.info("Connecting to server on port %s.", args.port)
        with grpc.insecure_channel("localhost:%s" % args.port) as channel:
            try:
                grpc.channel_ready_future(channel).result(timeout=1)
            except grpc.FutureTimeoutError:
                LOGGER.info("Failed to connect to grpc")
                return

            stub = data_pb2_grpc.DataServiceStub(channel)
            for resp in stub.get_live_reads(config_stream()):
                LOGGER.info("Response: %s", resp)
                sys.stdout.flush()

    # Create a gRPC server
    server = ReadUntilTestServer(args.port)

    # Add a response for a user to receive
    # server.data_service.add_response(data_pb2.GetLiveReadsResponse())
    import numpy

    server.data_service.add_response(
        data_pb2.GetLiveReadsResponse(
            channels={
                4: data_pb2.GetLiveReadsResponse.ReadData(
                    id="test-read",
                    number=1,
                    start_sample=0,
                    chunk_start_sample=0,
                    chunk_length=100,
                    chunk_classifications=[83],
                    raw_data=numpy.zeros(100, dtype="f4").tobytes(),
                    median_before=100,
                    median=150,
                )
            }
        )
    )

    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop()

    LOGGER.info("Server exited.")


if __name__ == "__main__":
    main()
