"""Utils for testing"""

import time


def wait_until(condition, interval=0.1, timeout=1):
    """Wait until a callable condition is true"""
    start = time.time()
    while not condition() and time.time() - start < timeout:
        time.sleep(interval)
