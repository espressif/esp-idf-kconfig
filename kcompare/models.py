# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Internal representation of Kconfig snapshots and comparison results.

Designed so reporters can emit human, JSON, or markdown from the same objects.
"""

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple

if TYPE_CHECKING:
    from .codeowners import CodeownersIndex


@dataclass(frozen=True)
class SymbolSnapshot:
    """
    Structural snapshot of one config symbol (non-choice-member).
    """

    name: str
    # Ordered default definitions as strings, e.g. "y if FOO"
    defaults: Tuple[str, ...]
    # Definition locations ("file:line" relative to IDF root); one per node.
    locations: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ChoiceSnapshot:
    """
    Structural snapshot of one choice (named or anonymous).
    """

    id: str  # name, or "file:line" relative to IDF root
    name: Optional[str]
    # Definition locations ("file:line" relative to IDF root); one per node.
    locations: Tuple[str, ...]
    # Ordered default definitions as strings
    defaults: Tuple[str, ...]
    # Symbol names appearing as default targets (same order as defaults)
    default_symbol_names: Tuple[str, ...]
    # Names of the choice's member config options
    options: Tuple[str, ...] = ()


@dataclass
class ConfigurationSnapshot:
    """
    Full configuration snapshot for one commit + target.
    """

    commit: str
    commit_sha: str
    target: str
    symbols: Dict[str, SymbolSnapshot] = field(default_factory=dict)
    choices: Dict[str, ChoiceSnapshot] = field(default_factory=dict)
    # deprecated -> (new_name, inverted)
    renames: Dict[str, Tuple[str, bool]] = field(default_factory=dict)


@dataclass(frozen=True)
class RenamedEntry:
    old_name: str
    new_name: str
    inverted: bool


@dataclass(frozen=True)
class DefaultChange:
    id: str  # symbol name or choice id
    kind: str  # "symbol" | "choice"
    old_defaults: Tuple[str, ...]
    new_defaults: Tuple[str, ...]
    # For choices: default target symbol names on each side
    old_default_symbols: Tuple[str, ...] = ()
    new_default_symbols: Tuple[str, ...] = ()
    # For choices: the choice's member option names on each side
    old_options: Tuple[str, ...] = ()
    new_options: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionNote:
    """
    Note attached to a codeowner-group report explaining that some configs it
    would otherwise show are extracted into another group's standalone
    report (see :class:`kcompare.codeowners.Extraction`).
    """

    description: str
    target_group: str


def _choice_ref_dict(choice_id: str, choice_options: Dict[str, Tuple[str, ...]]) -> Dict[str, Any]:
    """
    Serialize a choices_added/choices_removed entry as ``{"id", "options"}``.
    """
    return {"id": choice_id, "options": list(choice_options.get(choice_id, ()))}


@dataclass
class DiffReport:
    """
    Comparison result: older → newer.
    """

    older_commit: str
    older_sha: str
    newer_commit: str
    newer_sha: str
    target: str
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    renamed: List[RenamedEntry] = field(default_factory=list)
    defaults_changed: List[DefaultChange] = field(default_factory=list)
    # Choice-level adds/removes (by id)
    choices_added: List[str] = field(default_factory=list)
    choices_removed: List[str] = field(default_factory=list)
    # Member option names for each id in choices_added/choices_removed.
    choice_options: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    # Definition locations per symbol name / choice id (union of both sides).
    # Used only by the codeowner split; never serialized into the JSON contract.
    locations_by_id: Dict[str, Tuple[str, ...]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        JSON-serializable single-target report body (the ``target`` view entry).

        The commit refs/SHAs are intentionally omitted here: they belong to the
        enclosing report's preamble, not to each per-target entry.
        """
        return {
            "target": self.target,
            "added": list(self.added),
            "removed": list(self.removed),
            "renamed": [_renamed_dict(r) for r in self.renamed],
            "defaults_changed": [_default_dict(c) for c in self.defaults_changed],
            "choices_added": [_choice_ref_dict(c, self.choice_options) for c in self.choices_added],
            "choices_removed": [_choice_ref_dict(c, self.choice_options) for c in self.choices_removed],
        }

    def is_empty(self) -> bool:
        """
        True when the report contains no differences.
        """
        return not (
            self.added
            or self.removed
            or self.renamed
            or self.defaults_changed
            or self.choices_added
            or self.choices_removed
        )

    def iter_changes(self) -> List["MergedChange"]:
        """
        All changes in this report as a uniform list of ``MergedChange``,
        each tagged with this report's single target.

        Lets callers that need to walk every change generically (merging
        across per-target reports, codeowner attribution, ...) use one loop
        instead of repeating the six-bucket walk (``added``, ``removed``,
        ``renamed``, ``choices_added``, ``choices_removed``,
        ``defaults_changed``) by hand.
        """
        targets = (self.target,)
        changes: List[MergedChange] = []
        for name in self.added:
            changes.append(MergedChange(kind="added", affected_targets=targets, name=name))
        for name in self.removed:
            changes.append(MergedChange(kind="removed", affected_targets=targets, name=name))
        for r in self.renamed:
            changes.append(
                MergedChange(
                    kind="renamed",
                    affected_targets=targets,
                    old_name=r.old_name,
                    new_name=r.new_name,
                    inverted=r.inverted,
                )
            )
        for choice_id in self.choices_added:
            changes.append(
                MergedChange(
                    kind="choice_added",
                    affected_targets=targets,
                    choice_id=choice_id,
                    choice_options=self.choice_options.get(choice_id, ()),
                )
            )
        for choice_id in self.choices_removed:
            changes.append(
                MergedChange(
                    kind="choice_removed",
                    affected_targets=targets,
                    choice_id=choice_id,
                    choice_options=self.choice_options.get(choice_id, ()),
                )
            )
        for dc in self.defaults_changed:
            changes.append(MergedChange(kind="default_changed", affected_targets=targets, default=dc))
        return changes


@dataclass(frozen=True)
class SkippedTarget:
    """
    Machine-readable record of a target that was not compared because it is
    present in only one of the two commits.
    """

    target: str
    present_in: str  # commit ref where the target exists
    missing_from: str  # commit ref where the target is absent


@dataclass
class MultiTargetDiffReport:
    """
    Per-target DiffReports for a commit comparison across one or more targets,
    plus the target universe and structured information about targets skipped
    because they were not present on both sides.

    Single-target runs use this same shape with a one-element ``reports`` list,
    so the emitted JSON contract is uniform regardless of ``-t``.
    """

    older_commit: str
    older_sha: str
    newer_commit: str
    newer_sha: str
    # Targets actually compared (present in both commits).
    targets_compared: List[str] = field(default_factory=list)
    # Structured skip records (the full target universe is
    # ``targets_compared`` plus these).
    targets_skipped: List[SkippedTarget] = field(default_factory=list)
    reports: List[DiffReport] = field(default_factory=list)
    # Ownership index parsed from the newer worktree's CODEOWNERS; only set when
    # the codeowner split is requested. Not serialized.
    codeowners: Optional["CodeownersIndex"] = None
    # Codeowner group this report was filtered to (set on split sub-reports).
    codeowner_group: Optional[str] = None
    # Notes about configs extracted into another group's standalone report
    # (set on split sub-reports; see kcompare.split_codeowners).
    extraction_notes: Tuple[ExtractionNote, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        """
        JSON-serializable dict.
        """
        data: Dict[str, Any] = {
            "aggregation": "target",
            "older_commit": self.older_commit,
            "older_sha": self.older_sha,
            "newer_commit": self.newer_commit,
            "newer_sha": self.newer_sha,
        }
        if self.codeowner_group is not None:
            data["codeowner_group"] = self.codeowner_group
        if self.extraction_notes:
            data["extraction_notes"] = [_extraction_note_dict(n) for n in self.extraction_notes]
        data["targets_compared"] = list(self.targets_compared)
        data["targets_skipped"] = [asdict(s) for s in self.targets_skipped]
        # Omit empty per-target bodies: targets_compared still lists everything
        # that was compared, but reports only carries targets with differences.
        data["reports"] = [r.to_dict() for r in self.reports if not r.is_empty()]
        return data


# Change "kinds" used by the change/aggregated views, in display order.
_KIND_ORDER = {
    "added": 0,
    "removed": 1,
    "renamed": 2,
    "choice_added": 3,
    "choice_removed": 4,
    "default_changed": 5,
}


@dataclass(frozen=True)
class MergedChange:
    """
    One change (of any kind) together with the set of targets it affects.

    A single kind-tagged type keeps the change/aggregated views easy to
    iterate and filter. Only the fields relevant to ``kind`` are populated.
    """

    kind: str  # one of _KIND_ORDER
    affected_targets: Tuple[str, ...]  # sorted, subset of targets_compared
    name: Optional[str] = None  # added / removed
    old_name: Optional[str] = None  # renamed
    new_name: Optional[str] = None  # renamed
    inverted: bool = False  # renamed
    choice_id: Optional[str] = None  # choice_added / choice_removed
    choice_options: Tuple[str, ...] = ()  # choice_added / choice_removed
    default: Optional[DefaultChange] = None  # default_changed

    def sort_key(self) -> Tuple[int, Tuple[str, ...]]:
        """
        Deterministic ordering key: by kind, then by identity.
        """
        if self.kind in ("added", "removed"):
            ident: Tuple[str, ...] = (self.name or "",)
        elif self.kind == "renamed":
            ident = (self.old_name or "", self.new_name or "")
        elif self.kind in ("choice_added", "choice_removed"):
            ident = (self.choice_id or "",)
        else:  # default_changed
            assert self.default is not None
            ident = (self.default.kind, self.default.id)
        return (_KIND_ORDER[self.kind], ident)

    def merge_key(self) -> Tuple[Any, ...]:
        """
        Identity used to merge the same change reported for several targets
        into one entry with a combined ``affected_targets`` set.
        """
        if self.kind in ("added", "removed"):
            return (self.kind, self.name)
        if self.kind == "renamed":
            return (self.kind, self.old_name, self.new_name, self.inverted)
        if self.kind in ("choice_added", "choice_removed"):
            return (self.kind, self.choice_id)
        assert self.default is not None
        return (self.kind, self.default)


def _renamed_dict(r: RenamedEntry) -> Dict[str, Any]:
    """
    Serialize a rename (identity fields only; no target set).
    """
    return {"old_name": r.old_name, "new_name": r.new_name, "inverted": r.inverted}


def _default_dict(dc: DefaultChange) -> Dict[str, Any]:
    """
    Serialize a default change (identity ``id`` + ``kind`` + before/after
    defaults), matching the original single-target report shape.
    """
    return {
        "id": dc.id,
        "kind": dc.kind,
        "old_defaults": list(dc.old_defaults),
        "new_defaults": list(dc.new_defaults),
        "old_default_symbols": list(dc.old_default_symbols),
        "new_default_symbols": list(dc.new_default_symbols),
        "old_options": list(dc.old_options),
        "new_options": list(dc.new_options),
    }


def _extraction_note_dict(note: ExtractionNote) -> Dict[str, Any]:
    """
    Serialize an :class:`ExtractionNote`.
    """
    return {"description": note.description, "target_group": note.target_group}


def _changeset_dict(changes: List[MergedChange], all_set: Optional[Set[str]] = None) -> Dict[str, Any]:
    """
    Build a report body (same buckets as ``DiffReport.to_dict``) from a list
    of ``MergedChange``.

    When *all_set* is ``None`` (the aggregated view, where the target set is
    already the group key), ``added``/``removed`` stay plain name lists and
    no ``targets_affected`` field is added, matching ``DiffReport.to_dict``.
    When *all_set* is given (the change view's full compared-target set,
    possibly empty), every item also gets a ``targets_affected`` field,
    collapsed to the sentinel ``["all"]`` when it equals *all_set* exactly.
    """
    annotate = all_set is not None

    def targets_affected(c: MergedChange) -> List[str]:
        if all_set and set(c.affected_targets) == all_set:
            return ["all"]
        return list(c.affected_targets)

    added: List[Any] = []
    removed: List[Any] = []
    renamed: List[Dict[str, Any]] = []
    choices_added: List[Dict[str, Any]] = []
    choices_removed: List[Dict[str, Any]] = []
    defaults_changed: List[Dict[str, Any]] = []
    for c in changes:
        if c.kind == "added":
            added.append({"name": c.name, "targets_affected": targets_affected(c)} if annotate else c.name)
        elif c.kind == "removed":
            removed.append({"name": c.name, "targets_affected": targets_affected(c)} if annotate else c.name)
        elif c.kind == "renamed":
            entry: Dict[str, Any] = {"old_name": c.old_name, "new_name": c.new_name, "inverted": c.inverted}
            if annotate:
                entry["targets_affected"] = targets_affected(c)
            renamed.append(entry)
        elif c.kind in ("choice_added", "choice_removed"):
            entry = {"id": c.choice_id, "options": list(c.choice_options)}
            if annotate:
                entry["targets_affected"] = targets_affected(c)
            (choices_added if c.kind == "choice_added" else choices_removed).append(entry)
        else:  # default_changed
            assert c.default is not None
            entry = _default_dict(c.default)
            if annotate:
                entry["targets_affected"] = targets_affected(c)
            defaults_changed.append(entry)
    return {
        "added": added,
        "removed": removed,
        "renamed": renamed,
        "defaults_changed": defaults_changed,
        "choices_added": choices_added,
        "choices_removed": choices_removed,
    }


def group_merged_changes(
    changes: List[MergedChange], targets_compared: List[str]
) -> Tuple[List[Tuple[Tuple[str, ...], bool, List[MergedChange]]], Tuple[str, ...]]:
    """
    Group *changes* by their exact ``affected_targets`` set.

    Returns ``(groups, all_set)`` where each group is
    ``(targets, is_all, changes)``. The "all" group (changes affecting every
    compared target) is listed first, then broader sets before narrower ones,
    then lexicographically. Empty combinations are naturally absent.
    """
    all_set = tuple(sorted(targets_compared))
    buckets: Dict[Tuple[str, ...], List[MergedChange]] = {}
    for change in changes:
        buckets.setdefault(change.affected_targets, []).append(change)

    def order_key(item: Tuple[Tuple[str, ...], List[MergedChange]]) -> Tuple[int, int, Tuple[str, ...]]:
        targets, _ = item
        is_all = targets == all_set
        return (0 if is_all else 1, -len(targets), targets)

    groups: List[Tuple[Tuple[str, ...], bool, List[MergedChange]]] = []
    for targets, group_changes in sorted(buckets.items(), key=order_key):
        group_changes.sort(key=lambda c: c.sort_key())
        groups.append((targets, targets == all_set, group_changes))
    return groups, all_set


@dataclass
class MergedDiffReport:
    """
    Change-oriented view of a comparison, used for both the ``change`` and
    ``aggregated`` aggregations. ``changes`` holds every distinct change once,
    annotated with the targets it affects; the aggregation only changes how
    they are rendered/serialized.
    """

    older_commit: str
    older_sha: str
    newer_commit: str
    newer_sha: str
    aggregation: str  # "change" | "aggregated"
    targets_compared: List[str] = field(default_factory=list)
    targets_skipped: List[SkippedTarget] = field(default_factory=list)
    changes: List[MergedChange] = field(default_factory=list)
    # Definition locations per symbol name / choice id (union across targets).
    # Used only by the codeowner split; never serialized into the JSON contract.
    locations_by_id: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    # Ownership index parsed from the newer worktree's CODEOWNERS; only set when
    # the codeowner split is requested. Not serialized.
    codeowners: Optional["CodeownersIndex"] = None
    # Codeowner group this report was filtered to (set on split sub-reports).
    codeowner_group: Optional[str] = None
    # Notes about configs extracted into another group's standalone report
    # (set on split sub-reports; see kcompare.split_codeowners).
    extraction_notes: Tuple[ExtractionNote, ...] = ()

    def _preamble(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "aggregation": self.aggregation,
            "older_commit": self.older_commit,
            "older_sha": self.older_sha,
            "newer_commit": self.newer_commit,
            "newer_sha": self.newer_sha,
        }
        if self.codeowner_group is not None:
            data["codeowner_group"] = self.codeowner_group
        if self.extraction_notes:
            data["extraction_notes"] = [_extraction_note_dict(n) for n in self.extraction_notes]
        data["targets_compared"] = list(self.targets_compared)
        data["targets_skipped"] = [asdict(s) for s in self.targets_skipped]
        return data

    def to_dict(self) -> Dict[str, Any]:
        """
        JSON-serializable dict; shape depends on ``aggregation``.
        """
        data = self._preamble()
        if self.aggregation == "aggregated":
            groups, _all_set = group_merged_changes(self.changes, self.targets_compared)
            fold_all = len(self.targets_compared) >= 2
            data["reports"] = [
                {
                    "targets": ["all"] if (is_all and fold_all) else list(targets),
                    **_changeset_dict(group_changes),
                }
                for targets, is_all, group_changes in groups
            ]
        else:  # change
            all_set = set(self.targets_compared) if len(self.targets_compared) >= 2 else set()
            data["reports"] = _changeset_dict(self.changes, all_set)
        return data
