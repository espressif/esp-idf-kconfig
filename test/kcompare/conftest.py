# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
pytest fixtures for kcompare tests.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict
from typing import Iterator
from typing import Optional

import pytest

from esp_kconfiglib.report import KconfigReport

FIXTURES = Path(__file__).resolve().parent / "fixtures"
IDF_OLDER = FIXTURES / "idf_older"
IDF_NEWER = FIXTURES / "idf_newer"
CWD_TRAP = FIXTURES / "cwd_trap"


def _git(repo: Path, *args: str, env: Optional[Dict[str, str]] = None) -> str:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=full_env,
    )
    return result.stdout.strip()


@dataclass(frozen=True)
class IdfGitRepo:
    path: Path
    older_sha: str
    newer_sha: str


def _init_idf_git_repo(tmp_path: Path) -> IdfGitRepo:
    """
    Build a git repo with two commits: idf_older then idf_newer.
    """
    repo = tmp_path / "idf_repo"
    if repo.exists():
        shutil.rmtree(repo)
    shutil.copytree(IDF_OLDER, repo)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "older")
    older_sha = _git(repo, "rev-parse", "HEAD")

    for entry in list(repo.iterdir()):
        if entry.name == ".git":
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    for entry in IDF_NEWER.iterdir():
        dest = repo / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dest)
        else:
            shutil.copy2(entry, dest)

    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "newer")
    newer_sha = _git(repo, "rev-parse", "HEAD")
    return IdfGitRepo(path=repo, older_sha=older_sha, newer_sha=newer_sha)


@pytest.fixture(autouse=True)
def _reset_kconfig_report() -> Iterator[None]:
    """
    KconfigReport is a process-wide singleton; clear it after each test.
    """
    yield
    instance = KconfigReport._instance
    if instance is not None:
        instance.reset()


@pytest.fixture
def idf_older() -> Path:
    return IDF_OLDER


@pytest.fixture
def idf_newer() -> Path:
    return IDF_NEWER


@pytest.fixture
def cwd_trap() -> Path:
    return CWD_TRAP


@pytest.fixture
def idf_git_repo(tmp_path: Path) -> IdfGitRepo:
    """
    Temporary git clone of the dummy IDF with older then newer commits.
    """
    return _init_idf_git_repo(tmp_path)
