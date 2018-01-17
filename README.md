[//]: 
Read Until2
===========

Temporary Build Instructions
----------------------------

    make -f MakegRPC.mk build
    make install

This will glone the .proto files and try to build them (with a lot of nastiness)
Included are modified versions of the files `minknow/rpc/*service.py`: nasty
python2 relative imports have been amended and additional imports of `*pb_grpc`
have been added. All of this needs fixing upstream.




[//]: 
[![Build Status](https://travis-ci.org/nanoporetech/read_until.svg?branch=master)](https://travis-ci.org/nanoporetech/read_until)

[//]: 
The Read Until API provides a mechanism for a client script to connect to a
MinKNOW server. The server can be asked to push a raw data to the client 
script in real-time. The data can be analysed in the way most fit for purpose, 
and a return call can be made to the server to unblock the read in progress.

[//]: 
Documentation can be found at https://nanoporetech.github.io/read_until/.


Build
-----

The project should be installed inside a virtual environment. A Makefile is
provided to fetch, compile and install all direct dependencies into an
environment.

To setup the environment run:

    git clone --recursive https://github.com/nanoporetech/read_until
    cd read_until 
    make install
    . ./venv/bin/activate

