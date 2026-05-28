# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
IDF environment detection and KCONFIG_PARSER_VERSION toggling.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

_idf_targets_cache: Tuple[str, ...] = ()


def get_idf_path() -> Path:
    """
    Return the IDF_PATH from the environment, or raise.
    """
    raw = os.environ.get("IDF_PATH")
    if not raw:
        raise RuntimeError(
            "IDF_PATH is not set. Please activate your ESP-IDF environment before running integration tests."
        )
    p = Path(raw).resolve()
    if not (p / "tools" / "idf.py").is_file():
        raise RuntimeError(f"IDF_PATH={p} does not look like an ESP-IDF checkout (missing tools/idf.py).")
    return p


def get_idf_version(idf_path: Path) -> Tuple[int, int]:
    """
    Return (major, minor) from IDF_PATH/tools/cmake/version.cmake.
    """
    version_cmake = idf_path / "tools" / "cmake" / "version.cmake"
    if not version_cmake.is_file():
        return (0, 0)
    text = version_cmake.read_text(encoding="utf-8")
    major = _extract_cmake_var(text, "IDF_VERSION_MAJOR")
    minor = _extract_cmake_var(text, "IDF_VERSION_MINOR")
    return (major, minor)


def get_idf_head_sha(idf_path: Path) -> str:
    """
    Return the short HEAD SHA of the IDF checkout.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(idf_path),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _extract_cmake_var(text: str, var: str) -> int:
    m = re.search(rf"set\s*\(\s*{var}\s+(\d+)\s*\)", text)
    return int(m.group(1)) if m else 0


def idf_version_at_least(idf_path: Path, major: int, minor: int) -> bool:
    """
    Check if the IDF checkout is at least version (major, minor).
    """
    actual = get_idf_version(idf_path)
    return actual >= (major, minor)


def parser_versions() -> Tuple[str, ...]:
    """
    Return the KCONFIG_PARSER_VERSION values to parametrise over.
    """
    override = os.environ.get("INTEGRATION_PARSER_VERSIONS")
    if override:
        return tuple(v.strip() for v in override.split(",") if v.strip())
    return ("1", "2")


def set_parser_version(env: dict, version: str) -> dict:  # type: ignore[type-arg]
    """
    Return a copy of *env* with KCONFIG_PARSER_VERSION set.
    """
    new_env = dict(env)
    new_env["KCONFIG_PARSER_VERSION"] = version
    return new_env


def get_python_version() -> str:
    """
    Return the Python version string (e.g. '3.14.1').
    """

    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
