# SPDX-FileCopyrightText: 2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os

import pytest

from esp_kconfiglib import Kconfig

TEST_FILES_PATH = os.path.abspath(os.path.dirname(__file__))
KCONFIG_PATH = os.path.join(TEST_FILES_PATH, "kconfigs")
SDKCONFIGS_PATH = os.path.join(TEST_FILES_PATH, "sdkconfigs")


class TestDefaultsBase:
    """
    Base class for tests that check default values in Kconfig.
    It sets the KCONFIG_PARSER_VERSION environment variable based on the test parameter.
    """

    @pytest.fixture(scope="class", autouse=True)
    def version(self, request):
        # Set the KCONFIG_PARSER_VERSION environment variable
        version = request.param
        os.environ["KCONFIG_PARSER_VERSION"] = version
        yield
        # Clean up after the test
        del os.environ["KCONFIG_PARSER_VERSION"]


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestValidDefaultValue(TestDefaultsBase):
    """
    Checking whether default value of incorrect type is correctly detected and ignored.
    NOTE: kconfig checks value several times in different places -> warnings are not always the same.
    """

    @pytest.mark.parametrize("sdkconfig", ["sdkconfig.valid_defaults", "sdkconfig.invalid_defaults"])
    def test_defaults_validity(self, capsys: pytest.CaptureFixture, sdkconfig: str) -> None:
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.default_validity"))
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


@pytest.mark.parametrize("version", ["2"], indirect=True)
class TestLoadingDefaults(TestDefaultsBase):
    """
    Checking whether default values are loaded correctly:
        * promptless symbols ignore their default values from sdkconfig silently
        * If a dependent symbol is loaded before the "dependee", both symbols should be loaded correctly
    """

    def test_defaults_loading(self, capsys: pytest.CaptureFixture) -> None:
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.loading_defaults"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.differing_defaults"))
        _, err = capsys.readouterr()

        # Check stderr for expected messages
        assert "Default value for DEPENDEE" in err
        assert "Default value for DEP" in err
        assert "Default value for PROMPTLESS" not in err, (
            "Promptless symbols should ignore their default values from sdkconfig"
        )

        out_sdkconfig = kconfig._config_contents(header=None)

        # Check output sdkconfig for expected values
        assert "CONFIG_DEPENDEE is not set" in out_sdkconfig
        assert "CONFIG_DEP=1" in out_sdkconfig
        assert "CONFIG_PROMPTLESS_Y=y" in out_sdkconfig
        assert "CONFIG_PROMPTLESS_N" not in out_sdkconfig, (
            "Promptless symbols should not be present in the output sdkconfig"
        )
