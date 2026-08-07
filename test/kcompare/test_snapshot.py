# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from typing import Dict
from typing import List
from typing import Tuple

import pytest

from kcompare.diff import compare_snapshots
from kcompare.discover import prepare_kconfig_env
from kcompare.snapshot import build_snapshot


def _env_for(idf: Path, staging: Path, target: str = "esp32") -> Tuple[Dict[str, str], List[str]]:
    return prepare_kconfig_env(str(idf), target, str(staging))


def test_snapshot_defaults_select_choice(idf_older: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, _ = _env_for(idf_older, tmp_path / "staging")
    monkeypatch.delenv("srctree", raising=False)
    snap = build_snapshot(
        idf_path=str(idf_older),
        commit_ref="older",
        commit_sha="a" * 40,
        target="esp32",
        env_updates=env,
    )

    assert "OPT_A" not in snap.symbols
    assert "OPT_B" not in snap.symbols
    assert "SRC" in snap.symbols
    assert "TGT" in snap.symbols
    assert snap.symbols["VAL"].defaults == ("1 if SRC", "2")
    assert "MYCHOICE" in snap.choices
    assert snap.choices["MYCHOICE"].default_symbol_names == ("OPT_A",)
    assert snap.choices["MYCHOICE"].options == ("OPT_A", "OPT_B")


def test_snapshot_captures_symbol_and_choice_locations(
    idf_older: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env, _ = _env_for(idf_older, tmp_path / "staging")
    monkeypatch.delenv("srctree", raising=False)
    snap = build_snapshot(
        idf_path=str(idf_older),
        commit_ref="older",
        commit_sha="a" * 40,
        target="esp32",
        env_updates=env,
    )

    assert snap.symbols["SRC"].locations == ("components/foo/Kconfig:1",)
    # The named choice keeps its definition location.
    assert snap.choices["MYCHOICE"].locations == ("components/foo/Kconfig:27",)


def test_snapshot_includes_renames(idf_newer: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, rename_paths = _env_for(idf_newer, tmp_path / "staging")
    monkeypatch.delenv("srctree", raising=False)
    snap = build_snapshot(
        idf_path=str(idf_newer),
        commit_ref="newer",
        commit_sha="b" * 40,
        target="esp32",
        env_updates=env,
        rename_paths=rename_paths,
        load_renames_flag=True,
    )
    assert snap.renames["GONE"] == ("GONE_NEW", False)
    assert snap.renames["OLD"] == ("NEW", False)
    assert snap.renames["INV"] == ("INV_NEW", True)


def test_build_snapshot_uses_checkout_not_cwd(
    idf_older: Path,
    idf_newer: Path,
    cwd_trap: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Parser v2 opens the root Kconfig by filename alone. Ensure absolute path +
    chdir pin each checkout (without using legacy $srctree).
    """
    monkeypatch.chdir(cwd_trap)
    monkeypatch.setenv("KCONFIG_PARSER_VERSION", "2")
    monkeypatch.setenv("srctree", str(cwd_trap))

    older_env, _ = _env_for(idf_older, tmp_path / "staging_old")
    newer_env, _ = _env_for(idf_newer, tmp_path / "staging_new")
    older_env["srctree"] = str(cwd_trap)
    newer_env["srctree"] = str(cwd_trap)

    older = build_snapshot(
        idf_path=str(idf_older),
        commit_ref="old",
        commit_sha="1" * 40,
        target="esp32",
        env_updates=older_env,
    )
    newer = build_snapshot(
        idf_path=str(idf_newer),
        commit_ref="new",
        commit_sha="2" * 40,
        target="esp32",
        env_updates=newer_env,
    )

    assert "TRAP_ONLY" not in older.symbols
    assert "TRAP_ONLY" not in newer.symbols
    assert older.symbols["IDF_EXPERIMENTAL_FEATURES"].defaults == ("n",)
    assert newer.symbols["IDF_EXPERIMENTAL_FEATURES"].defaults == ("y",)

    report = compare_snapshots(older, newer)
    assert any(
        c.id == "IDF_EXPERIMENTAL_FEATURES" and c.old_defaults == ("n",) and c.new_defaults == ("y",)
        for c in report.defaults_changed
    )


def test_end_to_end_diff_from_two_fixtures(
    idf_older: Path, idf_newer: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("srctree", raising=False)
    older_env, _ = _env_for(idf_older, tmp_path / "staging_old")
    newer_env, newer_renames = _env_for(idf_newer, tmp_path / "staging_new")

    older = build_snapshot(
        idf_path=str(idf_older),
        commit_ref="old",
        commit_sha="1" * 40,
        target="esp32",
        env_updates=older_env,
    )
    newer = build_snapshot(
        idf_path=str(idf_newer),
        commit_ref="new",
        commit_sha="2" * 40,
        target="esp32",
        env_updates=newer_env,
        rename_paths=newer_renames,
        load_renames_flag=True,
    )

    report = compare_snapshots(older, newer)
    assert report.added == ["ADDED"]
    assert report.removed == []
    assert len(report.renamed) == 1
    assert report.renamed[0].old_name == "GONE"
    assert report.renamed[0].new_name == "GONE_NEW"
    assert any(c.id == "FOO" for c in report.defaults_changed)
    assert any(c.id == "MYCHOICE" and c.kind == "choice" for c in report.defaults_changed)
