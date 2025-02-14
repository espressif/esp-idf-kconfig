#!/usr/bin/env python
#
# Command line tool to check kconfig files
#
# SPDX-FileCopyrightText: 2018-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0

import argparse
import os
import re
from typing import Optional
from typing import Tuple

from .check_deprecated_options import _prepare_deprecated_options
from .check_deprecated_options import check_deprecated_options

# output file with suggestions will get this suffix
OUTPUT_SUFFIX = ".new"

CONFIG_PREFIX = "CONFIG_"

SPACES_PER_INDENT = 4

CONFIG_NAME_MAX_LENGTH = 50

CONFIG_NAME_MIN_PREFIX_LENGTH = 3

# The checker will not fail if it encounters this string (it can be used for temporarily resolve conflicts)
RE_NOERROR = re.compile(r"\s+#\s+NOERROR\s+$")

# list or rules for lines
LINE_ERROR_RULES = [
    # (regular expression for finding,      error message,                                  correction)
    (
        re.compile(r"\t"),
        "tabulators should be replaced by spaces",
        r" " * SPACES_PER_INDENT,
    ),
    (re.compile(r"\s+\n"), "trailing whitespaces should be removed", r"\n"),
    (re.compile(r".{120}"), "line should be shorter than 120 characters", None),
]


class InputError(RuntimeError):
    """
    Represents and error on the input
    """

    def __init__(self, path, line_number, error_msg, suggested_line):
        super(InputError, self).__init__("{}:{}: {}".format(path, line_number, error_msg))
        self.suggested_line = suggested_line


class BaseChecker(object):
    """
    Base class for all checker objects
    """

    def __init__(self, path_in_idf):
        self.path_in_idf = path_in_idf

    def finalize(self):
        """
        Abstract method for finalizing the checker
        """
        pass

    def process_line(self, line, line_number):
        """
        Abstract method for processing a line
        """
        raise NotImplementedError("process_line method is not implemented in BaseChecker")


class SourceChecker(BaseChecker):
    # allow to source only files which will be also checked by the script
    # Note: The rules are complex and the LineRuleChecker cannot be used
    def process_line(self, line, line_number):
        m = re.search(r'^\s*[ro]{0,2}source(\s*)"([^"]+)"', line)

        if m:
            if len(m.group(1)) == 0:
                raise InputError(
                    self.path_in_idf,
                    line_number,
                    '"source" has to been followed by space',
                    line.replace("source", "source "),
                )
            path = m.group(2)
            filename = os.path.basename(path)
            if path in [
                "$COMPONENT_KCONFIGS_SOURCE_FILE",
                "$COMPONENT_KCONFIGS_PROJBUILD_SOURCE_FILE",
            ]:
                pass
            elif not filename.startswith("Kconfig."):
                raise InputError(
                    self.path_in_idf,
                    line_number,
                    "only filenames starting with Kconfig.* can be sourced",
                    line.replace(path, os.path.join(os.path.dirname(path), "Kconfig." + filename)),
                )


class LineRuleChecker(BaseChecker):
    """
    checks LINE_ERROR_RULES for each line
    """

    def process_line(self, line, line_number):
        suppress_errors = RE_NOERROR.search(line) is not None
        errors = []
        for rule in LINE_ERROR_RULES:
            m = rule[0].search(line)
            if m:
                if suppress_errors:
                    # just print but no failure
                    e = InputError(self.path_in_idf, line_number, rule[1], line)
                    print(f"NOERROR: {e}")
                else:
                    errors.append(rule[1])
                if rule[2]:
                    line = rule[0].sub(rule[2], line)
        if len(errors) > 0:
            raise InputError(self.path_in_idf, line_number, "; ".join(errors), line)


class ConfigNameChecker(BaseChecker):
    """
    Checks if the global syntax of config/symbol names is correct.
    Every rule is in separate method to allow easy extension.
    """

    def __init__(self, path_in_idf):
        super().__init__(path_in_idf)

    def rule_prefix(self, config_name: str, line: str, line_number: int) -> None:
        if not config_name.startswith(CONFIG_PREFIX):
            config_name_start = line.find(config_name)
            raise InputError(
                self.path_in_idf,
                line_number,
                f"{config_name} should start with {CONFIG_PREFIX}",
                f"{line[:config_name_start]}{CONFIG_PREFIX}{line[config_name_start:]}",
            )

    def rule_uppercase(self, config_name: str, line: str, line_number: int) -> None:
        if not config_name.isupper():
            raise InputError(
                self.path_in_idf,
                line_number,
                f"{config_name} should be all uppercase",
                line.replace(config_name, config_name.upper()),
            )

    def rule_name_len(self, config_name: str, line: str, line_number: int) -> None:
        name_length = len(config_name)
        # When checking Kconfig files, there is not yet a prefix and thus, 50-char length is checked without it.
        # To be consistent, prefix is not counted in the length.
        if name_length - len(CONFIG_PREFIX) > CONFIG_NAME_MAX_LENGTH:
            raise InputError(
                self.path_in_idf,
                line_number,
                f"{config_name} is {name_length} characters long and it should be {CONFIG_NAME_MAX_LENGTH} at most",
                line,
            )  # no suggested correction for this

    def process_line(self, line: str, line_number: int) -> None:
        raise NotImplementedError("ConfigNameChecker checks config names, not lines.")

    def process_config_name(self, config_name: str, line: str, line_number: int) -> None:
        for rule in (self.rule_prefix, self.rule_uppercase, self.rule_name_len):
            rule(config_name, line, line_number)


class IndentAndNameChecker(BaseChecker):
    """
    checks the indentation of each line and configuration names
    """

    def __init__(self, path_in_idf, debug=False):
        super(IndentAndNameChecker, self).__init__(path_in_idf)
        self.debug = debug
        self.min_prefix_length = CONFIG_NAME_MIN_PREFIX_LENGTH

        # stack of the nested menuconfig items, e.g. ['mainmenu', 'menu', 'config']
        self.level_stack = []

        # stack common prefixes of configs
        self.prefix_stack = []

        # if the line ends with '\' then we force the indent of the next line
        self.force_next_indent = 0

        # menu items which increase the indentation of the next line
        self.re_increase_level = re.compile(
            r"""^\s*
                                          (
                                               (menu(?!config))
                                              |(mainmenu)
                                              |(choice)
                                              |(config)
                                              |(menuconfig)
                                              |(help)
                                              |(if)
                                              |(source)
                                              |(osource)
                                              |(rsource)
                                              |(orsource)
                                          )
                                       """,
            re.X,
        )

        # closing menu items which decrease the indentation
        self.re_decrease_level = re.compile(
            r"""^\s*
                                          (
                                               (endmenu)
                                              |(endchoice)
                                              |(endif)
                                          )
                                       """,
            re.X,
        )

        # matching beginning of the closing menuitems
        self.pair_dic = {
            "endmenu": "menu",
            "endchoice": "choice",
            "endif": "if",
        }

        # regex for config names
        self.re_name = re.compile(
            r"""^
                                       (
                                            (?:config)
                                           |(?:menuconfig)
                                           |(?:choice)

                                       )\s+
                                       (\w+)
                                      """,
            re.X,
        )

        # regex for new prefix stack
        self.re_new_stack = re.compile(
            r"""^
                                            (
                                                 (?:menu(?!config))
                                                |(?:mainmenu)
                                                |(?:choice)

                                            )
                                            """,
            re.X,
        )

        # regexes to get lines containing expressions
        # Unquoted symbols are either config names, y/n or (hex)num literals. Catching also no-uppercase config names (TyPO_NAME) to throw an error later on.
        # Quoted symbols are "y"/"n", env_vars or string literals; the last two categories can contain anything between the quotes, thus it is broader.
        symbol = r"\w+|\".+?\"|'.+?'"
        reg_prompt = re.compile(r"^\".*?\"\s+(?:if)\s+(?P<expression0>.*)$")
        reg_default = re.compile(r"^(?P<expression0>.*)\s+(?:if)\s+(?P<expression1>.*)$")
        reg_select_imply = re.compile(rf"^(?P<expression0>{symbol})\s+(?:if)\s+(?P<expression1>.*)$")
        reg_range = re.compile(
            rf"^(?P<expression0>{symbol})\s+(?P<expression1>{symbol})\s+(?:if)\s+(?P<expression2>.*)$"
        )
        reg_depends_on_visible_if = re.compile(r"^(?P<expression0>.*)$")
        reg_config_menuconfig_choice = re.compile(rf"^(?P<expression>{symbol})$")
        self.reg_switch = re.compile(
            r"^\s*(?P<keyword>prompt|default|select|imply|range|depends on|config|menuconfig|choice|visible if)\s+(?P<body>.*)$"
        )
        self.reg_symbol = re.compile(rf"{symbol}", re.X)

        self.kw_to_regex = {
            "prompt": reg_prompt,
            "default": reg_default,
            "select": reg_select_imply,
            "imply": reg_select_imply,
            "range": reg_range,
            "depends on": reg_depends_on_visible_if,
            "visible if": reg_depends_on_visible_if,
            "config": reg_config_menuconfig_choice,
            "menuconfig": reg_config_menuconfig_choice,
            "choice": reg_config_menuconfig_choice,
        }

    def finalize(self):
        if len(self.prefix_stack) > 0:
            self.check_common_prefix("", "EOF")
        if len(self.prefix_stack) != 0:
            if self.debug:
                print(self.prefix_stack)
            raise RuntimeError("Prefix stack should be empty. Perhaps a menu/choice hasn't been closed")

    def del_from_level_stack(self, count):
        """delete count items from the end of the level_stack"""
        if count > 0:
            # del self.level_stack[-0:] would delete everything and we expect not to delete anything for count=0
            del self.level_stack[-count:]

    def update_level_for_inc_pattern(self, new_item):
        if self.debug:
            print("level+", new_item, ": ", self.level_stack, end=" -> ")
        # "config" and "menuconfig" don't have a closing pair. So if new_item is an item which need to be indented
        # outside the last "config" or "menuconfig" then we need to find to a parent where it belongs
        if new_item in [
            "config",
            "menuconfig",
            "menu",
            "choice",
            "if",
            "source",
            "rsource",
            "osource",
            "orsource",
        ]:
            # item is not belonging to a previous "config" or "menuconfig" so need to indent to parent
            for i, item in enumerate(reversed(self.level_stack)):
                if item in ["menu", "mainmenu", "choice", "if"]:
                    # delete items ("config", "menuconfig", "help") until the appropriate parent
                    self.del_from_level_stack(i)
                    break
            else:
                # delete everything when configs are at top level without a parent menu, mainmenu...
                self.del_from_level_stack(len(self.level_stack))

        self.level_stack.append(new_item)
        if self.debug:
            print(self.level_stack)
        # The new indent is for the next line. Use the old one for the current line:
        return len(self.level_stack) - 1

    def update_level_for_dec_pattern(self, new_item):
        if self.debug:
            print("level-", new_item, ": ", self.level_stack, end=" -> ")
        target = self.pair_dic[new_item]
        for i, item in enumerate(reversed(self.level_stack)):
            # find the matching beginning for the closing item in reverse-order search
            # Note: "menuconfig", "config" and "help" don't have closing pairs and they are also on the stack. Now they
            # will be deleted together with the "menu" or "choice" we are closing.
            if item == target:
                i += 1  # delete also the matching beginning
                if self.debug:
                    print("delete ", i, end=" -> ")
                self.del_from_level_stack(i)
                break
        if self.debug:
            print(self.level_stack)
        return len(self.level_stack)

    def check_name_sanity(self, line: str, line_number: int) -> None:
        def is_hex(s: str) -> bool:
            return re.search(r"^0x[0-9a-fA-F]+$", s) is not None

        line = line[: line.index("#")] + "\n" if "#" in line else line
        line_with_symbols = self.reg_switch.match(line)

        if line_with_symbols:
            expressions = self.kw_to_regex[line_with_symbols.group("keyword")].match(line_with_symbols.group("body"))
            if expressions:
                for k in expressions.groupdict().keys():
                    symbols = self.reg_symbol.findall(expressions.groupdict()[k])
                    for symbol in symbols:
                        if not (
                            symbol in ("y", '"y"', "n", '"n"')
                            or symbol.isupper()
                            or symbol.isnumeric()
                            or is_hex(symbol)
                            or symbol.startswith(('"', "'"))
                        ):
                            raise InputError(
                                self.path_in_idf,
                                line_number,
                                f"config name {symbol} should be all uppercase",
                                line.replace(symbol, symbol.upper()),
                            )

    def check_name_and_update_prefix(self, line, line_number):
        m = self.re_name.search(line)
        if m:
            name = m.group(2)
            name_length = len(name)

            if name_length > CONFIG_NAME_MAX_LENGTH:
                raise InputError(
                    self.path_in_idf,
                    line_number,
                    f"{name} is {name_length} characters long and it should be {CONFIG_NAME_MAX_LENGTH} at most",
                    line + "\n",
                )  # no suggested correction for this
            if len(self.prefix_stack) == 0:
                self.prefix_stack.append(name)
            elif self.prefix_stack[-1] is None:
                self.prefix_stack[-1] = name
            else:
                # this has nothing common with paths but the algorithm can be used for this also
                self.prefix_stack[-1] = os.path.commonprefix([self.prefix_stack[-1], name])
            if self.debug:
                print("prefix+", self.prefix_stack)
        m = self.re_new_stack.search(line)
        if m:
            self.prefix_stack.append(None)
            if self.debug:
                print("prefix+", self.prefix_stack)

    def check_common_prefix(self, line, line_number):
        common_prefix = self.prefix_stack.pop()
        if self.debug:
            print("prefix-", self.prefix_stack)
        if common_prefix is None:
            return
        common_prefix_len = len(common_prefix)
        if common_prefix_len < self.min_prefix_length:
            raise InputError(
                self.path_in_idf,
                line_number,
                'The common prefix for the config names of the menu ending at this line is "{}".\n'
                "\tAll config names in this menu should start with the same prefix of {} characters "
                "or more.".format(common_prefix, self.min_prefix_length),
                line,
            )  # no suggested correction for this
        if len(self.prefix_stack) > 0:
            parent_prefix = self.prefix_stack[-1]
            if parent_prefix is None:
                # propagate to parent level where it will influence the prefix checking with the rest which might
                # follow later on that level
                self.prefix_stack[-1] = common_prefix
            else:
                if len(self.level_stack) > 0 and self.level_stack[-1] in [
                    "mainmenu",
                    "menu",
                ]:
                    # the prefix from menu is not required to propagate to the children
                    return
                if not common_prefix.startswith(parent_prefix):
                    raise InputError(
                        self.path_in_idf,
                        line_number,
                        f"Common prefix '{common_prefix}' should start with {parent_prefix}",
                        line,
                    )  # no suggested correction for this

    def process_line(self, line, line_number):
        stripped_line = line.strip()
        if len(stripped_line) == 0:
            self.force_next_indent = 0
            return
        # Ignore comment lines
        if stripped_line.startswith("#"):
            return
        current_level = len(self.level_stack)
        m = re.search(r"\S", line)  # indent found as the first non-space character
        if m:
            current_indent = m.start()
        else:
            current_indent = 0

        if current_level > 0 and self.level_stack[-1] == "help":
            if current_indent >= current_level * SPACES_PER_INDENT:
                # this line belongs to 'help'
                self.force_next_indent = 0
                return

        if self.force_next_indent > 0:
            if current_indent != self.force_next_indent:
                raise InputError(
                    self.path_in_idf,
                    line_number,
                    "Indentation consists of {} spaces instead of {}".format(current_indent, self.force_next_indent),
                    (" " * self.force_next_indent) + line.lstrip(),
                )
            else:
                if not stripped_line.endswith("\\"):
                    self.force_next_indent = 0
                return

        elif stripped_line.endswith("\\") and stripped_line.startswith(("config", "menuconfig", "choice")):
            raise InputError(
                self.path_in_idf,
                line_number,
                "Line-wrap with backslash is not supported here",
                line,
            )  # no suggestion for this

        m = self.re_increase_level.search(line)
        if m:
            current_level = self.update_level_for_inc_pattern(m.group(1))
        else:
            m = self.re_decrease_level.search(line)
            if m:
                new_item = m.group(1)
                current_level = self.update_level_for_dec_pattern(new_item)
                if new_item not in ["endif"]:
                    # endif doesn't require to check the prefix because the items inside if/endif belong to the
                    # same prefix level
                    self.check_common_prefix(line, line_number)

        # name has to be checked after increase/decrease indentation level
        # otherwise false-positive indentation error for lines below name is raised
        self.check_name_sanity(line, line_number)
        self.check_name_and_update_prefix(stripped_line, line_number)

        expected_indent = current_level * SPACES_PER_INDENT

        if stripped_line.endswith("\\"):
            self.force_next_indent = expected_indent + SPACES_PER_INDENT
        else:
            self.force_next_indent = 0

        if current_indent != expected_indent:
            raise InputError(
                self.path_in_idf,
                line_number,
                "Indentation consists of {} spaces instead of {}".format(current_indent, expected_indent),
                (" " * expected_indent) + line.lstrip(),
            )


class SDKRenameChecker(BaseChecker):
    """
    Checks sdkconfig.rename[.target] files:
    * if the line contains at least two tokens (old and new config name pairs)
    * if the inversion syntax is used correctly
    """

    def __init__(self, path_in_idf):
        super().__init__(path_in_idf)
        self.renames = dict()  # key = old name, value = new name
        self.config_name_checker = ConfigNameChecker(path_in_idf)

    def process_line(self, line: str, line_number: int) -> None:
        # The line should look like CONFIG_OLD_NAME CONFIG_NEW_NAME # optional comment,
        # just # comment or blank line.
        if line.startswith("#") or line.isspace():
            return

        tokens = line.split()
        if len(tokens) < 2:
            raise InputError(
                self.path_in_idf,
                line_number,
                "Line should contain at least old and new config names.",
                line,  # no suggestions for this
            )
        else:
            old_name, new_name = tokens[:2]  # [:2] removes optional comment from tokens

        inversion = False
        if new_name.startswith("!"):  # inversion
            new_name = new_name[1:]
            inversion = True

        ############################################
        # sdkconfig.rename specific checks
        ############################################
        # Check inversion syntax
        if old_name.startswith("!"):
            raise InputError(
                self.path_in_idf,
                line_number,
                "For inversion, use CONFIG_OLD !CONFIG_NEW syntax",
                line[: line.index(old_name)]
                + old_name[1:]
                + line[line.index(old_name) + len(old_name) : line.index(new_name)]
                + "!"
                + line[line.index(new_name) :],
            )

        # Check for duplicit lines
        if old_name in self.renames.keys() and self.renames[old_name] == new_name:
            raise InputError(
                self.path_in_idf,
                line_number,
                f"There is a duplicit line: {old_name} {new_name if not inversion else '!'+new_name}",
                "",  # omit the duplicate
            )

        # Check if the there is repeated rename from the old name
        # This is not allowed because if the two different new names would have different values, the result would be ambiguous
        # NOTE: Multiple renames to the same new name are allowed. In that case, the value of the new name is just propagated to all the old names.
        if old_name in self.renames.keys():
            raise InputError(
                self.path_in_idf,
                line_number,
                f"There already is a renaming from an old config name {old_name}",
                line,  # no suggestions for this
            )

        ############################################
        # Checking correctness of the config names
        ############################################
        # We want to check only if correct prefix is used, old names may not comply with the rules
        self.config_name_checker.rule_prefix(old_name, line, line_number)
        self.config_name_checker.process_config_name(new_name, line, line_number)

        # Add the new renaming to the dictionary
        self.renames[old_name] = new_name


def valid_directory(path):
    if not os.path.isdir(path):
        raise argparse.ArgumentTypeError("{} is not a valid directory!".format(path))
    return path


def validate_file(file_full_path: str, verbose: bool = False, replace: bool = False) -> bool:
    # Even in case of in_place modification, create a new file with suggestions (original will be replaced later).
    suggestions_full_path = file_full_path + OUTPUT_SUFFIX
    fail = False
    checkers: Tuple[BaseChecker, ...] = tuple()
    if "Kconfig" in os.path.basename(file_full_path):
        checkers = (
            IndentAndNameChecker(file_full_path),  # indent checker has to be before line checker, otherwise
            # false-positive indent error if error in line_checker
            LineRuleChecker(file_full_path),
            SourceChecker(file_full_path),
        )
    elif "sdkconfig.rename" in os.path.basename(file_full_path):
        checkers = (SDKRenameChecker(file_full_path),)

    if not checkers:
        raise NotImplementedError(
            f"The {os.path.basename(file_full_path)} files are not currently supported by kconfcheck."
        )

    with open(file_full_path, "r", encoding="utf-8") as f, open(
        suggestions_full_path, "w", encoding="utf-8", newline="\n"
    ) as f_o:
        try:
            for line_number, line in enumerate(f):
                try:
                    for checker in checkers:
                        checker.process_line(line=line, line_number=line_number)
                    # The line is correct therefore we echo it to the output file
                    f_o.write(line)
                except InputError as e:
                    print(e)
                    fail = True
                    f_o.write(e.suggested_line)
        except UnicodeDecodeError:
            raise ValueError("The encoding of {} is not Unicode.".format(file_full_path))
        finally:
            for checker in checkers:
                try:
                    checker.finalize()
                except InputError as e:
                    print(e)
                    fail = True

    if replace:
        os.replace(suggestions_full_path, file_full_path)

    if fail:
        print(
            "\t{} has been saved with suggestions for resolving the issues.\n"
            "\tPlease note that the suggestions can be wrong and "
            "you might need to re-run the checker several times "
            "for solving all issues".format(suggestions_full_path if not replace else file_full_path)
        )
        return False
    else:
        print("{}: OK".format(file_full_path))
        # If replace, file already removed
        if not replace:
            try:
                os.remove(suggestions_full_path)
            except Exception:
                # It is not a serious error if the file cannot be deleted
                print(f"{suggestions_full_path} cannot be deleted!")
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Kconfig style checker")
    parser.add_argument(
        "--check",
        "-c",
        choices=["syntax", "deprecated"],
        default="syntax",
        help="Check syntax or deprecated options",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Kconfig files to check (full paths separated by space)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print more information (useful for debugging)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=f"[only for --check syntax] Apply the changes to the original files instead of creating {OUTPUT_SUFFIX} files",
    )
    parser.add_argument(
        "--includes",
        "-d",
        nargs="*",
        help="[only for --check deprecated] Paths for recursive search of sdkconfig files",
        type=valid_directory,
    )
    parser.add_argument(
        "--exclude-submodules",
        nargs="*",
        type=valid_directory,
        help="[only for --check deprecated] Exclude ESP-IDF submodules",
    )

    args = parser.parse_args()

    if args.check == "syntax" and (args.includes is not None or args.exclude_submodules is not None):
        raise argparse.ArgumentError(
            None, "--includes and --exclude-submodules are available only when using --check deprecated option."
        )

    if args.check == "deprecated" and args.replace:
        raise argparse.ArgumentError(None, "--replace is available only when using --check syntax option.")

    success_counter = 0
    failure_counter = 0
    ignored_counter = 0

    files = [os.path.abspath(file_path) for file_path in args.files]

    if args.check == "deprecated":
        files, deprecated_options, ignore_dirs = _prepare_deprecated_options(
            args.includes, args.exclude_submodules, files
        )

    for full_path in files:
        file_ok: Optional[bool] = False
        if args.check == "syntax":
            file_ok = validate_file(full_path, args.verbose, args.replace)
        elif args.check == "deprecated":
            file_ok = check_deprecated_options(full_path, deprecated_options, ignore_dirs)
        else:
            raise argparse.ArgumentError(None, f"Unknown check type: {args.check} passed to --check argument.")

        if file_ok is None:
            ignored_counter += 1
        elif file_ok is True:
            success_counter += 1
        else:
            failure_counter += 1

    def _handle_plural(cnt: int) -> str:
        return "s" if cnt > 1 else ""

    if success_counter > 0:
        print(f"{success_counter} file{_handle_plural(success_counter)} have been successfully checked.")
    if ignored_counter > 0:
        print(f"{ignored_counter} file{_handle_plural(success_counter)} have been ignored.")
    if failure_counter > 0:
        print(f"{failure_counter} file{_handle_plural(success_counter)} have errors. Please take a look at the log.")
        return 1

    if not files:
        print("WARNING: no files specified.")
    return 0
