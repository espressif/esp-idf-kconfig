Kconfig Files Checking
======================

.. _kconfcheck:

The ``kconfcheck`` tool checks whether given Kconfig files comply with the format rules described below. The checker checks all ``Kconfig[.projbuild]`` files given as arguments, and generates a new file with suffix ``.new`` with suggestions about how to fix issues (if there are any).

Please note that the checker cannot correct all format issues and the responsibility of the developer is to final check and make corrections in order to fix the issues. For example, indentations will be corrected if there is not any misleading formatting, but it cannot find problems as, e.g., ``depends on N`` (config named ``N``) instead of ``depends on n`` (always false).

The ``esp-idf-kconfig`` package is available in ESP-IDF environments, where the checker tool can be invoked by running command ``python -m kconfcheck <path_to_kconfig_file>``.

Kconfig Format Rules
--------------------

Format rules for Kconfig files are as follows:

- Option names in any menus should have consistent prefixes. The prefix currently should have at least 3 characters.
- The unit of indentation should be 4 spaces. All sub-items belonging to a parent item are indented by one level deeper. For example, ``menu`` is indented by 0 spaces, ``config``  ``menu`` by 4 spaces, ``help`` in ``config`` by 8 spaces, and the text under ``help`` by 12 spaces.
- No trailing spaces are allowed at the end of the lines.
- The maximum length of options is 50 characters.
- The maximum length of lines is 120 characters.
- The name of a config option must be uppercase.
