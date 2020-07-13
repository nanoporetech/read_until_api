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
        Pop an item from the front of the queue. If timeout is specified an IndexError
        will be raised if there is nothing in the list after the timeout has occurred.
        This is by design as None type could have been added to the list.

        :param timeout: How long to wait for, in seconds, for an item to appear
        :returns: First item in the queue
        """
        with self._condition:
            if not self._list:
                self._condition.wait_for(lambda: len(self._list) > 0, timeout=timeout)
            return self._list.pop(0)

    def pop_all(self, timeout=None):
        """
        Waits at most timeout seconds for the queue to be non empty.
        When the queue is non empty or timeout is reached, the elements in the queue
        are returned (And popped)

        :param timeout: How long to wait for, in seconds, for items to appear
        :returns: All items in the queue
        """
        with self._condition:
            if not self._list:
                self._condition.wait_for(lambda: len(self._list) > 0, timeout=timeout)
            result, self._list = self._list, []
            return result
