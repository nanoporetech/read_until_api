"""
MinKNOW RPC Access
==================

Provides access to MinKNOW via RPC.

This RPC system is gRPC-based. You might want to look at the `gRPC
documentation <http://www.grpc.io/grpc/python/>`_ for more information, but most
of the detail is hidden by the code in this module.

The RPC system is divided into services, covering related units of functionality
like controlling the device or managing data acquisition.

The core class is :py:class:`Connection` - this provides a connection to MinKNOW, with a
property for each service.

For each service, the related Protobuf messages are available from
``minknow.rpc.<service>_service``, or as ``connection.<service>._pb``
(if ``connection`` is a Connection object).


.. _rpc-services:

Services
--------

The available services are:

acquisition
    Control data acquisition. This includes setting up the analysis configuration. See
    :py:class:`acquisition_service.AcquisitionService` for a description of the available methods.
device
    Get information about and control the attached device. This useful presents information and
    settings in a device-independent way, so it can be used on PromethIONs as easily as on MinIONs.
    See :py:class:`device_service.DeviceService` for a description of the available methods.
instance
    Get information about the instance of MinKNOW you are connected to (eg: software version).
    See :py:class:`instance_service.InstanceService` for a description of the available methods.
minion_device
    MinION-specific device interface. This exposes low-level settings for MinIONs and similar
    devices (eg: GridIONs). See :py:class:`minion_device_service.MinionDeviceService` for a
    description of the available methods.
protocol
    Control protocol scripts. See :py:class:`protocol_service.ProtocolService` for a description of
    the available methods.


Convenience Wrappers
--------------------

The :py:class:`StatusWatcher` class provides a more convenient interface to the
:py:meth:`acquisition.AcquisitionService.watch_for_status_change` method.

"""


#
# Services
#
_services = {
    'acquisition': ['AcquisitionService'],
    'analysis_configuration': ['AnalysisConfigurationService'],
    'data': ['DataService'],
    'device': ['DeviceService'],
    'keystore': ['KeyStoreService'],
    'instance': ['InstanceService'],
    'log': ['LogService'],
    'minion_device': ['MinionDeviceService'],
    'protocol': ['ProtocolService'],
    'production': ['ProductionService'],
    'promethion_device': ['PromethionDeviceService'],
}
_optional_services = ['production']


#
# Module meta-information
#

__all__ = [svc + '_service' for svc in _services] + [
    'StatusWatcher',
    'Connection',
]


#
# Submodule imports
#

from .wrappers import StatusWatcher

# Convenience imports for each service
import importlib
for svc in _services:
    try:
        # effectively does `import .{svc}_service as {svc}_service`
        vars()[svc + '_service'] = importlib.import_module('.{}_service'.format(svc), __name__)
    except ImportError:
        if svc not in _optional_services:
            raise


#
# Connection class
#

class Connection(object):
    """A connection to MinKNOW via RPC.

    Note that this only provides access to the new RPC system. The old one is
    available via the minknow.engine_client module.

    Each service is available as a property of the same name on the Connection
    object. See :ref:`rpc-services` for a list.

    Given a connection object ``connection``, for each service,
    ``connection.<service>`` is a "service object". This exposes the RPC methods
    for that service in a more convenient form than gRPC's own Python bindings
    do.

    For example, when calling ``start_protocol`` on the ``protocol`` service,
    instead of doing

    >>> protocol_service.start_protocol(
    >>>     protocol_service._pb.StartProtocolMessage(path="my_script"))

    you can do

    >>> connection.protocol.start_protocol(path="my_script")

    Note that you must use keyword arguments - no positional parameters are
    available.

    This "unwrapping" of request messages only happens at one level, however. If
    you want to change the target temperature settings on a MinION, you need to do
    something like

    >>> temp_settings = connection.minion_device._pb.TemperatureRange(min=37.0, max=37.0)
    >>> connection.minion_device.change_settings(
    >>>     temperature_target=temp_settings)
    """

    def __init__(self, port=None, host='127.0.0.1'):
        """Connect to MinKNOW.

        The port for a given instance of MinKNOW is provided by the manager
        service.

        If no port is provided, it will attempt to get the port from the
        MINKNOW_RPC_PORT environment variable (set for protocol scripts, for
        example). If this environment variable does not exist (or is not a
        number), it will raise an error.

        :param port: the port to connect on (defaults to ``MINKNOW_RPC_PORT`` environment variable)
        :param host: the host MinKNOW is running on (defaults to localhost)
        """
        import grpc, os

        self.host = host
        if port is None:
            port = int(os.environ['MINKNOW_RPC_PORT'])
        self.port = port

        self.channel = grpc.insecure_channel("{}:{}".format(host, port))

        # One entry for each service
        for name, svc_list in _services.items():
            for svc in svc_list:
                try:
                    # effectively does `self.{name} = {name}_service.{svc}(self.channel)`
                    setattr(self, name, getattr(globals()[name + '_service'], svc)(self.channel))
                except KeyError:
                    if name not in _optional_services:
                        raise
