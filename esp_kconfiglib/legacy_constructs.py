# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Detect unsupported legacy Kconfig constructs near a parser v2 error.

Parser v2 rejects some constructs that parser v1 still accepts. When kconfgen
re-parses a failed tree with v1, these matches distinguish an intentional
rejection from a possible parser bug.
"""

import re
from dataclasses import dataclass
from typing import List
from typing import Pattern
from typing import Tuple


@dataclass
class LegacyMatch:
    """
    One unsupported construct found near a parse error.
    """

    description: str
    line_nr: int
    line_text: str


# Every regex matches one legacy unsupported construct
_LINE_PATTERNS: Tuple[Tuple[Pattern[str], str], ...] = (
    (
        re.compile(r"^\s*-+help-+\s*$"),
        "'---help---'; use an indented 'help' keyword instead",
    ),
    (
        re.compile(r"^\s*tristate\b"),
        "'tristate' type; use 'bool' instead",
    ),
    (
        re.compile(r"^\s*def_(?:bool|int|hex|string|tristate|float)\b"),
        "'def_<type>' shorthand; split it into a type and a default",
    ),
    (
        re.compile(r"^\s*optional\b"),
        "'optional' on a choice; this keyword is not supported",
    ),
    (
        re.compile(r"^\s*option\b(?!\s*env=)"),
        "'option' other than 'option env='; this form is not supported",
    ),
    (
        re.compile(r"^\s*[A-Za-z0-9_]+\s*\+="),
        "preprocessor '+=' assignment; only 'NAME = value' and 'NAME := value' are supported",
    ),
    (
        re.compile(r"^\s*\$\("),
        "bare preprocessor macro call; only simple 'NAME = value' / 'NAME := value' macros are supported",
    ),
    (
        re.compile(r"^\s*[A-Za-z0-9_]+\s*:?=\s*\$\([^)\s]+,"),
        "preprocessor function call; only simple 'NAME = value' / 'NAME := value' macros are supported",
    ),
)

# Special case: malformed (menu)config/choice names
# A config/menuconfig/choice header; group 1 is the name token (FOO, FOO.BAR, "quoted").
_NAMED_ENTRY_RE = re.compile(r"^\s*(?:config|menuconfig|choice)\s+(\S+)\s*$")
# Parser v2 identifier: letters, digits and underscores only (lowercase is still accepted).
_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
# Quoted choice name, e.g. choice "Connection Method" — accepted with a deprecation notice.
_QUOTED_NAME_RE = re.compile(r"^[\"'].*[\"']$")
_ILLEGAL_NAME_DESC = "config/choice name with characters other than letters, digits and underscores"


def _strip_inline_comment(line: str) -> str:
    hash_pos = line.find("#")
    if hash_pos == -1:
        return line
    return line[:hash_pos]


def _matches_on_line(line: str) -> List[str]:
    stripped = _strip_inline_comment(line)
    found: List[str] = []
    for pattern, description in _LINE_PATTERNS:
        if pattern.search(stripped):
            found.append(description)

    # Check for illegal config/choice names
    name_match = _NAMED_ENTRY_RE.match(stripped)
    if name_match:
        name = name_match.group(1)
        if not _QUOTED_NAME_RE.match(name) and not _VALID_NAME_RE.match(name):
            found.append(_ILLEGAL_NAME_DESC)
    return found


def find_legacy_constructs(filename: str, linenum: int) -> List[LegacyMatch]:
    """
    Scan linenum and the adjacent lines of filename for unsupported constructs.

    Parser v2 often reports the error on the previous line (at the newline)
    when the next token is something like ``---help---``. Checking the
    neighbours covers that.
    """
    LINE_OFFSET = 1
    try:
        with open(filename, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []

    matches: List[LegacyMatch] = []
    seen = set()
    for line_nr in range(linenum - LINE_OFFSET, linenum + LINE_OFFSET + 1):
        if line_nr < 1 or line_nr > len(lines):
            continue
        line_text = lines[line_nr - 1]
        for description in _matches_on_line(line_text):
            if description in seen:
                continue
            seen.add(description)
            matches.append(LegacyMatch(description=description, line_nr=line_nr, line_text=line_text))
    return matches
