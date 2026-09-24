Migration Guide From esp-idf-kconfig v2.x to v3.x
=================================================

.. _migration-guide:

This guide describes changes made between esp-idf-kconfig v2 and v3 and, if possible, also provides a guide on how to migrate your code to the new version.

Changes Overview
----------------

- `Missing tristate type/m Value`_
- `The def_<type> Options Are Not Supported`_
- `config or choice Names Must Contain Only Numbers, Uppercase Letters, and Underscores`_
- `Deprecated Constructs`_

.. _missing-tristate:

Missing ``tristate`` type/``m`` Value
--------------------------------------

The ``tristate`` type and its ``m`` value were removed as they were found to be out of scope for general project configuration. There is no direct replacement for it, but depending on your use case, you can mimic this behavior (see below). If you used the ``tristate`` type without using the ``m`` value, you can simply replace it with the ``bool`` type. If you used the ``m`` value, continue reading for alternatives.

``tristate`` as a Simple "Three Value Type"
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you used the ``tristate`` simply to represent a three-value type, you can replace it with the ``int`` type and use, for example, the following value mapping:

- ``n`` (disabled) -> 0
- ``m`` (module) -> 1
- ``y`` (enabled) -> 2

.. code-block:: kconfig

    config TRISTATE_OPTION
        tristate "Option with old tristate syntax"
        default m

    config INT_OPTION
        int "My option with new int syntax"
        range 0 2
        default 2 # equivalent to "y"

Full ``tristate`` Logic Support
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

First of all, it is necessary to define what exactly the ``tristate`` value was used for and how it worked. The ``tristate``'s third value, ``m``, was used to represent that the config option should be enabled if a special ``MODULES`` config option is enabled. This means the config option with the ``m`` value was evaluated as ``y`` if the special config option ``MODULES`` was also evaluated as ``y``.

.. note::

    The purpose of the ``tristate`` type was to easily toggle the configuration when building the Linux kernel with and without kernel modules. This is the reason why the special config is named ``MODULES``. On top of that, the original use case was very specific, which led to the decision to remove the ``tristate`` type altogether.

You can manually mimic the same behavior as closely as possible by using the following syntax:

.. code-block:: kconfig

    config MODULES # Or any other name you prefer (advised to change!)
        bool "Make third state of tristate option enabled"
        default n
        help
            If enabled, the third value of the "tristate" option will be evaluated as "y".
            However, it is recommended to use another name for this option as the original
            name MODULES may clash with an existing MODULES option.

    # config TRISTATE_OPTION
    #    tristate "Option with old tristate syntax"
    #    default m
    #    help
    #        This option no longer works

    config NEW_TRISTATE_OPTION
        int "New tristate option"
        range 0 2
        default 1

    config OTHER_OPTION
        string "Other option"
        # the old option does not work anymore
        # default "enabled" if TRISTATE_OPTION
        # Write the condition explicitly
        default "enabled" if NEW_TRISTATE_OPTION == 2 || (NEW_TRISTATE_OPTION == 1 && MODULES)

.. _missing-def-type:

The ``def_<type>`` Options Are Not Supported
---------------------------------------------

The ``def_<type>`` options were removed as they were not used in the ESP-IDF ecosystem. However, they were just a shorthand for defining a config type plus default value on one line. If you used them in your Kconfig files, you can replace them with the explicit syntax:

.. code-block:: kconfig

    config MY_OPTION
        def_bool y

    # should be replaced with:

    config MY_OPTION
        bool
        default y

.. _only-uppercase-names:

``config`` or ``choice`` Names Must Contain Only Numbers, Uppercase Letters, and Underscores
---------------------------------------------------------------------------------------------

This restriction has been enforced by our ``kconfcheck`` tool (see :ref:`kconfcheck`) for some time now. With the new release, this rule becomes mandatory to clearly define how config options should be named. To comply with the new restriction, use only uppercase letters, numbers, and underscores in config option names.

.. tip::

    Renaming a config option can cause compatibility issues. To avoid them, you can use the ``sdkconfig.rename`` file. This file contains pairs of old and new config names, with each pair on a separate line in the format ``CONFIG_old_name CONFIG_NEW_NAME``. The old name is then written to the ``sdkconfig`` file to preserve backward compatibility.

For more information, refer to the `sdkconfig.rename <https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-guides/kconfig/configuration_structure.html#sdkconfig-rename-and-sdkconfig-rename-chip>`__ description in the ESP-IDF documentation.

.. code-block:: text

    # sdkconfig.rename file
    # both names will be written to the sdkconfig file with the value of the new config option
    CONFIG_old_lowercase CONFIG_NEW_UPPERCASE


.. code-block:: text

    # content of sdkconfig file

    # ...
    CONFIG_NEW_UPPERCASE=y
    # ...

    # Deprecated options for backward compatibility

    # ...
    CONFIG_old_lowercase=y # The value is the same between the new and old config options
    # ...

    # End of deprecated options

.. _deprecated-constructs:

Deprecated Constructs
----------------------

The constructs below are accepted with a deprecation note printed to ``stderr``. They will become errors in a future major release.

The ``---help---`` / ``--help--`` Keyword
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Replace it with the plain ``help`` keyword indented one level deeper than its ``config``/``choice`` keyword:

.. code-block:: kconfig

    config MY_OPTION
        bool "My option with the old help syntax"
        ---help---
            This is my option.

    # should be replaced with:

    config MY_OPTION
        bool "My option with the new help syntax"
        help
            This is my option.

The ``optional`` Keyword for Choice Entries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``optional`` is a noop for some time. A ``choice`` cannot be left without a selection. Remove the
keyword; no replacement is needed. If you want to make a choice that can have no selection, use the following syntax with an additional "enable" symbol:

.. code-block:: kconfig

    config ENABLE_CHOICE
        bool "Enable choice"
        help
            This choice can be left without a selection.

    choice CHOICE_NAME
        prompt "Choose an option"
        depends on ENABLE_CHOICE

        config OPTION_A
            bool "Option A"

        config OPTION_B
            bool "Option B"

    endchoice

The ``option`` Keyword
^^^^^^^^^^^^^^^^^^^^^^


The ``option`` keyword is now deprecated except for ``option env=``. Other sub-keywords are effectively a noop; ``modules`` lost its meaning with the removal of the tristate type, and ``defconfig_list`` and ``allnoconfig_y`` do not have a meaning in the ESP-IDF context. Remove them from your Kconfig files.

.. _only-simple-preprocessor-macros:

Preprocessor Macros
^^^^^^^^^^^^^^^^^^^^

Simple ``symbol = value`` / ``symbol := value`` macros will remain working.

The following extended forms are deprecated **without replacement**:

- The ``+=`` assignment operator.
- A bare macro call on its own line, used only for its side effect (e.g. ``$(info,hello)``).
- A macro value that calls a preprocessor function (e.g. ``FOO := $(shell,echo hi)``) rather than being a simple literal or ``$(ENV_VAR)`` reference.
