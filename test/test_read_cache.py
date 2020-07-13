"""test_read_cache.py

Tests for read cache
"""
import random
import threading
import time

import pytest

from read_until.read_cache import AccumulatingCache, ReadCache
from .test_utils import generate_read


def test_maxsize():
    max_size = 3
    rc = ReadCache(max_size)

    for c in range(1, 2 * max_size):
        channel, read = generate_read(channel=c)
        rc[channel] = read

    assert len(rc) == max_size, "ReadCache has wrong size"

    with pytest.raises(ValueError):
        rc = ReadCache(0)


def test_update_key():
    """Test that the read is replaced"""
    rc = ReadCache()
    read_number = 1
    channel = 1

    for i in range(5):
        _, read = generate_read(channel=channel, number=read_number + i)
        rc[channel] = read

    assert list(rc.keys()) == [channel], "Keys are wrong"
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

    assert list(rc.keys()) == order, "Keys in wrong order"

    # Move read 4 to end by updating
    channel = max_size - 1
    _, read = generate_read(channel=channel, number=rc[channel].number + 1)
    rc[channel] = read
    order.append(order.pop(channel - 1))

    assert list(rc.keys()) == order, "Key order wrong after update"

    # Add another read not in cache, should remove oldest read
    channel, read = generate_read(channel=max_size + 1)
    rc[channel] = read
    order.pop(0)
    order.append(channel)
    assert list(rc.keys()) == order, "Key order wrong after update"


def test_empty():
    rc = ReadCache()
    assert len(rc) == 0, "Not empty"


def test_setitem():
    rc = ReadCache()

    channel, read = generate_read(channel=1)
    rc[channel] = read
    assert len(rc) == 1, "ReadCache has wrong size"

    rc.setdefault(*generate_read(channel=3))
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

    with pytest.raises(KeyError):
        _ = rc[last + 1]


def test_del():
    max_size = 5
    rc = ReadCache(max_size)

    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c)
        rc[channel] = read
        last = c

    assert last in rc, "Key to be deleted not in ReadCache"
    del rc[last]
    assert last not in rc, "Deleted key still in ReadCache"


def test_clear():
    max_size = 5
    rc = ReadCache(max_size)

    for c in range(1, max_size + 1):
        rc.setdefault(*generate_read(channel=c))

    rc.clear()
    assert len(rc) == 0, "ReadCache cleared but not empty"


def test_bool():
    """Test ReadCache truthiness

    In python bool(object) uses __bool__ or __len__ if bool is not defined
    """
    rc = ReadCache()
    assert not rc, "ReadCache not False"
    rc.setdefault(*generate_read())
    assert rc, "ReadCache not True"


def test_len():
    max_size = 5
    rc = ReadCache(max_size)

    assert len(rc) == 0, "ReadCache not empty"

    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c)
        rc[channel] = read
        last = c

    assert len(rc) == max_size, "ReadCache is wrong size"


def test_iter():
    max_size = 5
    rc = ReadCache(max_size)

    keys = []
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c)
        rc[channel] = read
        keys.append(channel)

    iter_keys = []
    for k, v in rc.items():
        iter_keys.append(k)

    assert keys == iter_keys


def test_popitem():
    max_size = 5
    rc = ReadCache(max_size)

    keys = []
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c)
        rc[channel] = read
        keys.append(channel)

    assert list(rc.keys()) == keys, "Keys not in order added"

    # pop last then first
    for lifo in [True, False]:
        idx = -1 if lifo else 0
        rc.popitem(lifo)
        keys.pop(idx)
        assert list(rc.keys()) == keys, "Key order wrong"


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

    assert list(rc.keys()) == keys, "Keys not in order added"

    pop_n = 3

    # Pop last n items
    lifo = True
    reads = rc.popitems(pop_n, lifo)
    size -= pop_n
    keys = keys[:-pop_n]
    assert list(rc.keys()) == keys, "Keys not right"
    assert len(reads) == pop_n, "Wrong number of reads returned"
    assert len(rc) == size, "ReadCache is wrong size"

    # Pop first n items
    lifo = False
    reads = rc.popitems(pop_n, lifo)
    size -= pop_n
    keys = keys[pop_n:]
    assert list(rc.keys()) == keys, "Keys not right"
    assert len(reads) == pop_n, "Wrong number of reads returned"
    assert len(rc) == size, "ReadCache is wrong size"

    # Pop remaining items at max_size
    reads = rc.popitems(max_size, last=True)
    assert not rc, "ReadCache should be empty"
    assert len(reads) == size, "Wrong number of reads returned"
    assert list(reversed(keys)) == [ch for ch, _ in reads], "Reads in wrong order"

    # Re-fill and request more than max_size
    keys = []
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c)
        rc[channel] = read
        keys.append(channel)

    reads = rc.popitems(2 * max_size, last=False)
    assert not rc, "ReadCache should be empty"
    assert keys == [ch for ch, _ in reads], "Reads in wrong order"


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
        channel, read = generate_read(channel=c, number=c + 1)
        rc[channel] = read

    assert rc.missed == max_size, ".missed is wrong"

    # Test replaced
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c, number=c + 1)
        rc[channel] = read

    assert rc.replaced == max_size, ".replaces is wrong"


def test_accumulating_setitem():
    max_size = 5
    rc = AccumulatingCache(max_size)

    read_len = []

    # Normal set
    channel, read = generate_read(channel=1, number=1)
    rc[channel] = read

    # log raw_data length
    read_len.append(len(read.raw_data))

    assert len(rc) == 1, "ReadCache has wrong size"
    assert len(rc[1].raw_data) == sum(read_len)

    rc.setdefault(*generate_read(channel=3))
    assert len(rc) == 2, "ReadCache has wrong size"

    # Same read, new chunk
    channel, read = generate_read(channel=1, number=1)
    rc[channel] = read

    # log raw_data length
    read_len.append(len(read.raw_data))

    assert len(rc[1].raw_data) == sum(read_len)

    # New read for channel 1
    channel, read = generate_read(channel=1, number=10)
    rc[channel] = read

    # Fill cache, test max_size
    for i in range(10, 10 + max_size):
        rc.setdefault(*generate_read(channel=i))

    assert len(rc) == max_size


def test_accumulating_replace():
    max_size = 2
    rc = AccumulatingCache(max_size)

    # Add channel 1, 2, then 3 should only have 2 & 3
    for i in range(1, 3):
        channel, read = generate_read(channel=i)
        rc[channel] = read

    assert rc.keys() == {1, 2}

    channel, read = generate_read(channel=3)
    rc[channel] = read

    assert rc.keys() == {2, 3}


def test_accumulating_popitems_lifo():
    max_size = 10
    rc = AccumulatingCache(max_size)

    keys = []
    for i in range(1, max_size + 1):
        rc.setdefault(*generate_read(channel=i))
        keys.append(i)

    n = 5

    # Get the newest n items, these will be given newest -> oldest
    #   eg [10, 9, 8, ...], the insertion order is reversed
    lifo = [ch for ch, data in rc.popitems(5, last=True)]
    lifo_keys = [keys.pop(-1) for _ in range(n)]
    assert lifo == lifo_keys


def test_accumulating_popitems_fifo():
    max_size = 10
    rc = AccumulatingCache(max_size)

    n = 5
    keys = []
    for i in range(1, max_size + 1):
        ch, read = generate_read(channel=i)
        rc[ch] = read
        keys.append(i)

    # Get the oldest n items, just the first n items
    fifo = [ch for ch, data in rc.popitems(n, last=False)]
    fifo_keys = [keys.pop(0) for _ in range(n)]
    assert fifo == fifo_keys


def test_accumulating_popitems_lifo_all():
    max_size = 10
    rc = AccumulatingCache(max_size)

    keys = []
    for i in range(1, max_size + 1):
        ch, read = generate_read(channel=i)
        rc[ch] = read
        keys.append(i)

    # Test asking for more than capacity, LIFO -> reversed keys
    all_items = [ch for ch, data in rc.popitems(max_size * 2, last=True)]
    fifo_keys = [keys.pop(-1) for _ in range(max_size)]
    assert fifo_keys == all_items


def test_accumulating_popitems_fifo_all():
    max_size = 10
    rc = AccumulatingCache(max_size)

    keys = []
    for i in range(1, max_size + 1):
        ch, read = generate_read(channel=i)
        rc[ch] = read
        keys.append(i)

    # Test asking for more than capacity, FIFO -> insertion order
    all_items = [ch for ch, data in rc.popitems(max_size + 1, last=False)]
    assert keys == all_items


def test_accumulating_del():
    max_size = 2
    rc = AccumulatingCache(max_size)
    channel, read = generate_read()

    rc[channel] = read
    assert len(rc) == 1
    del rc[channel]
    assert len(rc) == 0


def test_accumulating_iter():
    max_size = 5
    rc = AccumulatingCache(max_size)

    keys = []
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c)
        rc[channel] = read
        keys.append(channel)

    iter_keys = []
    for k, v in rc.items():
        iter_keys.append(k)

    assert keys == iter_keys


def test_accumulating_attributes():
    max_size = 10
    rc = AccumulatingCache(max_size)

    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c, number=c)
        rc[channel] = read

    assert len(rc) == rc.size
    assert rc.missed == 0
    assert rc.replaced == 0

    # Test replaced
    # Refill with same channels and read numbers
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c, number=c)
        rc[channel] = read

    assert rc.replaced == max_size, ".replaced is wrong"

    # Test missed
    for c in range(1, max_size + 1):
        channel, read = generate_read(channel=c, number=c + 1)
        rc[channel] = read

    assert rc.missed == max_size, ".missed is wrong"


def add_to_cache(cache, n=10):
    """Add n reads to a Cache"""
    for i in range(1, n + 1):
        channel, read = generate_read(channel=i)
        cache[channel] = read


def test_threaded_access():
    # Init ReadCache up-to MinION size
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

    print(
        "\n\n{got}/{exp} ({iterations} iterations)".format(
            got=got, exp=exp, iterations=iterations,
        )
    )

    assert got == exp
