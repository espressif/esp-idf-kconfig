# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
#

# Test to verify stdout and stderr clearly separated in kconfserver output:
# * stdout is line-delimited JSON only
# * everything else goes to stderr
import json
import os
import shutil
import subprocess
import sys
import threading
from typing import List

import pytest

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_TEST_DIR, "..", ".."))


def _child_env():
    env = os.environ.copy()
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _REPO_ROOT + (os.pathsep + prev if prev else "")
    return env


PROTOCOL_VERSIONS = [1, 2, 3]
KCONFIG_PARSER_VERSIONS = [1, 2]


def _popen_kconfserver(sdkconfig_path, extra_args=None):
    """
    Cannot use pexpect here; we need stdout/stderr clearly separated.
    """
    cmd = [
        sys.executable,
        "-u",
        "-m",
        "coverage",
        "run",
        "-m",
        "kconfserver",
        "--env",
        "COMPONENT_KCONFIGS_SOURCE_FILE=",
        "--env",
        "COMPONENT_KCONFIGS_PROJBUILD_SOURCE_FILE=",
        "--env",
        "COMPONENT_KCONFIGS=",
        "--env",
        "COMPONENT_KCONFIGS_PROJBUILD=",
        "--kconfig",
        "Kconfig",
        "--config",
        sdkconfig_path,
    ]
    if extra_args:
        cmd.extend(extra_args)
    env = _child_env()
    env.setdefault("PYTHONUNBUFFERED", "1")
    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0,
        cwd=_TEST_DIR,
        env=env,
    )


def _buffer_stderr(proc: subprocess.Popen, buf_list: List[str]) -> None:
    """
    Read stderr and store it in a "buffer" in order to keep the PIPE buffer
    from getting full.
    """
    stderr = proc.stderr
    assert stderr is not None  # we always use stderr=subprocess.PIPE
    try:
        for line in iter(stderr.readline, ""):
            buf_list.append(line)
    finally:
        stderr.close()


def _line_is_json(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    try:
        json.loads(s)
    except json.JSONDecodeError:
        return False
    return True


@pytest.fixture
def copy_sdkconfig(tmp_path):
    sdkconfig_path = tmp_path / "sdkconfig"
    shutil.copy(os.path.join(_TEST_DIR, "sdkconfig"), sdkconfig_path)
    return str(sdkconfig_path)


@pytest.mark.parametrize(
    "parser_version", KCONFIG_PARSER_VERSIONS, ids=[f"parser-v{v}" for v in KCONFIG_PARSER_VERSIONS]
)
@pytest.mark.parametrize("protocol_version", PROTOCOL_VERSIONS, ids=[f"protocol-v{v}" for v in PROTOCOL_VERSIONS])
def test_stdout_is_line_delimited_json(copy_sdkconfig, parser_version, protocol_version, monkeypatch):
    """
    Everything on stdout must be JSON lines; status and diagnostics use stderr
    so clients can parse stdout without filtering.
    """
    monkeypatch.setenv("KCONFIG_PARSER_VERSION", str(parser_version))
    sdkconfig_path = copy_sdkconfig
    stderr_lines: list = []
    proc = _popen_kconfserver(sdkconfig_path)
    t = threading.Thread(target=_buffer_stderr, args=(proc, stderr_lines), daemon=True)
    t.start()
    try:
        assert _line_is_json(proc.stdout.readline()), "initial response: stdout line is not JSON"
        proc.stdin.write(json.dumps({"version": protocol_version, "load": None}) + "\n")
        proc.stdin.flush()
        assert _line_is_json(proc.stdout.readline()), "after load: stdout line is not JSON"
        proc.stdin.write(json.dumps({"version": protocol_version, "save": sdkconfig_path}) + "\n")
        proc.stdin.flush()
        assert _line_is_json(proc.stdout.readline()), "after save: stdout line is not JSON"
    finally:
        proc.stdin.close()
        remaining = proc.stdout.read()
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        t.join(timeout=10)

    for raw_line in remaining.splitlines():
        if raw_line.strip():
            assert _line_is_json(raw_line), f"trailing stdout is not JSON: {raw_line!r}"

    stderr_text = "".join(stderr_lines)
    assert "Server running" in stderr_text
    assert "Saving config" in stderr_text


def test_cli_protocol_version_warning_on_stderr(copy_sdkconfig, monkeypatch):
    """
    ``--version`` above ``MAX_PROTOCOL_VERSION`` prints a stderr warning (unsupported protocol),
    but stdout must still start with a JSON line.
    """
    monkeypatch.setenv("KCONFIG_PARSER_VERSION", str(KCONFIG_PARSER_VERSIONS[0]))
    sdkconfig_path = copy_sdkconfig
    stderr_lines: list = []
    proc = _popen_kconfserver(sdkconfig_path, extra_args=["--version", "99"])
    t = threading.Thread(target=_buffer_stderr, args=(proc, stderr_lines), daemon=True)
    t.start()
    try:
        assert _line_is_json(proc.stdout.readline()), "initial response must still be JSON on stdout"
    finally:
        proc.stdin.close()
        proc.stdout.read()
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        t.join(timeout=10)

    stderr_text = "".join(stderr_lines)
    assert "newer than maximum" in stderr_text
