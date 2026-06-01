# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
pytest configuration and fixtures for esp-idf-kconfig integration tests with ESP-IDF.

The tests assume pytest is launched from inside an active ESP-IDF Python
environment (CI ``before_script`` sources ``export.{sh,ps1}`` and then
installs esp-idf-kconfig into IDF's venv). That makes ``sys.executable``
the right interpreter for invoking ``idf.py`` directly via
``subprocess.run`` — no PATH or environment merging is required.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Iterator
from typing import Optional

import pytest

from .helpers.env import get_idf_head_sha
from .helpers.env import get_idf_path
from .helpers.env import get_idf_version
from .helpers.env import get_python_version

logger = logging.getLogger(__name__)

IGNORE_COPY = {
    "build",
    "sdkconfig",
    "sdkconfig.old",
    "managed_components",
    "dependencies.lock",
    ".component_hash",
    ".git",
    "__pycache__",
}


# ---------------------------------------------------------------------------
# CLI options
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--work-dir",
        default=None,
        help="Persistent work directory for temp files (not cleaned up on failure).",
    )


# ---------------------------------------------------------------------------
# Sharding (opt-in via INTEGRATION_SHARD_TOTAL / INTEGRATION_SHARD_INDEX)
# ---------------------------------------------------------------------------
# We use dedicated env vars instead of CI_NODE_TOTAL/CI_NODE_INDEX because
# GitLab sets those for parallel:matrix: as well, which would incorrectly
# shard tests across matrix cells that differ only in IDF_BRANCH.


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:  # type: ignore[type-arg]
    count = int(os.environ.get("INTEGRATION_SHARD_TOTAL", "1"))
    index = int(os.environ.get("INTEGRATION_SHARD_INDEX", "0"))
    if count <= 1:
        return

    selected = [item for i, item in enumerate(items) if i % count == index]
    deselected = [item for i, item in enumerate(items) if i % count != index]
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected


# ---------------------------------------------------------------------------
# Report header (IDF version, SHA, Python version in CI logs)
# ---------------------------------------------------------------------------


def pytest_report_header(config: pytest.Config) -> str:
    try:
        idf_path = get_idf_path()
    except RuntimeError:
        return "IDF_PATH: NOT SET"

    version = get_idf_version(idf_path)
    sha = get_idf_head_sha(idf_path)
    py_ver = get_python_version()
    return f"IDF_PATH: {idf_path}\nIDF version: {version[0]}.{version[1]}  (HEAD: {sha})\nPython: {py_ver}"


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def idf_path() -> Path:
    """
    Return the resolved IDF_PATH; fail immediately if unset.
    """
    return get_idf_path()


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def idf_py(idf_path: Path) -> Callable[..., subprocess.CompletedProcess]:  # type: ignore[type-arg]
    """
    Return a callable that invokes ``idf.py <args>`` via ``sys.executable``.

    Pytest is expected to be running inside IDF's active Python venv, so
    ``sys.executable`` is the interpreter that has IDF's deps (``click``,
    ``pyparsing``, etc.). ``capture_output=True`` and ``text=True`` are
    set by default; callers can override either via ``**kwargs``.
    """

    def _run(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
        cmd = [sys.executable, str(idf_path / "tools" / "idf.py"), *args]
        kwargs.setdefault("capture_output", True)
        kwargs.setdefault("text", True)
        logger.info("Running: %s", " ".join(cmd))
        return subprocess.run(cmd, **kwargs)

    return _run


@pytest.fixture
def test_app_copy(
    request: pytest.FixtureRequest,
    idf_path: Path,
    tmp_path: Path,
) -> Path:
    """
    Copy an example app to a temp directory and return the path.

    The ``request.param`` must be the path relative to IDF_PATH
    (e.g. ``"examples/get-started/hello_world"``).
    """
    rel_path: str = request.param
    src = idf_path / rel_path
    if not src.is_dir():
        pytest.skip(f"Example {rel_path} not found at {src}")

    dst = tmp_path / Path(rel_path).name

    def _ignore(directory: str, contents: list) -> list:  # type: ignore[type-arg]
        return [c for c in contents if c in IGNORE_COPY]

    shutil.copytree(str(src), str(dst), ignore=_ignore)
    return dst


@pytest.fixture
def idf_copy(idf_path: Path, tmp_path: Path) -> Iterator[Path]:
    """
    Full IDF copy via ``git worktree add`` (fast, no network).

    Currently no integration test needs to mutate IDF, but the fixture is
    prepared for future use.
    """
    worktree_path = tmp_path / "idf_worktree"
    branch_name = f"test-worktree-{os.getpid()}"

    try:
        subprocess.run(
            ["git", "worktree", "add", "-B", branch_name, str(worktree_path), "HEAD"],
            cwd=str(idf_path),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        pytest.fail(f"git worktree add failed: {e.stderr}")

    dot_git = worktree_path / ".git"
    if dot_git.exists():
        if dot_git.is_file():
            dot_git.unlink()
        else:
            shutil.rmtree(str(dot_git))

    yield worktree_path

    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=str(idf_path),
        check=False,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        cwd=str(idf_path),
        check=False,
        capture_output=True,
    )


@pytest.fixture
def work_dir(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """
    Return a working directory: either ``--work-dir`` or tmp_path.
    """
    custom: Optional[str] = request.config.getoption("--work-dir")
    if custom:
        p = Path(custom)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return tmp_path
