Installation steps for Minknow + read_until_api + third party Python package (pytorch) for Linux
--------------------

*Installing minknow on Ubuntu 16 as explained in the [official guide](https://community.nanoporetech.com/protocols/experiment-companion-minknow/v/mke_1013_v1_revaj_11apr2016/installing-minknow-on-linu):*

`sudo apt-get update`

`wget -O- https://mirror.oxfordnanoportal.com/apt/ont-repo.pub | sudo apt-key add -`

`echo "deb http://mirror.oxfordnanoportal.com/apt xenial-stable non-free" | sudo tee /etc/apt/sources.list.d/nanoporetech.sources.list`

`sudo apt-get update`

`sudo apt-get install minknow-nc`

***Restart the computer***

*Optional - In order to check the installation perform a hardware test in MinKNOW with the minion device connected while the configuration flowcell is inserted to make sure the installation*

*Clone read_until_api and install it*

`git clone https://github.com/nanoporetech/read_until_api.git`

`cd read_until_api/`

`sudo /opt/ONT/MinKNOW/ont-python/bin/python setup.py install`

*Optional - Test that read until works by running the playback script (there is a "costume script" menu when selecting "new experiment" in MinKNOW). Keep in mind that it requires a fast5 Bulk file*

*Optional - Another test for read until is to run the "simple" example (need to be run during a running experiment, for example during the playback).You can run it with the command:*

`/opt/ONT/MinKNOW/ont-python/bin/python PATH/TO/read_until_api/read_until/simple.py --verbose`

*Installing torch (specifically with cuda91 and built for python 2.7 UCS2, because thats the python MinKNOW uses)*

`sudo /opt/ONT/MinKNOW/ont-python/bin/python -m pip install http://download.pytorch.org/whl/cu91/torch-0.4.0-cp27-cp27m-linux_x86_64.whl`

*Installing torchvision*

`sudo /opt/ONT/MinKNOW/ont-python/bin/python -m pip install torchvision`

***Restart the computer***

*Test that everything works by inserting:*

```python
import torch
import torchvision
```

*To the PATH/TO/read_until_api/read_until/simple.py imports at the beginning of the file*

*Finally, run an experiment (preferably with the playback script), during the experiment run the "simple" script*

`/opt/ONT/MinKNOW/ont-python/bin/python PATH/TO/read_until_api/read_until/simple.py --verbose`

*If everything runs without errors, you can use the newly installed packages with read_until_api*

*If there are errors with a different python package, one can try to install the package by only installing/updating required dependencies with the command:*

`sudo -H /opt/ONT/MinKNOW/ont-python/bin/python -m pip install --upgrade --upgrade-strategy only-if-needed YourPackage`

*In addition, it will install the package in your current location which might help with troubleshooting*

*Before trying to reinstall the packages, one must follow the [official guide to uninstall MinKNOW](https://community.nanoporetech.com/support/faq/test1/minknow/troubleshooting-MinKNOW/how-do-i-do-a-full-uninstall-of-minknow?search_term=uninstall) then manually remove the folder `/opt/ONT` and restart the computer.*


*- ArtemD*
