# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Exception types raised by kcompare.

All kcompare failures inherit from ``KcompareError`` so the CLI can catch
one base type.
"""


class KcompareError(Exception):
    """
    Base exception for kcompare failures.
    """


class GitError(KcompareError):
    """
    Raised when a git operation fails or commit ordering is ambiguous.
    """


class IdfEnvError(KcompareError):
    """
    Raised when eim install or environment capture fails (or eim is missing).
    """


class SnapshotError(KcompareError):
    """
    Raised when a configuration snapshot cannot be built.
    """
