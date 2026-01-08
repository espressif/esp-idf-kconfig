# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os

import pytest

from kconfiglib import Kconfig

TEST_FILES_PATH = os.path.abspath(os.path.dirname(__file__))
KCONFIG_PATH = os.path.join(TEST_FILES_PATH, "kconfigs")
SDKCONFIGS_PATH = os.path.join(TEST_FILES_PATH, "sdkconfigs")


class TestChoiceLoading:
    """
    Test if special cases for choice loading are working as expected:
    * there are no y-set symbols in the sdkconfig file for given choice (should print info message)
    * y-set symbol is not the first one in the sdkconfig file for given choice:
        * if there is any y-set symbol in the sdkconfig file for given choice, it should NOT print info message
        * otherwise, it is case one
    * multiple y-set symbols in the sdkconfig file for given choice: info should be printed and
      last y-set symbol should be used
    """

    def test_no_y_set_symbols(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        When all choice symbols are set to n in the sdkconfig, an info message should be printed
        and the default selection (ALPHA) should be used.
        """
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.choice_loading"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.choice_all_disabled"))

        captured = capsys.readouterr()

        # Info message should be printed about trying to set the symbol to n
        assert "info:" in captured.err
        assert "Trying to set symbol ALPHA to n" in captured.err
        assert "TEST_CHOICE" in captured.err

        # The default selection (ALPHA) should remain as it's the default
        assert kconfig.syms["ALPHA"].str_value == "y"
        assert kconfig.syms["BETA"].str_value == "n"
        assert kconfig.syms["GAMMA"].str_value == "n"

    def test_y_set_symbol_not_first(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        When a y-set symbol is not the first one in the sdkconfig for a choice,
        but there is a valid y selection, no info message should be printed.
        """
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.choice_loading"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.choice_non_first_userset"))

        captured = capsys.readouterr()

        # No info message should be printed since GAMMA is correctly set to y
        assert "info:" not in captured.err

        # GAMMA should be selected as specified in sdkconfig
        assert kconfig.syms["ALPHA"].str_value == "n"
        assert kconfig.syms["BETA"].str_value == "n"
        assert kconfig.syms["GAMMA"].str_value == "y"

    def test_multiple_y_set_symbols(self, capsys: pytest.CaptureFixture[str]) -> None:
        """
        When multiple choice symbols are set to y in the sdkconfig, an info message should be
        printed and the last y-set symbol should be used.
        """
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.choice_loading"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.choice_multiple_y"))

        captured = capsys.readouterr()

        # Info message should be printed about multiple active selections
        assert "info:" in captured.err
        assert "multiple active selections" in captured.err
        assert "GAMMA" in captured.err  # Last y-set symbol should be mentioned

        # GAMMA should be selected as it's the last y-set symbol
        assert kconfig.syms["ALPHA"].str_value == "n"
        assert kconfig.syms["BETA"].str_value == "n"
        assert kconfig.syms["GAMMA"].str_value == "y"
