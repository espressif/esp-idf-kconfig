# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from typing import Dict
from typing import Optional
from typing import Tuple

from kcompare.diff import compare_snapshots
from kcompare.models import ChoiceSnapshot
from kcompare.models import ConfigurationSnapshot
from kcompare.models import SymbolSnapshot


def _sym(
    name: str,
    defaults: Tuple[str, ...] = (),
) -> SymbolSnapshot:
    return SymbolSnapshot(name=name, defaults=defaults)


def _snap(
    commit: str,
    symbols: Optional[Dict[str, SymbolSnapshot]] = None,
    choices: Optional[Dict[str, ChoiceSnapshot]] = None,
    renames: Optional[Dict[str, Tuple[str, bool]]] = None,
) -> ConfigurationSnapshot:
    return ConfigurationSnapshot(
        commit=commit,
        commit_sha=commit * 8 if len(commit) == 1 else commit,
        target="esp32",
        symbols=dict(symbols or {}),
        choices=dict(choices or {}),
        renames=dict(renames or {}),
    )


def test_added_removed_renamed() -> None:
    older = _snap(
        "a",
        symbols={
            "OLD_ONLY": _sym("OLD_ONLY"),
            "RENAMED_OLD": _sym("RENAMED_OLD"),
            "KEEP": _sym("KEEP"),
        },
    )
    newer = _snap(
        "b",
        symbols={
            "NEW_ONLY": _sym("NEW_ONLY"),
            "RENAMED_NEW": _sym("RENAMED_NEW"),
            "KEEP": _sym("KEEP"),
        },
        renames={"RENAMED_OLD": ("RENAMED_NEW", False)},
    )
    report = compare_snapshots(older, newer)
    assert report.added == ["NEW_ONLY"]
    assert report.removed == ["OLD_ONLY"]
    assert len(report.renamed) == 1
    assert report.renamed[0].old_name == "RENAMED_OLD"
    assert report.renamed[0].new_name == "RENAMED_NEW"
    assert report.renamed[0].inverted is False


def test_rename_missing_stays_independent() -> None:
    older = _snap("a", symbols={"A": _sym("A")})
    newer = _snap("b", symbols={"A_NEW": _sym("A_NEW")})
    report = compare_snapshots(older, newer)
    assert report.added == ["A_NEW"]
    assert report.removed == ["A"]
    assert report.renamed == []


def test_inverted_rename() -> None:
    older = _snap("a", symbols={"OLD": _sym("OLD")})
    newer = _snap(
        "b",
        symbols={"NEW": _sym("NEW")},
        renames={"OLD": ("NEW", True)},
    )
    report = compare_snapshots(older, newer)
    assert report.renamed[0].inverted is True
    assert report.added == []
    assert report.removed == []


def test_defaults_changed() -> None:
    older = _snap(
        "a",
        symbols={
            "FOO": _sym("FOO", defaults=("y",)),
        },
    )
    newer = _snap(
        "b",
        symbols={
            "FOO": _sym("FOO", defaults=("n",)),
        },
    )
    report = compare_snapshots(older, newer)
    assert len(report.defaults_changed) == 1
    assert report.defaults_changed[0].old_defaults == ("y",)
    assert report.defaults_changed[0].new_defaults == ("n",)


def test_choice_default_change_reports_symbol_names() -> None:
    older = _snap(
        "a",
        choices={
            "MYCHOICE": ChoiceSnapshot(
                id="MYCHOICE",
                name="MYCHOICE",
                locations=("Kconfig:10",),
                defaults=("OPT_A",),
                default_symbol_names=("OPT_A",),
                options=("OPT_A", "OPT_B"),
            )
        },
    )
    newer = _snap(
        "b",
        choices={
            "MYCHOICE": ChoiceSnapshot(
                id="MYCHOICE",
                name="MYCHOICE",
                locations=("Kconfig:10",),
                defaults=("OPT_B",),
                default_symbol_names=("OPT_B",),
                options=("OPT_A", "OPT_B", "OPT_C"),
            )
        },
    )
    report = compare_snapshots(older, newer)
    assert len(report.defaults_changed) == 1
    ch = report.defaults_changed[0]
    assert ch.kind == "choice"
    assert ch.old_default_symbols == ("OPT_A",)
    assert ch.new_default_symbols == ("OPT_B",)
    assert ch.old_options == ("OPT_A", "OPT_B")
    assert ch.new_options == ("OPT_A", "OPT_B", "OPT_C")


def test_choice_added_and_removed_report_options() -> None:
    older = _snap(
        "a",
        choices={
            "OLD_CHOICE": ChoiceSnapshot(
                id="OLD_CHOICE",
                name="OLD_CHOICE",
                locations=("Kconfig:1",),
                defaults=(),
                default_symbol_names=(),
                options=("OLD_OPT_A", "OLD_OPT_B"),
            )
        },
    )
    newer = _snap(
        "b",
        choices={
            "NEW_CHOICE": ChoiceSnapshot(
                id="NEW_CHOICE",
                name="NEW_CHOICE",
                locations=("Kconfig:1",),
                defaults=(),
                default_symbol_names=(),
                options=("NEW_OPT_A", "NEW_OPT_B"),
            )
        },
    )
    report = compare_snapshots(older, newer)
    assert report.choices_added == ["NEW_CHOICE"]
    assert report.choices_removed == ["OLD_CHOICE"]
    assert report.choice_options["NEW_CHOICE"] == ("NEW_OPT_A", "NEW_OPT_B")
    assert report.choice_options["OLD_CHOICE"] == ("OLD_OPT_A", "OLD_OPT_B")
