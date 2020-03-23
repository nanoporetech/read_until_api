"""test_read_cache.py

Tests for read cache
"""
import random
import threading
import time

import pytest
import numpy

from read_until.read_cache import AccumulatingCache, ReadCache
from read_until.generated.minknow.rpc import data_pb2


def generate_read(**kwargs):
    """Generate a (channel, ReadData) tuple, using random numbers

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
        id="test-read",
        number=random.randint(1, 10000),
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


def test_maxsize():
    max_size = 3
    rc = ReadCache(max_size)

    for c in range(1, 2 * max_size):
        channel, read = generate_read(channel=c)
        rc[channel] = read

    assert len(rc) == max_size, "ReadCache has wrong size"

    with pytest.raises(AttributeError):
        rc = ReadCache(0)


def test_update_key():
    """Test that the read is replaced"""
    rc = ReadCache()
    read_number = 1
    channel = 1

    for i in range(5):
        _, read = generate_read(channel=channel, number=read_number + i)
        rc[channel] = read

    assert list(rc.dict.keys()) == [channel], "Keys are wrong"
    assert len(rc) == 1, "Wrong number of entries"
    assert rc[channel].number != read_number, "read might have not been updated"


def test_order():
    max_size = 5
    rc = ReadCache(size=max_size)
    order = []
    for channel in range(1, max_size + 1):
        _, read = generate_read(channel=channel)
        rc[channel] = read
        order.append(channel)

    assert list(rc.dict.keys()) == order, "Keys in wrong order"

    # Move read 4 to end by updating
    channel = max_size - 1
    _, read = generate_read(channel=channel, number=rc[channel].number + 1)
    rc[channel] = read
    order.append(order.pop(channel-1))

    assert list(rc.dict.keys()) == order, "Key order wrong after update"

    # Add another read not in cache, should remove oldest read
    channel, read = generate_read(channel=max_size + 1)
    rc[channel] = read
    order.pop(0)
    order.append(channel)
    assert list(rc.dict.keys()) == order, "Key order wrong after update"


def test_empty():
    rc = ReadCache()
    assert len(rc) == 0, "Not empty"
    assert rc.__len__() == 0, "Not empty"
    channel, read = generate_read()
    rc[channel] = read
    rc.dict.clear()
    assert len(rc) == 0, "Not empty after clear"


def test_setitem():
    rc = ReadCache()

    channel, read = generate_read(channel=1)
    rc[channel] = read
    assert len(rc) == 1, "ReadCache has wrong size"

    # Maybe unnecessary, in the future may want to raise NotImplemented
    # with pytest.raises(AttributeError):
    #     rc.setdefault(generate_read(channel=2))

    assert len(rc) == 1, "ReadCache has wrong size"

    rc.__setitem__(*generate_read(channel=3))

    assert len(rc) == 2, "ReadCache has wrong size"


def test_getitem():
    rc = ReadCache()

    for c in range(1, 5):
        channel, read = generate_read(channel=c)
        rc[channel] = read
        last = c

    assert len(rc) == 4, "ReadCache has wrong size"

    # Get last set item, should be the same as `read`
    r = rc[last]
    assert read == r, "Reads do not match"

    r = rc.__getitem__(last)
    assert read == r, "Reads do not match"

    with pytest.raises(KeyError):
        _ = rc[last + 1]


def test_del():
    max_size = 5
    rc = ReadCache(max_size)

    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c)
        rc[channel] = read
        last = c

    assert len(rc) == max_size, "ReadCache is wrong size"
    assert list(rc.dict.keys()) == list(range(1, max_size + 1)), "Keys mismatch"

    del rc[last]
    assert last not in rc.dict.keys(), "Deleted key still in ReadCache"

    last -= 1
    rc.__delitem__(last)
    assert last not in rc.dict.keys(), "Deleted key still in ReadCache"

    rc.dict.clear()
    assert len(rc) == 0, "ReadCache cleared but not empty"


def test_bool():
    """Test ReadCache truthiness

    In python bool(object) uses __bool__ or __len__ if bool is not defined
    """
    rc = ReadCache()
    assert not rc, "ReadCache not False"
    rc.__setitem__(*generate_read())
    assert rc, "ReadCache not True"


def test_len():
    max_size = 5
    rc = ReadCache(max_size)

    assert len(rc) == 0, "ReadCache not empty"
    assert rc.__len__() == 0, "ReadCache not empty"

    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c)
        rc[channel] = read
        last = c

    assert len(rc) == max_size, "ReadCache is wrong size"
    assert rc.__len__() == max_size, "ReadCache is wrong size"


def test_popitem():
    max_size = 5
    rc = ReadCache(max_size)

    keys = []
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c)
        rc[channel] = read
        keys.append(channel)

    assert list(rc.dict.keys()) == keys, "Keys not in order added"

    # pop last then first
    for lifo in [True, False]:
        idx = -1 if lifo else 0
        rc.popitem(lifo)
        keys.pop(idx)
        assert list(rc.dict.keys()) == keys, "Key order wrong"


def test_popitems():
    max_size = 10
    size = max_size

    rc = ReadCache(max_size)

    keys = []
    # Fill Cache
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c)
        rc[channel] = read
        keys.append(channel)

    assert list(rc.dict.keys()) == keys, "Keys not in order added"

    pop_n = 3

    # Pop last n items
    lifo = True
    reads = rc.popitems(pop_n, lifo)
    size -= pop_n
    keys = keys[:-pop_n]
    assert list(rc.dict.keys()) == keys, "Keys not right"
    assert len(reads) == pop_n, "Wrong number of reads returned"
    assert len(rc) == size, "ReadCache is wrong size"

    # Pop first n items
    lifo = False
    reads = rc.popitems(pop_n, lifo)
    size -= pop_n
    keys = keys[pop_n:]
    assert list(rc.dict.keys()) == keys, "Keys not right"
    assert len(reads) == pop_n, "Wrong number of reads returned"
    assert len(rc) == size, "ReadCache is wrong size"

    # Pop remaining items
    reads = rc.popitems(max_size, last=True)
    assert not rc, "ReadCache should be empty"
    assert len(reads) == size, "Wrong number of reads returned"
    assert list(reversed(keys)) == [ch for ch, _ in reads], "Reads in wrong order"


def test_attributes():
    # Test size
    max_size = 10
    rc = ReadCache(max_size)

    assert rc.size == max_size, ".size is wrong"

    # Fill the cache
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c, number=c)
        rc[channel] = read

    assert len(rc) == rc.size

    # Test missed
    # Refill all reads with different read numbers
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c, number=c+1)
        rc[channel] = read

    assert rc.missed == max_size, ".missed is wrong"

    # Test replaced
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c, number=c+1)
        rc[channel] = read

    assert rc.replaced == max_size, ".replaces is wrong"


def test_accumulating_setitem():
    rc = AccumulatingCache()

    channel, read = generate_read(channel=1)
    rc[channel] = read
    assert len(rc) == 1, "ReadCache has wrong size"

    rc.__setitem__(*generate_read(channel=3))
    assert len(rc) == 2, "ReadCache has wrong size"


def add_to_cache(cache, n=10):
    """Add n reads to a Cache"""
    for i in range(1, n+1):
        channel, read = generate_read(channel=i)
        cache[channel] = read


def test_threaded_access():
    # Init ReacCache up-to MinION size
    rc = ReadCache(512)

    # Create random number of reads
    exp = random.randint(100, 512)

    # Start thread to add to cache
    t1 = threading.Thread(target=add_to_cache, args=(rc, exp), daemon=True)
    t1.start()
    pause = random.randint(1, 2) / 1000
    time.sleep(pause)

    iterations = 0
    got = 0

    while rc:
        got += len(rc.popitems(512))
        iterations += 1
        time.sleep(pause)

    print(f"\n\n{got}/{exp} ({iterations} iterations)")

    assert got == exp
