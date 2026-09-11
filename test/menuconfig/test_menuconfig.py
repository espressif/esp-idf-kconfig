# SPDX-FileCopyrightText: 2025-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import shutil
import sys
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Union

import pytest

from esp_kconfiglib import Kconfig
from esp_kconfiglib.core import MENU
from esp_kconfiglib.core import Choice
from esp_kconfiglib.core import MenuNode
from esp_kconfiglib.core import Symbol
from esp_kconfiglib.core import _restore_default
from esp_menuconfig import _needs_save
from esp_menuconfig import menuconfig
from esp_menuconfig import reload_sdkconfig_file
from esp_menuconfig.formatting import mismatch_column_widths
from esp_menuconfig.formatting import mismatch_format_row
from esp_menuconfig.formatting import mismatch_notice_text
from esp_menuconfig.formatting import mismatch_table_header
from esp_menuconfig.formatting import node_str
from esp_menuconfig.model import ChangeResult
from esp_menuconfig.model import MenuConfigState

TEST_FILES_PATH = os.path.abspath(os.path.dirname(__file__))
KCONFIGS_PATH = os.path.join(TEST_FILES_PATH, "kconfigs")
SDKCONFIGS_PATH = os.path.join(TEST_FILES_PATH, "sdkconfigs")
SDKCONFIGS_NEEDS_SAVE_PATH = os.path.join(SDKCONFIGS_PATH, "test_needs_save")
SDKCONFIGS_CHOICE_DEFAULT_PATH = os.path.join(SDKCONFIGS_PATH, "test_choice_defaults")


def _make_state(kconf: "Kconfig") -> MenuConfigState:
    """Create a MenuConfigState without loading config from KCONFIG_CONFIG."""
    return MenuConfigState(
        kconf=kconf,
        conf_filename="",
        minconf_filename="",
        conf_changed=False,
        write_deprecated=False,
    )


class MenuconfigTestBase:
    @pytest.fixture(scope="class", autouse=True)
    def version(self, request):
        # Set the KCONFIG_PARSER_VERSION environment variable
        version = request.param
        os.environ["KCONFIG_PARSER_VERSION"] = version
        yield
        # Clean up after the test
        del os.environ["KCONFIG_PARSER_VERSION"]


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestNeedsSave(MenuconfigTestBase):
    """
    Checking cases in which the sdkconfig file needs to be saved.
    Does not check the actual content of the sdkconfig file (this is done in test_kconfiglib.py).

    Principle:
        1) Set the KCONFIG_CONFIG environment variable to point to the sdkconfig file.
        2) Load the Kconfig file and the sdkconfig file.
        3) Call menuconfig with headless=True (disabling the TUI).
        4) Check if the configuration needs to be saved.

    As we are determining if the configuration needs to be saved, we are checking if correct flags
    were set during the loading of the files -> we cannot simply monkeypatch the values inside the Kconfig system.
    """

    def assert_and_print_actual(self, val: bool, kconfig: "Kconfig") -> None:
        needs_save = _needs_save()
        try:
            assert needs_save is val
        except AssertionError:
            print(
                f"menuconfig {'wants' if needs_save else 'does not want'} to save the sdkconfig file even "
                f"though it is {'not' if needs_save else ''} expected to.",
                file=sys.stderr,
            )
            if needs_save:
                print("menuconfig attempted to save following output:", file=sys.stderr)
                print(kconfig._config_contents(None), file=sys.stderr)
            raise

    def test_no_change(self) -> None:
        # Nothing changed in the configuration, there should be no need to save.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_NEEDS_SAVE_PATH, "sdkconfig.no_change")
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        menuconfig(kconfig, headless=True)
        self.assert_and_print_actual(False, kconfig)

    def test_new_symbol_in_kconfig(self) -> None:
        # New symbol is added to the Kconfig file (or removed from sdkconfig file).
        # In other words, there is a symbol in Kconfig which is not in sdkconfig.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_NEEDS_SAVE_PATH, "sdkconfig.new_kconfig_symbol")
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        menuconfig(kconfig, headless=True)
        self.assert_and_print_actual(True, kconfig)

    def test_reset_from_different_value(self) -> None:
        # Symbol is reset to default value from user value different from default.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_NEEDS_SAVE_PATH, "sdkconfig.reset_from_different_value")
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        menuconfig(kconfig, headless=True)
        _restore_default(kconfig.syms["CREW"].nodes[0])
        self.assert_and_print_actual(True, kconfig)

    def test_reset_from_same_value(self) -> None:
        # User previously set the value as the same as default.
        # Still need to save in order to add the # default: comment.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_NEEDS_SAVE_PATH, "sdkconfig.reset_from_same_value")
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        menuconfig(kconfig, headless=True)
        _restore_default(kconfig.syms["CREW"].nodes[0])
        self.assert_and_print_actual(True, kconfig)

    def test_user_value_changed(self) -> None:
        # User changed the value of a symbol which was already user-set.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_NEEDS_SAVE_PATH, "sdkconfig.user_value_changed")
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        menuconfig(kconfig, headless=True)
        kconfig.syms["CREW"].set_value("n")
        self.assert_and_print_actual(True, kconfig)

    @pytest.mark.parametrize("defaults_policy", ["sdkconfig", "kconfig"])
    def test_default_value_in_kconfig_changed(self, defaults_policy: str, monkeypatch: pytest.MonkeyPatch) -> None:
        # Default value of a symbol in Kconfig changed.
        # Using "original sdkconfig" with the "old" default value.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_NEEDS_SAVE_PATH, "sdkconfig.no_change")
        monkeypatch.setenv("KCONFIG_DEFAULTS_POLICY", defaults_policy)
        # MOTORS_ENABLED default value changed from "n" to "y"
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.default_value_changed"))
        menuconfig(kconfig, headless=True)
        self.assert_and_print_actual(True if defaults_policy == "kconfig" else False, kconfig)

    def test_userset_choice(self) -> None:
        # User-set choice from sdkconfig should not trigger save.
        # Reason: IDFGH-16950 (user-set choice with non-first selection triggered save)
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_NEEDS_SAVE_PATH, "sdkconfig.no_change")
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        kconfig.load_config(os.path.join(SDKCONFIGS_NEEDS_SAVE_PATH, "sdkconfig.userset_choice"))
        menuconfig(kconfig, headless=True)
        self.assert_and_print_actual(False, kconfig)


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestBaselineSyncAfterSave(MenuconfigTestBase):
    """
    write_config() does not refresh Symbol._sdkconfig_value / _loaded_as_default.
    Menuconfig must reload the main sdkconfig after a successful save so _needs_save()
    stays false when the user saved and made no further edits (quit must not ask again).
    """

    def test_sync_after_write_clears_needs_save(self, tmp_path: Path) -> None:
        src = os.path.join(SDKCONFIGS_NEEDS_SAVE_PATH, "sdkconfig.new_kconfig_symbol")
        dst = tmp_path / "sdkconfig"
        shutil.copy(src, dst)
        os.environ["KCONFIG_CONFIG"] = str(dst)
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        menuconfig(kconfig, headless=True)
        assert _needs_save() is True
        kconfig.write_config(str(dst))
        assert _needs_save() is True
        reload_sdkconfig_file(str(dst))
        assert _needs_save() is False


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestChoicesDefault(MenuconfigTestBase):
    """
    Test if menuconfig can handle default values for choice symbols correctly.
    Inherently, it also tests if the default value is correctly handled in Kconfig.
    """

    def _change_node_monkeypatch(self, sc: Union["Symbol", "Choice"]) -> None:
        """
        Cannot use change_node() from model (does not work in headless mode)
        -> using monkeypatch method without menuconfig-related TUI functionality.
        """
        if len(sc.assignable) == 1:
            sc.set_value(sc.assignable[0])
        else:
            # Set the symbol to the value after the current value in
            # sc.assignable, with wrapping
            # i.e y -> n, n -> y
            val_index = sc.assignable.index(sc.bool_value)
            sc.set_value(sc.assignable[(val_index + 1) % len(sc.assignable)])

    def test_unchanged_choice_default(self) -> None:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.choice_default"))
        menuconfig(kconfig, headless=True)
        assert kconfig.syms["FOO"].has_active_default_value() is True
        assert kconfig.syms["BAR"].has_active_default_value() is True
        assert kconfig.syms["QUX"].has_active_default_value() is True
        assert kconfig.syms["BAZ"].has_active_default_value() is True

        assert kconfig.syms["FOO"].str_value == "y"
        assert kconfig.syms["BAR"].str_value == "n"
        assert kconfig.syms["BAZ"].str_value == "y"
        assert kconfig.syms["QUX"].str_value == "n"

        sdkconfig = kconfig._config_contents(None)
        assert "# default:\nCONFIG_FOO=y" in sdkconfig, (
            f"Default value for choice symbol FOO should be 'y' in {sdkconfig}."
        )
        assert "# default:\n# CONFIG_BAR is not set" in sdkconfig, (
            f"Default value for choice symbol BAR should be 'n' in {sdkconfig}."
        )
        assert "# default:\nCONFIG_BAZ=y" in sdkconfig, (
            f"Default value for choice symbol BAZ should be 'y' in {sdkconfig}."
        )
        assert "# default:\n# CONFIG_QUX is not set" in sdkconfig, (
            f"Default value for choice symbol QUX should be 'n' in {sdkconfig}."
        )

    def test_changed_choice_default(self) -> None:
        """
        Test if changed value from menuconfig is correctly written to sdkconfig.
        """
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.choice_default"))
        menuconfig(kconfig, headless=True)

        sym = kconfig.syms["QUX"]
        self._change_node_monkeypatch(sym)

        assert kconfig.syms["BAZ"].has_active_default_value() is False
        assert kconfig.syms["QUX"].has_active_default_value() is False
        assert kconfig.syms["BAZ"].str_value == "n", (
            f"Value for choice symbol BAZ should be 'n', but is {kconfig.syms['BAZ'].str_value}."
        )
        assert kconfig.syms["QUX"].str_value == "y", (
            f"Value for choice symbol QUX should be 'y', but is {kconfig.syms['QUX'].str_value}."
        )

        sdkconfig2 = kconfig._config_contents(None)  # Getting only the content, not actually writing to the file
        # Check if the sdkconfig file was updated correctly
        assert "# CONFIG_BAZ is not set" in sdkconfig2, (
            f"Value for choice symbol BAZ should be 'n' and user-set in {sdkconfig2}."
        )
        assert "CONFIG_QUX=y" in sdkconfig2, f"Value for choice symbol QUX should be 'y' and user-set in {sdkconfig2}."

    def test_reset_choice_default(self, version: str) -> None:
        """
        Test
        - if values loaded as non-default, but with the same value as default, are correctly recognized
        - if user-set values are correctly reset to default
        """
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.choice_default"))
        kconfig.load_config(os.path.join(SDKCONFIGS_CHOICE_DEFAULT_PATH, "sdkconfig.not_defaults"))

        assert kconfig.syms["FOO"].has_active_default_value() is False
        assert kconfig.syms["BAR"].has_active_default_value() is False
        assert kconfig.syms["BAZ"].has_active_default_value() is False
        assert kconfig.syms["QUX"].has_active_default_value() is False

        assert kconfig.syms["FOO"].str_value == "n"
        assert kconfig.syms["BAR"].str_value == "y"
        # second choice has same values as default, but user-set
        assert kconfig.syms["BAZ"].str_value == "y"
        assert kconfig.syms["QUX"].str_value == "n"

        menuconfig(kconfig, headless=True)
        _restore_default(kconfig.syms["BAZ"].nodes[0])
        _restore_default(kconfig.named_choices["NAMED_CHOICE"].nodes[0])
        sdkconfig = kconfig._config_contents(None)

        assert "# default:\nCONFIG_FOO=y" in sdkconfig, (
            f"Default value for choice symbol FOO should be 'y' in {sdkconfig}."
        )
        assert "# default:\n# CONFIG_BAR is not set" in sdkconfig, (
            f"Default value for choice symbol BAR should be 'n' in {sdkconfig}."
        )
        assert "# default:\nCONFIG_BAZ=y" in sdkconfig, (
            f"Default value for choice symbol BAZ should be 'y' in {sdkconfig}."
        )
        assert "# default:\n# CONFIG_QUX is not set" in sdkconfig, (
            f"Default value for choice symbol QUX should be 'n' in {sdkconfig}."
        )


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestIndirectlySetValues(MenuconfigTestBase):
    """
    Test if menuconfig correctly handles values indirectly set via "set" and "set default" options.
    """

    def test_indirectly_set_value(self) -> None:
        """
        Test if:
        - "set" option prevent its target from being changed
        - correct precedence is applied (indirectly set > user-set > default for "set")
        - target ignores (but preserves) its user-set values when indirectly set via "set" option

        - "set default" option sets the target to given values but allows user to change it
        - correct precedence (user-set > indirectly set > default for "set default")
        """
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.indirect_sets"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "test_indirect_sets", "sdkconfig"))

        state = _make_state(kconfig)

        sym = kconfig.syms["SET_TARGET"]
        assert sym.str_value == "4"  # indirectly set value has absolute precedence
        assert sym._user_value == "2"  # user-set value is preserved, but ignored

        result = state.change_node(sym.nodes[0])
        assert result == ChangeResult.NO_CHANGE, "Changing indirectly set value should not be allowed, but it was."

        # Turn off source, which indirectly sets the value. User-set value of the target should be restored.
        kconfig.syms["SET_SOURCE"].set_value("n")
        assert sym.str_value == "2", (
            "User-set value should be restored in target symbol after turning off the source symbol, but it is not."
        )

        sym = kconfig.syms["SET_DEFAULT_TARGET"]
        assert sym.str_value == "2"  # set default value has lower precedence than user-set value
        _restore_default(sym.nodes[0])
        assert sym.str_value == "4", (
            "After restoring target symbol's value, indirectly set default value should be used, but it is not."
        )

        menuconfig(kconfig, headless=True)


class TestSetRiskyConfig:
    """
    Test if menuconfig correctly handles 'warning' option for symbols: change_node() should return
    NEEDS_WARNING to confirm changing the value of a risky symbol, but only if the symbol is
    not already user-set.
    """

    @pytest.mark.parametrize("parser_version", (1, 2))
    def test_risky_symbol_returns_needs_warning(self, parser_version: int) -> None:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.warning"), parser_version=parser_version)
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "test_warning", "sdkconfig.warning"))

        state = _make_state(kconfig)

        # RISKY_BOOL: has warning, default value → should return NEEDS_WARNING
        sym = kconfig.syms["RISKY_BOOL"]
        assert sym.warning != ""
        result = state.change_node(sym.nodes[0])
        assert result == ChangeResult.NEEDS_WARNING

        # After force_change_node (simulating user confirming), it should toggle
        result = state.force_change_node(sym.nodes[0])
        assert result == ChangeResult.TOGGLED
        assert sym.str_value == "y"

    @pytest.mark.parametrize("parser_version", (1, 2))
    def test_risky_int_returns_needs_input_via_warning(self, parser_version: int) -> None:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.warning"), parser_version=parser_version)
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "test_warning", "sdkconfig.warning"))

        state = _make_state(kconfig)

        # RISKY_INT: has warning, default value → NEEDS_WARNING
        sym = kconfig.syms["RISKY_INT"]
        assert sym.warning != ""
        result = state.change_node(sym.nodes[0])
        assert result == ChangeResult.NEEDS_WARNING

        # After force (user confirmed warning), it needs input for the int value
        result = state.force_change_node(sym.nodes[0])
        assert result == ChangeResult.NEEDS_INPUT

        # ALREADY_USER_SET_RISKY_INT: has warning, but already user-set → NEEDS_INPUT directly
        sym = kconfig.syms["ALREADY_USER_SET_RISKY_INT"]
        assert sym.warning != ""
        result = state.change_node(sym.nodes[0])
        assert result == ChangeResult.NEEDS_INPUT


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestFloatInput(MenuconfigTestBase):
    def test_float_value_change(self) -> None:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.float"))

        state = _make_state(kconfig)

        sym = kconfig.syms["FLOAT_VALUE"]
        assert sym.str_value == "1.0"

        result = state.change_node(sym.nodes[0])
        assert result == ChangeResult.NEEDS_INPUT

        # Simulate user entering value via set_val
        state.set_val(sym, "1.25")
        assert sym.str_value == "1.25"

        sdkconfig = kconfig._config_contents(None)
        assert "CONFIG_FLOAT_VALUE=1.25" in sdkconfig


def _node_str_wrapper(node: MenuNode) -> str:
    """Wrapper matching the old _node_str() interface for tests."""
    return node_str(
        node,
        show_name=False,
        has_visible_child_fn=lambda n: n.list is not None,
        kconf=node.kconfig,
    )


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestChoiceDefaultMenuLabels(MenuconfigTestBase):
    """IDF-14509: parent choices show (default value); options show (default selection) only when appropriate."""

    @pytest.mark.parametrize(
        ("kconfig_file", "named_default_selection", "named_sym_to_leave_default"),
        [
            # Implicit default: first symbol in the named choice
            ("Kconfig.choice_default", "FOO", "BAR"),
            # Explicit `default BAR` — (default selection) must follow Kconfig, not symbol order
            ("Kconfig.choice_explicit_default", "BAR", "FOO"),
        ],
    )
    def test_choice_default_and_selection_labels(
        self,
        version: int,
        tmp_path: Path,
        kconfig_file: str,
        named_default_selection: str,
        named_sym_to_leave_default: str,
    ) -> None:
        sdkconfig = tmp_path / "sdkconfig"
        sdkconfig.write_text("", encoding="utf-8")
        prev_kconfig_config = os.environ.get("KCONFIG_CONFIG")
        os.environ["KCONFIG_CONFIG"] = str(sdkconfig)
        try:
            kconfig = Kconfig(os.path.join(KCONFIGS_PATH, kconfig_file), parser_version=version)
            menuconfig(kconfig, headless=True)

            named_choice_node = None
            unnamed_choice_node = None
            sym_nodes: Dict[str, Any] = {}

            for n in kconfig.node_iter():
                if isinstance(n.item, Choice) and n.prompt:
                    if n.prompt[0] == "prompt for named choice":
                        named_choice_node = n
                    elif n.prompt[0] == "unnamed choice":
                        unnamed_choice_node = n
                elif isinstance(n.item, Symbol) and n.item.name in ("FOO", "BAR", "BAZ", "QUX"):
                    sym_nodes[n.item.name] = n

            assert named_choice_node is not None
            assert unnamed_choice_node is not None
            for name in ("FOO", "BAR", "BAZ", "QUX"):
                assert name in sym_nodes, f"missing menu node for {name}"

            named_parent = _node_str_wrapper(named_choice_node)
            assert "(default value)" in named_parent
            assert "mismatched" not in named_parent
            assert "prompt for named choice" in named_parent

            default_line = _node_str_wrapper(sym_nodes[named_default_selection])
            other_line = _node_str_wrapper(sym_nodes[named_sym_to_leave_default])
            assert "(default selection)" in default_line
            assert "(default value)" not in default_line
            assert "(default selection)" not in other_line
            assert "(default value)" not in other_line

            unnamed_parent = _node_str_wrapper(unnamed_choice_node)
            assert "(default value)" in unnamed_parent
            assert "mismatched" not in unnamed_parent

            baz_line = _node_str_wrapper(sym_nodes["BAZ"])
            qux_line = _node_str_wrapper(sym_nodes["QUX"])
            assert "(default selection)" in baz_line
            assert "(default value)" not in baz_line
            assert "(default selection)" not in qux_line
            assert "(default value)" not in qux_line

            kconfig.syms[named_sym_to_leave_default].set_value("y")

            named_parent_after = _node_str_wrapper(named_choice_node)
            assert "(default value)" not in named_parent_after
            foo_after = _node_str_wrapper(sym_nodes["FOO"])
            bar_after = _node_str_wrapper(sym_nodes["BAR"])
            assert "(default selection)" not in foo_after
            assert "(default selection)" not in bar_after
        finally:
            if prev_kconfig_config is None:
                os.environ.pop("KCONFIG_CONFIG", None)
            else:
                os.environ["KCONFIG_CONFIG"] = prev_kconfig_config


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestMenuconfigSdkconfigDefaultsPath(MenuconfigTestBase):
    """Default ``sdkconfig.defaults`` path next to ``sdkconfig`` (menuconfig ``[D]``)."""

    def test_default_minconf_filename(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Menuconfig derives the default minimal-config path from ``KCONFIG_CONFIG``."""
        sdkconfig = tmp_path / "sdkconfig"
        sdkconfig.write_text("", encoding="utf-8")
        monkeypatch.setenv("KCONFIG_CONFIG", str(sdkconfig))

        from esp_kconfiglib.core import standard_config_filename

        expected = os.path.join(os.path.dirname(standard_config_filename()), "sdkconfig.defaults")
        assert expected == str(tmp_path / "sdkconfig.defaults")


class TestMenuconfigHeadlessEnvVar:
    """``_main()`` should pass ``headless=True`` when ``MENUCONFIG_HEADLESS=1``."""

    @pytest.fixture
    def patched_main(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
        sdkconfig = tmp_path / "sdkconfig"
        sdkconfig.write_text("", encoding="utf-8")
        monkeypatch.setenv("KCONFIG_CONFIG", str(sdkconfig))

        captured: Dict[str, Any] = {}
        real_kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        captured["kconf"] = real_kconfig

        def fake_kconfig_ctor(*args: Any, **kwargs: Any) -> Kconfig:
            return real_kconfig

        def fake_menuconfig(kconf: Kconfig, headless: bool = False) -> None:
            captured["headless"] = headless

        monkeypatch.setattr("esp_kconfiglib.core.Kconfig", fake_kconfig_ctor)
        monkeypatch.setattr("esp_menuconfig.menuconfig", fake_menuconfig)
        return captured

    @pytest.mark.parametrize("env_val, expected_headless", [("1", True), ("0", False), ("", False)])
    def test_headless_env_var(
        self,
        patched_main: Dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        env_val: str,
        expected_headless: bool,
    ) -> None:
        monkeypatch.delenv("SDKCONFIG_RENAME", raising=False)
        monkeypatch.delenv("COMPONENT_SDKCONFIG_RENAMES", raising=False)
        if env_val:
            monkeypatch.setenv("MENUCONFIG_HEADLESS", env_val)
        else:
            monkeypatch.delenv("MENUCONFIG_HEADLESS", raising=False)

        from esp_menuconfig.__main__ import _main

        _main.callback(kconfig="Kconfig")

        assert patched_main["headless"] is expected_headless


def _sc_names(nodes: List[MenuNode]) -> List[str]:
    """Names of Symbol/Choice items; narrows for mypy."""
    return [n.item.name for n in nodes if isinstance(n.item, (Symbol, Choice)) and n.item.name is not None]


def _symbol_node(nodes: List[MenuNode], name: str) -> MenuNode:
    """Return the first shown node whose item is Symbol *name*."""
    for node in nodes:
        item = node.item
        if type(item) is Symbol and item.name == name:
            return node
    raise AssertionError(f"no symbol node named {name}")


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestSearchNodes(MenuconfigTestBase):
    def test_search_matches_config_prefix(self) -> None:
        """sdkconfig-style CONFIG_FOO queries should match symbol FOO."""
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        state = _make_state(kconfig)

        bare_matches, bare_err = state.search_nodes("motors_enabled")
        prefixed_matches, prefixed_err = state.search_nodes("CONFIG_MOTORS_ENABLED")
        mixed_case_matches, mixed_err = state.search_nodes("config_MOTORS_ENABLED")

        assert bare_err is None and prefixed_err is None and mixed_err is None
        bare_names = _sc_names(bare_matches)
        assert bare_names
        assert bare_names == _sc_names(prefixed_matches)
        assert bare_names == _sc_names(mixed_case_matches)
        assert bare_names[0] == "MOTORS_ENABLED"

    def test_search_config_prefix_alone_matches_prefixed_names(self) -> None:
        """A bare CONFIG_ token matches every symbol via its prefixed name."""
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        state = _make_state(kconfig)

        matches, err = state.search_nodes("CONFIG_")
        assert err is None
        assert matches
        assert "MOTORS_ENABLED" in set(_sc_names(matches))

    def test_search_anchored_bare_name_still_matches(self) -> None:
        """Anchored regex against bare symbol name must keep working."""
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        state = _make_state(kconfig)

        matches, err = state.search_nodes("^motors_enabled$")
        assert err is None
        assert _sc_names(matches) == ["MOTORS_ENABLED"]

        prefixed_matches, prefixed_err = state.search_nodes("^config_motors_enabled$")
        assert prefixed_err is None
        assert _sc_names(prefixed_matches) == ["MOTORS_ENABLED"]


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestDefaultMismatchList(MenuconfigTestBase):
    def test_default_mismatches_lists_symbols_and_choices(self) -> None:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.pilot_mismatch"))
        kconfig.report.reset()
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.pilot_mismatch"))
        state = _make_state(kconfig)

        symbols, choices = state.default_mismatches()
        assert [(sym.name, kconfig_val, sdk_val) for sym, kconfig_val, sdk_val in symbols] == [("FOO", "1", "2")]
        assert [(choice.name, kconfig_val, sdk_val) for choice, kconfig_val, sdk_val in choices] == [
            ("PICK", "CA", "CB")
        ]

        kconfig.report.reset()

    def test_default_mismatches_unique_after_reload(self) -> None:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.pilot_mismatch"))
        kconfig.report.reset()
        sdkconfig = os.path.join(SDKCONFIGS_PATH, "sdkconfig.pilot_mismatch")
        kconfig.load_config(sdkconfig)
        kconfig.load_config(sdkconfig)
        state = _make_state(kconfig)

        symbols, choices = state.default_mismatches()
        assert [sym.name for sym, _, _ in symbols] == ["FOO"]
        assert [choice.name for choice, _, _ in choices] == ["PICK"]

        kconfig.report.reset()

    def test_node_str_marks_mismatched_default_values(self) -> None:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.pilot_mismatch"))
        kconfig.report.reset()
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.pilot_mismatch"))

        foo_node = None
        pick_node = None
        for node in kconfig.node_iter():
            if type(node.item) is Symbol and node.item.name == "FOO":
                foo_node = node
            elif type(node.item) is Choice and node.item.name == "PICK":
                pick_node = node

        assert foo_node is not None
        assert pick_node is not None
        assert "(default value, mismatched)" in _node_str_wrapper(foo_node)
        assert "(default value, mismatched)" in _node_str_wrapper(pick_node)

        kconfig.report.reset()

    def test_default_mismatches_empty_without_sdkconfig_defaults(self) -> None:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.pilot_mismatch"))
        kconfig.report.reset()
        state = _make_state(kconfig)

        symbols, choices = state.default_mismatches()
        assert symbols == []
        assert choices == []

        kconfig.report.reset()

    def test_apply_mismatch_resolution_sets_user_value(self) -> None:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.pilot_mismatch"))
        kconfig.report.reset()
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.pilot_mismatch"))
        state = _make_state(kconfig)

        foo = kconfig.syms["FOO"]
        pick = kconfig.named_choices["PICK"]
        state.apply_mismatch_resolution(foo, "kconfig", "1", "2")
        assert foo.str_value == "1"
        assert foo._user_value == "1"
        assert state.conf_changed

        state.apply_mismatch_resolution(pick, "sdkconfig", "CA", "CB")
        assert pick.selection is kconfig.syms["CB"]
        assert kconfig.syms["CB"]._user_value == 2

        state.apply_mismatch_resolution(pick, "kconfig", "choice deselected", "CB")
        assert pick._user_selection is None
        assert kconfig.syms["CB"]._user_value is None

        state.apply_mismatch_resolution(pick, "sdkconfig", "CA", "CB")
        assert pick.selection is kconfig.syms["CB"]

        state.clear_mismatch_resolution(foo)
        assert foo._user_value is None
        state.clear_mismatch_resolution(pick)
        assert pick._user_selection is None
        assert kconfig.syms["CB"]._user_value is None

        kconfig.report.reset()

    def _dep_state(self) -> MenuConfigState:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.mismatch_dep"))
        kconfig.report.reset()
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.mismatch_dep"))
        return _make_state(kconfig)

    def test_resolution_hiding_selected_node_keeps_cursor(self) -> None:
        """Resolving A hides B; the cursor must survive on a still-visible node."""
        state = self._dep_state()
        b_node = _symbol_node(state.shown, "B")
        state.sel_node_i = state.shown.index(b_node)

        state.apply_mismatch_resolution(state.kconf.syms["A"], "kconfig", "n", "y")

        assert b_node not in state.shown
        assert state.selected_node.item is state.kconf.syms["A"]

        state.kconf.report.reset()

    def test_resolution_emptying_current_menu_falls_back_to_show_all(self) -> None:
        """Submenu S only holds C, which depends on A; resolving A empties S."""
        state = self._dep_state()
        menu_node = next(n for n in state.shown if n.item == MENU)
        assert state.enter_menu(menu_node)
        assert _sc_names(state.shown) == ["C"]

        state.apply_mismatch_resolution(state.kconf.syms["A"], "kconfig", "n", "y")

        assert state.show_all
        assert state.selected_node.item is state.kconf.syms["C"]

        state.kconf.report.reset()

    def test_unresolved_default_mismatch_count_tracks_user_values(self) -> None:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.pilot_mismatch"))
        kconfig.report.reset()
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.pilot_mismatch"))
        state = _make_state(kconfig)

        assert state.unresolved_default_mismatch_count() == 2
        foo = kconfig.syms["FOO"]
        pick = kconfig.named_choices["PICK"]
        state.apply_mismatch_resolution(foo, "kconfig", "1", "2")
        assert state.unresolved_default_mismatch_count() == 1
        state.apply_mismatch_resolution(pick, "sdkconfig", "CA", "CB")
        assert state.unresolved_default_mismatch_count() == 0
        state.clear_mismatch_resolution(foo)
        assert state.unresolved_default_mismatch_count() == 1

        kconfig.report.reset()


def test_mismatch_table_aligns_columns() -> None:
    from rich.text import Text

    rows = [
        ("A", "2", "41"),
        ("SSS", "something very long that will stretch", "something else that is long"),
        ("PICK", "CA", "CB"),
    ]
    kconfig_header, sdkconfig_header = "Kconfig value", "sdkconfig value"
    name_width, kconfig_width, sdkconfig_width, resolution_width = mismatch_column_widths(
        rows, kconfig_header, sdkconfig_header
    )
    widths = (name_width, kconfig_width, sdkconfig_width, resolution_width)
    config_header = Text.from_markup(
        mismatch_table_header("Config name", kconfig_header, sdkconfig_header, *widths)
    ).plain
    choice_header = Text.from_markup(
        mismatch_table_header("Choice name", kconfig_header, sdkconfig_header, *widths)
    ).plain
    config_row = Text.from_markup(mismatch_format_row("A", "2", "41", *widths)).plain
    long_row = Text.from_markup(
        mismatch_format_row("SSS", "something very long that will stretch", "something else that is long", *widths)
    ).plain
    choice_row = Text.from_markup(mismatch_format_row("PICK", "CA", "CB", *widths)).plain
    focused_row = Text.from_markup(mismatch_format_row("A", "2", "41", *widths, focus_col=1)).plain

    assert "Config name" in config_header
    assert "Choice name" in choice_header
    assert "Resolution" in config_header
    assert "(not resolved)" in config_row
    sdk_col = config_header.index("sdkconfig value")
    assert choice_header.index("sdkconfig value") == sdk_col
    assert config_row.index("41") == sdk_col
    assert long_row.index("something else that is long") == sdk_col
    assert choice_row.index("CB") == sdk_col
    assert config_header.index("Resolution") == config_row.index("(not resolved)")
    assert focused_row.index("2") == config_header.index("Kconfig value")
    assert focused_row[focused_row.index("2") - 1] == ">"


def test_mismatch_notice_text_singular_and_plural() -> None:
    from rich.text import Text

    assert "1 default value mismatch" in Text.from_markup(mismatch_notice_text(1)).plain
    assert "2 default value mismatches" in Text.from_markup(mismatch_notice_text(2)).plain
    assert "Press M to review" in Text.from_markup(mismatch_notice_text(2)).plain
