"""
Wrapper around MinKNOW API, which uses minknow python if available,
or its own built in minknow grpc code if not.

Its important to use minknow if available as only one instance
of a protobuf can exist in a single instance of python.
"""

import os
import sys

# pylint: disable=invalid-name
remove_extra_import = False
try:
    import minknow.rpc  # pylint: disable=unused-import
except ImportError:
    root_dir = os.path.dirname(__file__)
    import_path = os.path.join(root_dir, "generated")
    sys.path.append(import_path)
    remove_extra_import = True

# pylint: disable=wrong-import-position
import minknow.rpc.acquisition_pb2 as acquisition_pb2
import minknow.rpc.acquisition_pb2_grpc as acquisition_pb2_grpc
import minknow.rpc.analysis_configuration_pb2 as analysis_configuration_pb2
import minknow.rpc.analysis_configuration_pb2_grpc as analysis_configuration_pb2_grpc
import minknow.rpc.data_pb2 as data_pb2
import minknow.rpc.data_pb2_grpc as data_pb2_grpc

__all__ = [
    "acquisition_pb2",
    "acquisition_pb2_grpc",
    "analysis_configuration_pb2",
    "analysis_configuration_pb2_grpc",
    "data_pb2",
    "data_pb2_grpc",
]

if remove_extra_import:
    assert sys.path[-1] == import_path
    del sys.path[-1]
