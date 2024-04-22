"""Test grpc server for read until"""

import argparse
from collections import namedtuple
from concurrent import futures
import inspect
import logging
from pathlib import Path
from queue import Queue, Empty
import sys
from threading import Thread
import time
import typing
from typing import Optional

import grpc
from minknow_api import (
    acquisition_pb2,
    acquisition_pb2_grpc,
    analysis_configuration_pb2,
    analysis_configuration_pb2_grpc,
    data_pb2,
    data_pb2_grpc,
    device_pb2,
    device_pb2_grpc,
    instance_pb2,
    instance_pb2_grpc,
)


LOGGER = logging.getLogger(__name__)
CLASS_MAP = {
    83: "strand",
    67: "strand1",
    77: "multiple",
    90: "zero",
    65: "adapter",
    66: "mux_uncertain",
    70: "user2",
    68: "user1",
    69: "event",
    80: "pore",
    85: "unavailable",
    84: "transition",
    78: "unclassed",
}


class AnalysisConfigurationService(
    analysis_configuration_pb2_grpc.AnalysisConfigurationServiceServicer
):
    """Test server implementation of AnalysisConfigurationService
    """

    def get_read_classifications(self, request, context):
        """Mimic get read classifications, for now return hard-coded CLASS_MAP"""
        return analysis_configuration_pb2.GetReadClassificationsResponse(
            read_classifications=CLASS_MAP,
        )


class DataService(data_pb2_grpc.DataServiceServicer):
    """Test server implementation of DataService.

    Contains useful methods for testing responses to get_live_reads
    """

    ChannelDataItem = namedtuple("ChannelDataItem", ["time", "data"])

    def __init__(self):
        self.live_reads_responses_to_send = Queue()
        self._live_reads_terminate = Queue()
        self.live_reads_requests = []
        self.live_reads_responses = []

        self.channel_data = {}

    def add_response(self, response: data_pb2.GetLiveReadsResponse):
        """
        Add a response to be sent to any live_reads readers.

        If no readers exist, it will be send as soon as one connects.
        """
        self.live_reads_responses_to_send.put(response)

    def terminate_live_reads(self, error_code=None):
        """Terminate one open live reads stream. if error is passed,
        that error code will be raised as a GRPC Exception"""
        self._live_reads_terminate.put(error_code)

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
            bias_voltages=data_pb2.GetDataTypesResponse.DataType(
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
                if request.HasField("actions"):
                    for action in request.actions.actions:
                        self._add_channel_data(action.channel, action)

        request_thread = Thread(target=request_handler, args=(self, request_iterator,))
        request_thread.start()

        while request_thread.is_alive():
            # If we have been asked to exit then abort
            try:
                resp = self._live_reads_terminate.get(block=False)
                LOGGER.info("Exiting get_live_reads due to terminate request")
                if resp:
                    _context.set_code(resp)
                return
            except Empty:
                pass

            try:
                # Send responses as the queue is filled.
                resp = self.live_reads_responses_to_send.get(timeout=0.1)
                if resp:
                    self.live_reads_responses.append(resp)
                for channel, reads in resp.channels.items():
                    self._add_channel_data(channel, reads)
                yield resp
            except Empty:
                continue

    def find_response_times(self) -> typing.List[float]:
        """Find response times (in seconds) based on sent/received data from the server"""
        response_times = []
        response_time = 0
        for _channel, data in self.channel_data.items():
            start_item = None
            for data_item in data:
                if start_item:
                    if isinstance(
                        start_item.data, data_pb2.GetLiveReadsResponse.ReadData
                    ):
                        matched = False
                        read_id = start_item.data.id
                        matched = read_id == data_item.data.id

                        # its possible a new read comes in before the first one is responded to
                        # so we dont get match
                        if matched:
                            response_time = data_item.time - start_item.time
                            assert response_time > 0
                    response_times.append(response_time)
                    start_item = None
                else:
                    start_item = data_item

        return response_times

    def _add_channel_data(self, channel, data):
        if channel not in self.channel_data:
            self.channel_data[channel] = []
        self.channel_data[channel].append(self.ChannelDataItem(time.time(), data))


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


class DeviceService(device_pb2_grpc.DeviceServiceServicer):
    def get_calibration(self, request, context):
        # Return the identity calibration: scaling=1, offset=0
        n_channels = len(range(request.first_channel, request.last_channel)) + 1
        return device_pb2.GetCalibrationResponse(
            digitisation=1,
            offsets=[0.0] * n_channels,
            pa_ranges=[1.0] * n_channels,
            has_calibration=True,
        )

    def get_flow_cell_info(self, request, context):
        return device_pb2.GetFlowCellInfoResponse(
            has_flow_cell=True,
            channel_count=512,
            wells_per_channel=4,
            flow_cell_id="",
            asic_id_str="",
            product_code="",
            user_specified_flow_cell_id="",
            user_specified_product_code="",
            has_adapter=False,
            adapter_id="",
            temperature_offset=0.0,
            asic_version="",
        )


class InstanceService(instance_pb2_grpc.InstanceServiceServicer):
    """
    The most basic implementation of InstanceServicerServicer.

    get_version_info() must be implemented for minknow_api.Connection() to work.
    """

    def get_version_info(
        self,
        _request: instance_pb2.GetVersionInfoRequest,
        _context: grpc.ServicerContext,
    ) -> instance_pb2.GetVersionInfoResponse:
        """Find the version information for the instance"""
        return instance_pb2.GetVersionInfoResponse(
            minknow=instance_pb2.GetVersionInfoResponse.MinknowVersion(
                major=6, minor=0, patch=0, full="6.0.0"
            )
        )


TEST_CERTS_DIR = Path(__file__).parent / "test_certs"
CA_PATH = TEST_CERTS_DIR / "ca.crt"
SERVER_KEY_PATH = TEST_CERTS_DIR / "localhost.key"
SERVER_CERT_PATH = TEST_CERTS_DIR / "localhost.crt"


def channel_credentials() -> grpc.ChannelCredentials:
    """Create a gRPC ChannelCredentials object using the test certificates."""
    with open(CA_PATH, "rb") as ca_file:
        return grpc.ssl_channel_credentials(root_certificates=ca_file.read())


def _add_servicer_to_server(servicer: object, server: grpc.Server):
    """Adds an arbitrary servicer to a grpc server.

    The servicer must ultimately derive from the base servicer in the generated gRPC
    code (eg: minknow_api.manager.ManagerServiceServicer for the manager service).
    """
    # first, find the adder function - we'll assume the base servicer is just below
    # `object` in the class hierarchy
    base_servicer_type = inspect.getmro(type(servicer))[-2]
    pb2_grpc_module = inspect.getmodule(base_servicer_type)
    adder_name = f"add_{base_servicer_type.__name__}_to_server"
    adder = getattr(pb2_grpc_module, adder_name)
    adder(servicer, server)


class ReadUntilTestServer:
    """
    Runs a test gRPC server implementing the bits of MinKNOW's API relevant to Read
    Until.

    Args:
        port: Listen on a fixed port (defaults to an automatically-assigned free port).
        acquisition_service: Override the acquisition_service implementation.
        analysis_configuration_service: Override the analysis_configuration_service
            implementation.
        data_service: Override the data_service implementation.
        device_service: Override the device_service implementation.
        instance_service: Override the instance_service implementation.

    Attrs:
        server (grpc.Server): The gRPC server.
        port (int): The port the server is listening on.
    """

    def __init__(
        self,
        port: int = 0,
        acquisition_service: Optional[
            acquisition_pb2_grpc.AcquisitionServiceServicer
        ] = None,
        analysis_configuration_service: Optional[
            analysis_configuration_pb2_grpc.AnalysisConfigurationServiceServicer
        ] = None,
        data_service: Optional[data_pb2_grpc.DataServiceServicer] = None,
        device_service: Optional[device_pb2_grpc.DeviceServiceServicer] = None,
        instance_service: Optional[instance_pb2_grpc.InstanceServiceServicer] = None,
    ):
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))

        if acquisition_service is None:
            acquisition_service = AcquisitionService()
        self.acquisition_service = acquisition_service
        _add_servicer_to_server(acquisition_service, self.server)

        if analysis_configuration_service is None:
            analysis_configuration_service = AnalysisConfigurationService()
        self.analysis_configuration_service = analysis_configuration_service
        _add_servicer_to_server(analysis_configuration_service, self.server)

        if data_service is None:
            data_service = DataService()
        self.data_service = data_service
        _add_servicer_to_server(data_service, self.server)

        if device_service is None:
            device_service = DeviceService()
        self.device_service = device_service
        _add_servicer_to_server(device_service, self.server)

        if instance_service is None:
            instance_service = InstanceService()
        self.instance_service = instance_service
        _add_servicer_to_server(instance_service, self.server)

        with open(SERVER_KEY_PATH, "rb") as key_file:
            key = key_file.read()
        with open(SERVER_CERT_PATH, "rb") as cert_file:
            cert = cert_file.read()
        self.port = self.server.add_secure_port(
            f"127.0.0.1:{port}", grpc.ssl_server_credentials([(key, cert)],),
        )
        logging.info("gRPC server listening on %s", self.port)
        self.server.start()
        logging.info("gRPC server started")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        logging.info("gRPC server stopping")
        self.server.stop(0)
        logging.debug("gRPC server stopped")


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
    server.data_service.add_response(data_pb2.GetLiveReadsResponse())

    try:
        with server as TestServer:
            TestServer.wait_for_termination(86400)
    except KeyboardInterrupt:
        pass

    LOGGER.info("Server exited.")


if __name__ == "__main__":
    main()
