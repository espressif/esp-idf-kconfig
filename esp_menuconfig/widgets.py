# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Textual widgets for menuconfig."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from textual.binding import Binding
from textual.message import Message
from textual.widgets import OptionList

from .formatting import node_str

if TYPE_CHECKING:
    from textual.geometry import Size

    from esp_kconfiglib.core import MenuNode

    from .model import MenuConfigState


class MenuOptionList(OptionList):
    """Menu list backed by Textual's native OptionList."""

    BINDINGS = [
        Binding("enter,right,l", "select_node", "Enter", show=False),
        Binding("space", "toggle_node", "Toggle", show=False),
        Binding("left,h,backspace", "leave_menu", "Back", show=False),
        Binding("escape", "escape_menu", "Escape", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "first", "Home", show=False),
        Binding("G", "last", "End", show=False),
        Binding("n,N", "set_n", "Disable symbol", show=False),
        Binding("y,Y", "set_y", "Enable symbol", show=False),
    ]

    class NodeSelected(Message):
        def __init__(self, node: MenuNode) -> None:
            super().__init__()
            self.node = node

    class NodeToggled(Message):
        def __init__(self, node: MenuNode) -> None:
            super().__init__()
            self.node = node

    class LeaveRequested(Message):
        pass

    class EscapePressed(Message):
        pass

    class BoolValueSet(Message):
        def __init__(self, bool_val: int) -> None:
            super().__init__()
            self.bool_val = bool_val

    _BACK_LABEL = "<-- Back"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._menu_nodes: list[MenuNode | None] = []

    def populate(self, state: MenuConfigState, restore_index: int | None = None) -> None:
        self._menu_nodes = []
        self.clear_options()
        is_root = state.cur_menu is state.kconf.top_node
        if not is_root:
            self._menu_nodes.append(None)
            self.add_option(self._BACK_LABEL)
        for node in state.shown:
            self._menu_nodes.append(node)
            label = node_str(
                node,
                show_name=state.show_name,
                has_visible_child_fn=state.has_visible_child,
                kconf=state.kconf,
            )
            if not (state._visible(node) or not state.show_all):
                label = f"[dim]{label}[/dim]"
            self.add_option(label)
        offset = 0 if is_root else 1
        if restore_index is not None and 0 <= restore_index + offset < len(self._menu_nodes):
            self.highlighted = restore_index + offset

    @property
    def current_node(self) -> MenuNode | None:
        if self.highlighted is not None and self.highlighted < len(self._menu_nodes):
            return self._menu_nodes[self.highlighted]
        return None

    def _select_current(self) -> None:
        if self.highlighted is not None and self.highlighted < len(self._menu_nodes):
            node = self._menu_nodes[self.highlighted]
            if node is None:
                self.post_message(self.LeaveRequested())
            else:
                self.post_message(self.NodeSelected(node))

    def action_select_node(self) -> None:
        self._select_current()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self._select_current()

    def action_toggle_node(self) -> None:
        node = self.current_node
        if node:
            self.post_message(self.NodeToggled(node))

    def action_leave_menu(self) -> None:
        self.post_message(self.LeaveRequested())

    def action_escape_menu(self) -> None:
        self.post_message(self.EscapePressed())

    def action_set_n(self) -> None:
        self.post_message(self.BoolValueSet(0))

    def action_set_y(self) -> None:
        self.post_message(self.BoolValueSet(2))

    def get_content_height(self, container: "Size", viewport: "Size", width: int) -> int:
        if width <= 0:
            return 0
        return int(super().get_content_height(container, viewport, width))
