# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for KconfigExpression (recursive descent parser).

Tests the parser in isolation — verifying AST structure, error rejection,
and parseImpl location tracking.
"""

from typing import Any
from typing import List

import pytest
from pyparsing import ParseException

from esp_kconfiglib.kconfig_grammar import expression


def _parse(expr: str) -> List[Any]:
    return expression.parse_string(expr, parse_all=True).as_list()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Correctness: verify exact AST output
# ---------------------------------------------------------------------------

VALID_EXPRESSIONS = [
    # --- bare atoms ---
    ("FOO", ["FOO"]),
    ("y", ["y"]),
    ("n", ["n"]),
    ('"y"', ['"y"']),
    ('"n"', ['"n"']),
    ("42", ["42"]),
    ("-42", ["-42"]),
    ("0x1234", ["0x1234"]),
    ("0XABCD", ["0XABCD"]),
    ('"hello"', ['"hello"']),
    ("'hello'", ["'hello'"]),
    ("4.4", ["4.4"]),
    ("5.3.1", ["5.3.1"]),
    ("-3.14", ["-3.14"]),
    ("1e-6", ["1e-6"]),
    ("-2.5E10", ["-2.5E10"]),
    ("$ENV_VAR", ["$ENV_VAR"]),
    ('"$ENV_VAR"', ['"$ENV_VAR"']),
    ("$(ENV_VAR)", ["$(ENV_VAR)"]),
    # long name
    (
        "VERY_LONG_AND_COMPLEX_NAME_WHICH_I_HAD_HARD_TIME_TO_COME_UP_WITH",
        ["VERY_LONG_AND_COMPLEX_NAME_WHICH_I_HAD_HARD_TIME_TO_COME_UP_WITH"],
    ),
    # --- unary negation ---
    ("!FOO", [["!", "FOO"]]),
    ("!!FOO", [["!", ["!", "FOO"]]]),
    ("!!!FOO", [["!", ["!", ["!", "FOO"]]]]),
    # --- comparisons ---
    ("A = B", [["A", "=", "B"]]),
    ("A != B", [["A", "!=", "B"]]),
    ("VER > 5.0", [["VER", ">", "5.0"]]),
    ("VER < 6.0", [["VER", "<", "6.0"]]),
    ("VER <= 5.3", [["VER", "<=", "5.3"]]),
    ("VER >= 5.3", [["VER", ">=", "5.3"]]),
    ('A = "hello"', [["A", "=", '"hello"']]),
    # chained comparisons stay flat
    ("A = B = C", [["A", "=", "B", "=", "C"]]),
    ("A < B < C", [["A", "<", "B", "<", "C"]]),
    # --- logical AND ---
    ("A && B", [["A", "&&", "B"]]),
    ("A && B && C && D", [["A", "&&", "B", "&&", "C", "&&", "D"]]),
    # --- logical OR ---
    ("A || B", [["A", "||", "B"]]),
    ("A || B || C || D", [["A", "||", "B", "||", "C", "||", "D"]]),
    # --- mixed precedence ---
    ("A && B || C", [[["A", "&&", "B"], "||", "C"]]),
    ("A || B && C", [["A", "||", ["B", "&&", "C"]]]),
    ("A && !B || C && D", [[["A", "&&", ["!", "B"]], "||", ["C", "&&", "D"]]]),
    ("!A || !B && C", [[["!", "A"], "||", [["!", "B"], "&&", "C"]]]),
    # --- parenthesised ---
    ("(A)", ["A"]),
    ("((A))", ["A"]),
    ("(A || B) && C", [[["A", "||", "B"], "&&", "C"]]),
    ("A && (B || C)", [["A", "&&", ["B", "||", "C"]]]),
    ("((A || B))", [["A", "||", "B"]]),
    ("(A || B) && (C) || (D && E)", [[[["A", "||", "B"], "&&", "C"], "||", ["D", "&&", "E"]]]),
    # --- comparison inside logical ---
    ("A = B && C != D", [[["A", "=", "B"], "&&", ["C", "!=", "D"]]]),
    ('G = "F" || G = "G"', [[["G", "=", '"F"'], "||", ["G", "=", '"G"']]]),
    ("VER > 5.0 && VER < 6.0", [[["VER", ">", "5.0"], "&&", ["VER", "<", "6.0"]]]),
    # --- negation with complex subexpression ---
    ("!(A && B) || C", [[["!", ["A", "&&", "B"]], "||", "C"]]),
    ("!A && !(B || C)", [[["!", "A"], "&&", ["!", ["B", "||", "C"]]]]),
    ("!(!(A && B) || !(C || D))", [["!", [["!", ["A", "&&", "B"]], "||", ["!", ["C", "||", "D"]]]]]),
    # --- deeply nested ---
    (
        "((A || B) && (C || D)) || ((E && F) || (G && H))",
        [
            [
                [["A", "||", "B"], "&&", ["C", "||", "D"]],
                "||",
                [["E", "&&", "F"], "||", ["G", "&&", "H"]],
            ]
        ],
    ),
]


@pytest.mark.parametrize("expr, expected", VALID_EXPRESSIONS, ids=[e for e, _ in VALID_EXPRESSIONS])
def test_valid_expression(expr: str, expected: List[Any]) -> None:
    assert _parse(expr) == expected


# ---------------------------------------------------------------------------
# Error rejection: invalid inputs must raise ParseException
# ---------------------------------------------------------------------------

INVALID_EXPRESSIONS: List[str] = [
    "&&",
    "||",
    "= FOO",
    "!= BAR",
    "()",
    "(A && B",
    "A )",
    "A && )",
    ") && A",
    "A || (B && )",
    "",
    "   ",
]


@pytest.mark.parametrize("expr", INVALID_EXPRESSIONS)
def test_invalid_expression(expr: str) -> None:
    with pytest.raises(ParseException):
        _parse(expr)


# ---------------------------------------------------------------------------
# parseImpl location tracking: verify end_pos after parsing
# ---------------------------------------------------------------------------

LOCATION_CASES = [
    ("FOO", 0, 3),
    ("A && B", 0, 6),
    ("  A && B", 0, 8),
    ("A || B && C", 0, 11),
    ("!(A || B)", 0, 9),
]


@pytest.mark.parametrize("instring, start, expected_end", LOCATION_CASES)
def test_parseimpl_end_position(instring: str, start: int, expected_end: int) -> None:
    end_pos, _ = expression.parseImpl(instring, start)
    assert end_pos == expected_end
