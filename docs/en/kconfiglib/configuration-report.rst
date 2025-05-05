Configuration Report
====================

.. _configuration_report:

The ``esp-idf-kconfig`` provides an advanced configuration report featuring a complete information about the configuration process of the project.

Verbosity Levels
^^^^^^^^^^^^^^^^

Configuration report provides three configuration verbosity levels:

* ``quiet`` - Configuration report is printed only if there are any errors.
* ``default`` - Configuration is printed every time, but without additional information for the user.
* ``verbose`` - Configuration report is printed every time with additional information (error/warning/info statements explanation, link to the documentation etc.).

Verbosity can be set via ``KCONFIG_REPORT_VERBOSITY`` environment variable.

Report Status
^^^^^^^^^^^^^

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
