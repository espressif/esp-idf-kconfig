#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2018-2023 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import filecmp
import os
import shutil
import unittest

from kconfcheck.core import (
    CONFIG_NAME_MAX_LENGTH,
    IndentAndNameChecker,
    InputError,
    LineRuleChecker,
    SourceChecker,
    validate_kconfig_file,
)


class ApplyLine(object):
    def apply_line(self, string):
        self.checker.process_line(string + "\n", 0)

    def expect_error(self, string, expect, cleanup=None):
        try:
            with self.assertRaises(InputError) as cm:
                self.apply_line(string)
            if expect:
                self.assertEqual(cm.exception.suggested_line, expect + "\n")
        finally:
            if cleanup:
                # cleanup of the previous failure
                self.apply_line(cleanup)

    def expt_success(self, string):
        self.apply_line(string)


class TestLineRuleChecker(unittest.TestCase, ApplyLine):
    def setUp(self):
        self.checker = LineRuleChecker("Kconfig")

    def tearDown(self):
        pass

    def test_tabulators(self):
        self.expect_error("\ttest", expect="    test")
        self.expect_error("\t    test", expect="        test")
        self.expect_error("   \ttest", expect="       test")
        self.expect_error("     \t     test", expect="              test")
        self.expt_success("         test")
        self.expt_success("test")

    def test_trailing_whitespaces(self):
        self.expect_error(" ", expect="")
        self.expect_error("     ", expect="")
        self.expect_error("test ", expect="test")
        self.expt_success("test")
        self.expt_success("")

    def test_line_length(self):
        self.expect_error("x" * 120, expect=None)
        self.expt_success("x" * 119)
        self.expt_success("")


class TestSourceChecker(unittest.TestCase, ApplyLine):
    def setUp(self):
        self.checker = SourceChecker("Kconfig")

    def tearDown(self):
        pass

    def test_source_file_name(self):
        self.expect_error(
            'source "notKconfig.test"', expect='source "Kconfig.notKconfig.test"'
        )
        self.expect_error('source "Kconfig"', expect='source "Kconfig.Kconfig"')
        self.expt_success('source "Kconfig.in"')
        self.expt_success('source "/tmp/Kconfig.test"')
        self.expt_success('source "/tmp/Kconfig.in"')
        self.expect_error('source"Kconfig.in"', expect='source "Kconfig.in"')
        self.expt_success('source "/tmp/Kconfig.in"  # comment')


class TestIndentAndNameChecker(unittest.TestCase, ApplyLine):
    def setUp(self):
        self.checker = IndentAndNameChecker("Kconfig")
        self.checker.min_prefix_length = 4

    def tearDown(self):
        self.checker.__exit__("Kconfig", None, None)


class TestIndent(TestIndentAndNameChecker):
    def setUp(self):
        super(TestIndent, self).setUp()
        self.checker.min_prefix_length = 0  # prefixes are ignored in this test case

    def test_indent_characters(self):
        self.expt_success('menu "test"')
        self.expect_error(" test", expect="    test")
        self.expect_error("  test", expect="    test")
        self.expect_error("   test", expect="    test")
        self.expect_error("     test", expect="    test")
        self.expt_success("    test")
        self.expt_success("    test2")
        self.expt_success("    config")
        self.expect_error("    default", expect="        default")
        self.expt_success("        help")
        self.expect_error("         text", expect="            text")
        self.expt_success("            help text")
        self.expt_success("    menu")
        self.expt_success("    endmenu")
        self.expect_error(
            "         choice", expect="    choice", cleanup="    endchoice"
        )
        self.expect_error("       choice", expect="    choice", cleanup="    endchoice")
        self.expt_success("    choice")
        self.expt_success("    endchoice")
        self.expt_success("    config")
        self.expt_success("endmenu")

    def test_help_content(self):
        self.expt_success('menu "test"')
        self.expt_success("    config")
        self.expt_success("        help")
        self.expt_success("            description")
        self.expt_success("            config keyword in the help")
        self.expt_success("            menu keyword in the help")
        self.expt_success("            menuconfig keyword in the help")
        self.expt_success("            endmenu keyword in the help")
        self.expt_success("            endmenu keyword in the help")
        self.expt_success("")  # newline in help
        self.expt_success("            endmenu keyword in the help")
        self.expect_error(
            '          menu "real menu with wrong indent"',
            expect='    menu "real menu with wrong indent"',
            cleanup="    endmenu",
        )
        self.expt_success("endmenu")

    def test_mainmenu(self):
        self.expt_success('mainmenu "test"')
        self.expect_error("test", expect="    test")
        self.expt_success("    not_a_keyword")
        self.expt_success("    config")
        self.expt_success("    menuconfig")
        self.expect_error("test", expect="        test")
        self.expect_error("   test", expect="        test")
        self.expt_success("    menu")
        self.expt_success("    endmenu")

    def test_ifendif(self):
        self.expt_success('menu "test"')
        self.expt_success("    config")
        self.expt_success("        help")
        self.expect_error("        if", expect="    if", cleanup="    endif")
        self.expt_success("    if")
        self.expect_error("    config", expect="        config")
        self.expt_success("        config")
        self.expt_success("            help")
        self.expt_success("    endif")
        self.expt_success("    config")
        self.expt_success("endmenu")

    def test_config_without_menu(self):
        self.expt_success("menuconfig")
        self.expt_success("    help")
        self.expt_success("        text")
        self.expt_success("")
        self.expt_success("        text")
        self.expt_success("config")
        self.expt_success("    help")

    def test_source_after_config(self):
        self.expt_success("menuconfig")
        self.expt_success("    help")
        self.expt_success("        text")
        self.expect_error("    source", expect="source")
        self.expt_success('source "Kconfig.in"')

    def test_comment_after_config(self):
        self.expt_success("menuconfig")
        self.expt_success("    # comment")
        self.expt_success("    help")
        self.expt_success("        text")
        self.expt_success('        # second not realcomment"')


class TestName(TestIndentAndNameChecker):
    def setUp(self):
        super(TestName, self).setUp()
        self.checker.min_prefix_length = 0  # prefixes are ignored in this test case

    def test_name_length(self):
        max_length = CONFIG_NAME_MAX_LENGTH
        too_long = max_length + 1
        self.expt_success('menu "test"')
        self.expt_success("    config ABC")
        self.expt_success("    config " + ("X" * max_length))
        self.expect_error("    config " + ("X" * too_long), expect=None)
        self.expt_success("    menuconfig " + ("X" * max_length))
        self.expect_error("    menuconfig " + ("X" * too_long), expect=None)
        self.expt_success("    choice " + ("X" * max_length))
        self.expect_error("    choice " + ("X" * too_long), expect=None)
        self.expt_success("endmenu")


class TestPrefix(TestIndentAndNameChecker):
    def test_prefix_len(self):
        self.expt_success('menu "test"')
        self.expt_success("    config ABC_1")
        self.expt_success("    config ABC_2")
        self.expt_success("    config ABC_DEBUG")
        self.expt_success("    config ABC_ANOTHER")
        self.expt_success("endmenu")
        self.expt_success('menu "test2"')
        self.expt_success("    config A")
        self.expt_success("    config B")
        self.expect_error("endmenu", expect=None)

    def test_choices(self):
        self.expt_success('menu "test"')
        self.expt_success("    choice ASSERTION_LEVEL")
        self.expt_success("        config ASSERTION_DEBUG")
        self.expt_success("        config ASSERTION_RELEASE")
        self.expt_success("        menuconfig ASSERTION_XY")
        self.expt_success("    endchoice")
        self.expt_success("    choice DEBUG")
        self.expt_success("        config DE_1")
        self.expt_success("        config DE_2")
        self.expect_error("    endchoice", expect=None)
        self.expect_error("endmenu", expect=None)

    def test_nested_menu(self):
        self.expt_success('menu "test"')
        self.expt_success("    config DOESNT_MATTER")
        self.expt_success('    menu "inner menu"')
        self.expt_success("        config MENUOP_1")
        self.expt_success("        config MENUOP_2")
        self.expt_success("        config MENUOP_3")
        self.expt_success("    endmenu")
        self.expt_success("endmenu")

    def test_nested_ifendif(self):
        self.expt_success('menu "test"')
        self.expt_success("    config MENUOP_1")
        self.expt_success("    if MENUOP_1")
        self.expt_success("        config MENUOP_2")
        self.expt_success("    endif")
        self.expt_success("endmenu")

    def test_no_prefix(self):
        self.expt_success('menu "test"')
        self.expt_success("    config NOPREFIX")
        self.expt_success("    config IDF_PREFIXA")
        self.expt_success("    config IDF_PREFIXB")
        self.expect_error("endmenu", expect=None)


class TestReplace(unittest.TestCase):
    """
    Test the (not only) pre-commit hook in place change by running validate_kconfig_file() with replace=True.
    Original Kconfig should be modified instead of creating new file.
    """

    @classmethod
    def setUpClass(cls):
        test_files_path = os.path.join(os.path.dirname(__file__))
        cls.ORIGINAL = os.path.join(test_files_path, "Kconfig")
        assert os.path.isfile(cls.ORIGINAL)
        cls.TEST_FILE = cls.ORIGINAL + ".test"

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.TEST_FILE)
        except FileNotFoundError:
            pass

    def setUp(self):
        shutil.copy(self.ORIGINAL, self.TEST_FILE)

    def tearDown(self):
        try:
            os.remove(self.TEST_FILE + ".new")
        except FileNotFoundError:
            pass

    def test_no_replace(self):
        validate_kconfig_file(self.TEST_FILE, replace=False)
        self.assertTrue(os.path.isfile(self.TEST_FILE + ".new"))
        self.assertTrue(os.path.isfile(self.TEST_FILE))
        self.assertFalse(filecmp.cmp(self.TEST_FILE + ".new", self.ORIGINAL))
        self.assertTrue(filecmp.cmp(self.TEST_FILE, self.ORIGINAL))

    def test_replace(self):
        validate_kconfig_file(os.path.abspath(self.TEST_FILE), replace=True)
        self.assertTrue(os.path.isfile(self.TEST_FILE))
        self.assertFalse(os.path.isfile(self.TEST_FILE + ".new"))
        self.assertFalse(filecmp.cmp(self.TEST_FILE, self.ORIGINAL))


if __name__ == "__main__":
    unittest.main()
