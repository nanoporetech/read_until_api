"""read_cache.py

ReadCaches for the ReadUntilClient
"""
from collections import OrderedDict
from collections.abc import MutableMapping
from threading import RLock


class ReadCache(MutableMapping):
    """A thread-safe dict-like container with a maximum size
    This ReadCache contains all the required methods for working as an ordered
    cache with a max size.

    When implementing a ReadCache, this can be subclassed and a custom method
    for __setitem__ provided, see examples.

    Parameters
    ----------
    size : int
        The maximum number of items to hold

    Attributes
    ----------
    size : int
        The maximum size of the cache
    missed : int
        The number items never removed from the queue
    replaced : int
        The number of items replaced by a newer item (reads chunks replaced by a
        chunk from the same read)
    dict : OrderedDict
        An instance of an OrderedDict that forms the read cache
    lock : threading.Rlock
        The instance of the lock used to make the cache thread-safe

    Examples
    --------
    When inheriting from ReadCache only the __setitem__ method needs to be
    included. The attribute `self.dict` is an instance of OrderedDict that
    forms the cache so this is the object that must be updated.

    This example is not likely to be a good cache.

    >>> class DerivedCache(ReadCache):
    ...     def __setitem__(self, key, value):
    ...         # The lock is required to maintain thread-safety
    ...         with self.lock:
    ...             # Logic to apply when adding items to the cache
    ...             self.dict[key] = value
    """

    def __init__(self, size=100):
        if size < 1:
            # FIXME: ValueError maybe more appropriate
            #  https://docs.python.org/3/library/exceptions.html#ValueError
            raise AttributeError("'size' must be >1.")
        self.size = size
        self.dict = OrderedDict()
        self.lock = RLock()
        self.missed = 0
        self.replaced = 0

    def __getitem__(self, key):
        """Delegate with lock."""
        with self.lock:
            return self.dict[key]

    def __setitem__(self, key, value):
        """Add items to self.dict, evicting oldest items if cache is at capacity"""
        with self.lock:
            # Check if same read
            if key in self.dict:
                if self.dict[key].number == value.number:
                    # Same read
                    self.replaced += 1
                else:
                    # Different read
                    self.missed += 1
                # Remove the old chunk
                del self.dict[key]

            # Set the new chunk
            self.dict[key] = value

            # Check that we aren't above max size
            while len(self.dict) > self.size:
                k, v = self.dict.popitem(last=False)
                self.missed += 1

    def __delitem__(self, key):
        """Delegate with lock."""
        with self.lock:
            del self.dict[key]

    def __len__(self):
        """Delegate with lock."""
        with self.lock:
            return len(self.dict)

    def __iter__(self):
        """Delegate with lock."""
        with self.lock:
            yield from self.dict.__iter__()

    def popitem(self, last=True):
        """Delegate with lock."""
        with self.lock:
            return self.dict.popitem(last=last)

    def popitems(self, items=1, last=True):
        """Return a list of popped items from the cache.

        Parameters
        ----------
        items : int
            Maximum number of items to return
        last : bool
            If True, return the newest entry (LIFO); else the oldest (FIFO).

        Returns
        -------
        list
            Output list of upto `items` (key, value) pairs from the cache
        """
        if items > self.size:
            items = self.size

        with self.lock:
            data = []
            while self.dict and len(data) != items:
                data.append(self.dict.popitem(last=last))
        return data


class AccumulatingCache(ReadCache):
    def __setitem__(self, key, value):
        """Cache that accumulates read chunks as they are received"""
        with self.lock:
            if key not in self.dict:
                # Key not in dict
                self.dict[key] = value
            else:
                # Key exists
                if self.dict[key].number == value.number:
                    # Same read, update raw_data
                    self.dict[key].raw_data += value.raw_data
                    self.replaced += 1
                else:
                    # New read
                    self.dict[key] = value
                    self.missed += 1

            self.dict.move_to_end(key)

            if len(self) > self.size:
                k, v = self.popitem(last=False)
