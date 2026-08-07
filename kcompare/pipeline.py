# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
End-to-end comparison pipeline.
"""

import os
import sys
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from esp_pylib.logger import log
from rich.markup import escape

from .codeowners import CodeownersIndex
from .codeowners import parse_codeowners
from .codeowners import parse_codeowners_text
from .diff import compare_snapshots
from .discover import prepare_kconfig_env
from .errors import GitError
from .errors import SnapshotError
from .git_ops import add_worktree
from .git_ops import log_commits_touching_path
from .git_ops import order_commits
from .git_ops import remove_worktree
from .git_ops import show_file_at_ref
from .git_ops import staging_dir
from .git_ops import worktree_path_for_sha
from .idf_env import list_targets
from .idf_env import prepare_checkout
from .models import ConfigurationSnapshot
from .models import DiffReport
from .models import MultiTargetDiffReport
from .models import SkippedTarget
from .snapshot import build_snapshot


def _prepare_worktree(
    repo: str,
    commit_ref: str,
    commit_sha: str,
    skip_install: bool,
    quiet: bool = False,
) -> Tuple[str, Dict[str, str]]:
    """
    Create a worktree for *commit_sha*, set it up with eim, and return
    ``(worktree_path, exported_env)``.
    """
    worktree_path = worktree_path_for_sha(repo, commit_sha)
    add_worktree(repo, commit_sha, worktree_path)
    log.print(
        f"Preparing checkout {escape(commit_ref)} ({commit_sha[:12]}) — eim install can take several minutes...",
        file=sys.stderr,
        markup=False,
    )
    exported = prepare_checkout(worktree_path, skip_install=skip_install, quiet=quiet)
    return worktree_path, exported


# Release / backport branches often replace the detailed CODEOWNERS file with a
# catch-all stub (sometimes plus a later one-off rule). Treat anything below
# this many parsed ``/components`` rules as unusable for --by-codeowner.
_CODEOWNERS_MIN_COMPONENT_RULES = 10
# How many recent commits that touched CODEOWNERS to search for a full file
# before falling back to master.
_CODEOWNERS_HISTORY_DEPTH = 3
_CODEOWNERS_RELPATH = ".gitlab/CODEOWNERS"


def _load_codeowners(repo: str, worktree_path: str, newer_sha: str) -> CodeownersIndex:
    """
    Parse ``.gitlab/CODEOWNERS`` from *worktree_path* (the newer checkout).

    When that file has fewer than ``_CODEOWNERS_MIN_COMPONENT_RULES`` parsed
    ``/components`` rules (as on release tags after the backport trim, e.g.
    ``v6.0`` / ``v6.1-beta1``), search the last ``_CODEOWNERS_HISTORY_DEPTH``
    commits reachable from *newer_sha* that modified the file and use the
    newest revision that clears the threshold. If none does, fall back to
    ``master:.gitlab/CODEOWNERS`` in *repo*.

    Raises ``SnapshotError`` when the file is absent, or when neither recent
    history nor ``master`` yields a usable CODEOWNERS file.
    """
    path = os.path.join(worktree_path, ".gitlab", "CODEOWNERS")
    if not os.path.isfile(path):
        raise SnapshotError(f"CODEOWNERS not found in newer checkout: {path}")
    index = parse_codeowners(path)
    if index.component_rule_count >= _CODEOWNERS_MIN_COMPONENT_RULES:
        return index

    log.warn(
        f"newer checkout's CODEOWNERS has fewer than {_CODEOWNERS_MIN_COMPONENT_RULES} "
        f"/components rules; searching the last {_CODEOWNERS_HISTORY_DEPTH} commits that "
        f"modified {_CODEOWNERS_RELPATH}"
    )
    try:
        history = log_commits_touching_path(repo, newer_sha, _CODEOWNERS_RELPATH, _CODEOWNERS_HISTORY_DEPTH)
    except GitError as exc:
        log.warn(f"could not walk CODEOWNERS history: {escape(str(exc))}")
        history = []

    for sha in history:
        try:
            text = show_file_at_ref(repo, sha, _CODEOWNERS_RELPATH)
        except GitError:
            continue
        candidate = parse_codeowners_text(text)
        if candidate.component_rule_count >= _CODEOWNERS_MIN_COMPONENT_RULES:
            log.warn(f"using CODEOWNERS from commit {sha[:12]}")
            return candidate

    log.warn("no usable CODEOWNERS in recent history; falling back to CODEOWNERS from master")
    try:
        text = show_file_at_ref(repo, "master", _CODEOWNERS_RELPATH)
    except GitError as exc:
        raise SnapshotError(
            f"newer checkout's CODEOWNERS is trimmed and could not load CODEOWNERS from master: {exc}"
        ) from exc
    index = parse_codeowners_text(text)
    if index.component_rule_count < _CODEOWNERS_MIN_COMPONENT_RULES:
        raise SnapshotError(
            f"CODEOWNERS from master also has fewer than {_CODEOWNERS_MIN_COMPONENT_RULES} "
            f"/components rules; cannot split report by codeowner"
        )
    return index


def _snapshot_from_worktree(
    repo: str,
    worktree_path: str,
    commit_ref: str,
    commit_sha: str,
    target: str,
    exported_env: Dict[str, str],
    load_renames: bool,
) -> ConfigurationSnapshot:
    """
    Build a ConfigurationSnapshot from an already-prepared worktree.
    """
    stage = staging_dir(repo, commit_sha)
    env_updates, rename_paths = prepare_kconfig_env(worktree_path, target, stage)
    merged = dict(exported_env)
    merged.update(env_updates)
    return build_snapshot(
        idf_path=worktree_path,
        commit_ref=commit_ref,
        commit_sha=commit_sha,
        target=target,
        env_updates=merged,
        rename_paths=rename_paths,
        load_renames_flag=load_renames,
    )


def _intersect_targets(
    older_wt: str,
    newer_wt: str,
    older_ref: str,
    newer_ref: str,
    quiet: bool,
) -> Tuple[List[str], List[SkippedTarget]]:
    """
    Return chip targets common to both checkouts, plus skip notes for
    targets present on only one side.
    """
    older_targets = set(list_targets(older_wt, quiet=quiet))
    newer_targets = set(list_targets(newer_wt, quiet=quiet))
    common = sorted(older_targets & newer_targets)
    skipped: List[SkippedTarget] = []
    for chip in sorted(older_targets - newer_targets):
        skipped.append(SkippedTarget(target=chip, present_in=older_ref, missing_from=newer_ref))
        log.print(
            f"NOTE: target '{chip}' is present in {older_ref} but not in {newer_ref}; skipping",
            file=sys.stderr,
            markup=False,
        )
    for chip in sorted(newer_targets - older_targets):
        skipped.append(SkippedTarget(target=chip, present_in=newer_ref, missing_from=older_ref))
        log.print(
            f"NOTE: target '{chip}' is present in {newer_ref} but not in {older_ref}; skipping",
            file=sys.stderr,
            markup=False,
        )
    if not common:
        raise SnapshotError(f"no chip target is common to both {older_ref} and {newer_ref}")
    return common, skipped


def run_repo_compare(
    repo: str,
    commit1: str,
    commit2: str,
    target: Optional[str] = None,
    skip_install: bool = False,
    keep_worktrees: bool = False,
    quiet: bool = False,
    by_codeowner: bool = False,
) -> MultiTargetDiffReport:
    """
    Compare two commits in an ESP-IDF repo (full component set).

    When *target* is given, only that chip is compared. When omitted, every
    chip common to both commits (``idf.py --list-targets``) is compared;
    targets present on only one side are recorded in ``targets_skipped``.

    Worktrees are created once per commit and reused for every target.

    Workflow:
    1. Order the commits (older / newer) and create one worktree per commit.
    2. Set up each worktree with eim and capture its environment.
    3. Resolve the target list (requested chip, or the intersection of
       supported chips).
    4. Build a ConfigurationSnapshot and DiffReport per target.
    5. Clean up worktrees (unless ``keep_worktrees``) and return the
       collected per-target reports.
    """
    repo = os.path.abspath(repo)
    if not os.path.exists(os.path.join(repo, ".git")):
        raise SnapshotError(f"not a git repository: {repo}")

    older_ref, older_sha, newer_ref, newer_sha = order_commits(repo, commit1, commit2)
    if target:
        scope = f"for target {escape(target)}"
    else:
        scope = "across all common targets"
    log.print(
        f"Comparing older {escape(older_ref)} ({older_sha[:12]}) → "
        f"newer {escape(newer_ref)} ({newer_sha[:12]}) {scope}",
        file=sys.stderr,
        markup=False,
    )

    older_wt: str = ""
    newer_wt: str = ""
    skipped: List[SkippedTarget] = []
    targets: List[str] = []
    reports: List[DiffReport] = []
    codeowners: Optional[CodeownersIndex] = None
    try:
        older_wt, older_exported = _prepare_worktree(repo, older_ref, older_sha, skip_install, quiet)
        newer_wt, newer_exported = _prepare_worktree(repo, newer_ref, newer_sha, skip_install, quiet)

        if target:
            targets = [target]
        else:
            targets, skipped = _intersect_targets(older_wt, newer_wt, older_ref, newer_ref, quiet)

        for chip in targets:
            if not target:
                log.print(f"Comparing target '{escape(chip)}'...", file=sys.stderr, markup=False)
            older_snap = _snapshot_from_worktree(
                repo, older_wt, older_ref, older_sha, chip, older_exported, load_renames=False
            )
            newer_snap = _snapshot_from_worktree(
                repo, newer_wt, newer_ref, newer_sha, chip, newer_exported, load_renames=True
            )
            reports.append(compare_snapshots(older_snap, newer_snap))

        if by_codeowner:
            codeowners = _load_codeowners(repo, newer_wt, newer_sha)
    finally:
        if not keep_worktrees:
            if older_wt:
                remove_worktree(repo, older_wt, force=True)
            if newer_wt:
                remove_worktree(repo, newer_wt, force=True)

    return MultiTargetDiffReport(
        older_commit=older_ref,
        older_sha=older_sha,
        newer_commit=newer_ref,
        newer_sha=newer_sha,
        targets_compared=targets,
        targets_skipped=skipped,
        reports=reports,
        codeowners=codeowners,
    )
