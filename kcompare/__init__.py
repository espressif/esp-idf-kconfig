# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Compare Kconfig configurations between two ESP-IDF commits.

Compares the full IDF component set. The current working directory must be
an ESP-IDF repository root.
"""

__all__ = ["main"]


def main() -> None:
    from .cli import main as _main

    _main()
