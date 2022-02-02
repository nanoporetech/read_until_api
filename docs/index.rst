Welcome to the Read Until API
=============================

The Read Until API provides a mechanism for a client script to connect to a
MinKNOW server. The server provides raw data to the client script in real-time,
allowing it to be analysed in the way most fit for purpose. Then the client
script can send a response to the server to unblock a read that is in progress.

Installation
------------

The package can be installed into a virtual environment or MinKNOW's python
environment.

Two demonstration programs are provided in the ``examples`` directory:

   i)  read_until_simple: this serves as a simple test, and the code
       demonstrates use of basic functionality for developers
       (read_until.simple).
   ii) read_until_ident: this is a more fully-featured example of the
       API to identify reads via base-calling and alignment. To run it
       requires the optional dependency ``ont-pyguppy-client-lib`` (see https://pypi.org/project/ont-pyguppy-client-lib/).


Full API reference
------------------

.. toctree::
   :maxdepth: 2

   read_until
