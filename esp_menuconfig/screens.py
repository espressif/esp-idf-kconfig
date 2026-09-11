# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Dialog screens for menuconfig."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Callable
from typing import List
from typing import NamedTuple
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import Union

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.events import Key
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Footer
from textual.widgets import Input
from textual.widgets import Label
from textual.widgets import OptionList
from textual.widgets import Static
from textual.widgets import TextArea
from textual.widgets.option_list import Option

from esp_kconfiglib.constants import DefaultsPolicy

from .formatting import MISMATCH_COL_FIRST
from .formatting import MISMATCH_COL_NAME
from .formatting import MISMATCH_COL_SECOND
from .formatting import MISMATCH_DETAIL_HELP_LINES
from .formatting import MISMATCH_FOCUS_COLS
from .formatting import MISMATCH_SCREEN_HELP_TEXT
from .formatting import info_str
from .formatting import info_title
from .formatting import jump_to_match_str
from .formatting import mismatch_column_headers
from .formatting import mismatch_column_widths
from .formatting import mismatch_detail_column_headers
from .formatting import mismatch_detail_info
from .formatting import mismatch_detail_values
from .formatting import mismatch_divider
from .formatting import mismatch_format_row
from .formatting import mismatch_item_label
from .formatting import mismatch_policy_banner
from .formatting import mismatch_table_header
from .formatting import mismatch_value_label
from .formatting import mismatch_value_order

if TYPE_CHECKING:
    from esp_kconfiglib.core import Choice
    from esp_kconfiglib.core import MenuNode
    from esp_kconfiglib.core import Symbol

    from .model import MenuConfigState


class KeyDialogScreen(ModalScreen[Optional[str]]):
    """Modal dialog closed by pressing one of the allowed keys or clicking a button."""

    DEFAULT_CSS = """
    KeyDialogScreen {
        align: center middle;
        background: $background 60%;
    }
    #dialog-buttons {
        width: 100%;
        height: auto;
        align-horizontal: center;
        margin-top: 1;
    }
    #dialog-buttons Button {
        margin: 0 1;
    }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    _BUTTON_RE = re.compile(r"\((\w)\)(\w*)")

    def __init__(self, title: str, text: str, keys: str) -> None:
        super().__init__()
        self.dialog_title = title
        self.dialog_text = text
        self.allowed_keys = keys
        self._buttons: list[tuple[str, str]] = []
        self._body_text = self._parse_text(text)

    def _parse_text(self, text: str) -> str:
        lines = text.split("\n")
        last_line = lines[-1]
        matches = list(self._BUTTON_RE.finditer(last_line))
        if matches:
            for m in matches:
                key_char = m.group(1).lower()
                label = f"({m.group(1)}){m.group(2)}"
                self._buttons.append((key_char, label))
            return "\n".join(lines[:-1]).rstrip()
        return text

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.dialog_title, id="dialog-title")
            if self._body_text:
                yield Label(self._body_text, id="dialog-body", markup=False)
            with Horizontal(id="dialog-buttons"):
                for key_char, label in self._buttons:
                    yield Button(label, id=f"btn-{key_char}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        key_char = bid[len("btn-") :] if bid.startswith("btn-") else None
        if key_char and key_char in self.allowed_keys:
            self.dismiss(key_char)

    def on_key(self, event: Key) -> None:
        if event.key in ("left", "right"):
            buttons = self.query("Button")
            if buttons:
                focused = self.focused
                indices = list(range(len(buttons)))
                current = next((i for i, b in enumerate(buttons) if b is focused), -1)
                if event.key == "right":
                    nxt = indices[(current + 1) % len(indices)]
                else:
                    nxt = indices[(current - 1) % len(indices)]
                buttons[nxt].focus()
            event.prevent_default()
            event.stop()
            return
        key = event.character
        if key and key.lower() in self.allowed_keys:
            event.prevent_default()
            event.stop()
            self.dismiss(key.lower())

    def action_cancel(self) -> None:
        self.dismiss(None)


class InputScreen(ModalScreen[Optional[str]]):
    """Modal dialog with a text input field."""

    DEFAULT_CSS = """
    InputScreen {
        align: center middle;
        background: $background 60%;
    }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(
        self,
        title: str,
        initial_text: str,
        info_text: str | None = None,
        validator: Callable[[str], tuple[bool, str | None]] | None = None,
    ) -> None:
        super().__init__()
        self.dialog_title = title
        self.initial_text = initial_text
        self.info_text = info_text
        self.validator = validator

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.dialog_title, id="dialog-title", markup=False)
            if self.info_text:
                yield Label(self.info_text, id="dialog-info", markup=False)
            yield Input(value=self.initial_text, id="dialog-input")

    def on_mount(self) -> None:
        self.query_one("#dialog-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value
        if self.validator:
            valid, error = self.validator(value)
            if not valid:
                self.app.push_screen(InvalidValueScreen(error))
                return
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class InvalidValueScreen(ModalScreen[None]):
    """Modal shown when an entered value fails validation. Closes on any key."""

    DEFAULT_CSS = """
    InvalidValueScreen {
        align: center middle;
        background: $background 60%;
    }
    InvalidValueScreen #dialog-hint {
        margin-top: 1;
        text-style: italic;
    }
    """

    def __init__(self, error: Optional[str] = None) -> None:
        super().__init__()
        self.error = error or "Invalid value"

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Invalid value", id="dialog-title")
            yield Label(self.error, id="dialog-body", markup=False)
            yield Label("Press any key to continue.", id="dialog-hint")

    def on_key(self, event: Key) -> None:
        event.prevent_default()
        event.stop()
        self.dismiss(None)


class HelpPopupScreen(ModalScreen[None]):
    """Centered popup with a title and body text. Closed by any key."""

    DEFAULT_CSS = """
    HelpPopupScreen {
        align: center middle;
        background: $background 60%;
    }
    HelpPopupScreen #dialog-body {
        width: 100%;
        height: auto;
        text-wrap: wrap;
    }
    """

    def __init__(self, title: str, text: str) -> None:
        super().__init__()
        self.dialog_title = title
        self.dialog_text = text

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.dialog_title, id="dialog-title", markup=False)
            yield Label(self.dialog_text, id="dialog-body")

    def on_key(self, event: Key) -> None:
        event.prevent_default()
        event.stop()
        self.dismiss(None)


class SaveMinimalResult(NamedTuple):
    """Result of the minimal-config save dialog."""

    filename: str
    use_labels: bool


class SimpleCheckbox(Static):
    """A single-line checkbox without Textual's bordered toggle styling."""

    can_focus = True
    value = reactive(False)

    def __init__(self, label: str, *, value: bool = False, id: Optional[str] = None) -> None:
        super().__init__(id=id, markup=False)
        self.label = label
        self.value = value

    def render(self) -> str:
        mark = "x" if self.value else " "
        return f"[{mark}] {self.label}"

    def on_click(self) -> None:
        self.value = not self.value

    def on_key(self, event: Key) -> None:
        if event.key in ("space", "enter"):
            self.value = not self.value
            event.prevent_default()
            event.stop()


class SaveMinimalConfigScreen(ModalScreen[Optional[SaveMinimalResult]]):
    """Save dialog for the minimal config: filename plus a menu-labels toggle."""

    DEFAULT_CSS = """
    SaveMinimalConfigScreen {
        align: center middle;
        background: $background 60%;
    }
    SaveMinimalConfigScreen #save-min-filename-label {
        width: 100%;
    }
    SaveMinimalConfigScreen #checkbox-row {
        width: 100%;
        height: 1;
        margin-top: 1;
        align-horizontal: center;
    }
    SaveMinimalConfigScreen #labels-checkbox {
        width: auto;
        height: 1;
    }
    SaveMinimalConfigScreen #labels-checkbox:focus {
        color: $block-cursor-foreground;
        background: $block-cursor-background;
        text-style: $block-cursor-text-style;
    }
    SaveMinimalConfigScreen #dialog-buttons {
        width: 100%;
        height: auto;
        align-horizontal: center;
        margin-top: 1;
        border-top: solid $surface;
        padding-top: 1;
    }
    SaveMinimalConfigScreen #dialog-buttons Button {
        margin: 0 1;
    }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, default_filename: str, default_labels: bool) -> None:
        super().__init__()
        self.default_filename = default_filename
        self.default_labels = default_labels

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Save minimal configuration", id="dialog-title")
            yield Label("Filename:", id="save-min-filename-label")
            yield Input(value=self.default_filename, id="dialog-input")
            with Horizontal(id="checkbox-row"):
                yield SimpleCheckbox(
                    "Include menu labels",
                    value=self.default_labels,
                    id="labels-checkbox",
                )
            with Horizontal(id="dialog-buttons"):
                yield Button("Save", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        # Pre-select the whole path so it can be overwritten immediately.
        inp = self.query_one("#dialog-input", Input)
        inp.focus()
        inp.select_all()

    def _current_row(self) -> int:
        """
        Return the focused row index: 0=filename, 1=labels checkbox, 2=buttons.
        """
        focused = self.focused
        if focused is None:
            return 0
        if focused.id == "dialog-input":
            return 0
        if focused.id == "labels-checkbox":
            return 1
        if focused.id in ("btn-save", "btn-cancel"):
            return 2
        return 0

    def _focus_row(self, row: int) -> None:
        if row == 0:
            self.query_one("#dialog-input", Input).focus()
        elif row == 1:
            self.query_one("#labels-checkbox", SimpleCheckbox).focus()
        else:
            self.query_one("#btn-save", Button).focus()

    def on_key(self, event: Key) -> None:
        if event.key in ("up", "down"):
            row = self._current_row()
            row = (row + 1) % 3 if event.key == "down" else (row - 1) % 3
            self._focus_row(row)
            event.prevent_default()
            event.stop()
            return

        if event.key not in ("left", "right"):
            return

        focused = self.focused
        if focused is None or focused.id == "dialog-input":
            # Leave ←/→ to the Input cursor.
            return

        if focused.id == "labels-checkbox":
            # Right checks, left unchecks.
            self.query_one("#labels-checkbox", SimpleCheckbox).value = event.key == "right"
            event.prevent_default()
            event.stop()
            return

        if focused.id in ("btn-save", "btn-cancel"):
            buttons = list(self.query("#dialog-buttons Button"))
            if buttons:
                current = next((i for i, b in enumerate(buttons) if b is focused), 0)
                nxt = (current + 1) % len(buttons) if event.key == "right" else (current - 1) % len(buttons)
                buttons[nxt].focus()
            event.prevent_default()
            event.stop()

    def _submit(self) -> None:
        filename = self.query_one("#dialog-input", Input).value.strip()
        if not filename:
            self.app.push_screen(InvalidValueScreen("Filename must not be empty."))
            return
        use_labels = bool(self.query_one("#labels-checkbox", SimpleCheckbox).value)
        self.dismiss(SaveMinimalResult(filename, use_labels))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self._submit()
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class LoadScreen(ModalScreen[Optional[str]]):
    """Load dialog with filename input."""

    DEFAULT_CSS = """
    LoadScreen {
        align: center middle;
        background: $background 60%;
    }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, default_filename: str) -> None:
        super().__init__()
        self.default_filename = default_filename

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Load configuration from", id="dialog-title")
            yield Input(value=self.default_filename, id="dialog-input")

    def on_mount(self) -> None:
        self.query_one("#dialog-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


def _page(ol: OptionList, direction: int) -> None:
    """
    Scroll ``ol`` by a full page, keeping the highlight on the same row.

    ``OptionList.action_page_down``/``action_page_up`` move the highlight by a
    page but then scroll only the minimal distance needed to reveal it, which
    can leave the new highlight right at the edge of the view after just one
    line of scrolling. Scrolling the viewport by a full page first, then
    re-highlighting the option at the same row, matches the behavior of e.g.
    terminal pagers.
    """
    option_count = ol.option_count
    if not option_count:
        return
    page = ol.scrollable_content_region.height
    if page <= 0:
        return
    if option_count <= page:
        # Everything already fits in the view, so there is nothing to scroll:
        # jump to the start/end, like the equivalent Home/End move.
        ol.highlighted = 0 if direction < 0 else option_count - 1
        return
    scroll = int(ol.scroll_y)
    row = (ol.highlighted or 0) - scroll
    max_scroll = option_count - page
    new_scroll = min(max(scroll + direction * page, 0), max_scroll)
    ol.scroll_to(y=new_scroll, animate=False, immediate=True)
    ol.highlighted = min(max(new_scroll + row, 0), option_count - 1)


def _copy_via_system_tool(text: str) -> bool:
    """
    Copy text to the system clipboard using an OS-native helper.

    OSC 52 (the escape sequence written by ``App.copy_to_clipboard``) is
    not honoured by several common terminals (e.g. GNOME Terminal, xterm,
    Konsole with default settings), so we also try to shell out to a
    native clipboard tool.

    Returns True if a tool was available and exited cleanly.
    """
    candidates: List[List[str]] = []
    system = platform.system()
    if system == "Darwin":
        candidates.append(["pbcopy"])
    elif system == "Windows":
        candidates.append(["clip"])
    else:
        if os.environ.get("WAYLAND_DISPLAY"):
            candidates.append(["wl-copy"])
        candidates.append(["xclip", "-selection", "clipboard"])
        candidates.append(["xsel", "--clipboard", "--input"])

    for cmd in candidates:
        if shutil.which(cmd[0]) is None:
            continue
        try:
            subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                check=True,
                timeout=1,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
            continue
    return False


class InfoScreen(ModalScreen[None]):
    """Fullscreen information display for a symbol/choice/menu/comment."""

    DEFAULT_CSS = """
    InfoScreen {
        background: $surface;
    }
    InfoScreen #info-title {
        dock: top;
        height: 1;
        background: $accent;
        color: $text;
        text-style: bold;
    }
    InfoScreen #info-body {
        height: 1fr;
        border: thick $primary;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding(
            "escape,q,h,left,backspace",
            "dismiss_screen",
            "Return",
            show=True,
            priority=True,
            key_display="←",
        ),
        Binding("slash", "jump_to", "Search", show=True),
        Binding(
            "c",
            "copy_text",
            "Copy",
            show=True,
            priority=True,
            tooltip="Copy the selected text, or the whole info text if nothing is selected",
        ),
    ]

    def __init__(self, node: MenuNode, state: MenuConfigState, from_jump_to: bool = False) -> None:
        super().__init__()
        self.node = node
        self._state = state
        self.from_jump_to = from_jump_to

    def compose(self) -> ComposeResult:
        yield Static(info_title(self.node), id="info-title")
        yield TextArea(
            info_str(self.node, self._state.kconf),
            id="info-body",
            read_only=True,
            show_cursor=False,
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#info-body", TextArea).focus()

    def action_copy_text(self) -> None:
        body = self.query_one("#info-body", TextArea)
        text = body.selected_text or body.text
        if _copy_via_system_tool(text):
            self.notify(f"{'Selection' if body.selected_text else 'Info text'} copied to clipboard")
        else:
            self.app.copy_to_clipboard(text)
            self.notify(
                "Sent the text to your terminal's clipboard. If pasting doesn't work, "
                "install a clipboard helper (wl-copy, xclip, or xsel) and try again.",
                severity="warning",
            )

    def action_dismiss_screen(self) -> None:
        self.app.pop_screen()

    def action_jump_to(self) -> None:
        if self.from_jump_to:
            self.app.pop_screen()
            return
        self.app.push_screen(
            JumpToScreen(self._state),
            callback=self._handle_jump,
        )

    def _handle_jump(self, node: MenuNode | None) -> None:
        if node:
            self._state.jump_to(node)
            self.app.pop_screen()


class JumpToScreen(ModalScreen[Optional["MenuNode"]]):
    """Fullscreen search dialog using OptionList for results."""

    DEFAULT_CSS = """
    JumpToScreen {
        background: $surface;
        #search-input {
            dock: top;
        }
        #matches-list {
            height: 1fr;
            max-height: 100%;
        }
    }
    """

    BINDINGS = [
        Binding("enter", "jump", "Go to selected", show=True, priority=True),
        Binding("escape", "cancel", "Cancel", show=True, priority=True),
        Binding(
            "ctrl+f",
            "show_info",
            "Info",
            show=True,
            priority=True,
            tooltip="View the help of the selected item without leaving the search",
        ),
        Binding("pageup", "page_up", "Up by page", show=True, priority=True, key_display="PgUp"),
        Binding("pagedown", "page_down", "Down by page", show=True, priority=True, key_display="PgDn"),
        Binding("up", "cursor_up", "Up", show=True, priority=True),
        Binding("down", "cursor_down", "Down", show=True, priority=True),
    ]

    def __init__(self, state: MenuConfigState) -> None:
        super().__init__()
        self._state = state
        self._matches: list[MenuNode] = []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search symbols by substring or regex...", id="search-input")
        yield OptionList(id="matches-list")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._matches, error = self._state.search_nodes(event.value)
        optlist = self._matches_list()
        optlist.clear_options()
        if error:
            optlist.add_option(escape(error))
            return
        for node in self._matches:
            optlist.add_option(escape(jump_to_match_str(node)))
        if self._matches:
            optlist.highlighted = 0

    def _matches_list(self) -> OptionList:
        return self.query_one("#matches-list", OptionList)

    def _selected_node(self) -> Optional["MenuNode"]:
        optlist = self._matches_list()
        index = optlist.highlighted
        if not self._matches or type(index) is not int:
            return None
        return self._matches[index]

    def action_jump(self) -> None:
        node = self._selected_node()
        if node is not None:
            self.dismiss(node)

    def action_show_info(self) -> None:
        node = self._selected_node()
        if node is not None:
            self.app.push_screen(InfoScreen(node, self._state, from_jump_to=True))

    def action_cursor_down(self) -> None:
        self._matches_list().action_cursor_down()

    def action_cursor_up(self) -> None:
        self._matches_list().action_cursor_up()

    def action_page_down(self) -> None:
        _page(self._matches_list(), 1)

    def action_page_up(self) -> None:
        _page(self._matches_list(), -1)

    def action_cancel(self) -> None:
        self.dismiss(None)


@dataclass
class _MismatchEntry:
    item: Union["Symbol", "Choice"]
    name: str
    kconfig_value: str
    sdkconfig_value: str
    is_choice: bool = False
    resolution: Optional[str] = None
    # Resolution this row had when the screen was opened, so leaving the screen
    # only touches the configuration for rows the user actually changed.
    baseline: Optional[str] = None


class DefaultMismatchScreen(ModalScreen[None]):
    """Fullscreen list of symbols and choices with a default-value mismatch."""

    DEFAULT_CSS = """
    DefaultMismatchScreen {
        background: $surface;
    }
    DefaultMismatchScreen #mismatch-title {
        dock: top;
        height: 1;
        background: $accent;
        color: $text;
        text-style: bold;
    }
    DefaultMismatchScreen #mismatch-policy {
        dock: top;
        height: auto;
        color: $text-muted;
    }
    DefaultMismatchScreen #mismatch-list {
        height: 1fr;
        max-height: 100%;
    }
    """

    BINDINGS = [
        Binding(
            "left",
            "col_left",
            "Move left",
            show=True,
            priority=True,
            key_display="←",
            tooltip="Focus name, current value, or alternative value",
        ),
        Binding(
            "right",
            "col_right",
            "Move right",
            show=True,
            priority=True,
            key_display="→",
            tooltip="Focus name, current value, or alternative value",
        ),
        Binding(
            "enter",
            "apply_focused",
            "Apply/Enter details",
            show=True,
            priority=True,
            tooltip="Use the focused value, or open details on the name",
        ),
        Binding("k,K", "set_all_kconfig", "Set all to Kconfig", show=True, priority=True),
        Binding("s,S", "set_all_sdkconfig", "Set all to sdkconfig", show=True, priority=True),
        Binding("r,R", "unresolve", "Clear selection", show=True, priority=True),
        Binding("escape,backspace", "cancel", "Return", show=True, priority=True),
        Binding("h,H", "show_help", "Help", show=True, priority=True),
        Binding("pageup,pagedown", "noop", show=False, priority=True),
    ]

    def __init__(self, state: MenuConfigState) -> None:
        super().__init__()
        self._state = state
        self._entries: List[Optional[_MismatchEntry]] = []
        self._col_focus = MISMATCH_COL_NAME
        self._highlighted_i: Optional[int] = None
        self._name_width = 0
        self._first_width = 0
        self._second_width = 0
        self._resolution_width = 0
        self._policy = self._state.kconf.defaults_policy
        self._value_order = mismatch_value_order(self._policy)
        self._first_header, self._second_header = mismatch_column_headers(self._policy)

    def _ordered_values(self, kconfig_value: str, sdkconfig_value: str) -> Tuple[str, str]:
        """
        Reorder ``(kconfig_value, sdkconfig_value)`` into ``(first, second)`` column
        order per :attr:`_value_order`, so the current value is always shown first.
        """
        values = {"kconfig": kconfig_value, "sdkconfig": sdkconfig_value}
        first_source, second_source = self._value_order
        return values[first_source], values[second_source]

    def compose(self) -> ComposeResult:
        yield Static("Default value mismatches", id="mismatch-title")
        yield Static(mismatch_policy_banner(self._policy), id="mismatch-policy")
        yield OptionList(id="mismatch-list")
        yield Footer()

    def on_mount(self) -> None:
        self._populate()
        self._mismatch_list().focus()

    def _mismatch_list(self) -> OptionList:
        return self.query_one("#mismatch-list", OptionList)

    def _populate(self) -> None:
        symbols, choices = self._state.default_mismatches()
        optlist = self._mismatch_list()
        optlist.clear_options()
        self._entries = []
        self._highlighted_i = None
        self._col_focus = MISMATCH_COL_NAME

        symbol_rows = [
            (
                mismatch_item_label(sym),
                *self._ordered_values(
                    mismatch_value_label(sym, kconfig_value), mismatch_value_label(sym, sdkconfig_value)
                ),
            )
            for sym, kconfig_value, sdkconfig_value in symbols
        ]
        choice_rows = [
            (
                mismatch_item_label(choice),
                *self._ordered_values(
                    mismatch_value_label(choice, kconfig_value), mismatch_value_label(choice, sdkconfig_value)
                ),
            )
            for choice, kconfig_value, sdkconfig_value in choices
        ]
        (
            self._name_width,
            self._first_width,
            self._second_width,
            self._resolution_width,
        ) = mismatch_column_widths(symbol_rows + choice_rows, self._first_header, self._second_header)

        self._add_mismatch_section(
            optlist,
            "Config options",
            "Config name",
            symbols,
            is_choice=False,
        )
        optlist.add_option(
            Option(
                mismatch_divider(
                    self._first_header,
                    self._second_header,
                    self._name_width,
                    self._first_width,
                    self._second_width,
                    self._resolution_width,
                ),
                disabled=True,
            )
        )
        self._entries.append(None)
        self._add_mismatch_section(
            optlist,
            "Choices",
            "Choice name",
            choices,
            is_choice=True,
        )

        first_item = next((i for i, entry in enumerate(self._entries) if entry is not None), None)
        if first_item is not None:
            optlist.highlighted = first_item
            self._highlighted_i = first_item
            self._refresh_row(first_item)

    def _add_mismatch_section(
        self,
        optlist: OptionList,
        title: str,
        name_header: str,
        items: Sequence[Tuple[Union["Symbol", "Choice"], str, str]],
        *,
        is_choice: bool,
    ) -> None:
        optlist.add_option(Option(f"[b]{escape(title)}[/b]", disabled=True))
        self._entries.append(None)
        optlist.add_option(
            Option(
                mismatch_table_header(
                    name_header,
                    self._first_header,
                    self._second_header,
                    self._name_width,
                    self._first_width,
                    self._second_width,
                    self._resolution_width,
                ),
                disabled=True,
            )
        )
        self._entries.append(None)
        if items:
            for item, kconfig_value, sdkconfig_value in items:
                resolution = self._state.mismatch_resolution(item, kconfig_value, sdkconfig_value)
                entry = _MismatchEntry(
                    item,
                    mismatch_item_label(item),
                    kconfig_value,
                    sdkconfig_value,
                    is_choice=is_choice,
                    resolution=resolution,
                    baseline=resolution,
                )
                optlist.add_option(self._row_prompt(entry, None))
                self._entries.append(entry)
        else:
            optlist.add_option(Option("(none)", disabled=True))
            self._entries.append(None)

    def _row_prompt(self, entry: _MismatchEntry, focus_col: Optional[int]) -> str:
        first_value, second_value = self._ordered_values(
            mismatch_value_label(entry.item, entry.kconfig_value),
            mismatch_value_label(entry.item, entry.sdkconfig_value),
        )
        return mismatch_format_row(
            entry.name,
            first_value,
            second_value,
            self._name_width,
            self._first_width,
            self._second_width,
            self._resolution_width,
            policy=self._policy,
            resolution=entry.resolution,
            focus_col=focus_col,
        )

    def _refresh_row(self, index: int) -> None:
        if index < 0 or index >= len(self._entries):
            return
        entry = self._entries[index]
        if entry is None:
            return
        focus_col = self._col_focus if index == self._highlighted_i else None
        optlist = self._mismatch_list()
        optlist.replace_option_prompt_at_index(index, self._row_prompt(entry, focus_col))

    def _current_entry(self) -> Optional[_MismatchEntry]:
        optlist = self._mismatch_list()
        if optlist.highlighted is None or optlist.highlighted >= len(self._entries):
            return None
        return self._entries[optlist.highlighted]  # type: ignore

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        prev = self._highlighted_i
        self._highlighted_i = event.option_index
        if prev is not None and prev != self._highlighted_i:
            self._refresh_row(prev)
        if self._highlighted_i is not None:
            self._refresh_row(self._highlighted_i)

    def _apply_resolution(self, index: int, source: str) -> None:
        if index >= len(self._entries):
            return
        entry = self._entries[index]
        if entry is None:
            return
        entry.resolution = source
        self._refresh_row(index)

    def _clear_resolution(self, index: int) -> None:
        if index >= len(self._entries):
            return
        entry = self._entries[index]
        if entry is None or entry.resolution is None:
            return
        entry.resolution = None
        self._refresh_row(index)

    def action_unresolve(self) -> None:
        optlist = self._mismatch_list()
        index = optlist.highlighted
        entry = self._current_entry()
        if entry is not None and entry.resolution is not None and index is not None:
            self._clear_resolution(index)

    def _apply_all(self, source: str) -> None:
        for index, entry in enumerate(self._entries):
            if entry is not None:
                self._apply_resolution(index, source)

    def action_show_help(self) -> None:
        self.app.push_screen(HelpPopupScreen("Help", MISMATCH_SCREEN_HELP_TEXT))

    def action_set_all_kconfig(self) -> None:
        self._apply_all("kconfig")

    def action_set_all_sdkconfig(self) -> None:
        self._apply_all("sdkconfig")

    def action_noop(self) -> None:
        return

    def action_col_left(self) -> None:
        self._move_col(-1)

    def action_col_right(self) -> None:
        self._move_col(1)

    def _move_col(self, delta: int) -> None:
        if self._current_entry() is None:
            return
        self._col_focus = max(0, min(MISMATCH_FOCUS_COLS - 1, self._col_focus + delta))
        optlist = self._mismatch_list()
        if optlist.highlighted is not None:
            self._refresh_row(optlist.highlighted)

    def action_apply_focused(self) -> None:
        optlist = self._mismatch_list()
        index = optlist.highlighted
        entry = self._current_entry()
        if entry is None or index is None:
            return
        if self._col_focus == MISMATCH_COL_NAME:
            self._open_detail(index, entry)
        elif self._col_focus == MISMATCH_COL_FIRST:
            self._apply_resolution(index, self._value_order[0])
        elif self._col_focus == MISMATCH_COL_SECOND:
            self._apply_resolution(index, self._value_order[1])

    def _open_detail(self, index: int, entry: _MismatchEntry) -> None:
        location = ""
        if entry.item.nodes:
            node = entry.item.nodes[0]
            location = f"{node.filename}:{node.linenr}"
        first_value, second_value = self._ordered_values(
            mismatch_value_label(entry.item, entry.kconfig_value),
            mismatch_value_label(entry.item, entry.sdkconfig_value),
        )
        self.app.push_screen(
            MismatchDetailScreen(
                entry.name,
                location,
                first_value,
                second_value,
                self._policy,
                is_choice=entry.is_choice,
            ),
            callback=lambda source, i=index: self._on_detail_result(i, source),
        )

    def _on_detail_result(self, index: int, source: Optional[str]) -> None:
        if source is None:
            return
        self._apply_resolution(index, source)

    def _changed_entries(self) -> List[_MismatchEntry]:
        return [entry for entry in self._entries if entry is not None and entry.resolution != entry.baseline]

    def _commit(self) -> None:
        changed = self._changed_entries()
        for entry in changed:
            if entry.resolution is None:
                self._state.clear_mismatch_resolution(entry.item, update_menu=False)
            else:
                self._state.apply_mismatch_resolution(
                    entry.item,
                    entry.resolution,
                    entry.kconfig_value,
                    entry.sdkconfig_value,
                    update_menu=False,
                )
        if changed:
            self._state._update_menu()

    def action_cancel(self) -> None:
        if not self._changed_entries():
            self.dismiss(None)
            return
        self.app.push_screen(
            KeyDialogScreen(
                title="Return",
                text="Apply the selected values?\n\n(Y)es  (N)o  (C)ancel",
                keys="ync",
            ),
            callback=self._handle_return_response,
        )

    def _handle_return_response(self, key: Optional[str]) -> None:
        if key == "y":
            self._commit()
            self.dismiss(None)
        elif key == "n":
            self.dismiss(None)


class MismatchDetailScreen(ModalScreen[Optional[str]]):
    """Popup to inspect a mismatch and pick Kconfig or sdkconfig."""

    DEFAULT_CSS = """
    MismatchDetailScreen {
        align: center middle;
        background: $background 60%;
    }
    MismatchDetailScreen #dialog {
        width: 80;
        max-width: 90%;
        height: auto;
        min-height: 18;
        padding: 2 4;
    }
    MismatchDetailScreen #detail-info {
        height: auto;
    }
    MismatchDetailScreen #detail-values {
        height: 5;
        margin: 1 0;
        content-align: center middle;
        text-align: center;
    }
    MismatchDetailScreen #detail-help {
        margin-top: 1;
        text-style: italic;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding(
            "q,Q,s,S,o,O,d,D,f,F,c,C,a,A,r,R,p,P,m,M,slash,question_mark,backspace",
            "noop",
            show=False,
            priority=True,
        ),
    ]

    def action_noop(self) -> None:
        return

    def __init__(
        self,
        name: str,
        location: str,
        first_value: str,
        second_value: str,
        policy: DefaultsPolicy,
        *,
        is_choice: bool,
    ) -> None:
        super().__init__()
        self._item_name = name
        self._location = location
        self._first_value = first_value
        self._second_value = second_value
        self._first_header, self._second_header = mismatch_detail_column_headers(policy)
        self._value_order = mismatch_value_order(policy)
        self._is_choice = is_choice
        self._focus_col = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._info(), id="detail-info")
            yield Static("\n")
            yield Static("Select which value to apply:", id="detail-select-label")
            yield Static(self._values(), id="detail-values")
            yield Static("\n")
            yield Static(MISMATCH_DETAIL_HELP_LINES, id="detail-help", markup=False)

    def _info(self) -> str:
        return mismatch_detail_info(self._item_name, self._location, is_choice=self._is_choice)

    def _values(self) -> str:
        return mismatch_detail_values(
            self._first_value,
            self._second_value,
            self._focus_col,
            self._first_header,
            self._second_header,
        )

    def _redraw(self) -> None:
        self.query_one("#detail-values", Static).update(self._values())

    def on_key(self, event: Key) -> None:
        if event.key == "left":
            self._focus_col = 0
            self._redraw()
            event.prevent_default()
            event.stop()
        elif event.key == "right":
            self._focus_col = 1
            self._redraw()
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            self.dismiss(self._value_order[self._focus_col])
            event.prevent_default()
            event.stop()

    def action_cancel(self) -> None:
        self.dismiss(None)
