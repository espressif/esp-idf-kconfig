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

Deprecated Options Checking
---------------------------

The ``kconfcheck`` tool also provides a ``check-deprecated-kconfig-options`` pre-commit hook that verifies whether ``sdkconfig.defaults`` or ``sdkconfig.ci`` files reference deprecated Kconfig option names (i.e., names that appear in ``sdkconfig.rename`` files as the left hand side - see :ref:`deprecated-options` for more details).

.. warning::

  Please bear in mind that the checker has its limits and won't be able to catch all deprecated options. The checker will catch options that are deprecated in the ESP-IDF root rename file, any of the built-in component rename files, or in the project's own rename files.

  The checker also skips target-specific rename files (e.g., ``sdkconfig.rename.esp32``) used by the ESP-IDF build system.

To use the hook, add the following to your ``.pre-commit-config.yaml``:

.. code-block:: yaml

    - repo: https://github.com/espressif/esp-idf-kconfig.git
      rev: <version>
      hooks:
        - id: check-deprecated-kconfig-options

The hook can also be run manually:

.. code-block:: console

    python -m kconfcheck --check deprecated [files...]

``sdkconfig.rename`` file scope
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Rename files are classified into **global** and **local** scopes to prevent false positives when independent projects (e.g., examples, test apps) coincidentally use config options of the same name and one project decides to deprecate it.

**Global scope** — rename files at the IDF root or anywhere under ``components/``. These apply when checking any file in the tree.

**Local scope** — rename files located under a *project root*. A directory is considered a project root if it contains a ``CMakeLists.txt`` with a ``project(`` call. Local renames only apply to files within the same project subtree.

When checking a file at path ``P``:

1. The checker walks up from ``P`` to find its nearest project root ancestor (if any).
2. The effective deprecated set is computed as the union of ``global_deprecated`` and ``local_deprecated[project_root]``.
3. If ``P`` is not under any project root, only the global set is used.

.. note::

  The global deprecated set (IDF root and ``components/``) is collected once when the checker
  starts. Per-project local sets are computed on demand: only the first time a file from a
  given project is processed does the checker walk that project's subtree. Projects whose
  files are not being checked are never scanned, so a typical pre-commit run touching only a
  few files remains fast even on large codebases.

This means that a deprecated option defined in ``examples/project_a/sdkconfig.rename`` will not cause failures in ``examples/project_b/sdkconfig.defaults``.

Rename files that have no project root ancestor and are not under ``components/`` or at the IDF root level (e.g., shared example components without a ``project()`` call) are skipped by the pre-commit hook. Their deprecated names are not enforced anywhere.
