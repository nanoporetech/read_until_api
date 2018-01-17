[//]: 
Read Until Raw
==============


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

