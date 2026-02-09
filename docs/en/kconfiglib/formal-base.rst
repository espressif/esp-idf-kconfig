Formal Description of Kconfig Language
==========================================

.. _formal_base:

Below, a context-free grammar describing the Kconfig language is presented. This grammar is used as a base for the ``esp-idf-kconfig`` parser based on `Pyparsing <https://github.com/pyparsing/pyparsing>`_. Indentation is omitted in the grammar for simplicity, but in :ref:`detailed description <language-description>`, indentation is explicitly mentioned. Terminals are in uppercase, non-terminals are in lowercase, literals are in double-quotes.

.. code-block:: bnf

    # Entry point
    mainmenu ::= "mainmenu" + menu_name + entries*
    entries ::= config | menu | choice | source | menuconfig | if_entry | comment | macro

    # Entries
    config ::= "config" + config_name + config_options
    menu ::= "menu" + menu_name + menu_options + entries + "endmenu"
    choice ::= "choice" + choice_name + config_options + entries* + "endchoice""
    source ::= ("source" | "rsource" | "osource" | "orsource") + path
    menuconfig ::= "menuconfig" + config_name + config_options
    if_entry ::= "if" + expression + entries + "endif"
    comment ::= "comment" + STRING + depends_on*
    macro ::= macro_name + ("=" | ":=") + value

    menu_options ::= visible_if

    # (menu)config and choice options
    config_options ::= (config_type | config_and_prompt)
                       + (default* | help_option | depends_on* | range_entry* | prompt | select* | imply* | option* | set * | set_default * | warning)*

    config_type ::= "bool" | "int" | "hex" | "string" | "float"
    config_and_prompt ::= config_type + noname_prompt
    noname_prompt ::= STRING [+ "if" + expression]

    default ::= "default" + symbol [+ "if" + expression ]
    help_option ::= "help" + MULTILINE_STRING
    depends_on ::= "depends on" + expression
    range_entry ::= "range" + number + number [+ "if" + expression]
    prompt ::= "prompt" + STRING [+ "if" + expression ]
    select ::= "select" + symbol [+ "if" + expression ]
    imply ::= "imply" + symbol [+ "if" + expression ]
    set ::= "set" + assignment [+ "if" + expression ]
    set_default ::= "set default" + assignment [+ "if" + expression ]
    option ::= "option env=" + STRING
    visible_if ::= "visible if" + expression
    warning ::= "warning" + noname_prompt

    assignment ::= symbol + "=" +  ( value | symbol )

    expression ::= expression + "=" + expression
                | expression + "!=" + expression
                | expression + "<" + expression
                | expression + ">" + expression
                | expression + "<=" + expression
                | expression + ">=" + expression
                | "(" + expression + ")"
                | "!" + expression
                | expression + "&&" + expression
                | expression + "||" + expression

    # Terminals
    symbol ::= config_symbol | envvar | value
    # Regular expression "[A-Z0-9_]+" means "Capitalized letters from the English alphabet, numbers, and underscores"
    config_name ::= REGEX("[A-Z0-9_]+")
    choice_name ::= REGEX("[A-Z0-9_]+")
    macro_name ::= REGEX("[A-Z0-9_]+")
    value ::= INT | HEX | STRING | FLOAT
    menu_name ::= QUOTED_STRING
    path ::= QUOTED_STRING
