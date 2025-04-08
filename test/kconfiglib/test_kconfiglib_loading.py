# SPDX-FileCopyrightText: 2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os

import pytest

from kconfiglib import Kconfig

TEST_FILES_PATH = os.path.abspath(os.path.dirname(__file__))
KCONFIG_PATH = os.path.join(TEST_FILES_PATH, "kconfigs", "Kconfig.default_validity")
SDKCONFIGS_PATH = os.path.join(TEST_FILES_PATH, "sdkconfigs")


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestValidDefaultValue:
    """
    Checking whether default value of incorrect type is correctly detected and ignored.
    NOTE: kconfig checks value several times in different places -> warnings are not always the same.
    """

    @pytest.fixture(scope="class", autouse=True)
    def version(self, request):
        # Set the KCONFIG_PARSER_VERSION environment variable
        version = request.param
        os.environ["KCONFIG_PARSER_VERSION"] = version
        yield
        # Clean up after the test
        del os.environ["KCONFIG_PARSER_VERSION"]

    @pytest.mark.parametrize("sdkconfig", ["sdkconfig.valid_defaults", "sdkconfig.invalid_defaults"])
    def test_defaults_validity(self, capsys: pytest.CaptureFixture, sdkconfig: str) -> None:
        kconfig = Kconfig(KCONFIG_PATH)
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, sdkconfig))
        _, err = capsys.readouterr()

        names_and_valid_values = {
            "BOOL_CONFIG": "y",
            "INT_CONFIG": "1",
            "HEX_CONFIG": "0x42",
            "STRING_CONFIG": "string",
        }

        for name in names_and_valid_values:
            assert kconfig.syms[name].str_value == names_and_valid_values[name]

        # kconfiglib checks string and bool values ahead "normal" checks and uses different messages
        # FIXME after this warning will be converted to kconfiglib report
        stderr_lines = (
            "Failed to set default value for HEX_CONFIG from sdkconfig",
            "Failed to set default value for INT_CONFIG from sdkconfig",
            "'0x42' is not a valid value for the bool symbol BOOL_CONFIG",
            "malformed string literal in assignment to",
        )  # STRING_CONFIG
        for line in stderr_lines:
            if sdkconfig == "sdkconfig.invalid_defaults":
                assert line in err
            else:
                assert line not in err
