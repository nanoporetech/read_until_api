Welcome to the Read Until API
=============================

This package provides a high level API to the raw read data streaming
functionality in MinKNOW.

Installation
------------

The package can be installed into MinKNOW's python environment using the
python interpreter in the MinKNOW root directory. For example on Ubuntu:

.. code-block:: bash

    sudo /opt/ONT/MinKNOW/ont-python/bin/python setup.py install


Two demonstration programs are provided (and are installed into
MinKNOW/ont-python/bin/):

   i)  read_until_simple: this serves as a simple test, and the code
       demonstrates use of basic functionality for develops
       (read_until.simple).
   ii) read_until_ident: this is a rather more fully featured example of use
       of the API to identify reads via basecalling and alignment. To run it
       requires the optional dependencies of scrappy and mappy. The latter of
       these can be installed via `ont-python/bin/python -m pip install mappy`,
       whilst the former can be obtained from Oxford Nanopore Technologies'
       github repositories.


Full API reference
------------------

.. toctree::
   :maxdepth: 3
      
   read_until 

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

