# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Menuconfig state and logic, decoupled from any UI framework.

``MenuConfigState`` holds the shared navigation/editing state consumed by the
Textual UI layer (``app.py``, ``widgets.py``).
"""

from __future__ import annotations

import errno
import os
import re
import typing
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from enum import auto
from typing import TYPE_CHECKING
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

from esp_kconfiglib.core import BOOL_TO_STR
from esp_kconfiglib.core import FLOAT
from esp_kconfiglib.core import HEX
from esp_kconfiglib.core import INT
from esp_kconfiglib.core import MENU
from esp_kconfiglib.core import STRING
from esp_kconfiglib.core import Choice
from esp_kconfiglib.core import MenuNode
from esp_kconfiglib.core import Symbol
from esp_kconfiglib.core import _recursively_perform_action
from esp_kconfiglib.core import _restore_default
from esp_kconfiglib.core import expr_value

from .formatting import _is_y_mode_choice_sym
from .formatting import check_valid as _fmt_check_valid

if TYPE_CHECKING:
    from esp_kconfiglib import Kconfig


class ChangeResult(Enum):
    NO_CHANGE = auto()
    TOGGLED = auto()
    NEEDS_INPUT = auto()
    NEEDS_WARNING = auto()
    LEFT_MENU = auto()


@dataclass
class MenuConfigState:
    kconf: Kconfig
    conf_filename: str
    minconf_filename: str
    conf_changed: bool

    show_all: bool = False
    show_help: bool = False
    show_name: bool = False
    write_deprecated: bool = False

    cur_menu: MenuNode = field(init=False)
    shown: List[MenuNode] = field(default_factory=list, init=False)
    sel_node_i: int = field(default=0, init=False)

    _sorted_sc_cache: List[MenuNode] = field(default_factory=list, init=False, repr=False)
    _sorted_mc_cache: List[MenuNode] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self.cur_menu = self.kconf.top_node
        self.shown = self.shown_nodes(self.cur_menu)

    # --- Visibility / node enumeration ---

    def shown_nodes(self, menu: MenuNode) -> List[MenuNode]:
        def rec(node: Optional[MenuNode]) -> List[MenuNode]:
            if not node:
                return []
            res = []
            while node:
                if self._visible(node) or self.show_all:
                    res.append(node)
                    if node.list and not node.is_menuconfig:
                        res += rec(node.list)
                elif node.list and isinstance(node.item, Symbol):
                    shown_children = rec(node.list)
                    if shown_children:
                        res.append(node)
                        if not node.is_menuconfig:
                            res += shown_children
                node = node.next
            return res

        if isinstance(menu.item, Choice):
            seen_syms = {node.item for node in rec(menu.list) if isinstance(node.item, Symbol)}
            res = []
            for choice_node in menu.item.nodes:
                for node in rec(choice_node.list):
                    if node.item not in seen_syms or choice_node is menu:
                        res.append(node)
                        if isinstance(node.item, Symbol):
                            seen_syms.add(node.item)
            return res

        return rec(menu.list)

    def has_visible_child(self, menu: MenuNode) -> bool:
        """Return True if *menu* has at least one visible child (short-circuits)."""
        node = menu.list
        while node:
            if self._visible(node) or self.show_all:
                return True
            if node.list and isinstance(node.item, Symbol):
                if self.has_visible_child(node):
                    return True
            node = node.next
        return False

    @typing.no_type_check
    def _visible(self, node: MenuNode) -> bool:
        return (
            node.prompt and expr_value(node.prompt[1]) and not (node.item == MENU and not expr_value(node.visibility))
        )

    @property
    def selected_node(self) -> MenuNode:
        return self.shown[self.sel_node_i]

    # --- Navigation ---

    def enter_menu(self, node: MenuNode) -> bool:
        if not node.is_menuconfig:
            return False

        shown_sub = self.shown_nodes(node)
        if not shown_sub:
            return False

        self.cur_menu = node
        self.shown = shown_sub
        self.sel_node_i = 0

        if isinstance(node.item, Choice):
            self._select_selected_choice_sym()

        return True

    def _select_selected_choice_sym(self) -> None:
        choice = self.cur_menu.item
        if not isinstance(choice, Choice):
            return
        if choice.selection:
            for node in choice.selection.nodes:
                if node in self.shown:
                    self.sel_node_i = self.shown.index(node)
                    return

    def leave_menu(self) -> bool:
        if self.cur_menu is self.kconf.top_node:
            return False

        parent = self._parent_menu(self.cur_menu)
        if not parent:
            parent = self.kconf.top_node
        self.shown = self.shown_nodes(parent)
        self.sel_node_i = self.shown.index(self.cur_menu)
        self.cur_menu = parent

        return True

    def jump_to(self, node: MenuNode) -> None:
        old_show_all = self.show_all
        jump_into = (isinstance(node.item, Choice) or node.item == MENU) and node.list

        if jump_into:
            self.cur_menu = node
            node = node.list  # type: ignore
        else:
            parent = self._parent_menu(node)
            if parent:
                self.cur_menu = parent
            else:
                self.cur_menu = self.kconf.top_node

        self.shown = self.shown_nodes(self.cur_menu)
        if node not in self.shown:
            self.show_all = True
            self.shown = self.shown_nodes(self.cur_menu)

        self.sel_node_i = self.shown.index(node)

        if jump_into and not old_show_all and self.show_all:
            self.toggle_show_all()

        if jump_into and isinstance(self.cur_menu.item, Choice):
            self._select_selected_choice_sym()

    # --- Value modification ---

    def change_node(self, node: MenuNode) -> ChangeResult:
        if not self.changeable(node):
            return ChangeResult.NO_CHANGE

        sc = node.item

        if not isinstance(sc, (Symbol, Choice)):
            return ChangeResult.NO_CHANGE

        if isinstance(sc, Symbol) and sc.warning and not sc.choice and sc.has_active_default_value():
            return ChangeResult.NEEDS_WARNING

        return self._perform_toggle(sc, node)

    def force_change_node(self, node: MenuNode) -> ChangeResult:
        sc = node.item
        if not isinstance(sc, (Symbol, Choice)):
            return ChangeResult.NO_CHANGE

        return self._perform_toggle(sc, node)

    def _perform_toggle(self, sc: Union[Symbol, Choice], node: MenuNode) -> ChangeResult:
        if sc.orig_type in (INT, HEX, STRING, FLOAT):
            return ChangeResult.NEEDS_INPUT

        if len(sc.assignable) == 1:
            self._set_val(sc, sc.assignable[0])
        else:
            val_index = sc.assignable.index(sc.bool_value)
            self._set_val(sc, sc.assignable[(val_index + 1) % len(sc.assignable)])

        if _is_y_mode_choice_sym(sc) and not node.list:
            self.leave_menu()
            return ChangeResult.LEFT_MENU

        return ChangeResult.TOGGLED

    def changeable(self, node: MenuNode) -> bool:
        sc = node.item

        if not isinstance(sc, (Symbol, Choice)):
            return False

        if not (node.prompt and expr_value(node.prompt[1])):
            return False

        if isinstance(sc, Symbol) and sc.orig_type in (STRING, INT, HEX, FLOAT):
            return not sc._has_active_indirect_set

        return len(sc.assignable) > 1 or _is_y_mode_choice_sym(sc)

    def set_val(self, sc: Union[Symbol, Choice], val: Union[str, int]) -> None:
        self._set_val(sc, val)

    def _set_val(self, sc: Union[Symbol, Choice], val: Union[str, int]) -> None:
        if val in BOOL_TO_STR:
            val = BOOL_TO_STR[val]  # type: ignore

        if val != sc.str_value:
            sc.set_value(val)
            self.conf_changed = True
            self._update_menu()

    def set_sel_node_bool_val(self, bool_val: int) -> None:
        sc = self.shown[self.sel_node_i].item
        if isinstance(sc, (Symbol, Choice)) and bool_val in sc.assignable:
            self._set_val(sc, bool_val)

    def restore_default(self, node: MenuNode) -> None:
        _restore_default(node)
        self.conf_changed = True
        self._update_menu()

    def restore_defaults_recursive(self, node: MenuNode) -> None:
        _recursively_perform_action(node, _restore_default)
        self.conf_changed = True
        self._update_menu()

    def check_valid(self, sym: Symbol, s: str) -> Tuple[bool, Optional[str]]:
        return _fmt_check_valid(sym, s)

    # --- Display mode toggles ---

    def toggle_show_all(self) -> None:
        self.show_all = not self.show_all
        new_shown = self.shown_nodes(self.cur_menu)

        for node in self.shown[self.sel_node_i :: -1]:
            if node in new_shown:
                self.sel_node_i = new_shown.index(node)
                break
        else:
            for node in self.shown[self.sel_node_i + 1 :]:
                if node in new_shown:
                    self.sel_node_i = new_shown.index(node)
                    break
            else:
                self.show_all = True
                return

        self.shown = new_shown

    # --- Config file operations ---

    def needs_save(self) -> bool:
        if self.kconf.missing_syms:
            return True

        for sym in self.kconf.unique_defined_syms:
            if sym._sdkconfig_value is None:
                if sym.config_string:
                    return True
            elif sym.str_value != sym._sdkconfig_value:
                return True
            else:
                if not sym._loaded_as_default and sym.has_active_default_value():
                    return True
                elif sym._loaded_as_default and not sym.has_active_default_value():
                    return True

        return False

    def load_config(self) -> Tuple[bool, str]:
        msg = self.kconf.load_config()
        if not os.path.exists(self.conf_filename):
            return True, msg
        return self.needs_save(), msg

    def try_load(self, filename: str) -> Tuple[bool, Optional[str]]:
        try:
            self.kconf.load_config(filename, replace=False, is_main_sdkconfig=False)
            return True, None
        except EnvironmentError as e:
            msg = f"Error loading '{filename}'\n\n{e.strerror}"
            if e.errno:
                msg += f" (errno: {errno.errorcode[e.errno]})"
            return False, msg

    def reload_sdkconfig_file(self, filename: str) -> None:
        self.kconf.load_config(filename, replace=True, is_main_sdkconfig=True)

    # --- Menu path ---

    def menu_path(self) -> List[str]:
        from .formatting import menu_path_strs

        return menu_path_strs(self.cur_menu, self.kconf.top_node)

    # --- Search ---

    def search_nodes(self, query: str) -> Tuple[List[MenuNode], Optional[str]]:
        if not query.strip():
            return [], None

        try:
            regex_searches = [re.compile(regex).search for regex in query.lower().split()]
        except re.error as e:
            msg = "Bad regular expression"
            if hasattr(e, "msg"):
                msg += ": " + e.msg
            return [], msg

        matches = []  # type: List[MenuNode]

        for node in self._get_sorted_sc_nodes():
            sc = node.item
            if not isinstance(sc, (Symbol, Choice)):
                continue
            for search in regex_searches:
                if not (sc.name and search(sc.name.lower()) or node.prompt and search(node.prompt[0].lower())):
                    break
            else:
                matches.append(node)

        for node in self._get_sorted_menu_comment_nodes():
            for search in regex_searches:
                if not search(node.prompt[0].lower() if node.prompt else ""):
                    break
            else:
                matches.append(node)

        return matches, None

    def _get_sorted_sc_nodes(self) -> List[MenuNode]:
        if not self._sorted_sc_cache:
            for sym in sorted(self.kconf.unique_defined_syms, key=lambda s: s.name):
                self._sorted_sc_cache += sym.nodes
            choices = sorted(self.kconf.unique_choices, key=lambda c: c.name or "")
            self._sorted_sc_cache += sorted(
                [node for choice in choices for node in choice.nodes],
                key=lambda node: node.prompt[0] if node.prompt else "",
            )
        return self._sorted_sc_cache

    @typing.no_type_check
    def _get_sorted_menu_comment_nodes(self) -> List[MenuNode]:
        if not self._sorted_mc_cache:
            self._sorted_mc_cache += sorted(self.kconf.menus, key=lambda mc: mc.prompt[0])
            self._sorted_mc_cache += sorted(self.kconf.comments, key=lambda mc: mc.prompt[0])
        return self._sorted_mc_cache

    # --- Internal ---

    def _update_menu(self) -> None:
        sel_node = self.shown[self.sel_node_i]
        self.shown = self.shown_nodes(self.cur_menu)
        self.sel_node_i = self.shown.index(sel_node)

    @staticmethod
    def _parent_menu(node: MenuNode) -> Optional[MenuNode]:
        menu = node.parent
        while menu and not menu.is_menuconfig and menu.parent:
            menu = menu.parent
        return menu
