import os.path
import sys

from setuptools import find_packages, setup


def read(rel_path):
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, rel_path), "r") as fp:
        return fp.read()


def get_version(rel_path):
    for line in read(rel_path).splitlines():
        if line.startswith("__version__"):
            delim = '"' if '"' in line else "'"
            return line.split(delim)[1]
    else:
        raise RuntimeError("Unable to find version string.")


def get_long_description():
    with open("README.md", "r") as f:
        text = f.read()
    return text


_install_requires = ["kconfiglib>=13.7.1"]

if sys.platform == "win32":
    _install_requires.append("windows-curses")

setup(
    name="esp-idf-kconfig",
    version=get_version("esp_idf_kconfig/__init__.py"),
    author="Espressif Systems",
    author_email="",
    description="Kconfig tooling for esp-idf",
    long_description_content_type="text/markdown",
    long_description=get_long_description(),
    url="https://github.com/espressif/esp-idf-kconfig",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=_install_requires,
    extras_require={
        "dev": [
            "flake8>=3.2.0",
            "flake8-import-order",
            "black",
            "pre-commit",
            "pexpect",
        ],
    },
    keywords=["espressif", "embedded", "project", "configuration", "kconfig"],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Environment :: Console",
        "Topic :: Software Development :: Embedded Systems",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: POSIX",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS :: MacOS X",
    ],
)
