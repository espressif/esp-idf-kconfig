# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Prepare ESP-IDF checkouts through the ESP-IDF Installation Manager (eim).

Replaces the legacy install.sh / export.sh flow:

* ``eim install -p <path>`` sets up the toolchain for an existing checkout
  without overwriting the tree.
* ``eim run <command> <path>`` sources that checkout's activation script and
  runs a command inside the resulting environment.

See https://docs.espressif.com/projects/idf-im-ui/en/latest/ for details.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Dict
from typing import List
from typing import Optional

from esp_pylib.logger import log
from rich.markup import escape

from .errors import IdfEnvError

EIM_DOCS_URL = "https://docs.espressif.com/projects/idf-im-ui/en/latest/"


def _require_eim() -> str:
    """
    Return the path to the ``eim`` executable, or fail with an install hint.
    """
    eim = shutil.which("eim")
    if eim is None:
        log.hint(f"install the ESP-IDF Installation Manager (eim): {EIM_DOCS_URL}")
        raise IdfEnvError("eim CLI not found on PATH")
    return eim


def _run_eim(cmd: List[str], quiet: bool, error_msg: str) -> subprocess.CompletedProcess:
    """
    Run an ``eim`` command, routing its output to stderr so machine-readable
    stdout stays clean. When *quiet* is True, output is captured and only
    replayed on failure.
    """
    if quiet:
        result = subprocess.run(cmd, capture_output=True, text=True)
    else:
        result = subprocess.run(cmd, stdout=sys.stderr, stderr=sys.stderr, text=True)
    if result.returncode != 0:
        if quiet:
            sys.stderr.write(result.stdout)
            sys.stderr.write(result.stderr)
        raise IdfEnvError(f"{error_msg} (exit code {result.returncode})")
    return result


def install_idf(idf_path: str, quiet: bool = False) -> None:
    """
    Set up ESP-IDF tools for the existing checkout via ``eim install -p``.

    EIM detects the existing git checkout at *idf_path* and installs the
    toolchain for the version found there without overwriting the tree.
    """
    eim = _require_eim()
    log.print(
        f"Installing ESP-IDF tools for {escape(idf_path)} via eim (this can take several minutes)...",
        file=sys.stderr,
        markup=False,
    )
    cmd = [eim, "--do-not-track", "true", "install", "-p", idf_path, "--non-interactive", "true"]
    _run_eim(cmd, quiet=quiet, error_msg=f"eim install failed for {idf_path}")


def export_idf_environ(idf_path: str, quiet: bool = False) -> Dict[str, str]:
    """
    Capture the activated ESP-IDF environment for *idf_path* via ``eim run``.

    ``eim run`` sources the checkout's activation script and then runs a small
    Python snippet that dumps ``os.environ`` into a temporary JSON file. Using
    a file (rather than stdout) keeps any banners printed by eim or the
    activation script from corrupting the result.

    When *quiet* is True, command output is suppressed (captured and only
    shown on failure).
    """
    eim = _require_eim()
    log.print(
        f"Capturing ESP-IDF environment from {escape(idf_path)} via eim run...",
        file=sys.stderr,
        markup=False,
    )

    fd, env_json_path = tempfile.mkstemp(suffix=".json", prefix="kcompare_env_")
    os.close(fd)
    try:
        snippet = 'import json,os,sys; open(sys.argv[1],"w").write(json.dumps(dict(os.environ)))'
        command = f"python -c {shlex.quote(snippet)} {shlex.quote(env_json_path)}"
        cmd = [eim, "--do-not-track", "true", "run", command, idf_path]
        _run_eim(cmd, quiet=quiet, error_msg=f"eim run (environment capture) failed for {idf_path}")

        try:
            with open(env_json_path, encoding="utf-8") as f:
                env: Dict[str, str] = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise IdfEnvError(f"failed to read environment JSON from eim run: {exc}") from exc
    finally:
        os.unlink(env_json_path)

    return env


def list_targets(idf_path: str, quiet: bool = False) -> List[str]:
    """
    Run ``idf.py --list-targets`` inside the checkout's eim environment and
    return the list of chip targets supported by this checkout.

    The command's output is redirected to a temporary file so that banners
    from eim or the activation script do not mix into the target list.
    """
    eim = _require_eim()

    fd, out_path = tempfile.mkstemp(suffix=".txt", prefix="kcompare_targets_")
    os.close(fd)
    try:
        command = f"idf.py --list-targets > {shlex.quote(out_path)}"
        cmd = [eim, "--do-not-track", "true", "run", command, idf_path]
        _run_eim(cmd, quiet=quiet, error_msg=f"eim run (idf.py --list-targets) failed for {idf_path}")

        try:
            with open(out_path, encoding="utf-8") as f:
                content = f.read()
        except OSError as exc:
            raise IdfEnvError(f"failed to read targets from eim run: {exc}") from exc
    finally:
        os.unlink(out_path)

    targets = [line.strip() for line in content.splitlines() if line.strip()]
    if not targets:
        raise IdfEnvError(f"idf.py --list-targets returned no targets for {idf_path}")
    return targets


def prepare_checkout(
    idf_path: str,
    skip_install: bool = False,
    quiet: bool = False,
    base_env: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Install (unless skipped) via eim and capture the environment; return the
    merged environment dict.
    """
    if not skip_install:
        install_idf(idf_path, quiet=quiet)
    exported_env = export_idf_environ(idf_path, quiet=quiet)
    merged_env = dict(base_env or os.environ)
    merged_env.update(exported_env)
    return merged_env
