Documentation of ``esp-idf-kconfig``
====================================

This is the documentation for the ``esp-idf-kconfig`` project. The ``esp-idf-kconfig`` package is a Python library for working with :ref:`Kconfig <kconfiglib-index>` configuration files. It is designed to be used with the `Espressif IoT Development Framework (ESP-IDF) <https://docs.espressif.com/projects/esp-idf/en/latest/index.html>`_, although it can be used as a standalone package as well. Core kconfiglib and menuconfig functionality has been copied from the original `kconfiglib <https://github.com/ulfalizer/Kconfiglib>`_ repository.

The ``esp-idf-kconfig`` package is used for compile-time project configuration. For the detailed description of the Kconfig language, see the :ref:`Kconfig <kconfiglib-index>` section. Contributions are welcome. Before contributing please make sure that you have read the :ref:`Developer and Contributor Guide <developer-guide>`.

ESP-IDF specific user guide can be found in the `ESP-IDF documentation <https://docs.espressif.com/projects/esp-idf/en/latest/api-guide/kconfig/index.html>`_.

For those who want to visit the original Kconfig language documentation from the Linux kernel, see the `Kconfig language documentation <https://www.kernel.org/doc/Documentation/kbuild/kconfig-language.txt>`_.

Excluding the core functionality, the ``esp-idf-kconfig`` package has been extended with the following features:

- Checking the validity of Kconfig files (kconfcheck)
- Support for configuration via IDEs (kconfserver)
- Advanced Kconfig file manipulation (kconfgen)

Documentation Overview
----------------------

.. toctree::
    :maxdepth: 2

    Kconfig Language <kconfiglib/index>
    Checking Kconfig Files <kconfcheck/index>
    Developer and Contributor Guide <developer-guide/index>
