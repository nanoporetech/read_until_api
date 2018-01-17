from __future__ import absolute_import, division, print_function, unicode_literals

import collections
import minknow.rpc
import numpy

from enum import Enum

__all__ = [
    'DeviceType',
    'Device',
    ]


class DeviceType(Enum):
    """The type of device."""
    MINION = minknow.rpc.device_service.GetDeviceInfoResponse.MINION
    PROMETHION = minknow.rpc.device_service.GetDeviceInfoResponse.PROMETHION
    PROMETHION_BETA = minknow.rpc.device_service.GetDeviceInfoResponse.PROMETHION_BETA
    GRIDION = minknow.rpc.device_service.GetDeviceInfoResponse.GRIDION

    def is_minion_like(self):
        """Whether the device acts like a MinION."""
        return self in [DeviceType.MINION, DeviceType.GRIDION]

    def is_promethion_like(self):
        """Whether the device acts like a PromethION."""
        return self in [DeviceType.PROMETHION, DeviceType.PROMETHION_BETA]


def _numpy_type(desc):
    if desc.type == desc.SIGNED_INTEGER:
        type_char = 'i'
    elif desc.type == desc.UNSIGNED_INTEGER:
        type_char = 'u'
    elif desc.type == desc.FLOATING_POINT:
        type_char = 'f'
    else:
        raise RuntimeError("Unknown type format {}".format(desc))
    type_desc = '{}{}{}'.format('>' if desc.big_endian else '<',
                                type_char,
                                desc.size)
    return numpy.dtype(type_desc)


ChannelConfigChange = collections.namedtuple('ChannelConfigChange', ['offset', 'config'])
ChannelSignalData = collections.namedtuple('ChannelSignalData', [
    'name',
    'signal',
    'config_changes',
    ])
SignalData = collections.namedtuple('SignalData', [
    'samples_since_start',
    'seconds_since_start',
    'channels',
    'bias_voltages'
    ])

NumpyDTypes = collections.namedtuple('NumpyDTypes', [
    'bias_voltages',
    'calibrated_signal',
    'uncalibrated_signal',
])


class Device(object):
    """High-level interface to a sequencing device.

    This can be used to control a single MinION, or a single flowcell port on a PromethION or
    GridION. It hides the details of the MinKNOW RPC interface (although the ``rpc`` property can be
    used to access the RPCs directly).

    Note that channels are counted from 1.

    Properties:

    rpc -- a minknow.rpc.Connection instance
    version_info -- the version information of the MinKNOW instance that has been connected to
    output_dirs -- the output directories of the MinKNOW instance
    device_info -- information about the device MinKNOW is managing
    numpy_data_types -- a NumpyDTypes tuple describing the data types provided by the data rpc service

    :param connection: a minknow.rpc.Connection object
    """

    def __init__(self, connection=None):
        if connection is None:
            self.rpc = minknow.rpc.Connection()
        else:
            self.rpc = connection
        self.version_info = self.rpc.instance.get_version_info()
        self.output_dirs = self.rpc.instance.get_output_directories()
        self.device_info = self.rpc.device.get_device_info()
        self._data_types = self.rpc.data.get_data_types()
        self.numpy_data_types =  NumpyDTypes(
            _numpy_type(self._data_types.bias_voltages),
            _numpy_type(self._data_types.calibrated_signal),
            _numpy_type(self._data_types.uncalibrated_signal),
        )

    def __repr__(self):
        return "<minknow.Device for {}>".format(self.device_info.device_id)

    @property
    def minknow_version(self):
        """The MinKNOW version, as a string."""
        return self.version_info.minknow.full

    @property
    def protocols_version(self):
        """The version of the installed protocols, as a string."""
        return self.version_info.protocols

    @property
    def output_directory(self):
        """The location of the output directory.

        The returned path is only valid on the machine that MinKNOW is running on.
        """
        return self.output_dirs.output

    @property
    def log_directory(self):
        """The location MinKNOW writes its logs to.

        The returned path is only valid on the machine that MinKNOW is running on.
        """
        return self.output_dirs.log

    @property
    def reads_directory(self):
        """The location MinKNOW writes reads files to.

        Note that reads will actually be written to subdirectories of this location, depending on
        the read writer configuration.

        The returned path is only valid on the machine that MinKNOW is running on.
        """
        return self.output_dirs.reads

    @property
    def device_type(self):
        """The type of device."""
        return DeviceType(self.device_info.device_type)

    @property
    def device_id(self):
        """The globally unique identifier for the device."""
        return self.device_info.device_id

    @property
    def flowcell_info(self):
        """Information about the attached flowcell, if any.

        Returns None if no flowcell is attached. Otherwise, returns an object with at least the
        following attributes:

        channel_count -- the number of channels available
        wells_per_channel    -- the number of wells available
        flowcell_id   -- the unique identifier of the attached flowcell
        """
        # TODO: when we have a streaming version of flowcell_info, cache this stuff and watch for
        # changes
        info = self.rpc.device.get_flowcell_info()
        if info.has_flowcell:
            return info
        return None

    def get_signal(self, **kwargs):
        """Get signal data from the device.

        This can be used to sample the signal being produced by the device. The signal can be
        returned as raw ADC values or as calibrated picoamp (pA) values; see ``set_calibration`` on
        the device service for the values used in this conversion.

        In addition to the signal, this can return the associated channel configuration and/or bias
        voltage information, to help analyse the data.

        If a device settings change RPC has completed before this method is called, the data returned
        is guaranteed to have been generated by the device after those settings were applied.
        However, note that no guarantee is made about how device settings changes that overlap with
        this request will affect the returned data.

        Exactly one of ``seconds`` or ``samples`` must be provided.

        The returned named tuple has the following fields:

        samples_since_start
            The number of samples collected before the first returned sample.
        seconds_since_start
            As samples_since_start, but expressed in seconds.
        channels
            A ChannelSignalData tuple (see below).
        bias_voltages
            If bias voltages were requested, a numpy array of bias voltages in millivolts. This will
            be the same length as the ``signal`` array on each channel. Note that there should be no
            need to apply any further corrections to the value (eg: the 5x amplifier on a MinION is
            already accounted for). Be aware that the types stored in this array will be different
            for MinION-like devices (integers) and PromethION-like devices (floating-point).

        The ChannelSignalData tuple has the following fields:

        name
            The name of the channel.
        signal
            The signal data, as a 1-dimensional numpy array.
        config_changes
            If channel configuration changes were requested, a list of those changes (each of which
            has an ``offset`` field, which is an offset into the signal array, and a ``config``
            field, which contains the updated configuration for the channel). This will contain at
            least one element, with offset 0, which is the configuration that applies to the first
            sample returned.

        :param seconds: Amount of data to collect in seconds
        :param samples: Amount of data to collect in samples
        :param first_channel: The first channel to collect data from.
        :param last_channel: The last channel to collect data from.
        :param include_channel_configs: Whether to return changes in channel configurations.
        :param include_bias_voltages: Whether to return bias voltage information.
        :param calibrated_data: Whether to calibrate the data
        :returns: a SignalData named tuple
        """
        if kwargs.get('calibrated_data', False):
            signal_dtype = self.numpy_data_types.calibrated_signal
        else:
            signal_dtype = self.numpy_data_types.uncalibrated_signal

        reserve_size = kwargs.get('samples', 0)
        # don't raise here when these keys are missing - let the RPC call raise the correct error
        # instead
        first_channel = kwargs.get('first_channel', 0)
        channel_count = kwargs.get('last_channel', 0) + 1 - first_channel

        include_bias_voltages = kwargs.get('include_bias_voltages', False)
        if include_bias_voltages:
            bias_voltage_dtype = _numpy_type(self._data_types.bias_voltages)
            bias_voltages = numpy.zeros(reserve_size, bias_voltage_dtype)
        else:
            bias_voltages = []
        channel_configs = [[] for i in range(channel_count)]

        signal = [numpy.zeros(reserve_size, signal_dtype) for i in range(channel_count)]

        start_samples = None
        for msg in self.rpc.data.get_signal_bytes(**kwargs):
            if start_samples is None:
                offset = 0
                start_samples = msg.samples_since_start
                start_seconds = msg.seconds_since_start
            else:
                offset = msg.samples_since_start - start_samples
            for i, c in enumerate(msg.channels, start=msg.skipped_channels):
                arr = numpy.fromstring(c.data, signal_dtype)
                if reserve_size:
                    signal[i][offset:offset+len(arr)] = arr
                else:
                    signal[i] = numpy.append(signal[i], arr)
                if len(c.config_changes):
                    for change in c.config_changes:
                        channel_configs[i].append(ChannelConfigChange(change.offset + offset,
                                                                      change.config))
            if len(msg.bias_voltages):
                arr = numpy.fromstring(msg.bias_voltages, bias_voltage_dtype)
                if reserve_size:
                    bias_voltages[offset:offset+len(arr)] = arr
                else:
                    bias_voltages = numpy.append(bias_voltages, arr)

        return SignalData(
                start_samples,
                start_seconds,
                [
                    ChannelSignalData(name, signal, configs)
                    for name, (signal, configs)
                    in enumerate(zip(signal, channel_configs), start=first_channel)
                ],
                bias_voltages)



