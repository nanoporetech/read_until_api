import threading

class StatusWatcher(object):
    """
    Convenience wrapper for monitoring acquisition status.

    To use this class, simply call watcher.wait() as if looping through a generator, then
    after you are done with the watcher, call watcher.stop() (within the loop still) and then
    wait for the generator to close and it will exit the loop.

    If you break out of the loop then the cpp side may use some extra resources as it will not
    be immediately notified that the stream has been cancelled

    >>> watcher = StatusWatcher(rpc_connection)
    >>> msgs = minknow.rpc.acquisition_service
    >>> for status in status_watcher.wait():
    >>>     if status.status == msgs.PROCESSING:
    >>>         connection.acquisition.stop(data_action_on_stop=msgs.StopRequest.STOP_KEEP_ALL_DATA, wait_until_ready=True)
    >>>     elif status.status == msgs.READY:
    >>>         watcher.stop()

    """

    def __init__(self, connection):
        self.connection = connection
        self.is_stopped = False
        self.cv = threading.Condition()

    def wait(self):
        return self.connection.acquisition.watch_for_status_change(self._wait_for_stop())

    def stop(self):
        self.cv.acquire()
        self.is_stopped = True
        self.cv.notify()
        self.cv.release()

    def _wait_for_stop(self):
        self.cv.acquire()
        while not self.is_stopped:
            self.cv.wait()
        self.cv.release()
        req = self.connection.acquisition._pb.WatchForStatusChangeRequest()
        req.stop = True
        yield req
