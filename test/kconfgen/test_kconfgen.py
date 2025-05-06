# SPDX-FileCopyrightText: 2024-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import re
import subprocess
import textwrap
from dataclasses import asdict
from dataclasses import dataclass
from typing import Optional

import pytest

from kconfiglib import POLICY_USE_KCONFIG
from kconfiglib import POLICY_USE_SDKCONFIG

KCONFIG_PARSER_VERSIONS = ["1", "2"]


# Define argument container for CLI invocation
@dataclass
class Args:
    output: str
    config: Optional[str] = None
    sdkconfig_rename: Optional[str] = None
    env: Optional[str] = None

    def to_cli(self):
        # Build flags from args fields except env and output (handled separately)
        flags = []
        for field, value in asdict(self).items():
            if value is None or field in ("env", "output"):
                continue
            key = field.replace("_", "-")
            flags.extend([f"--{key}", value])
        return flags


# Fixture to set parser policy for each test (uses os.environ to avoid scope mismatch)
@pytest.fixture(autouse=True)
def set_parser_version(request):
    version = request.param
    # set environment variable for this test invocation
    os.environ["KCONFIG_PARSER_VERSION"] = str(version)


class KconfgenBaseTestCase:
    @pytest.fixture(autouse=True)
    def runner(self, tmp_path):
        def invoke_and_test(
            args: Args, in_text: str, expected: str, test: str = "in", expected_error: Optional[str] = None
        ) -> Optional[str]:
            # write kconfig input
            kconfig_path = os.path.join(str(tmp_path), "kconfig")
            with open(kconfig_path, "w") as f:
                f.write(textwrap.dedent(in_text))
            # prepare output path
            out_path = os.path.join(str(tmp_path), "output")
            # build command
            cmd = (
                ["python", "-m", "kconfgen"]
                + args.to_cli()
                + ["--output", args.output, out_path, "--kconfig", kconfig_path]
            )
            # setup env
            env = os.environ.copy()
            if args.env:
                key, _, val = args.env.partition("=")
                env[key] = val
            # execute
            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
            if expected_error:
                assert result.returncode != 0
                assert expected_error in result.stderr
                return None
            assert result.returncode == 0, result.stderr
            with open(out_path) as f:
                text = f.read()
            # assertions
            if test == "in":
                assert expected in text
            elif test == "not in":
                assert expected not in text
            elif test == "equal":
                assert expected == text
            elif test == "not equal":
                assert expected != text
            elif test == "regex":
                assert re.search(expected, text)
            else:
                pytest.skip(f"Unknown test type {test}")
            return text

        return invoke_and_test


@pytest.mark.parametrize("set_parser_version", KCONFIG_PARSER_VERSIONS, indirect=True)
class TestCmake(KconfgenBaseTestCase):
    @pytest.fixture(autouse=True)
    def init(self):
        self.args = Args(output="cmake")

    HEXPREFIX = textwrap.dedent(
        """
        mainmenu "Test"

            config HEX_NOPREFIX
                hex "Hex Item default no prefix"
                default 33

            config HEX_PREFIX
                hex "Hex Item default prefix"
                default 0x77
        """
    )

    def test_string_escape(self, runner):
        if os.environ.get("KCONFIG_PARSER_VERSION") == "2":
            pytest.skip("Kconfiglib v2 does not support character escaping")
        in_text = """
        mainmenu "Test"

            config PASSWORD
                string "password"
                default "\\\\~!@#$%^&*()\\\""
        """
        runner(self.args, in_text, 'set(CONFIG_PASSWORD "\\\\~!@#$%^&*()\\"")')

    def test_hex_prefix(self, runner):
        runner(self.args, TestCmake.HEXPREFIX, 'set(CONFIG_HEX_NOPREFIX "0x33")')
        runner(self.args, TestCmake.HEXPREFIX, 'set(CONFIG_HEX_PREFIX "0x77")')


@pytest.mark.parametrize("set_parser_version", KCONFIG_PARSER_VERSIONS, indirect=True)
class TestJson(KconfgenBaseTestCase):
    @pytest.fixture(autouse=True)
    def init(self):
        self.args = Args(output="json")

    def test_string_escape(self, runner):
        if os.environ.get("KCONFIG_PARSER_VERSION") == "2":
            pytest.skip("Kconfiglib v2 does not support character escaping")
        in_text = """
        mainmenu "Test"

            config PASSWORD
                string "password"
                default "\\\\~!@#$%^&*()\\\""
        """
        runner(self.args, in_text, '"PASSWORD": "\\\\~!@#$%^&*()\\""')

    def test_hex_prefix(self, runner):
        snippet = TestCmake.HEXPREFIX
        runner(self.args, snippet, f'"HEX_NOPREFIX": {0x33}')
        runner(self.args, snippet, f'"HEX_PREFIX": {0x77}')


@pytest.mark.parametrize("set_parser_version", KCONFIG_PARSER_VERSIONS, indirect=True)
class TestJsonMenus(KconfgenBaseTestCase):
    @pytest.fixture(autouse=True)
    def init(self):
        self.args = Args(output="json_menus")

    def test_multiple_ranges(self, runner):
        in_text = """
        mainmenu "Test"

            config IDF_TARGET
                string "IDF target"
                default "esp32"

            config SOME_SETTING
                int "setting for the chip"
                range 0 100 if IDF_TARGET="esp32s0"
                range 0 10 if IDF_TARGET="esp32"
                range -10 1 if IDF_TARGET="esp32s2"
        """
        runner(self.args, in_text, r'"range":\s+\[\s+0,\s+10\s+\]', test="regex")

    def test_hex_ranges(self, runner):
        in_text = """
        mainmenu "Test"

            config SOME_SETTING
                hex "setting for the chip"
                range 0x0 0xaf if UNDEFINED
                range 0x10 0xaf
        """
        runner(self.args, in_text, r'"range":\s+\[\s+16,\s+175\s+\]', test="regex")


@pytest.mark.parametrize("set_parser_version", KCONFIG_PARSER_VERSIONS, indirect=True)
class TestConfig(KconfgenBaseTestCase):
    input = textwrap.dedent(
        """
        mainmenu "Test"

            config TEST
                bool "test"
                default "n"
        """
    )

    @pytest.fixture(autouse=True)
    def init(self, tmp_path):
        cfg = os.path.join(str(tmp_path), "config")
        with open(cfg, "w") as f:
            f.write(
                textwrap.dedent(
                    """
                    # default:
                    CONFIG_TEST=y
                    # default:
                    CONFIG_UNKNOWN=y
                    """
                )
            )
        self.args = Args(output="config", config=cfg)

    def test_keep_saved_option(self, runner):
        runner(self.args, TestConfig.input, "CONFIG_TEST=y")

    def test_discard_unknown_option(self, runner):
        runner(self.args, TestConfig.input, "CONFIG_UNKNOWN", test="not in")


@pytest.mark.parametrize("set_parser_version", KCONFIG_PARSER_VERSIONS, indirect=True)
class TestRenameConfig(KconfgenBaseTestCase):
    input = textwrap.dedent(
        """
        mainmenu "Test"

            config RENAMED_OPTION
                bool "Renamed option"
                default y
        """
    )

    @pytest.fixture(autouse=True)
    def init(self, tmp_path):
        self.args = Args(output="config")
        self.rename_file = os.path.join(str(tmp_path), "rename")

    def prepare_rename_file(self, text):
        with open(self.rename_file, "w") as f:
            f.write(textwrap.dedent(text))
        self.args.sdkconfig_rename = self.rename_file

    def prepare_sdkconfig_file(self, tmp_path, text):
        cfg = os.path.join(str(tmp_path), "sdkconfig")
        with open(cfg, "w") as f:
            f.write(textwrap.dedent(text))
        self.args.config = cfg

    def test_renamed_option_disabled(self, runner, tmp_path):
        self.prepare_rename_file(
            """
            CONFIG_NAMED_OPTION             CONFIG_RENAMED_OPTION
            """
        )
        self.prepare_sdkconfig_file(
            tmp_path,
            """
            # CONFIG_NAMED_OPTION is not set
            """,
        )
        runner(self.args, TestRenameConfig.input, "# CONFIG_RENAMED_OPTION is not set")

    def test_rename_inversion(self, runner, tmp_path):
        self.prepare_rename_file(
            """
            CONFIG_NAMED_OPTION             !CONFIG_RENAMED_OPTION
            """
        )
        self.prepare_sdkconfig_file(
            tmp_path,
            """
            # CONFIG_NAMED_OPTION is not set
            """,
        )
        runner(self.args, TestRenameConfig.input, "CONFIG_RENAMED_OPTION=y")

    @pytest.mark.parametrize(
        "invalid_line",
        (
            """
                CONFIG_NAMED_OPTION             CONFIG_NAMED_OPTION
                """,
            """
                CONFIG_NAMED_OPTION             !CONFIG_NAMED_OPTION
                """,
        ),
        ids=("same_name", "inversion"),
    )
    def test_forbidden_renaming(self, runner, invalid_line):
        expected_error = "Replacement name is the same as original name (NAMED_OPTION)."
        self.prepare_rename_file(invalid_line)
        runner(
            self.args,
            TestRenameConfig.input,
            "",
            expected_error=f"RuntimeError: Error in {self.rename_file} (line 2): {expected_error}",
        )

    def test_lowercase_in_old_name(self, runner):
        if os.environ.get("KCONFIG_PARSER_VERSION") == "2":
            pytest.skip("Kconfiglib v2 does not allow lowercase in config names")

        lc_input = textwrap.dedent(
            """
            mainmenu "Test"

                config named_OPTION
                    bool "Lowercase option"
                    default y
            """
        )
        self.args = Args(output="config")
        self.prepare_rename_file(
            """
            CONFIG_named_OPTION             CONFIG_NAMED_OPTION
            """
        )
        runner(self.args, lc_input, "CONFIG_named_OPTION=y")


@pytest.mark.parametrize("set_parser_version", KCONFIG_PARSER_VERSIONS, indirect=True)
class TestHeader(KconfgenBaseTestCase):
    @pytest.fixture(autouse=True)
    def init(self):
        self.args = Args(output="header")

    def test_string_escape(self, runner):
        if os.environ.get("KCONFIG_PARSER_VERSION") == "2":
            pytest.skip("Kconfiglib v2 does not support character escaping")
        in_text = """
        mainmenu "Test"

            config PASSWORD
                string "password"
                default "\\\\~!@#$%^&*()\\\""
        """
        runner(self.args, in_text, '#define CONFIG_PASSWORD "\\\\~!@#$%^&*()\\""')

    def test_hex_prefix(self, runner):
        runner(self.args, TestCmake.HEXPREFIX, "#define CONFIG_HEX_NOPREFIX 0x33")
        runner(self.args, TestCmake.HEXPREFIX, "#define CONFIG_HEX_PREFIX 0x77")


@pytest.mark.parametrize("set_parser_version", KCONFIG_PARSER_VERSIONS, indirect=True)
class TestDocs(KconfgenBaseTestCase):
    @pytest.fixture(autouse=True)
    def init(self):
        self.args = Args(output="docs", env="IDF_TARGET=esp32")

    def test_multiple_ranges_with_negation(self, runner):
        in_text = """
        mainmenu "Test"

            config IDF_TARGET
                string "IDF target"
                default "esp32"

            config IDF_TARGET_ESP32
                bool
                default "y" if IDF_TARGET="esp32"

            config SOME_SETTING
                int "setting for the chip"
                range 0 10 if IDF_TARGET_ESP32
                range 0 100 if !IDF_TARGET_ESP32
        """
        out = runner(self.args, in_text, r"Range:\n\s+- from 0 to 10", test="regex")
        assert "- from 0 to 100" not in out

    def test_choice(self, runner):
        in_text = """
        mainmenu "Test"

            menu "TEST"
                choice TYPES
                    prompt "types"
                    default TYPES_OP2
                    help
                        Description of TYPES

                    config TYPES_OP1
                        bool "option 1"
                    config TYPES_OP2
                        bool "option 2"
                endchoice
            endmenu
        """
        expected = textwrap.dedent(
            """
            TEST
            ----

            Contains:

            - :ref:`CONFIG_TYPES`

            .. _CONFIG_TYPES:

            CONFIG_TYPES
            ^^^^^^^^^^^^

                types

                :emphasis:`Found in:` :ref:`test`

                Description of TYPES

                Available options:

                      .. _CONFIG_TYPES_OP1:

                    - option 1             (CONFIG_TYPES_OP1)

                      .. _CONFIG_TYPES_OP2:

                    - option 2             (CONFIG_TYPES_OP2)"""
        ).strip()
        runner(self.args, in_text, expected)


@pytest.mark.parametrize("set_parser_version", KCONFIG_PARSER_VERSIONS, indirect=True)
class TestDefaults(KconfgenBaseTestCase):
    input = textwrap.dedent(
        """
        mainmenu "Test"

            menu "Label"
                config IDF_TARGET
                    string "IDF target"
                    default "esp32"

                menu "This is a menu label"
                    config TEST2
                        bool "test"
                        default "y"
                endmenu

                menu "Label"
                    config TEST
                        bool "test"
                        default "y"
                        comment "This is a comment for TEST"
                endmenu
            endmenu
        """
    )

    @pytest.fixture(autouse=True)
    def init(self, tmp_path):
        cfg = os.path.join(str(tmp_path), "config")
        with open(cfg, "w") as f:
            f.write(
                textwrap.dedent(
                    """
                    CONFIG_TEST=n
                    CONFIG_TEST2=n
                    """
                )
            )
        self.args = Args(output="savedefconfig", config=cfg)

    def test_save_default(self, runner):
        runner(self.args, TestDefaults.input, "CONFIG_TEST=n")
        runner(self.args, TestDefaults.input, "# CONFIG_TEST is not set", test="not in")

    def test_save_default_with_labels(self, runner, tmp_path, monkeypatch):
        # Without labels
        runner(self.args, TestDefaults.input, "# This is a menu label", test="not in")
        without = open(os.path.join(str(tmp_path), "output")).read().splitlines(keepends=True)
        # Enable labels
        monkeypatch.setenv("ESP_IDF_KCONFIG_MIN_LABELS", "1")
        runner(self.args, TestDefaults.input, "# This is a menu label")
        with_labels = open(os.path.join(str(tmp_path), "output")).read().splitlines(keepends=True)
        assert "# This is a comment for TEST\n" not in with_labels
        assert with_labels.count("# Label\n") == 2
        stripped = with_labels[:3] + [
            line for line in with_labels[3:] if not (line.startswith("#") and line != "# default:\n") and line != "\n"
        ]
        assert stripped == without


@pytest.mark.parametrize("set_parser_version", KCONFIG_PARSER_VERSIONS, indirect=True)
class TestNonSetValues(KconfgenBaseTestCase):
    input = textwrap.dedent(
        """
        mainmenu "Test"

            menu "Test No Numerical Defaults"
                config IDF_TARGET
                    string "IDF target"
                    default "esp32"

                config INTEGER
                    int "This is an integer without default value."
                    default 1 if IDF_TARGET="esp48"

                config HEXADECIMAL
                    hex "This is a hexadecimal without default value."
                    default 0xAA if IDF_TARGET="esp48"
            endmenu
        """
    )

    @pytest.fixture(autouse=True)
    def init(self, tmp_path):
        cfg = os.path.join(str(tmp_path), "config")
        open(cfg, "w").close()
        self.args = Args(output="savedefconfig", config=cfg)

    def test_no_num_default(self, runner):
        self.args.output = "config"
        runner(self.args, TestNonSetValues.input, "CONFIG_INTEGER=1", test="not in")
        runner(self.args, TestNonSetValues.input, "CONFIG_HEXADECIMAL=0xAA", test="not in")


@pytest.mark.parametrize("set_parser_version", KCONFIG_PARSER_VERSIONS, indirect=True)
class TestChooseDefaultValue(KconfgenBaseTestCase):
    input = textwrap.dedent(
        """
        mainmenu "Test Choose Default Value"

            config FOO
                bool "Foo config option"
                default y

        """
    )

    @pytest.fixture(autouse=True)
    def init(self, tmp_path):
        sdk = os.path.join(str(tmp_path), "sdkconfig")
        with open(sdk, "w") as f:
            f.write("# default:\nCONFIG_FOO=n\n")
        self.args = Args(output="config", config=sdk)

    def test_default(self, runner):
        self.args.env = f"KCONFIG_DEFAULTS_POLICY={POLICY_USE_SDKCONFIG}"
        out = runner(self.args, TestChooseDefaultValue.input, "# CONFIG_FOO is not set")
        assert "# CONFIG_FOO is not set\n" in out.splitlines(True)

    def test_ignore_sdkconfig(self, runner):
        self.args.env = f"KCONFIG_DEFAULTS_POLICY={POLICY_USE_KCONFIG}"
        runner(self.args, TestChooseDefaultValue.input, "CONFIG_FOO=y")
