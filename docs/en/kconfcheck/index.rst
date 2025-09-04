.. _kconfcheck:

Kconfig Files Checking
======================

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

Format rules for ``source`` statements are as follows:

- Environment variables can specify path to the sourced file, but not its name; file name must be specified explicitly.
- The sourced file must be named as ``Kconfig.<suffix>``. Suffix is up to the user to define, but must be present.

How to Use the ``kconfcheck`` Tool
----------------------------------

The ``esp-idf-kconfig`` package provides a pre-commit hook named ``check-kconfig-files`` that can be used to automatically check Kconfig files before committing changes. This ensures that all Kconfig files in your repository comply with the format rules and helps maintain consistency across the project. It is also the most convenient way to use the checker.

To use the ``check-kconfig-files`` pre-commit hook, add the following configuration to your repository's ``.pre-commit-config.yaml`` file:

.. code-block:: yaml

    - repo: https://github.com/espressif/esp-idf-kconfig.git
      rev: <version>
      hooks:
        - id: check-kconfig-files

Check the version of the ``esp-idf-kconfig`` package you are using and replace `<version>` with the appropriate version (e.g. ``3.0.0``). It is recommended to use the latest stable version of the package.

For more information about pre-commit hooks and how to set them up, refer to the official pre-commit documentation: https://pre-commit.com/.

As an alternative, you can also run the checker manually without using pre-commit hooks. This is useful for one-off checks or if you cannot use pre-commit hooks in your workflow.

To run the checker manually, use the following command:

.. code-block:: console

    python -m kconfcheck <path_to_kconfig_file>
