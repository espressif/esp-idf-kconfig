# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import json
import re
from io import StringIO

from rich.console import Console

from kcompare.emitter import emit_human
from kcompare.emitter import emit_report
from kcompare.emitter import format_json
from kcompare.emitter import format_markdown
from kcompare.emitter import format_markdown_multi
from kcompare.models import DefaultChange
from kcompare.models import DiffReport
from kcompare.models import MultiTargetDiffReport
from kcompare.models import RenamedEntry


def _sample_report() -> DiffReport:
    return DiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        target="esp32",
        added=["NEW_OPT"],
        removed=["OLD_OPT"],
        renamed=[RenamedEntry("RENAME_OLD", "RENAME_NEW", False)],
        defaults_changed=[
            DefaultChange(
                id="FOO",
                kind="symbol",
                old_defaults=("y",),
                new_defaults=("n",),
            )
        ],
    )


def test_json_and_markdown_and_human() -> None:
    report = _sample_report()
    data = json.loads(format_json(report))
    assert data["target"] == "esp32"
    assert data["added"] == ["NEW_OPT"]

    md = format_markdown(report)
    assert "# Kconfig comparison" in md
    assert "NEW_OPT" in md

    buf = StringIO()
    emit_report(report, "human", file=buf)
    assert "Kconfig comparison" in buf.getvalue()


def test_markdown_default_table_escapes_pipes() -> None:
    """
    Kconfig ``A || B`` must not break markdown pipe tables (e.g. GitLab wiki).
    """
    report = DiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        target="esp32",
        defaults_changed=[
            DefaultChange(
                id="FOO",
                kind="symbol",
                old_defaults=("n if A || B",),
                new_defaults=("n if A || B", "C if D || E"),
            )
        ],
    )
    md = format_markdown(report)
    assert r"`default n if A \|\| B`" in md
    assert r"`default C if D \|\| E`" in md
    # One row for the unchanged default, one for the inserted default.
    data_rows = [
        line
        for line in md.splitlines()
        if line.startswith("| ") and not line.startswith("| ---") and not line.startswith("| before")
    ]
    assert len(data_rows) == 2
    assert data_rows[0] == r"| `default n if A \|\| B` |  | `default n if A \|\| B` |"
    assert data_rows[1] == r"| *(new)* | **→** | `default C if D \|\| E` |"


def test_choices_added_removed_show_options() -> None:
    report = DiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        target="esp32",
        choices_added=["NEW_CHOICE"],
        choices_removed=["OLD_CHOICE"],
        choice_options={"NEW_CHOICE": ("OPT_A", "OPT_B"), "OLD_CHOICE": ("OPT_C",)},
    )
    md = format_markdown(report)
    assert "`NEW_CHOICE` (options: `OPT_A`, `OPT_B`)" in md
    assert "`OLD_CHOICE` (options: `OPT_C`)" in md

    buf = StringIO()
    emit_report(report, "human", file=buf)
    output = buf.getvalue()
    assert "NEW_CHOICE [options: OPT_A, OPT_B]" in output
    assert "OLD_CHOICE [options: OPT_C]" in output

    data = json.loads(format_json(report))
    assert {"id": "NEW_CHOICE", "options": ["OPT_A", "OPT_B"]} in data["choices_added"]
    assert {"id": "OLD_CHOICE", "options": ["OPT_C"]} in data["choices_removed"]


def test_defaults_diff_aligns_unchanged_lines_around_a_removal() -> None:
    """
    Removing a middle default must not misalign the unrelated defaults that
    surround it: "default 1"/"default 3" stay paired, only "default 2" is
    marked removed.
    """
    report = DiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        target="esp32",
        defaults_changed=[
            DefaultChange(
                id="FOO",
                kind="symbol",
                old_defaults=("1", "2", "3"),
                new_defaults=("1", "3"),
            )
        ],
    )
    md = format_markdown(report)
    data_rows = [
        line
        for line in md.splitlines()
        if line.startswith("| ") and not line.startswith("| ---") and not line.startswith("| before")
    ]
    assert len(data_rows) == 3
    assert data_rows[0] == "| `default 1` |  | `default 1` |"
    assert data_rows[1] == "| `default 2` | **→** | *(removed)* |"
    assert data_rows[2] == "| `default 3` |  | `default 3` |"


def test_defaults_diff_console_survives_line_wrapping_of_a_long_condition() -> None:
    """
    A removed default with a condition long enough to word-wrap onto extra
    terminal lines must not push the following unchanged default ("3") out
    of alignment with its counterpart, and changed lines must be bold.
    """
    report = DiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        target="esp32",
        defaults_changed=[
            DefaultChange(
                id="FOO",
                kind="symbol",
                old_defaults=("1", "2 if SOME_CONDITION_NAME_THAT_IS_LONG_ENOUGH_TO_WRAP_ONTO_MORE_THAN_ONE_LINE", "3"),
                new_defaults=("1", "3"),
            )
        ],
    )
    console = Console(file=StringIO(), width=70, height=1000, force_terminal=True, color_system="standard")
    emit_human(report, console)
    lines = console.file.getvalue().splitlines()

    default_3_lines = [line for line in lines if "default 3" in line]
    assert len(default_3_lines) == 1
    assert default_3_lines[0].count("default 3") == 2

    removed_lines = [line for line in lines if "(removed)" in line]
    assert len(removed_lines) == 1
    assert "default 3" not in removed_lines[0]

    # Check for the bold SGR parameter (1) rather than a literal "\x1b[1m"
    # substring: rich may pack it together with the color code (e.g.
    # "\x1b[1;31m") instead of emitting it as its own escape sequence.
    changed_line = next(line for line in lines if "default 2" in line)
    sgr_params = [p for code in re.findall(r"\x1b\[([0-9;]*)m", changed_line) for p in code.split(";")]
    assert "1" in sgr_params


def test_unnamed_choice_display() -> None:
    report = DiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        target="esp32",
        choices_added=["components/foo/Kconfig:42"],
        defaults_changed=[
            DefaultChange(
                id="components/bar/Kconfig:10",
                kind="choice",
                old_defaults=("SYM_A",),
                new_defaults=("SYM_B",),
                old_default_symbols=("SYM_A",),
                new_default_symbols=("SYM_B",),
            )
        ],
    )
    buf = StringIO()
    emit_report(report, "human", file=buf)
    output = buf.getvalue()
    assert "unnamed choice defined at components/foo/Kconfig:42" in output
    assert "unnamed choice defined at components/bar/Kconfig:10" in output

    md = format_markdown(report)
    assert "unnamed choice defined at components/foo/Kconfig:42" in md


def _sample_multi_report() -> MultiTargetDiffReport:
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
                added=["ESP32_ONLY_OPT"],
            ),
            DiffReport(
                older_commit="v1",
                older_sha="a" * 40,
                newer_commit="v2",
                newer_sha="b" * 40,
                target="esp32s2",
                removed=["ESP32S2_ONLY_OPT"],
            ),
        ],
    )


def test_multi_target_json_and_markdown_and_human() -> None:
    report = _sample_multi_report()

    buf = StringIO()
    emit_report(report, "json", file=buf)
    data = json.loads(buf.getvalue())
    assert [r["target"] for r in data["reports"]] == ["esp32", "esp32s2"]
    assert data["reports"][0]["added"] == ["ESP32_ONLY_OPT"]

    md = format_markdown_multi(report)
    assert "## Target: esp32\n" in md
    assert "## Target: esp32s2\n" in md
    assert "ESP32_ONLY_OPT" in md
    assert "ESP32S2_ONLY_OPT" in md

    buf = StringIO()
    emit_report(report, "human", file=buf)
    output = buf.getvalue()
    assert "TARGET: esp32" in output
    assert "TARGET: esp32s2" in output
    assert "ESP32_ONLY_OPT" in output


def test_multi_target_omits_empty_targets() -> None:
    report = MultiTargetDiffReport(
        older_commit="v1",
        older_sha="a" * 40,
        newer_commit="v2",
        newer_sha="b" * 40,
        targets_compared=["esp32", "esp32s2", "esp32c3"],
        reports=[
            DiffReport(
                older_commit="v1",
                older_sha="a" * 40,
                newer_commit="v2",
                newer_sha="b" * 40,
                target="esp32",
                added=["ONLY_ESP32"],
            ),
            DiffReport(
                older_commit="v1",
                older_sha="a" * 40,
                newer_commit="v2",
                newer_sha="b" * 40,
                target="esp32s2",
            ),
            DiffReport(
                older_commit="v1",
                older_sha="a" * 40,
                newer_commit="v2",
                newer_sha="b" * 40,
                target="esp32c3",
            ),
        ],
    )

    data = report.to_dict()
    assert data["targets_compared"] == ["esp32", "esp32s2", "esp32c3"]
    assert [r["target"] for r in data["reports"]] == ["esp32"]

    md = format_markdown_multi(report)
    assert "## Target: esp32\n" in md
    assert "## Target: esp32s2\n" not in md
    assert "## Target: esp32c3\n" not in md

    buf = StringIO()
    emit_report(report, "human", file=buf)
    output = buf.getvalue()
    assert "TARGET: esp32" in output
    assert "TARGET: esp32s2" not in output
    assert "TARGET: esp32c3" not in output
    # Preamble still mentions every compared target.
    assert "esp32s2" in output
