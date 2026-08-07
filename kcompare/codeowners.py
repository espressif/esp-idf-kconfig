# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Parse an ESP-IDF ``.gitlab/CODEOWNERS`` file and map component paths to
codeowner groups.

Only ``/components...`` rules are considered for ownership: the part after
``/components`` identifies the component (possibly a wildcard) and the groups
are the suffixes after ``@esp-idf-codeowners/`` (nested suffixes such as
``app-utilities/console`` are preserved).

Matching follows GitLab semantics for the subset used by these rules:
patterns are anchored at the repository root, a trailing ``/`` matches the
directory and everything under it, ``*`` matches within a single path segment
and ``**`` matches across segments. When several rules match a path, the last
one wins.

On top of the parsed file, a small hardcoded list of override rows (same
``/components/<path> @group`` shape) takes precedence over it, carving
components that would otherwise be split across several groups into their own
standalone codeowner group (e.g. ``components/soc`` -> ``soc``). Paths that
match neither the overrides nor the file fall back to the synthetic
``COMMON_GROUP_NAME`` group (root ``Kconfig``, components with no CODEOWNERS
entry) instead of being broadcast to every group.
"""

import re
from dataclasses import dataclass
from typing import Dict
from typing import Iterable
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple

_GROUP_PREFIX = "@esp-idf-codeowners/"

# Fallback codeowner group for configs with no CODEOWNERS match at all (the
# root Kconfig, and components the CODEOWNERS file does not mention).
COMMON_GROUP_NAME = "common"

# Hardcoded, CODEOWNERS-formatted override rows that take precedence over the
# parsed CODEOWNERS file (last-match-wins is still used among these rows
# themselves). Add further rows here to carve more components out into their
# own standalone report.
_OVERRIDE_RULES_TEXT = """
/components/soc/    @esp-idf-codeowners/soc
"""

# Human-readable description of what each override/fallback group collects,
# used in the "configs are extracted to a standalone report" note shown in
# the group(s) that would otherwise have owned them.
_EXTRACTION_DESCRIPTIONS: Dict[str, str] = {
    "soc": "components/soc",
    COMMON_GROUP_NAME: "the root Kconfig and components with no CODEOWNERS entry",
}


@dataclass(frozen=True)
class _Rule:
    """
    One CODEOWNERS ``/components`` rule: the raw pattern, a compiled path
    matcher, and the owner groups it assigns.
    """

    pattern: str
    regex: "re.Pattern[str]"
    groups: Tuple[str, ...]


@dataclass(frozen=True)
class Extraction:
    """
    One "configs extracted to a standalone report" relationship: *group*
    holds configs that would otherwise appear in *shadowed_groups* (or every
    other group, when ``None``), described by *description* for the note
    shown in the affected groups' reports.
    """

    group: str
    description: str
    shadowed_groups: Optional[Tuple[str, ...]]


def _translate(pattern: str) -> str:
    """
    Translate a gitignore-style *pattern* (no leading or trailing slash) into a
    regex body where ``*`` stays inside a path segment and ``**`` spans them.
    """
    out: List[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        char = pattern[i]
        if char == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


def _compile(pattern: str) -> "re.Pattern[str]":
    """
    Compile a CODEOWNERS *pattern* into a regex that matches a repo-relative
    path (the directory itself or anything beneath it).
    """
    body = _translate(pattern.strip("/"))
    return re.compile(rf"^{body}(?:/.*)?$")


def _parse_groups(tokens: List[str]) -> Tuple[str, ...]:
    """
    Extract group suffixes from the ``@esp-idf-codeowners/<group>`` owner
    tokens of a rule, preserving order and dropping duplicates.
    """
    groups: List[str] = []
    for token in tokens:
        if token.startswith(_GROUP_PREFIX):
            group = token[len(_GROUP_PREFIX) :]
            if group and group not in groups:
                groups.append(group)
    return tuple(groups)


def _parse_component_rules(text: str) -> List[_Rule]:
    """
    Parse ``/components`` rules from CODEOWNERS-formatted *text* (shared by
    the real CODEOWNERS file and the hardcoded override rows).
    """
    rules: List[_Rule] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith("/components"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern, owners = parts[0], parts[1:]
        groups = _parse_groups(owners)
        if not groups:
            continue
        rules.append(_Rule(pattern=pattern, regex=_compile(pattern), groups=groups))
    return rules


# Compiled once: independent of any particular repo's CODEOWNERS file.
_OVERRIDE_RULES: Tuple[_Rule, ...] = tuple(_parse_component_rules(_OVERRIDE_RULES_TEXT))


def _match(rules: Iterable[_Rule], rel_path: str) -> Optional[Tuple[str, ...]]:
    """
    Last-match-wins lookup of *rel_path* against *rules*.
    """
    matched: Optional[Tuple[str, ...]] = None
    for rule in rules:
        if rule.regex.match(rel_path):
            matched = rule.groups
    return matched


class CodeownersIndex:
    """
    Ownership lookup built from the ``/components`` rules of a CODEOWNERS file
    plus the hardcoded override rows.
    """

    def __init__(self, rules: List[_Rule]) -> None:
        self._rules = rules
        self._override_rules = _OVERRIDE_RULES
        all_groups: List[str] = []
        for rule in rules:
            for group in rule.groups:
                if group not in all_groups:
                    all_groups.append(group)
        self.all_groups: Tuple[str, ...] = tuple(sorted(all_groups))
        self.extractions: Tuple[Extraction, ...] = self._build_extractions()

    def _build_extractions(self) -> Tuple[Extraction, ...]:
        """
        Build the :class:`Extraction` list: one entry per override target
        group (with the groups it draws configs away from, resolved against
        this index's own file rules), plus the built-in ``common`` fallback
        (which draws from every group).
        """
        shadowed_by_group: Dict[str, Set[str]] = {}
        for rule in self._override_rules:
            # Representative path for this override pattern, resolved
            # against the *file* rules only, to find which groups it would
            # otherwise have belonged to.
            probe = rule.pattern.strip("/")
            shadowed = _match(self._rules, probe) or ()
            for group in rule.groups:
                shadowed_by_group.setdefault(group, set()).update(shadowed)

        extractions = [
            Extraction(
                group=group,
                description=_EXTRACTION_DESCRIPTIONS.get(group, group),
                shadowed_groups=tuple(sorted(shadowed)),
            )
            for group, shadowed in sorted(shadowed_by_group.items())
        ]
        extractions.append(
            Extraction(
                group=COMMON_GROUP_NAME,
                description=_EXTRACTION_DESCRIPTIONS[COMMON_GROUP_NAME],
                shadowed_groups=None,
            )
        )
        return tuple(extractions)

    @property
    def component_rule_count(self) -> int:
        """
        Number of parsed ``/components`` ownership rules in this index.
        """
        return len(self._rules)

    def groups_for_path(self, rel_path: str) -> Optional[Tuple[str, ...]]:
        """
        Return the owner groups for a repo-relative *rel_path* (no ``:line``
        suffix). Hardcoded override rows take precedence over the parsed
        CODEOWNERS file; within each set, last-match-wins. Returns ``None``
        when neither the overrides nor the file match (the caller should
        fall back to :data:`COMMON_GROUP_NAME`).
        """
        override = _match(self._override_rules, rel_path)
        if override is not None:
            return override
        return _match(self._rules, rel_path)


def parse_codeowners_text(text: str) -> CodeownersIndex:
    """
    Parse CODEOWNERS contents from *text* and return a :class:`CodeownersIndex`
    built from its ``/components`` rules.
    """
    return CodeownersIndex(_parse_component_rules(text))


def parse_codeowners(path: str) -> CodeownersIndex:
    """
    Parse the CODEOWNERS file at *path* and return a :class:`CodeownersIndex`
    built from its ``/components`` rules.
    """
    with open(path, encoding="utf-8") as handle:
        return parse_codeowners_text(handle.read())
