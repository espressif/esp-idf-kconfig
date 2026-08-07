# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Split a comparison report into per-codeowner-group reports.

Each change (symbol/choice add/remove/rename/default) is attributed to the
codeowner groups that own the component it is defined in, resolved from the
definition locations captured in the snapshots (hardcoded overrides such as
``components/soc`` take precedence over the CODEOWNERS file; see
``codeowners.py``). A change whose location matches neither an override nor
the CODEOWNERS file (for example a symbol defined in the root ``Kconfig``) is
attributed to the synthetic :data:`COMMON_GROUP_NAME` group instead.

Groups that lose configs to another standalone group this way (an override
target, or ``common``) get an :class:`~kcompare.models.ExtractionNote`
pointing to that group's report.
"""

from typing import Dict
from typing import FrozenSet
from typing import Iterable
from typing import List
from typing import Set
from typing import Tuple
from typing import Union

from .codeowners import COMMON_GROUP_NAME
from .codeowners import CodeownersIndex
from .models import DiffReport
from .models import ExtractionNote
from .models import MergedChange
from .models import MergedDiffReport
from .models import MultiTargetDiffReport

SplitReport = Union[MultiTargetDiffReport, MergedDiffReport]


def _path_of(location: str) -> str:
    """
    Strip the ``:line`` suffix from a ``file:line`` location.
    """
    return location.rsplit(":", 1)[0] if ":" in location else location


def _owners_for_locations(locations: Iterable[str], index: CodeownersIndex) -> Set[str]:
    """
    Union of owner groups for *locations*, falling back to
    :data:`COMMON_GROUP_NAME` for any location (or the absence of one) that
    matches neither the overrides nor the CODEOWNERS file.
    """
    locations = list(locations)
    if not locations:
        return {COMMON_GROUP_NAME}
    owners: Set[str] = set()
    for location in locations:
        groups = index.groups_for_path(_path_of(location))
        owners.update(groups if groups is not None else (COMMON_GROUP_NAME,))
    return owners


def _groups_for_ids(
    ids: Iterable[str], locations_by_id: Dict[str, Tuple[str, ...]], index: CodeownersIndex
) -> FrozenSet[str]:
    """
    Resolve the codeowner groups a change belongs to, combining the locations
    of all its *ids* (e.g. both sides of a rename).
    """
    locations: Set[str] = set()
    for identifier in ids:
        locations.update(locations_by_id.get(identifier, ()))
    return frozenset(_owners_for_locations(locations, index))


def _merged_change_ids(change: MergedChange) -> Tuple[str, ...]:
    """
    Identifiers used to look up a merged change's definition locations.
    """
    if change.kind in ("added", "removed"):
        return (change.name or "",)
    if change.kind == "renamed":
        return (change.old_name or "", change.new_name or "")
    if change.kind in ("choice_added", "choice_removed"):
        return (change.choice_id or "",)
    assert change.default is not None
    return (change.default.id,)


def _filter_diffreport(sub: DiffReport, index: CodeownersIndex, group: str) -> DiffReport:
    """
    Return a copy of *sub* keeping only the changes owned by *group*.
    """
    locations = sub.locations_by_id

    def keep(*ids: str) -> bool:
        return group in _groups_for_ids(ids, locations, index)

    return DiffReport(
        older_commit=sub.older_commit,
        older_sha=sub.older_sha,
        newer_commit=sub.newer_commit,
        newer_sha=sub.newer_sha,
        target=sub.target,
        added=[n for n in sub.added if keep(n)],
        removed=[n for n in sub.removed if keep(n)],
        renamed=[r for r in sub.renamed if keep(r.old_name, r.new_name)],
        defaults_changed=[d for d in sub.defaults_changed if keep(d.id)],
        choices_added=[c for c in sub.choices_added if keep(c)],
        choices_removed=[c for c in sub.choices_removed if keep(c)],
        choice_options=dict(sub.choice_options),
    )


def _all_groups_in_diffreport(sub: DiffReport, index: CodeownersIndex) -> Set[str]:
    """
    Every codeowner group that at least one change in *sub* belongs to.
    """
    locations = sub.locations_by_id
    groups: Set[str] = set()
    for change in sub.iter_changes():
        groups |= _groups_for_ids(_merged_change_ids(change), locations, index)
    return groups


def _extraction_notes_for(group_names: Set[str], index: CodeownersIndex) -> Dict[str, Tuple[ExtractionNote, ...]]:
    """
    For every group in *group_names* that would otherwise have received
    configs now diverted to a standalone extraction group (an override
    target, or ``common``), build the note pointing to that group's report.
    """
    notes: Dict[str, List[ExtractionNote]] = {}
    for extraction in index.extractions:
        if extraction.group not in group_names:
            continue
        if extraction.shadowed_groups is None:
            targets = group_names - {extraction.group}
        else:
            targets = (set(extraction.shadowed_groups) & group_names) - {extraction.group}
        note = ExtractionNote(description=extraction.description, target_group=extraction.group)
        for target in targets:
            notes.setdefault(target, []).append(note)
    return {group: tuple(items) for group, items in notes.items()}


def _split_multi(report: MultiTargetDiffReport, index: CodeownersIndex) -> Dict[str, MultiTargetDiffReport]:
    """
    Split a per-target ``MultiTargetDiffReport`` by codeowner group.
    """
    group_names: Set[str] = set()
    for sub in report.reports:
        group_names |= _all_groups_in_diffreport(sub, index)
    notes = _extraction_notes_for(group_names, index)

    result: Dict[str, MultiTargetDiffReport] = {}
    for group in sorted(group_names):
        sub_reports = [_filter_diffreport(sub, index, group) for sub in report.reports]
        sub_reports = [sub for sub in sub_reports if not sub.is_empty()]
        result[group] = MultiTargetDiffReport(
            older_commit=report.older_commit,
            older_sha=report.older_sha,
            newer_commit=report.newer_commit,
            newer_sha=report.newer_sha,
            targets_compared=list(report.targets_compared),
            targets_skipped=list(report.targets_skipped),
            reports=sub_reports,
            codeowner_group=group,
            extraction_notes=notes.get(group, ()),
        )
    return result


def _split_merged(report: MergedDiffReport, index: CodeownersIndex) -> Dict[str, MergedDiffReport]:
    """
    Split a change-oriented ``MergedDiffReport`` by codeowner group.
    """
    locations = report.locations_by_id
    change_groups = [
        (change, _groups_for_ids(_merged_change_ids(change), locations, index)) for change in report.changes
    ]

    group_names: Set[str] = set()
    for _change, groups in change_groups:
        group_names |= groups
    notes = _extraction_notes_for(group_names, index)

    result: Dict[str, MergedDiffReport] = {}
    for group in sorted(group_names):
        changes = [change for change, groups in change_groups if group in groups]
        result[group] = MergedDiffReport(
            older_commit=report.older_commit,
            older_sha=report.older_sha,
            newer_commit=report.newer_commit,
            newer_sha=report.newer_sha,
            aggregation=report.aggregation,
            targets_compared=list(report.targets_compared),
            targets_skipped=list(report.targets_skipped),
            changes=changes,
            codeowner_group=group,
            extraction_notes=notes.get(group, ()),
        )
    return result


def split_by_codeowner(report: SplitReport, index: CodeownersIndex) -> Dict[str, SplitReport]:
    """
    Split *report* into ``{group_name: report}`` by codeowner group.

    *report* is either a ``MultiTargetDiffReport`` (``target`` aggregation) or a
    ``MergedDiffReport`` (``change`` / ``aggregated``). Only groups with at
    least one change are returned; the result preserves group-name ordering.
    """
    if type(report) is MultiTargetDiffReport:
        return dict(_split_multi(report, index))
    if type(report) is MergedDiffReport:
        return dict(_split_merged(report, index))
    raise TypeError(f"cannot split report of type {type(report).__name__}")
