# SPDX-FileCopyrightText: 2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import sys
from typing import TYPE_CHECKING
from typing import Any
from typing import Dict
from typing import Union

import pytest

from esp_menuconfig.core import _change_node

if TYPE_CHECKING:
    from esp_kconfiglib.core import Choice
    from esp_kconfiglib.core import Symbol

from esp_kconfiglib import Kconfig
from esp_menuconfig import _needs_save
from esp_menuconfig import _restore_default
from esp_menuconfig import menuconfig

TEST_FILES_PATH = os.path.abspath(os.path.dirname(__file__))
KCONFIGS_PATH = os.path.join(TEST_FILES_PATH, "kconfigs")
SDKCONFIGS_PATH = os.path.join(TEST_FILES_PATH, "sdkconfigs")
SDKCONFIGS_NEEDS_SAVE_PATH = os.path.join(SDKCONFIGS_PATH, "test_needs_save")
SDKCONFIGS_CHOICE_DEFAULT_PATH = os.path.join(SDKCONFIGS_PATH, "test_choice_defaults")


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
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_NEEDS_SAVE_PATH, "sdkconfig.change")
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
    def test_default_value_in_kconfig_changed(self, defaults_policy: str) -> None:
        # Default value of a symbol in Kconfig changed.
        # Using "original sdkconfig" with the "old" default value.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_NEEDS_SAVE_PATH, "sdkconfig.no_change")
        os.environ["KCONFIG_DEFAULTS_POLICY"] = defaults_policy
        # MOTORS_ENABLED default value changed from "n" to "y"
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.default_value_changed"))
        menuconfig(kconfig, headless=True)
        self.assert_and_print_actual(True if defaults_policy == "kconfig" else False, kconfig)


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestChoicesDefault(MenuconfigTestBase):
    """
    Test if menuconfig can handle default values for choice symbols correctly.
    Inherently, it also tests if the default value is correctly handled in Kconfig.
    """

    def _change_node_monkeypatch(self, sc: Union["Symbol", "Choice"]) -> None:
        """
        Cannot use _change_node() from menuconfig (does not work in headless mode)
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

        # Check if the value was changed correctly
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


@pytest.mark.parametrize("version", ["2"], indirect=True)
class TestIndirectlySetValues(MenuconfigTestBase):
    """
    Test if menuconfig correctly handles values indirectly set via "set" and "set default" options.
    NOTE: Only for KCONFIG_PARSER_VERSION=2, as this is the only version which supports indirectly set values.
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

        sym = kconfig.syms["SET_TARGET"]
        assert sym.str_value == "4"  # indirectly set value has absolute precedence
        assert sym._user_value == "2"  # user-set value is preserved, but ignored

        assert _change_node(sym.nodes[0]) is False, "Changing indirectly set value should not be allowed, but it was."

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
    Test if menuconfig correctly handles 'warning' option for symbols: key_dialog should be called
    to confirm changing the value of a risky symbol, but only if the symbol is not already user-set.
    """

    @pytest.fixture
    def monkeypatch_menuconfig(self):
        """
        Fixture to monkeypatch menuconfig core functions for testing.
        Provides mock implementations for key_dialog, input_dialog, and update_menu.
        """
        import esp_menuconfig.core

        # Store original functions
        original_key_dialog = esp_menuconfig.core._key_dialog
        original_input_dialog = esp_menuconfig.core._input_dialog
        original_update_menu = esp_menuconfig.core._update_menu

        # Track if key_dialog was called
        mock_state = {"key_dialog_called": False}

        def mock_key_dialog(title, text, keys):
            mock_state["key_dialog_called"] = True
            assert title == "Set dangerous option?"
            assert keys == "yn"
            assert "This symbol has a following warning:" in text
            return "y"

        def mock_input_dialog(title, initial_text, info_text=None):
            return "999"  # New, "user-set" value for the int symbol

        def reset_key_dialog_called():
            mock_state["key_dialog_called"] = False

        # Apply monkeypatches
        esp_menuconfig.core._key_dialog = mock_key_dialog
        esp_menuconfig.core._input_dialog = mock_input_dialog
        esp_menuconfig.core._update_menu = lambda: None  # Disable menu updates in tests

        # Yield the mock state tracker
        yield {
            "key_dialog_called": lambda: mock_state["key_dialog_called"],
            "reset_key_dialog_called": reset_key_dialog_called,
        }

        # Restore original functions
        esp_menuconfig.core._key_dialog = original_key_dialog
        esp_menuconfig.core._input_dialog = original_input_dialog
        esp_menuconfig.core._update_menu = original_update_menu

    @pytest.mark.parametrize("parser_version", (1, 2))
    def test_set_risky_config(self, monkeypatch_menuconfig: Dict[str, Any], parser_version: int) -> None:
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.warning"), parser_version=parser_version)
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "test_warning", "sdkconfig.warning"))

        # key = symbol name, value = (key_dialog should be printed, new value after changing)
        sym_names = {
            "RISKY_BOOL": (True, "y"),
            "RISKY_INT": (True, "999"),
            "ALREADY_USER_SET_RISKY_INT": (False, "999"),
        }

        for sym_name in sym_names:
            assert kconfig.syms[sym_name].warning != "", f"Symbol {sym_name} should be marked as risky, but is not."

        for sym_name, (should_call_key_dialog, new_value) in sym_names.items():
            sym = kconfig.syms[sym_name]
            monkeypatch_menuconfig["reset_key_dialog_called"]()
            assert _change_node(sym.nodes[0]) is True, f"Changing value of symbol {sym_name} should be allowed."
            assert sym.str_value == new_value, (
                f"Value of symbol {sym_name} should be changed to {new_value}, but is {sym.str_value}."
            )
            assert monkeypatch_menuconfig["key_dialog_called"]() is should_call_key_dialog, (
                f"key_dialog should {'be' if should_call_key_dialog else 'not be'} called when changing "
                f"the value of symbol {sym_name}, but it was"
                f"{' not' if not monkeypatch_menuconfig['key_dialog_called']() else ''}."
            )
