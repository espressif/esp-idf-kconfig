# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Compare two ConfigurationSnapshots (older → newer).
"""

from typing import Dict
from typing import List
from typing import Set
from typing import Tuple

from .models import ConfigurationSnapshot
from .models import DefaultChange
from .models import DiffReport
from .models import RenamedEntry


def _locations_by_id(older: ConfigurationSnapshot, newer: ConfigurationSnapshot) -> Dict[str, Tuple[str, ...]]:
    """
    Map each symbol name / choice id to the union of its definition locations
    across both snapshots. Used by the codeowner split to resolve ownership;
    keyed identically to the diff buckets (symbol names and choice ids).
    """
    locations: Dict[str, Tuple[str, ...]] = {}
    for name in set(older.symbols) | set(newer.symbols):
        merged: Set[str] = set()
        if name in older.symbols:
            merged.update(older.symbols[name].locations)
        if name in newer.symbols:
            merged.update(newer.symbols[name].locations)
        locations[name] = tuple(sorted(merged))
    for choice_id in set(older.choices) | set(newer.choices):
        merged = set()
        if choice_id in older.choices:
            merged.update(older.choices[choice_id].locations)
        if choice_id in newer.choices:
            merged.update(newer.choices[choice_id].locations)
        locations[choice_id] = tuple(sorted(merged))
    return locations


def compare_snapshots(older: ConfigurationSnapshot, newer: ConfigurationSnapshot) -> DiffReport:
    """
    Compare two ConfigurationSnapshots (older → newer).
    Returns a DiffReport containing the differences between the two snapshots.
    """
    report = DiffReport(
        older_commit=older.commit,
        older_sha=older.commit_sha,
        newer_commit=newer.commit,
        newer_sha=newer.commit_sha,
        target=newer.target,
        locations_by_id=_locations_by_id(older, newer),
    )

    ##########
    # Symbols
    ##########

    # Added and removed symbols
    old_names: Set[str] = set(older.symbols)
    new_names: Set[str] = set(newer.symbols)
    added = sorted(new_names - old_names)
    removed = sorted(old_names - new_names)

    # Renamed symbols
    # If symbol is removed, also remove it from added/removed lists
    renamed_old: Set[str] = set()
    renamed_new: Set[str] = set()
    renamed_entries: List[RenamedEntry] = []

    for old_name in removed:
        mapping = newer.renames.get(old_name)
        if not mapping:
            continue
        new_name, inverted = mapping
        if new_name in added:
            renamed_entries.append(RenamedEntry(old_name=old_name, new_name=new_name, inverted=inverted))
            renamed_old.add(old_name)
            renamed_new.add(new_name)

    report.renamed = sorted(renamed_entries, key=lambda e: (e.old_name, e.new_name))
    report.added = [n for n in added if n not in renamed_new]
    report.removed = [n for n in removed if n not in renamed_old]

    # Defaults changed
    for name in sorted(old_names & new_names):
        old_sym = older.symbols[name]
        new_sym = newer.symbols[name]
        if old_sym.defaults != new_sym.defaults:
            report.defaults_changed.append(
                DefaultChange(
                    id=name,
                    kind="symbol",
                    old_defaults=old_sym.defaults,
                    new_defaults=new_sym.defaults,
                )
            )

    ##########
    # Choices
    ##########

    # Added and removed choices
    old_choice_ids = set(older.choices)
    new_choice_ids = set(newer.choices)
    report.choices_added = sorted(new_choice_ids - old_choice_ids)
    report.choices_removed = sorted(old_choice_ids - new_choice_ids)
    for choice_id in report.choices_added:
        report.choice_options[choice_id] = newer.choices[choice_id].options
    for choice_id in report.choices_removed:
        report.choice_options[choice_id] = older.choices[choice_id].options

    # Defaults changed
    for choice_id in sorted(old_choice_ids & new_choice_ids):
        old_ch = older.choices[choice_id]
        new_ch = newer.choices[choice_id]
        if old_ch.defaults != new_ch.defaults:
            report.defaults_changed.append(
                DefaultChange(
                    id=choice_id,
                    kind="choice",
                    old_defaults=old_ch.defaults,
                    new_defaults=new_ch.defaults,
                    old_default_symbols=old_ch.default_symbol_names,
                    new_default_symbols=new_ch.default_symbol_names,
                    old_options=old_ch.options,
                    new_options=new_ch.options,
                )
            )

    report.defaults_changed.sort(key=lambda c: (c.kind, c.id))
    return report
