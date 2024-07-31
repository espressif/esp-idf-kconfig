# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import re
from typing import List
from typing import Optional
from typing import Tuple
from typing import TYPE_CHECKING

from pyparsing import alphanums
from pyparsing import Forward
from pyparsing import Group
from pyparsing import IndentedBlock
from pyparsing import infix_notation
from pyparsing import Keyword
from pyparsing import LineEnd
from pyparsing import Literal
from pyparsing import one_of
from pyparsing import OneOrMore
from pyparsing import opAssoc
from pyparsing import Opt
from pyparsing import ParseException
from pyparsing import PrecededBy
from pyparsing import QuotedString
from pyparsing import Regex
from pyparsing import Suppress
from pyparsing import Token
from pyparsing import Word

if TYPE_CHECKING:
    from kconfiglib.kconfig_parser import Parser


class KconfigBlock(Token):
    """
    Abstract class for custom Kconfig related pyparsiong blocks.
    """

    def __init__(self):
        super().__init__()

    def get_preceding_line(self, instring: str, loc: int) -> Optional[str]:
        if loc <= 0 or loc > len(instring):
            return None

        # Start looking backward from loc - 1 to find the previous newline
        pos = instring.rfind("\n", 0, loc - 1)
        # Now find the start of the line preceding the one we just found
        end_of_prev_line = pos
        pos = instring.rfind("\n", 0, pos - 1)

        start_of_prev_line = pos + 1

        # Return the preceding line
        return instring[start_of_prev_line : end_of_prev_line + 1]

    def leading_whitespace_len(self, line: str) -> int:
        return len(line) - len(line.lstrip())

    def first_non_empty_line_idx(self, lines: list, idx: int = 0) -> Optional[int]:
        for i, line in enumerate(lines[idx:]):
            if line.strip():
                return i + idx
        return None


class KconfigHelpBlock(KconfigBlock):
    """
    This ParserElement is used to parse help blocks in Kconfig files. It turned out it is easier to do that directly than to use pyparsing's IndentedBlock or other approach.
    It is little strange to cast it into one token, but help block is just a plain text without any structure or meaning for the parser. Parsing it as a one token helps
    the parser not to search for possible matches in it.
    """

    def __init__(self):
        super().__init__()

    def _generateDefaultName(self) -> str:
        return "help_block"

    def parseImpl(self, instring: str, loc: int, doActions: bool = True) -> Tuple[int, str]:
        result = []
        lines = instring[loc:].split("\n")

        preceding_line = self.get_preceding_line(instring, loc)
        if not preceding_line:
            raise ParseException(instring, loc, "Error parsing help block.", self)
        help_keyword_indent = self.leading_whitespace_len(preceding_line)
        # This is the indentation of the first line of the help block.
        # From now on, everything with the same or higher indentation (plus empty lines after which the same indentation level continues) is considered to be part of the help block.
        idx = self.first_non_empty_line_idx(lines)
        if idx is None:
            raise ParseException(instring, loc, "Error parsing help block.", self)
        default_indent = self.leading_whitespace_len(lines[idx])
        if default_indent <= help_keyword_indent:
            raise ParseException(instring, loc, "Help block must be indented more than the help keyword.", self)

        indents_removed = 0
        line: str
        for i, line in enumerate(lines):
            # NOTE: Now, there can be blank lines right after help keyword. This is IMHO against Kconfig language, but it is used in some kconfig files.
            # FIXME in the future

            # blank line inside help block:
            if not line or line.isspace():
                idx = self.first_non_empty_line_idx(lines, idx=i)
                if idx is None:
                    break
                if (
                    self.first_non_empty_line_idx(lines, idx=i)
                    and self.leading_whitespace_len(lines[idx]) >= default_indent
                ):
                    result.append(line[default_indent:] if line else line)
                    indents_removed += 1 if line else 0
                else:
                    break

            # line of help block
            elif self.leading_whitespace_len(line) >= default_indent:
                result.append(line[default_indent:])  # cannot use strip as I want to preserve inner indentation
                indents_removed += 1
            else:
                break
            # end of help block
        result_str = "\n".join(result)
        # It is OK to final loc like this; if some lines are overindented in the help,
        # the overindentation is preserved in the help text itself
        return loc + len(result_str) + indents_removed * default_indent, result_str


class KconfigGrammar:
    """
    Grammar of the kconfig language.
    Parse actions are defined in the Parser class -> if another format will be used, it is enough to change the Parser class.
    """

    def __init__(self, parser: "Parser") -> None:
        self.init_grammar(parser)

    def init_grammar(self, parser: "Parser") -> None:
        """
        Initializes the grammar for the Kconfig language.

        The pyparsing package embraces "bottom-up" approach both in the parsing and grammar definition.
        Thus, the logic behind the definitions is that first, nested elements are defined (e.g. config options) and only then the wrapping element (e.g. config itself) is defined.

        More info is directly in the code below.
        """

        # Complete regex combining all the parts:
        symbol_regex = r"""(?<!\S)
                           (y|n|\"y\"|\"n\")(?!\S)  # y, n, "y", "n" symbols
                           |0[x|X][\da-fA-F]+  # hexnums: 0x1234, 0X1234ABCD
                           |[\d-]+   # numbers: 1234, -1234
                           |[A-Z\d_]+  # variables: FOO, BAR_BAR, ENABLE_ESP64
                           |'[^']*'  # strings: 'here is a đĐđĐ[]tring'
                           |\"[^\"]*\" # strings: "hello world", ""
                           |\"\$\([A-Z_\d]+\)\" # "$(ENVVAR)"
                           |\"\$[A-Z_\d]+\""""  # "$ENVVAR"
        symbol = Regex(symbol_regex, re.X)

        # The regex above is equivalent to the following pyparsing definition:
        # Order matters! Order of thumb: more specific first.
        # symbol = (
        #    oneOf("y n \"y\" \"n\"", as_keyword=True)
        #    | Combine(CaselessLiteral("0x") + Word(hexnums))  # 0x1234, 0x1234ABCD, etc.
        #    | Word(nums + "-")  # 1234, -1234, etc.
        #    | Word(alphanums.upper() + "_" + nums)  # FOO, BAR_BAR, ENABLE_ESP64, etc.
        #    | QuotedString("'", unquote_results=False)
        #    | QuotedString('"', unquote_results=False)  # 'here is a đĐđĐ[]tring', "hello world", etc.
        #    | Literal('""')  # "" - needs to be a separate case, because the case above ignores ""
        #    | Combine(Literal('"$(') + Word(alphanums.upper() + "_") + Literal(')"'))  # "$(ENVVAR)"
        #    | Combine(Literal('"$') + Word(alphanums.upper() + "_") + Literal('"'))  # "$ENVVAR"
        # )

        #############################
        # Conditions and expressions
        ############################
        # Operators with precedence given by the order of the list
        operator_with_precedence = [
            (Literal("!"), 1, opAssoc.RIGHT),
            (one_of("= != < > <= >="), 2, opAssoc.LEFT),
            (one_of("&&"), 2, opAssoc.LEFT),
            (one_of("||"), 2, opAssoc.LEFT),
        ]

        # Expression has operators above and symbols as operands
        expression = infix_notation(symbol, operator_with_precedence)

        condition = Suppress(Keyword("if")) + Group(expression)
        # By default, pyparsing removes all the leading and trailing whitespaces and thus these two constructs appear the same:
        #    ...
        #    default y
        #
        # if SOME_VAR...
        #
        # and
        #
        # default y if SOME_VAR
        #
        # Here, we are forcing that there cannot be a line break between "default" and "if"
        # to correctly parse inline condition (second case in the example above).
        inline_condition = ~PrecededBy(LineEnd()) + condition

        ##########################
        # Options
        #
        # They are mostly for configs & choices, but:
        # - "depends on" can be used for menus, comments
        # - "visible if" can be used for menus
        ##########################

        # Prompt is a string (with optional condition) defined either with "prompt" keyword or implicitly (without a keword) after a type definition
        # Every config/choice can have max. one prompt which is used to show to the user. Optionally, it can be conditioned.
        inline_prompt = (QuotedString('"') | QuotedString("'")) + Opt(inline_condition)
        prompt = Keyword("prompt") + Group(inline_prompt).set_results_name("prompt")

        # Type of the config/choice.
        config_type = (one_of(["bool", "int", "string", "hex"], as_keyword=True) + Opt(inline_prompt)).set_results_name(
            "type"
        )

        # Direct dependencies for the given menu entry (menu, choice, comment, config)
        # If multiple dependencies are needed, they are grouped using standard logical operators.
        # For now, it is OK to have multiple depends_on -> list_all_matches=True
        # NOTE: It should not be needed to have multiple depends on - they can always be grouped into one expression via &&.
        depends_on = Keyword("depends on") + expression.set_results_name("depends_on", list_all_matches=True)

        # Default value for the config.
        # It is OK to have multiple defaults -> list_all_matches=True
        default = Keyword("default") + (expression + Opt(inline_condition)).set_results_name(
            "default", list_all_matches=True
        )

        # help option
        # It is a bit tricky to parse as the help text can be anything (including newlines).
        help_option = Keyword("help") + LineEnd() + KconfigHelpBlock().leave_whitespace().set_results_name("help_text")

        # Select and imply are both reverse dependencies (it tells us the the selected/implied config depends on the current one).
        # Difference: select is a hard dependency (if the current config is set, the selected one must be set as well not matter what its direct dependencies say!),
        #             imply is a weak dependency (if the current config is set, the implied one can be set as well if direct dependencies will not say otherwise).
        # It is OK to have multiple selects and implies -> list_all_matches=True
        select = Keyword("select") + (Word(alphanums + "_") + Opt(inline_condition)).set_results_name(
            "select", list_all_matches=True
        )
        imply = Keyword("imply") + (Word(alphanums + "_") + Opt(inline_condition)).set_results_name(
            "imply", list_all_matches=True
        )

        # General option, used only for env variables in ESP IDF context.
        option = Keyword("option") + Literal("env=") + Group(QuotedString('"')).set_results_name("option")

        # Allowed range for the config value.
        # It is OK to have multiple ranges -> list_all_matches=True
        range_entry = Keyword("range") + Group(symbol + symbol + Opt(inline_condition)).set_results_name(
            "range", list_all_matches=True
        )

        # Explicitly specifies if the given entry is visible or not.
        # Details about visibility are in the documentation.
        visible_if = Keyword("visible if") + Group(expression).set_results_name("visible_if")

        ###########################
        # Config
        ###########################
        # List of all possible options for the config/choice.
        config_opts = IndentedBlock(
            config_type | default | help_option | depends_on | range_entry | prompt | select | imply | option,
            grouped=True,
        ).set_results_name("config_opts")

        config_name = Word(alphanums.upper() + "_").set_results_name("config_name", list_all_matches=True)

        config = Keyword("config") + config_name + config_opts
        config = config.set_parse_action(parser.parse_config)

        ###########################
        # Comment
        ###########################
        # Not a #-like comment (which is ignored), but a comment block showed in generated sdkconfig file.
        comment_opts = IndentedBlock(depends_on, grouped=True).set_results_name("comment_opts")

        comment = Keyword("comment") + inline_prompt + Opt(comment_opts)
        comment = comment.set_parse_action(parser.parse_comment)

        ###########################
        # Source
        ###########################
        # [o|r|or]source point to a file that should be placed in the place of source.
        # Details about the source are in the documentation.
        # parsing info is in the __call__ method of the KconfigGrammar class (TLDR: recursively, new KconfigGrammar class is created and sourced_root is parsed).
        source_type = one_of(["orsource", "source", "rsource", "osource"], as_keyword=True)
        path = QuotedString('"').set_results_name("path")
        source = (source_type + path).set_parse_action(parser.parse_sourced)

        ########################
        # Choice
        ########################
        # Choice is a group of configs that can have only one active at a time.
        choice = (
            Keyword("choice")
            + (
                Opt(symbol).set_results_name("name")
                + Opt(config_opts)
                + IndentedBlock(config).set_results_name("configs")
            ).set_parse_action(parser.parse_choice)
            + Keyword("endchoice")
        )

        ########################
        # Menuconfig
        ########################
        menuconfig = (Keyword("menuconfig") + config_name + config_opts).set_parse_action(parser.parse_config)

        ########################
        # Menu
        ########################
        menu = Forward()  # Forward declaration is needed because of recursive structure of the menu.
        # if_entry is a recursive element (if_entry can contain menu, menu can contain if_entry).
        # So this is just a declaration of the element, definition comes later.
        if_entry = Forward()  # Forward declaration is needed because of recursive structure of the menu.

        # List of all possible entries in the menu/if block.
        entries = IndentedBlock(config | menu | choice | source | menuconfig | if_entry | comment).set_results_name(
            "entries"
        )

        # List of all possible options for the menu, similar to config_opts.
        menu_opts = IndentedBlock(visible_if | depends_on, grouped=True).set_results_name("menu_opts")

        menu << (Keyword("menu") + QuotedString('"') + Opt(menu_opts) + entries + Keyword("endmenu")).set_parse_action(
            parser.parse_menu
        ).set_results_name("menu")

        ###########################
        # If entry
        ###########################
        # Not "if" as a condition, but "if" as a separate block
        if_entry << Keyword("if") + (expression + entries).set_parse_action(parser.parse_if_entry) + Keyword("endif")

        ###########################
        # Main menu
        ###########################
        mainmenu = (Keyword("mainmenu") + (QuotedString('"') | QuotedString("'")) + entries).add_parse_action(
            parser.parse_mainmenu
        )

        ############################
        # Entry points
        ############################
        # The root of the grammar. It is used to parse the main Kconfig file, which needs to contain mainmenu as a top element.
        self.root = mainmenu

        # sourced file can have different strucutre than the main Kconfig file, thus using a separate root.
        sourced_root = OneOrMore(config | menu | choice | source | menuconfig | if_entry | comment)
        self.sourced_root = sourced_root

    def preprocess_file(self, file: str, ensure_end_newline: bool = True) -> str:
        """
        Helper method for preprocessing the Kconfig files.
        Unfortunately, some Kconfig syntax would be so diffcult to support in pyparsing that it is easier to preprocess the files.
        Specifically, it:
            * merges lines split with '\'
            * removes inline comments
        """

        def remove_inline_comments(s: str) -> str:
            return s[: s.index("#")] + "\n" if "#" in s else s

        with open(file, "r") as f:
            lines = f.readlines()
            return_file = ""
            split_lines_idxs: List[int] = []

            for line_idx, line in enumerate(lines):
                # Remove unneccessary whitespaces from otherwise empty line
                if line.isspace():
                    return_file += "\n"
                    continue

                # Remove inline comments
                line = remove_inline_comments(line)

                # Merge lines split with '\' and place blank lines to reserve line numbering.
                if line_idx in split_lines_idxs:
                    split_lines_idxs.remove(line_idx)
                    return_file += "\n"  # In order to match the original numbering, blank lines are added.
                    continue
                if line.endswith("\\\n"):
                    merged_line = line.rstrip("\n")[:-1]
                    for next_line_idx, next_line in enumerate(lines[line_idx + 1 :]):
                        if next_line.endswith("\\\n"):
                            merged_line += remove_inline_comments(next_line).lstrip(" ").rstrip("\\\n")
                            split_lines_idxs.append(next_line_idx + line_idx + 1)
                        else:  # first line without '\' is still part of the merged line
                            merged_line += " " + remove_inline_comments(next_line).lstrip(" ")
                            split_lines_idxs.append(next_line_idx + line_idx + 1)
                            break
                    return_file += merged_line
                    continue

                return_file += line

        return return_file if not ensure_end_newline else return_file + "\n"

    def __call__(self, file: str, sourced: bool = False):
        """
        Here, pyparsing parsing takes place.
        Parameters:
        * file: str - path to the Kconfig file
        * sourced: bool - flag indicating if the file is from [o|r|or]source entry
        """
        file_content = self.preprocess_file(file)
        # If the file is empty, we have nothing to do
        if not file_content or file_content.isspace():
            return ""

        if not sourced:
            try:
                output = self.root.parse_string(file_content, parse_all=True)
            except ParseException as e:
                raise KconfigParseError(f"Error parsing file {file}: {str(e)}")
        else:
            try:
                output = self.sourced_root.parse_string(file_content, parse_all=True)
            except ParseException as e:
                raise KconfigParseError(f"Error parsing sourced file {file}: {str(e)}")
        return output


class KconfigParseError(Exception):
    """
    Exception raised when parsing of the Kconfig file fails.
    """

    pass
