# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Output formatters for DiffReport: JSON, Markdown, and human-readable console.
"""

import difflib
import json
import os
import re
import sys
from typing import IO
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import TypeVar
from typing import Union

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .codeowners import COMMON_GROUP_NAME
from .models import DefaultChange
from .models import DiffReport
from .models import ExtractionNote
from .models import MergedChange
from .models import MergedDiffReport
from .models import MultiTargetDiffReport
from .models import SkippedTarget
from .models import group_merged_changes

_LOCATION_RE = re.compile(r".+:\d+$")

# One aligned row of a defaults diff: (old_line, new_line, changed). Either
# line is None for a pure add/remove; changed is False only for an "equal"
# row (both sides present and identical).
_DefaultRow = Tuple[Optional[str], Optional[str], bool]

_T = TypeVar("_T")


def _md_bullet_section(title: str, items: List[_T], render_line: Callable[[_T], str], heading_level: int) -> List[str]:
    """
    Render one "<Title> (N)" markdown section as a bulleted list (one line
    per item, via *render_line*), or return an empty list when *items* is
    empty. Shared by the single/multi-target and change/aggregated markdown
    renderers so the Added/Removed/Renamed/Choices sections aren't each
    written out separately per report shape.
    """
    if not items:
        return []
    h = "#" * heading_level
    lines = [f"{h} {title} ({len(items)})\n"]
    lines.extend(render_line(item) for item in items)
    lines.append("")
    return lines


def _emit_bullet_section(
    console: Console, title: str, items: List[_T], style: str, render_line: Callable[[_T], str]
) -> None:
    """
    Print one "<TITLE> (N)" console section as a bulleted list (one line
    per item, via *render_line*), or nothing when *items* is empty. Shared
    by the single/multi-target and change/aggregated console renderers.
    """
    if not items:
        return
    console.rule(f"{title} ({len(items)})", style=style, align="left")
    for item in items:
        console.print(Text(render_line(item), style=style))
    console.print()


def _targets_label(targets: Tuple[str, ...], all_set: Tuple[str, ...], all_label: str = "all") -> str:
    """
    Render an affected-target set as *all_label* (when it covers every compared
    target, and at least two targets were compared) or a comma-separated list
    otherwise.
    """
    if len(all_set) >= 2 and tuple(targets) == all_set:
        return all_label
    return ", ".join(targets)


def _display_choice_id(choice_id: str) -> str:
    """
    If *choice_id* looks like a file:line location (unnamed choice), prefix
    it with a descriptive label. Named choices are returned unchanged.
    """
    if _LOCATION_RE.match(choice_id):
        return f"unnamed choice defined at {choice_id}"
    return choice_id


def _options_suffix_md(options: Tuple[str, ...]) -> str:
    """
    Markdown ``(options: `A`, `B`)`` suffix for a choice's member symbols, or
    the empty string when there are none to show.
    """
    if not options:
        return ""
    return " (options: " + ", ".join(f"`{o}`" for o in options) + ")"


def _options_suffix_plain(options: Tuple[str, ...]) -> str:
    """
    Plain-text ``[options: A, B]`` suffix for console output.
    """
    if not options:
        return ""
    return " [options: " + ", ".join(options) + "]"


def _aligned_default_rows(old_vals: Tuple[str, ...], new_vals: Tuple[str, ...]) -> List[_DefaultRow]:
    """
    Align *old_vals* and *new_vals* (each an ordered list of ``default ...``
    lines) using a sequence diff, so a default inserted/removed in the middle
    of the list doesn't shift every line after it out of alignment.

    Returns one row per line: unchanged lines are paired together, and only
    lines that were actually added, removed, or modified are marked as such.
    """
    matcher = difflib.SequenceMatcher(None, old_vals, new_vals, autojunk=False)
    rows: List[_DefaultRow] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                rows.append((old_vals[i], new_vals[j], False))
        elif tag == "delete":
            for i in range(i1, i2):
                rows.append((old_vals[i], None, True))
        elif tag == "insert":
            for j in range(j1, j2):
                rows.append((None, new_vals[j], True))
        else:  # replace
            old_slice = old_vals[i1:i2]
            new_slice = new_vals[j1:j2]
            for old_line, new_line in zip(old_slice, new_slice):
                rows.append((old_line, new_line, True))
            for old_line in old_slice[len(new_slice) :]:
                rows.append((old_line, None, True))
            for new_line in new_slice[len(old_slice) :]:
                rows.append((None, new_line, True))
    return rows


def _extraction_target_ref(target_group: str, output_file: Optional[str]) -> str:
    """
    Human-readable reference to another codeowner group's report: the actual
    output file when *output_file* (the ``--by-codeowner`` template) is
    known, otherwise just the group name.
    """
    if output_file and output_file != "-":
        stem, ext = os.path.splitext(output_file)
        return f"`{stem}_{_group_slug(target_group)}{ext}`"
    return f"the `{target_group}` codeowner group report"


def _extraction_note_texts(notes: Tuple[ExtractionNote, ...], output_file: Optional[str]) -> Tuple[str, ...]:
    """
    Render each :class:`ExtractionNote` in *notes* as a full sentence.
    """
    return tuple(
        f"Configs from {note.description} are extracted to a standalone report; see "
        f"{_extraction_target_ref(note.target_group, output_file)}."
        for note in notes
    )


def format_json(report: DiffReport) -> str:
    """
    Serialize the ``DiffReport`` as JSON.
    """
    return json.dumps(report.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _md_table_cell(text: str) -> str:
    """
    Escape characters that break GFM/wiki markdown pipe tables.

    Unescaped ``|`` (common in Kconfig ``default ... if A || B`` expressions)
    is treated as a column separator even inside backticks, which makes the
    after column look empty on GitLab wiki and similar renderers.
    """
    return text.replace("|", r"\|")


def _md_default_cell(line: Optional[str], marker: Optional[str] = None) -> str:
    """
    Format one side of a default-change table cell.

    *line* is the ``default ...`` value (without the ``default`` prefix);
    *marker* is used for pure add/remove placeholders such as ``*(new)*``.
    """
    if line is not None:
        text = f"`default {line}`"
    else:
        assert marker is not None
        text = marker
    return _md_table_cell(text)


def _md_default_change_rows(dc: DefaultChange) -> List[Tuple[str, str, str]]:
    """
    Build aligned (before, marker, after) table rows for one default change.

    Each aligned default entry is its own table row so long conditions that
    wrap in the renderer stay paired on the same row instead of drifting
    across ``<br>``-joined lines in a single cell. The marker column carries
    a bold arrow for changed rows: bolding backtick-wrapped code is not
    reliably rendered by every markdown viewer, but bold *plain* text always
    stands out, so that's used as the "this row changed" indicator instead.
    """
    rows: List[Tuple[str, str, str]] = []
    for old_line, new_line, changed in _aligned_default_rows(dc.old_defaults, dc.new_defaults):
        before = _md_default_cell(old_line, "*(new)*" if old_line is None else None)
        after = _md_default_cell(new_line, "*(removed)*" if new_line is None else None)
        marker = "**→**" if changed else ""
        rows.append((before, marker, after))
    return rows


def _append_md_default_table(lines: List[str], dc: DefaultChange) -> None:
    """Append a before/after table for one default change."""
    lines.append("| before | | after |")
    lines.append("| --- | --- | --- |")
    for before, marker, after in _md_default_change_rows(dc):
        lines.append(f"| {before} | {marker} | {after} |")
    lines.append("")


def _md_defaults_section(changes: List[DefaultChange], heading_level: int = 3) -> str:
    """
    Render the "Defaults changed" section for markdown output.

    Each entry gets a "before" / "after" table with the complete, ordered
    default block on each side.
    """
    h = "#" * heading_level
    lines: List[str] = []
    sym_changes = [c for c in changes if c.kind == "symbol"]
    choice_changes = [c for c in changes if c.kind == "choice"]

    if sym_changes:
        lines.append(f"{h} Symbol defaults changed\n")
        for c in sym_changes:
            lines.append(f"**`{c.id}`**\n")
            _append_md_default_table(lines, c)

    if choice_changes:
        lines.append(f"{h} Choice defaults changed\n")
        for c in choice_changes:
            label = _display_choice_id(c.id)
            options = _options_suffix_md(c.new_options or c.old_options)
            lines.append(f"**`{label}`**{options}\n")
            _append_md_default_table(lines, c)

    return "\n".join(lines)


def _choice_bullet_md(report: DiffReport) -> Callable[[str], str]:
    """
    Render-line function for one choice id in a markdown bullet section:
    ``- `id` (options: ...)``.
    """
    return lambda choice_id: (
        f"- `{_display_choice_id(choice_id)}`{_options_suffix_md(report.choice_options.get(choice_id, ()))}"
    )


def _markdown_sections(report: DiffReport, heading_level: int = 2) -> List[str]:
    """
    Build the Added/Removed/Renamed/Choices/Defaults sections for one
    ``DiffReport``, at the given markdown heading level.
    """
    parts: List[str] = []
    parts.extend(_md_bullet_section("Added", report.added, lambda name: f"- `{name}`", heading_level))
    parts.extend(_md_bullet_section("Removed", report.removed, lambda name: f"- `{name}`", heading_level))
    parts.extend(
        _md_bullet_section(
            "Renamed",
            report.renamed,
            lambda r: f"- `{r.old_name}` → `{r.new_name}`{' (inverted)' if r.inverted else ''}",
            heading_level,
        )
    )
    parts.extend(_md_bullet_section("Choices added", report.choices_added, _choice_bullet_md(report), heading_level))
    parts.extend(
        _md_bullet_section("Choices removed", report.choices_removed, _choice_bullet_md(report), heading_level)
    )

    if report.defaults_changed:
        parts.append(_md_defaults_section(report.defaults_changed, heading_level=heading_level + 1))

    return parts


def format_markdown(report: DiffReport) -> str:
    """
    Render the ``DiffReport`` as Markdown.
    """
    parts: List[str] = [
        f"# Kconfig comparison: {report.older_commit} → {report.newer_commit}\n\nTarget: **{report.target}**\n"
    ]
    parts.extend(_markdown_sections(report, heading_level=2))
    return "\n".join(parts)


def _md_preamble(
    older_commit: str,
    newer_commit: str,
    aggregation: str,
    targets_compared: List[str],
    targets_skipped: List[SkippedTarget],
    extraction_note_lines: Tuple[str, ...] = (),
) -> List[str]:
    """
    Build the shared Markdown header (title + aggregation + target universe),
    mirroring the JSON preamble.
    """
    parts: List[str] = [
        f"# Kconfig comparison: {older_commit} → {newer_commit}\n",
        f"- **Aggregation:** {aggregation}",
        f"- **Targets compared:** {', '.join(targets_compared) if targets_compared else '(none)'}",
        "",
    ]
    if targets_skipped:
        parts.append("## Skipped targets\n")
        for s in targets_skipped:
            parts.append(f"- `{s.target}` — present in {s.present_in}, missing from {s.missing_from}")
        parts.append("")
    for line in extraction_note_lines:
        parts.append(f"> {line}")
    if extraction_note_lines:
        parts.append("")
    return parts


def format_markdown_multi(report: MultiTargetDiffReport, output_file: Optional[str] = None) -> str:
    """
    Render a ``MultiTargetDiffReport`` as Markdown: one section per target,
    each with its own Added/Removed/... sub-sections.

    Targets with no differences are omitted (the preamble's
    ``targets_compared`` still lists every target that was compared).
    """
    parts = _md_preamble(
        report.older_commit,
        report.newer_commit,
        "target",
        report.targets_compared,
        report.targets_skipped,
        _extraction_note_texts(report.extraction_notes, output_file),
    )

    for sub in report.reports:
        if sub.is_empty():
            continue
        parts.append(f"## Target: {sub.target}\n")
        parts.extend(_markdown_sections(sub, heading_level=3))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Human (colorized console)
# ---------------------------------------------------------------------------


def _make_console(file: IO[str]) -> Console:
    """
    Build a ``Console`` writing to *file*.

    Color is only used on an actual terminal (Rich's default detection);
    when writing to a pipe/file, a generous fixed width avoids wrapping
    that would otherwise fragment long symbol/expression names.
    """
    is_tty = bool(getattr(file, "isatty", lambda: False)())
    if is_tty:
        return Console(file=file, highlight=False)
    # Rich only honors an explicit width if height is also set (otherwise it
    # falls back to terminal/env detection); fix both so non-tty output
    # (files, captured stdout) isn't wrapped by a stale/absent terminal size.
    return Console(file=file, width=120, height=1000, highlight=False)


def _default_change_rows(dc: DefaultChange) -> List[Tuple[str, str, str, str, bool]]:
    """
    Build one (old_text, old_style, new_text, new_style, changed) tuple per
    aligned default entry.

    Each aligned line becomes its own table row in the caller (rather than
    being crammed into a single multi-line cell), so a long condition that
    word-wraps in the terminal only grows its own row instead of shifting
    every following line out of alignment between the old/new columns.

    Lines are aligned via :func:`_aligned_default_rows` so an insertion or
    removal in the middle of the list doesn't misalign every line after it.
    """
    rows: List[Tuple[str, str, str, str, bool]] = []
    for old_line, new_line, changed in _aligned_default_rows(dc.old_defaults, dc.new_defaults):
        if old_line is not None and new_line is not None:
            if changed:
                rows.append((f"default {old_line}", "bold red", f"default {new_line}", "bold green", True))
            else:
                rows.append((f"default {old_line}", "dim", f"default {new_line}", "dim", False))
        elif old_line is not None:
            rows.append((f"default {old_line}", "bold red", "(removed)", "dim italic", True))
        else:
            assert new_line is not None
            rows.append(("(new)", "dim italic", f"default {new_line}", "bold green", True))
    return rows


def _build_defaults_table(defaults_changed: List[DefaultChange], targets_texts: Optional[List[Text]] = None) -> Table:
    """
    Build the Rich table for a "DEFAULTS CHANGED" section: one row group per
    change, each aligned default line as its own row so a long condition
    that word-wraps in the terminal only grows its own row instead of
    shifting every following line out of alignment between the old/new
    columns.

    When *targets_texts* is given (one entry per item in *defaults_changed*,
    same order), an extra "Targets" column is appended; used by the merged
    (change/aggregated) view, omitted for a single-target report.
    """
    table = Table(box=box.SIMPLE_HEAVY, header_style="bold cyan", pad_edge=False, expand=False)
    table.add_column("Symbol / Choice")
    table.add_column("Kind")
    table.add_column("Old default")
    table.add_column("")
    table.add_column("New default")
    if targets_texts is not None:
        table.add_column("Targets")

    for i, dc in enumerate(defaults_changed):
        if i:
            table.add_row(*([""] * len(table.columns)))
        options = _options_suffix_plain(dc.new_options or dc.old_options) if dc.kind == "choice" else ""
        label = dc.id if dc.kind == "symbol" else f"{_display_choice_id(dc.id)}{options}"
        targets_text = targets_texts[i] if targets_texts is not None else None
        for j, (old_text, old_style, new_text, new_style, changed) in enumerate(_default_change_rows(dc)):
            row = [
                Text(label) if j == 0 else Text(""),
                Text(dc.kind, style="dim") if j == 0 else Text(""),
                Text(old_text, style=old_style),
                Text("→" if changed else "", style="dim"),
                Text(new_text, style=new_style),
            ]
            if targets_text is not None:
                row.append(targets_text if j == 0 else Text(""))
            table.add_row(*row)
    return table


def _choice_bullet_human(report: DiffReport, marker: str) -> Callable[[str], str]:
    """
    Render-line function for one choice id in a console bullet section:
    ``  + id [options: ...]``.
    """
    return lambda choice_id: (
        f"  {marker} {_display_choice_id(choice_id)}{_options_suffix_plain(report.choice_options.get(choice_id, ()))}"
    )


def emit_human(report: DiffReport, console: Console, print_header: bool = True) -> None:
    """
    Render the ``DiffReport`` as colorized console output.

    ``print_header`` can be disabled when the caller (e.g. multi-target
    output) already printed its own title/target heading.
    """
    if print_header:
        console.print(Text(f"Kconfig comparison: {report.older_commit} → {report.newer_commit}", style="bold"))
        console.print(Text(f"Target: {report.target}", style="dim"))
        console.print()

    _emit_bullet_section(console, "ADDED", report.added, "green", lambda name: f"  + {name}")
    _emit_bullet_section(console, "REMOVED", report.removed, "red", lambda name: f"  - {name}")
    _emit_bullet_section(
        console,
        "RENAMED",
        report.renamed,
        "yellow",
        lambda r: f"  {r.old_name} → {r.new_name}{'  (inverted)' if r.inverted else ''}",
    )
    _emit_bullet_section(console, "CHOICES ADDED", report.choices_added, "green", _choice_bullet_human(report, "+"))
    _emit_bullet_section(console, "CHOICES REMOVED", report.choices_removed, "red", _choice_bullet_human(report, "-"))

    if report.defaults_changed:
        console.rule(f"DEFAULTS CHANGED ({len(report.defaults_changed)})", style="cyan", align="left")
        console.print(_build_defaults_table(report.defaults_changed))
        console.print()


def _emit_human_preamble(
    console: Console,
    older_commit: str,
    newer_commit: str,
    aggregation: str,
    targets_compared: List[str],
    targets_skipped: List[SkippedTarget],
    extraction_note_lines: Tuple[str, ...] = (),
) -> None:
    """
    Print the shared console header (title + aggregation + target universe),
    mirroring the JSON preamble.
    """
    compared = ", ".join(targets_compared) if targets_compared else "(none)"
    console.print(Text(f"Kconfig comparison: {older_commit} → {newer_commit}", style="bold"))
    console.print(Text(f"Aggregation: {aggregation}", style="dim"))
    console.print(Text(f"Targets compared: {compared}", style="dim"))
    for s in targets_skipped:
        console.print(
            Text(f"Skipped: {s.target} (present in {s.present_in}, missing from {s.missing_from})", style="yellow")
        )
    for line in extraction_note_lines:
        console.print(Text(f"Note: {line}", style="italic dim"))
    console.print()


def emit_human_multi(report: MultiTargetDiffReport, console: Console, output_file: Optional[str] = None) -> None:
    """
    Render a ``MultiTargetDiffReport`` as colorized console output: one
    labeled section per target.

    Targets with no differences are omitted (the preamble's target list still
    shows every target that was compared).
    """
    _emit_human_preamble(
        console,
        report.older_commit,
        report.newer_commit,
        "target",
        report.targets_compared,
        report.targets_skipped,
        _extraction_note_texts(report.extraction_notes, output_file),
    )

    for sub in report.reports:
        if sub.is_empty():
            continue
        console.rule(f"TARGET: {sub.target}", style="bold blue", align="left")
        console.print()
        emit_human(sub, console, print_header=False)


# ---------------------------------------------------------------------------
# Merged (change / aggregated) views
# ---------------------------------------------------------------------------


def _md_change_line(change: MergedChange, all_set: Tuple[str, ...], show_targets: bool) -> str:
    """
    Render one non-default change as a markdown list item.
    """
    suffix = f" — _{_targets_label(change.affected_targets, all_set, 'all chips')}_" if show_targets else ""
    if change.kind == "added":
        return f"- `{change.name}`{suffix}"
    if change.kind == "removed":
        return f"- `{change.name}`{suffix}"
    if change.kind == "renamed":
        inv = " (inverted)" if change.inverted else ""
        return f"- `{change.old_name}` → `{change.new_name}`{inv}{suffix}"
    # choice_added / choice_removed
    options = _options_suffix_md(change.choice_options)
    return f"- `{_display_choice_id(change.choice_id or '')}`{options}{suffix}"


_CHANGE_KIND_TITLES: Tuple[Tuple[str, str], ...] = (
    ("added", "Added"),
    ("removed", "Removed"),
    ("renamed", "Renamed"),
    ("choice_added", "Choices added"),
    ("choice_removed", "Choices removed"),
)


def _md_change_sections(
    changes: List[MergedChange], all_set: Tuple[str, ...], show_targets: bool, heading_level: int
) -> List[str]:
    """
    Render categorized markdown sections for a list of merged changes.
    """
    h = "#" * heading_level
    parts: List[str] = []
    for kind, title in _CHANGE_KIND_TITLES:
        items = [c for c in changes if c.kind == kind]
        parts.extend(
            _md_bullet_section(title, items, lambda c: _md_change_line(c, all_set, show_targets), heading_level)
        )

    defaults = [c for c in changes if c.kind == "default_changed"]
    if defaults:
        parts.append(f"{h} Defaults changed ({len(defaults)})\n")
        for change in defaults:
            assert change.default is not None
            label = _display_choice_id(change.default.id) if change.default.kind == "choice" else change.default.id
            options = (
                _options_suffix_md(change.default.new_options or change.default.old_options)
                if change.default.kind == "choice"
                else ""
            )
            tlabel = _targets_label(change.affected_targets, all_set, "all chips")
            target_note = f" — _{tlabel}_" if show_targets else ""
            parts.append(f"**`{label}`**{options} ({change.default.kind}){target_note}\n")
            _append_md_default_table(parts, change.default)

    return parts


def format_markdown_merged(report: MergedDiffReport, output_file: Optional[str] = None) -> str:
    """
    Render a ``MergedDiffReport`` as Markdown (change or aggregated view).
    """
    parts = _md_preamble(
        report.older_commit,
        report.newer_commit,
        report.aggregation,
        report.targets_compared,
        report.targets_skipped,
        _extraction_note_texts(report.extraction_notes, output_file),
    )

    all_set = tuple(sorted(report.targets_compared))
    if report.aggregation == "aggregated":
        groups, _all = group_merged_changes(report.changes, report.targets_compared)
        for targets, _is_all, group_changes in groups:
            label = _targets_label(targets, all_set, "all chips")
            parts.append(f"## Targets: {label}\n")
            parts.extend(_md_change_sections(group_changes, all_set, show_targets=False, heading_level=3))
    else:  # change
        parts.extend(_md_change_sections(report.changes, all_set, show_targets=True, heading_level=2))

    return "\n".join(parts)


_CHANGE_KIND_STYLES: Dict[str, Tuple[str, str]] = {
    "added": ("ADDED", "green"),
    "removed": ("REMOVED", "red"),
    "renamed": ("RENAMED", "yellow"),
    "choice_added": ("CHOICES ADDED", "green"),
    "choice_removed": ("CHOICES REMOVED", "red"),
}


def _change_bullet_human(
    kind: str, marker: str, target_suffix: Callable[[MergedChange], str]
) -> Callable[[MergedChange], str]:
    """
    Render-line function for one merged change in a console bullet section.
    """
    if kind in ("added", "removed"):
        return lambda c: f"  {marker} {c.name}{target_suffix(c)}"
    if kind == "renamed":
        return lambda c: f"  {c.old_name} → {c.new_name}{'  (inverted)' if c.inverted else ''}{target_suffix(c)}"
    return lambda c: (
        f"  {marker} {_display_choice_id(c.choice_id or '')}{_options_suffix_plain(c.choice_options)}{target_suffix(c)}"
    )


def _emit_human_change_sections(
    changes: List[MergedChange], console: Console, all_set: Tuple[str, ...], show_targets: bool
) -> None:
    """
    Render categorized colorized console output for a list of merged changes.
    """

    def target_suffix(change: MergedChange) -> str:
        return f"  [{_targets_label(change.affected_targets, all_set)}]" if show_targets else ""

    markers = {"added": "+", "removed": "-", "renamed": "", "choice_added": "+", "choice_removed": "-"}
    for kind, (title, style) in _CHANGE_KIND_STYLES.items():
        items = [c for c in changes if c.kind == kind]
        _emit_bullet_section(console, title, items, style, _change_bullet_human(kind, markers[kind], target_suffix))

    defaults = [c for c in changes if c.kind == "default_changed"]
    if defaults:
        console.rule(f"DEFAULTS CHANGED ({len(defaults)})", style="cyan", align="left")
        dcs: List[DefaultChange] = []
        for change in defaults:
            assert change.default is not None
            dcs.append(change.default)
        targets_texts = (
            [Text(_targets_label(c.affected_targets, all_set), style="blue") for c in defaults]
            if show_targets
            else None
        )
        console.print(_build_defaults_table(dcs, targets_texts))
        console.print()


def emit_human_merged(report: MergedDiffReport, console: Console, output_file: Optional[str] = None) -> None:
    """
    Render a ``MergedDiffReport`` as colorized console output.
    """
    _emit_human_preamble(
        console,
        report.older_commit,
        report.newer_commit,
        report.aggregation,
        report.targets_compared,
        report.targets_skipped,
        _extraction_note_texts(report.extraction_notes, output_file),
    )

    all_set = tuple(sorted(report.targets_compared))
    if report.aggregation == "aggregated":
        groups, _all = group_merged_changes(report.changes, report.targets_compared)
        for targets, _is_all, group_changes in groups:
            label = _targets_label(targets, all_set, "all")
            console.rule(f"TARGETS: {label}", style="bold blue", align="left")
            console.print()
            _emit_human_change_sections(group_changes, console, all_set, show_targets=False)
    else:  # change
        _emit_human_change_sections(report.changes, console, all_set, show_targets=True)


def _write_text(file: IO[str], text: str) -> None:
    file.write(text)
    if not text.endswith("\n"):
        file.write("\n")


# ---------------------------------------------------------------------------
# Codeowner-split output
# ---------------------------------------------------------------------------

_SplitReport = Union[MultiTargetDiffReport, MergedDiffReport]
_PREAMBLE_KEYS = (
    "aggregation",
    "older_commit",
    "older_sha",
    "newer_commit",
    "newer_sha",
    "targets_compared",
    "targets_skipped",
)


def _group_slug(group: str) -> str:
    """
    Filesystem-safe group name for output filenames (``/`` becomes ``_``).
    """
    return group.replace("/", "_")


def _split_json_wrapper(groups: Dict[str, _SplitReport]) -> Dict[str, Any]:
    """
    Wrap per-group reports in a single JSON object: the shared preamble plus a
    ``codeowner_groups`` map of ``group -> full report dict``.
    """
    bodies = {group: report.to_dict() for group, report in groups.items()}
    wrapper: Dict[str, Any] = {}
    first = next(iter(bodies.values()))
    for key in _PREAMBLE_KEYS:
        if key in first:
            wrapper[key] = first[key]
    wrapper["codeowner_groups"] = bodies
    return wrapper


def _group_report_header(group: str) -> str:
    """
    Header line printed above a per-codeowner-group report.

    The synthetic "common" group has no CODEOWNERS entry of its own, so it
    gets an explanatory note spelling out what it actually contains.
    """
    header = f"Report for codeowner group {group}\n"
    if group == COMMON_GROUP_NAME:
        header += "(configs which do not belong to any other codeowner group)\n"
    return header + "\n"


def emit_codeowner_split(groups: Dict[str, _SplitReport], fmt: str, output_file: Optional[str] = None) -> None:
    """
    Emit the per-codeowner-group *groups* in *fmt*.

    When *output_file* is a real path it is treated as a template: each group is
    written to ``<stem>_<group><ext>`` (``/`` in the group replaced by ``_``).
    Otherwise every group report is written to stdout, JSON as one wrapping
    object and human/markdown each prefixed with a group header.
    """
    if output_file and output_file != "-":
        stem, ext = os.path.splitext(output_file)
        for group, report in groups.items():
            path = f"{stem}_{_group_slug(group)}{ext}"
            with open(path, "w", encoding="utf-8") as handle:
                if fmt != "json":
                    handle.write(_group_report_header(group))
                emit_report(report, fmt, file=handle, output_file=output_file)
        return

    if fmt == "json":
        _write_text(sys.stdout, json.dumps(_split_json_wrapper(groups), indent=2))
        return

    for index, (group, report) in enumerate(groups.items()):
        if index:
            sys.stdout.write("\n")
        sys.stdout.write(_group_report_header(group))
        emit_report(report, fmt, file=sys.stdout, output_file=output_file)


def emit_report(
    report: Union[DiffReport, MultiTargetDiffReport, MergedDiffReport],
    fmt: str,
    file: IO[str] = sys.stdout,
    output_file: Optional[str] = None,
) -> None:
    """
    Write ``report`` to ``file`` in the requested format.

    ``fmt`` is one of ``"json"``, ``"markdown"``/``"md"``, or ``"human"``
    (colorized console output). ``report`` may be a single-target
    ``DiffReport``, a per-target ``MultiTargetDiffReport``, or a
    change-oriented ``MergedDiffReport`` (change / aggregated views).
    ``output_file`` is only used to resolve extraction-note references to the
    ``--by-codeowner`` output template (e.g. ``report.md`` -> ``report_soc.md``).
    """
    if type(report) is MergedDiffReport:
        if fmt == "json":
            _write_text(file, json.dumps(report.to_dict(), indent=2))
        elif fmt == "markdown":
            _write_text(file, format_markdown_merged(report, output_file))
        else:
            emit_human_merged(report, _make_console(file), output_file)
        return

    if type(report) is MultiTargetDiffReport:
        if fmt == "json":
            _write_text(file, json.dumps(report.to_dict(), indent=2))
        elif fmt == "markdown":
            _write_text(file, format_markdown_multi(report, output_file))
        else:
            emit_human_multi(report, _make_console(file), output_file)
        return

    assert type(report) is DiffReport
    if fmt == "json":
        _write_text(file, format_json(report))
    elif fmt == "markdown":
        _write_text(file, format_markdown(report))
    else:
        emit_human(report, _make_console(file))
