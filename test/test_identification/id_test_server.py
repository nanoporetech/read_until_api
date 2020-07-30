"""Test grpc server for read until"""

import argparse
import logging
import random
import sys
import tempfile
import time
from pathlib import Path
from shutil import which
from threading import Thread
from uuid import uuid4

import numpy as np
from minknow_api import (
    data_pb2,
    data_pb2_grpc,
)

from ..read_until_test_server import ReadUntilTestServer
from ..test_utils import run_server

# from minknow_api.testutils import MockMinKNOWServer

DIR = Path(__file__).parent.resolve()

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


class DataService(data_pb2_grpc.DataServiceServicer):
    def __init__(self):
        self.logger = logging.getLogger("[SERVER]")
        # Have we received the StreamSetup?
        self.setup = False
        # First and last channel from StreamSetup
        self.first = None
        self.last = None
        # Raw data dtype
        self.dtype = None

        self.action_responses = []

        # Number of unblock/stop actions received
        self.unblock_count = 0
        self.stop_count = 0

        # Total number of requests processed
        self.processed_requests = 0

        # Send sparse data back, skip ~40% of time
        self.sparse = True
        # Number of read batches to send, useful for controlling
        #   how many reads this server sends out
        self.batches = float("inf")
        self.sent_batches = 0
        self.sent_reads = 0
        self.test_read = open(str(DIR / "test_read.b"), "rb").read()

    def _read_data_generator(self):
        """Generate a (channel, ReadData) tuple, using random numbers
        """
        read_number = 1
        sample_number = 0
        for channel in range(self.first, self.last + 1):
            # 40% chance of skipping a read, simulates sparse read data
            if np.random.choice([True, False], 1, p=[0.4, 0.6]) and self.sparse:
                continue

            sample_length = random.randint(1000, 3000)
            defaults = data_pb2.GetLiveReadsResponse.ReadData(
                id=str(uuid4()),
                number=read_number,
                start_sample=sample_number,
                chunk_start_sample=sample_number,
                chunk_length=sample_length,
                chunk_classifications=[83],
                # raw_data=np.random.randint(sample_length, dtype=np.int16).tobytes(),
                raw_data=self.test_read,
                # guarantee > 60 pa delta - simple treats this as a read.
                median_before=random.uniform(200, 250),
                median=random.uniform(100, 120),
            )

            yield channel, defaults
            read_number += random.randint(1, 4)
            sample_number += random.randint(1, 10000)

    def request_handler(self, iterator):
        for req in iterator:
            if req.HasField("setup"):
                self.logger.info("Received StreamSetup request")
                self.setup = True
                self.first = req.setup.first_channel
                self.last = req.setup.last_channel
                # print(f"{self.first}-{self.last}")
                # TODO: use self.dtype to send back different kinds of data
                self.dtype = req.setup.raw_data_type
                # Reset these vars
                self.action_responses = []
                self.unblock_count = 0
                self.stop_count = 0
                self.processed_requests = 0
                self.sent_batches = 0
                self.sent_reads = 0
            elif not self.setup:
                raise RuntimeError("Expected StreamSetup first")
            elif req.HasField("actions"):
                i = 0
                for resp in req.actions.actions:
                    i += 1
                    self.processed_requests += 1
                    if resp.HasField("unblock"):
                        self.unblock_count += 1
                    elif resp.HasField("stop_further_data"):
                        self.stop_count += 1
                    self.action_responses.append(
                        data_pb2.GetLiveReadsResponse.ActionResponse(
                            action_id=resp.action_id,
                            response=data_pb2.GetLiveReadsResponse.ActionResponse.Response.SUCCESS,
                        )
                    )
                self.logger.info("Received {} action(s)".format(i))
            else:
                raise RuntimeError("Uhh oh")

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

    def get_live_reads(self, request_iterator, context):

        request_thread = Thread(target=self.request_handler, args=(request_iterator,))
        request_thread.start()
        while request_thread.is_alive():
            if self.sent_batches >= self.batches or not self.setup:
                continue

            data = {ch: d for ch, d in self._read_data_generator()}
            self.sent_reads += len(data)
            self.logger.info("Sending {} read(s)".format(len(data)))
            yield data_pb2.GetLiveReadsResponse(
                samples_since_start=0,
                seconds_since_start=0,
                # map<int32, ReadData> (channel, ReadData)
                channels=data,
                # repeated ActionResponse
                action_responses=self.action_responses,
            )
            self.action_responses = []
            self.sent_batches += 1
            # TODO: interval time should be tied to read length
            time.sleep(1)


def main():
    """Cli entrypoint for test server"""
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    parser = argparse.ArgumentParser(description="Testing grpc read until server")
    parser.add_argument(
        "--port", default=8800, type=int, help="Port to run grpc server on"
    )
    parser.add_argument(
        "--g", default=5555, type=int, help="Port to run guppy server on"
    )

    args = parser.parse_args()
    # Create a gRPC server
    server = ReadUntilTestServer(args.port, data_service=DataService,)

    # Add a response for a user to receive
    # server.data_service.add_response(data_pb2.GetLiveReadsResponse())

    try:
        with server as TestServer:
            GUPPY_EXEC = which("guppy_basecall_server")
            if GUPPY_EXEC is None:
                logging.warning("guppy_basecall_server not found")

            log_path = tempfile.mkdtemp()
            config = "dna_r9.4.1_450bps_fast.cfg"

            opts = [
                "--config",
                config,
                "--port",
                str(args.g),
                "--log_path",
                log_path,
                "--disable_pings",
            ]

            guppy_server, guppy_port = run_server(GUPPY_EXEC, opts)
            logging.info(guppy_port)

            TestServer.wait_for_termination(86400)
    except KeyboardInterrupt:
        pass

    guppy_server.stdout.close()
    guppy_server.kill()
    guppy_server.wait()

    LOGGER.info("Server exited.")


if __name__ == "__main__":
    main()
