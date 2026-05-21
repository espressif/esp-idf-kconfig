# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Placeholder for interactive TUI tests (keypress simulation, screenshot diffs).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Interactive TUI tests tracked in IDF-15659")


def test_placeholder() -> None:
    pass
