Prototype real-time analysis components
=======================================

[![Build Status](https://travis-ci.org/nanoporetech/pomoxis.svg?branch=master)](https://travis-ci.org/nanoporetech/pomoxis)

Pomoxis contains a set of services to perform analysis of squiggles as they are
produced in real-time along with fast pipelines for generating draft assemblies.

Documentation can be found at https://nanoporetech.github.io/pomoxis/.
  

Build
-----

Pomoxis should be installed inside a virtual environment. A Makefile is
provided to fetch, compile and install all direct dependencies into an
environment.

To setup the environment run:

    git clone --recursive https://git/research/pomoxis.git
    cd pomoxis
    make install
    . ./venv/bin/activate


Extras
------

The distribution bundles some common bioinformatics tools (some of which are not
currently used by pomoxis itself):

* miniasm
* minimap
* racon
* bwa
* samtools

These will be compiled and installed into the virtual environment created as above.
