# SPDX-FileCopyrightText: 2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import sys

import pytest

from kconfiglib import Kconfig
from menuconfig import _needs_save
from menuconfig import _restore_default
from menuconfig import menuconfig

TEST_FILES_PATH = os.path.abspath(os.path.dirname(__file__))
KCONFIGS_PATH = os.path.join(TEST_FILES_PATH, "kconfigs")
SDKCONFIGS_PATH = os.path.join(TEST_FILES_PATH, "sdkconfigs", "test_needs_save")


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestNeedsSave:
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

    @pytest.fixture(scope="class", autouse=True)
    def version(self, request):
        # Set the KCONFIG_PARSER_VERSION environment variable
        version = request.param
        os.environ["KCONFIG_PARSER_VERSION"] = version
        yield
        # Clean up after the test
        del os.environ["KCONFIG_PARSER_VERSION"]

    def test_no_change(self) -> None:
        # Nothing changed in the configuration, there should be no need to save.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_PATH, "sdkconfig.no_change")
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        menuconfig(kconfig, headless=True)
        self.assert_and_print_actual(False, kconfig)

    def test_new_symbol_in_kconfig(self) -> None:
        # New symbol is added to the Kconfig file (or removed from sdkconfig file).
        # In other words, there is a symbol in Kconfig which is not in sdkconfig.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_PATH, "sdkconfig.change")
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        menuconfig(kconfig, headless=True)
        self.assert_and_print_actual(True, kconfig)

    def test_reset_from_different_value(self) -> None:
        # Symbol is reset to default value from user value different from default.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_PATH, "sdkconfig.reset_from_different_value")
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        menuconfig(kconfig, headless=True)
        _restore_default(kconfig.syms["CREW"].nodes[0])
        self.assert_and_print_actual(True, kconfig)

    def test_reset_from_same_value(self) -> None:
        # User previously set the value as the same as default.
        # Still need to save in order to add the # default: comment.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_PATH, "sdkconfig.reset_from_same_value")
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        menuconfig(kconfig, headless=True)
        _restore_default(kconfig.syms["CREW"].nodes[0])
        self.assert_and_print_actual(True, kconfig)

    def test_user_value_changed(self) -> None:
        # User changed the value of a symbol which was already user-set.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_PATH, "sdkconfig.user_value_changed")
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig"))
        menuconfig(kconfig, headless=True)
        kconfig.syms["CREW"].set_value("n")
        self.assert_and_print_actual(True, kconfig)

    @pytest.mark.parametrize("defaults_policy", ["sdkconfig", "kconfig"])
    def test_default_value_in_kconfig_changed(self, defaults_policy: str) -> None:
        # Default value of a symbol in Kconfig changed.
        # Using "original sdkconfig" with the "old" default value.
        os.environ["KCONFIG_CONFIG"] = os.path.join(SDKCONFIGS_PATH, "sdkconfig.no_change")
        os.environ["KCONFIG_DEFAULTS_POLICY"] = defaults_policy
        # MOTORS_ENABLED default value changed from "n" to "y"
        kconfig = Kconfig(os.path.join(KCONFIGS_PATH, "Kconfig.default_value_changed"))
        menuconfig(kconfig, headless=True)
        self.assert_and_print_actual(True if defaults_policy == "kconfig" else False, kconfig)
