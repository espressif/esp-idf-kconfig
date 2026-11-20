.. _kconfiglib-index:

Kconfig Language and Parsers
============================

Kconfig (short for "Kernel CONFIGuration") is a language developed to manage the configuration of a Linux kernel, which first appeared in the 1990s. However, over the years, it started to be used in other projects as well; UBoot, Zephyr RTOS, ESP-IDF, and more. Originally, the Kconfig implementation was written in C, but later, a Python implementation named `kconfiglib <https://github.com/ulfalizer/Kconfiglib>`_ was developed by GitHub user Ulfalizer.

Unfortunately, even though this has been the only Python implementation of the Kconfig language and it has been widely used, it has not been maintained for more than 4 years in July 2024. This was one of the reasons why ``esp-idf-kconfig`` was developed.

The ``esp-idf-kconfig`` package, originated in 2018, includes wider suite of tools, tailored for ESP-IDF, and is actively maintained. The package is designed to be used with the `Espressif IoT Development Framework (ESP-IDF) <https://docs.espressif.com/projects/esp-idf/en/latest/index.html>`_, although it can be used with other projects as well, either as a whole suite or as individual tools.

The package also includes a `Pyparsing <https://github.com/pyparsing/pyparsing>`_-based
Kconfig parser (parser v2). Although it is slower than the original implementation
(parser v1), it is intended to be developer friendly, easy to
read, maintain and expand, which are the areas the previous parser was lacking.
When ``kconfgen`` fails under parser v2, it re-parses with v1.
If v1 also rejects the tree, the original v2 error is kept.
If v1 accepts it, ``kconfgen`` checks the error location for :ref:`unsupported legacy constructs <differences>`.
If one is found, the failure is reported as intended; otherwise it is reported as a possible parser bug.

The parser is selected as follows:

1. The ``KCONFIG_PARSER_VERSION`` environment variable (``1`` or ``2``), if set. This is meant for the user, e.g. to temporarily fall back to parser v1.
2. Otherwise, a ``# kconfig-parser-version: <1|2>`` comment in the root ``Kconfig`` file, if present. This is meant for projects (e.g. ESP-IDF) which want a different default parser. The comment has to be in the leading comment block of the file, i.e. before the first line that is neither empty nor a comment. Only the root ``Kconfig`` file is inspected, files sourced from it are not:

   .. code-block:: kconfig

       # kconfig-parser-version: 2
       mainmenu "My Project Configuration"

3. Otherwise, parser v1 is used.

Empty values are treated as unset. Any other value than ``1`` or ``2`` is ignored with a warning, as if it was unset. Because the comment is an ordinary Kconfig comment, older ``esp-idf-kconfig`` versions ignore it and keep using parser v1.

.. toctree::
    :maxdepth: 2

    Formal Base <formal-base>
    Language Description <language>
    Differences from Kconfiglib <differences>
    Default Values <defaults>
    Deprecated Options <deprecated-options>
    Configuration Report <configuration-report>
