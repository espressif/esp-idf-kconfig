__version__ = '0.1.0'

from .kconfgen import main as _kconfgen_main
from .kconfserver import main as _kconfserver_main

def kconfgen_main():
    _kconfgen_main()

def kconfserver_main():
    _kconfserver_main()
