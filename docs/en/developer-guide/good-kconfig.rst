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
