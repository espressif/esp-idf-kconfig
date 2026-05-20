# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for deprecated-aware menuconfig save paths and `_main()` env-var loading."""

from pathlib import Path
from typing import Any
from typing import Dict
from typing import Iterator

import pytest

import esp_menuconfig
from esp_kconfiglib import Kconfig
from esp_kconfiglib.constants import DEP_OP_BEGIN
from esp_kconfiglib.constants import DEP_OP_END
from esp_menuconfig import menuconfig

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPRECATED_FIXTURES = REPO_ROOT / "test" / "kconfiglib" / "deprecated"
DEPRECATED_KCONFIG = DEPRECATED_FIXTURES / "Kconfig"
DEPRECATED_RENAME = DEPRECATED_FIXTURES / "sdkconfig.rename"
DEPRECATED_OLD_NAMES = DEPRECATED_FIXTURES / "sdkconfig.old_names"


@pytest.fixture(autouse=True)
def reset_report_singleton() -> Iterator[None]:
    """Reset the KconfigReport singleton between tests (it is a process-wide singleton)."""
    yield
    from esp_kconfiglib.report import KconfigReport

    instance = KconfigReport._instance
    if instance is not None:
        instance.reset()


@pytest.fixture
def kconfig_config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point KCONFIG_CONFIG to a tmp file so menuconfig() never touches the cwd."""
    sdkconfig = tmp_path / "sdkconfig"
    sdkconfig.write_text(DEPRECATED_OLD_NAMES.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("KCONFIG_CONFIG", str(sdkconfig))
    return sdkconfig


@pytest.fixture
def empty_kconfig_config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """KCONFIG_CONFIG pointing at an empty file (used by no-rename baseline tests)."""
    sdkconfig = tmp_path / "sdkconfig"
    sdkconfig.write_text("", encoding="utf-8")
    monkeypatch.setenv("KCONFIG_CONFIG", str(sdkconfig))
    return sdkconfig


def _build_kconfig() -> "Kconfig":
    return Kconfig(str(DEPRECATED_KCONFIG))


class TestMenuconfigWriteDeprecatedFlag:
    """Verify that ``write_deprecated`` is derived from the Kconfig's rename state."""

    def test_flag_true_when_rename_files_loaded(self, kconfig_config_env: Path) -> None:
        kconf = _build_kconfig()
        kconf.load_rename_files([str(DEPRECATED_RENAME)])

        menuconfig(kconf, headless=True)

        state = esp_menuconfig._module_state
        assert state is not None
        assert state.write_deprecated is True
        assert kconf.deprecated_options is not None
        assert kconf.deprecated_options.has_entries is True

    def test_flag_false_when_no_rename_files(self, empty_kconfig_config_env: Path) -> None:
        kconf = _build_kconfig()

        menuconfig(kconf, headless=True)

        state = esp_menuconfig._module_state
        assert state is not None
        assert state.write_deprecated is False
        assert kconf.deprecated_options is None


class TestMenuconfigSavePathsWriteDeprecated:
    """The save paths must propagate ``write_deprecated``."""

    def test_save_emits_deprecated_block(self, kconfig_config_env: Path, tmp_path: Path) -> None:
        kconf = _build_kconfig()
        kconf.load_rename_files([str(DEPRECATED_RENAME)])

        menuconfig(kconf, headless=True)
        state = esp_menuconfig._module_state
        assert state is not None
        assert state.write_deprecated is True

        out = tmp_path / "sdkconfig.out"
        kconf.write_config(str(out), write_deprecated=state.write_deprecated)

        contents = out.read_text(encoding="utf-8")
        assert DEP_OP_BEGIN in contents
        assert DEP_OP_END in contents
        assert "CONFIG_OLD_FEATURE_ENABLE=y" in contents
        assert "CONFIG_OLD_SPEED=200" in contents

    def test_save_omits_deprecated_block_without_renames(self, empty_kconfig_config_env: Path, tmp_path: Path) -> None:
        kconf = _build_kconfig()

        menuconfig(kconf, headless=True)
        state = esp_menuconfig._module_state
        assert state is not None
        assert state.write_deprecated is False

        out = tmp_path / "sdkconfig.out"
        kconf.write_config(str(out), write_deprecated=state.write_deprecated)

        contents = out.read_text(encoding="utf-8")
        assert DEP_OP_BEGIN not in contents
        assert DEP_OP_END not in contents


class TestMenuconfigSaveLambdaWiring:
    """Sanity check that the save path propagates ``write_deprecated``."""

    def test_save_dialog_lambda_threads_flag(
        self, kconfig_config_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kconf = _build_kconfig()
        kconf.load_rename_files([str(DEPRECATED_RENAME)])

        menuconfig(kconf, headless=True)
        state = esp_menuconfig._module_state
        assert state is not None
        assert state.write_deprecated is True

        out = tmp_path / "sdkconfig.s_key"

        def save_fn(fn: str) -> None:
            kconf.write_config(fn, write_deprecated=state.write_deprecated)

        save_fn(str(out))

        contents = out.read_text(encoding="utf-8")
        assert DEP_OP_BEGIN in contents


class TestMainEnvVarLoading:
    """`_main()` should discover rename files from env vars before delegating to menuconfig."""

    @pytest.fixture
    def patched_main(self, monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
        """Patch ``standard_kconfig`` and ``menuconfig`` so we can inspect what
        ``_main()`` builds without launching the TUI."""
        captured: Dict[str, Any] = {}

        def fake_standard_kconfig() -> Kconfig:
            kconf = _build_kconfig()
            captured["kconf"] = kconf
            return kconf

        def fake_menuconfig(kconf: Kconfig) -> None:
            captured["menuconfig_called_with"] = kconf

        monkeypatch.setattr("esp_kconfiglib.core.standard_kconfig", fake_standard_kconfig)
        monkeypatch.setattr("esp_menuconfig.menuconfig", fake_menuconfig)
        return captured

    def test_loads_renames_from_sdkconfig_rename(
        self,
        patched_main: Dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        empty_kconfig_config_env: Path,
    ) -> None:
        monkeypatch.setenv("SDKCONFIG_RENAME", str(DEPRECATED_RENAME))
        monkeypatch.delenv("COMPONENT_SDKCONFIG_RENAMES", raising=False)

        from esp_menuconfig.__main__ import _main

        _main()

        kconf = patched_main["kconf"]
        assert patched_main.get("menuconfig_called_with") is kconf
        assert kconf.deprecated_options is not None
        assert kconf.deprecated_options.has_entries is True

    def test_loads_renames_from_component_sdkconfig_renames_default_separator(
        self,
        patched_main: Dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        empty_kconfig_config_env: Path,
    ) -> None:
        monkeypatch.delenv("SDKCONFIG_RENAME", raising=False)
        monkeypatch.delenv("SDKCONFIG_RENAMES_LIST_SEPARATOR", raising=False)
        monkeypatch.setenv("COMPONENT_SDKCONFIG_RENAMES", str(DEPRECATED_RENAME))

        from esp_menuconfig.__main__ import _main

        _main()

        kconf = patched_main["kconf"]
        assert kconf.deprecated_options is not None
        assert kconf.deprecated_options.has_entries is True

    def test_loads_renames_from_component_sdkconfig_renames_semicolon(
        self,
        patched_main: Dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        empty_kconfig_config_env: Path,
    ) -> None:
        second_rename = tmp_path / "sdkconfig.rename.extra"
        second_rename.write_text("CONFIG_OLD_EXTRA CONFIG_FEATURE_ENABLE\n", encoding="utf-8")

        joined = f"{DEPRECATED_RENAME};{second_rename}"
        monkeypatch.delenv("SDKCONFIG_RENAME", raising=False)
        monkeypatch.setenv("SDKCONFIG_RENAMES_LIST_SEPARATOR", "semicolon")
        monkeypatch.setenv("COMPONENT_SDKCONFIG_RENAMES", joined)

        from esp_menuconfig.__main__ import _main

        _main()

        kconf = patched_main["kconf"]
        assert kconf.deprecated_options is not None
        assert kconf.deprecated_options.has_entries is True
        assert kconf.deprecated_options.get_new_option("OLD_EXTRA") == "FEATURE_ENABLE"

    def test_no_env_vars_means_no_rename_load(
        self,
        patched_main: Dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        empty_kconfig_config_env: Path,
    ) -> None:
        monkeypatch.delenv("SDKCONFIG_RENAME", raising=False)
        monkeypatch.delenv("COMPONENT_SDKCONFIG_RENAMES", raising=False)
        monkeypatch.delenv("SDKCONFIG_RENAMES_LIST_SEPARATOR", raising=False)

        from esp_menuconfig.__main__ import _main

        _main()

        kconf = patched_main["kconf"]
        assert kconf.deprecated_options is None
