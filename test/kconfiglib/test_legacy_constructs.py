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
        ("        ---help---", "'---help---'"),
        ("        --help--", "'---help---'"),
        ('        tristate "foo"', "'tristate' type"),
        ("        def_bool y", "'def_<type>' shorthand"),
        ("        def_tristate m", "'def_<type>' shorthand"),
        ("        optional", "'optional' on a choice"),
        ("        option modules", "'option' other than"),
        ("    FOO += bar", "preprocessor '+='"),
        ("    $(warning-if,y,hello)", "bare preprocessor macro"),
        ("    FOO := $(shell,echo hi)", "preprocessor function call"),
        ("    config FOO.BAR", "config/choice name"),
    ],
)
def test_detects_construct_on_reported_line(tmp_path, line, expected_fragment):
    path = _write(tmp_path, f'mainmenu "T"\n{line}\n')
    matches = find_legacy_constructs(str(path), 2)
    assert matches
    assert expected_fragment in matches[0].description
    assert matches[0].line_nr == 2


def test_help_dashes_reported_on_previous_line(tmp_path):
    path = _write(
        tmp_path,
        'mainmenu "T"\n    config FOO\n        bool "foo"\n        ---help---\n          text\n',
    )
    # Even if the error is reported on the bool line (line 3), the next line is scanned.
    matches = find_legacy_constructs(str(path), 3)
    assert len(matches) == 1
    assert "'---help---'" in matches[0].description
    assert matches[0].line_nr == 4


def test_ignores_supported_option_env(tmp_path):
    path = _write(tmp_path, "        option env=MY_VAR\n")
    assert find_legacy_constructs(str(path), 1) == []


def test_ignores_quoted_choice_name(tmp_path):
    path = _write(tmp_path, '    choice "Connection Method"\n')
    assert find_legacy_constructs(str(path), 1) == []


def test_ignores_plain_help_keyword(tmp_path):
    path = _write(tmp_path, "        help\n")
    assert find_legacy_constructs(str(path), 1) == []
