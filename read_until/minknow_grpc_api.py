"""
Wrapper around MinKNOW API, which uses minknow python if available,
or its own built in minknow grpc code if not.

Its important to use minknow if available as only one instance
of a protobuf can exist in a single instance of python.
"""

import os
import sys

remove_extra_import = False
try:
    import minknow.rpc
except ImportError:
    root_dir = os.path.dirname(__file__)
    import_path = os.path.join(root_dir, "generated")
    sys.path.append(import_path)
    remove_extra_import = True

import minknow.rpc.data_pb2 as data_pb2
import minknow.rpc.data_pb2_grpc as data_pb2_grpc
import minknow.rpc.acquisition_pb2 as acquisition_pb2
import minknow.rpc.acquisition_pb2_grpc as acquisition_pb2_grpc

if remove_extra_import:
    assert sys.path[-1] == import_path
    del sys.path[-1]
