# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Dialog screens for menuconfig."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from typing import Callable
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.screen import Screen
from textual.widgets import Button
from textual.widgets import Input
from textual.widgets import Label
from textual.widgets import OptionList
from textual.widgets import Static

from .formatting import JUMP_TO_HELP_LINES
from .formatting import info_str
from .formatting import info_title
from .formatting import jump_to_match_str

if TYPE_CHECKING:
    from esp_kconfiglib.core import MenuNode

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
                yield Label(self._body_text, id="dialog-body")
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
            yield Label(self.dialog_title, id="dialog-title")
            if self.info_text:
                yield Label(self.info_text, id="dialog-info")
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
            yield Label(self.error, id="dialog-body")
            yield Label("Press any key to continue.", id="dialog-hint")

    def on_key(self, event: Key) -> None:
        event.prevent_default()
        event.stop()
        self.dismiss(None)


class SaveScreen(ModalScreen[Optional[str]]):
    """Save dialog with filename input."""

    DEFAULT_CSS = """
    SaveScreen {
        align: center middle;
        background: $background 60%;
    }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, default_filename: str, description: str) -> None:
        super().__init__()
        self.default_filename = default_filename
        self.description = description

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Save {self.description} to", id="dialog-title")
            yield Input(value=self.default_filename, id="dialog-input")

    def on_mount(self) -> None:
        self.query_one("#dialog-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

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


class InfoScreen(Screen[None]):
    """Fullscreen information display for a symbol/choice/menu/comment."""

    DEFAULT_CSS = """
    InfoScreen #info-title {
        dock: top;
        height: 1;
        background: $accent;
        color: $text;
        text-style: bold;
    }
    InfoScreen #info-body {
        height: 1fr;
        overflow-y: auto;
        border: thick $primary;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("escape,q,h,left,backspace", "dismiss_screen", "Return", show=True),
        Binding("slash", "jump_to", "Search", show=True),
    ]

    def __init__(self, node: MenuNode, state: MenuConfigState, from_jump_to: bool = False) -> None:
        super().__init__()
        self.node = node
        self._state = state
        self.from_jump_to = from_jump_to

    def compose(self) -> ComposeResult:
        yield Static(info_title(self.node), id="info-title")
        yield Static(info_str(self.node, self._state.kconf), id="info-body")

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


class JumpToScreen(Screen[Optional["MenuNode"]]):
    """Fullscreen search dialog using OptionList for results."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, state: MenuConfigState) -> None:
        super().__init__()
        self._state = state
        self._matches: list[MenuNode] = []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search symbols...", id="search-input")
        yield OptionList(id="matches-list")
        yield Static("\n".join(JUMP_TO_HELP_LINES), id="jump-help")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._matches, error = self._state.search_nodes(event.value)
        ol = self.query_one("#matches-list", OptionList)
        ol.clear_options()
        if error:
            ol.add_option(error)
            return
        for node in self._matches:
            ol.add_option(jump_to_match_str(node))
        if self._matches:
            ol.highlighted = 0

    def on_key(self, event: Key) -> None:
        ol = self.query_one("#matches-list", OptionList)
        if event.key == "down":
            ol.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif event.key == "up":
            ol.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            if self._matches and ol.highlighted is not None:
                self.dismiss(self._matches[ol.highlighted])
                event.prevent_default()
                event.stop()
        elif event.key == "ctrl+f":
            if self._matches and ol.highlighted is not None:
                node = self._matches[ol.highlighted]
                self.app.push_screen(InfoScreen(node, self._state, from_jump_to=True))
                event.prevent_default()
                event.stop()

    def action_cancel(self) -> None:
        self.dismiss(None)
