# SPDX-FileCopyrightText: 2024-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from kconfiglib import Kconfig

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
            sys.executable,
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
        result = subprocess.run(kconfgen_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
