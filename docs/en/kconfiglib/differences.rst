.. _differences:

List of Changes in the pyparsing parser
=======================================

Although we tried to keep the ``esp-idf-kconfig`` package as close to the original ``kconfiglib`` as possible, there are some differences between the two. This section describes those differences. For the original definition of the Kconfig language, please refer to the `Kconfig language documentation <https://www.kernel.org/doc/Documentation/kbuild/kconfig-language.txt>`_.

- ``option`` keyword is deprecated and supported only in the form of ``option env=``.
- ``def_<type>`` keywords are not supported.
- ``tristate`` logic (and thus ``m`` value) is not supported.
- ``optional`` keyword for ``choice`` entries is not supported.
- Explicit prompts for ``menu`` entries are not supported.
- ``choice`` entries are now forced to be a ``bool`` type.
- ``---help---`` keyword is not supported.
- ``config`` or ``choice`` names must contain only numbers, uppercase letters from the English alphabet and underscores.
- Multiple definitions of ``config``/``choice`` entries are now reported to the user.
- The inference of default values has been reworked (see :ref:`defaults`).
