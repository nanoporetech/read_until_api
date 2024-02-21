"""Utils for testing"""
import sys
import io
import random
import re
import subprocess
import time
import typing
import uuid

import numpy

from minknow_api import data_pb2


def wait_until(
    condition: typing.Callable[[], bool], interval: float = 0.1, timeout: float = 1
) -> None:
    """Wait until a callable condition is true"""
    start = time.time()
    while not condition() and time.time() - start < timeout:
        time.sleep(interval)


def generate_read(**kwargs):
    """Generate a (channel, ReadData) tuple, using random numbers

    All parameters must be given as keyword arguments

    :param channel: Channel number to give the read
    :type channel: int
    :param id: str
    :type id: Read ID to give the read
    :param start_sample: The start sample for the read
    :type start_sample: int
    :param chunk_start_sample: The read chunk start sample
    :type chunk_start_sample: int
    :param chunk_length: The chunk length for the read
    :type chunk_length: int
    :param chunk_classifications: Chunk classification, default is ``[83]``
    :type chunk_classifications: List[int,]
    :param raw_data: Raw bytes for the read, should be from int16 or float32,
        the default is float32
    :type raw_data: bytes
    :param median_before: Drawn from random.uniform(200, 250)
    :type median_before: float
    :param median: Drawn from random.uniform(100, 120)
    :type median: float
    """
    # If channel not in kwargs use a random int
    if "channel" in kwargs:
        channel = kwargs.pop("channel")
    else:
        # TODO: should take other flow cell sizes
        channel = random.randint(1, 512)

    sample_length = random.randint(1000, 3000)
    sample_number = 0
    defaults = dict(
        id=str(uuid.uuid4()),
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

    # remove keys we don't want
    for key in kwargs.keys() - defaults.keys():
        kwargs.pop(key)

    # update the defaults dict with any kwargs
    kwargs = {**defaults, **kwargs}

    return channel, data_pb2.GetLiveReadsResponse.ReadData(**kwargs)


def run_server(bin_path, options):
    """Start a basecall server with the specified parameters.

    :param bin_path: Path to basecall server binary executable.
    :param options: List of command line options for the server.
    :return: A tuple containing the handle to the server process, and the port the server is listening on.

    If the server cannot be started, the port will be returned as 0.
    """
    server_args = [bin_path]
    server_args.extend(options)

    server = subprocess.Popen(
        server_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )

    pattern = re.compile(r"Starting server on port: (\d+)")

    port = 0

    for line in server.stdout:
        if pattern.findall(line):
            port = int(pattern.findall(line)[0])
            break

        if not line:
            break

    return server, port
