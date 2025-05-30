# SPDX-FileCopyrightText: 2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import sys
from typing import TYPE_CHECKING
from typing import Union

import pytest

if TYPE_CHECKING:
    from kconfiglib.core import Choice
    from kconfiglib.core import Symbol

from kconfiglib import Kconfig
from menuconfig import _needs_save
from menuconfig import _restore_default
from menuconfig import menuconfig

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
        assert kconfig.syms["FOO"].has_default_value() is True
        assert kconfig.syms["BAR"].has_default_value() is True
        assert kconfig.syms["QUX"].has_default_value() is True
        assert kconfig.syms["BAZ"].has_default_value() is True

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
        assert kconfig.syms["BAZ"].has_default_value() is False
        assert kconfig.syms["QUX"].has_default_value() is False
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

        assert kconfig.syms["FOO"].has_default_value() is False
        assert kconfig.syms["BAR"].has_default_value() is False
        assert kconfig.syms["BAZ"].has_default_value() is False
        assert kconfig.syms["QUX"].has_default_value() is False

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
