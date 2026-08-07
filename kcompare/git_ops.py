# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Git helpers: commit ordering and detached worktrees for ESP-IDF checkouts.
"""

import os
import re
import shutil
import subprocess
from typing import List
from typing import Optional
from typing import Tuple

from esp_pylib.logger import log
from rich.markup import escape

from .errors import GitError

_IDF_VERSION_HEADER = "components/esp_common/include/esp_idf_version.h"
_IDF_VERSION_MACRO_RE = re.compile(r"#define\s+ESP_IDF_VERSION_{}\s+(\d+)")


def _run_git(repo: str, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """
    Run a ``git -C <repo>`` command.  Raises ``GitError`` on non-zero exit
    when ``check`` is True.
    """
    cmd = ["git", "-C", repo] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed"
        raise GitError(msg)
    return result


def resolve_sha(repo: str, ref: str) -> str:
    """
    Resolve a ref to a full commit SHA.
    """
    result = _run_git(repo, ["rev-parse", "--verify", f"{ref}^{{commit}}"])
    return str(result.stdout.strip())


def show_file_at_ref(repo: str, ref: str, path: str) -> str:
    """
    Return the contents of *path* as it exists at git *ref* (``git show``).
    """
    result = _run_git(repo, ["show", f"{ref}:{path}"])
    return str(result.stdout)


def log_commits_touching_path(repo: str, ref: str, path: str, max_count: int) -> List[str]:
    """
    Return up to *max_count* commit SHAs (newest first) that modified *path*
    and are reachable from *ref*.
    """
    result = _run_git(
        repo,
        ["log", ref, "-n", str(max_count), "--format=%H", "--", path],
    )
    text = str(result.stdout).strip()
    if not text:
        return []
    return text.splitlines()


def _is_ancestor(repo: str, maybe_ancestor: str, maybe_descendant: str) -> bool:
    """
    True when ``maybe_ancestor`` is a git ancestor of ``maybe_descendant``.
    """
    result = _run_git(
        repo,
        ["merge-base", "--is-ancestor", maybe_ancestor, maybe_descendant],
        check=False,
    )
    return result.returncode == 0


def _idf_version(repo: str, sha: str) -> Optional[Tuple[int, int, int]]:
    """
    Return the (MAJOR, MINOR, PATCH) ESP-IDF version at ``sha``, read from
    ``components/esp_common/include/esp_idf_version.h``, or None if the file
    or its version macros cannot be found.
    """
    try:
        text = show_file_at_ref(repo, sha, _IDF_VERSION_HEADER)
    except GitError:
        return None
    parts: List[int] = []
    for part in ("MAJOR", "MINOR", "PATCH"):
        match = re.search(_IDF_VERSION_MACRO_RE.pattern.format(part), text)
        if not match:
            return None
        parts.append(int(match.group(1)))
    return parts[0], parts[1], parts[2]


def order_commits(repo: str, commit1: str, commit2: str) -> Tuple[str, str, str, str]:
    """
    Decide older vs newer.

    Returns (older_ref, older_sha, newer_ref, newer_sha) where refs are the
    original CLI strings.

    Rules:
      1. Ancestor relation via merge-base --is-ancestor: unambiguous when true.
      2. Else compare ESP-IDF version numbers (esp_idf_version.h). This is
         needed for diverged release/backport branches (e.g. release/6.0 vs
         v6.1-beta1) where commit timestamps do not reflect functional order:
         a backport branch keeps getting fresh commits while staying
         featurewise behind the branch it was forked from.
      3. Else assume the CLI argument order (commit1 = older, commit2 = newer).
    """
    sha1 = resolve_sha(repo, commit1)
    sha2 = resolve_sha(repo, commit2)
    if sha1 == sha2:
        raise GitError(f"both refs resolve to the same commit {sha1}")

    if _is_ancestor(repo, sha1, sha2):
        return commit1, sha1, commit2, sha2
    if _is_ancestor(repo, sha2, sha1):
        return commit2, sha2, commit1, sha1

    v1 = _idf_version(repo, sha1)
    v2 = _idf_version(repo, sha2)
    if v1 is not None and v2 is not None and v1 != v2:
        if v1 < v2:
            return commit1, sha1, commit2, sha2
        return commit2, sha2, commit1, sha1

    log.warn(
        f"cannot determine older/newer between {escape(commit1)} ({sha1[:12]}) and "
        f"{escape(commit2)} ({sha2[:12]}) via ancestry or ESP-IDF version; "
        "assuming CLI argument order (first commit = older, second = newer)"
    )
    return commit1, sha1, commit2, sha2


def add_worktree(repo: str, sha: str, path: str) -> str:
    """
    Create a detached worktree at ``path`` for ``sha``. Returns ``path``.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.exists(path):
        remove_worktree(repo, path, force=True)
    _run_git(repo, ["worktree", "add", "--detach", path, sha])
    return path


def remove_worktree(repo: str, path: str, force: bool = False) -> None:
    """
    Remove a worktree path if it exists.
    """
    if not os.path.exists(path):
        return
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(path)
    result = _run_git(repo, args, check=False)
    if result.returncode != 0 and os.path.exists(path):
        # Fall back to plain delete + prune if git refuses (e.g. dirty worktree).
        shutil.rmtree(path, ignore_errors=True)
        _run_git(repo, ["worktree", "prune"], check=False)


def worktree_base(repo: str) -> str:
    """
    Directory under the IDF repo used for kcompare worktrees.
    """
    return os.path.join(repo, ".kcompare", "worktrees")


def worktree_path_for_sha(repo: str, sha: str) -> str:
    """
    Deterministic worktree directory path for the first 12 chars of ``sha``.
    """
    return os.path.join(worktree_base(repo), sha[:12])


def staging_dir(repo: str, sha: str) -> str:
    """
    Directory for generated kconfigs.in / rename lists for one checkout.
    """
    path = os.path.join(repo, ".kcompare", "staging", sha[:12])
    os.makedirs(path, exist_ok=True)
    return path
