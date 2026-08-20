# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Detect whether a directory is an ESP-IDF repository root.
"""

import os


def is_idf_root(path: str) -> bool:
    """
    Return True if *path* looks like an ESP-IDF repository root.

    Heuristic: has a root ``Kconfig`` and ``tools/cmake/project.cmake``.
    """
    return os.path.isfile(os.path.join(path, "Kconfig")) and os.path.isfile(
        os.path.join(path, "tools", "cmake", "project.cmake")
    )
