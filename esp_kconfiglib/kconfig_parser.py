# SPDX-FileCopyrightText: 2024-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
from dataclasses import dataclass
from glob import iglob
from os.path import dirname
from os.path import expandvars
from os.path import join
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union
from typing import no_type_check

from pyparsing import ParserElement
from pyparsing import ParseResults
from pyparsing import line as pyparsing_line
from pyparsing import lineno

from esp_kconfiglib.kconfig_grammar import KconfigGrammar

from .core import AND
from .core import BOOL
from .core import COMMENT
from .core import EQUAL
from .core import GREATER
from .core import GREATER_EQUAL
from .core import HEX
from .core import INT
from .core import LESS
from .core import LESS_EQUAL
from .core import MENU
from .core import NOT
from .core import OR
from .core import STRING
from .core import TYPE_TO_STR
from .core import UNEQUAL
from .core import Choice
from .core import Kconfig
from .core import KconfigError
from .core import MenuNode
from .core import Symbol
from .core import Variable

ParserElement.enablePackrat(cache_size_limit=None)  # Speeds up parsing by caching intermediate results


@dataclass
class Orphan:
    """
    Pyparsing parses the elements with a "bottom-up" approach, thus children are parsed before their parents.
    This class is used to store the nodes and their metadata that are not part of the menu tree (without parent).
    """

    locations: List[Tuple[str, int]]
    node: MenuNode

    def __repr__(self) -> str:
        return "Orphan({}, {})".format(self.node, self.locations)


class Parser:
    """
    The Parser class is responsible for parsing the Kconfig file and building the menu tree.

    Parsing logic: pyparsing is used to parse the input Kconfig file(s) and provide tokens.
    It is supposed that new formats (beside Kconfig) will be supported in the future, so the grammar describing Kconfig
    is in its separate class KconfigGrammar.

    In contrast to the previous (C-like) parsing char-by-char, the new approach utilizes pyparsing
    library and semantic actions (called parse actions in this context and behaving like callbacks).
    """

    def __init__(self, kconfig: "Kconfig", filename: Optional[str] = None) -> None:
        self.kconfig = kconfig

        self.grammar = KconfigGrammar(self)
        self.orphans: List[Orphan] = []

        if not filename:
            self.file_stack = [self.kconfig.filename]
        else:
            self.file_stack = [filename]
        self.location_stack: List[Tuple[str, int]] = []

        self.grammar_for_sourced_files = KconfigGrammar(self)

    def parse_all(self) -> None:
        self.grammar(self.kconfig.filename)

    def get_children(self, parent: MenuNode, location: Tuple[str, int]) -> None:
        if not self.orphans:
            return
        orphans_for_adoption: List[MenuNode] = []
        while self.orphans:
            adopted = False
            for file, start in self.orphans[-1].locations:
                if file == location[0] and location[1] < start:
                    orphan: MenuNode = self.orphans.pop().node
                    orphan.parent = parent
                    orphans_for_adoption.append(orphan)
                    adopted = True
                    break
            if not adopted:
                break

        orphans_for_adoption.reverse()
        # MenuNode.list = first child element
        for orphan in orphans_for_adoption:
            if parent.list:  # there are already children
                orphans_sibling = parent.list
                while orphans_sibling.next:
                    orphans_sibling = orphans_sibling.next
                orphans_sibling.next = orphan
            else:
                parent.list = orphan

    ############################
    # Parse Actions
    ############################
    def parse_mainmenu(self, s: str, loc: int, parsed_mainmenu: ParseResults) -> None:
        self.kconfig.linenr = lineno(loc, s)
        self.kconfig.top_node.prompt = (parsed_mainmenu[1], self.kconfig.y)
        self.get_children(self.kconfig.top_node, (self.file_stack[0], 0))

    def parse_config(self, s: str, loc: int, parsed_config: ParseResults) -> None:
        self.kconfig.linenr = lineno(loc, s)
        sym = self.kconfig._lookup_sym(parsed_config[1])
        self.kconfig.defined_syms.append(sym)

        node = MenuNode(
            kconfig=self.kconfig,
            item=sym,
            is_menuconfig=parsed_config[0] == "menuconfig",
            filename=self.file_stack[-1],
            linenr=lineno(loc, s),
        )

        sym.nodes.append(node)
        self.parse_options(node, parsed_config)
        if parsed_config["config_opts"]["visible_if"]:
            self.kconfig._warn(
                f'config {sym.name} (defined at {self.file_stack[-1]}:{node.linenr}) has a "visible if" option, '
                "which is not supported for configs"
            )

        orphan = Orphan(
            node=node,
            locations=[location for location in self.location_stack if self.location_stack]
            + [(self.file_stack[-1], lineno(loc, s))],
        )
        self.orphans.append(orphan)

    def parse_menu(self, s: str, loc: int, parsed_menu: ParseResults) -> None:
        self.kconfig.linenr = lineno(loc, s)
        menunode = MenuNode(
            kconfig=self.kconfig, item=MENU, is_menuconfig=True, filename=self.file_stack[-1], linenr=lineno(loc, s)
        )

        #                    menu name     condition = always true for menu
        menunode.prompt = (parsed_menu[1], self.kconfig.y)

        menu_options = parsed_menu[2]
        if menu_options["depends_on"]:  # depends on
            for depend in menu_options["depends_on"]:
                expr = self.parse_expression(depend)
                menunode.dep = self.kconfig._make_and(menunode.dep, expr)
        if menu_options["visible_if"]:  # visible if
            menunode.visibility = self.kconfig._make_and(
                menunode.visibility,
                self.parse_expression(menu_options["visible_if"][0]),
            )

        self.kconfig.menus.append(menunode)
        self.get_children(menunode, (self.file_stack[-1], lineno(loc, s)))
        orphan = Orphan(
            node=menunode,
            locations=[location for location in self.location_stack if self.location_stack]
            + [(self.file_stack[-1], lineno(loc, s))],
        )

        self.orphans.append(orphan)

    def parse_sourced(self, s: str, loc: int, parsed_source: ParseResults) -> None:
        self.kconfig.linenr = lineno(loc, s)
        path = expandvars(parsed_source.path)
        if parsed_source[0] in ["rsource", "orsource"]:
            path = join(dirname(self.file_stack[-1]), path)

        # NOTE: We most probably do not use srctree -> remove when refactoring
        filenames = sorted(iglob(join(self.kconfig._srctree_prefix, path)))

        if not filenames and parsed_source[0] in ["source", "rsource"]:
            raise KconfigError(
                "{}:{}: '{}' not found (in '{}'). Check that "
                "environment variables are set correctly (e.g. "
                "$srctree, which is {}). Also note that unset "
                "environment variables expand to the empty string.".format(
                    self.file_stack[-1],
                    lineno(loc, s),
                    path,
                    pyparsing_line(loc, s).strip(),
                    f"set to '{self.kconfig.srctree}'" if self.kconfig.srctree else "unset or blank",
                )
            )

        for filename in filenames:
            self.location_stack.append((self.file_stack[-1], lineno(loc, s)))
            if filename in self.file_stack:
                raise KconfigError(f"{self.file_stack[-1]}:{lineno(loc, s)}: Recursive source of '{filename}' detected")
            self.file_stack.append(filename)
            self.grammar_for_sourced_files(filename, sourced=True)
            self.file_stack.pop()
            self.location_stack.pop()

    def parse_choice(self, s: str, loc: int, parsed_choice: ParseResults) -> None:
        self.kconfig.linenr = lineno(loc, s)
        line_number = lineno(loc, s)
        if parsed_choice.name:
            choice = self.kconfig.named_choices.get(parsed_choice.name)
            if not choice:
                choice = Choice(kconfig=self.kconfig, name=parsed_choice.name, direct_dep=self.kconfig.n)
                self.kconfig.named_choices[parsed_choice.name] = choice
        else:  # nameless choice
            choice = Choice(kconfig=self.kconfig, name=None, direct_dep=self.kconfig.n)
        self.kconfig.choices.append(choice)
        self.kconfig._set_type(choice, BOOL)
        choice.kconfig = self.kconfig

        node = MenuNode(
            kconfig=self.kconfig, item=choice, is_menuconfig=True, filename=self.file_stack[-1], linenr=line_number
        )
        choice.nodes.append(node)

        self.parse_options(node, parsed_choice)
        if not node.prompt:
            self.kconfig._warn(
                f"<choice {choice.name}> (defined at {self.file_stack[-1]}:{node.linenr}) defined without a prompt"
            )
        if parsed_choice["config_opts"]["visible_if"]:
            self.kconfig._warn(
                f'choice {choice.name} (defined at {self.file_stack[-1]}:{node.linenr}) has a "visible if" option, '
                "which is not supported for choices"
            )

        self.get_children(node, (self.file_stack[-1], line_number))
        child = node.list
        children_with_default = []
        while child:
            if not isinstance(child.item, int) and child.item and child.item.defaults:
                children_with_default.append(child)
                break
            else:
                child = child.next

        for child in children_with_default:
            self.kconfig._warn(
                "default on the choice symbol "
                f"{child.item.name if isinstance(child.item, (Symbol, Choice)) else child.item} "
                f"(defined at {self.file_stack[-1]}:{child.linenr}) will have no effect, as defaults "
                "do not affect choice symbols"
            )

        orphan = Orphan(
            node=node,
            locations=[location for location in self.location_stack if self.location_stack]
            + [(self.file_stack[-1], line_number)],
        )
        self.orphans.append(orphan)

    def parse_comment(self, s: str, loc: int, parsed_comment: ParseResults) -> None:
        self.kconfig.linenr = lineno(loc, s)
        node = MenuNode(
            kconfig=self.kconfig, item=COMMENT, is_menuconfig=False, filename=self.file_stack[-1], linenr=lineno(loc, s)
        )
        self.kconfig.comments.append(node)
        self.parse_prompt(node, [(parsed_comment[1], None)])
        orphan = Orphan(
            node=node,
            locations=[location for location in self.location_stack if self.location_stack]
            + [(self.file_stack[-1], lineno(loc, s))],
        )
        self.orphans.append(orphan)

        if parsed_comment.comment_opts and parsed_comment.comment_opts["depends_on"]:
            for depend in parsed_comment.comment_opts["depends_on"]:
                expr = self.parse_expression(depend)
                node.dep = self.kconfig._make_and(node.dep, expr)
        else:
            node.dep = self.kconfig.y

    def parse_macro(self, s: str, loc: int, parsed_macro: ParseResults) -> None:
        name = parsed_macro["name"]
        op = parsed_macro["operation"]
        val = parsed_macro["value"]
        if name in self.kconfig.variables:  # Already seen variable
            var = self.kconfig.variables[name]
        else:
            # New variable
            var = Variable()
            var.kconfig = self.kconfig
            var.name = name
            var._n_expansions = 0

            self.kconfig.variables[name] = var

        # legacy; in order to make everything work, we need to set the value to the is_recursive flag
        # Difference between "=" and ":=" is that in original kconfiglib, ":=" is expanded immediately,
        # while "=" is expanded when used. However, we currently support only simple NAME = VALUE macros,
        # where there is no difference between the two (literal is always expanded to itself).
        if op == "=":
            var.is_recursive = True
        elif op == ":=":
            var.is_recursive = False

        if isinstance(val, Symbol):
            val = val.name

        var.value = self.kconfig._expand_whole(val, ())

    def parse_prompt(self, node: MenuNode, prompts: List[Tuple]) -> None:
        for prompt in prompts:
            if node.prompt:
                self.kconfig._warn(node.item.name_and_loc + " defined with multiple prompts in single location")  # type: ignore
            prompt_str = prompt[0]

            if prompt_str != prompt_str.strip():
                self.kconfig._warn(node.item.name_and_loc + " has leading or trailing whitespace in its prompt")  # type: ignore
                prompt_str = prompt_str.strip()

            condition: Union["Symbol", str, Tuple] = self.kconfig.y
            if prompt[1]:
                condition = self.parse_expression(prompt[1])
            node.prompt = (prompt_str, condition)

    def parse_if_entry(self, s: str, loc: int, located_if_entry: ParseResults) -> None:
        self.kconfig.linenr = lineno(loc, s)
        parsed_if_entry = located_if_entry
        expression = self.parse_expression(parsed_if_entry[0])

        node = MenuNode(kconfig=self.kconfig, item=None)
        node.dep = expression  # type: ignore

        self.get_children(node, (self.file_stack[-1], lineno(loc, s)))
        orphan = Orphan(
            node=node,
            locations=[location for location in self.location_stack if self.location_stack]
            + [(self.file_stack[-1], lineno(loc, s))],
        )
        self.orphans.append(orphan)

    def parse_expression(self, expr: list) -> Union[str, tuple, Symbol]:
        expr = expr[0] if len(expr) == 1 else expr
        prefix_expr = self.infix_to_prefix(expr)
        kconfigized_expr: Union[str, tuple, Symbol] = self.kconfigize_expr(prefix_expr)  # type: ignore
        return kconfigized_expr

    def parse_options(self, node: MenuNode, parsed_config: ParseResults) -> None:
        #####################
        # _parse_props() functionality
        #####################
        if node.item.__class__ not in (Symbol, Choice):
            raise RuntimeError("Attempted to parse options for MenuNode item which is neither Symbol nor Choice.")

        config_options = parsed_config.config_opts
        if not config_options:  # choice can have no options
            return

        # set type (and optional prompt)
        if config_options["type"]:
            self.kconfig._set_type(node.item, self.str_to_kconfig_type[config_options["type"]])
        else:
            if node.item.__class__ != Choice:  # Choices can have implicit type by their first child
                raise ValueError(
                    f"Config {parsed_config[1]}, defined in {self.file_stack[-1]}:{node.linenr} has no type."
                )

        # parse default
        if config_options["default"]:
            for default in config_options["default"]:
                # cannot use list() as an argument, because list("abc") is ["a", "b", "c"], not ["abc"]
                value = self.parse_expression(default[0])
                if len(default) > 1 and default[1]:
                    expr = self.parse_expression(default[1])
                    node.defaults.append((value, expr))
                else:
                    node.defaults.append((value, self.kconfig.y))

        # set help
        # NOTE: some special characters may not be supported.
        if config_options["help"]:
            node.help = config_options["help"]

        # set depends_on
        node.dep = self.kconfig.y  # basic dependency is always true
        if config_options["depends_on"]:
            for depend in config_options["depends_on"]:
                expr = self.parse_expression(depend)
                node.dep = self.kconfig._make_and(node.dep, expr)

        # NOTE: mypy does not recognize __class__ is <class> checks, thus many # type: ignore[union-attr]
        #       rather than to sacrifice speed in favor of mypy.
        # parse select
        if config_options["select"]:
            if node.item.__class__ is Symbol and node.item.orig_type == BOOL:  # type: ignore[union-attr]
                for select in config_options["select"]:
                    target_sym = self.kconfigize_expr(select[0])
                    if len(select) > 1 and select[1]:
                        expr = self.parse_expression(select[1])
                        node.selects.append((target_sym, expr))
                    else:
                        node.selects.append((target_sym, self.kconfig.y))
            else:
                self.kconfig._warn(
                    (
                        f"{node.item.name} of type {TYPE_TO_STR[node.item.orig_type]} "  # type: ignore[union-attr]
                        f"(defined at {self.file_stack[-1]}:{node.linenr}) "
                        "has 'select' option, which is only supported for boolean symbols. Option ignored."
                    )
                )

        # parse imply
        if config_options["imply"]:
            if node.item.__class__ is Symbol and node.item.orig_type == BOOL:  # type: ignore[union-attr]
                for imply in config_options["imply"]:
                    target_sym = self.kconfigize_expr(imply[0])
                    if len(imply) > 1 and imply[1]:
                        expr = self.infix_to_prefix(imply[1])
                        node.implies.append((target_sym, expr))
                    else:
                        node.implies.append((target_sym, self.kconfig.y))
            else:
                self.kconfig._warn(
                    (
                        f"{node.item.name} of type {TYPE_TO_STR[node.item.orig_type]} "  # type: ignore[union-attr]
                        f"(defined at {self.file_stack[-1]}:{node.linenr}) "
                        "has 'imply' option, which is only supported for boolean symbols. Option ignored."
                    )
                )

        # parse prompt
        if config_options["prompt"]:
            self.parse_prompt(node, config_options["prompt"])

        # parse range
        if config_options["range"]:
            for range_entry in config_options["range"]:
                if len(range_entry) not in (2, 3):
                    raise ValueError("Range must have two values and optional condition")
                condition: Union["Symbol", Tuple, str] = self.kconfig.y
                if len(range_entry) == 3 and range_entry[2]:
                    condition = self.parse_expression(range_entry[2])
                sym0 = self.kconfigize_expr(range_entry[0])
                sym1 = self.kconfigize_expr(range_entry[1])
                node.ranges.append((sym0, sym1, condition))

        # parse set default (weak indirect value setting)
        if config_options["weak_set"]:
            if node.item.__class__ is Symbol and node.item.orig_type == BOOL:  # type: ignore[union-attr]
                for set_entry in config_options["weak_set"]:
                    target_sym = self.kconfigize_expr(set_entry[0])
                    val = self.kconfigize_expr(set_entry[1])
                    cond = self.kconfig.y if set_entry[2] is None else self.parse_expression(set_entry[2])
                    node.weak_sets.append((target_sym, val, cond))
            else:
                self.kconfig._warn(
                    (
                        f"{node.item.name} of type {TYPE_TO_STR[node.item.orig_type]} "  # type: ignore[union-attr]
                        f"(defined at {self.file_stack[-1]}:{node.linenr}) "
                        "has 'set default' option, which is only supported for boolean symbols. Option ignored."
                    )
                )

        # parse set (indirect value setting)
        if config_options["set"]:
            if node.item.__class__ is Symbol and node.item.orig_type == BOOL:  # type: ignore[union-attr]
                for set_entry in config_options["set"]:
                    target_sym = self.kconfigize_expr(set_entry[0])
                    val = self.kconfigize_expr(set_entry[1])
                    cond = self.kconfig.y if set_entry[2] is None else self.parse_expression(set_entry[2])
                    node.sets.append((target_sym, val, cond))
            else:
                self.kconfig._warn(
                    (
                        f"{node.item.name} of type {TYPE_TO_STR[node.item.orig_type]} "  # type: ignore[union-attr]
                        f"(defined at {self.file_stack[-1]}:{node.linenr}) "
                        "has 'set' option, which is only supported for boolean symbols. Option ignored."
                    )
                )

        # parse option
        if config_options["option"]:
            env_var = config_options["option"][0]
            node.item.env_var = env_var  # type: ignore
            if env_var in os.environ:
                sym_name = os.environ.get(env_var) or ""
                node.defaults.append((self.kconfig._lookup_const_sym(sym_name), self.kconfig.y))
            else:
                self.kconfig._warn(
                    f"{node.item.name} has 'option env=\"{env_var}\"', "  # type: ignore
                    f"but the environment variable {env_var} is not set",
                    self.file_stack[-1],
                    node.linenr,
                )

    # mypy cannot recognize "if parsed_expr.__class__" as handling certain types complains in the rest of the function
    @no_type_check
    def infix_to_prefix(self, parsed_expr: Union[str, list, Symbol]) -> Union[str, tuple, Symbol]:
        """
        Converts a nested list of operands and operators from infix to prefix notation, because Kconfig uses it.
        """
        if parsed_expr.__class__ in (str, Symbol):
            return parsed_expr
        else:
            if parsed_expr[0] == "!":  # negation; !EXPRESSION
                return ("!", self.infix_to_prefix(parsed_expr[1]))
            elif len(parsed_expr) == 3:  # binary operation; OPERAND OPERATOR OPERAND
                return (parsed_expr[1], self.infix_to_prefix(parsed_expr[0]), self.infix_to_prefix(parsed_expr[2]))
            elif (
                len(parsed_expr) % 2 == 1 and len(parsed_expr) > 1
            ):  # multiple operators; OPERAND OPERATOR OPERAND OPERATOR OPERAND ...
                return (parsed_expr[1], self.infix_to_prefix(parsed_expr[0]), self.infix_to_prefix(parsed_expr[2:]))
            elif len(parsed_expr) == 1:  # single operand
                return self.infix_to_prefix(parsed_expr[0])
            else:
                raise ValueError(f"{self.file_stack[-1]}: Malformed expression {parsed_expr}")

    def create_envvar(self, name: str) -> "Symbol":
        """
        Creates an environment variable from a string
        """
        if name in os.environ:
            self.kconfig.env_vars.add(name)
            value = os.environ.get(name) or ""
            env_var_sym = self.kconfig._lookup_const_sym(value)
        else:
            # If the given name is not in the environment variables, we set the value
            # to the name itself (e.g. "${ENVAR_NAME}")
            env_var_sym = self.kconfig._lookup_const_sym(f"${{{name}}}")  # will expand to ${ENVAR_NAME}
        return env_var_sym

    def kconfigize_expr(self, expr: Union[str, tuple, list]) -> Union[str, tuple, "Symbol", int]:
        """
        Converts a string or a list of operands and operators to the corresponding Kconfig symbols and operators.
        """

        def is_dec_hex(s: str) -> bool:
            if not s:
                return False
            if s.isnumeric():
                return True
            if s[0] == "-":
                s = s[1:]
                for c in s:
                    if not c.isdigit():
                        return False
                return True
            elif s[0:2] in ["0x", "0X"]:
                s = s[2:]
                for c in s:
                    if c not in "0123456789abcdefABCDEF":
                        return False
                return True
            else:
                return False

        operators = ("&&", "||", "!", "=", "!=", "<", "<=", ">", ">=")
        if isinstance(expr, str):
            if expr in operators:
                return self.kconfigize_operator[expr]
            # $(NAME) first tries to expand as a macro, then as an environment variable,
            # ${NAME} only as environment variable.
            # Also their quoted versions, e.g. "$(NAME)", "${NAME}" are allowed.
            # This really matters only with "$(NAME)" because macro can be an int. Others are strings by default.
            elif expr.startswith(('"$', "'$", "$")):  # environment variable or macro to expand
                quoted = False
                # remove quotes and $, then decide what to do based on brackets
                if expr.startswith(('"$', "'$")):
                    expr = expr[2:-1]  # remove "$ and trailing "
                    quoted = True
                else:
                    expr = expr[1:]  # remove only $
                if expr.startswith("(") and expr.endswith(
                    ")"
                ):  # first try to expand as a macro, then as an environment variable, then cause error
                    expr = expr[1:-1]
                    if self.kconfig.variables.get(expr):
                        return self.kconfigize_expr(
                            f'"{self.kconfig.variables[expr].value}"' if quoted else self.kconfig.variables[expr].value
                        )
                    elif expr in os.environ:
                        return self.create_envvar(expr)
                    elif quoted:
                        return self.kconfigize_expr(
                            ""
                        )  # macros failed to expand even as environment variable are substituted with empty string
                    else:
                        raise KconfigError(f"{expr}: macro expanded to blank string")
                else:  # name in {} or without brackets at all (only for environment variables)
                    expr = expr[1:-1] if expr.startswith("{") and expr.endswith("}") else expr
                    return self.create_envvar(expr)

            else:  # symbol
                if expr in ("n", "'n'", '"n"'):
                    return self.kconfig.n
                elif expr in ("y", "'y'", '"y"'):
                    return self.kconfig.y
                else:
                    if (expr.startswith(("'", '"')) or not expr.isupper()) and not is_dec_hex(expr):
                        sym = self.kconfig._lookup_const_sym(expr[1:-1] if expr.startswith(("'", '"')) else expr)
                    else:
                        sym = self.kconfig._lookup_sym(expr)
                    return sym
        elif expr.__class__ in (tuple, list):
            if expr[0] in operators:
                if len(expr) == 3:  # expr operator expr
                    return (
                        self.kconfigize_operator[expr[0]],
                        self.kconfigize_expr(expr[1]),
                        self.kconfigize_expr(expr[2]),
                    )
                else:  # negation, ! variable
                    return (self.kconfigize_operator[expr[0]], self.kconfigize_expr(expr[1]))
            else:
                raise ValueError(f"Invalid operator {expr[0]}")
        else:
            raise ValueError(f"Invalid expression, was {type(expr)}, expected tuple or string.")

    """
    Converts a string operator to the corresponding Kconfig operator.
    NOTE: kconfig uses _T_<NAME> constants (tokens) for operators, here, we are using standard constants
    because it makes no sense to use tokens here.
    """
    kconfigize_operator = {
        "&&": AND,
        "||": OR,
        "!": NOT,
        "=": EQUAL,
        "!=": UNEQUAL,
        "<": LESS,
        "<=": LESS_EQUAL,
        ">": GREATER,
        ">=": GREATER_EQUAL,
    }

    # NOTE: in the future, make e.g. "constants.py" file and move the constants form core and parser there
    str_to_kconfig_type = {
        "bool": BOOL,
        "string": STRING,
        "int": INT,
        "hex": HEX,
    }
