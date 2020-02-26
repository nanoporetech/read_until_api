"""
Wrapper around MinKNOW API, which uses minknow python if available,
or its own built in minknow grpc code if not.

Its important to use minknow if available as only one instance
of a protobuf can exist in a single instance of python.
"""

import os
import sys

# pylint: disable=invalid-name
path_addition = None
try:
    import minknow.rpc  # pylint: disable=unused-import
except ImportError:
    for path in sys.path:
        potential_path_addition = os.path.join(path, "read_until", "generated")
        generated_file = os.path.join(
            potential_path_addition, "minknow", "rpc", "data_pb2.py"
        )
        if os.path.exists(generated_file):
            sys.path.append(potential_path_addition)
            path_addition = potential_path_addition
            break

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

if path_addition is not None:
    del sys.path[sys.path.index(path_addition)]
