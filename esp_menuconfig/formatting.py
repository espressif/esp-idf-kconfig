# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Pure display functions for converting Kconfig objects to formatted strings.

These functions are stateless and have no UI dependencies.
They can be tested in complete isolation.
"""

from __future__ import annotations

import textwrap
import typing
from typing import TYPE_CHECKING
from typing import Callable
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

from esp_kconfiglib.core import AND
from esp_kconfiglib.core import BOOL
from esp_kconfiglib.core import BOOL_TO_STR
from esp_kconfiglib.core import COMMENT
from esp_kconfiglib.core import FLOAT
from esp_kconfiglib.core import HEX
from esp_kconfiglib.core import INT
from esp_kconfiglib.core import MENU
from esp_kconfiglib.core import OR
from esp_kconfiglib.core import STR_TO_BOOL
from esp_kconfiglib.core import STRING
from esp_kconfiglib.core import TYPE_TO_STR
from esp_kconfiglib.core import Choice
from esp_kconfiglib.core import MenuNode
from esp_kconfiglib.core import Symbol
from esp_kconfiglib.core import expr_str
from esp_kconfiglib.core import expr_value
from esp_kconfiglib.core import is_float
from esp_kconfiglib.core import split_expr
from esp_kconfiglib.core import standard_sc_expr_str

if TYPE_CHECKING:
    from esp_kconfiglib import Kconfig

SUBMENU_INDENT = 4

_VAL_N = STR_TO_BOOL["n"]
_VAL_Y = STR_TO_BOOL["y"]

INFO_HELP_LINES = """
[ESC/q] Return to menu      [/] Jump to symbol
"""[1:-1].split("\n")

JUMP_TO_HELP_LINES = """
Type text to narrow the search. Regexes are supported (via Python's 're'
module). The up/down cursor keys step in the list. [Enter] jumps to the
selected symbol. [ESC] aborts the search. Type multiple space-separated
strings/regexes to find entries that match all of them. Type Ctrl-F to
view the help of the selected item without leaving the dialog.
"""[1:-1].split("\n")


def node_str(
    node: MenuNode,
    *,
    show_name: bool,
    has_visible_child_fn: Callable[[MenuNode], bool],
    kconf: Kconfig,
) -> str:
    indent = 0
    parent = node.parent
    while parent and not parent.is_menuconfig:
        indent += SUBMENU_INDENT
        parent = parent.parent

    s = "{:{}}".format(value_str(node), 3 + indent)

    if _should_show_name(node, show_name):
        if isinstance(node.item, Symbol):
            s += f" <{node.item.name}>"
        else:
            s += (
                " " + standard_sc_expr_str(node.item)
                if isinstance(node.item, (Choice))
                else node.prompt[0]
                if node.prompt
                else ""
            )

    if node.prompt:
        if node.item == COMMENT:
            s += f" *** {node.prompt[0]} ***"
        else:
            s += " " + node.prompt[0]

        if isinstance(node.item, Symbol):
            sym = node.item

            if _is_y_mode_choice_sym(sym):
                if sym.orig_type and sym.choice and sym.choice._user_selection is None and sym.choice.selection is sym:
                    s += " (default selection)"
            elif sym.has_active_default_value():
                s += " (default value)"

            for _, cond, source in sym.rev_values:
                if expr_value(cond):
                    s += f" (force-set by {source.name})"
                    break

    if isinstance(node.item, Choice) and node.item.bool_value == _VAL_Y:
        choice = node.item
        sym = choice.selection
        if sym:
            for sym_node in sym.nodes:
                if sym_node.parent is node and sym_node.prompt:
                    s += f" ({sym_node.prompt[0]})"
                    break
            else:
                for sym_node in sym.nodes:
                    if sym_node.prompt:
                        s += f" ({sym_node.prompt[0]})"
                        break

        if node.prompt and choice.orig_type and choice._user_selection is None:
            s += " (default value)"

    if node.is_menuconfig:
        s += "  --->" if has_visible_child_fn(node) else "  ----"

    return s


@typing.no_type_check  # mypy cannot infer the type of item and its checks
def value_str(node: MenuNode) -> str:
    item = node.item

    if item in (MENU, COMMENT):
        return ""

    if not item.orig_type:
        return ""

    if item.orig_type in (STRING, INT, HEX, FLOAT):
        return f"({item.str_value})"

    # BOOL
    if _is_y_mode_choice_sym(item):
        return "(X)" if item.choice.selection is item else "( )"

    bool_val_str = (" ", None, "*")[item.bool_value]

    if len(item.assignable) <= 1:
        return "" if isinstance(item, Choice) else f"-{bool_val_str}-"

    if item.type == BOOL:
        return f"[{bool_val_str}]"

    return f"<{bool_val_str}>"


@typing.no_type_check  # mypy cannot infer type of the return string
def info_str(node: MenuNode, kconf: Kconfig) -> str:
    if isinstance(node.item, Symbol):
        sym = node.item
        return (
            _name_info(sym)
            + _prompt_info(sym)
            + f"Type: {TYPE_TO_STR[sym.type]}\n"
            + _value_info(sym)
            + _warning_info(sym)
            + _help_info(sym)
            + _direct_dep_info(sym, kconf)
            + _defaults_info(sym, kconf)
            + _select_imply_info(sym, kconf)
            + _set_info(sym, kconf)
            + _kconfig_def_info(sym, kconf)
        )

    if isinstance(node.item, Choice):
        choice = node.item
        return (
            _name_info(choice)
            + _prompt_info(choice)
            + f"Type: {TYPE_TO_STR[choice.type]}\n"
            + f"Mode: {choice.str_value}\n"
            + _help_info(choice)
            + _choice_syms_info(choice)
            + _direct_dep_info(choice, kconf)
            + _defaults_info(choice, kconf)
            + _kconfig_def_info(choice, kconf)
        )

    return _kconfig_def_info(node, kconf)


def info_title(node: MenuNode) -> str:
    if isinstance(node.item, Symbol):
        return "Symbol information"
    if isinstance(node.item, Choice):
        return "Choice information"
    if node.item == MENU:
        return "Menu information"
    return "Comment information"


def range_info(sym: Symbol) -> Optional[str]:
    if sym.orig_type in (INT, HEX, FLOAT):
        for low, high, cond in sym.ranges:
            if expr_value(cond):
                return f"Range: from {low.str_value} to {high.str_value}"
    return None


def check_valid(sym: Symbol, s: str) -> Tuple[bool, Optional[str]]:
    if sym.orig_type not in (INT, HEX, FLOAT):
        return True, None

    if sym.orig_type == FLOAT:
        if not is_float(s):
            err = f"'{s}' is a malformed float value"
            if "," in s and "." not in s:
                err += "; use a decimal point ('.') not a comma"
            return False, err
        val = float(s)

        for low_sym, high_sym, cond in sym.ranges:
            if expr_value(cond):
                low_s = low_sym.str_value
                high_s = high_sym.str_value
                if not float(low_s) <= val <= float(high_s):
                    return False, f"{s} is outside the range {low_s} to {high_s}"
                break

        return True, None

    base = 10 if sym.orig_type == INT else 16
    try:
        int(s, base)
    except ValueError:
        return False, f"'{s}' is a malformed {TYPE_TO_STR[sym.orig_type]} value"

    for low_sym, high_sym, cond in sym.ranges:
        if expr_value(cond):
            low_s = low_sym.str_value
            high_s = high_sym.str_value
            if not int(low_s, base) <= int(s, base) <= int(high_s, base):
                return False, f"{s} is outside the range {low_s} to {high_s}"
            break

    return True, None


def menu_path_strs(cur_menu: MenuNode, top_node: MenuNode) -> List[str]:
    prompts = []
    menu = cur_menu
    while menu and menu is not top_node:
        prompts.append(
            menu.prompt[0]
            if menu.prompt
            else standard_sc_expr_str(menu.item)
            if isinstance(menu.item, (Symbol, Choice))
            else ""
        )
        menu = menu.parent  # type: ignore
    prompts.append("(Top)")
    prompts.reverse()
    return prompts


def load_save_info() -> str:
    import os

    return f"(Relative to {os.path.join(os.getcwd(), '')})" + "\n\nRefer to your home directory with ~"


def name_and_val_str(sc: Union[Symbol, Choice]) -> str:
    if isinstance(sc, Symbol) and not sc.is_constant and not _is_num(sc.name):
        if not sc.nodes:
            return f"{sc.name}(undefined/n)"
        return f"{sc.name}(={sc.str_value})"
    return standard_sc_expr_str(sc)


def jump_to_match_str(node: MenuNode) -> str:
    if isinstance(node.item, (Symbol, Choice)):
        s = name_and_val_str(node.item)
        if node.prompt:
            s += f' "{node.prompt[0]}"'
        return s
    if node.item == MENU:
        return f'menu "{node.prompt[0] if node.prompt else ""}"'
    return f'comment "{node.prompt[0] if node.prompt else ""}"'


# --- Private helpers ---


def _is_y_mode_choice_sym(item: Union[Symbol, Choice, int, None]) -> bool:
    return isinstance(item, Symbol) and bool(item.choice) and item.visibility == 2


def _should_show_name(node: MenuNode, show_name: bool) -> bool:
    return not node.prompt or (show_name and isinstance(node.item, (Symbol, Choice)))  # type: ignore


def _is_num(name: str) -> bool:
    try:
        int(name)
        return True
    except ValueError:
        pass

    if name.startswith(("0x", "0X")):
        try:
            int(name, 16)
            return True
        except ValueError:
            pass

    return is_float(name)


def _name_info(sc: Union[Symbol, Choice]) -> str:
    return f"Name: {sc.name}\n" if sc.name else ""


def _prompt_info(sc: Union[Symbol, Choice]) -> str:
    s = ""
    for node in sc.nodes:
        if node.prompt:
            s += f"Prompt: {node.prompt[0]}\n"
    return s


def _value_info(sym: Symbol) -> str:
    value = f"{sym.str_value}" if sym.orig_type == STRING else f"'{sym.str_value}'"
    return f"Value: {value}\n"


def _warning_info(sym: Symbol) -> str:
    return f"This symbol has a 'warning' with the following reason: {sym.warning}\n" if sym.warning else ""


def _help_info(sc: Union[Symbol, Choice]) -> str:
    s = "\n"
    for node in sc.nodes:
        if node.help is not None:
            s += f"Help:\n\n{textwrap.indent(node.help, '  ')}\n\n"
    return s


def _choice_syms_info(choice: Choice) -> str:
    s = "Choice symbols:\n"
    for sym in choice.syms:
        s += "  - " + sym.name
        if sym is choice.selection:
            s += " (selected)"
        s += "\n"
    return s + "\n"


@typing.no_type_check
def _direct_dep_info(sc: Union[Symbol, Choice], kconf: Kconfig) -> str:
    return (
        ""
        if sc.direct_dep is kconf.y
        else f"Direct dependencies (={BOOL_TO_STR[expr_value(sc.direct_dep)]}):\n{_split_expr_info(sc.direct_dep, 2)}\n"
    )


def _defaults_info(sc: Union[Symbol, Choice], kconf: Kconfig) -> str:
    if not sc.defaults:
        return ""

    s = "Default"
    if len(sc.defaults) > 1:
        s += "s"
    s += ":\n"
    if isinstance(sc, Symbol) and sc._default_value_injected:
        s += f"  - {sc.defaults[0][0].name} (injected default value from sdkconfig)\n"
    for val, cond in sc.orig_defaults:
        s += "  - "
        if isinstance(sc, Symbol):
            s += _expr_str(val)
            if isinstance(val, tuple):
                s += f"  (={BOOL_TO_STR[expr_value(val)]})"
        else:
            s += val.name
        s += "\n"

        if cond is not kconf.y:
            s += f"    Condition (={BOOL_TO_STR[expr_value(cond)]}):\n{_split_expr_info(cond, 4)}"

    return s + "\n"


def _split_expr_info(expr: Union[Symbol, Choice, Tuple], indent: int) -> str:
    if len(split_expr(expr, AND)) > 1:
        split_op = AND
        op_str = "&&"
    else:
        split_op = OR
        op_str = "||"

    s = ""
    for i, term in enumerate(split_expr(expr, split_op)):
        s += f"{indent * ' '}{'  ' if i == 0 else op_str} {_expr_str(term)}"
        if isinstance(term, tuple):
            s += f"  (={BOOL_TO_STR[expr_value(term)]})"
        s += "\n"

    return s


def _select_imply_info(sym: Symbol, kconf: Kconfig) -> str:
    def sis(expr: Union[Symbol, Choice, Tuple], val: int, title: str) -> str:
        sis_list = [si for si in split_expr(expr, OR) if expr_value(si) == val]
        if not sis_list:
            return ""
        res = title
        for si in sis_list:
            res += f"  - {split_expr(si, AND)[0].name}\n"
        return res + "\n"

    s = ""

    if sym.rev_dep is not kconf.n:
        s += sis(sym.rev_dep, _VAL_Y, "Symbols currently y-selecting this symbol:\n")
        s += sis(sym.rev_dep, _VAL_N, "Symbols currently n-selecting this symbol (no effect):\n")

    if sym.weak_rev_dep is not kconf.n:
        s += sis(sym.weak_rev_dep, _VAL_Y, "Symbols currently y-implying this symbol:\n")
        s += sis(sym.weak_rev_dep, _VAL_N, "Symbols currently n-implying this symbol (no effect):\n")

    return s


def _set_info(sym: Symbol, kconf: Kconfig) -> str:
    def cond_str(cond: Union[Symbol, Choice, Tuple]) -> str:
        return f"if {_expr_str(cond)}" if cond is not kconf.y else ""

    s: str = ""
    active_indirects = []
    inactive_indirects = []
    active_weak_indirects = []
    inactive_weak_indirects = []

    for val, cond, src in sym.rev_values:
        entry = f"- {val.name} {cond_str(cond)} (by symbol {src.name})\n"
        if expr_value(cond):
            active_indirects.append(entry)
        else:
            inactive_indirects.append(entry)

    for val, cond, src in sym.weak_rev_values:
        entry = f"- {val.name} {cond_str(cond)} (by symbol {src.name})\n"
        if expr_value(cond):
            active_weak_indirects.append(entry)
        else:
            inactive_weak_indirects.append(entry)

    if active_indirects:
        s += "Active indirectly set values for this symbol (via 'set' option):\n"
        s += "".join(active_indirects)
    if inactive_indirects:
        s += "Inactive indirectly set values for this symbol (via 'set' option):\n"
        s += "".join(inactive_indirects)
    if active_weak_indirects:
        s += "Active indirectly weak set values for this symbol (via 'set' option):\n"
        s += "".join(active_weak_indirects)
    if inactive_weak_indirects:
        s += "Inactive indirectly weak set values for this symbol (via 'set' option):\n"
        s += "".join(inactive_weak_indirects)

    return s + "\n" if s else ""


def _kconfig_def_info(item: Union[MenuNode, Symbol, Choice], kconf: Kconfig) -> str:
    nodes = [item] if isinstance(item, MenuNode) else item.nodes

    s = f"Kconfig definition{'s' if len(nodes) > 1 else ''}, with parent deps. propagated to 'depends on'\n"
    s += (len(s) - 1) * "="

    for node in nodes:
        s += (
            f"\n\nAt {node.filename}:{node.linenr}\n{_include_path_info(node)}"
            f"    Menu path: {_menu_path_info(node, kconf)}\n\n"
            f"{textwrap.indent(node.custom_str(name_and_val_str), '  ')}"
        )

    return s


def _include_path_info(node: MenuNode) -> str:
    if not node.include_path:
        return ""
    include_path = " -> ".join(f"{filename}:{linenr}" for filename, linenr in node.include_path)
    return f"Included via {include_path}\n"


def _menu_path_info(node: MenuNode, kconf: Kconfig) -> str:
    path = ""
    while node.parent is not kconf.top_node:
        node = node.parent if node.parent else kconf.top_node
        if isinstance(node.item, (Symbol, Choice)):
            path = " -> " + (node.prompt[0] if node.prompt else standard_sc_expr_str(node.item)) + path
        else:
            path = " -> " + (node.prompt[0] if node.prompt else "") + path
    return "(Top)" + path


def _expr_str(expr: Union[Symbol, Choice, Tuple]) -> str:
    return expr_str(expr, name_and_val_str)  # type: ignore
