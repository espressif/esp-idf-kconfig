# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Curated example lists for the fast and full integration tests (both ESP_IDF build systems).

Single source of truth for which IDF examples are tested and on which targets.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import FrozenSet
from typing import Optional
from typing import Tuple


@dataclass(frozen=True)
class ExampleEntry:
    """
    One IDF example to test.
    """

    path: str
    """Relative to IDF_PATH."""

    fast_targets: Tuple[str, ...] = ()
    """Targets for the fast integration tests.  Empty tuple = not in the fast set."""

    full_targets: Optional[Tuple[str, ...]] = None
    """Targets for the full integration tests.  None = all supported per project README."""

    sdkconfig_ci: Tuple[str, ...] = ()
    """sdkconfig.ci.* variants to build (empty = default config only)."""

    build_system: str = "classic"
    """``"classic"`` or ``"cmakev2"``."""

    safe_to_build: bool = True
    """False for examples that could touch persistent silicon state (e.g. real efuse burns)."""

    tags: FrozenSet[str] = field(default_factory=frozenset)
    """Extra pytest marker tags for CLI selection (e.g. ``-m fast_pre_release``)."""


# ---------------------------------------------------------------------------
# Classic CMake fast integration tests (per-MR)
# ---------------------------------------------------------------------------
FAST_TARGETS: Tuple[str, ...] = ()
"""Default targets for the classic-CMake fast integration tests."""

FAST_EXAMPLES: Tuple[ExampleEntry, ...] = ()
"""Classic-CMake fast integration tests (per-MR). Concrete entries are added in a follow-up MR."""

# ---------------------------------------------------------------------------
# Classic CMake full (manual)
# ---------------------------------------------------------------------------
FULL_EXAMPLES: Tuple[ExampleEntry, ...] = FAST_EXAMPLES
"""Classic-CMake full integration tests, manual (superset of ``FAST_EXAMPLES``)."""

# ---------------------------------------------------------------------------
# cmakev2 fast integration tests (per-MR)
# ---------------------------------------------------------------------------
CMAKEV2_FAST_EXAMPLES: Tuple[ExampleEntry, ...] = ()
"""cmakev2 fast integration tests (per-MR). Concrete entries are added in a follow-up MR."""

# ---------------------------------------------------------------------------
# cmakev2 full (manual)
# ---------------------------------------------------------------------------
CMAKEV2_FULL_EXAMPLES: Tuple[ExampleEntry, ...] = CMAKEV2_FAST_EXAMPLES
"""cmakev2 full integration tests, manual (superset of ``CMAKEV2_FAST_EXAMPLES``)."""
