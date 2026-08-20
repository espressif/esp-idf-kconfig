# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import subprocess
from pathlib import Path
from typing import Dict
from typing import Optional

import pytest

from kcompare.git_ops import GitError
from kcompare.git_ops import order_commits
from kcompare.git_ops import resolve_sha


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


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "first")
    return repo


def test_order_by_ancestry(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    sha1 = resolve_sha(str(repo), "HEAD")
    (repo / "README").write_text("b\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "second")
    sha2 = resolve_sha(str(repo), "HEAD")

    _older_ref, older_sha, _newer_ref, newer_sha = order_commits(str(repo), sha2, sha1)
    assert older_sha == sha1
    assert newer_sha == sha2


def test_order_same_commit_errors(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    sha = resolve_sha(str(repo), "HEAD")
    with pytest.raises(GitError, match="same commit"):
        order_commits(str(repo), sha, sha)


def _diverge(repo: Path, branch: str, filename: str, content: str, committer_date: str) -> str:
    """
    Create *branch* off the repo's current HEAD, add *filename*, and return
    the resulting commit SHA. *committer_date* only exercises that timestamps
    are ignored for diverged branches; it must not affect the outcome.
    """
    base = resolve_sha(str(repo), "HEAD")
    _git(repo, "checkout", "-b", branch)
    (repo / filename).write_text(content, encoding="utf-8")
    _git(repo, "add", filename)
    _git(
        repo,
        "commit",
        "-m",
        branch,
        env={
            "GIT_AUTHOR_DATE": committer_date,
            "GIT_COMMITTER_DATE": committer_date,
        },
    )
    sha = resolve_sha(str(repo), "HEAD")
    _git(repo, "checkout", base)
    return sha


def test_order_falls_back_to_cli_position_on_diverged_branches(tmp_path: Path) -> None:
    # No esp_idf_version.h on either branch, so ancestry and version both fail
    # to decide; order_commits must fall back to CLI argument order rather
    # than the (unreliable) committer date.
    repo = _init_repo(tmp_path)
    sha_a = _diverge(repo, "branch-a", "A", "a\n", "2021-01-01T00:00:00")
    sha_b = _diverge(repo, "branch-b", "B", "b\n", "2020-01-01T00:00:00")

    _older_ref, older_sha, _newer_ref, newer_sha = order_commits(str(repo), sha_a, sha_b)
    assert older_sha == sha_a
    assert newer_sha == sha_b

    _older_ref, older_sha, _newer_ref, newer_sha = order_commits(str(repo), sha_b, sha_a)
    assert older_sha == sha_b
    assert newer_sha == sha_a


def _version_header(major: int, minor: int, patch: int) -> str:
    return (
        f"#define ESP_IDF_VERSION_MAJOR {major}\n"
        f"#define ESP_IDF_VERSION_MINOR {minor}\n"
        f"#define ESP_IDF_VERSION_PATCH {patch}\n"
    )


def test_order_by_idf_version_on_diverged_backport_branch(tmp_path: Path) -> None:
    # Mirrors release/6.0 (backport branch, committed later) vs v6.1-beta1
    # (committed earlier, but functionally newer): version numbers must win
    # over committer date and ancestry (there is none, since they diverged).
    repo = _init_repo(tmp_path)
    version_dir = repo / "components" / "esp_common" / "include"
    version_dir.mkdir(parents=True)
    (version_dir / "esp_idf_version.h").write_text(_version_header(5, 9, 0), encoding="utf-8")
    _git(repo, "add", "components")
    _git(repo, "commit", "-m", "add version header")

    sha_backport = _diverge(
        repo,
        "release-6.0",
        "components/esp_common/include/esp_idf_version.h",
        _version_header(6, 0, 0),
        "2024-06-01T00:00:00",
    )
    sha_beta = _diverge(
        repo,
        "v6.1-beta1",
        "components/esp_common/include/esp_idf_version.h",
        _version_header(6, 1, 0),
        "2024-01-01T00:00:00",
    )

    _older_ref, older_sha, _newer_ref, newer_sha = order_commits(str(repo), sha_backport, sha_beta)
    assert older_sha == sha_backport
    assert newer_sha == sha_beta
