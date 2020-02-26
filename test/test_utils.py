"""Utils for testing"""

import time
import typing


def wait_until(
    condition: typing.Callable[[], bool], interval: float = 0.1, timeout: float = 1
) -> None:
    """Wait until a callable condition is true"""
    start = time.time()
    while not condition() and time.time() - start < timeout:
        time.sleep(interval)
