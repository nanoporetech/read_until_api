import io
import os
import re
import tempfile
import zipfile

from distutils.cmd import Command
from setuptools import setup, find_packages
from setuptools.command.install import install
from setuptools.command.develop import develop
import pkg_resources


__pkg_name__ = "read_until"
__author__ = "cwright"
__description__ = "Read Until API"


__path__ = os.path.dirname(__file__)
__pkg_path__ = os.path.join(os.path.join(__path__, __pkg_name__))

# Get the version number from __init__.py
verstrline = open(os.path.join(__pkg_name__, "__init__.py"), "r").read()
vsre = r"^__version__ = ['\"]([^'\"]*)['\"]"
mo = re.search(vsre, verstrline, re.M)
if mo:
    __version__ = mo.group(1)
else:
    raise RuntimeError(
        'Unable to find version string in "{}/__init__.py".'.format(__pkg_name__)
    )


# Get requirements from file, we prefer to have
#   preinstalled these with pip to make use of wheels.
dir_path = os.path.dirname(__file__)
install_requires = []
with open(os.path.join(dir_path, "requirements.txt")) as fh:
    reqs = (
        r.split("#")[0].strip() for r in fh.read().splitlines() if not r.startswith("#")
    )
    for req in reqs:
        if req == "":
            continue
        if req.startswith("git+https"):
            req = req.split("/")[-1].split("@")[0]
        install_requires.append(req)

extra_requires = {"identification": ["scrappy", "mappy"]}
extensions = []


def generate_protos(base_out_dir):
    # Late import to ensure dependencies are installed when this runs.
    # pylint: disable=import-outside-toplevel
    from grpc.tools import protoc
    import requests

    proto_source = "https://github.com/nanoporetech/minknow_api/archive/master.zip"

    with tempfile.TemporaryDirectory() as tmpdirname:
        request = requests.get(proto_source)
        if not request.ok:
            raise Exception(
                "Failed to download protobuf sources from '%s'" % proto_source
            )
        zipped_content = zipfile.ZipFile(io.BytesIO(request.content))
        zipped_content.extractall(path=tmpdirname)

        proto_root = os.path.join(tmpdirname, os.listdir(tmpdirname)[0])
        print("Downloaded minknow api to '%s'" % proto_root)

        output_dir = os.path.join(base_out_dir, "read_until", "generated")
        try:
            os.makedirs(output_dir)
        except FileExistsError:
            pass
        files_to_generate = os.path.join(proto_root, "minknow", "rpc")
        assert os.path.isdir(files_to_generate)
        print(
            "Generating protobuf python for directory: '%s' into '%s': %s"
            % (files_to_generate, output_dir, os.listdir(files_to_generate))
        )

        files = [
            os.path.join(files_to_generate, f) for f in os.listdir(files_to_generate)
        ]

        proto_include = pkg_resources.resource_filename("grpc_tools", "_proto")
        command = [
            "grpc_tools.protoc",
            "-I%s" % proto_root,
            "-I%s" % proto_include,
            "--python_out=%s" % output_dir,
            "--grpc_python_out=%s" % output_dir,
            *files,
        ]
        if protoc.main(command) != 0:
            raise Exception("protoc error: {} failed".format(command))


class ProtoBuildCommand(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        base_dir = os.path.abspath(os.path.dirname(__file__))
        generate_protos(base_dir)


class DevelopCommand(develop):
    def run(self):
        develop.run(self)
        base_dir = os.path.abspath(os.path.dirname(__file__))
        generate_protos(base_dir)


class InstallCommand(install):
    def run(self):
        install.run(self)
        generate_protos(self.install_lib)


setup(
    name=__pkg_name__,
    version=__version__,
    url="https://github.com/nanoporetech/{}".format(__pkg_name__),
    author=__author__,
    author_email="{}@nanoporetech.com".format(__author__),
    description=__description__,
    python_requires=">=3.5",
    dependency_links=[],
    ext_modules=extensions,
    install_requires=install_requires,
    tests_require=[].extend(install_requires),
    extras_require=extra_requires,
    # don't include any testing subpackages in dist
    packages=find_packages(exclude=["*.test", "*.test.*", "test.*", "test"]),
    package_data={},
    zip_safe=False,
    entry_points={
        "console_scripts": [
            "read_until_simple = {}.examples.simple:main".format(__pkg_name__),
            "read_until_ident = {}.examples.identification:main".format(__pkg_name__),
        ],
    },
    cmdclass={
        "build_proto": ProtoBuildCommand,
        "install": InstallCommand,
        "develop": DevelopCommand,
    },
)
