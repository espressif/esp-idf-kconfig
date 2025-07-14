Configuration Report
====================

.. _configuration_report:

The ``esp-idf-kconfig`` provides an advanced configuration report featuring a complete information about the configuration process of the project.

Verbosity Levels
----------------

Configuration report provides three configuration verbosity levels:

* ``quiet`` - Configuration report is printed only if there are any errors.
* ``default`` - Configuration is printed every time, but without additional information for the user.
* ``verbose`` - Configuration report is printed every time with additional information (error/warning/info statements explanation, link to the documentation etc.).

Verbosity can be set via ``KCONFIG_REPORT_VERBOSITY`` environment variable.

Report Status
-------------

Configuration report also informs the user about overall status of the configuration:

* ``Finished successfully`` - Configuration process was successful.
* ``Finished with notifications`` - Configuration process was successful, but there are some minor notifications.
* ``Finished with warnings`` - Configuration process was successful, but there are some warnings.
* ``Failed`` - Configuration process failed.

.. note::

    The difference between ``Finished with notifications`` and ``Finished with warnings`` is in the probability that the configuration is correct. In the first case, the configuration is most likely correct, although some situations requiring attention were detected. In the second case, there is a higher probability that the configuration is incorrect and/or the problems found need user intervention.

Structure of the Configuration Report
-------------------------------------

Configuration report consists of a header and zero or more report areas.

Header includes general information about the configuration process such as:

* parser version
* verbosity level
* configuration status

Every report area covers a specific type of information/warning/error message. Currently, the following report areas are supported:

Multiple Symbol or Choice Definition
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a config option or choice with the same name is defined multiple times, the configuration report will show a message with the name of the symbol or choice and definition locations.

Multiple definitions of config option or choice of the same name are allowed in Kconfig language, but it may happen that e.g. two config options with the same name are defined unintentionally in different components and used in different context. This situation may result in an unpredictable behavior, which is hard to debug. Because of that, ``esp-idf-kconfig`` notifies the user about such situations.

.. warning::

    Currently, multiple definitions of the same config option or choice is considered only a notification, not a warning. In the following version of ``esp-idf-kconfig``, this may change.

.. note::

    If you intentionally want to define config name or choice with the same name multiple times, you can suppress this notification by ``# ignore: multiple-definition`` comment in the Kconfig file. It is enough to put this comment only in one of the definitions.

    .. code-block:: kconfig

        config STARSHIP_NAME # ignore: multiple-definition
            string "Name your starship"
            default "USS-Enterprise"

        # (...)

        config STARSHIP_NAME # here, the pragma is not needed (but it is allowed)
            string "Name your starship"
            default "Millennium Falcon"

.. _default-value-mismatch-area:

Default Value Mismatch
^^^^^^^^^^^^^^^^^^^^^^

This area contains information about configuration options that have issues with their default values. Specific sub-areas are described below. The titles match those from the report.

For more information about default values, see :ref:`defaults`.

Config Symbols with Different Default Values Between Sdkconfig and Kconfig
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
This occurs when a configuration option's default value changes in the Kconfig file (typically due to a new version of a component or ESP-IDF being released) or when the sdkconfig file is manually modified.

* If the default value is changed in the Kconfig file, please refer to the corresponding component's documentation or release notes to understand the implications of this change.
* If you manually edited the value in sdkconfig, it is recommended to revert the change and set the user value through the menuconfig or other configuration tool.  Directly editing sdkconfig files is generally not recommended.

Promptless Config Symbols with Different Values Between Sdkconfig and Kconfig
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

.. note::

    This area is intended primarily for developers and advanced users and it is printed only in verbose mode. Promptless configuration options are those that do not have a prompt in the Kconfig file. As a result, they do not appear in the menuconfig and are not intended to be set by the user. These options are written to the sdkconfig file only to make them accessible to other tools.

This warning is printed when a promptless configuration option has a value in the sdkconfig file that differs from the default value in Kconfig file. This can happen if the sdkconfig file is manually edited or if the default value changes in the Kconfig file. The config option is also listed if it is marked as user-set in the sdkconfig file.

* If the default value is changed in the Kconfig file, it is probably OK to ignore this warning. However, you can check the component's documentation or release notes to ensure this change does not affect your project.
* If you manually edited the value of a promptless config option in sdkconfig (either changed the value or removed the ``# default:`` comment before the config option), this change will always be ignored and overwritten by the default value from the Kconfig file during the sdkconfig file update. Promptless symbols are not intended to be set by the user (they are only for internal use). It is not possible to externally change the value of promptless symbols.
