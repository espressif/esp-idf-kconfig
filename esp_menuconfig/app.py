# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Textual application for menuconfig."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from typing import Optional

from textual import on
from textual.app import App
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import OptionList
from textual.widgets import Static

from esp_kconfiglib.core import HEX
from esp_kconfiglib.core import MENU
from esp_kconfiglib.core import STRING
from esp_kconfiglib.core import TYPE_TO_STR
from esp_kconfiglib.core import Choice
from esp_kconfiglib.core import Symbol

from .formatting import range_info
from .model import ChangeResult
from .model import MenuConfigState
from .screens import InfoScreen
from .screens import InputScreen
from .screens import JumpToScreen
from .screens import KeyDialogScreen
from .screens import LoadScreen
from .screens import SaveScreen
from .widgets import MenuOptionList

if TYPE_CHECKING:
    from esp_kconfiglib.core import MenuNode


class MenuConfigApp(App[str]):
    """Main Textual application for menuconfig."""

    CSS = """
    #path-bar {
        dock: top;
        height: 1;
        background: $accent;
        color: $text;
        text-style: bold;
    }
    #mode-bar {
        dock: bottom;
        height: 1;
        background: $accent;
        color: $text;
    }
    #help-bar {
        dock: bottom;
        height: 4;
        padding: 0 1;
        display: none;
    }
    #dialog {
        width: 64;
        max-width: 90%;
        height: auto;
        border: thick $accent;
        padding: 1 2;
    }
    #dialog-title {
        text-style: bold;
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("q,Q", "quit_dialog", "Quit"),
        Binding("s,S", "save", "Save"),
        Binding("o,O", "load", "Load"),
        Binding("d,D", "save_minimal", "Save min"),
        Binding("slash", "jump_to", "Search"),
        Binding("question_mark", "show_info", "Info"),
        Binding("f,F", "toggle_help", "Help"),
        Binding("c,C", "toggle_name", "Name"),
        Binding("a,A", "toggle_all", "All"),
        Binding("r,R", "restore_default", "Reset"),
        Binding("p,P", "command_palette", "Palette"),
    ]

    def __init__(self, state: MenuConfigState, theme: Optional[str] = None) -> None:
        super().__init__()
        self.state = state
        if theme is not None:
            self.theme = theme

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="path-bar")
        yield MenuOptionList(id="menu-list")
        yield Static(id="mode-bar")
        yield Static(id="help-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.title = self.state.kconf.mainmenu_text
        self._refresh_menu()
        self.query_one("#menu-list", MenuOptionList).focus()

    # --- Actions ---

    def action_quit_dialog(self) -> None:
        if not self.state.needs_save():
            self.exit(f"No changes to save (for '{self.state.conf_filename}')")
            return
        self.push_screen(
            KeyDialogScreen(
                title="Quit",
                text="Save configuration?\n\n(Y)es  (N)o  (C)ancel",
                keys="ync",
            ),
            callback=self._handle_quit_response,
        )

    def _handle_quit_response(self, key: Optional[str]) -> None:
        if key == "y":
            msg = self._do_save(self.state.conf_filename)
            if msg:
                self.state.reload_sdkconfig_file(self.state.conf_filename)
                self.exit(msg)
        elif key == "n":
            self.exit(f"Configuration ({self.state.conf_filename}) was not saved")

    def action_save(self) -> None:
        msg = self._do_save(self.state.conf_filename)
        if msg:
            self.state.conf_changed = False
            self.state.reload_sdkconfig_file(self.state.conf_filename)
            self.notify(msg)

    def action_load(self) -> None:
        if self.state.conf_changed:
            self.push_screen(
                KeyDialogScreen(
                    title="Load",
                    text="You have unsaved changes. Load new\nconfiguration anyway?\n\n(O)K  (C)ancel",
                    keys="oc",
                ),
                callback=self._handle_load_confirm,
            )
        else:
            self._show_load_dialog()

    def _handle_load_confirm(self, key: Optional[str]) -> None:
        if key == "o":
            self._show_load_dialog()

    def _show_load_dialog(self) -> None:
        self.push_screen(
            LoadScreen(default_filename=self.state.conf_filename),
            callback=self._handle_load_result,
        )

    def _handle_load_result(self, filename: Optional[str]) -> None:
        if filename:
            filename = os.path.expanduser(filename)
            success, error = self.state.try_load(filename)
            if success:
                self.state.conf_changed = self.state.needs_save()
                if self.state.selected_node not in self.state.shown_nodes(self.state.cur_menu):
                    self.state.show_all = True
                self.state._update_menu()
                self._refresh_menu()
                self.notify(f"Loaded {filename}")
            else:
                self.notify(error or "Load failed", severity="error")

    def action_save_minimal(self) -> None:
        labels_env = os.environ.get("ESP_IDF_KCONFIG_MIN_LABELS")
        if labels_env is not None:
            self._do_save_minimal(labels_env == "1")
        else:
            self.push_screen(
                KeyDialogScreen(
                    title="Minimal configuration",
                    text=(
                        "Include menu section labels in sdkconfig.defaults?\n\n"
                        "When enabled, config options are grouped by the menus\n"
                        "they belong to, and menu names are included as comments.\n\n"
                        "(Y)es  (N)o  (C)ancel"
                    ),
                    keys="ync",
                ),
                callback=self._handle_min_labels_response,
            )

    def _handle_min_labels_response(self, key: Optional[str]) -> None:
        if key == "y":
            self._do_save_minimal(True)
        elif key == "n":
            self._do_save_minimal(False)

    def _do_save_minimal(self, use_labels: bool) -> None:
        desc = "minimal configuration (with menu labels)" if use_labels else "minimal configuration"
        self.push_screen(
            SaveScreen(default_filename=self.state.minconf_filename, description=desc),
            callback=lambda f: self._handle_save_minimal_result(f, use_labels),
        )

    def _handle_save_minimal_result(self, filename: Optional[str], use_labels: bool) -> None:
        if filename:
            from .idf_headers import idf_min_config_save_header

            try:
                self.state.kconf.write_min_config(
                    filename,
                    header=idf_min_config_save_header(self.state.kconf),
                    labels=use_labels,
                    normalize_unset=True,
                )
                self.state.minconf_filename = filename
                self.notify(f"Saved minimal config to {filename}")
            except EnvironmentError as e:
                self.notify(f"Error: {e}", severity="error")

    def action_jump_to(self) -> None:
        self.push_screen(JumpToScreen(self.state), callback=self._handle_jump_result)

    def _handle_jump_result(self, node: Optional["MenuNode"]) -> None:
        if node:
            self.state.jump_to(node)
            self._refresh_menu()

    def action_show_info(self) -> None:
        self._sync_sel_node_i()
        ml = self.query_one("#menu-list", MenuOptionList)
        node = ml.current_node
        if node:
            self.push_screen(InfoScreen(node, self.state))

    def action_toggle_help(self) -> None:
        self.state.show_help = not self.state.show_help
        self._refresh_help()

    def action_toggle_name(self) -> None:
        self.state.show_name = not self.state.show_name
        self._refresh_menu()

    def action_toggle_all(self) -> None:
        self._sync_sel_node_i()
        self.state.toggle_show_all()
        self._refresh_menu()

    def action_restore_default(self) -> None:
        self._sync_sel_node_i()
        ml = self.query_one("#menu-list", MenuOptionList)
        node = ml.current_node
        if not node:
            return
        if node.item == MENU:
            self.push_screen(
                KeyDialogScreen(
                    title="Restore defaults in menu?",
                    text=(
                        "Do you really want to restore the default values\nfor all symbols in this menu?\n\n(Y)es  (N)o"
                    ),
                    keys="yn",
                ),
                callback=lambda key: self._do_restore_menu(node) if key == "y" else None,
            )
        else:
            self.state.restore_default(node)
            self._refresh_menu()

    def _do_restore_menu(self, node: "MenuNode") -> None:
        self.state.restore_defaults_recursive(node)
        self._refresh_menu()

    # --- Message handlers from MenuOptionList ---

    @on(MenuOptionList.NodeSelected)
    def _on_node_selected(self, event: MenuOptionList.NodeSelected) -> None:
        self._sync_sel_node_i()
        node = event.node
        if not self.state.enter_menu(node):
            self._handle_change(node)
        else:
            self._refresh_menu()

    @on(MenuOptionList.NodeToggled)
    def _on_node_toggled(self, event: MenuOptionList.NodeToggled) -> None:
        self._sync_sel_node_i()
        node = event.node
        result = self.state.change_node(node)
        if result == ChangeResult.NO_CHANGE:
            if self.state.enter_menu(node):
                self._refresh_menu()
        elif result == ChangeResult.NEEDS_INPUT:
            self._show_input_dialog(node)
        elif result == ChangeResult.NEEDS_WARNING:
            self._show_warning_then_change(node)
        else:
            self._refresh_menu()

    @on(MenuOptionList.LeaveRequested)
    def _on_leave_requested(self, event: MenuOptionList.LeaveRequested) -> None:
        self._sync_sel_node_i()
        if self.state.cur_menu is self.state.kconf.top_node:
            return
        else:
            self.state.leave_menu()
            self._refresh_menu()

    @on(MenuOptionList.EscapePressed)
    def _on_escape_pressed(self, event: MenuOptionList.EscapePressed) -> None:
        self._sync_sel_node_i()
        if self.state.cur_menu is self.state.kconf.top_node:
            self.action_quit_dialog()
        else:
            self.state.leave_menu()
            self._refresh_menu()

    @on(OptionList.OptionHighlighted, "#menu-list")
    def _on_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        ml = self.query_one("#menu-list", MenuOptionList)
        idx = event.option_index
        node = ml._menu_nodes[idx] if idx < len(ml._menu_nodes) else None
        self._refresh_help(node)

    @on(MenuOptionList.BoolValueSet)
    def _on_bool_value_set(self, event: MenuOptionList.BoolValueSet) -> None:
        self._sync_sel_node_i()
        self.state.set_sel_node_bool_val(event.bool_val)
        self._refresh_menu()

    # --- Internal ---

    def _handle_change(self, node: "MenuNode") -> None:
        result = self.state.change_node(node)
        if result == ChangeResult.NEEDS_INPUT:
            self._show_input_dialog(node)
        elif result == ChangeResult.NEEDS_WARNING:
            self._show_warning_then_change(node)
        elif result != ChangeResult.NO_CHANGE:
            self._refresh_menu()

    def _show_input_dialog(self, node: "MenuNode") -> None:
        if not isinstance(node.item, Symbol):
            return

        sym: Symbol = node.item
        title = f"{node.prompt[0] if node.prompt else ''} ({TYPE_TO_STR[sym.orig_type]})"
        self.push_screen(
            InputScreen(
                title=title,
                initial_text=sym.str_value,
                info_text=range_info(sym),
                validator=lambda s, _sym=sym: self.state.check_valid(_sym, s),  # type: ignore
            ),
            callback=lambda val, _node=node: self._apply_input(_node, val),
        )

    def _apply_input(self, node: "MenuNode", val: Optional[str]) -> None:
        if val is None:
            return
        sym = node.item
        if not isinstance(sym, (Symbol, Choice)):
            return
        if sym.orig_type == HEX:
            val = val.strip()
            if not val.startswith(("0x", "0X")):
                val = "0x" + val
        elif sym.orig_type != STRING:
            val = val.strip()
        self.state.set_val(sym, val)
        self._refresh_menu()

    def _show_warning_then_change(self, node: "MenuNode") -> None:
        sym = node.item
        if not isinstance(sym, Symbol) or not sym.warning:
            return
        self.push_screen(
            KeyDialogScreen(
                title="Set dangerous option?",
                text=(
                    f"This symbol has a following warning:\n\n"
                    f"{sym.warning}\n\n"
                    f"Are you sure you want to change the value of this symbol?\n\n"
                    f"(Y)es  (N)o"
                ),
                keys="yn",
            ),
            callback=lambda key, _node=node: self._do_warned_change(_node) if key == "y" else None,
        )

    def _do_warned_change(self, node: "MenuNode") -> None:
        result = self.state.force_change_node(node)
        if result == ChangeResult.NEEDS_INPUT:
            self._show_input_dialog(node)
        else:
            self._refresh_menu()

    def _sync_sel_node_i(self) -> None:
        ml = self.query_one("#menu-list", MenuOptionList)
        node = ml.current_node
        if node and node in self.state.shown:
            self.state.sel_node_i = self.state.shown.index(node)

    def _refresh_menu(self) -> None:
        ml = self.query_one("#menu-list", MenuOptionList)
        ml.populate(self.state, restore_index=self.state.sel_node_i)

        path = self.state.menu_path()
        self.query_one("#path-bar", Static).update(" > ".join(path))

        self._refresh_modes()
        self._refresh_help()

    def _refresh_modes(self) -> None:
        modes = []
        if self.state.show_help:
            modes.append("show-help")
        if self.state.show_name:
            modes.append("show-name")
        if self.state.show_all:
            modes.append("show-all")
        bar = self.query_one("#mode-bar", Static)
        bar.update(" | ".join(modes) + " mode" if modes else "")

    def _refresh_help(self, node: Optional["MenuNode"] = None) -> None:
        help_bar = self.query_one("#help-bar", Static)
        if self.state.show_help:
            help_bar.display = True
            if node is None:
                ml = self.query_one("#menu-list", MenuOptionList)
                node = ml.current_node
            help_text = node.help if node else None
            help_bar.update(help_text or "(no help)")
        else:
            help_bar.display = False

    def _do_save(self, filepath: str) -> Optional[str]:
        from .idf_headers import idf_sdkconfig_header

        try:
            return self.state.kconf.write_config(
                filepath,
                header=idf_sdkconfig_header(),
                write_deprecated=False,
            )
        except EnvironmentError as e:
            self.notify(f"Error saving to '{filepath}': {e}", severity="error")
            return None
