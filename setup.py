from setuptools import setup, find_packages


PKG_NAME = "read_until"
AUTHOR = "Oxford Nanopore Technologies Ltd"

__version__ = ""
exec(open("{}/_version.py".format(PKG_NAME)).read())

with open("requirements.txt") as reqs:
    install_requires = [pkg.strip() for pkg in reqs]

setup(
    name=PKG_NAME,
    version=__version__,
    author=AUTHOR,
    author_email="info@nanoporetech.com",
    description="Read Until API",
    install_requires=install_requires,
    extra_requires={"guppy": ["ont-pyguppy-client-lib>=4.0.8"],},
    tests_require=[],
    # don't include any testing subpackages in dist
    packages=find_packages(exclude=["*.test", "*.test.*", "test.*", "test"]),
    zip_safe=False,
    entry_points={
        "console_scripts": [
            "read_until_simple = read_until.simple:main",
            "read_until_ident = read_until.identification:main [guppy]",
        ]
    },
)
