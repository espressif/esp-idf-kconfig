Formal Description of Kconfig Language
==========================================

.. _formal_base:

Below, a context-free grammar describing the Kconfig language is presented. This grammar is used as a base for the ``esp-idf-kconfig`` parser based on `Pyparsing <https://github.com/pyparsing/pyparsing>`_. Indentation is omitted in the grammar for simplicity, but in :ref:`detailed description <language-description>`, indentation is explicitly mentioned. Terminals are in uppercase, non-terminals are in lowercase, literals are in double-quotes.

.. code-block:: bnf

    # Entry point
    mainmenu ::= "mainmenu" + menu_name + entries*
    entries ::= config | menu | choice | source | menuconfig | if_entry | comment

    # Entries
    config ::= "config" + config_name + config_options
    menu ::= "menu" + menu_name + entries + "endmenu"
    choice ::= "choice" + choice_name + config_options + config* + "endchoice""
    source ::= ("source" | "rsource" | "osource" | "orsource") + path
    menuconfig ::= "menuconfig" + config_name + config_options
    if_entry ::= "if" + expression + entries + "endif"
    comment ::= "comment" + STRING + depends_on*

    # (menu)config and choice options
    config_options ::= (config_type | config_and_prompt)
                       + (default* | help_option | depends_on* | range_entry* | prompt | select* | imply* | option*)*

    config_type ::= "bool" | "int" | "hex" | "string"
    config_and_prompt ::= config_type + noname_prompt
    noname_prompt ::= STRING [+ "if" + expression]

    default ::= "default" + symbol [+ "if" + expression ]
    help_option ::= "help" + MULTILINE_STRING
    depends_on ::= "depends on" + expression
    range_entry ::= "range" + number + number [+ "if" + expression]
    prompt ::= "prompt" + STRING [+ "if" + expression ]
    select ::= "select" + symbol [+ "if" + expression ]
    imply ::= "imply" + symbol [+ "if" + expression ]
    option ::= "option env=" + STRING

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
    config_name ::= STRING
    value ::= INT | HEX | STRING
    menu_name ::= QUOTED_STRING
    path ::= QUOTED_STRING
