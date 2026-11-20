# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
from typing import Optional

import pytest

from esp_kconfiglib import Kconfig
from esp_kconfiglib.core import parser_version_from_kconfig_file
from esp_kconfiglib.core import select_parser_version

KCONFIG_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "kconfigs")

CONFIG_BODY = 'mainmenu "Test"\n\nconfig FOO\n    bool "Foo"\n'


def _set_env(monkeypatch: pytest.MonkeyPatch, version: Optional[str]) -> None:
    monkeypatch.delenv("srctree", raising=False)
    if version is None:
        monkeypatch.delenv("KCONFIG_PARSER_VERSION", raising=False)
    else:
        monkeypatch.setenv("KCONFIG_PARSER_VERSION", version)


def _write_kconfig(tmp_path: Path, header: str, body: str = CONFIG_BODY, name: str = "Kconfig") -> str:
    path = tmp_path / name
    path.write_text(header + body, encoding="utf-8")
    return str(path)


def _output(capsys: pytest.CaptureFixture) -> str:
    out, err = capsys.readouterr()
    return " ".join((out + err).split())  # rich wraps long lines


@pytest.mark.parametrize(
    "version, expected",
    [
        (None, 1),  # Nothing set -> library default (v1)
        ("", 1),  # Empty value is treated as unset
        ("  ", 1),  # Whitespace-only value is treated as unset
        ("1", 1),
        ("2", 2),
        (" 2 ", 2),  # Surrounding whitespace is ignored (e.g. "set VAR=2 && ..." in Windows cmd)
    ],
)
def test_parser_version_from_env(monkeypatch: pytest.MonkeyPatch, version: Optional[str], expected: int) -> None:
    _set_env(monkeypatch, version)

    assert select_parser_version() == expected
    assert Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.default_validity")).parser_version == expected


@pytest.mark.parametrize(
    "version, header, expected",
    [
        (None, "# kconfig-parser-version: 2\n", 2),  # Marker is used when the user did not choose
        (None, "# kconfig-parser-version: 1\n", 1),
        ("", "# kconfig-parser-version: 2\n", 2),
        ("1", "# kconfig-parser-version: 2\n", 1),  # User choice wins over the marker
        ("2", "# kconfig-parser-version: 1\n", 2),
        (None, "#kconfig-parser-version:2\n", 2),  # Whitespace around the marker parts is optional
        (None, "#\n# Some license header\n\n# kconfig-parser-version: 2\n#\n", 2),  # Anywhere in the leading block
        (None, CONFIG_BODY + "# kconfig-parser-version: 2\n", 1),  # Not in the leading comment block -> ignored
        (None, "# Kconfig-Parser-Version: 2\n", 1),  # Marker is case-sensitive
        (None, "# kconfig-parser-version 2\n", 1),  # Colon is required
        (None, "# Some comment\n", 1),  # No marker
    ],
)
def test_parser_version_from_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, version: Optional[str], header: str, expected: int
) -> None:
    _set_env(monkeypatch, version)
    kconfig = _write_kconfig(tmp_path, header, body="" if CONFIG_BODY in header else CONFIG_BODY)

    assert select_parser_version(kconfig) == expected
    assert Kconfig(kconfig).parser_version == expected


def test_marker_only_in_root_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, None)
    _write_kconfig(tmp_path, "# kconfig-parser-version: 2\n", body='config FOO\n    bool "Foo"\n', name="Kconfig.sub")
    root = _write_kconfig(tmp_path, "", body=f'mainmenu "Test"\n\nsource "{tmp_path / "Kconfig.sub"}"\n')

    assert select_parser_version(root) == 1
    assert Kconfig(root).parser_version == 1


def test_marker_respects_srctree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, None)
    _write_kconfig(tmp_path, "# kconfig-parser-version: 2\n")
    monkeypatch.setenv("srctree", str(tmp_path))

    assert parser_version_from_kconfig_file("Kconfig") == 2
    assert select_parser_version("Kconfig") == 2


def test_marker_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, None)

    assert parser_version_from_kconfig_file(str(tmp_path / "does-not-exist")) is None
    assert select_parser_version(str(tmp_path / "does-not-exist")) == 1


@pytest.mark.parametrize(
    "version, header, expected, warn_env, warn_marker",
    [
        # Invalid values are ignored with a warning, as if they were not set
        ("OFF", None, 1, True, False),  # CMake-style boolean
        ("v1", None, 1, True, False),
        ("0", "# kconfig-parser-version: 2\n", 2, True, False),
        ("3", "# kconfig-parser-version: 1\n", 1, True, False),
        (None, "# kconfig-parser-version: 3\n", 1, False, True),
        ("OFF", "# kconfig-parser-version: v2\n", 1, True, True),
        # The marker is not consulted at all once the user picked a valid version
        ("1", "# kconfig-parser-version: OFF\n", 1, False, False),
    ],
)
def test_parser_version_invalid(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    tmp_path: Path,
    version: Optional[str],
    header: Optional[str],
    expected: int,
    warn_env: bool,
    warn_marker: bool,
) -> None:
    _set_env(monkeypatch, version)
    kconfig = _write_kconfig(tmp_path, header) if header else None

    assert select_parser_version(kconfig) == expected
    output = _output(capsys)
    assert ("of the KCONFIG_PARSER_VERSION environment variable" in output) == warn_env, output
    assert ("of the kconfig-parser-version comment" in output) == warn_marker, output


def test_parser_version_argument_invalid(capsys: pytest.CaptureFixture) -> None:
    kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.default_validity"), parser_version=3)

    assert kconfig.parser_version == 1
    assert "unsupported Kconfig parser version '3'" in _output(capsys)


def test_explicit_argument_wins_over_marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, None)
    kconfig = _write_kconfig(tmp_path, "# kconfig-parser-version: 2\n")

    assert Kconfig(kconfig, parser_version=1).parser_version == 1
