# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Tests for CODEOWNERS loading, including history and master fallbacks.
"""

import os
import subprocess
from pathlib import Path
from typing import Dict
from typing import Optional

import pytest

from kcompare.errors import SnapshotError
from kcompare.pipeline import _CODEOWNERS_MIN_COMPONENT_RULES
from kcompare.pipeline import _load_codeowners

_EMPTY_CODEOWNERS = """\
# catch-all only (as on v6.0 / v6.1-beta1)
* @esp-idf-codeowners/all-maintainers
"""

# One leftover /components rule after the backport trim (as on v6.0.1 / v6.0.2).
_SPARSE_CODEOWNERS = """\
* @esp-idf-codeowners/all-maintainers

/components/esp_blockdev_util/        @esp-idf-codeowners/storage
"""


def _detailed_codeowners(n_rules: int = _CODEOWNERS_MIN_COMPONENT_RULES) -> str:
    """
    Build a CODEOWNERS file with at least *n_rules* ``/components`` lines.
    """
    lines = [
        "* @esp-idf-codeowners/other",
        "",
        "/components/app_trace/    @esp-idf-codeowners/debugging",
        "/components/console/      @esp-idf-codeowners/system",
    ]
    # Pad so the parsed /components rule count meets the usability threshold.
    for i in range(max(0, n_rules - 2)):
        lines.append(f"/components/filler{i}/    @esp-idf-codeowners/filler")
    return "\n".join(lines) + "\n"


_DETAILED_CODEOWNERS = _detailed_codeowners()


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


def _init_repo_with_master_codeowners(tmp_path: Path, master_text: str) -> Path:
    """
    Create a repo whose ``master`` branch has *master_text* as ``.gitlab/CODEOWNERS``.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "master")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    gitlab = repo / ".gitlab"
    gitlab.mkdir()
    (gitlab / "CODEOWNERS").write_text(master_text, encoding="utf-8")
    (repo / "README").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "master with CODEOWNERS")
    return repo


def _commit_codeowners(repo: Path, text: str, message: str) -> str:
    """
    Write CODEOWNERS, commit, and return the new HEAD SHA.
    """
    path = repo / ".gitlab" / "CODEOWNERS"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _fake_worktree(tmp_path: Path, text: str) -> Path:
    newer = tmp_path / "newer_wt"
    (newer / ".gitlab").mkdir(parents=True)
    (newer / ".gitlab" / "CODEOWNERS").write_text(text, encoding="utf-8")
    return newer


def test_load_codeowners_uses_newer_when_it_has_enough_components_rules(tmp_path: Path) -> None:
    repo = _init_repo_with_master_codeowners(tmp_path, _EMPTY_CODEOWNERS)
    newer_sha = _git(repo, "rev-parse", "HEAD")
    newer = _fake_worktree(tmp_path, _DETAILED_CODEOWNERS)

    index = _load_codeowners(str(repo), str(newer), newer_sha)
    assert index.component_rule_count >= _CODEOWNERS_MIN_COMPONENT_RULES
    assert index.groups_for_path("components/app_trace/Kconfig") == ("debugging",)


def test_load_codeowners_uses_recent_history_when_newer_is_trimmed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # master stays empty so a mistaken master fallback would fail the assertions.
    repo = _init_repo_with_master_codeowners(tmp_path, _EMPTY_CODEOWNERS)
    full_sha = _commit_codeowners(repo, _DETAILED_CODEOWNERS, "full CODEOWNERS")
    tip_sha = _commit_codeowners(repo, _EMPTY_CODEOWNERS, "trim CODEOWNERS for backports")
    newer = _fake_worktree(tmp_path, _EMPTY_CODEOWNERS)

    index = _load_codeowners(str(repo), str(newer), tip_sha)
    assert index.component_rule_count >= _CODEOWNERS_MIN_COMPONENT_RULES
    assert index.groups_for_path("components/console/Kconfig") == ("system",)

    captured = capsys.readouterr()
    combined = " ".join((captured.err + captured.out).split())
    assert "searching the last" in combined
    assert f"using CODEOWNERS from commit {full_sha[:12]}" in combined
    assert "falling back to CODEOWNERS from master" not in combined


def test_load_codeowners_history_recovers_from_sparse_tip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A tip with a few leftover ``/components`` rules (below the threshold) must
    still walk history — matching v6.0.1 / v6.0.2 after the backport trim.
    """
    repo = _init_repo_with_master_codeowners(tmp_path, _EMPTY_CODEOWNERS)
    full_sha = _commit_codeowners(repo, _DETAILED_CODEOWNERS, "full CODEOWNERS")
    _commit_codeowners(repo, _EMPTY_CODEOWNERS, "trim CODEOWNERS for backports")
    tip_sha = _commit_codeowners(repo, _SPARSE_CODEOWNERS, "add one component rule")
    newer = _fake_worktree(tmp_path, _SPARSE_CODEOWNERS)

    index = _load_codeowners(str(repo), str(newer), tip_sha)
    assert index.component_rule_count >= _CODEOWNERS_MIN_COMPONENT_RULES
    assert index.groups_for_path("components/app_trace/Kconfig") == ("debugging",)

    captured = capsys.readouterr()
    combined = " ".join((captured.err + captured.out).split())
    assert f"using CODEOWNERS from commit {full_sha[:12]}" in combined


def test_load_codeowners_falls_back_to_master_when_history_has_no_usable_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Release tip history only ever had a trimmed CODEOWNERS; master (not on
    # that history) holds the usable file used as the last-resort fallback.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "master")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base without CODEOWNERS")

    _git(repo, "checkout", "-b", "release")
    tip_sha = _commit_codeowners(repo, _EMPTY_CODEOWNERS, "trimmed CODEOWNERS")

    _git(repo, "checkout", "master")
    _commit_codeowners(repo, _DETAILED_CODEOWNERS, "master full CODEOWNERS")
    _git(repo, "checkout", "release")

    newer = _fake_worktree(tmp_path, _EMPTY_CODEOWNERS)
    index = _load_codeowners(str(repo), str(newer), tip_sha)
    assert index.component_rule_count >= _CODEOWNERS_MIN_COMPONENT_RULES
    assert index.groups_for_path("components/console/Kconfig") == ("system",)

    captured = capsys.readouterr()
    combined = " ".join((captured.err + captured.out).split())
    assert "falling back to CODEOWNERS from master" in combined


def test_load_codeowners_dies_when_master_also_below_threshold(tmp_path: Path) -> None:
    repo = _init_repo_with_master_codeowners(tmp_path, _EMPTY_CODEOWNERS)
    tip_sha = _git(repo, "rev-parse", "HEAD")
    newer = _fake_worktree(tmp_path, _EMPTY_CODEOWNERS)

    with pytest.raises(SnapshotError, match="master also has fewer than"):
        _load_codeowners(str(repo), str(newer), tip_sha)


def test_load_codeowners_dies_when_newer_file_missing(tmp_path: Path) -> None:
    repo = _init_repo_with_master_codeowners(tmp_path, _DETAILED_CODEOWNERS)
    tip_sha = _git(repo, "rev-parse", "HEAD")
    newer = tmp_path / "newer_wt"
    newer.mkdir()

    with pytest.raises(SnapshotError, match="CODEOWNERS not found"):
        _load_codeowners(str(repo), str(newer), tip_sha)
