.. _differences:

List of Changes in the Pyparsing Parser
=======================================

``esp-idf-kconfig`` ships two Kconfig parsers: parser v1 (the original, ``kconfiglib``-derived parser) and parser v2 (the default parser, based on ``pyparsing``). Although we tried to keep parser v2 as close to parser v1 as possible, there are some differences between the two. This section describes those differences. For the original definition of the Kconfig language, please refer to the `Kconfig language documentation <https://www.kernel.org/doc/Documentation/kbuild/kconfig-language.txt>`_.

- ``def_<type>`` keywords are not supported.
- ``tristate`` logic (and thus ``m`` value) is not supported.
- ``choice`` entries are now forced to be a ``bool`` type.
- ``config`` or ``choice`` names must contain only numbers, uppercase letters from the English alphabet and underscores.

When parser v2 fails and parser v1 accepts the same tree, ``kconfgen`` checks the error location (the reported line and the adjacent lines) for the unsupported constructs above.
If one is found, the failure is reported as intended: please fix the Kconfig.
If none is found, the failure is reported as a possible parser bug.
If both parsers reject the tree, the original v2 error is kept.
``KCONFIG_PARSER_VERSION=1`` is a temporary workaround only when parser v1 still accepts the tree.

Deprecated Constructs
---------------------

.. important::

    Do not use the following constructs in your Kconfig files. They will become errors in a future major release.
    See the :ref:`Migration Guide <migration-guide>` for how to replace each of them.

The following constructs are still accepted, because the original ``kconfiglib`` accepts them as well, but the parser v2 reports them as deprecated. They will become errors in a future major release.

- Help text that is not indented deeper than the ``help`` keyword. The Kconfig language is indentation based, but the original ``kconfiglib`` does not enforce indentation, which makes the end of a help block ambiguous for the reader. Indent the help text one level deeper than the ``help`` keyword.
- The ``boolean`` type keyword. Use ``bool`` instead.
- A ``config`` defined without an explicit type. Give the symbol a type (``bool``, ``string``, ``int``, ``hex``, or ``float``).
- An unquoted default on a string symbol that is not an all-uppercase name of an existing symbol. Quote the string, e.g. ``default "host.example.com"`` instead of ``default host.example.com``.
- A quoted ``choice`` name, e.g. ``choice "Connection Method"``. Such a name is not a valid identifier. The choice is treated as unnamed. You can either omit the choice identifier completely (preferred) or use an identifier consisting of only numbers, uppercase letters from the English alphabet and underscores.
- A ``config`` or ``choice`` name that contains lowercase letters. Lowercase names are not valid identifiers. Please use an identifier consisting of only numbers, uppercase letters from the English alphabet and underscores.
- The ``---help---``/``--help--`` keyword (any number of dashes on either side of ``help``). Use the plain ``help`` keyword instead.
- The ``optional`` keyword on a ``choice``. It has no effect. Remove it.
- The ``option`` keyword in the form of ``option modules``, ``option defconfig_list`` or ``option allnoconfig_y``. Use ``option env=`` for the only form recommended going forward, or see the :ref:`Migration Guide <migration-guide>` for the others.
