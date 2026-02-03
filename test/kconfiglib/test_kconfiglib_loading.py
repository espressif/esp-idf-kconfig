# SPDX-FileCopyrightText: 2025-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os

import pytest

from esp_kconfiglib import Kconfig
from esp_kconfiglib.core import STR_TO_BOOL
from esp_kconfiglib.core import TYPE_TO_STR

TEST_FILES_PATH = os.path.abspath(os.path.dirname(__file__))
KCONFIG_PATH = os.path.join(TEST_FILES_PATH, "kconfigs")
SDKCONFIGS_PATH = os.path.join(TEST_FILES_PATH, "sdkconfigs")


class TestBase:
    @pytest.fixture(scope="class", autouse=True)
    def version(self, request):
        # Set the KCONFIG_PARSER_VERSION environment variable
        version = request.param
        os.environ["KCONFIG_PARSER_VERSION"] = version
        yield
        # Clean up after the test
        del os.environ["KCONFIG_PARSER_VERSION"]


class TestDefaultsBase(TestBase):
    """
    Base class for tests that check default values in Kconfig.
    It sets the KCONFIG_PARSER_VERSION environment variable based on the test parameter.
    """

    @pytest.fixture(scope="class")
    def policy(self, request):
        # Set the KCONFIG_DEFAULTS_POLICY environment variable
        policy = request.param
        os.environ["KCONFIG_DEFAULTS_POLICY"] = policy
        yield
        # Clean up after the test
        del os.environ["KCONFIG_DEFAULTS_POLICY"]


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

        kconfig.report.reset()


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
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

        kconfig.report.reset()


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestDefaultMismatchReport(TestDefaultsBase):
    """
    Ensure symbol default mismatches are included in the report.
    """

    @pytest.mark.parametrize("policy", ["sdkconfig", "kconfig"], indirect=True)
    def test_symbol_default_mismatch_reported(self, policy: pytest.FixtureDef) -> None:
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.inversed_dep_order_1"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.inversed_dep_order_1"))
        report_json = kconfig.report._return_json()

        defaults_area = next(
            (area for area in report_json["areas"] if area["title"] == "Default Value Mismatch"),
            None,
        )
        assert defaults_area is not None

        changed_defaults = defaults_area["data"]["changed_defaults"]
        changed_names = {entry["name"] for entry in changed_defaults}
        assert {"FREE_0", "FREE_1", "FREE_2", "FREE_3"}.issubset(changed_names)
        if os.environ["KCONFIG_DEFAULTS_POLICY"] == "sdkconfig":
            assert {"DEPENDENT_0", "DEPENDENT_1"}.issubset(changed_names)
        elif os.environ["KCONFIG_DEFAULTS_POLICY"] == "kconfig":
            assert {"DEPENDENT_0", "DEPENDENT_1"}.isdisjoint(changed_names)

        kconfig.report.reset()


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestLoadingChoicesWithDefaults(TestDefaultsBase):
    """
    Checking whether choices with default values are loaded correctly.
    """

    @pytest.mark.parametrize("policy", ["sdkconfig", "kconfig"], indirect=True)
    def test_loading_choice_with_different_default(self, policy: pytest.FixtureDef) -> None:
        """
        Test loading a choice with different default values in sdkconfig and Kconfig.
        Checking JSON report for information.
        """
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.choices"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.choice.different_default"))
        output_sdkconfig = kconfig._config_contents(header=None)
        report_json = kconfig.report._return_json()
        changed_choices = [area for area in report_json["areas"] if area["title"] == "Default Value Mismatch"][0][
            "data"
        ]["changed_choices"]

        assert "Info" in report_json["header"]["status"]
        assert "CHOICE" in (changed_choice["name"] for changed_choice in changed_choices)
        assert (
            "FIRST"
            == [
                changed_choice["kconfig_selection"]
                for changed_choice in changed_choices
                if changed_choice["name"] == "CHOICE"
            ][0]
        )
        assert (
            "SECOND"
            == [
                changed_choice["sdkconfig_selection"]
                for changed_choice in changed_choices
                if changed_choice["name"] == "CHOICE"
            ][0]
        )

        if os.environ["KCONFIG_DEFAULTS_POLICY"] == "kconfig":
            assert "kconfig" in report_json["header"]["defaults_policy"]
            assert "CONFIG_FIRST=y" in output_sdkconfig
            assert "CONFIG_SECOND is not set" in output_sdkconfig
        elif os.environ["KCONFIG_DEFAULTS_POLICY"] == "sdkconfig":
            assert "CONFIG_FIRST is not set" in output_sdkconfig
            assert "CONFIG_SECOND=y" in output_sdkconfig

        assert "CONFIG_THIRD is not set" in output_sdkconfig

        kconfig.report.reset()

    @pytest.mark.parametrize("policy", ["sdkconfig", "kconfig"], indirect=True)
    def test_loading_choice_dependent_on_symbol(self, policy: pytest.FixtureDef) -> None:
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.choices"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.dependent_choice"))
        output_sdkconfig = kconfig._config_contents(header=None)
        report_json = kconfig.report._return_json()
        assert "Info" in report_json["header"]["status"]

        if os.environ["KCONFIG_DEFAULTS_POLICY"] == "sdkconfig":
            changed_choices = [area for area in report_json["areas"] if area["title"] == "Default Value Mismatch"][0][
                "data"
            ]["changed_choices"]
            dependent_choice = next(
                (changed_choice for changed_choice in changed_choices if changed_choice["name"] == "DEPENDENT_CHOICE"),
                None,
            )
            assert dependent_choice is not None
            assert "DEPENDENT_FIRST" == dependent_choice["kconfig_selection"]
            assert "DEPENDENT_SECOND" == dependent_choice["sdkconfig_selection"]

        if os.environ["KCONFIG_DEFAULTS_POLICY"] == "kconfig":
            assert "kconfig" in report_json["header"]["defaults_policy"]
            assert "CONFIG_DEPENDENT_FIRST" not in output_sdkconfig
            assert "CONFIG_DEPENDENT_SECOND" not in output_sdkconfig
        elif os.environ["KCONFIG_DEFAULTS_POLICY"] == "sdkconfig":
            assert "CONFIG_FIRST=y" in output_sdkconfig
            assert "CONFIG_SECOND is not set" in output_sdkconfig

        kconfig.report.reset()

    def test_choice_having_non_first_default_value(self) -> None:
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.choice_non_first_default"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.choice_non_first_default"))
        output_sdkconfig = kconfig._config_contents(header=None)
        report_json = kconfig.report._return_json()

        # Nothing should be reported
        assert "OK" in report_json["header"]["status"]

        # Nothing should be changed
        assert "CONFIG_ALPHA is not set" in output_sdkconfig
        assert "CONFIG_BETA=y" in output_sdkconfig
        assert "CONFIG_GAMMA is not set" in output_sdkconfig

        kconfig.report.reset()


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestLoadingUserSetChoice(TestBase):
    """
    Test loading user-set choice symbols from sdkconfig.
    """

    def test_loading_user_set_choice(self):
        # Reusing Kconfig from another test case to avoid duplication -
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.choice_loading"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.choice_non_first_userset"))

        # Report should be empty
        report_json = kconfig.report._return_json()
        assert "OK" in report_json["header"]["status"]
        assert report_json["areas"] == []

        # Symbol values should be unchanged
        assert kconfig.syms["ALPHA"].str_value == "n"
        assert kconfig.syms["BETA"].str_value == "n"
        assert kconfig.syms["GAMMA"].str_value == "y"

        kconfig.report.reset()

    def test_loading_choice_all_disabled(self):
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.choice_loading"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.choice_all_disabled"))
        report_json = kconfig.report._return_json()
        assert "Info" in report_json["header"]["status"]
        misc_area = next((area for area in report_json["areas"] if area["title"] == "Miscellaneous"), None)
        assert misc_area is not None
        assert (
            "Trying to set symbol ALPHA to n, but it is currently selected by choice TEST_CHOICE. "
            "For setting it to n, set another choice symbol to y instead." in misc_area["data"]
        )

        assert kconfig.syms["ALPHA"].str_value == "y"
        assert kconfig.syms["BETA"].str_value == "n"
        assert kconfig.syms["GAMMA"].str_value == "n"
        kconfig.report.reset()


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestMultipleValueSet(TestBase):
    """
    Test cases test what happens if one config option is set multiple times.

    If the symbol/choice is set in multiple files (sdkconfig.defaults and sdkconfig),
    the last value should be used and no warning should be produced.

    If the symbol/choice is set multiple times in the same file, expected behavior follows:
    Symbol:
        * Last user-set value is used (even if default values follow)
        * If no user-set values are provided, last default value is used
    If there is more than one value (no matter whether user-set, default or a mix) a warning is printed.

    Choice:
        * Last choice symbol user-set to y is considered choice selection
        * If no choice symbol user-set to y is provided, last choice symbol with default value is used

    NOTE: After every test, we need to run kconfig.report.reset(). KconfigReport is a singleton,
    which is normally OK (we do not use multiple Kconfig instances in one script). However, tests are
    an exception, so we need to make sure the singleton is clear after each test.
    """

    def test_symbols(self):
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.multiple_value_set"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.multiset_symbols"))

        output_sdkconfig = kconfig._config_contents(header=None)
        json_report = kconfig.report._return_json()
        multiple_assignments = [area for area in json_report["areas"] if area["title"] == "Multiple Assignments"][0]

        assert "CONFIG_CONTROL=1" in output_sdkconfig
        assert 'CONFIG_MULTIPLE_DEFAULT="d3"' in output_sdkconfig
        assert 'CONFIG_MULTIPLE_COMMON="c3"' in output_sdkconfig

        assert "CONTROL" not in multiple_assignments["data"]["symbols"]
        assert "MULTIPLE_DEFAULT" in multiple_assignments["data"]["symbols"]
        assert "MULTIPLE_COMMON" in multiple_assignments["data"]["symbols"]

        kconfig.report.reset()

    def test_choices(self):
        """
        Test that last user-set value is used for choices.
        """
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.multiple_value_set"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.multiset_choices"))
        output_sdkconfig = kconfig._config_contents(header=None)
        json_report = kconfig.report._return_json()

        multiple_assignments = [area for area in json_report["areas"] if area["title"] == "Multiple Assignments"][0]

        # Control choice
        ################
        assert "CONFIG_ALPHA_CONTROL=y" in output_sdkconfig
        assert "CONFIG_BETA_CONTROL is not set" in output_sdkconfig
        assert "CONFIG_GAMMA_CONTROL is not set" in output_sdkconfig
        assert "CHOICE_CONTROL" not in multiple_assignments["data"]["choices"]

        # Multiple default values, out of order
        #######################################
        assert "CONFIG_ALPHA_DEFAULT is not set" in output_sdkconfig
        assert "CONFIG_BETA_DEFAULT is not set" in output_sdkconfig
        assert "CONFIG_GAMMA_DEFAULT=y" in output_sdkconfig
        assert "CHOICE_DEFAULT" in multiple_assignments["data"]["choices"]

        # Multiple default and user-set values, out of order
        ####################################################
        assert "CONFIG_ALPHA_COMMON is not set" in output_sdkconfig
        assert "CONFIG_BETA_COMMON=y" in output_sdkconfig
        assert "CONFIG_GAMMA_COMMON is not set" in output_sdkconfig
        assert "CHOICE_COMMON" in multiple_assignments["data"]["choices"]

        # Multiple default values, in order
        ###################################
        assert "CONFIG_ALPHA_SECOND_DEFAULT is not set" in output_sdkconfig
        assert "CONFIG_BETA_SECOND_DEFAULT is not set" in output_sdkconfig
        assert "CONFIG_GAMMA_SECOND_DEFAULT=y" in output_sdkconfig
        assert "CHOICE_SECOND_DEFAULT" in multiple_assignments["data"]["choices"]

        # Multiple default and user-set values, in order
        ################################################
        assert "CONFIG_ALPHA_SECOND_COMMON is not set" in output_sdkconfig
        assert "CONFIG_BETA_SECOND_COMMON is not set" in output_sdkconfig
        assert "CONFIG_GAMMA_SECOND_COMMON=y" in output_sdkconfig
        assert "CHOICE_SECOND_COMMON" in multiple_assignments["data"]["choices"]

        assert "Info" in json_report["header"]["status"]
        misc_area = next((area for area in json_report["areas"] if area["title"] == "Miscellaneous"), None)
        assert misc_area is not None
        assert (
            "Choice CHOICE_SECOND_COMMON has multiple active selections. "
            "The last one will be used: GAMMA_SECOND_COMMON ." in misc_area["data"]
        )

        kconfig.report.reset()

    def test_echo_into_sdkconfig(self):
        """
        This test ensures special case user often do works:
        1) Generate sdkconfig from Kconfig
        2) echo "CONFIG_FOO=y" >> sdkconfig
        3) Run Kconfig again
        Expected result: FOO should be set to y, no matter if it is a config option or a choice option.
        In case of choice, the rest should be set to n and user-set.
        """
        SDKCONFIG_TMP = "sdkconfig.tmp"

        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.multiple_value_set"))
        kconfig.write_config(os.path.join(SDKCONFIGS_PATH, SDKCONFIG_TMP))

        config_contents = kconfig._config_contents(header=None)
        assert "CONFIG_CONTROL=1" in config_contents
        assert "CONFIG_ALPHA_CONTROL=y" in config_contents
        assert "CONFIG_BETA_CONTROL is not set" in config_contents
        assert "CONFIG_GAMMA_CONTROL is not set" in config_contents

        # equivalent to:
        # $ echo "CONFIG_CONTROL=42" >> sdkconfig.tmp && echo "CONFIG_BETA_CONTROL=y" >> sdkconfig.tmp
        with open(os.path.join(SDKCONFIGS_PATH, SDKCONFIG_TMP), "a") as f:
            f.write("CONFIG_CONTROL=42\n")
            f.write("CONFIG_BETA_CONTROL=y\n")

        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, SDKCONFIG_TMP))
        new_config_contents = kconfig._config_contents(header=None)
        assert "CONFIG_CONTROL=42" in new_config_contents
        assert "CONFIG_CONTROL=1" not in new_config_contents

        assert "CONFIG_ALPHA_CONTROL is not set" in new_config_contents
        assert "CONFIG_BETA_CONTROL=y" in new_config_contents
        assert "CONFIG_GAMMA_CONTROL is not set" in new_config_contents

        os.remove(os.path.join(SDKCONFIGS_PATH, SDKCONFIG_TMP))
        kconfig.report.reset()


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestLoadingDeprecated(TestBase):
    """
    Test ensures deprecated values are loaded correctly
    if given flag (load_deprecated) is set in kconfig.load_config().

    If the flag is set, the deprecated values should:
    * Be loaded into the Kconfig and used in expression evaluation
    * All should have correct type.
    * Should NOT be written out to sdkconfig.
    """

    @pytest.fixture
    def deprecated_names(self):
        return [
            "OLD_BOOL",
            "OLD_STRING",
            "OLD_HEX",
            "OLD_INT",
            "OLD_BOOL_INVERTED",
        ]

    @pytest.fixture
    def expressions(self):
        return [
            # Expressions without deprecated values
            ("NEW_BOOL=y", "y"),
            ('NEW_STRING="test"', "y"),
            ("NEW_HEX=0xbeef", "y"),
            ("NEW_INT=42", "y"),
            ("NEW_INT<42 || NEW_BOOL=y", "y"),
            ("NEW_BOOL=n && NEW_HEX=0xdeadbeef", "n"),
            ('NEW_STRING="something different"', "n"),
            # Expressions with deprecated values
            ("OLD_BOOL=y", "y"),
            ('OLD_STRING="test"', "y"),
            ("OLD_HEX=0xbeef", "y"),
            ("OLD_INT=42", "y"),
            ("OLD_BOOL_INVERTED=n", "y"),
            ("OLD_INT<42 || OLD_BOOL=y", "y"),
            ("OLD_BOOL=y && OLD_HEX=0xdeadbeef", "n"),
            ('OLD_STRING="something different"', "n"),
        ]

    def test_flag_unset(self, deprecated_names, expressions):
        """
        Unset flag should mean deprecated values are not loaded.
        """
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.deprecated_vals"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.deprecated_vals"))

        # Ensure deprecated names are not in kconfig.syms nor in output
        for name in deprecated_names:
            assert name not in kconfig.syms
            assert "CONFIG_" + name not in kconfig._config_contents(header=None)

        for expression, expected_result in expressions:
            if "NEW" in expression:
                assert kconfig.eval_string(expression) == STR_TO_BOOL[expected_result]
            else:  # expressions with deprecated names should always evaluate to "n"
                assert kconfig.eval_string(expression) == STR_TO_BOOL["n"]

        kconfig.report.reset()

    def test_flag_set(self, deprecated_names, expressions):
        """
        Set flag should mean deprecated values are loaded.
        """

        def name_to_type(name: str) -> str:
            if "BOOL" in name:
                return "bool"
            if "STRING" in name:
                return "string"
            if "HEX" in name:
                return "hex"
            if "INT" in name:
                return "int"
            return "unknown"

        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.deprecated_vals"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.deprecated_vals"), load_deprecated=True)

        # Ensure deprecated names are in kconfig.syms, but not in output
        # Also ensure the type is correctly guessed
        for name in deprecated_names:
            assert name in kconfig.syms
            assert "CONFIG_" + name not in kconfig._config_contents(header=None)
            assert name_to_type(name) == TYPE_TO_STR[kconfig.syms[name].orig_type]

        for expression, expected_result in expressions:
            try:
                assert kconfig.eval_string(expression) == STR_TO_BOOL[expected_result]
            except AssertionError:
                print(f"§OLD_STRING = {kconfig.syms['OLD_STRING'].str_value}")
                raise

        kconfig.report.reset()


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestDisabledSymbols(TestBase):
    """
    Test ensures disabled symbols/choices with user-set value are reported correctly.
    """

    def test_disabled_symbols(self):
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.disabled_symbols_choices"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.disabled_symbols_choices"))
        report_json = kconfig.report._return_json()
        area = next(
            (area for area in report_json["areas"] if area["title"] == "Disabled Symbols/Choices With User-Set Value"),
            None,
        )
        assert area is not None, "Disabled Symbols/Choices With User-Set Value area not found in report"

        assert "DISABLED_SYMBOL" in area["data"]["symbols"]
        assert "y" in area["data"]["symbols"]["DISABLED_SYMBOL"]["value"]
        assert "sdkconfig.disabled_symbols_choices" in area["data"]["symbols"]["DISABLED_SYMBOL"]["source"]

        assert "DISABLED_INT" in area["data"]["symbols"]
        assert "42" in area["data"]["symbols"]["DISABLED_INT"]["value"]
        assert "sdkconfig.disabled_symbols_choices" in area["data"]["symbols"]["DISABLED_INT"]["source"]

        assert "INSIDE_MENU" in area["data"]["symbols"]
        assert "hi" in area["data"]["symbols"]["INSIDE_MENU"]["value"]
        assert "sdkconfig.disabled_symbols_choices" in area["data"]["symbols"]["INSIDE_MENU"]["source"]

        assert "DISABLED_CHOICE" in area["data"]["choices"]
        assert "CHOICE_B" in area["data"]["choices"]["DISABLED_CHOICE"]["value"]
        assert "sdkconfig.disabled_symbols_choices" in area["data"]["choices"]["DISABLED_CHOICE"]["source"]

        kconfig.report.reset()


@pytest.mark.parametrize("version", ["1", "2"], indirect=True)
class TestDefaultPragmaRegression(TestBase):
    """
    There was a regression that the default pragma got unintentionally
    applied over to the next symbol if current symbol was not part of the configuration
    (not in any of the loaded Kconfig files).
    """

    def test_default_pragma_regression(self):
        kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.default_pragma_regression"))
        kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.default_pragma_regression"))
        tested_symbol = kconfig.syms["PRAGMA_TEST"]
        assert tested_symbol.str_value == "y"
        # default pragma should not be transferred to this symbol
        assert not tested_symbol._loaded_as_default
        # sdkconfig value correctly loaded
        assert tested_symbol.str_value == "y"

        kconfig.report.reset()
