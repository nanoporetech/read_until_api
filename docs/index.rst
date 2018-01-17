Welcome to read_until_raw's documentation!
==================================



Installation
------------

The package should be installed inside a virtual environment. A Makefile is
provided to fetch, compile and install all direct dependencies into an
environment. (Some additional build dependencies may not installed via this
Makefile, see `.travis.yml` for additional requirements if things fail).

To setup the environment run:

.. code-block:: bash
    git clone --recursive https://git/research/read_until_raw.git
    cd read_until_raw
    make install
    . ./venv/bin/activate

See :doc:`examples` for common workflows.

Contents
--------

.. toctree::
   :maxdepth: 2

   examples

Full API reference
------------------

.. toctree::
   :maxdepth: 3
      
   read_until_raw 

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

