Ubuntu Installation
-------------------

*The following walkthrough for installing MinKNOW with the Read Until API on
Ubuntu 16.04 was contributed by [ArtemD](https://github.com/danartei).*

Begin by installing MinKNOW as in the [guide](https://community.nanoporetech.com/protocols/experiment-companion-minknow/v/mke_1013_v1_revaj_11apr2016/installing-minknow-on-linu):

    sudo apt-get update
    wget -O- https://mirror.oxfordnanoportal.com/apt/ont-repo.pub | sudo apt-key add -
    echo "deb http://mirror.oxfordnanoportal.com/apt xenial-stable non-free" | sudo tee /etc/apt/sources.list.d/nanoporetech.sources.list
    sudo apt-get update
    sudo apt-get install minknow-nc

At this point, restart the computer. The installation can be tested by
performing a hardware test in MinKNOW with a MinION connected with a
Configuration Test Cell.

Next, download the `read_until_api` project and install it into the MinKNOW
python installation:

    git clone https://github.com/nanoporetech/read_until_api.git
    cd read_until_api/
    sudo /opt/ONT/MinKNOW/ont-python/bin/python setup.py install

To test the Read Until installation, it is possible to run the playback script
in MinKNOW: select the "Custom Script" menu option after starting a new
experiment. After starting playback, from a commandline run:

    sudo /opt/ONT/MinKNOW/ont-python/bin/python <path/to/>read_until_api/read_until/simple.py --verbose

Finally restart the computer.


**Other python libraries**

The following are instructions for installing selected additional python libraries.

To use the more involved examples from the Read Until API, install `scrappy` and
`mappy`:

    sudo /opt/ONT/MinKNOW/ont-python/bin/python -m pip install scrappy mappy


Installing `pytorch` requires using the Python 2.7 UCS2 wheel:

    sudo /opt/ONT/MinKNOW/ont-python/bin/python -m pip install http://download.pytorch.org/whl/cpu/torch-0.4.0-cp27-cp27m-linux_x86_64.whl
    sudo /opt/ONT/MinKNOW/ont-python/bin/python -m pip install torchvision 


Trouble Shooting
================

Upgrading of python packages can interfere with the ont-python installation,
notably if pre-existing packages are updated. To mitigate  this pip can be
instructed to avoid upgrading packages:

    sudo /opt/ONT/MinKNOW/ont-python/bin/python -m pip install --upgrade --upgrade-strategy only-if-needed <package>

If something has gone wrong, reinstallation of MinKNOW might be useful
following the [guide](https://community.nanoporetech.com/support/faq/test1/minknow/troubleshooting-MinKNOW/how-do-i-do-a-full-uninstall-of-minknow?search_term=uninstall)
then manually remove the folder `/opt/ONT` and restart the computer.
