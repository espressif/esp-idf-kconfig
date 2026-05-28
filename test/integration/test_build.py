# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Integration build tests: ``idf.py set-target`` + ``idf.py build`` per
(example for each target for each parser version).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable
from typing import List
from typing import Tuple

import pytest

from .fixtures.examples import CMAKEV2_FAST_EXAMPLES
from .fixtures.examples import FAST_EXAMPLES
from .fixtures.examples import ExampleEntry
from .helpers.env import parser_versions

logger = logging.getLogger(__name__)


def _build_params(
    examples: Tuple[ExampleEntry, ...],
) -> List[pytest.param]:
    """
    Expand (example for each target for each parser version) into pytest params.

    Each param carries ``(example_path, target, parser_version)`` and an
    id like ``hello_world/esp32/pv1``.
    """
    params: List[pytest.param] = []
    versions = parser_versions()
    for entry in examples:
        if not entry.fast_targets:
            continue
        for target in entry.fast_targets:
            for pv in versions:
                short_name = Path(entry.path).name
                params.append(
                    pytest.param(
                        entry.path,
                        target,
                        pv,
                        id=f"{short_name}/{target}/pv{pv}",
                    )
                )
    return params


# ---------------------------------------------------------------------------
# Classic CMake fast tier
# ---------------------------------------------------------------------------


@pytest.mark.fast
@pytest.mark.parametrize(
    "example_path,target,parser_version",
    _build_params(FAST_EXAMPLES),
)
def test_build_classic(
    example_path: str,
    target: str,
    parser_version: str,
    idf_py: Callable[..., "subprocess.CompletedProcess[str]"],
    test_app_copy: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Build a classic-CMake example: set-target then build.
    """
    monkeypatch.setenv("KCONFIG_PARSER_VERSION", parser_version)
    app_dir = test_app_copy(example_path)
    _set_target_and_build(app_dir, target, idf_py)


# ---------------------------------------------------------------------------
# cmakev2 fast tier
# ---------------------------------------------------------------------------


@pytest.mark.cmakev2_fast
@pytest.mark.parametrize(
    "example_path,target,parser_version",
    _build_params(CMAKEV2_FAST_EXAMPLES),
)
def test_build_cmakev2(
    example_path: str,
    target: str,
    parser_version: str,
    idf_py: Callable[..., "subprocess.CompletedProcess[str]"],
    test_app_copy: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Build a cmakev2 example: set-target then build.
    """
    monkeypatch.setenv("KCONFIG_PARSER_VERSION", parser_version)
    app_dir = test_app_copy(example_path)
    _set_target_and_build(app_dir, target, idf_py)


# ---------------------------------------------------------------------------
# Shared build logic
# ---------------------------------------------------------------------------


def _set_target_and_build(
    app_dir: Path,
    target: str,
    idf_py: Callable[..., "subprocess.CompletedProcess[str]"],
) -> None:
    logger.info("set-target %s in %s", target, app_dir)
    result = idf_py("set-target", target, cwd=app_dir, check=False)
    if result.returncode != 0:
        pytest.fail(
            f"idf.py set-target {target} failed (rc={result.returncode}):\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    logger.info("build in %s", app_dir)
    result = idf_py("build", cwd=app_dir, check=False)
    if result.returncode != 0:
        pytest.fail(
            f"idf.py build failed (rc={result.returncode}):\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    logger.info("build succeeded: %s / %s", app_dir.name, target)
