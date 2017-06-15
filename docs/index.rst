.. TODO fill in name
Welcome to {}'s documentation!
==================================

.. TODO: add description

Installation
------------

The package should be installed inside a virtual environment. A Makefile is
provided to fetch, compile and install all direct dependencies into an
environment. (Some additional build dependencies may not installed via this
Makefile, see `.travis.yml` for additional requirements if things fail).

To setup the environment run:

.. code-block:: bash
    #TODO: amend this
    git clone --recursive https://git/research/pomoxis.git
    cd pomoxis
    make install
    . ./venv/bin/activate

See :doc:`examples` for common workflows.

Contents
--------

.. toctree::
   :maxdepth: 2

   examples
.. TODO: add more pages

Full API reference
------------------

.. toctree::
   :maxdepth: 3
      
   pomoxis
.. TODO: change name above

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

