# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from esp_kconfiglib import Kconfig

TEST_FILES_PATH = os.path.abspath(os.path.dirname(__file__))
TESTS_PATH_OK = os.path.join(TEST_FILES_PATH, "kconfigs", "ok")
TESTS_PATH_WARNINGS = os.path.join(TEST_FILES_PATH, "kconfigs", "warnings")
TESTS_PATH_ERRORS = os.path.join(TEST_FILES_PATH, "kconfigs", "errors")


class TestKconfigVersions:
    def test_kconfig_no_envvar(self):
        try:
            del os.environ["KCONFIG_PARSER_VERSION"]
        except KeyError:
            pass
        config = Kconfig(os.path.join(TESTS_PATH_OK, "Empty.in"))
        assert config.parser_version == 1

    @pytest.mark.parametrize("version", ["1", "2"])
    def test_kconfig(self, version):
        os.environ["KCONFIG_PARSER_VERSION"] = version
        config = Kconfig(os.path.join(TESTS_PATH_OK, "Empty.in"))
        assert config.parser_version == int(version)


class BaseKconfigTest:
    def call_kconfig(self, path: str, input_file_name: str, output_file_name: str) -> subprocess.CompletedProcess:
        kconfgen_cmd = [
            "coverage",
            "run",
            "-m",
            "kconfgen",
            "--kconfig",
            os.path.join(path, input_file_name),
            "--output",
            "config",
            output_file_name,
            "--env",
            "KCONFIG_REPORT_VERBOSITY=default",
        ]
        result = subprocess.run(
            kconfgen_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=os.environ.copy(),
            cwd=os.getcwd(),
        )
        return result

    def check_output(self, path: str, actual_output_file: Path, expected_output_file: Path) -> None:
        with open(os.path.join(path, expected_output_file), "r") as expected, open(actual_output_file, "r") as actual:
            expected_output = expected.read()
            actual_output = actual.read()
        assert actual_output == expected_output

    def check_stderr(self, path: str, actual_stderr: str, expected_stderr: Path) -> None:
        with open(os.path.join(path, expected_stderr), "r") as expected:
            expected_stderr_content = expected.readlines()
        # We do not check stderr 1:1, because some paths could change.
        for stderr_line in expected_stderr_content:
            # For some reason, CI breaks stderr into multiple lines.
            assert stderr_line.strip() in actual_stderr.replace("\n", "")


class TestOKCases(BaseKconfigTest):
    @pytest.fixture(autouse=True)
    def set_env_vars(self):
        os.environ["TEST_FILE_PREFIX"] = os.path.join(TESTS_PATH_OK, "kconfigs_for_sourcing")
        os.environ["TEST_ENV_SET"] = "y"  # used in SeveralConfigs
        os.environ["MAX_NUMBER_OF_MOTORS"] = "4"  # used in Macro
        yield
        # Cleanup
        del os.environ["TEST_FILE_PREFIX"]
        del os.environ["TEST_ENV_SET"]
        del os.environ["MAX_NUMBER_OF_MOTORS"]

    @pytest.mark.parametrize(
        "filename", set(Path(file).stem for file in os.listdir(TESTS_PATH_OK) if file != "kconfigs_for_sourcing")
    )
    @pytest.mark.parametrize("version", ["1", "2"])
    def test_ok_cases(self, filename, version):
        os.environ["KCONFIG_PARSER_VERSION"] = version
        assert os.environ.get("KCONFIG_PARSER_VERSION", "") == version
        v1_skipped_tests = {
            "EnvironmentVariable": "Original kconfiglib does not support unquoted environment variable expansion.",
        }
        if int(version) == 1 and filename in v1_skipped_tests.keys():
            pytest.skip(v1_skipped_tests[filename])

        with tempfile.NamedTemporaryFile() as f:
            result = self.call_kconfig(path=TESTS_PATH_OK, input_file_name=f"{filename}.in", output_file_name=f.name)
            assert result.returncode == 0
            self.check_output(path=TESTS_PATH_OK, actual_output_file=f.name, expected_output_file=f"{filename}.out")


class TestWarningCases(BaseKconfigTest):
    @pytest.mark.parametrize(
        "filename", set(Path(file).stem for file in os.listdir(TESTS_PATH_WARNINGS) if file != "kconfigs_for_sourcing")
    )
    @pytest.mark.parametrize("version", ["1", "2"])
    def test_warning_cases(self, filename, version):
        os.environ["KCONFIG_PARSER_VERSION"] = version
        assert os.environ.get("KCONFIG_PARSER_VERSION", "") == version
        v1_skipped_tests = {
            "UndefinedEnvironmentVariable": (
                "Original kconfiglib does not support unquoted environment variable expansion."
            ),
            "SelectImplyNonBool": (
                "Parser v1 does not emit type-check warnings for 'select' and 'imply' on non-bool source symbols."
            ),
            "Deprecated_QuotedChoiceName": (
                "Parser v1 silently accepts a quoted choice name and does not deprecate it."
            ),
            "Deprecated_LegacyBooleanType": (
                "Parser v1 silently accepts the 'boolean' type keyword and does not deprecate it."
            ),
            "Deprecated_HelpIndentation": "Parser v1 does not enforce indentation and thus does not deprecate it.",
            "Deprecated_LowercaseChoiceName": "Parser v1 does not report lowercase letters in choice names.",
            "IllegalReference": "Parser v1 does not report illegal characters in symbol references.",
            "Deprecated_HelpDashes": "Parser v1 silently accepts --help-- / ---help--- and does not deprecate it.",
            "Deprecated_Optional": "Parser v1 silently accepts 'optional' and does not deprecate it.",
            "Deprecated_OptionDefconfigList": (
                "Parser v1 silently accepts 'option defconfig_list' and does not deprecate it."
            ),
            "Deprecated_OptionAllnoconfigY": (
                "Parser v1 silently accepts 'option allnoconfig_y' and does not deprecate it."
            ),
            "Deprecated_PreprocessorPlusEquals": (
                "Parser v1 silently accepts preprocessor '+=' and does not deprecate it."
            ),
            "Deprecated_PreprocessorBareMacro": (
                "Parser v1 silently accepts a bare macro call and does not deprecate it."
            ),
            "Deprecated_PreprocessorFunctionMacro": (
                "Parser v1 silently accepts a preprocessor function-call macro and does not deprecate it."
            ),
        }
        if int(version) == 1 and filename in v1_skipped_tests.keys():
            pytest.skip(v1_skipped_tests[filename])

        with tempfile.NamedTemporaryFile() as f:
            result = self.call_kconfig(
                path=TESTS_PATH_WARNINGS, input_file_name=f"{filename}.in", output_file_name=f.name
            )
            self.check_stderr(
                path=TESTS_PATH_WARNINGS,
                actual_stderr=result.stderr,
                expected_stderr=f"{filename}.stderr",
            )
            assert result.returncode == 0


class TestErrorCases(BaseKconfigTest):
    @pytest.mark.parametrize(
        "filename", set(Path(file).stem for file in os.listdir(TESTS_PATH_ERRORS) if file != "kconfigs_for_sourcing")
    )
    @pytest.mark.parametrize("version", ["1", "2"])
    def test_error_cases(self, filename, version):
        v1_skipped_tests = {
            "NoMainmenu": "Original kconfiglib supports Kconfigs without root mainmenu.",
            "IllegalConfigName": "Original kconfiglib allows any character in a config name.",
            "IllegalChoiceName": "Original kconfiglib allows any character in a choice name.",
            "TextAfterMenuTitle": "Original kconfiglib rejects it as well, but with a different message.",
            "TextAfterCommentText": "Original kconfiglib rejects it as well, but with a different message.",
        }
        if int(version) == 1 and filename in v1_skipped_tests.keys():
            pytest.skip(v1_skipped_tests[filename])
        os.environ["KCONFIG_PARSER_VERSION"] = version
        assert os.environ.get("KCONFIG_PARSER_VERSION", "") == version

        with tempfile.NamedTemporaryFile() as f:
            result = self.call_kconfig(
                path=TESTS_PATH_ERRORS, input_file_name=f"{filename}.in", output_file_name=f.name
            )
            self.check_stderr(
                path=TESTS_PATH_ERRORS,
                actual_stderr=result.stderr,
                expected_stderr=f"{filename}.stderr",
            )
            assert result.returncode == 1


class TestEscapedQuotesInPrompts:
    """Prompts are not part of the generated config, so they cannot be covered by EscapedQuotes.in/.out."""

    @pytest.mark.parametrize("version", ["1", "2"])
    def test_prompt_keeps_escaped_quotes(self, version):
        os.environ["KCONFIG_PARSER_VERSION"] = version
        config = Kconfig(os.path.join(TESTS_PATH_OK, "EscapedQuotes.in"))
        assert config.syms["A"].nodes[0].prompt[0] == 'config prompt with "escaped" quotes'


class TestHelpTextIsLiteral:
    """Help text is not part of the generated config, so it cannot be covered by *.in/.out fixtures."""

    @pytest.mark.parametrize("version", ["1", "2"])
    def test_hash_is_not_a_comment_marker(self, version):
        os.environ["KCONFIG_PARSER_VERSION"] = version
        config = Kconfig(os.path.join(TESTS_PATH_OK, "HelpTextLiteral.in"))
        assert config.syms["A"].nodes[0].help == (
            "# This looks like a comment but is literal help text.\n"
            "See issue #123 for more details on PKCS#5.\n"
            "\n"
            "# Another comment-looking line, after a blank line.\n"
            "Second paragraph."
        )


class TestIndirectSetWithSymbolValue:
    """
    Changing the source value at runtime is not covered by IndirectValueSetSymbol.in/.out fixtures.
    """

    @pytest.mark.parametrize("version", ["1", "2"])
    @pytest.mark.parametrize(
        "src, dst, new_value",
        [
            ("SRC_INT", "DST_INT", "33"),
            ("SRC_HEX", "DST_HEX", "0x21"),
            ("SRC_FLOAT", "DST_FLOAT", "3.5"),
            ("SRC_STR", "DST_STR", "new"),
            ("SRC_INT", "WEAK_DST_INT", "33"),
            ("SRC_HEX", "WEAK_DST_HEX", "0x21"),
            ("SRC_FLOAT", "WEAK_DST_FLOAT", "3.5"),
            ("SRC_STR", "WEAK_DST_STR", "new"),
        ],
    )
    def test_target_follows_source_change(self, monkeypatch, version, src, dst, new_value):
        monkeypatch.setenv("KCONFIG_PARSER_VERSION", version)
        config = Kconfig(os.path.join(TESTS_PATH_OK, "IndirectValueSetSymbol.in"))
        assert config.syms[dst].str_value == config.syms[src].str_value
        config.syms[src].set_value(new_value)
        assert config.syms[dst].str_value == new_value


@pytest.mark.parametrize("version", ["1", "2"])
class TestIndirectSetWithUnavailableSymbolValue:
    """
    "set DST=SRC" in APPLY behaves as "set DST=SRC if APPLY && <SRC is available>", where SRC is available
    if its direct dependencies are satisfied. Otherwise, the option is inactive and the target falls back
    to the next "set" option, user value or defaults.
    """

    KCONFIG = os.path.join(TEST_FILES_PATH, "kconfigs", "Kconfig.set_unavailable_source")

    @pytest.mark.parametrize(
        "dst, user_value, src_value",
        [
            ("DST_INT", "5", "22"),
            ("DST_HEX", "0x5", "0x16"),
            ("DST_FLOAT", "5.5", "2.5"),
            ("DST_STR", "user", "src"),
        ],
    )
    def test_set_falls_back_to_user_value(self, monkeypatch, version, dst, user_value, src_value):
        monkeypatch.setenv("KCONFIG_PARSER_VERSION", version)
        config = Kconfig(self.KCONFIG)
        sym = config.syms[dst]
        sym.set_value(user_value)
        # Evaluate the target while "set" is active to check no state from this evaluation leaks
        assert sym.str_value == src_value
        assert sym._has_active_indirect_set

        config.syms["SRC_ENABLED"].set_value("n")
        assert sym.str_value == user_value
        assert not sym._has_active_indirect_set

        config.syms["SRC_ENABLED"].set_value("y")
        assert sym.str_value == src_value

    @pytest.mark.parametrize(
        "dst, default_value, src_value",
        [
            ("WEAK_DST_INT", "7", "22"),
            ("WEAK_DST_HEX", "0x7", "0x16"),
            ("WEAK_DST_FLOAT", "1.0", "2.5"),
            ("WEAK_DST_STR", "dst", "src"),
        ],
    )
    def test_set_default_falls_back_to_default(self, monkeypatch, version, dst, default_value, src_value):
        monkeypatch.setenv("KCONFIG_PARSER_VERSION", version)
        config = Kconfig(self.KCONFIG)
        sym = config.syms[dst]
        assert sym.str_value == src_value

        config.syms["SRC_ENABLED"].set_value("n")
        assert sym.str_value == default_value

    def test_next_set_applies(self, monkeypatch, version):
        monkeypatch.setenv("KCONFIG_PARSER_VERSION", version)
        config = Kconfig(self.KCONFIG)
        sym = config.syms["NEXT_DST_INT"]
        assert sym.str_value == "22"

        config.syms["SRC_ENABLED"].set_value("n")
        assert sym.str_value == "99"

    def test_indirect_set_flag_not_stale(self, monkeypatch, version):
        monkeypatch.setenv("KCONFIG_PARSER_VERSION", version)
        config = Kconfig(self.KCONFIG)
        sym = config.syms["DST_INT"]
        sym.set_value("5")
        assert sym.str_value == "22"
        assert sym.has_active_indirect_set
        assert sym.active_indirect_set is sym.rev_values[0]
        assert sym.has_active_default_value()

        # Deliberately do not read str_value before checking the flag
        config.syms["SRC_ENABLED"].set_value("n")
        assert not sym.has_active_indirect_set
        assert sym.active_indirect_set is None
        assert not sym.has_active_default_value()
        assert sym.str_value == "5"

    def test_active_set_default(self, monkeypatch, version):
        monkeypatch.setenv("KCONFIG_PARSER_VERSION", version)
        config = Kconfig(self.KCONFIG)
        sym = config.syms["WEAK_DST_INT"]
        assert sym.active_indirect_set is sym.weak_rev_values[0]
        assert not sym.has_active_indirect_set

        # User value takes precedence over "set default"
        sym.set_value("5")
        assert sym.active_indirect_set is None
        assert sym.str_value == "5"


@pytest.mark.parametrize("version", ["1", "2"])
class TestIndirectSetEdgeCases:
    """
    Edge cases of "set"/"set default" options not covered by the fixtures in ok/ and warnings/.
    """

    KCONFIG = os.path.join(TEST_FILES_PATH, "kconfigs", "Kconfig.set_edge_cases")

    @pytest.mark.parametrize("dst", ["STR_TARGET", "WEAK_STR_TARGET"])
    def test_empty_string_value(self, monkeypatch, version, dst):
        monkeypatch.setenv("KCONFIG_PARSER_VERSION", version)
        config = Kconfig(self.KCONFIG)
        assert config.syms[dst].str_value == ""

        # Once the option is inactive, the default value is used again
        config.syms["APPLY_SET" if dst == "STR_TARGET" else "APPLY_SET_DEFAULT"].set_value("n")
        assert config.syms[dst].str_value == "default"
        config.report.reset()

    @pytest.mark.parametrize(
        "dst, src, value, clamped, low, high",
        [
            ("INT_TARGET", "APPLY_SET", "100", "10", "0", "10"),
            ("WEAK_INT_TARGET", "APPLY_SET_DEFAULT", "100", "10", "0", "10"),
            ("HEX_TARGET", "APPLY_SET", "0x100", "0x10", "0x0", "0x10"),
            ("WEAK_HEX_TARGET", "APPLY_SET_DEFAULT", "0x100", "0x10", "0x0", "0x10"),
            ("FLOAT_TARGET", "APPLY_SET", "10.5", "1.5", "0.0", "1.5"),
            ("WEAK_FLOAT_TARGET", "APPLY_SET_DEFAULT", "10.5", "1.5", "0.0", "1.5"),
        ],
    )
    def test_out_of_range_value_is_clamped_and_logged(self, monkeypatch, version, dst, src, value, clamped, low, high):
        monkeypatch.setenv("KCONFIG_PARSER_VERSION", version)
        config = Kconfig(self.KCONFIG)
        config.report.reset()
        config.syms[dst]._invalidate()

        assert config.syms[dst].str_value == clamped
        notes = [m["message"] for m in config.report._log_cache if m["level"] == "note"]
        assert any(
            note.startswith(f"indirectly set value {value} on {dst} ")
            and f"(by {src} " in note
            and note.endswith(f"clamped to {clamped} due to being outside the active range ([{low}, {high}])")
            for note in notes
        ), notes
        config.report.reset()

    def test_bool_target_is_ignored(self, monkeypatch, version):
        monkeypatch.setenv("KCONFIG_PARSER_VERSION", version)
        config = Kconfig(os.path.join(TESTS_PATH_WARNINGS, "IndirectSetBoolTarget.in"))
        for name in ("BOOL_TARGET", "WEAK_BOOL_TARGET"):
            sym = config.syms[name]
            assert sym.str_value == "n"
            assert not sym.rev_values
            assert not sym.weak_rev_values
        # The ignored options are removed from the source as well
        source = config.syms["SOURCE"]
        assert not source.sets
        assert not source.weak_sets
        assert not source.nodes[0].sets
        assert not source.nodes[0].weak_sets
        config.report.reset()

    def test_bool_target_reported_at_definition_with_set(self, monkeypatch, version):
        monkeypatch.setenv("KCONFIG_PARSER_VERSION", version)
        kconfig_path = os.path.join(TEST_FILES_PATH, "kconfigs", "Kconfig.set_bool_target_multidef")
        config = Kconfig(kconfig_path)
        source = config.syms["SOURCE"]
        first, second = source.nodes

        notes = [
            m["message"]
            for m in config.report._log_cache
            if m["message"].startswith(second.filename) and "with the bool symbol BOOL_TARGET" in m["message"]
        ]
        assert len(notes) == 2
        assert all(note.startswith(f"{second.filename}:{second.linenr}: ") for note in notes)
        assert any("'set' option" in note for note in notes)
        assert any("'set default' option" in note for note in notes)

        # Only the options with the bool target are removed; the other "set" option still applies
        assert [target.name for target, _, _ in source.sets] == ["INT_TARGET"]
        assert [target.name for target, _, _ in first.sets] == ["INT_TARGET"]
        assert not second.sets
        assert not source.weak_sets
        assert not second.weak_sets
        assert config.syms["INT_TARGET"].str_value == "1"
        config.report.reset()
