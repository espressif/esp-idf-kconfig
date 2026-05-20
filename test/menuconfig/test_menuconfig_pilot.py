# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Pilot-driven smoke tests for the Textual menuconfig UI.

These tests use Textual's :class:`~textual.pilot.Pilot` API
(via ``App.run_test()``) to drive the menuconfig application headlessly
and verify the most error-prone interactions:

* runtime imports survive when entering Edit on a scalar symbol,
* case-insensitive command keys (legacy menuconfig behavior),
* HEX inputs with leading whitespace are not silently dropped,
* invalid inputs on range-less symbols surface a feedback modal,
* the help (``?``) screen opens correctly.

The Pilot driver runs the app in-process without a real terminal, so the
tests are deterministic and fast.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Coroutine

import pytest
from textual.pilot import Pilot

from esp_kconfiglib import Kconfig
from esp_menuconfig.app import MenuConfigApp
from esp_menuconfig.model import MenuConfigState
from esp_menuconfig.screens import InfoScreen
from esp_menuconfig.screens import InputScreen
from esp_menuconfig.screens import InvalidValueScreen
from esp_menuconfig.widgets import MenuOptionList

KCONFIGS_PATH = Path(__file__).parent / "kconfigs"
KCONFIG_ALL_SCALARS = str(KCONFIGS_PATH / "Kconfig.pilot_all_scalars")
KCONFIG_SUBMENU = str(KCONFIGS_PATH / "Kconfig.pilot_submenu")
KCONFIG_CHOICE = str(KCONFIGS_PATH / "Kconfig.pilot_choice")


def _make_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kconfig_path: str = KCONFIG_ALL_SCALARS,
) -> MenuConfigApp:
    """Build a ``MenuConfigApp`` over a fixture Kconfig with a temp sdkconfig."""
    sdkconfig = tmp_path / "sdkconfig"
    sdkconfig.write_text("", encoding="utf-8")
    monkeypatch.setenv("KCONFIG_CONFIG", str(sdkconfig))

    kconf = Kconfig(kconfig_path)
    kconf.warn = False

    state = MenuConfigState(
        kconf=kconf,
        conf_filename=str(sdkconfig),
        minconf_filename=str(tmp_path / "sdkconfig.defaults"),
        conf_changed=False,
        write_deprecated=False,
    )
    return MenuConfigApp(state)


def _run(coro_fn: Callable[[], Coroutine[Any, Any, None]]) -> None:
    """Run ``coro_fn()`` under a fresh event loop."""
    asyncio.run(coro_fn())


# Index of each symbol inside ``MenuOptionList`` when starting at the root menu
# (no back-button is shown at the top level).
_IDX_BOOL = 0
_IDX_INT = 1
_IDX_HEX = 2
_IDX_STRING = 3  # noqa: F841 (kept for clarity even if unused)
_IDX_FLOAT = 4  # noqa: F841


async def _highlight(pilot: Pilot, index: int) -> None:
    """Move the highlight in the menu list to ``index``."""
    ml = pilot.app.query_one("#menu-list", MenuOptionList)
    ml.highlighted = index
    await pilot.pause()


def test_quit_dialog_opens_and_dismisses_without_saving(tmp_path, monkeypatch):
    """Lowercase ``q`` opens the quit dialog; ``n`` exits without saving."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            from esp_menuconfig.screens import KeyDialogScreen

            assert isinstance(app.screen, KeyDialogScreen)
            await pilot.press("n")
            await pilot.pause()
        assert app.return_value is not None
        assert "not saved" in app.return_value.lower()

    _run(go)


def test_uppercase_quit_binding_opens_quit_dialog(tmp_path, monkeypatch):
    """Uppercase ``Q`` also opens the quit dialog (case-insensitive binding)."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("Q")
            await pilot.pause()
            from esp_menuconfig.screens import KeyDialogScreen

            assert isinstance(app.screen, KeyDialogScreen)
            await pilot.press("escape")
            await pilot.pause()

    _run(go)


def test_int_symbol_enters_input_screen(tmp_path, monkeypatch):
    """Pressing Enter on an INT symbol pushes ``InputScreen``.

    Without the ``Symbol`` import being a runtime import, this would raise
    ``NameError: name 'Symbol' is not defined`` from ``_show_input_dialog``.
    """

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _highlight(pilot, _IDX_INT)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, InputScreen)

    _run(go)


def test_uppercase_save_binding_triggers_save(tmp_path, monkeypatch):
    """Capital ``S`` triggers the Save action (case-insensitive binding)."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _highlight(pilot, _IDX_BOOL)
            await pilot.press("space")
            await pilot.pause()
            assert app.state.conf_changed is True

            await pilot.press("S")
            await pilot.pause()
            assert app.state.conf_changed is False

        sdkconfig = Path(app.state.conf_filename)
        assert sdkconfig.exists()
        contents = sdkconfig.read_text(encoding="utf-8")
        assert "CONFIG_BOOL_SYM" in contents

    _run(go)


def test_hex_leading_whitespace_is_stripped(tmp_path, monkeypatch):
    """Entering `` 0xff`` for a HEX symbol stores ``0xff`` (no silent drop)."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _highlight(pilot, _IDX_HEX)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, InputScreen)

            input_widget = app.screen.query_one("#dialog-input")
            input_widget.value = " 0xff"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

        sym = app.state.kconf.syms["HEX_SYM"]
        assert sym.str_value == "0xff"

    _run(go)


@pytest.mark.parametrize(
    ("highlight_index", "invalid_text", "error_fragment"),
    [
        (_IDX_HEX, "zzz", "zzz"),
        (_IDX_INT, "MEOW", "MEOW"),
    ],
    ids=["hex_no_range", "int_with_range"],
)
def test_invalid_input_always_shows_modal(tmp_path, monkeypatch, highlight_index, invalid_text, error_fragment):
    """Invalid input pushes ``InvalidValueScreen`` for both range-less and ranged symbols."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _highlight(pilot, highlight_index)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, InputScreen)

            input_widget = app.screen.query_one("#dialog-input")
            input_widget.value = invalid_text
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(app.screen, InvalidValueScreen)
            assert error_fragment in app.screen.error

            await pilot.press("space")
            await pilot.pause()
            assert not isinstance(app.screen, InvalidValueScreen)

    _run(go)


def test_info_screen_opens_on_question_mark(tmp_path, monkeypatch):
    """Pressing ``?`` on a highlighted symbol pushes ``InfoScreen``."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _highlight(pilot, _IDX_BOOL)
            await pilot.press("?")
            await pilot.pause()
            assert isinstance(app.screen, InfoScreen)

    _run(go)


# --- #2 HEX-without-0x-prefix branch ---------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [("ff", "0xff"), (" ff", "0xff")],
    ids=["no_prefix", "leading_space_no_prefix"],
)
def test_hex_input_without_prefix_is_prepended(tmp_path, monkeypatch, text, expected):
    """Inputs without a ``0x`` prefix get one prepended (after stripping)."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _highlight(pilot, _IDX_HEX)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, InputScreen)

            input_widget = app.screen.query_one("#dialog-input")
            input_widget.value = text
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

        assert app.state.kconf.syms["HEX_SYM"].str_value == expected

    _run(go)


# --- #3 Quit-with-changes Y/N/C branches -----------------------------------


async def _toggle_bool_to_dirty(pilot: Pilot) -> None:
    """Flip BOOL_SYM via ``space`` so ``state.conf_changed`` becomes ``True``."""
    await _highlight(pilot, _IDX_BOOL)
    await pilot.press("space")
    await pilot.pause()
    assert pilot.app.state.conf_changed is True


def test_quit_with_changes_save_branch_exits_with_saved_message(tmp_path, monkeypatch):
    """``q`` then ``y`` on the quit dialog saves and exits."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _toggle_bool_to_dirty(pilot)
            await pilot.press("q")
            await pilot.pause()
            from esp_menuconfig.screens import KeyDialogScreen

            assert isinstance(app.screen, KeyDialogScreen)
            await pilot.press("y")
            await pilot.pause()

        assert app.return_value is not None
        assert "saved" in app.return_value.lower()
        sdkconfig = Path(app.state.conf_filename)
        assert sdkconfig.exists()
        assert "CONFIG_BOOL_SYM" in sdkconfig.read_text(encoding="utf-8")

    _run(go)


def test_quit_with_changes_discard_branch_exits_without_saving(tmp_path, monkeypatch):
    """``q`` then ``n`` on the quit dialog exits without saving."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _toggle_bool_to_dirty(pilot)
            await pilot.press("q")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()

        assert app.return_value is not None
        assert "not saved" in app.return_value.lower()

    _run(go)


def test_quit_with_changes_cancel_branch_keeps_app_running(tmp_path, monkeypatch):
    """``q`` then ``c`` on the quit dialog dismisses and keeps the app running."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _toggle_bool_to_dirty(pilot)
            await pilot.press("q")
            await pilot.pause()
            from esp_menuconfig.screens import KeyDialogScreen

            assert isinstance(app.screen, KeyDialogScreen)
            await pilot.press("c")
            await pilot.pause()

            assert not isinstance(app.screen, KeyDialogScreen)
            assert app.return_value is None
            assert app.state.conf_changed is True

            await pilot.press("q")
            await pilot.press("n")
            await pilot.pause()

    _run(go)


# --- #4 Submenu enter/leave ------------------------------------------------


def test_submenu_enter_and_leave(tmp_path, monkeypatch):
    """Entering a submenu changes ``cur_menu``; ``backspace`` returns to the parent."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch, kconfig_path=KCONFIG_SUBMENU)
        async with app.run_test() as pilot:
            await pilot.pause()
            top = app.state.kconf.top_node
            assert app.state.cur_menu is top

            # Inner menu is the second visible entry under the root.
            await _highlight(pilot, 1)
            await pilot.press("enter")
            await pilot.pause()
            assert app.state.cur_menu is not top

            await pilot.press("backspace")
            await pilot.pause()
            assert app.state.cur_menu is top

    _run(go)


# --- #5 Restore default ----------------------------------------------------


def test_restore_default_reverts_changed_symbol(tmp_path, monkeypatch):
    """Pressing ``r`` on a changed scalar reverts it to its default."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            sym = app.state.kconf.syms["BOOL_SYM"]
            assert sym.str_value == "y"

            await _highlight(pilot, _IDX_BOOL)
            await pilot.press("space")
            await pilot.pause()
            assert sym.str_value == "n"

            await pilot.press("r")
            await pilot.pause()
            assert sym.str_value == "y"

    _run(go)


# --- #7 InfoScreen close keys ---------------------------------------------


@pytest.mark.parametrize("close_key", ["escape", "q", "h", "left", "backspace"])
def test_info_screen_closes_on_any_dismiss_key(tmp_path, monkeypatch, close_key):
    """All keys declared in ``InfoScreen.BINDINGS`` for dismiss actually pop the screen."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _highlight(pilot, _IDX_BOOL)
            await pilot.press("?")
            await pilot.pause()
            assert isinstance(app.screen, InfoScreen)

            await pilot.press(close_key)
            await pilot.pause()
            assert not isinstance(app.screen, InfoScreen)

    _run(go)


# --- #8 JumpToScreen navigation -------------------------------------------


def test_jump_to_navigates_to_matched_symbol(tmp_path, monkeypatch):
    """Searching for a symbol and pressing Enter navigates to it."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            # Start with the FLOAT symbol highlighted so the jump observably moves us.
            await _highlight(pilot, _IDX_FLOAT)

            await pilot.press("slash")
            await pilot.pause()
            from esp_menuconfig.screens import JumpToScreen

            assert isinstance(app.screen, JumpToScreen)

            search_input = app.screen.query_one("#search-input")
            search_input.value = "bool_sym"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert not isinstance(app.screen, JumpToScreen)
            ml = app.query_one("#menu-list", MenuOptionList)
            assert ml.current_node is app.state.kconf.syms["BOOL_SYM"].nodes[0]

    _run(go)


# --- #9 Validator messages per scalar type --------------------------------


@pytest.mark.parametrize(
    ("highlight_index", "invalid_text", "expected_fragment"),
    [
        (_IDX_FLOAT, "1,5", "decimal point"),
        (_IDX_INT, "99", "outside the range"),
    ],
    ids=["float_comma_hint", "int_out_of_range"],
)
def test_validator_message_explains_why(tmp_path, monkeypatch, highlight_index, invalid_text, expected_fragment):
    """Validator error text reaches the modal with the right type-specific hint."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _highlight(pilot, highlight_index)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, InputScreen)

            input_widget = app.screen.query_one("#dialog-input")
            input_widget.value = invalid_text
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(app.screen, InvalidValueScreen)
            assert expected_fragment in app.screen.error

    _run(go)


# --- #10 Choice selection -------------------------------------------------


def test_choice_option_selection_changes(tmp_path, monkeypatch):
    """Selecting a different choice option flips which symbol is ``y``."""

    async def go() -> None:
        app = _make_app(tmp_path, monkeypatch, kconfig_path=KCONFIG_CHOICE)
        async with app.run_test() as pilot:
            await pilot.pause()

            sym_a = app.state.kconf.syms["OPTION_A"]
            sym_b = app.state.kconf.syms["OPTION_B"]
            assert sym_a.str_value == "y"
            assert sym_b.str_value == "n"

            # Enter the choice (first visible entry at root).
            await _highlight(pilot, 0)
            await pilot.press("enter")
            await pilot.pause()
            assert app.state.cur_menu is not app.state.kconf.top_node

            # Highlight OPTION_B and press 'y' to select it.
            ml = app.query_one("#menu-list", MenuOptionList)
            for i, node in enumerate(ml._menu_nodes):
                if node is not None and getattr(node.item, "name", None) == "OPTION_B":
                    ml.highlighted = i
                    break
            else:
                raise AssertionError("OPTION_B node not found in choice menu")
            await pilot.pause()

            await pilot.press("y")
            await pilot.pause()

            assert sym_b.str_value == "y"
            assert sym_a.str_value == "n"

    _run(go)
