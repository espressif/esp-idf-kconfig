# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Tests for splitting reports by codeowner group.
"""

from pathlib import Path
from typing import Dict
from typing import Tuple

from kcompare.aggregate import merge_report
from kcompare.codeowners import CodeownersIndex
from kcompare.codeowners import parse_codeowners
from kcompare.codeowners import parse_codeowners_text
from kcompare.models import DefaultChange
from kcompare.models import DiffReport
from kcompare.models import MergedDiffReport
from kcompare.models import MultiTargetDiffReport
from kcompare.split_codeowners import split_by_codeowner

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "CODEOWNERS"


def _codeowners(report: MultiTargetDiffReport) -> CodeownersIndex:
    assert report.codeowners is not None
    return report.codeowners


def _multi() -> MultiTargetDiffReport:
    """
    One-target report exercising: single owner, multi-owner, a multi-definition
    symbol (union of owners), a choice, and an unmatched (root) symbol that must
    broadcast to every group.
    """
    locations: Dict[str, Tuple[str, ...]] = {
        "SYM_TRACE": ("components/app_trace/Kconfig:1",),
        "SYM_HW": ("components/esp_hw_support/Kconfig:5",),
        "SYM_MULTI": ("components/app_trace/Kconfig:9", "components/esp_driver_sdmmc/Kconfig:3"),
        "SYM_ROOT": ("Kconfig:12",),
        "CH_CONSOLE": ("components/console/Kconfig:20",),
    }
    diff = DiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        target="esp32",
        added=["SYM_TRACE", "SYM_HW", "SYM_MULTI"],
        removed=["SYM_ROOT"],
        choices_added=["CH_CONSOLE"],
        locations_by_id=locations,
    )
    return MultiTargetDiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        targets_compared=["esp32"],
        reports=[diff],
        codeowners=parse_codeowners(str(FIXTURE)),
    )


def test_split_multi_assigns_changes_to_owner_groups() -> None:
    report = _multi()
    groups = split_by_codeowner(report, _codeowners(report))

    debugging = groups["debugging"]
    assert type(debugging) is MultiTargetDiffReport
    assert "SYM_TRACE" in debugging.reports[0].added
    assert "SYM_MULTI" in debugging.reports[0].added  # multi-def union includes debugging

    peripherals = groups["peripherals"]
    assert type(peripherals) is MultiTargetDiffReport
    assert "SYM_HW" in peripherals.reports[0].added

    system = groups["system"]
    assert type(system) is MultiTargetDiffReport
    assert "SYM_HW" in system.reports[0].added

    storage = groups["storage"]
    assert type(storage) is MultiTargetDiffReport
    assert "SYM_MULTI" in storage.reports[0].added  # from the esp_driver_sdmmc definition

    console = groups["app-utilities/console"]
    assert type(console) is MultiTargetDiffReport
    assert "CH_CONSOLE" in console.reports[0].choices_added


def test_unmatched_change_extracted_to_common_group() -> None:
    report = _multi()
    codeowners = _codeowners(report)
    groups = split_by_codeowner(report, codeowners)

    # SYM_ROOT is defined in the root Kconfig (no /components rule) -> only
    # in the synthetic "common" group, not in any codeowner group.
    common = groups["common"]
    assert type(common) is MultiTargetDiffReport
    assert "SYM_ROOT" in common.reports[0].removed
    for group, split in groups.items():
        if group == "common":
            continue
        assert type(split) is MultiTargetDiffReport
        assert "SYM_ROOT" not in split.reports[0].removed
    # power-management owns none of the matched changes and doesn't exist,
    # since SYM_ROOT no longer broadcasts to it.
    assert "power-management" not in groups
    # Every real group gets a note pointing to the "common" report instead.
    debugging = groups["debugging"]
    assert debugging.extraction_notes
    assert debugging.extraction_notes[0].target_group == "common"


def test_split_sets_codeowner_group_and_drops_empty_targets() -> None:
    report = _multi()
    groups = split_by_codeowner(report, _codeowners(report))
    debugging = groups["debugging"]
    assert type(debugging) is MultiTargetDiffReport
    assert debugging.codeowner_group == "debugging"
    # The single target has changes for debugging, so it is retained.
    assert [r.target for r in debugging.reports] == ["esp32"]


def test_split_merged_report() -> None:
    report = _multi()
    codeowners = _codeowners(report)
    merged = merge_report(report, "change")
    assert type(merged) is MergedDiffReport
    assert merged.codeowners is codeowners
    # locations propagated into the merged report.
    assert merged.locations_by_id["SYM_HW"] == ("components/esp_hw_support/Kconfig:5",)

    groups = split_by_codeowner(merged, codeowners)
    debugging = groups["debugging"]
    assert type(debugging) is MergedDiffReport
    debugging_names = {c.name for c in debugging.changes if c.kind == "added"}
    assert "SYM_TRACE" in debugging_names
    assert "SYM_MULTI" in debugging_names
    # SYM_ROOT is extracted to "common" instead of reaching every group.
    common = groups["common"]
    assert type(common) is MergedDiffReport
    common_removed = {c.name for c in common.changes if c.kind == "removed"}
    assert "SYM_ROOT" in common_removed
    for group, split in groups.items():
        if group == "common":
            continue
        assert type(split) is MergedDiffReport
        removed = {c.name for c in split.changes if c.kind == "removed"}
        assert "SYM_ROOT" not in removed


def test_soc_override_splits_into_own_group_and_notes_shadowed_groups() -> None:
    """
    components/soc is normally owned by system+peripherals, but the hardcoded
    override carves it out into its own "soc" group; only those two groups
    (not e.g. debugging) get a note pointing to it.
    """
    codeowners = parse_codeowners_text(
        "/components/soc/  @esp-idf-codeowners/system @esp-idf-codeowners/peripherals\n"
        "/components/esp_hw_support/  @esp-idf-codeowners/system @esp-idf-codeowners/peripherals\n"
        "/components/app_trace/  @esp-idf-codeowners/debugging\n"
    )
    locations: Dict[str, Tuple[str, ...]] = {
        "SYM_SOC": ("components/soc/Kconfig:1",),
        # Keeps system/peripherals non-empty so they're still emitted (and can
        # carry the "soc" extraction note) even though SYM_SOC moved away.
        "SYM_HW": ("components/esp_hw_support/Kconfig:5",),
        "SYM_TRACE": ("components/app_trace/Kconfig:1",),
    }
    diff = DiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        target="esp32",
        added=["SYM_SOC", "SYM_HW", "SYM_TRACE"],
        locations_by_id=locations,
    )
    report = MultiTargetDiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        targets_compared=["esp32"],
        reports=[diff],
        codeowners=codeowners,
    )
    groups = split_by_codeowner(report, codeowners)

    soc = groups["soc"]
    assert type(soc) is MultiTargetDiffReport
    assert "SYM_SOC" in soc.reports[0].added
    assert soc.extraction_notes == ()

    system = groups["system"]
    assert type(system) is MultiTargetDiffReport
    assert "SYM_SOC" not in system.reports[0].added
    assert [n.target_group for n in system.extraction_notes] == ["soc"]

    peripherals = groups["peripherals"]
    assert type(peripherals) is MultiTargetDiffReport
    assert "SYM_SOC" not in peripherals.reports[0].added
    assert [n.target_group for n in peripherals.extraction_notes] == ["soc"]

    # debugging never owned components/soc, so it gets no "soc" note.
    debugging = groups["debugging"]
    assert type(debugging) is MultiTargetDiffReport
    assert "SYM_SOC" not in debugging.reports[0].added
    assert "SYM_TRACE" in debugging.reports[0].added
    assert debugging.extraction_notes == ()


def test_split_with_default_change_uses_symbol_location() -> None:
    locations: Dict[str, Tuple[str, ...]] = {"SYM_HW": ("components/esp_hw_support/Kconfig:5",)}
    diff = DiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        target="esp32",
        defaults_changed=[DefaultChange(id="SYM_HW", kind="symbol", old_defaults=("y",), new_defaults=("n",))],
        locations_by_id=locations,
    )
    report = MultiTargetDiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        targets_compared=["esp32"],
        reports=[diff],
        codeowners=parse_codeowners(str(FIXTURE)),
    )
    groups = split_by_codeowner(report, _codeowners(report))
    assert set(groups.keys()) == {"system", "peripherals"}
    system = groups["system"]
    assert type(system) is MultiTargetDiffReport
    assert system.reports[0].defaults_changed[0].id == "SYM_HW"
