.. _differences:

List of Changes in the Pyparsing Parser
=======================================

Although we tried to keep the ``esp-idf-kconfig`` package as close to the original ``kconfiglib`` as possible, there are some differences between the two. This section describes those differences. For the original definition of the Kconfig language, please refer to the `Kconfig language documentation <https://www.kernel.org/doc/Documentation/kbuild/kconfig-language.txt>`_.

- ``option`` keyword is deprecated and supported only in the form of ``option env=``.
- ``def_<type>`` keywords are not supported.
- ``tristate`` logic (and thus ``m`` value) is not supported.
- ``optional`` keyword for ``choice`` entries is not supported.
- ``choice`` entries are now forced to be a ``bool`` type.
- ``---help---`` keyword is not supported.
- ``config`` or ``choice`` names must contain only numbers, uppercase letters from the English alphabet and underscores.
- Multiple definitions of ``config``/``choice`` entries are now reported to the user.
- The inference of default values has been reworked (see :ref:`defaults`).
- Preprocessor macros are supported only in the form of ``symbol = value`` or ``symbol := value`` and strings need to be enclosed in quotes.
- New parser recognizes default values in ``sdkconfig`` files (see :ref:`defaults`).

Deprecated Constructs
---------------------

.. important::

    Do not use the following constructs in your Kconfig files. They will become errors in a future major release.

The following constructs are still accepted, because the original ``kconfiglib`` accepts them as well, but the parser v2 reports them as deprecated. They will become errors in a future major release.

- Help text that is not indented deeper than the ``help`` keyword. The Kconfig language is indentation based, but the original ``kconfiglib`` does not enforce indentation, which makes the end of a help block ambiguous for the reader. Indent the help text one level deeper than the ``help`` keyword.
- The ``boolean`` type keyword. Use ``bool`` instead.
- A ``config`` defined without an explicit type. Give the symbol a type (``bool``, ``string``, ``int``, ``hex``, or ``float``).
- An unquoted default on a string symbol that is not an all-uppercase name of an existing symbol. Quote the string, e.g. ``default "host.example.com"`` instead of ``default host.example.com``.
- A quoted ``choice`` name, e.g. ``choice "Connection Method"``. Such a name is not a valid identifier. The choice is treated as unnamed. You can either omit the choice identifier completely (preferred) or use an identifier consisting of only numbers, uppercase letters from the English alphabet and underscores.
- A ``config`` or ``choice`` name that contains lowercase letters. Lowercase names are not valid identifiers. Please use an identifier consisting of only numbers, uppercase letters from the English alphabet and underscores.
