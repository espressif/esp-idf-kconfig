# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Trivial sanity test: IDF is reachable and ``idf.py --version`` succeeds.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable

import pytest

logger = logging.getLogger(__name__)


@pytest.mark.fast
@pytest.mark.cmakev2_fast
class TestFastSanity:
    """
    Verify the integration test infrastructure can reach IDF.
    """

    def test_idf_path_exists(self, idf_path: Path) -> None:
        assert idf_path.is_dir(), f"IDF_PATH {idf_path} is not a directory"
        assert (idf_path / "tools" / "idf.py").is_file(), "idf.py not found"

    def test_idf_py_version(
        self,
        idf_py: Callable[..., "subprocess.CompletedProcess[str]"],
    ) -> None:
        result = idf_py("--version", check=False)
        logger.info("idf.py --version stdout: %s", result.stdout.strip())
        assert result.returncode == 0, f"idf.py --version failed: {result.stderr}"
        assert "ESP-IDF" in result.stdout, f"Unexpected idf.py --version output: {result.stdout}"
