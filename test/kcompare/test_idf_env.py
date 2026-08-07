# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Tests for kcompare.idf_env's eim-based install / environment capture / target listing.
"""

import json
import subprocess
from pathlib import Path
from typing import Any
from typing import List

import pytest

from kcompare import idf_env
from kcompare.errors import IdfEnvError
from kcompare.idf_env import export_idf_environ
from kcompare.idf_env import install_idf
from kcompare.idf_env import list_targets


def _fake_completed_process(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def eim_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Pretend the ``eim`` binary is available on PATH.
    """
    monkeypatch.setattr(idf_env.shutil, "which", lambda name: "/usr/bin/eim")


def test_missing_eim_raises_with_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(idf_env.shutil, "which", lambda name: None)
    hints: List[str] = []
    monkeypatch.setattr(idf_env.log, "hint", lambda *args: hints.append(" ".join(str(a) for a in args)))

    with pytest.raises(IdfEnvError, match="eim CLI not found"):
        install_idf("/some/idf", quiet=True)

    assert any("eim" in h and "docs.espressif.com" in h for h in hints)


def test_install_idf_invokes_eim_install(eim_on_path: None, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[List[str]] = []

    def _fake_run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
        calls.append(cmd)
        return _fake_completed_process(0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    install_idf("/work/tree", quiet=True)

    (cmd,) = calls
    assert cmd[0] == "/usr/bin/eim"
    assert "install" in cmd
    assert "-p" in cmd and "/work/tree" in cmd


def test_install_idf_raises_on_failure(eim_on_path: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed_process(1, stderr="boom"))

    with pytest.raises(IdfEnvError, match="eim install failed"):
        install_idf("/work/tree", quiet=True)


def test_export_idf_environ_reads_dumped_json(eim_on_path: None, monkeypatch: pytest.MonkeyPatch) -> None:
    captured_env = {"IDF_PATH": "/work/tree", "PATH": "/tools/bin:/usr/bin"}

    def _fake_run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
        # The command is 'eim ... run "python -c ... <json_path>" <idf_path>'.
        # Emulate eim run by writing the env JSON to the path baked into the command.
        run_command = cmd[cmd.index("run") + 1]
        json_path = run_command.split()[-1].strip("'\"")
        Path(json_path).write_text(json.dumps(captured_env))
        return _fake_completed_process(0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    env = export_idf_environ("/work/tree", quiet=True)
    assert env == captured_env


def test_export_idf_environ_raises_on_failure(eim_on_path: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed_process(1, stderr="nope"))

    with pytest.raises(IdfEnvError, match="environment capture"):
        export_idf_environ("/work/tree", quiet=True)


def test_list_targets_parses_redirected_output(eim_on_path: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
        run_command = cmd[cmd.index("run") + 1]
        out_path = run_command.split(">", 1)[1].strip().strip("'\"")
        Path(out_path).write_text("esp32\nesp32s2\nesp32c3\n")
        return _fake_completed_process(0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    targets = list_targets("/work/tree", quiet=True)
    assert targets == ["esp32", "esp32s2", "esp32c3"]


def test_list_targets_raises_on_failure(eim_on_path: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed_process(1, stderr="boom"))

    with pytest.raises(IdfEnvError, match="list-targets"):
        list_targets("/work/tree", quiet=True)


def test_list_targets_raises_on_empty_output(eim_on_path: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
        run_command = cmd[cmd.index("run") + 1]
        out_path = run_command.split(">", 1)[1].strip().strip("'\"")
        Path(out_path).write_text("\n")
        return _fake_completed_process(0)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(IdfEnvError, match="no targets"):
        list_targets("/work/tree", quiet=True)
