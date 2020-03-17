"""read_cache.py

ReadCaches for the ReadUntilClient
"""
from collections import OrderedDict
from threading import Lock


class ReadCache:
    """An ordered and keyed queue of a maximum size to store read chunks."""

    def __init__(self, size=100):
        """
        :param size: maximum number of entries, when more entries are added
           the oldest current entries will be removed.

        The attributes .missed and .replaced count the total number of reads
        never popped, and the number of reads chunks replaced by a chunk from
        the same read.
        """
        if size < 1:
            raise AttributeError("'size' must be >1.")
        self.size = size
        self.dict = OrderedDict()
        self.lock = Lock()
        self.missed = 0
        self.replaced = 0

    def __getitem__(self, key):
        with self.lock:
            return self.dict[key]

    def __setitem__(self, key, value):
        with self.lock:
            counted = False
            while len(self.dict) >= self.size:
                counted = True
                k, popped_value = self.dict.popitem(last=False)
                if k == key and popped_value.number == value.number:
                    self.replaced += 1
                else:
                    self.missed += 1
            if key in self.dict:
                if not counted:
                    if self.dict[key].number == value.number:
                        self.replaced += 1
                    else:
                        self.missed += 1
                del self.dict[key]
            self.dict[key] = value

    def __delitem__(self, key):
        with self.lock:
            del self.dict[key]

    def __len__(self):
        return len(self.dict)

    def popitem(self, last=True):
        """Return the newest (or oldest) entry.

        :param last: if `True` return the newest entry, else the oldest.

        """
        with self.lock:
            return self.dict.popitem(last=last)

    def popitems(self, items, last=True):
        """Return a list of the newest (or oldest) entries.

        :param items: maximum number of items to return, zero items may
            be return (i.e. an empty list).
        :param last: if `True` return the newest entry, else the oldest.

        """
        with self.lock:
            data = list()
            for _ in range(items):
                try:
                    item = self.dict.popitem(last=last)
                except KeyError:
                    pass
                else:
                    data.append(item)
            return data
