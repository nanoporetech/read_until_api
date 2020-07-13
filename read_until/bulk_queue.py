from threading import Condition


class BulkQueue(object):
    """
    A basic Queue that has the ability to:
    * pop/put an item
    * pop all in queue
    * put an iterable in the queue

    Get/get_all by default will wait until there is something in the queue.
    """

    def __init__(self):
        self._condition = Condition()
        self._list = []

    def put(self, item):
        """
        Put item in the queue

        :param item: Any item
        """
        self.put_iterable([item])

    def put_iterable(self, items):
        """
        Extend the queue with an iterable of items

        :param items: Iterable of items to put in queue
        """
        with self._condition:
            self._list.extend(items)
            self._condition.notify()

    def pop(self, timeout=None):
        """
        Pops an item from the front of the queue. If timeout is None/0, try to pop
        immediately else wait up to timeout seconds for there to be something in the queue.

        If there is nothing in the queue, an IndexError will be raised.

        :param timeout: How long to wait for, in seconds, for an item to appear
        :returns: First item in the queue
        """
        with self._condition:
            if not self._list and timeout:
                self._condition.wait_for(lambda: len(self._list) > 0, timeout=timeout)
            return self._list.pop(0)

    def pop_all(self, timeout=None):
        """
        Pops all elements from the queue. If timeout is None/0, pop all immediately
        else wait up to timeout seconds for there to be something in the queue.

        :param timeout: How long to wait for, in seconds, for items to appear
        :returns: All items in the queue
        :rtype: list
        """
        with self._condition:
            if not self._list and timeout:
                self._condition.wait_for(lambda: len(self._list) > 0, timeout=timeout)
            result, self._list = self._list, []
            return result
