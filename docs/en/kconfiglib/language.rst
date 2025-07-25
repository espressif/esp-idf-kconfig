.. _language-description:

Description of ``kconfig`` Language
===================================

This description is based on the original Kconfig language, as described in the `Kconfig language documentation <https://www.kernel.org/doc/Documentation/kbuild/kconfig-language.txt>`_. However, this documentation aims to provide clearer and more formal description of the language, including :ref:`list of differences <differences>` between the original Kconfig language and the ``esp-idf-kconfig`` implementation. It also reflects changes made in the `esp-idf-kconfig` implementation.


Introduction and Basic Concepts
-------------------------------

The language is used to describe configuration options (configs and choices), organize them in a tree-like structure for e.g. GUI configurators and to define relations between the configs. Kconfig keywords can be divided into two groups: entries and options. Entries define basic structure of the configuration itself and individual configuration options. Options further specify the entries. All the possible keywords together with their syntax and semantics will be described further. For now, here is a list of all Kconfig keywords:

- entries (described in `Entries`_): ``mainmenu``, ``menu``, ``config``, ``menuconfig``, ``choice``, ``source``, ``if``, ``comment`` and macros
- options (described in `Options`_), ``<type>`` (one of ``bool``, ``int``, ``string``, ``hex``), ``prompt``, ``depends on``, ``default``, ``help``, ``range``, ``select``, ``imply``, ``option``, ``visible if``

Kconfig is indentation based language (like e.g. Python or YAML). In the context of `esp-idf-kconfig`, the indentation should always be 4 spaces. The language is case-sensitive, so ``config`` and ``CONFIG`` have different meaning. When quoting strings, it is highly recommended to use double quotes.

Entries
-------

Entries are of two types: one type is describing the config options (``config``, ``menuconfig``, ``choice``), second type is used to organize or describe them (``mainmenu``, ``menu``, ``source``, ``if``, ``comment``). The in depth description of the entries follows. Information about the usage, possible options, formal syntax and examples are provided for every entry.

.. _mainmenu:

The ``mainmenu`` Entry
^^^^^^^^^^^^^^^^^^^^^^

The root entry of the configuration is the ``mainmenu`` entry, which is followed by a block of other entries indented by one level. There must be exactly one ``mainmenu`` entry in a configuration, specifically in the root Kconfig file. The ``mainmenu`` entry has no options. The ``menu_name`` is a double-quoted string that will as the heading of the configuration menu (invoked e.g. by menuconfig).

.. note::

    In context of ESP-IDF, the ``mainmenu`` entry is defined in the root ``Kconfig`` file of the project.

Syntax is as follows, where ``entries`` can be zero or more of the following: ``config``, ``menu``, ``choice``, ``source``, ``menuconfig``, ``if``, ``comment``, which will be explained further. As stated before, those entries are indented by one level.

.. code-block:: bnf

    mainmenu ::= "mainmenu" + menu_name + entries

Example:

.. code-block:: kconfig

    mainmenu "Spaceship configuration"

        config SHIP_NAME
            string "USS Enterprise"
            default "USS Enterprise"

        choice SHIP_STATUS
            bool "Ship status"

            config STATUS_ACTIVE
                bool "active"

            config STATUS_INACTIVE
                bool "inactive"

        (...)

The ``menu`` Entry
^^^^^^^^^^^^^^^^^^

The ``menu`` entry is used to group configuration options together. It can contain the same entries as the ``mainmenu`` entry. In contrast to the ``mainmenu`` entry, the ``menu`` entry is ended explicitly with the ``endmenu`` keyword on the same indentation level as the menu start.

The ``menu`` has following options: ``visible if``, ``depends on``, neither of them is mandatory.

Syntax is as follows, where ``entries`` and ``menu_name`` are defined the same as in the ``mainmenu`` entry. The ``menu_name`` is a double-quoted string.

.. code-block:: bnf

    menu ::= "menu" + menu_name + [+ visible_if | depends_on] + entries + "endmenu"

.. note::
    ``visible if`` vs ``depends on``:
    - ``visible if`` is used to conditionally show/hide the menu e.g. in the GUI configurator. Even if the menu is not visible, its sub-entries still influence the rest of the configuration (e.g. via dependencies).
    - ``depends on`` is used to conditionally include the menu in the configuration. If the condition is not met, the configuration behaves like the menu was not there at all.

Example:

.. code-block:: kconfig

    menu "Crew"
        # If ship is inactive, crew is not visible, but still present in the configuration
        visible if STATUS_ACTIVE

        config CREW_ONBOARD
            int "Crew members onboard"
            default 430

        config CAPTAIN
            string "Captain"
            default "James T. Kirk"
            (...)

        (...)

    endmenu

    menu "Rations"
        # If ship is not active, this menu is completely removed from the configuration
        depends on STATUS_ACTIVE

        config RATION_TYPE
            string "Type of rations"
            default "Synthfood"

        (...)

    endmenu

.. _config:

The ``config`` Entry
^^^^^^^^^^^^^^^^^^^^

The ``config`` entry is used to define a configuration option and is probably the most used entry in the Kconfig language.

This entry can have the following options:

- ``<type>``: mandatory, one of ``bool``, ``int``, ``string``, ``hex``
- ``prompt``: optional, at most one
- ``default``: optional, multiple times
- ``help``: optional, at most one
- ``depends on``: optional, multiple times (but always can be merged into one, see :ref:`depends on section <depends-on-option>`)
- ``range``: optional, multiple times
- ``select``: optional, multiple times
- ``imply``: optional, multiple times
- ``option``: deprecated

The formal syntax is as follows, where ``config_name`` is a non-quoted capitalized string consisting of letters from the English alphabet, numbers, and underscores, ``config_options`` are listed above and described in the `Options`_ section. Those options are indented by one level.

.. code-block:: bnf

    config ::= "config" + config_name + config_options

Examples:

.. code-block:: kconfig

    config CAPTAIN
        string
        prompt "Captain"
        default "James T. Kirk"
        imply FIRST_OFFICER
        help
            Captain of the ship.


.. code-block:: kconfig

    config SUBLIGHT_SPEED
        int "Sublight speed"
        depends on SUBLIGHT_DRIVE
        help
            Speed of the ship in sublight mode in percent.
        range 0 100
        default 10

The ``choice`` Entry
^^^^^^^^^^^^^^^^^^^^

The ``choice`` entry is used to define an exclusive choice between several configs. These configs need to be defined in the body of the choice. The ``choice`` entry has the same options as the ``config`` entry, except for the ``<type>`` option, which is always ``bool`` and it is not necessary to define it (although possible, for compatibility reasons).

.. note::

    In contrast to the upstream Kconfig language, the ``optional`` keyword is not supported in the ``choice`` entry, as well as other types.


The ``choice`` entry consists of the ``choice`` keyword, followed by ``choice_name``, ``config_options`` block and several ``entries`` closed by ``endchoice`` keyword (see the formal syntax below). The ``choice_name`` is a non-quoted capitalized string consisting of letters, numbers, and underscores, ``config_options`` are described in the `Options`_ section. The ``config_options`` and ``entries`` are indented by one level, ``endchoice`` token is at the same indentation level as the ``choice`` token.


.. code-block:: bnf

    choice ::= "choice" + choice_name + config_options + entries* + "endchoice"

.. note::

    The ``choice`` entry should contain only ``config`` entries as its sub-entries. Syntactically, ``choice`` is allowed to contain other entries (such as ``menu``) as well, although this functionality results in rather unusual and confusing structure. Usually, it is better to define those elements outside of the ``choice``.

    .. code-block:: kconfig

        choice DRIVE_IN_USE
            prompt "Choose drive type"

            config WARP_DRIVE
                bool "Warp drive"

            config SUBLIGHT_DRIVE
                bool "Sublight drive"

            menu "Warp drive configuration"
                # This menu will be shown inside the choice in GUI/TUI,
                # but it is separated from the choice logic (WARP_SPEED is not a choice config).
                visible if WARP_DRIVE

                config WARP_SPEED
                    int "Light years per second"
                    default 8

            endmenu
        endchoice



Example usage:

.. code-block:: kconfig

    choice DRIVE
        prompt "Choose drive type"

        config WARP_DRIVE
            bool "Warp drive"

        config SUBLIGHT_DRIVE
            bool "Sublight drive"

    endchoice


The ``menuconfig`` Entry
^^^^^^^^^^^^^^^^^^^^^^^^

The ``menuconfig`` is a combination of ``menu`` and ``config`` entries. It is used to define a configuration option that is also a menu. This means that ``menuconfig`` has a value, but also a submenu with more config options. This particular entry is useful if some functionality should have a general config, e.g. ``FEATURE_ENABLED``, but also several more specific configs for specifying e.g. its behavior.

This entry can have the same options as ``config`` (``<type>``, ``prompt``, ``depends on``, ``default``, ``help``, ``range``, ``select``, ``imply``, ``option``, ``visible if``, from which only ``<type>`` is mandatory).


Syntax is as follows. The sub-configs are not marked by the indentation, but by the ``depends on`` option, which is set to the ``menuconfig``'s name, or, alternatively, with the ``if`` block. The ``config_name`` is a non-quoted capitalized string consisting of letters from the English alphabet, numbers, and underscores, ``config_options`` are described in the `Options`_ section and are indented by one level.

.. code-block:: bnf

    # The sub-configs are not present as they are not a part of the syntax, but rather a semantical construct.
    menuconfig ::= "menuconfig" + config_name + config_options


Config entries that should be sub-configs of given ``menuconfig`` must have the ``depends on`` option set to the ``menuconfig``'s name, as shown in the example.

Example usage:

.. code-block:: kconfig

    menuconfig ENABLE_WARP
        bool "Enable warp drive."
        default y
        depends on WARP_DRIVE

    # Note: choose only one of the following in your configuration

    config WARP_SPEED
        int "Light years per second"
        depends on ENABLE_WARP
        default 8

    if ENABLE_WARP

        config WARP_COLOR
            hex "Warp color"
            default 0x00FF00

    endif

.. note::

    When to use ``menuconfig``, ``choice``, ``menu``?

    - Use ``menuconfig`` when you want to have a general config for enabling/disabling a functionality and several specific configs for its configuration.
    - Use ``choice`` when you want to have an exclusive choice between several configs.
    - Use ``menu`` when you want to group several entries together, but you don't need to have an umbrella config for them - or those entries are not only configs.

The Macro Entry
^^^^^^^^^^^^^^^

Macro is a special type of entry allowing user to define a name for given value without creating a config option. Instead of other entries, it is not started by any keyword, but rather a direct assignment of a value to a name. Once defined, the macro can be used in other entries as a value (e.g. in ``default`` or ``range`` options). If used before its definition, the system will evaluate it as non-existent. There are two ways how to use the macro:

* ``$(MACRO_NAME)``: The system will first try to expand it as a macro. If the macro is not defined, the system will try to expand it as an environment variable. If that fails, the value is empty and will cause a parse error. The value may be bool, string, int or hex.
* ``"$(MACRO_NAME)"``: Same as above, but the value will always be a string and empty expansion does not result in an error but empty string instead.

.. note::

    Macros are only helpers when e.g. some value is used repeatedly in one ``Kconfig`` file. Unlike config options, macros are not written out to ``sdkconfig`` files in any way.

The syntax is as follows. The ``symbol_name`` is a non-quoted capitalized string consisting of letters from the English alphabet, numbers, and underscores, ``value`` is an integer, hexadecimal number, string or a Kconfig boolean (y/n). In the context of simple ``NAME = value`` pairs, there is not difference between ``=`` and ``:=`` and the support of the latter is only for compatibility reasons.

.. code-block:: bnf

    macro ::= symbol_name + ("=" | ":=") + value

.. note::

    Original ``kconfiglib`` supported wider variety of macros. However, ESP-IDF does not use them and thus, only basic macros are supported.

Example:

.. code-block:: kconfig

    MAX_NUMBER_OF_MOTORS := 1

    config MOTOR_NUMBER
        int "Number of motors"
        default $(MAX_NUMBER_OF_MOTORS)
        help
            Number of motors

The ``if`` Entry
^^^^^^^^^^^^^^^^

The ``if`` keyword as an entry is used to define a conditional block of entries. The block is only included in the configuration if the condition is met.

Syntax is as follows, where ``expression`` is a boolean expression and ``entries`` are the same as in the ``mainmenu`` or ``menu`` entry (i.e. all entries except ``mainmenu``). The ``expression`` consists of config names connected with standard numeric and boolean operators. The ``entries`` are indented by one level. The ``if`` entry has no options and is ended explicitly with the ``endif`` keyword on the same indentation level as the ``if`` keyword.

.. code-block:: bnf

    if_entry ::= "if" + expression + entries + "endif"


Example usage:

.. code-block:: kconfig

    if ENABLE_WARP

        config WARP_SPEED
            int "Light years per second"
            default 8

    endif

The ``comment`` Entry
^^^^^^^^^^^^^^^^^^^^^

The ``comment`` entry is used to add a comment for the user into the configuration. The comment can be used to describe a group of entries, a single entry or to add a note to the configuration.

The only option of the ``comment`` entry is optional ``depends_on``.

.. note::

    Please pay attention to the difference between the ``comment`` entry and #-style comment. The first one is a part of the configuration and puts comments e.g. into the GUI interface (``idf.py menuconfig``), the second one is a standard comment ignored by the parser.
    In other words, use ``comment`` if you want to add a comment for the user, use #-style comment if you want to add a comment for the developer.

Syntax is as follows, where ``comment_prompt`` is a quoted string and ``depends_on`` is a list of config names, which the comment depends on. The ``depends_on`` is optional.

.. code-block:: bnf

    comment ::= "comment" + comment_prompt + depends_on*

Example:

.. code-block:: kconfig

    # Comment below will show up in the GUI configurator, but not this one
    comment "Warp drive configuration"
        depends on WARP_DRIVE

    menuconfig WARP_DRIVE
        (...)

The ``source`` Entry
^^^^^^^^^^^^^^^^^^^^

This entry is used to include another Kconfig file into the current one. The ``source`` entry is used to split the configuration into multiple files, which can be useful for better organization of the configuration. The ``source`` entry has no options.

There are four sub-types of ``source`` entry:

- ``source``: The path specified  must lead to a valid Kconfig file and must be absolute.
- ``rsource``: The path specified must lead to a valid Kconfig, but is relative to the current Kconfig file.
- ``osource``: The path specified does not need to lead to a valid Kconfig file, but must be absolute. The file is included only if it exists.
- ``orsource``: The path specified does not need to lead to a valid Kconfig file and is relative to the current Kconfig file. The file is included only if it exists.

Syntax is as follows, where ``path`` is a quoted string.

.. code-block:: bnf

    source ::= ("source" | "rsource" | "osource" | "orsource") + path

Example:

.. code-block:: kconfig

    menu "Crew"

        rsource "./Kconfig.core_crew"
        orsource "./Kconfig.optional_crew"

.. _Options:

Options
-------

Options further specify the entries and are indented by one level. They will be described in the following sections. Every option has an information about its syntax and semantics, possible entries where it can be used and if it is mandatory or optional.

The ``<type>`` Option
^^^^^^^^^^^^^^^^^^^^^

The type of the configuration option. The possible values are ``bool``, ``int``, ``string``, ``hex``. If used, only one type definition is allowed per entry. Optionally, it can be followed by the inline prompt and the ``if`` keyword and a boolean expression (see :ref:`prompt option section <prompt-option>` for more details). If the expression will be false, the option will not be visible in the GUI configurator.

This option can be used in the following entries:

- ``config``: mandatory
- ``menuconfig``: mandatory
- ``choice``: optional, only for compatibility reasons, only ``bool`` type is allowed

.. note::

        The ``tristate`` and ``def_<type>`` types are not supported in the `esp-idf-kconfig` implementation.

Syntax is as follows, where inline prompt is an optional quoted string and can be used to define the prompt directly after the type definition:

.. code-block:: bnf

    type ::= "bool" | "int" | "string" | "hex" [+ inline_prompt [+ "if" + condition]]

Example:

.. code-block:: kconfig

    config WARP_DRIVE
        bool "Warp drive"

    config WARP_SPEED
        int "Light years per second"
        default 8

    config WARP_COLOR
        hex "Warp color"
        default 0x00FF00

    config CAPTAIN
        string "Captain"
        default "James T. Kirk"

The ``prompt`` Option
^^^^^^^^^^^^^^^^^^^^^

.. _prompt-option:

Prompt is the string which can be seen in a GUI configuration tool (e.g. ``idf.py menuconfig``). Prompt can be defined either implicitly (after the type definition) or explicitly (as a separate option starting with ``prompt`` keyword). The prompt is a quoted string optionally followed by the ``if`` keyword and a boolean expression to condition it.

This option can be used in the following entries and is optional:

- ``config``
- ``menuconfig``
- ``choice``

If no prompt is defined, given entry is considered as not visible (refer to :ref:`visible if option section <visible-if-option>` for more information about visibility).

.. note::

    Prompt vs config name: prompt is the string you see in ``menuconfig`` TUI, config name is what ESP-IDF sees when reading e.g. ``sdkconfig``. Kconfig system also adds a ``CONFIG_`` prefix to all the config names to distinguish them from e.g. environment variables.

Example:

.. code-block:: kconfig

    config RATION_PER_PERSON
        # This is a specific config option. If it is not a detailed view, we want it to hide it,
        # but still be present in the configuration and e.g. influence the total number of food.
        int "Rations per person and day" if DETAILED_VIEW
        default 3


The ``depends on`` Option
^^^^^^^^^^^^^^^^^^^^^^^^^

.. _depends-on-option:

The ``depends on`` option is used to define a (direct) dependency of the current option on another option. The dependency is an expression of config names connected with standard numeric and boolean operators (see `Expressions`_ for more details).

This option can be used in the following entries and is optional:

- ``config``
- ``menuconfig``
- ``choice``
- ``comment``
- ``menu``

.. code-block:: bnf

    depends_on ::= "depends on" + expression


Example:

.. code-block:: kconfig

    config WARP_SPEED
        int "Light years per second"
        # if warp drive is chosen and enabled, this option will be added to the configuration and be visible
        depends on WARP_DRIVE && ENABLE_WARP
        default 8

.. _select-option:
.. _imply-option:
.. _select-imply-options:

The ``select`` and ``imply`` Options
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``select`` and ``imply`` options are used to define a so-called reverse dependency between ``bool`` configs. Let's suppose you have two ``bool``-type configs, ``SOURCE`` and ``TARGET``. You want to set a value for ``TARGET`` based on the value of ``SOURCE``. Reverse dependency means that the relation between ``SOURCE`` and ``TARGET`` is defined in the ``SOURCE`` config definition. This is in contrast to the direct dependency, which is defined in the ``TARGET`` config definition (for details, please visit :ref:`depends on option <depends-on-option>`).

If you want to define reverse dependency, you can use the ``select`` or ``imply`` options in the ``SOURCE`` definition. The difference between ``select`` and ``imply`` options is that ``select`` ignores the direct dependencies of the target symbol, while ``imply`` does not ignore them.

.. note::

    Both ``select`` and ``imply`` options are only applicable to ``bool`` type (menu)configs. In other words, you cannot use them to set a value for a non-``bool`` dependent (target) symbol. If you want to set reverse dependency for non-``bool`` target symbol, use the :ref:`set and set default options <set-set-default-options>`.

    Generally, the source symbol must always be of type ``bool``. However, this limitation can be worked around by introducing so-called "mapping symbol" (see :ref:`reverse_dependencies_by_non_bool_source`).

Both options always select/imply only one other ``(menu)config`` (however, they can be used multiple times) and can be defined conditionally with the ``if`` keyword and a boolean expression.

These options can be used in the following entries (optionally, multiple times):

- ``config``: only for ``bool`` type
- ``menuconfig``: only for ``bool`` type

.. code-block:: bnf

    select ::= "select" + symbol [+ "if" + expression]
    imply ::= "imply" + symbol [+ "if" + expression]

Where ``symbol`` is a non-quoted capitalized string consisting of letters from the English alphabet, numbers, and underscores. The ``if`` keyword and the boolean expression are optional.

.. note::

    Reverse dependencies are often needed; but use them with caution. They can lead to unexpected behavior and make the configuration harder to understand.

Example for ``select`` and ``imply``:

.. code-block:: kconfig

    comment "Reverse dependency example"

    config LEFT_MOTOR
        bool "Target symbol for imply"

    config RIGHT_MOTOR
        bool "Target symbol for source"

    config SUBLIGHT_DRIVE
        bool "Source symbol"
        # if SUBLIGHT_DRIVE is enabled (equals y), RIGHT_MOTOR is also enabled (equals y) and cannot be set to n - no matter what its direct dependencies say!
        # if SUBLIGHT_DRIVE is disabled (equals n), RIGHT_MOTOR can be enabled or disabled (both y and n are allowed)
        select RIGHT_MOTOR
        # if SUBLIGHT_DRIVE is enabled (equals y), LEFT_MOTOR is also enabled (equals y), but can be disabled (equals n) by its direct dependencies!
        # if SUBLIGHT_DRIVE is disabled (equals n), LEFT_MOTOR can be enabled or disabled (both y and n are allowed)
        imply LEFT_MOTOR

.. _set-option:
.. _set-default-option:
.. _set-set-default-options:

The ``set`` and ``set default`` Options
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``set`` and ``set default`` options allow you to define reverse dependency between a ``bool``-type source symbol and non-``bool`` (``int``, ``string``, ``hex``) target symbol. Let's suppose you have a ``bool``-type symbol ``SOURCE`` and non-``bool`` symbol ``TARGET``. You want to set a value for ``TARGET`` based on the value of ``SOURCE``. Reverse dependency means that the relation between ``SOURCE`` and ``TARGET`` is defined in the ``SOURCE`` config definition.

The ``set`` option ignores direct dependencies and defaults of the target symbol, the ``set default`` option does not.

Although ``TARGET`` symbol can be of ``int``, ``string``, or ``hex`` type, the ``SOURCE`` symbol must be of type ``bool``.

.. note::

    As mentioned above, source symbols can only be of a ``bool``-type. However, this limitation can be worked around by introducing so-called "mapping symbol" (see :ref:`reverse_dependencies_by_non_bool_source`).

This option can be used in the following entries (optionally, multiple times):

- ``config``: only for ``bool``-type source symbols
- ``menuconfig``: only for ``bool``-type source symbols

Formal syntax is as follows:

.. code-block:: bnf

    set ::= "set" + assignment [+ "if" + expression ]
    set_default ::= "set default" + assignment [+ "if" + expression ]

    assignment ::= symbol + "=" +  ( value | symbol )

Where ``symbol`` is a non-quoted capitalized string consisting of letters from the English alphabet, numbers, and underscores, ``value`` is a quoted string, integer or hexadecimal number. The ``if`` keyword and the boolean expression are optional.

Example for ``set`` and ``set default``:

.. code-block:: kconfig

    config SHIP_NAME
        string "Ship name"
        default "USS Generic"

    config NUMBER_OF_MOTORS
        int "Number of motors"
        default 1
        depends on SUBLIGHT_DRIVE

    config ENTERPRISE_DEFAULT_VALUES
        bool "Provide Enterprise default values"
        default n
        # If ENTERPRISE_DEFAULT_VALUES is enabled, Enterprise-specific default values
        # are set for SHIP_NAME and NUMBER_OF_MOTORS.
        # However, user can still change them.
        set default SHIP_NAME="USS Enterprise"
        set default NUMBER_OF_MOTORS=6

    config ENTERPRISE_NCC1701_VALUES
        bool "Provide values for specific USS Enterprise NCC-1701"
        default n
        # If ENTERPRISE_NCC1701_VALUES is enabled, values for specific USS Enterprise NCC-1701
        # are set for SHIP_NAME and NUMBER_OF_MOTORS. These values would also override values
        # set by ``set default`` (e.g. by ``ENTERPRISE_DEFAULT_VALUES``).
        # These cannot be changed by the user.
        set SHIP_NAME="USS Enterprise NCC-1701"
        set NUMBER_OF_MOTORS=2

The ``default`` Option
^^^^^^^^^^^^^^^^^^^^^^

The ``default`` option is used to define the default value of the configuration option. The default value can be defined conditionally with the ``if`` keyword and a boolean expression. If more than one default value is defined, the first one with its condition met is used.

This option can be used in the following entries (optionally, multiple times):

- ``config``, but if the config is a choice entry, the default value has no meaning; it is ignored and a warning is shown.
- ``menuconfig``
- ``choice``

.. code-block:: bnf

    default ::= "default" + symbol [+ "if" + expression]


Example:

.. code-block:: kconfig

    config WARP_SPEED
        int "Light years per second"
        default 10 if WARP_TURBO
        default 8

The ``help`` Option
^^^^^^^^^^^^^^^^^^^

The ``help`` option is used to define a help text for the configuration option. The help text is a multiline string indented by one level.

This option can be used in the following entries and is optional:

- ``config``
- ``menuconfig``
- ``choice``
- ``menu``

.. code-block:: bnf

    help_option ::= "help" + multiline_string

Example:

.. code-block:: kconfig

    config WARP_SPEED
        int "Light years per second"
        help
            Speed of the ship in warp mode in light years per second.
            The speed is limited by the warp drive power.

The ``range`` Option
^^^^^^^^^^^^^^^^^^^^

The ``range`` option is used to define the range of the configuration option of type ``int`` or ``hex``. The range is defined by two numbers; lower and upper limit. Both limit values are included in the allowed interval. The range can be defined conditionally with the ``if`` keyword and a boolean expression.

This option can be used in the following entries and is optional:

- ``config``: only for ``int`` and ``hex`` types
- ``menuconfig``: only for ``int`` and ``hex`` types

.. code-block:: bnf

    range_entry ::= "range" + number + number [+ "if" + expression]

Example:

.. code-block:: kconfig

    config SUBLIGHT_SPEED
        int "Sublight speed"
        depends on SUBLIGHT_DRIVE
        help
            Speed of the ship in sublight mode in percent.
        # Limiting the speed to 0-100 percent interval.
        range 0 100
        default 10

The ``visible if`` Option
^^^^^^^^^^^^^^^^^^^^^^^^^

.. _visible-if-option:

This option is used to conditionally show/hide the menu in the GUI configurator. Even if the entry is not visible, entry itself and its sub-entries still influence the rest of the configuration (e.g. via dependencies).

This option can be used in the following entries and is optional:

- ``menu``

The syntax is shown below, where ``expression`` is a boolean expression.

.. code-block:: bnf

    visible_if ::= "visible if" + expression

Example:

.. code-block:: kconfig

    menu "Crew"
        # If ship is inactive, crew is not visible, but still present in the configuration
        visible if STATUS_ACTIVE

        config CREW_ONBOARD
            int "Crew members onboard"
            default 430

        config CAPTAIN
            string "Captain"
            default "James T. Kirk"
            (...)

        (...)
    endmenu

The ``option`` Option (Deprecated)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``option`` option is used to define an environment variable for the configuration option.

.. note::

    There is no need to use ``option env=``. Instead, it is possible to directly use ``default "${ENV_VAR_NAME}"``.


Expressions
-----------

In the previous text, expressions were mentioned several times. Expressions are (menu)config and choice names connected by one of the allowed logic operators: ``=``, ``!=``, ``<``, ``>``, ``<=``, ``>=``, ``&&``, ``||``. Expressions can be nested with parentheses.

The formal syntax is as follows:

.. code-block:: bnf

    expression ::= symbol
                | symbol '=' symbol
                | symbol '!=' symbol
                | symbol '<' symbol
                | symbol '>' symbol
                | symbol '<=' symbol
                | symbol '>=' symbol
                | (expression)
                | !expression
                | expression && expression
                | expression || expression

Example:

.. code-block:: kconfig

    (...)
    depends on WARP_DRIVE && ENABLE_WARP
    (...)
    default 10 if WARP_TURBO
    (...)


Using Environment Variables in Expressions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Environment variables can also be used in expressions. The name of the environment variable is enclosed in curly brackets and preceded by a dollar sign. The whole expression is then enclosed in double quotes. Subsequently, values from environment variables can be used only with ``string`` config options. Environment variables are evaluated in parse-time. If the environment variable is not defined, Kconfig system treats it as an string with the value of environment variable name (including the dollar sign and curly brackets, e.g. ``${ENV_VAR_NAME}``).

Example:

.. code-block:: kconfig

    config CAPTAIN_NAME
        string "Name of the ship's captain"
        default "${CAPTAIN_NAME}" # if CAPTAIN_NAME environment is defined, it will have it's value. If not, the value will be "${CAPTAIN_NAME}"

.. note::

    Originally, the value of environment variables was transferred into Kconfig system with the ``option env=ENV_VAR_NAME`` syntax. This is currently deprecated and it is strongly recommended to use ``default "${ENV_VAR_NAME}"`` instead.
