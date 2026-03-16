.. _deprecated-options:

Deprecated Options
==================

When configuration option names change across versions of a project, the old names become *deprecated*. The ``esp-idf-kconfig`` configuration system provides a mechanism for maintaining backward compatibility with deprecated option names, so that existing configuration files continue to work after a rename.

This mechanism is driven by **rename files** — simple text files that declare mappings from old (deprecated) option names to their new replacements.

Rename File Format
------------------

Rename files (conventionally named ``sdkconfig.rename``) contain one mapping per line:

.. code-block:: text

    CONFIG_OLD_OPTION_NAME    CONFIG_NEW_OPTION_NAME

Each line declares that ``CONFIG_OLD_OPTION_NAME`` is deprecated and has been replaced by ``CONFIG_NEW_OPTION_NAME``. Lines starting with ``#`` are comments. Blank lines are ignored.

Boolean Inversion
^^^^^^^^^^^^^^^^^

If the semantics of an option were inverted during the rename (e.g. an "enable" option became a "disable" option), prefix the new name with ``!``:

.. code-block:: text

    CONFIG_FEATURE_ENABLE    !CONFIG_FEATURE_DISABLE

When an inverted mapping is applied:

- A deprecated value of ``y`` is resolved to ``n`` on the new symbol, and vice versa.
- An unset deprecated option (``# CONFIG_FEATURE_ENABLE is not set``) is resolved to ``y`` on the new symbol.

Loading Rename Files
--------------------

Rename files are loaded via :py:meth:`Kconfig.load_rename_files`:

.. code-block:: python

    config = Kconfig("Kconfig")
    config.load_rename_files(["path/to/sdkconfig.rename"])

This must be called **before** :py:meth:`Kconfig.load_config` for deprecated option resolution to take effect during configuration loading. Once loaded, the mappings are stored internally and used automatically by the loading and writing methods described below.

The ``deprecated_options`` property on the ``Kconfig`` instance exposes the underlying ``DeprecatedOptions`` object (or ``None`` if no rename files have been loaded). This can be used by external tools that need direct access to the mappings.

Loading Configuration with Deprecated Names
--------------------------------------------

When :py:meth:`Kconfig.load_config` encounters a configuration assignment whose name is not defined in the Kconfig tree, it checks whether the name has a deprecated mapping. If so:

1. The deprecated name is resolved to the new (replacement) symbol.
2. The value is applied to the new symbol. For inverted boolean mappings, the value is flipped.
3. An informational message is printed to stderr, e.g.::

       sdkconfig:15 CONFIG_OLD_FEATURE_ENABLE was replaced with CONFIG_FEATURE_ENABLE

4. The deprecated name does **not** appear in ``Kconfig.missing_syms``.

If no mapping exists, the name is treated as a genuinely unknown symbol and is added to ``missing_syms`` as usual.

This resolution works for both assignment lines (``CONFIG_OLD=value``) and unset lines (``# CONFIG_OLD is not set``).

The Deprecated Block in Configuration Output
---------------------------------------------

The configuration output (e.g. ``sdkconfig``) can optionally include a **deprecated compatibility block** — a section at the end of the file that contains assignments using the old (deprecated) names. This block is delimited by marker comments:

.. code-block:: text

    # Deprecated options for backward compatibility
    CONFIG_OLD_FEATURE_ENABLE=y
    CONFIG_OLD_SPEED=200
    # End of deprecated options

The purpose of this block is to allow tools that read the configuration file (such as linker script generators, CMake includes, or user scripts) to continue working with the old names without modification.

Loading and Skipping the Deprecated Block
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a configuration file that contains a deprecated block is loaded, the block is handled by the ``load_deprecated`` parameter of :py:meth:`Kconfig.load_config`:

- ``load_deprecated=False`` (default): The entire block is **skipped**. Lines inside the block markers are not processed and do not appear in ``missing_syms``. This is the appropriate mode for tools like ``menuconfig`` that should not be affected by the deprecated block.
- ``load_deprecated=True``: Lines in the block are loaded as synthetic symbols. These symbols are added to ``Kconfig.syms`` but are **not** part of the menu tree — they cannot be seen or changed in ``menuconfig``. Their primary use is for **expression evaluation**: tools that evaluate Kconfig expressions (e.g. ``config.eval_string("OLD_OPTION=y")``) can reference deprecated names and get correct results.

Writing Deprecated Blocks
^^^^^^^^^^^^^^^^^^^^^^^^^

The ``write_deprecated`` parameter controls whether the deprecated block is included in the output:

- :py:meth:`Kconfig.write_config(filename, write_deprecated=True) <Kconfig.write_config>` — appends the deprecated block to the ``sdkconfig`` output.
- :py:meth:`Kconfig.write_autoconf(filename, write_deprecated=True) <Kconfig.write_autoconf>` — appends ``#define`` aliases for deprecated names to the C header output (e.g. ``#define CONFIG_OLD_NAME CONFIG_NEW_NAME``).

Both default to ``write_deprecated=False``, so deprecated blocks are only written when explicitly requested.

The deprecated block in the C header output looks like:

.. code-block:: c

    /* List of deprecated options */
    #define CONFIG_OLD_FEATURE_ENABLE CONFIG_FEATURE_ENABLE
    #define CONFIG_OLD_SPEED CONFIG_FEATURE_SPEED

For inverted boolean mappings, the ``#define`` uses a ``!`` prefix: ``#define CONFIG_OLD_ENABLE !CONFIG_NEW_DISABLE``.

Incremental Rebuild Support
----------------------------

:py:meth:`Kconfig.sync_deps` creates dependency tracking files (e.g. ``feature/enable.cdep`` for ``FEATURE_ENABLE``) that build systems use to determine which source files need recompilation when a configuration value changes.

When rename files are loaded, ``sync_deps`` also creates dependency files for deprecated aliases. For example, if ``OLD_FEATURE_ENABLE`` maps to ``FEATURE_ENABLE``, both ``feature/enable.cdep`` and ``old/feature/enable.cdep`` are touched when the value changes. This ensures that source files referencing the old name via ``#ifdef CONFIG_OLD_FEATURE_ENABLE`` are correctly rebuilt.

Summary
-------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Operation
     - Behavior
   * - ``load_rename_files(paths)``
     - Parses rename files and enables deprecated option handling.
   * - ``load_config()`` (default)
     - Resolves deprecated names to new symbols. Skips the deprecated block.
   * - ``load_config(load_deprecated=True)``
     - Additionally loads the deprecated block as synthetic symbols for expression evaluation.
   * - ``write_config(write_deprecated=True)``
     - Appends a deprecated compatibility block with old-name assignments.
   * - ``write_autoconf(write_deprecated=True)``
     - Appends ``#define`` aliases mapping old names to new names.
   * - ``sync_deps()``
     - Touches ``.cdep`` files for both new and deprecated names.
