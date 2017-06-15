import os
import sys
import shutil
import re
import shutil
import platform
from glob import glob
from setuptools import setup, find_packages, Extension
from setuptools import Distribution, Command
from setuptools.command.install import install
import pkg_resources


#TODO: fill in these
__pkg_name__ = ''
__author__ = ''
__description__ = ''


__path__ = os.path.dirname(__file__)
__pkg_path__ = os.path.join(os.path.join(__path__, __pkg_name__))

# Get the version number from __init__.py
verstrline = open(os.path.join(__pkg_name__, '__init__.py'), 'r').read()
vsre = r"^__version__ = ['\"]([^'\"]*)['\"]"
mo = re.search(vsre, verstrline, re.M)
if mo:
    __version__ = mo.group(1)
else:
    raise RuntimeError('Unable to find version string in "{}/__init__.py".'.format(__pkg_name__))


# Get requirements from file, we prefer to have
#   preinstalled these with pip to make use of wheels.
dir_path = os.path.dirname(__file__)
install_requires = []
with open(os.path.join(dir_path, 'requirements.txt')) as fh:
    reqs = (
        r.split('#')[0].strip()
        for r in fh.read().splitlines() if not r.strip().startswith('#')
    )
    # Allow specifying git repos
    for req in reqs:
        if req.startswith('git+https'):
            req.split('/')[-1].split('@')[0]
    install_requires.append(req)


extra_requires = {
    #TODO: any optional requirements
}



extensions = []
#TODO: compile any extensions
#extensions.append(Extension(
#    'name',
#    sources=[]
#    include_dirs=[],
#    extra_compile_args=['-pedantic', '-Wall', '-std=c99', '-march=native', '-ffast-math', '-DUSE_SSE2', '-DNDEBUG'],
#    libraries=[] #e.g. 'blas'
#))


setup(
    name=__pkg_name__,
    version=__version__,
    url='https://github.com/nanoporetech/{}'.format(__pkg_name__),
    author=__author__,
    author_email='{}@nanoporetech.com'.format(__author__),
    description=__description__,
    dependency_links=[],
    ext_modules=extensions,
    install_requires=install_requires,
    tests_require=[].extend(install_requires),
    extras_require=extra_requires,
    # don't include any testing subpackages in dist
    packages=find_packages(exclude=['*.test', '*.test.*', 'test.*', 'test']),
    package_data={},
    zip_safe=False,
    data_files=[
        #TODO: Probably won't have these, use package_data in most cases 
    ],
    entry_points={
        'console_scripts': [
            #TODO: add entry points
            #'name' = {}.package.module:function'.format(__pkg_name__)
        ]
    },
    scripts=[
        #TODO: Probably won't have these, use entry_points
    ]
)
