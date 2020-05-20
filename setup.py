import sys
from setuptools import setup, find_packages


PKG_NAME = "read_until"
AUTHOR = "Oxford Nanopore Technologies Ltd"

sys.path.insert(0, "./{}".format(PKG_NAME))
from _version import __version__ as VERSION
del sys.path[0]

with open("requirements.txt") as reqs:
    install_requires = [pkg.strip() for pkg in reqs]

setup(
    name=PKG_NAME,
    version=VERSION,
    author=AUTHOR,
    author_email="info@nanoporetech.com",
    description="Read Until API",
    install_requires=install_requires,
    tests_require=["pytest"],
    # don't include any testing subpackages in dist
    packages=find_packages(exclude=["*.test", "*.test.*", "test.*", "test"]),
    zip_safe=False,
    entry_points={
        "console_scripts": [
            "read_until_simple = {}.simple:main".format(PKG_NAME),
            "read_until_ident = {}.identification:main".format(PKG_NAME),
        ]
    },
)
