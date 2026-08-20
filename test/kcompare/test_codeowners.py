# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the CODEOWNERS parser and path -> group matching.
"""

from pathlib import Path

from kcompare.codeowners import COMMON_GROUP_NAME
from kcompare.codeowners import parse_codeowners
from kcompare.codeowners import parse_codeowners_text

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "CODEOWNERS"


def test_all_groups_only_from_components_rules() -> None:
    index = parse_codeowners(str(FIXTURE))
    # "other" (the '*' rule) and "build-config" (the root /Kconfig rule) are not
    # /components rules and must not appear.
    assert index.all_groups == (
        "app-utilities/console",
        "debugging",
        "peripherals",
        "power-management",
        "storage",
        "system",
    )


def test_simple_and_multi_owner_match() -> None:
    index = parse_codeowners(str(FIXTURE))
    assert index.groups_for_path("components/app_trace/Kconfig") == ("debugging",)
    assert index.groups_for_path("components/esp_hw_support/foo.c") == ("system", "peripherals")


def test_last_match_wins_nested_override() -> None:
    index = parse_codeowners(str(FIXTURE))
    # The nested lowpower rule comes after the esp_hw_support rule and wins.
    assert index.groups_for_path("components/esp_hw_support/lowpower/Kconfig") == ("power-management",)
    assert index.groups_for_path("components/esp_hw_support/other/Kconfig") == ("system", "peripherals")


def test_wildcard_and_more_specific_override() -> None:
    index = parse_codeowners(str(FIXTURE))
    assert index.groups_for_path("components/esp_driver_gpio/Kconfig") == ("peripherals",)
    # The specific esp_driver_sdmmc rule follows the wildcard and wins.
    assert index.groups_for_path("components/esp_driver_sdmmc/Kconfig") == ("peripherals", "storage")


def test_unmatched_paths_return_none() -> None:
    index = parse_codeowners(str(FIXTURE))
    assert index.groups_for_path("Kconfig") is None
    assert index.groups_for_path("tools/idf.py") is None
    assert index.groups_for_path("components/unknown_component/Kconfig") is None


def test_soc_override_takes_precedence_over_codeowners_file() -> None:
    text = "/components/soc/  @esp-idf-codeowners/system @esp-idf-codeowners/peripherals\n"
    index = parse_codeowners_text(text)
    # The hardcoded override wins over the file's own rule for the same path.
    assert index.groups_for_path("components/soc/Kconfig") == ("soc",)
    assert index.groups_for_path("components/soc/esp32/Kconfig") == ("soc",)
    # Unrelated paths are unaffected.
    assert index.groups_for_path("components/other/Kconfig") is None


def test_soc_extraction_shadows_the_groups_it_replaces() -> None:
    text = "/components/soc/  @esp-idf-codeowners/system @esp-idf-codeowners/peripherals\n"
    index = parse_codeowners_text(text)
    extraction_by_group = {e.group: e for e in index.extractions}
    soc = extraction_by_group["soc"]
    assert soc.shadowed_groups == ("peripherals", "system")
    assert "components/soc" in soc.description


def test_common_extraction_is_always_present_and_shadows_every_group() -> None:
    index = parse_codeowners(str(FIXTURE))
    extraction_by_group = {e.group: e for e in index.extractions}
    common = extraction_by_group[COMMON_GROUP_NAME]
    assert common.shadowed_groups is None  # broadcasts a note to every other group
