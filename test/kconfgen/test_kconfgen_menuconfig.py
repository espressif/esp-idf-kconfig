# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for the kconfgen --menuconfig flag wiring."""

from pathlib import Path
from typing import Any
from typing import Iterator
from typing import List

import pytest

import kconfgen.core
from esp_kconfiglib import Kconfig
from esp_kconfiglib.constants import DEP_OP_BEGIN

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPRECATED_FIXTURES = REPO_ROOT / "test" / "kconfiglib" / "deprecated"
DEPRECATED_KCONFIG = DEPRECATED_FIXTURES / "Kconfig"
DEPRECATED_RENAME = DEPRECATED_FIXTURES / "sdkconfig.rename"
DEPRECATED_OLD_NAMES = DEPRECATED_FIXTURES / "sdkconfig.old_names"


@pytest.fixture(autouse=True)
def reset_report_singleton() -> Iterator[None]:
    """KconfigReport is a process-wide singleton; reset between tests."""
    yield
    from esp_kconfiglib.report import KconfigReport

    instance = KconfigReport._instance
    if instance is not None:
        instance.reset()


@pytest.fixture
def captured_menuconfig(monkeypatch: pytest.MonkeyPatch) -> List[Kconfig]:
    """Replace ``esp_menuconfig.menuconfig`` with a recorder that never blocks on curses."""
    import esp_menuconfig

    calls: List[Kconfig] = []

    def fake_menuconfig(kconf: Kconfig) -> None:
        calls.append(kconf)

    monkeypatch.setattr(esp_menuconfig, "menuconfig", fake_menuconfig)
    return calls


def _invoke_kconfgen(monkeypatch: pytest.MonkeyPatch, argv: List[str]) -> None:
    monkeypatch.setattr("sys.argv", ["kconfgen", *argv])
    kconfgen.core.main()


class TestKconfgenMenuconfigFlag:
    def test_menuconfig_flag_launches_tui_and_emits_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        captured_menuconfig: List[Kconfig],
    ) -> None:
        out = tmp_path / "sdkconfig.out"
        _invoke_kconfgen(
            monkeypatch,
            [
                "--kconfig",
                str(DEPRECATED_KCONFIG),
                "--output",
                "config",
                str(out),
                "--menuconfig",
            ],
        )

        assert len(captured_menuconfig) == 1
        assert isinstance(captured_menuconfig[0], Kconfig)
        assert out.exists(), "kconfgen should still emit the requested output file"
        contents = out.read_text(encoding="utf-8")
        assert "CONFIG_FEATURE_ENABLE=y" in contents

    def test_menuconfig_omitted_means_no_tui(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        captured_menuconfig: List[Kconfig],
    ) -> None:
        out = tmp_path / "sdkconfig.out"
        _invoke_kconfgen(
            monkeypatch,
            [
                "--kconfig",
                str(DEPRECATED_KCONFIG),
                "--output",
                "config",
                str(out),
            ],
        )

        assert captured_menuconfig == []
        assert out.exists()

    def test_menuconfig_with_renames_writes_deprecated_block(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        captured_menuconfig: List[Kconfig],
    ) -> None:
        config_in = tmp_path / "sdkconfig.in"
        config_in.write_text(DEPRECATED_OLD_NAMES.read_text(encoding="utf-8"), encoding="utf-8")
        out = tmp_path / "sdkconfig.out"

        _invoke_kconfgen(
            monkeypatch,
            [
                "--kconfig",
                str(DEPRECATED_KCONFIG),
                "--config",
                str(config_in),
                "--sdkconfig-rename",
                str(DEPRECATED_RENAME),
                "--output",
                "config",
                str(out),
                "--menuconfig",
            ],
        )

        assert len(captured_menuconfig) == 1
        contents = out.read_text(encoding="utf-8")
        assert DEP_OP_BEGIN in contents
        assert "CONFIG_OLD_FEATURE_ENABLE=y" in contents

    def test_menuconfig_with_dont_write_deprecated_skips_block(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        captured_menuconfig: List[Kconfig],
    ) -> None:
        config_in = tmp_path / "sdkconfig.in"
        config_in.write_text(DEPRECATED_OLD_NAMES.read_text(encoding="utf-8"), encoding="utf-8")
        out = tmp_path / "sdkconfig.out"

        _invoke_kconfgen(
            monkeypatch,
            [
                "--kconfig",
                str(DEPRECATED_KCONFIG),
                "--config",
                str(config_in),
                "--sdkconfig-rename",
                str(DEPRECATED_RENAME),
                "--output",
                "config",
                str(out),
                "--menuconfig",
                "--dont-write-deprecated",
            ],
        )

        assert len(captured_menuconfig) == 1
        contents = out.read_text(encoding="utf-8")
        assert DEP_OP_BEGIN not in contents


class TestKconfgenMenuconfigImportLocality:
    """``esp_menuconfig`` must only be imported when ``--menuconfig`` is set."""

    def test_no_curses_import_without_menuconfig(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Capture both Args namespace and confirm we can run without ever
        # touching esp_menuconfig if --menuconfig is not on the cli. We do not
        # actually try to scrub sys.modules here (esp_menuconfig may already be
        # loaded by the test runner); instead, sentinel that the local import
        # branch is gated on args.menuconfig by stubbing esp_menuconfig.menuconfig
        # to raise — a no-flag run must not touch it.
        import esp_menuconfig

        def boom(_kconf: Any) -> None:
            raise AssertionError("esp_menuconfig.menuconfig must not run without --menuconfig")

        monkeypatch.setattr(esp_menuconfig, "menuconfig", boom)

        out = tmp_path / "sdkconfig.out"
        _invoke_kconfgen(
            monkeypatch,
            [
                "--kconfig",
                str(DEPRECATED_KCONFIG),
                "--output",
                "config",
                str(out),
            ],
        )
        assert out.exists()
