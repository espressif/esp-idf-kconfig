# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the change / aggregated views (kcompare.aggregate + models).
"""

from kcompare.aggregate import merge_report
from kcompare.models import DefaultChange
from kcompare.models import DiffReport
from kcompare.models import MultiTargetDiffReport
from kcompare.models import RenamedEntry
from kcompare.models import SkippedTarget


def _multi() -> MultiTargetDiffReport:
    """
    Two compared targets (esp32, esp32s2) plus one skipped (esp32c3).

    COMMON / rename A→B / default FOO affect both targets; ESP32_ONLY and the
    added choice CH affect esp32 only.
    """
    common_default = DefaultChange(id="FOO", kind="symbol", old_defaults=("y",), new_defaults=("n",))
    return MultiTargetDiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        targets_compared=["esp32", "esp32s2"],
        targets_skipped=[SkippedTarget("esp32c3", "v2", "v1")],
        reports=[
            DiffReport(
                older_commit="v1",
                older_sha="a" * 40,
                newer_commit="v2",
                newer_sha="b" * 40,
                target="esp32",
                added=["COMMON", "ESP32_ONLY"],
                renamed=[RenamedEntry("A", "B", False)],
                defaults_changed=[common_default],
                choices_added=["CH"],
                choice_options={"CH": ("OPT_A", "OPT_B")},
            ),
            DiffReport(
                older_commit="v1",
                older_sha="a" * 40,
                newer_commit="v2",
                newer_sha="b" * 40,
                target="esp32s2",
                added=["COMMON"],
                renamed=[RenamedEntry("A", "B", False)],
                defaults_changed=[common_default],
            ),
        ],
    )


def test_change_view_annotates_affected_targets() -> None:
    data = merge_report(_multi(), "change").to_dict()

    assert data["aggregation"] == "change"
    assert data["targets_compared"] == ["esp32", "esp32s2"]
    assert data["targets_skipped"][0]["target"] == "esp32c3"
    # Commit refs are in the preamble only.
    assert data["older_commit"] == "v1" and data["newer_commit"] == "v2"

    added = {c["name"]: c["targets_affected"] for c in data["reports"]["added"]}
    # Affecting every compared target collapses to the "all" sentinel.
    assert added["COMMON"] == ["all"]
    assert added["ESP32_ONLY"] == ["esp32"]

    rename = next(r for r in data["reports"]["renamed"] if r["old_name"] == "A")
    assert rename["new_name"] == "B"
    assert rename["targets_affected"] == ["all"]

    default = next(d for d in data["reports"]["defaults_changed"] if d["id"] == "FOO")
    assert default["kind"] == "symbol"
    assert default["targets_affected"] == ["all"]

    choice = next(c for c in data["reports"]["choices_added"] if c["id"] == "CH")
    assert choice["targets_affected"] == ["esp32"]
    assert choice["options"] == ["OPT_A", "OPT_B"]


def test_aggregated_view_buckets_by_target_set() -> None:
    data = merge_report(_multi(), "aggregated").to_dict()

    assert data["aggregation"] == "aggregated"
    groups = data["reports"]
    # "all" bucket first (folded to the "all" sentinel since 2+ targets were
    # compared), then the esp32-only bucket; no empty combinations.
    assert groups[0]["targets"] == ["all"]
    assert groups[1]["targets"] == ["esp32"]

    all_changes = groups[0]
    assert "COMMON" in all_changes["added"]
    assert all_changes["renamed"][0]["old_name"] == "A"
    assert all_changes["defaults_changed"][0]["id"] == "FOO"

    esp32_changes = groups[1]
    assert "ESP32_ONLY" in esp32_changes["added"]
    assert esp32_changes["choices_added"] == [{"id": "CH", "options": ["OPT_A", "OPT_B"]}]

    # Inside a group, per-change target lists are omitted (implied by the group).
    assert "targets_affected" not in all_changes["defaults_changed"][0]
    assert "targets_affected" not in all_changes["renamed"][0]
