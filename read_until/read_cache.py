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
        The number of items deleted from the cache (read chunks replaced by a
        chunk from a different read)
    replaced : int
        The number of items replaced by a newer item (read chunks replaced by a
        chunk from the same read)
    _dict : collections.OrderedDict
        An instance of an OrderedDict that forms the read cache
    lock : threading.Rlock
        The instance of the lock used to make the cache thread-safe

    Examples
    --------
    When inheriting from ReadCache only the __setitem__ method needs to be
    overridden. The attribute `self._dict` is an instance of OrderedDict that
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
        self._dict = OrderedDict()
        self.lock = RLock()
        self.missed = 0
        self.replaced = 0

    def __getitem__(self, key):
        """Delegate with lock."""
        with self.lock:
            return self._dict[key]

    def __setitem__(self, key, value):
        """Add items to ReadCache, evicting the oldest items if at capacity

        Parameters
        ----------
        key : int
            Channel number for the read chunk
        value : minknow.rpc.data_pb2.GetLiveReadsResponse.ReadData
            Live read data object from MinKNOW rpc. Requires attributes:
            `number`.

        Returns
        -------
        None
        """
        with self.lock:
            # Check if same read
            if key in self._dict:
                if self._dict[key].number == value.number:
                    # Same read
                    self.replaced += 1
                else:
                    # Different read
                    self.missed += 1
                # Remove the old chunk
                del self._dict[key]

            # Set the new chunk
            self._dict[key] = value

            # Check that we aren't above max size
            while len(self._dict) > self.size:
                k, v = self._dict.popitem(last=False)
                self.missed += 1

    def __delitem__(self, key):
        """Delegate with lock."""
        with self.lock:
            del self._dict[key]

    def __len__(self):
        """Delegate with lock."""
        with self.lock:
            return len(self._dict)

    def __iter__(self):
        """Delegate with lock."""
        with self.lock:
            yield from self._dict.__iter__()

    def keys(self):
        """Delegate with lock."""
        with self.lock:
            return self._dict.keys()

    def popitem(self, last=True):
        """Delegate with lock."""
        with self.lock:
            return self._dict.popitem(last=last)

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
            while self._dict and len(data) != items:
                data.append(self._dict.popitem(last=last))
        return data


class AccumulatingCache(ReadCache):
    def __setitem__(self, key, value):
        """Cache that accumulates read chunks as they are received

        Parameters
        ----------
        key : int
            Channel number for the read chunk
        value : minknow.rpc.data_pb2.GetLiveReadsResponse.ReadData
            Live read data object from MinKNOW rpc. Requires attributes:
            `number` and `raw_data`.

        Notes
        -----
        In this implementation attribute `replaced` counts reads where the
        `raw_data` is accumulated, not replaced.

        Returns
        -------
        None
        """
        with self.lock:
            if key not in self:
                # Key not in _dict
                self._dict[key] = value
            else:
                # Key exists
                if self[key].number == value.number:
                    # Same read, update raw_data
                    self[key].raw_data += value.raw_data
                    self.replaced += 1
                else:
                    # New read
                    self._dict[key] = value
                    self.missed += 1

            self._dict.move_to_end(key)

            if len(self) > self.size:
                k, v = self.popitem(last=False)
