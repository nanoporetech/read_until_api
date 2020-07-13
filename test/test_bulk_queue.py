import pytest
import threading
import time

from read_until.bulk_queue import BulkQueue


def test_put():
    bq = BulkQueue()
    bq.put(5)

    assert bq.pop_all() == [5]
    assert bq.pop_all() == []


def test_put_iterable():
    bq = BulkQueue()
    bq.put_iterable([5, 6])

    assert bq.pop_all() == [5, 6]
    assert bq.pop_all() == []


def test_pop():
    bq = BulkQueue()
    bq.put(5)

    assert bq.pop() == 5
    assert bq.pop_all() == []


def test_pop_error():
    bq = BulkQueue()
    with pytest.raises(IndexError):
        bq.pop()


def test_pop_wait():
    bq = BulkQueue()

    def slow_push():
        time.sleep(0.1)
        bq.put(5)

    t = threading.Thread(target=slow_push)
    t.start()

    assert bq.pop(timeout=0.3) == 5

    t.join()
    assert bq.pop_all() == []


def test_pop_not_wait():
    bq = BulkQueue()

    def slow_push():
        time.sleep(0.1)
        bq.put(5)

    t = threading.Thread(target=slow_push)
    t.start()

    with pytest.raises(IndexError):
        bq.pop()

    t.join()
    assert bq.pop_all() == [5]


def test_pop_all():
    bq = BulkQueue()
    bq.put(5)
    bq.put(6)

    assert bq.pop_all() == [5, 6]
    assert bq.pop_all() == []

def test_pop_all_wait():
    bq = BulkQueue()

    def slow_push():
        time.sleep(0.1)
        bq.put(5)

    t = threading.Thread(target=slow_push)
    t.start()

    assert bq.pop_all(timeout=0.3) == [5]

    t.join()
    assert bq.pop_all() == []


def test_pop_all_no_wait():
    bq = BulkQueue()

    def slow_push():
        time.sleep(0.1)
        bq.put(5)

    t = threading.Thread(target=slow_push)
    t.start()

    assert bq.pop_all() == []

    t.join()
    assert bq.pop_all() == [5]
    assert bq.pop_all() == []
