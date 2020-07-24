from collections import Counter, defaultdict,  OrderedDict
from itertools import count as _count
from threading import Event, Lock, Thread
import logging
import sys
import time
import uuid


try:
    import queue
except ImportError:
    import Queue as queue

import numpy

import minknow_api


if sys.version_info[0] < 3:
    NullRaw = ''
else:
    NullRaw = bytes('', 'utf8')


__all__ = ['ReadCache', 'ReadUntilClient', 'NullRaw']

# This replaces the results of an old call to MinKNOWs
# jsonRPC interface. That interface does not respond
# correctly when a run has been configured using the
# newer gRPC interace. This information is not currently
# available with the gRPC interface so as a temporary
# measure we list a standard set of values here.
CLASS_MAP = {
    'read_classification_map': {
        '83': 'strand',
        '67': 'strand1',
        '77': 'multiple',
        '90': 'zero',
        '65': 'adapter',
        '66': 'mux_uncertain',
        '70': 'user2',
        '68': 'user1',
        '69': 'event',
        '80': 'pore',
        '85': 'unavailable',
        '84': 'transition',
        '78': 'unclassed',
    }
}


def _numpy_type(desc):
    """Convert data type from RPC to numpy"""
    if desc.type == desc.SIGNED_INTEGER:
        type_char = "i"
    elif desc.type == desc.UNSIGNED_INTEGER:
        type_char = "u"
    elif desc.type == desc.FLOATING_POINT:
        type_char = "f"
    else:
        raise RuntimeError("Unknown type {}".format(desc))

    type_desc = "{}{}{}".format(">" if desc.big_endian else "<", type_char, desc.size)
    return numpy.dtype(type_desc)


class ReadCache(object):
    def __init__(self, size=100):
        """An ordered and keyed queue of a maximum size to store read chunks.

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
                k, v = self.dict.popitem(last=False)
                if k == key and v.number == value.number:
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
                except KeyError as e:
                    pass
                else:
                    data.append(item)
            return data


def _format_iter(data):
    # make a nice text string from iter
    data = list(data)
    result = ''
    if len(data) == 1:
        result = data[0]
    elif len(data) == 2:
        result = ' and '.join(data)
    else:
        result = ', '.join(data[:-1])
        result += ', and {}'.format(data[-1])
    return result


# Helper to generate new thread names
_counter = _count()
next(_counter)
def _new_thread_name(template="read_until-%d"):
    return template % next(_counter)


# The maximum allowed minimum read chunk size. Filtering of small read chunks
# from the gRPC stream is buggy. The value 0 effectively disables the 
# filtering functionality.
ALLOWED_MIN_CHUNK_SIZE = 0


class ReadUntilClient(object):

    def __init__(self, mk_host='127.0.0.1', mk_port=8000, cache_size=512, cache_type=ReadCache,
                 filter_strands=True, one_chunk=True, prefilter_classes={'strand', 'adapter'}):
        """A basic Read Until client. The class handles basic interaction
        with the MinKNOW gRPC stream and provides a thread-safe queue
        containing the most recent read data on each channel.

        :param mk_port: MinKNOW gRPC port for the sequencing device.
        :param cache_size: maximum number of read chunks to cache from
            gRPC stream. Setting this to the number of device channels
            will allow caching of the most recent data per channel.
        :param cache_type: a type derived from `ReadCache` for managing
            incoming read chunks. 
        :param filter_strands: pre-filter stream to keep only strand-like reads.
        :param one_chunk: attempt to receive only one_chunk per read. When
            enabled a request to stop receiving more data for a read is
            immediately staged when the first chunk is cached.
        :param prefilter_classes: a set of read classes to accept through
            prefilter. Ignored if filter_strands is `False`.

        To set up and use a client:

        >>> read_until_client = ReadUntilClient()

        This creates an initial connection to a MinKNOW instance in 
        preparation for setting up live reads stream. To initiate the stream:

        >>> read_until_client.run()

        The client is now recieving data and can send s
        Calls to methods of `read_until_client` can then be made in a separate
        thread. For example an continually running analysis function can be
        submitted to the executor as:

        >>> def analysis(client, *args, **kwargs):
        ...     while client.is_running:
        ...         for channel, read in client.get_read_chunks():
        ...             raw_data = numpy.fromstring(read.raw_data, client.signal_dtype)
        ...             # do something with raw data... and maybe call:
        ...             #    client.stop_receiving_read(channel, read.number)
        ...             #    client.unblock_read(channel, read.number)
        >>> with ThreadPoolExecutor() as executor:
        ...     executor.submit(analysis_function, read_until_client)

        To stop processing the gRPC read stream:

        >>> read_until_client.reset()

        If an analysis function is set up as above in response to
        `client.is_running`, calling the above call will cause the
        analysis function to return.

        """
        self.logger = logging.getLogger('ReadUntil')

        self.mk_host = mk_host
        self.mk_grpc_port = mk_port
        self.cache_size = cache_size
        self.CacheType = cache_type
        self.filter_strands = filter_strands
        self.one_chunk = one_chunk
        self.prefilter_classes = prefilter_classes

        client_type = 'single chunk' if self.one_chunk else 'many chunk'
        filters = ' '.join(self.prefilter_classes)
        filter_to = 'without prefilter'
        if self.filter_strands:
            if len(self.prefilter_classes) == 0:
                raise ValueError('Read filtering set but no filter classes given.')
            classes = _format_iter(self.prefilter_classes)
            filter_to = 'filtering to {} read chunks'.format(classes)
        self.logger.info('Creating {} client with {} data queue {}.'.format(
            client_type, self.CacheType.__name__, filter_to))

        self.logger.warn("Using pre-defined read classification map.")
        class_map = CLASS_MAP
        self.read_classes = {
            int(k):v for k, v in
            class_map['read_classification_map'].items()
        }
        self.strand_classes = set()
        for key, value in self.read_classes.items():
            if value in self.prefilter_classes:
                self.strand_classes.add(key)
        self.logger.debug('Strand-like classes are {}.'.format(self.strand_classes))

        self.grpc_port = self.mk_grpc_port
        self.logger.info('Creating rpc connection on port {}.'.format(self.grpc_port))
        self.connection = minknow_api.Connection(host=self.mk_host, port=self.grpc_port)
        self.logger.info('Got rpc connection.')
        self.msgs = self.connection.data._pb

        self.signal_dtype = _numpy_type(self.connection.data.get_data_types().calibrated_signal)

        # setup the queues and running status
        self._process_thread = None
        self.reset()


    def run(self, **kwargs):
        """Run Read Until analysis.

        :param **kwargs: keywork args for gRPC stream setup. Valid keys are:
            `first_channel`, `last_channel`, `raw_data_type`, and
            `sample_minimum_chunk_size`.
        """
        self._process_thread = Thread(
            target=self._run,
            name=_new_thread_name(),
            kwargs=kwargs
        )
        self._process_thread.start()
        self.logger.info("Processing started")


    def reset(self, timeout=5):
        """Reset the state of the client to an initial (not running) state with
        no data or requests in queues.

        """
        # self._process_reads is blocking => it runs in a thread.
        if self._process_thread is not None:
            self.logger.info("Reset request received, shutting down...")
            self.running.clear()
            self._process_thread.join() # block, try hard for .cancel() on stream
            if self._process_thread.is_alive():
                self.logger.warn("Stream handler did not finish correctly.")
            else:
                self.logger.info("Stream handler exited successfully.")
        self._process_thread = None

        # a flag to indicate whether gRPC stream is being processed. Any
        #    running ._runner() will respond to this.
        self.running = Event()
        # the action_queue is used to store unblock/stop_receiving_data
        #    requests before they are put on the gRPC stream.
        self.action_queue = queue.Queue()
        # the data_queue is used to store the latest chunk per channel
        self.data_queue = self.CacheType(size=self.cache_size)
        # stores all sent action ids -> unblock/stop
        self.sent_actions = dict()


    @property
    def aquisition_progress(self):
        """Get MinKNOW data acquisition progress.

        :returns: a structure with attributes .acquired and .processed.

        """
        return self.connection.acquisition.get_progress().raw_per_channel


    @property
    def queue_length(self):
        """The length of the read queue."""
        return len(self.data_queue)


    @property
    def missed_reads(self):
        """Number of reads ejected from queue (i.e reads had one or more chunks
        enter into the analysis queue but were replaced with a distinct read
        before being pulled from the queue."""
        return self.data_queue.missed


    @property
    def missed_chunks(self):
        """Number of read chunks replaced in queue by a chunk from the same
        read (a single read may have its queued chunk replaced more than once).

        """
        return self.data_queue.replaced


    @property
    def is_running(self):
        """The processing status of the gRPC stream."""
        return self.running.is_set()


    def get_read_chunks(self, batch_size=1, last=True):
        """Get read chunks, removing them from the queue.

        :param batch_size: maximum number of reads.
        :param last: get the most recent (else oldest)?

        """
        return self.data_queue.popitems(items=batch_size, last=True)


    def unblock_read(self, read_channel, read_number, duration=0.1):
        """Request that a read be unblocked.

        :param read_channel: a read's channel number.
        :param read_number: a read's read number (the nth read per channel).
        :param duration: time in seconds to apply unblock voltage.

        """
        self._put_action(read_channel, read_number, 'unblock', duration=duration)


    def stop_receiving_read(self, read_channel, read_number):
        """Request to receive no more data for a read.

        :param read_channel: a read's channel number.
        :param read_number: a read's read number (the nth read per channel).

        """
        self._put_action(read_channel, read_number, 'stop_further_data')


    def _run(self, **kwargs):
        self.running.set()
        # .get_live_reads() takes an iterable of requests and generates
        #    raw data chunks and responses to our requests: the iterable
        #    thereby controls the lifetime of the stream. ._runner() as
        #    implemented below initialises the stream then transfers
        #    action requests from the action_queue to the stream.
        reads = self.connection.data.get_live_reads(
            self._runner(**kwargs)
        )

        # ._process_reads() as implemented below is responsible for
        #    placing action requests on the queue and logging the responses.
        #    We really want to be calling reads.cancel() below so catch
        #    everything and anything.
        try:
            self._process_reads(reads)
        except Exception as e:
            self.logger.info(e)

        # signal to the server that we are done with the stream.
        reads.cancel()


    def _runner(self, first_channel=1, last_channel=512, min_chunk_size=ALLOWED_MIN_CHUNK_SIZE, action_batch=1000, action_throttle=0.001):
        """Yield the stream initializer request followed by action requests
        placed into the action_queue.

        :param first_channel: lowest channel for which to receive raw data.
        :param last_channel: highest channel (inclusive) for which to receive data.
        :param min_chunk_size: minimum number of raw samples in a raw data chunk.
        :param action_batch: maximum number of actions to batch in a single response.

        """
        # see note at top of this module
        if min_chunk_size > ALLOWED_MIN_CHUNK_SIZE:
            self.logger.warning("Reducing min_chunk_size to {}".format(ALLOWED_MIN_CHUNK_SIZE))
            min_chunk_size = ALLOWED_MIN_CHUNK_SIZE

        self.logger.info(
            "Sending init command, channels:{}-{}, min_chunk:{}".format(
            first_channel, last_channel, min_chunk_size)
        )
        yield self.msgs.GetLiveReadsRequest(
            setup=self.msgs.GetLiveReadsRequest.StreamSetup(
                first_channel=first_channel,
                last_channel=last_channel,
                raw_data_type=self.msgs.GetLiveReadsRequest.CALIBRATED,
                sample_minimum_chunk_size=min_chunk_size
            )
        )

        t0 = time.time()
        while self.is_running:
            t0 = time.time()
            # get as many items as we can up to the maximum, without blocking
            actions = list()
            for _ in range(action_batch):
                try:
                    action = self.action_queue.get_nowait()
                except queue.Empty:
                    break
                else:
                    actions.append(action)

            n_actions = len(actions)
            if n_actions > 0:
                self.logger.debug('Sending {} actions.'.format(n_actions))
                action_group = self.msgs.GetLiveReadsRequest(
                    actions=self.msgs.GetLiveReadsRequest.Actions(actions=actions)
                )
                yield action_group

            # limit response interval
            t1 = time.time()
            if t0 + action_throttle > t1:
                time.sleep(action_throttle + t0 - t1)
        else:
            self.logger.info("Reset signal received by action handler.")


    def _process_reads(self, reads):
        """Process the gRPC stream data, storing read chunks in the data_queue.

        :param reads: gRPC data stream iterable as produced by get_live_reads().
        
        """
        response_counter = defaultdict(Counter)

        unique_reads = set()

        read_count = 0
        samples_behind = 0
        raw_data_bytes = 0
        last_msg_time = time.time()
        for reads_chunk in reads:
            if not self.is_running:
                self.logger.info('Stopping processing of reads due to reset.')
                break
            # In each iteration, we get:
            #   i) responses to our previous actions (success/fail)
            #  ii) raw data for current reads

            # record a count of success and fails            
            if len(reads_chunk.action_responses):
                for response in reads_chunk.action_responses:
                    action_type = self.sent_actions[response.action_id]
                    response_counter[action_type][response.response] += 1

            progress = self.aquisition_progress
            for read_channel in reads_chunk.channels:
                read_count += 1
                read = reads_chunk.channels[read_channel]
                if self.one_chunk:
                    if read.id in unique_reads:
                        # previous stop request wasn't enacted in time, don't
                        #   put the read back in the queue to avoid situation
                        #   where read has been popped from queue already and
                        #   we reinsert.
                        self.logger.debug(
                            'Rereceived {}:{} after stop request.'.format(
                            read_channel, read.number
                        ))
                        continue
                    self.stop_receiving_read(read_channel, read.number)
                unique_reads.add(read.id)
                read_samples_behind = progress.acquired - read.chunk_start_sample
                samples_behind += read_samples_behind
                raw_data_bytes += len(read.raw_data)

                strand_like = any([x in self.strand_classes for x in read.chunk_classifications])
                if not self.filter_strands or strand_like:
                    self.data_queue[read_channel] = read

            now = time.time()
            if last_msg_time + 1 < now:
                self.logger.info(
                    "Interval update: {} read sections, {} unique reads (ever), "
                    "average {:.0f} samples behind. {:.2f} MB raw data, "
                    "{} reads in queue, {} reads missed, {} chunks replaced."
                    .format(
                        read_count, len(unique_reads),
                        samples_behind/read_count, raw_data_bytes/1024/1024,
                        self.queue_length, self.missed_reads, self.missed_chunks
                    )
                )
                self.logger.info("Response summary: {}".format(response_counter))

                read_count = 0
                samples_behind = 0
                raw_data_bytes = 0
                last_msg_time = now


    def _put_action(self, read_channel, read_number, action, **params):
        """Stores an action requests on the queue ready to be placed on the
        gRPC stream.

        :param read_channel: a read's channel number.
        :param read_number: a read's read number (the nth read per channel).
        :param action: either 'stop_further_data' or 'unblock'.
        :param params: dictionary of parameters for action. Allowed values
            are: 'duration' for `action='unblock'`.

        """
        action_id = str(uuid.uuid4())
        action_kwargs = {
            'action_id': action_id,
            'channel': read_channel,
            'number': read_number,
        }
        self.sent_actions[action_id] = action
        if action == 'stop_further_data':
            action_kwargs[action] = self.msgs.GetLiveReadsRequest.StopFurtherData()
        elif action == 'unblock':
            action_kwargs[action] = self.msgs.GetLiveReadsRequest.UnblockAction()
            if 'duration' in params:
                action_kwargs[action].duration = params['duration']
        else:
            raise ValueError("'action' parameter must must be 'stop_further_data' or 'unblock'.")

        action_request = self.msgs.GetLiveReadsRequest.Action(**action_kwargs)
        self.action_queue.put(action_request)
        self.logger.debug('Action {} on channel {}, read {} : {}'.format(
            action_id, read_channel, read_number, action
        ))


