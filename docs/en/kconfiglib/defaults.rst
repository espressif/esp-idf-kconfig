.. _defaults:

Default Values and Their Inference
==================================

In original ``kconfiglib``, when the configuration was written out to e.g. ``sdkconfig`` file, all the values were considered user-set, no matter if the user actually set them (even indirectly via e.g. ``sdkconfig.defaults``). This behavior resulted in rather confusing situations; when e.g. conditional default values were not updated if the condition was changed.

.. note::

    This note is intended primarily for component maintainers.

    The information below applies only to configuration options that have a prompt. Promptless config options have different value inference. When loading ``sdkconfig[.defaults]`` files, the values for promptless config options are **always ignored** (their value is always set to the **Kconfig default value**). These config options are also hidden in configuration tools, such as ``menuconfig``, and cannot be changed by the user.

Consider following example:

.. code-block:: kconfig

    # Kconfig file

    config A
        bool "Option A"
        default y

    config B
        int "Option B"
        depends on A
        default 42 if A
        default 0 if !A


.. code-block:: kconfig

    # sdkconfig file
    # Let's suppose both values were not set by the user, but rather automatically inferred
    CONFIG_A=y
    CONFIG_B=42


If user would run ``menuconfig`` tool and change the value of ``CONFIG_A`` to "n", the ``CONFIG_B`` would still be set to 42, even though it should be 0. This is because the value of ``CONFIG_B`` was considered user-set, even though it was not. In order to fix this behavior, the inference of default values was reworked in ``esp-idf-kconfig``. During writeout of the ``sdkconfig`` file, configuration system now distinguishes between user-set and inferred (default) values. Default values have a ``# default:`` comment/pragma preceding given line:

.. code-block:: kconfig

    # sdkconfig file. Explicitly stated that both values are default.
    # default:
    CONFIG_A=y
    # default:
    CONFIG_B=42

The configuration system now determines the value for given config option as follows. Difference from original approach used in ``esp-idf-kconfig<3`` are marked with (new), list is ordered by priority (from highest to lowest):

1. Value set by the user in current run of ``menuconfig`` tool.
2. User-set value from ``sdkconfig`` file.
3. Value from ``sdkconfig.defaults`` file. These values are also considered user-set.
4. (new) Default value from ``sdkconfig`` file.
5. Default value from the Kconfig file.

.. note::

    The ``sdkconfig.defaults``, despite its name, contains **user-set** values. The word "defaults" in the file name does not refer to default values as configuration system understands them, but rather default values (overrides) for given project.

Differing Default Values Between ``sdkconfig`` and ``Kconfig`` Files
--------------------------------------------------------------------

When e.g. updating components or ESP-IDF itself, it may happen that the default value for given configuration option will differ between ``sdkconfig`` and ``Kconfig``:

.. code-block:: kconfig

    # Kconfig file

    config C
        int "Option A"
        default 100 # in the previous version of the Kconfig file, it was 42


.. code-block:: kconfig

    # sdkconfig file
    # CONFIG_C still have default value from previous version of Kconfig file
    # default:
    CONFIG_C=42

In this case, configuration system notifies the user that ``sdkconfig`` and ``Kconfig`` default values are different. Default behavior is to use the value from ``sdkconfig`` file, in order to maintain backward compatibility. Configuration system also supports to choose a default value source via the ``KCONFIG_DEFAULTS_POLICY`` environment variable. The following values are supported:

* ``sdkconfig`` - use the value from ``sdkconfig`` file (default).
* ``kconfig`` - use the value from Kconfig file.
* ``interactive`` - ask the user to choose the source of the default value.

For more information about reporting of default value mismatches, see :ref:`default-value-mismatch-area`.
