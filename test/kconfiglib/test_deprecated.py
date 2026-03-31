# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile

import pytest

from esp_kconfiglib import Kconfig
from esp_kconfiglib.constants import DEP_OP_BEGIN
from esp_kconfiglib.constants import DEP_OP_END
from esp_kconfiglib.core import BOOL
from esp_kconfiglib.core import INT
from esp_kconfiglib.core import STRING
from esp_kconfiglib.deprecated import DeprecatedOptions
from esp_kconfiglib.report import STATUS_OK
from esp_kconfiglib.report import VERBOSITY_VERBOSE
from esp_kconfiglib.report import KconfigReport
from esp_kconfiglib.report import MiscArea

TEST_DIR = os.path.join(os.path.dirname(__file__), "deprecated")
KCONFIG = os.path.join(TEST_DIR, "Kconfig")
RENAME_FILE = os.path.join(TEST_DIR, "sdkconfig.rename")
RENAME_FILE_2 = os.path.join(TEST_DIR, "sdkconfig.rename2")
RENAME_SYNTAX_ERROR = os.path.join(TEST_DIR, "rename.syntax_error")
RENAME_SAME_NAME = os.path.join(TEST_DIR, "rename.same_name")
RENAME_MISSING_PREFIX = os.path.join(TEST_DIR, "rename.missing_prefix")
SDKCONFIG_LEGACY_SPEED = os.path.join(TEST_DIR, "sdkconfig.legacy_speed")
RENAME_DUPLICATE_OLD_A = os.path.join(TEST_DIR, "rename.duplicate_old_a")
SDKCONFIG_DUPLICATE_OLD_A = os.path.join(TEST_DIR, "sdkconfig.duplicate_old_a")


@pytest.fixture
def kconfig():
    """Create a Kconfig instance with rename files loaded."""
    config = Kconfig(KCONFIG)
    config.load_rename_files([RENAME_FILE])
    return config


@pytest.fixture
def kconfig_no_rename():
    """Create a Kconfig instance without rename files."""
    return Kconfig(KCONFIG)


class TestLoadRenameFiles:
    def test_load_rename_files(self, kconfig):
        assert kconfig.deprecated_options is not None
        assert kconfig.deprecated_options.has_entries

    def test_no_rename_files(self, kconfig_no_rename):
        assert kconfig_no_rename.deprecated_options is None

    def test_rename_mappings(self, kconfig):
        do = kconfig.deprecated_options
        assert do.get_new_option("OLD_FEATURE_ENABLE") == "FEATURE_ENABLE"
        assert do.get_new_option("OLD_SPEED") == "FEATURE_SPEED"
        assert do.get_new_option("OLD_NAME") == "FEATURE_NAME"
        assert do.get_new_option("OLD_ADDR") == "FEATURE_ADDR"
        assert do.get_new_option("INVERTED_ENABLE") == "FEATURE_DISABLE"

    def test_reverse_mappings(self, kconfig):
        do = kconfig.deprecated_options
        assert "OLD_FEATURE_ENABLE" in do.get_deprecated_option("FEATURE_ENABLE")
        assert "OLD_SPEED" in do.get_deprecated_option("FEATURE_SPEED")

    def test_inversions(self, kconfig):
        do = kconfig.deprecated_options
        assert do.is_inversion("INVERTED_ENABLE")
        assert do.is_inversion("INVERTED_ANOTHER")
        assert not do.is_inversion("OLD_FEATURE_ENABLE")

    def test_nonexistent_option(self, kconfig):
        assert kconfig.deprecated_options.get_new_option("NONEXISTENT") is None


class TestLoadConfigWithDeprecated:
    def test_deprecated_bool_resolved(self, kconfig):
        """Deprecated bool option value is applied to the new symbol."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.old_names"), replace=False)
        assert kconfig.syms["FEATURE_ENABLE"].str_value == "y"

    def test_deprecated_int_resolved(self, kconfig):
        """Deprecated int option value is applied to the new symbol."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.old_names"), replace=False)
        assert kconfig.syms["FEATURE_SPEED"].str_value == "200"

    def test_deprecated_string_resolved(self, kconfig):
        """Deprecated string option value is applied to the new symbol."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.old_names"), replace=False)
        assert kconfig.syms["FEATURE_NAME"].str_value == "custom_name"

    def test_deprecated_hex_resolved(self, kconfig):
        """Deprecated hex option value is applied to the new symbol."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.old_names"), replace=False)
        assert kconfig.syms["FEATURE_ADDR"].str_value == "0xAB"

    def test_deprecated_not_in_missing_syms(self, kconfig):
        """Deprecated options should not appear in missing_syms."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.old_names"), replace=True)
        missing_names = [name for name, _ in kconfig.missing_syms]
        assert "OLD_FEATURE_ENABLE" not in missing_names
        assert "OLD_SPEED" not in missing_names
        assert "OLD_NAME" not in missing_names
        assert "OLD_ADDR" not in missing_names

    def test_unknown_still_in_missing_syms(self, kconfig):
        """Truly unknown options (not deprecated) should still appear in missing_syms."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.unknown"), replace=True)
        missing_names = [name for name, _ in kconfig.missing_syms]
        assert "TRULY_UNKNOWN_OPTION" in missing_names
        assert "OLD_FEATURE_ENABLE" not in missing_names

    def test_inversion_set_to_y(self, kconfig):
        """Inverted deprecated option: CONFIG_INVERTED_ENABLE=y -> CONFIG_FEATURE_DISABLE=n."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.inversion"), replace=False)
        assert kconfig.syms["FEATURE_DISABLE"].str_value == "n"

    def test_inversion_set_to_n(self, kconfig):
        """Inverted deprecated option: CONFIG_INVERTED_ANOTHER=n -> CONFIG_ANOTHER_BOOL=y."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.inversion"), replace=False)
        assert kconfig.syms["ANOTHER_BOOL"].str_value == "y"

    def test_inversion_unset(self, kconfig):
        """Inverted deprecated option: '# CONFIG_INVERTED_ENABLE is not set' -> CONFIG_FEATURE_DISABLE=y."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.inversion_unset"), replace=False)
        assert kconfig.syms["FEATURE_DISABLE"].str_value == "y"

    def test_inversion_unset_another(self, kconfig):
        """Inverted deprecated option: '# CONFIG_INVERTED_ANOTHER is not set' -> CONFIG_ANOTHER_BOOL=y."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.inversion_unset"), replace=False)
        assert kconfig.syms["ANOTHER_BOOL"].str_value == "y"

    def test_both_names_new_wins(self, kconfig):
        """When both old and new names are present, the last assignment wins."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.both_names"), replace=False)
        # CONFIG_OLD_FEATURE_ENABLE=n sets FEATURE_ENABLE=n first,
        # then CONFIG_FEATURE_ENABLE=y overrides it
        assert kconfig.syms["FEATURE_ENABLE"].str_value == "y"

    def test_without_rename_files_deprecated_is_missing(self, kconfig_no_rename):
        """Without rename files, deprecated names appear in missing_syms."""
        kconfig_no_rename.load_config(os.path.join(TEST_DIR, "sdkconfig.old_names"), replace=True)
        missing_names = [name for name, _ in kconfig_no_rename.missing_syms]
        assert "OLD_FEATURE_ENABLE" in missing_names


class TestWriteConfigDeprecated:
    def test_write_config_with_deprecated(self, kconfig):
        """write_config(write_deprecated=True) includes the deprecated block."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".config", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_config(tmp, write_deprecated=True)
            with open(tmp) as f:
                contents = f.read()
            assert DEP_OP_BEGIN in contents
            assert DEP_OP_END in contents
            assert "CONFIG_OLD_FEATURE_ENABLE=y" in contents
            assert "CONFIG_OLD_SPEED=200" in contents
        finally:
            os.unlink(tmp)

    def test_write_config_without_deprecated(self, kconfig):
        """write_config(write_deprecated=False) omits the deprecated block."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".config", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_config(tmp, write_deprecated=False)
            with open(tmp) as f:
                contents = f.read()
            assert DEP_OP_BEGIN not in contents
            assert DEP_OP_END not in contents
        finally:
            os.unlink(tmp)

    def test_write_config_default_no_deprecated(self, kconfig):
        """write_config() default does not include deprecated block."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".config", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_config(tmp)
            with open(tmp) as f:
                contents = f.read()
            assert DEP_OP_BEGIN not in contents
        finally:
            os.unlink(tmp)

    def test_write_config_inversion_in_deprecated_block(self, kconfig):
        """Inversions are correctly written in the deprecated block."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        # FEATURE_ENABLE=y, FEATURE_DISABLE=n (default), ANOTHER_BOOL=y (default)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".config", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_config(tmp, write_deprecated=True)
            with open(tmp) as f:
                contents = f.read()
            # INVERTED_ENABLE is inversion of FEATURE_DISABLE
            # FEATURE_DISABLE=n -> INVERTED_ENABLE=y (inverted)
            assert "CONFIG_INVERTED_ENABLE=y" in contents
        finally:
            os.unlink(tmp)


class TestWriteAutoconfDeprecated:
    def test_write_autoconf_with_deprecated(self, kconfig):
        """write_autoconf(write_deprecated=True) includes deprecated #defines."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_autoconf(tmp, write_deprecated=True)
            with open(tmp) as f:
                contents = f.read()
            assert "List of deprecated options" in contents
            assert "#define CONFIG_OLD_FEATURE_ENABLE CONFIG_FEATURE_ENABLE" in contents
        finally:
            os.unlink(tmp)

    def test_write_autoconf_without_deprecated(self, kconfig):
        """write_autoconf(write_deprecated=False) omits deprecated #defines."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_autoconf(tmp, write_deprecated=False)
            with open(tmp) as f:
                contents = f.read()
            assert "List of deprecated options" not in contents
        finally:
            os.unlink(tmp)

    def test_write_autoconf_inversion_defines(self, kconfig):
        """Inverted deprecated options get ! prefix in #define."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_autoconf(tmp, write_deprecated=True)
            with open(tmp) as f:
                contents = f.read()
            assert "#define CONFIG_INVERTED_ENABLE !CONFIG_FEATURE_DISABLE" not in contents
            # FEATURE_DISABLE is "n" so its deprecated alias should NOT appear
            # (only defined options appear in the header)
        finally:
            os.unlink(tmp)


class TestSyncDepsDeprecated:
    def test_sync_deps_touches_deprecated_aliases(self, kconfig):
        """sync_deps() should touch cdep files for deprecated aliases."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.TemporaryDirectory() as deps_dir:
            kconfig.sync_deps(deps_dir)
            # FEATURE_ENABLE=y, so feature/enable.cdep should exist
            feature_enable_path = os.path.join(deps_dir, "feature", "enable.cdep")
            assert os.path.exists(feature_enable_path)
            # Its deprecated alias OLD_FEATURE_ENABLE should also be touched
            old_feature_enable_path = os.path.join(deps_dir, "old", "feature", "enable.cdep")
            assert os.path.exists(old_feature_enable_path)

    def test_sync_deps_touches_int_deprecated_aliases(self, kconfig):
        """sync_deps() should touch cdep files for deprecated int aliases."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.TemporaryDirectory() as deps_dir:
            kconfig.sync_deps(deps_dir)
            old_speed_path = os.path.join(deps_dir, "old", "speed.cdep")
            assert os.path.exists(old_speed_path)


class TestTypeInheritance:
    def test_deprecated_inherits_type_from_new_symbol(self, kconfig):
        """When a deprecated option is loaded, the value is applied using the new symbol's type."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.old_names"), replace=False)
        # The new symbol FEATURE_SPEED is INT, so even though we load via deprecated name,
        # the value is treated as INT
        sym = kconfig.syms["FEATURE_SPEED"]
        assert sym.str_value == "200"
        assert sym.orig_type == INT

    def test_deprecated_string_inherits_type(self, kconfig):
        """String type is correctly inherited."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.old_names"), replace=False)
        sym = kconfig.syms["FEATURE_NAME"]
        assert sym.str_value == "custom_name"
        assert sym.orig_type == STRING


class TestDeprecatedBlockSkip:
    def test_deprecated_block_skipped_by_default(self, kconfig_no_rename):
        """When load_deprecated=False (default), the entire deprecated block is skipped.

        This means tools like menuconfig can safely load a sdkconfig that
        contains a deprecated block without getting spurious missing_syms entries.
        """
        kconfig_no_rename.load_config(os.path.join(TEST_DIR, "sdkconfig.with_deprecated_block"), replace=True)
        missing_names = [name for name, _ in kconfig_no_rename.missing_syms]
        assert "OLD_FEATURE_ENABLE" not in missing_names
        assert "OLD_SPEED" not in missing_names
        # But the real symbols should still be loaded
        assert kconfig_no_rename.syms["FEATURE_ENABLE"].str_value == "y"
        assert kconfig_no_rename.syms["FEATURE_SPEED"].str_value == "200"

    def test_deprecated_block_loaded_when_requested(self, kconfig_no_rename):
        """When load_deprecated=True, deprecated block symbols are loaded."""
        kconfig_no_rename.load_config(
            os.path.join(TEST_DIR, "sdkconfig.with_deprecated_block"),
            replace=True,
            load_deprecated=True,
        )
        assert "OLD_FEATURE_ENABLE" in kconfig_no_rename.syms
        assert kconfig_no_rename.syms["OLD_FEATURE_ENABLE"].str_value == "y"


class TestRoundTrip:
    def test_write_then_load_preserves_values(self, kconfig):
        """Write sdkconfig with deprecated block, load it back, verify values match."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".config", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_config(tmp, write_deprecated=True)

            config2 = Kconfig(KCONFIG)
            config2.load_rename_files([RENAME_FILE])
            config2.load_config(tmp, replace=False)

            assert config2.syms["FEATURE_ENABLE"].str_value == "y"
            assert config2.syms["FEATURE_SPEED"].str_value == "200"
            assert config2.syms["FEATURE_NAME"].str_value == "custom_name"
            assert config2.syms["FEATURE_ADDR"].str_value == "0xAB"
        finally:
            os.unlink(tmp)

    def test_round_trip_deprecated_block_skipped(self, kconfig):
        """After round-trip, deprecated block does not pollute missing_syms."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".config", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_config(tmp, write_deprecated=True)

            config2 = Kconfig(KCONFIG)
            config2.load_config(tmp, replace=True)
            missing_names = [name for name, _ in config2.missing_syms]
            assert "OLD_FEATURE_ENABLE" not in missing_names
            assert "OLD_SPEED" not in missing_names
        finally:
            os.unlink(tmp)


class TestNonInvertedUnset:
    def test_noninverted_unset_resolves_to_n(self, kconfig):
        """Non-inverted '# CONFIG_OLD is not set' resolves to new_symbol=n."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.unset_noninverted"), replace=False)
        assert kconfig.syms["FEATURE_ENABLE"].str_value == "n"

    def test_noninverted_unset_not_in_missing_syms(self, kconfig):
        """Non-inverted unset deprecated option should not appear in missing_syms."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.unset_noninverted"), replace=True)
        missing_names = [name for name, _ in kconfig.missing_syms]
        assert "OLD_FEATURE_ENABLE" not in missing_names


class TestWriteDeprecatedTypeCoverage:
    def test_write_config_string_in_deprecated_block(self, kconfig):
        """String values are correctly quoted in the deprecated block."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".config", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_config(tmp, write_deprecated=True)
            with open(tmp) as f:
                contents = f.read()
            assert 'CONFIG_OLD_NAME="custom_name"' in contents
        finally:
            os.unlink(tmp)

    def test_write_config_hex_in_deprecated_block(self, kconfig):
        """Hex values include 0x prefix in the deprecated block."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".config", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_config(tmp, write_deprecated=True)
            with open(tmp) as f:
                contents = f.read()
            assert "CONFIG_OLD_ADDR=0x" in contents
        finally:
            os.unlink(tmp)

    def test_write_config_unset_bool_in_deprecated_block(self, kconfig):
        """Unset bool deprecated options are written as '# CONFIG_X is not set'."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        kconfig.syms["FEATURE_ENABLE"].set_value("n")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".config", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_config(tmp, write_deprecated=True)
            with open(tmp) as f:
                contents = f.read()
            assert "# CONFIG_OLD_FEATURE_ENABLE is not set" in contents
        finally:
            os.unlink(tmp)

    def test_write_autoconf_int_define(self, kconfig):
        """Int deprecated options appear as #define in autoconf header."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_autoconf(tmp, write_deprecated=True)
            with open(tmp) as f:
                contents = f.read()
            assert "#define CONFIG_OLD_SPEED CONFIG_FEATURE_SPEED" in contents
        finally:
            os.unlink(tmp)

    def test_write_autoconf_string_define(self, kconfig):
        """String deprecated options appear as #define in autoconf header."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_autoconf(tmp, write_deprecated=True)
            with open(tmp) as f:
                contents = f.read()
            assert "#define CONFIG_OLD_NAME CONFIG_FEATURE_NAME" in contents
        finally:
            os.unlink(tmp)

    def test_write_autoconf_hex_define(self, kconfig):
        """Hex deprecated options appear as #define in autoconf header."""
        kconfig.load_config(os.path.join(TEST_DIR, "sdkconfig.new_names"), replace=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".h", delete=False) as f:
            tmp = f.name
        try:
            kconfig.write_autoconf(tmp, write_deprecated=True)
            with open(tmp) as f:
                contents = f.read()
            assert "#define CONFIG_OLD_ADDR CONFIG_FEATURE_ADDR" in contents
        finally:
            os.unlink(tmp)


class TestRenameFileErrors:
    def _report(self):
        return Kconfig(KCONFIG).report

    def test_syntax_error(self):
        """Malformed line in rename file raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Syntax error"):
            DeprecatedOptions("CONFIG_", self._report(), path_rename_files=[RENAME_SYNTAX_ERROR])

    def test_same_name_replacement(self):
        """Mapping an option to itself raises RuntimeError."""
        with pytest.raises(RuntimeError, match="same as original name"):
            DeprecatedOptions("CONFIG_", self._report(), path_rename_files=[RENAME_SAME_NAME])

    def test_missing_config_prefix(self):
        """Option without correct CONFIG_ prefix raises RuntimeError."""
        with pytest.raises(RuntimeError):
            DeprecatedOptions("CONFIG_", self._report(), path_rename_files=[RENAME_MISSING_PREFIX])


class TestDuplicateRenameMappings:
    @pytest.fixture(autouse=True)
    def _reset_kconfig_report_singleton(self):
        """
        KconfigReport is a singleton; verbosity is read from env only on first __init__ per instance,
        so we need to reset it between tests.
        """
        KconfigReport._instance = None
        yield
        KconfigReport._instance = None

    def test_last_mapping_used(self):
        """When the same deprecated name is mapped twice, the last target wins."""
        config = Kconfig(KCONFIG)
        config.load_rename_files([RENAME_DUPLICATE_OLD_A])
        assert config.deprecated_options.get_new_option("OLD_A") == "FEATURE_SPEED"

    def test_resolved_value_uses_last_mapping(self):
        config = Kconfig(KCONFIG)
        config.load_rename_files([RENAME_DUPLICATE_OLD_A])
        config.load_config(SDKCONFIG_DUPLICATE_OLD_A, replace=False)
        assert config.syms["FEATURE_SPEED"].str_value == "200"
        assert config.syms["FEATURE_ENABLE"].str_value == "y"

    def test_duplicate_misc_not_in_report_when_verbosity_default(self, monkeypatch):
        monkeypatch.delenv("KCONFIG_REPORT_VERBOSITY", raising=False)
        config = Kconfig(KCONFIG)
        config.load_rename_files([RENAME_DUPLICATE_OLD_A])
        misc = config.report.area_to_instance[MiscArea]
        assert not any("duplicate" in m.lower() and "last mapping is used" in m.lower() for m in misc.messages)

    def test_duplicate_misc_in_report_when_verbosity_verbose(self, monkeypatch):
        monkeypatch.setenv("KCONFIG_REPORT_VERBOSITY", VERBOSITY_VERBOSE)
        config = Kconfig(KCONFIG)
        config.load_rename_files([RENAME_DUPLICATE_OLD_A])
        misc = config.report.area_to_instance[MiscArea]
        assert any("duplicate" in m.lower() and "last mapping is used" in m.lower() for m in misc.messages)

    def test_duplicate_misc_does_not_affect_status_when_verbosity_default(self, monkeypatch):
        monkeypatch.delenv("KCONFIG_REPORT_VERBOSITY", raising=False)
        config = Kconfig(KCONFIG)
        config.load_rename_files([RENAME_DUPLICATE_OLD_A])
        misc = config.report.area_to_instance[MiscArea]
        assert misc.report_severity() == STATUS_OK
        assert config.report.status == STATUS_OK


class TestUndefinedNewSymbol:
    def test_mapping_to_undefined_symbol_skips_silently(self):
        """If the new symbol doesn't exist in Kconfig, the deprecated name is not resolved."""
        config = Kconfig(KCONFIG)
        config.load_rename_files([RENAME_FILE])
        config.load_config(os.path.join(TEST_DIR, "sdkconfig.unknown"), replace=True)
        missing_names = [name for name, _ in config.missing_syms]
        assert "GHOST_OLD" in missing_names


class TestMultipleRenameFiles:
    def test_mappings_from_multiple_files(self):
        """Mappings from multiple rename files are merged."""
        config = Kconfig(KCONFIG)
        config.load_rename_files([RENAME_FILE, RENAME_FILE_2])
        do = config.deprecated_options

        # From first file
        assert do.get_new_option("OLD_FEATURE_ENABLE") == "FEATURE_ENABLE"
        # From second file
        assert do.get_new_option("LEGACY_SPEED") == "FEATURE_SPEED"

    def test_resolution_from_second_file(self):
        """Deprecated name from a second rename file is resolved during load."""
        config = Kconfig(KCONFIG)
        config.load_rename_files([RENAME_FILE, RENAME_FILE_2])
        config.load_config(SDKCONFIG_LEGACY_SPEED, replace=False)
        assert config.syms["FEATURE_SPEED"].str_value == "300"


class TestDeprecatedBlockTypeInheritance:
    def test_synthetic_symbol_inherits_type_from_new_symbol(self):
        """When load_deprecated=True with rename files, synthetic symbols inherit the new symbol's type."""
        config = Kconfig(KCONFIG)
        config.load_rename_files([RENAME_FILE])
        config.load_config(
            os.path.join(TEST_DIR, "sdkconfig.with_deprecated_block"),
            replace=True,
            load_deprecated=True,
        )
        old_speed = config.syms.get("OLD_SPEED")
        assert old_speed is not None
        assert old_speed.orig_type == INT

    def test_synthetic_bool_inherits_type(self):
        """Synthetic bool symbol inherits BOOL type from the new symbol."""
        config = Kconfig(KCONFIG)
        config.load_rename_files([RENAME_FILE])
        config.load_config(
            os.path.join(TEST_DIR, "sdkconfig.with_deprecated_block"),
            replace=True,
            load_deprecated=True,
        )
        old_enable = config.syms.get("OLD_FEATURE_ENABLE")
        assert old_enable is not None
        assert old_enable.orig_type == BOOL
