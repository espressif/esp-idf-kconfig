# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the ``-o``/``--output`` CLI option (format + destination file).
"""

import json
import os
from pathlib import Path
from typing import Iterator

import pytest

from kcompare.cli import main
from kcompare.codeowners import parse_codeowners
from kcompare.models import DiffReport
from kcompare.models import MultiTargetDiffReport

_CODEOWNERS_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "CODEOWNERS"


@pytest.fixture(autouse=True)
def _restore_kconfig_report_verbosity() -> Iterator[None]:
    """
    ``main()`` sets ``KCONFIG_REPORT_VERBOSITY`` in the process environment;
    restore it so this doesn't leak into other tests.
    """
    saved = os.environ.get("KCONFIG_REPORT_VERBOSITY")
    yield
    if saved is None:
        os.environ.pop("KCONFIG_REPORT_VERBOSITY", None)
    else:
        os.environ["KCONFIG_REPORT_VERBOSITY"] = saved


def _fake_report() -> MultiTargetDiffReport:
    return MultiTargetDiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        targets_compared=["esp32"],
        targets_skipped=[],
        reports=[
            DiffReport(
                older_commit="v1",
                older_sha="a" * 40,
                newer_commit="v2",
                newer_sha="b" * 40,
                target="esp32",
                added=["NEW_OPT"],
            )
        ],
    )


def _fake_multi_report() -> MultiTargetDiffReport:
    return MultiTargetDiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        reports=[
            DiffReport(
                older_commit="v1",
                older_sha="a" * 40,
                newer_commit="v2",
                newer_sha="b" * 40,
                target="esp32",
                added=["ALL_TARGETS_OPT"],
            )
        ],
    )


def _fake_two_target_report() -> MultiTargetDiffReport:
    return MultiTargetDiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        targets_compared=["esp32", "esp32s2"],
        reports=[
            DiffReport(
                older_commit="v1",
                older_sha="a" * 40,
                newer_commit="v2",
                newer_sha="b" * 40,
                target="esp32",
                added=["COMMON", "ESP32_ONLY"],
            ),
            DiffReport(
                older_commit="v1",
                older_sha="a" * 40,
                newer_commit="v2",
                newer_sha="b" * 40,
                target="esp32s2",
                added=["COMMON"],
            ),
        ],
    )


def _fake_codeowner_report() -> MultiTargetDiffReport:
    return MultiTargetDiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        targets_compared=["esp32"],
        reports=[
            DiffReport(
                older_commit="v1",
                older_sha="a" * 40,
                newer_commit="v2",
                newer_sha="b" * 40,
                target="esp32",
                added=["TRACE_OPT", "ROOT_OPT"],
                locations_by_id={
                    "TRACE_OPT": ("components/app_trace/Kconfig:1",),
                    "ROOT_OPT": ("Kconfig:3",),
                },
            )
        ],
        codeowners=parse_codeowners(str(_CODEOWNERS_FIXTURE)),
    )


def _stub_codeowner_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kcompare.cli.is_idf_root", lambda path: True)
    monkeypatch.setattr("kcompare.cli.run_repo_compare", lambda **kwargs: _fake_codeowner_report())


def _stub_repo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kcompare.cli.is_idf_root", lambda path: True)

    def _fake_compare(**kwargs: object) -> MultiTargetDiffReport:
        if kwargs.get("target"):
            return _fake_report()
        return _fake_multi_report()

    monkeypatch.setattr("kcompare.cli.run_repo_compare", _fake_compare)


def test_output_defaults_to_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_repo_mode(monkeypatch)
    monkeypatch.chdir(tmp_path)

    main(["c1", "c2", "-t", "esp32"], standalone_mode=False)

    out = capsys.readouterr().out
    assert "NEW_OPT" in out


def test_output_format_and_file_writes_to_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_repo_mode(monkeypatch)
    monkeypatch.chdir(tmp_path)
    out_file = tmp_path / "report.json"

    main(["c1", "c2", str(out_file), "-t", "esp32", "-o", "json"], standalone_mode=False)

    captured = capsys.readouterr()
    assert captured.out == ""
    data = json.loads(out_file.read_text())
    assert data["aggregation"] == "change"
    assert data["targets_compared"] == ["esp32"]
    assert data["reports"]["added"] == [{"name": "NEW_OPT", "targets_affected": ["esp32"]}]
    # Commit refs live only in the preamble, not in the reports body.
    assert "older_commit" not in data["reports"]


def test_output_dash_forces_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_repo_mode(monkeypatch)
    monkeypatch.chdir(tmp_path)

    main(["c1", "c2", "-", "-t", "esp32", "-o", "json"], standalone_mode=False)

    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["reports"]["added"] == [{"name": "NEW_OPT", "targets_affected": ["esp32"]}]


def test_default_run_sets_quiet_kconfig_report_verbosity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Without ``-v``, ``KCONFIG_REPORT_VERBOSITY`` must be "quiet" so
    ``KconfigReport`` (created lazily on the first ``Kconfig()`` build)
    installs its logger at ``Verbosity.SILENT`` and its ``log.note(...)``
    parser notes/warnings don't leak to stderr.
    """
    _stub_repo_mode(monkeypatch)
    monkeypatch.chdir(tmp_path)

    main(["c1", "c2", "-t", "esp32"], standalone_mode=False)

    assert os.environ["KCONFIG_REPORT_VERBOSITY"] == "quiet"


def test_verbose_run_sets_verbose_kconfig_report_verbosity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _stub_repo_mode(monkeypatch)
    monkeypatch.chdir(tmp_path)

    main(["c1", "c2", "-t", "esp32", "-v"], standalone_mode=False)

    assert os.environ["KCONFIG_REPORT_VERBOSITY"] == "verbose"


def test_omitted_target_runs_all_targets_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_repo_mode(monkeypatch)
    monkeypatch.chdir(tmp_path)

    main(["c1", "c2"], standalone_mode=False)

    out = capsys.readouterr().out
    assert "ALL_TARGETS_OPT" in out


def test_aggregation_defaults_to_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("kcompare.cli.is_idf_root", lambda path: True)
    monkeypatch.setattr("kcompare.cli.run_repo_compare", lambda **kwargs: _fake_two_target_report())
    monkeypatch.chdir(tmp_path)

    main(["c1", "c2", "-", "-o", "json"], standalone_mode=False)

    data = json.loads(capsys.readouterr().out)
    assert data["aggregation"] == "change"
    affected = {c["name"]: c["targets_affected"] for c in data["reports"]["added"]}
    # Affecting every compared target collapses to the "all" sentinel.
    assert affected["COMMON"] == ["all"]
    assert affected["ESP32_ONLY"] == ["esp32"]


def test_aggregation_target_emits_per_target_sections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("kcompare.cli.is_idf_root", lambda path: True)
    monkeypatch.setattr("kcompare.cli.run_repo_compare", lambda **kwargs: _fake_two_target_report())
    monkeypatch.chdir(tmp_path)

    main(["c1", "c2", "-", "-o", "json", "--aggregation", "target"], standalone_mode=False)

    data = json.loads(capsys.readouterr().out)
    assert data["aggregation"] == "target"
    assert data["reports"][0]["target"] == "esp32"
    assert data["reports"][0]["added"] == ["COMMON", "ESP32_ONLY"]
    assert data["reports"][1]["target"] == "esp32s2"
    assert data["reports"][1]["added"] == ["COMMON"]


def test_aggregation_aggregated_emits_groups(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("kcompare.cli.is_idf_root", lambda path: True)
    monkeypatch.setattr("kcompare.cli.run_repo_compare", lambda **kwargs: _fake_two_target_report())
    monkeypatch.chdir(tmp_path)

    main(["c1", "c2", "-", "-o", "json", "--aggregation", "aggregated"], standalone_mode=False)

    data = json.loads(capsys.readouterr().out)
    assert data["aggregation"] == "aggregated"
    assert data["reports"][0]["targets"] == ["all"]
    assert data["reports"][1]["targets"] == ["esp32"]


def test_by_codeowner_stdout_prefixes_group_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_codeowner_mode(monkeypatch)
    monkeypatch.chdir(tmp_path)

    main(["c1", "c2", "-t", "esp32", "--by-codeowner"], standalone_mode=False)

    out = capsys.readouterr().out
    assert "Report for codeowner group debugging" in out
    assert "Report for codeowner group common" in out
    # ROOT_OPT is unmatched, so it is extracted to the "common" group instead
    # of appearing in debugging; debugging gets a note pointing to it.
    common_section, _, debugging_section = out.partition("Report for codeowner group debugging")
    assert "TRACE_OPT" in debugging_section
    assert "ROOT_OPT" not in debugging_section
    assert "extracted to a standalone report" in debugging_section
    assert "ROOT_OPT" in common_section
    # The "common" group's header spells out what it actually contains.
    assert "configs which do not belong to any other codeowner group" in common_section
    assert "configs which do not belong to any other codeowner group" not in debugging_section


def test_by_codeowner_output_file_is_templated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_codeowner_mode(monkeypatch)
    monkeypatch.chdir(tmp_path)
    out_file = tmp_path / "report.json"

    main(["c1", "c2", str(out_file), "-t", "esp32", "-o", "json", "--by-codeowner"], standalone_mode=False)

    assert capsys.readouterr().out == ""
    debugging = tmp_path / "report_debugging.json"
    assert debugging.exists()
    data = json.loads(debugging.read_text())
    assert data["codeowner_group"] == "debugging"
    assert data["reports"]["added"] == [{"name": "TRACE_OPT", "targets_affected": ["esp32"]}]
    # ROOT_OPT (unmatched, root Kconfig) is extracted into its own "common"
    # report instead of appearing in debugging.
    assert data["extraction_notes"] == [
        {"description": "the root Kconfig and components with no CODEOWNERS entry", "target_group": "common"}
    ]
    common = tmp_path / "report_common.json"
    assert common.exists()
    common_data = json.loads(common.read_text())
    assert common_data["codeowner_group"] == "common"
    assert common_data["reports"]["added"] == [{"name": "ROOT_OPT", "targets_affected": ["esp32"]}]
    # A group that owns nothing beyond the extracted ROOT_OPT no longer exists.
    assert not (tmp_path / "report_peripherals.json").exists()


def test_by_codeowner_stdout_json_is_single_object(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_codeowner_mode(monkeypatch)
    monkeypatch.chdir(tmp_path)

    main(["c1", "c2", "-", "-t", "esp32", "-o", "json", "--by-codeowner"], standalone_mode=False)

    data = json.loads(capsys.readouterr().out)
    assert "codeowner_groups" in data
    assert data["aggregation"] == "change"
    assert "debugging" in data["codeowner_groups"]
    assert data["codeowner_groups"]["debugging"]["codeowner_group"] == "debugging"


def test_non_idf_root_dies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("kcompare.cli.is_idf_root", lambda path: False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        main(["c1", "c2", "-t", "esp32"], standalone_mode=False)
