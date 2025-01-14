.. _kconfiglib-index:

Kconfig Language and Parsers
============================

Kconfig (short for "Kernel CONFIGuration") is a language developed to manage the configuration of a Linux kernel, which first appeared in the 1990s. However, over the years, it started to be used in other projects as well; UBoot, Zephyr RTOS, ESP-IDF, and more. Originally, the Kconfig implementation was written in C, but later, a Python implementation named `kconfiglib <https://github.com/ulfalizer/Kconfiglib>`_ was developed by GitHub user Ulfalizer.

Unfortunately, even though this has been the only Python implementation of the Kconfig language and it has been widely used, it has not been maintained for more than 4 years in July 2024. This was one of the reasons why ``esp-idf-kconfig`` was developed.

The ``esp-idf-kconfig`` package, originated in 2018, includes wider suite of tools, tailored for ESP-IDF, and is actively maintained. The package is designed to be used with the `Espressif IoT Development Framework (ESP-IDF) <https://docs.espressif.com/projects/esp-idf/en/latest/index.html>`_, although it can be used with other projects as well, either as a whole suite or as individual tools.

The package also includes new parser, based on `Pyparsing <https://github.com/pyparsing/pyparsing>`_. Although it is slower than the original implementation, the new parser is intended to be developer friendly and easy to read and maintain. The new parser is under active development and new features are being added.

.. toctree::
    :maxdepth: 2

    Formal Base <formal-base>
    Language Description <language>
    Differences from Kconfiglib <differences>
    Default values <defaults>
