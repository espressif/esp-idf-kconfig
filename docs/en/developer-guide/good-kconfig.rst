.. _good-kconfig:

Guidelines for Writing Good Kconfig Files
=========================================

Kconfig is very powerful configuration language, but some constructs allowed by syntax may lead to unpredicted consequences. This guide is divided into two sections. In the :ref:`first_section documentation <kconfcheck-guidelines>`, ``kconfcheck``, a tool that checks ``Kconfig`` and various ``sdkconfig.*`` files is described. In the :ref:`second section <kconfig_guidelines>`, common situations that may lead to problems are described.

The ``kconfcheck`` Tool
-----------------------

.. _kconfcheck-guidelines:

The ``kconfcheck`` tool enforces a specific style of ``Kconfig`` and various ``sdkconfig.*`` files in order to be more uniform across all ESP-IDF components. In this section, tips and tricks for this tool will be described in the future. In the meantime, please visit the :ref:`Kconfig Files Checking <kconfcheck>` section in ESP-IDF Documentation.

Useful Tips and Tricks
----------------------

.. _kconfig_guidelines:

Dependencies
^^^^^^^^^^^^

Sometimes, developers tends to use construct:

.. code-block:: kconfig

    if CONDITION

        config OPTION
            bool "Prompt"

    endif

Although it may seem similar to many programming languages and thus be favorable by some, it is generally not recommended to use ``if`` block in this situation as it is not a proper Kconfig way to write a dependency. Below, there is a revised version of the above code:

.. code-block:: kconfig

    config OPTION
        bool "Prompt"
        depends on CONDITION

The ``if`` block is primarily used in situations where ``depends on`` syntax is not possible (e.g. conditional including of other Kconfig files via ``source`` entry).

.. _reverse_dependencies_by_non_bool_source:

Reverse Dependencies With non-``bool`` Source Configs
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To briefly summarize dependencies in Kconfig, there are two types of dependencies: direct and reverse. Direct dependencies are defined in the target symbol (symbol whose value is changed based on the value of another symbol), while reverse dependencies are defined in the source symbol (symbol whose value changes independently). Although there is no restriction on the type of the target symbol, the source symbol must be of ``bool`` type in order to define a reverse dependency.

.. note::

    Please visit the :ref:`select, imply <select-imply-options>` and :ref:`set and set default <set-set-default-options>` sections for more information about reverse dependencies.

However, in certain situations, it may be necessary to set a value of a non-``bool`` target symbol based on the value of a non-``bool`` source symbol. For example, you may want to set a ``string`` target symbol based on the value of a ``string`` source symbol. In such cases, there is no way to do this directly. However, by introducing another symbol (a "mapper"), you can achieve the desired result.

.. note::

    All of the following examples can be solved more easily with direct dependencies and/or by ``default`` option. Direct dependencies should be preferred if possible. However, target symbol may not be in the same Kconfig file, but e.g. in another component (or more generally, somewhere you cannot edit it) and thus it would be impossible to use direct dependencies.

Suppose you want to set ``JEDI_NAME`` to ``Mace Windu`` if ``LIGHTSABER_COLOR`` is set to ``purple``. In this example, ``LIGHTSABER_COLOR`` is a source symbol and ``JEDI_NAME`` is a target symbol. It is not possible to do this directly, as the source symbol ``LIGHTSABER_COLOR`` is not a ``bool``-type config option. However, if you define a ``bool``-type config option that will be used as a mapper (``LIGHTSABER_COLOR_PURPLE``), you can achieve the desired result. See the example below:

.. code-block:: kconfig

    # This is the target symbol (the one whose value is based on the value of source symbol)
    config JEDI_NAME
        string "Name of the Jedi"

    # This is the source symbol (the one whose value changes independently)
    # It is a string, which means that we cannot use any of the reverse dependency options
    # (select, imply, set, set default) on it.
    config LIGHTSABER_COLOR
        string "Color of the lightsaber"
        default "purple"

    # This is the mapper symbol that will be used to set the target symbol based on the source symbol
    config LIGHTSABER_COLOR_PURPLE
        # without a prompt, this symbol will not appear in menuconfig (we don't want the user to change it)
        bool
        default y if LIGHTSABER_COLOR="purple"
        set JEDI_NAME="Mace Windu"

    # You can use more mapper symbols for other colors

Previous example supposed that every mapping from ``LIGHTSABER_COLOR`` to ``JEDI_NAME`` is done by a separate mapper symbol. However, all the mapper symbols can be combined into a single one, which will set the value of ``JEDI_NAME`` based on the value of ``LIGHTSABER_COLOR``. See the example below:

.. code-block:: kconfig

    # This is the target symbol (the one whose value is based on the value of source symbol)
    config JEDI_NAME
        string "Name of the Jedi"

    # This is the source symbol (the one whose value changes independently)
    # It is a string, which means that we cannot use any of the reverse dependency options
    # (select, imply, set, set default) on it.
    config LIGHTSABER_COLOR
        string "Color of the lightsaber"
        default "purple"

    # This mapper symbol will map any specific value of LIGHTSABER_COLOR to a specific value of JEDI_NAME
    config LIGHTSABER_TO_JEDI_NAME
        bool
        default y # needs to be set to y for the set options to take effect
        set JEDI_NAME="Mace Windu" if LIGHTSABER_COLOR="purple"
        set JEDI_NAME="Anakin Skywalker" if LIGHTSABER_COLOR="blue"
        set JEDI_NAME="Darth Vader" if LIGHTSABER_COLOR="red"
        # ...and so on for other colors

In both cases, if none of the ``set`` options are satisfied, the value of ``JEDI_NAME`` will be empty. You can also add a default value to the ``JEDI_NAME`` symbol to avoid ``JEDI_NAME`` being empty if none of the ``set`` options are satisfied.

You can also use the mapper symbol when source is a non-``bool`` type config option and the target is a ``bool`` type config option. Below, there is an example for separate mapper symbols for each name:

.. code-block:: kconfig

    # This is the target symbol (the one whose value is based on the value of source symbol)
    config IS_JEDI
        bool "Is the person a Jedi?"
        default n

    # This is the source symbol (the one whose value changes independently)
    config NAME
        string "Name of the person"
        default "Yoda"

    # This mapper symbol will map the value of NAME to a boolean value of IS_JEDI
    config YODA_IS_JEDI
        bool
        default y if NAME="Yoda"
        select IS_JEDI

    # You can add more mapper symbols for other names

It is also possible to use a single mapper symbol that will set the value of ``IS_JEDI`` based on several values of ``NAME``. See the example below:

.. code-block:: Kconfig

    # This is the target symbol (the one whose value is based on the value of source symbol)
    config IS_JEDI
        bool "Is the person a Jedi?"
        default n

    # This is the source symbol (the one whose value changes independently)
    config NAME
        string "Name of the person"
        default "Yoda"

    # This mapper symbol will map the value of NAME to a boolean value of IS_JEDI
    config NAME_TO_IS_JEDI
        bool
        default y
        select IS_JEDI if NAME="Yoda"
        select IS_JEDI if NAME="Anakin Skywalker"
        # if none of the above conditions are satisfied, IS_JEDI will be set to n
