# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
End-to-end comparison on a dummy two-commit ESP-IDF git tree.
"""

from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import pytest

from kcompare.pipeline import run_repo_compare


def test_run_repo_compare_on_dummy_idf(idf_git_repo: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    git-init older→newer fixture commits, then run the full pipeline.

    ``prepare_checkout`` (install/export) is stubbed: the dummy tree has no
    real ESP-IDF toolchains, and kcompare only needs the worktree + Kconfig
    discovery path for this structural comparison.
    """

    def _fake_prepare_checkout(
        idf_path: str,
        skip_install: bool = False,
        quiet: bool = False,
        base_env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        return dict(base_env or {})

    monkeypatch.setattr("kcompare.pipeline.prepare_checkout", _fake_prepare_checkout)
    monkeypatch.delenv("srctree", raising=False)

    report = run_repo_compare(
        repo=str(idf_git_repo.path),
        commit1=idf_git_repo.newer_sha,
        commit2=idf_git_repo.older_sha,
        target="esp32",
        skip_install=True,
    )

    # Single-target runs use the uniform multi-target shape (one report).
    assert report.older_sha == idf_git_repo.older_sha
    assert report.newer_sha == idf_git_repo.newer_sha
    assert report.targets_compared == ["esp32"]
    assert report.targets_skipped == []

    (sub,) = report.reports
    assert sub.target == "esp32"
    assert sub.added == ["ADDED"]
    assert sub.removed == []
    assert len(sub.renamed) == 1
    assert sub.renamed[0].old_name == "GONE"
    assert sub.renamed[0].new_name == "GONE_NEW"
    assert any(c.id == "FOO" and c.kind == "symbol" for c in sub.defaults_changed)
    assert any(c.id == "MYCHOICE" and c.kind == "choice" for c in sub.defaults_changed)
    assert any(c.id == "IDF_EXPERIMENTAL_FEATURES" for c in sub.defaults_changed)


def test_run_repo_compare_all_targets_intersects_and_notes_exclusive_targets(
    idf_git_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    eim install/environment capture and idf.py --list-targets are stubbed: the
    dummy tree has no real ESP-IDF tools. ``esp32c3`` is only "supported" by the
    newer commit and must be reported as a skipped note, not compared.
    """

    def _fake_prepare_checkout(
        idf_path: str,
        skip_install: bool = False,
        quiet: bool = False,
        base_env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        return dict(base_env or {})

    def _fake_list_targets(worktree_path: str, quiet: bool = False) -> List[str]:
        # Distinguish older vs. newer worktree by its path suffix (sha prefix).
        if worktree_path.endswith(idf_git_repo.older_sha[:12]):
            return ["esp32"]
        return ["esp32", "esp32c3"]

    monkeypatch.setattr("kcompare.pipeline.prepare_checkout", _fake_prepare_checkout)
    monkeypatch.setattr("kcompare.pipeline.list_targets", _fake_list_targets)
    monkeypatch.delenv("srctree", raising=False)

    report = run_repo_compare(
        repo=str(idf_git_repo.path),
        commit1=idf_git_repo.newer_sha,
        commit2=idf_git_repo.older_sha,
        skip_install=True,
    )

    assert report.older_sha == idf_git_repo.older_sha
    assert report.newer_sha == idf_git_repo.newer_sha
    assert [r.target for r in report.reports] == ["esp32"]
    assert report.targets_compared == ["esp32"]

    # Structured, machine-readable skip info.
    (skipped,) = report.targets_skipped
    assert skipped.target == "esp32c3"
    assert skipped.present_in == idf_git_repo.newer_sha
    assert skipped.missing_from == idf_git_repo.older_sha

    (esp32_report,) = report.reports
    assert esp32_report.added == ["ADDED"]
