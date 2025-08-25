#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2018-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import filecmp
import os
import shutil
from dataclasses import dataclass
from typing import Optional

import pytest

from kconfcheck.core import CONFIG_NAME_MAX_LENGTH
from kconfcheck.core import IndentAndNameChecker
from kconfcheck.core import InputError
from kconfcheck.core import LineRuleChecker
from kconfcheck.core import SourceChecker
from kconfcheck.core import validate_file


class ApplyLine:
    def apply_line(self, string):
        self.checker.process_line(string + "\n", 0)

    def expect_error(self, string, expect, cleanup=None):
        try:
            with pytest.raises(InputError) as err:
                self.apply_line(string)
            if expect:
                assert err.value.suggested_line == (expect + "\n")
        finally:
            if cleanup:
                # cleanup of the previous failure
                self.apply_line(cleanup)

    def expect_success(self, string):
        assert self.apply_line(string) is None


class TestLineRuleChecker(ApplyLine):
    @pytest.fixture
    def prepare_checker(_):
        return LineRuleChecker("Kconfig")

    def test_tabulators(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_error("\ttest", expect="    test")
        self.expect_error("\t    test", expect="        test")
        self.expect_error("   \ttest", expect="       test")
        self.expect_error("     \t     test", expect="              test")
        self.expect_success("         test")
        self.expect_success("test")

    def test_trailing_whitespaces(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_error(" ", expect="")
        self.expect_error("     ", expect="")
        self.expect_error("test ", expect="test")
        self.expect_success("test")
        self.expect_success("")

    def test_line_length(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_error("x" * 120, expect=None)
        self.expect_success("x" * 119)
        self.expect_success("")


class TestSourceChecker(ApplyLine):
    @pytest.fixture
    def prepare_checker(_):
        return SourceChecker("Kconfig")

    def test_source_file_name(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_error('source "notKconfig.test"', expect='source "Kconfig.notKconfig.test"')
        self.expect_error('source "Kconfig"', expect='source "Kconfig.Kconfig"')
        self.expect_success('source "Kconfig.in"')
        self.expect_success('source "/tmp/Kconfig.test"')
        self.expect_success('source "/tmp/Kconfig.in"')
        self.expect_error('source"Kconfig.in"', expect='source "Kconfig.in"')
        self.expect_success('source "/tmp/Kconfig.in"  # comment')
        self.expect_error('source "$ENV_VAR/unsupported_name"', expect='source "$ENV_VAR/Kconfig.unsupported_name"')
        self.expect_error('source "$ENV_VAR"', expect='source "$ENV_VAR/Kconfig.<suffix>"')
        # special envvars that are ok even if they are not specifying Kconfig file name explicitly
        self.expect_success('source "$COMPONENT_KCONFIGS_SOURCE_FILE"')
        self.expect_success('source "$COMPONENT_KCONFIGS_PROJBUILD_SOURCE_FILE"')
        self.expect_success('source "$COMPONENT_KCONFIGS_EXCLUDED_SOURCE_FILE"')
        self.expect_success('source "$COMPONENT_KCONFIGS_PROJBUILD_EXCLUDED_SOURCE_FILE"')


class TestIndentAndNameChecker(ApplyLine):
    @pytest.fixture
    def prepare_checker(_, request):
        checker = IndentAndNameChecker("Kconfig")
        checker.min_prefix_length = request.param

        yield checker
        checker.finalize()


@pytest.mark.parametrize("prepare_checker", (0,), indirect=True)
class TestIndent(TestIndentAndNameChecker):
    def test_indent_characters(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success('menu "test"')
        self.expect_error(" test", expect="    test")
        self.expect_error("  test", expect="    test")
        self.expect_error("   test", expect="    test")
        self.expect_error("     test", expect="    test")
        self.expect_success("    test")
        self.expect_success("    test2")
        self.expect_success("    config")
        self.expect_error("    default", expect="        default")
        self.expect_success("        help")
        self.expect_error("         text", expect="            text")
        self.expect_success("            help text")
        self.expect_success("    menu")
        self.expect_success("    endmenu")
        self.expect_error("         choice", expect="    choice", cleanup="    endchoice")
        self.expect_error("       choice", expect="    choice", cleanup="    endchoice")
        self.expect_success("    choice")
        self.expect_success("    endchoice")
        self.expect_success("    config")
        self.expect_success("endmenu")

    def test_help_content(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success('menu "test"')
        self.expect_success("    config CONFIG_NAME")
        self.expect_success("        help")
        self.expect_success("            description")
        self.expect_success("            config keyword in the help")
        self.expect_success("            menu keyword in the help")
        self.expect_success("            menuconfig keyword in the help")
        self.expect_success("            endmenu keyword in the help")
        self.expect_success("            endmenu keyword in the help")
        self.expect_success("")  # newline in help
        self.expect_success("            endmenu keyword in the help")
        self.expect_error(
            '          menu "real menu with wrong indent"',
            expect='    menu "real menu with wrong indent"',
            cleanup="    endmenu",
        )
        self.expect_success("endmenu")

    def test_mainmenu(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success('mainmenu "test"')
        self.expect_error("test", expect="    test")
        self.expect_success("    not_a_keyword")
        self.expect_success("    config")
        self.expect_success("    menuconfig MENUCONFIG_NAME")
        self.expect_error("test", expect="        test")
        self.expect_error("   test", expect="        test")
        self.expect_success("    menu")
        self.expect_success("    endmenu")

    def test_ifendif(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success('menu "test"')
        self.expect_success("    config")
        self.expect_success("        help")
        self.expect_error("        if", expect="    if", cleanup="    endif")
        self.expect_success("    if")
        self.expect_error("    config", expect="        config")
        self.expect_success("        config")
        self.expect_success("            help")
        self.expect_success("    endif")
        self.expect_success("    config")
        self.expect_success("endmenu")

    def test_config_without_menu(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success("menuconfig MENUCONFIG_NAME")
        self.expect_success("    help")
        self.expect_success("        text")
        self.expect_success("")
        self.expect_success("        text")
        self.expect_success("config")
        self.expect_success("    help")

    def test_source_after_config(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success("menuconfig MENUCONFIG_NAME")
        self.expect_success("    help")
        self.expect_success("        text")
        self.expect_error("    source", expect="source")
        self.expect_success('source "Kconfig.in"')

    def test_comment_after_config(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success("menuconfig MENUCONFIG_NAME")
        self.expect_success("    # comment")
        self.expect_success("    help")
        self.expect_success("        text")
        self.expect_success('        # second not realcomment"')

    def test_missing_endmenu(self, prepare_checker):
        """
        IndentAndNameChecker raises RuntimeError if there is missing endmenu of inner menu
        """
        self.checker = prepare_checker
        self.expect_success('menu "test"')
        self.expect_success("    config FOO")
        self.expect_success("        bool")
        self.expect_success('    menu "inner menu"')
        self.expect_success("        config FOO_BAR")
        self.expect_success("            bool")
        with pytest.raises(RuntimeError):
            self.checker.finalize()


@pytest.mark.parametrize("prepare_checker", (0,), indirect=True)
class TestName(TestIndentAndNameChecker):
    def test_name_length(self, prepare_checker):
        self.checker = prepare_checker
        max_length = CONFIG_NAME_MAX_LENGTH
        too_long = max_length + 1
        self.expect_success('menu "test"')
        self.expect_success("    config ABC")
        self.expect_success("    config " + ("X" * max_length))
        self.expect_error("    config " + ("X" * too_long), expect=None)
        self.expect_success("    menuconfig " + ("X" * max_length))
        self.expect_error("    menuconfig " + ("X" * too_long), expect=None)
        self.expect_success("    choice " + ("X" * max_length))
        self.expect_error("    choice " + ("X" * too_long), expect=None)
        self.expect_success("endmenu")

    def test_name_sanity(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success('prompt "test" if OK_VAL || "$(OK_ENVVAR)" || 0x00 || 1 && y && "y"')
        self.expect_success("range C_MIN MAX_123 if OK_VAL || SOMETHING_EXTREMELY_LONG")
        self.expect_success("depends on OK_VAL")
        self.expect_success('default TEST_A if TEST_B=0x01 && TEST_C>42 || TEST_D="working" && TEST_E="y"')
        self.expect_success("imply TEST_VAL if TEST_VAL=42")
        self.expect_success("select TEST_VAL if TEST_VAL>=42")
        self.expect_success("visible if TEST_VAL!=42")
        self.expect_success("config THIS_IS_FINE")
        self.expect_success("choice OK_CHOICE")
        self.expect_success("endchoice")
        self.expect_success("menuconfig OK_MENUCONFIG")
        self.expect_success('    select OK if "$(Envvar)"')  # Envvar is valid envvar name
        # It is ok to test only one case for errors; if the previous ones passed, symbols are recognized correctly.
        self.expect_error("config Not_possible", expect="config NOT_POSSIBLE")
        self.expect_error(
            'prompt "test" if Ok_VAL || "$(OK_ENVVAR)" || 0x00 || 1 && y && "y"',
            expect='prompt "test" if OK_VAL || "$(OK_ENVVAR)" || 0x00 || 1 && y && "y"',
        )


@pytest.mark.parametrize("prepare_checker", (4,), indirect=True)
class TestPrefix(TestIndentAndNameChecker):
    def test_prefix_len(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success('menu "test"')
        self.expect_success("    config ABC_1")
        self.expect_success("    config ABC_2")
        self.expect_success("    config ABC_DEBUG")
        self.expect_success("    config ABC_ANOTHER")
        self.expect_success("endmenu")
        self.expect_success('menu "test2"')
        self.expect_success("    config A")
        self.expect_success("    config B")
        self.expect_error("endmenu", expect=None)

    def test_choices(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success('menu "test"')
        self.expect_success("    choice ASSERTION_LEVEL")
        self.expect_success("        config ASSERTION_DEBUG")
        self.expect_success("        config ASSERTION_RELEASE")
        self.expect_success("        menuconfig ASSERTION_XY")
        self.expect_success("    endchoice")
        self.expect_success("    choice DEBUG")
        self.expect_success("        config DE_1")
        self.expect_success("        config DE_2")
        self.expect_error("    endchoice", expect=None)
        self.expect_error("endmenu", expect=None)

    def test_nested_menu(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success('menu "test"')
        self.expect_success("    config DOESNT_MATTER")
        self.expect_success('    menu "inner menu"')
        self.expect_success("        config MENUOP_1")
        self.expect_success("        config MENUOP_2")
        self.expect_success("        config MENUOP_3")
        self.expect_success("    endmenu")
        self.expect_success("endmenu")

    def test_nested_ifendif(self, prepare_checker):
        self.checker = prepare_checker
        self.expect_success('menu "test"')
        self.expect_success("    config MENUOP_1")
        self.expect_success("    if MENUOP_1")
        self.expect_success("        config MENUOP_2")
        self.expect_success("    endif")
        self.expect_success("endmenu")


@dataclass
class DataTestReplace:
    TEST_FILE: Optional[str] = None
    ORIGINAL: Optional[str] = None


class TestReplace:
    """
    Test the (not only) pre-commit hook in place change by running validate_file() with replace=True.
    Original Kconfig should be modified instead of creating new file.
    """

    @pytest.fixture(scope="class")
    def data(_):
        data = DataTestReplace()
        test_files_path = os.path.join(os.path.dirname(__file__))
        data.ORIGINAL = os.path.join(test_files_path, "Kconfig")
        assert os.path.isfile(data.ORIGINAL)
        data.TEST_FILE = data.ORIGINAL + ".test"

        yield data

        try:
            os.remove(data.TEST_FILE)
        except FileNotFoundError:
            pass

    @pytest.fixture(autouse=True)
    def prepare(_, data):
        shutil.copy(data.ORIGINAL, data.TEST_FILE)

        yield

        try:
            os.remove(data.TEST_FILE + ".new")
        except FileNotFoundError:
            pass

    def test_no_replace(self, data):
        validate_file(data.TEST_FILE, replace=False)
        assert os.path.isfile(data.TEST_FILE + ".new")
        assert os.path.isfile(data.TEST_FILE)
        assert not filecmp.cmp(data.TEST_FILE + ".new", data.ORIGINAL)
        assert filecmp.cmp(data.TEST_FILE, data.ORIGINAL)

    def test_replace(self, data):
        validate_file(os.path.abspath(data.TEST_FILE), replace=True)
        assert os.path.isfile(data.TEST_FILE)
        assert not os.path.isfile(data.TEST_FILE + ".new")
        assert not filecmp.cmp(data.TEST_FILE, data.ORIGINAL)


@dataclass
class DataSDKConfigRename:
    correct_sdkconfigs: Optional[str] = None
    incorrect_sdkconfigs: Optional[str] = None
    suggestions: Optional[str] = None


class TestSDKConfigRename:
    @pytest.fixture(scope="class")
    def data(_):
        data = DataSDKConfigRename()
        current_path = os.path.abspath(os.path.dirname(__file__))
        data.correct_sdkconfigs = os.path.join(current_path, "sdkconfigs", "correct")
        data.incorrect_sdkconfigs = os.path.join(current_path, "sdkconfigs", "incorrect")
        data.suggestions = os.path.join(current_path, "sdkconfigs", "suggestions")
        yield data

    def test_correct_sdkconfigs(self, data):
        correct_files = os.listdir(data.correct_sdkconfigs)
        for correct_file in correct_files:
            is_valid = validate_file(os.path.join(data.correct_sdkconfigs, correct_file))
            assert is_valid

    def test_incorrect_sdkconfigs(self, data):
        incorrect_files = os.listdir(data.incorrect_sdkconfigs)
        for incorrect_file in incorrect_files:
            is_valid = validate_file(os.path.join(data.incorrect_sdkconfigs, incorrect_file))
            assert not is_valid
            with open(
                os.path.join(data.suggestions, incorrect_file + ".suggestions"), "r"
            ) as file_expected_suggestions, open(
                os.path.join(data.incorrect_sdkconfigs, incorrect_file + ".new"), "r"
            ) as file_real_suggestion:
                assert file_expected_suggestions.read() == file_real_suggestion.read()
            try:
                os.remove(os.path.join(data.incorrect_sdkconfigs, incorrect_file + ".new"))
            except FileNotFoundError:
                pass
