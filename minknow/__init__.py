"""APIs for interacting with MinKNOW.

This module contains code for interacting with the MinKNOW instrument software, which controls
single-molecule sequencing devices including MinIONs, GridIONs and PromethIONs.
"""

#from __future__ import absolute_import, division, print_function, unicode_literals

__author__ = "Oxford Nanopore Technologies, Ltd."
#from ._version import __version__

__all__ = [
    # submodules
    'rpc',

    # classes
    #'EngineClient',
    ]

#from .engine_client import EngineClient
from . import rpc
from ._rpc_wrapper import *
