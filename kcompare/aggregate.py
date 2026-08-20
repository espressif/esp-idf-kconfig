# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Fold a per-target ``MultiTargetDiffReport`` into a change-oriented
``MergedDiffReport`` for the ``change`` and ``aggregated`` views.

Each distinct change is emitted once, annotated with the set of targets it
affects. This is a pure presentation transform; the pipeline always produces
the per-target report and the aggregation is chosen at output time.
"""

from dataclasses import replace
from typing import Any
from typing import Dict
from typing import List
from typing import Set
from typing import Tuple

from .models import MergedChange
from .models import MergedDiffReport
from .models import MultiTargetDiffReport


def merge_report(multi: MultiTargetDiffReport, aggregation: str) -> MergedDiffReport:
    """
    Build a ``MergedDiffReport`` (``aggregation`` is ``"change"`` or
    ``"aggregated"``) from a per-target ``MultiTargetDiffReport``.

    Each ``DiffReport`` contributes its changes via ``iter_changes()``
    (uniform across added/removed/renamed/choices/defaults); changes with
    the same identity (``MergedChange.merge_key()``) across targets are
    folded into one entry with a combined ``affected_targets`` set.
    """
    locations: Dict[str, Set[str]] = {}
    first_seen: Dict[Tuple[Any, ...], MergedChange] = {}
    targets_by_key: Dict[Tuple[Any, ...], Set[str]] = {}

    for report in multi.reports:
        for key, locs in report.locations_by_id.items():
            locations.setdefault(key, set()).update(locs)
        for change in report.iter_changes():
            merge_key = change.merge_key()
            targets_by_key.setdefault(merge_key, set()).update(change.affected_targets)
            first_seen.setdefault(merge_key, change)

    changes: List[MergedChange] = [
        replace(change, affected_targets=tuple(sorted(targets_by_key[merge_key])))
        for merge_key, change in first_seen.items()
    ]
    changes.sort(key=lambda c: c.sort_key())

    return MergedDiffReport(
        older_commit=multi.older_commit,
        older_sha=multi.older_sha,
        newer_commit=multi.newer_commit,
        newer_sha=multi.newer_sha,
        aggregation=aggregation,
        targets_compared=list(multi.targets_compared),
        targets_skipped=list(multi.targets_skipped),
        changes=changes,
        locations_by_id={key: tuple(sorted(locs)) for key, locs in locations.items()},
        codeowners=multi.codeowners,
    )
