# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from esp_kconfiglib.legacy_constructs import find_legacy_constructs


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "Kconfig"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "line, expected_fragment",
    [
        ('        tristate "foo"', "'tristate' type"),
        ("        def_bool y", "'def_<type>' shorthand"),
        ("        def_tristate m", "'def_<type>' shorthand"),
        ("    config FOO.BAR", "config/choice name"),
        ('gsource "Kconfig.x"', "'gsource'/'grsource' keyword"),
        ('grsource "Kconfig.x"', "'gsource'/'grsource' keyword"),
    ],
)
def test_detects_construct_on_reported_line(tmp_path, line, expected_fragment):
    path = _write(tmp_path, f'mainmenu "T"\n{line}\n')
    matches = find_legacy_constructs(str(path), 2)
    assert matches
    assert expected_fragment in matches[0].description
    assert matches[0].line_nr == 2


def test_ignores_supported_option_env(tmp_path):
    path = _write(tmp_path, "        option env=MY_VAR\n")
    assert find_legacy_constructs(str(path), 1) == []


def test_ignores_quoted_choice_name(tmp_path):
    path = _write(tmp_path, '    choice "Connection Method"\n')
    assert find_legacy_constructs(str(path), 1) == []


def test_ignores_plain_help_keyword(tmp_path):
    path = _write(tmp_path, "        help\n")
    assert find_legacy_constructs(str(path), 1) == []


def test_detects_mainmenu_in_sourced_file(tmp_path):
    root = _write(tmp_path, 'mainmenu "T"\n')
    sourced = tmp_path / "Kconfig.sub"
    sourced.write_text('mainmenu "Sub"\n', encoding="utf-8")
    matches = find_legacy_constructs(str(sourced), 1, str(root))
    assert len(matches) == 1
    assert "'mainmenu' outside the root Kconfig file" in matches[0].description


@pytest.mark.parametrize("pass_root", [True, False])
def test_ignores_mainmenu_in_root_file(tmp_path, pass_root):
    root = _write(tmp_path, 'mainmenu "T"\nconfig\n')
    assert find_legacy_constructs(str(root), 2, str(root) if pass_root else None) == []
