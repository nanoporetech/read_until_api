Read Until
==========

The Read Until API provides a mechanism for a client script to connect to a
MinKNOW server. The server can be asked to push a raw data to the client 
script in real-time. The data can be analysed in the way most fit for purpose, 
and a return call can be made to the server to unblock the read in progress.

Installation
------------

The package can be installed into MinKNOW's python environment using the
python interpreter in the MinKNOW root directory. For example on Ubuntu:

    sudo /opt/ONT/MinKNOW/ont-python/bin/python setup.py install

Two demonstration programs are provided (and are installed into
MinKNOW/ont-python/bin/):

   1.  `read_until_simple`: this serves as a simple test, and the code
       demonstrates use of basic functionality for develops
       (read_until.simple).
   2.  `read_until_ident`: this is a rather more fully featured example of use
       of the API to identify reads via basecalling and alignment. To run it
       requires the optional dependencies of scrappy and mappy. The latter of
       these can be installed via `ont-python/bin/python -m pip install mappy`,
       whilst the former can be obtained from Oxford Nanopore Technologies'
       github repositories.

