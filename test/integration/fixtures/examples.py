# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Curated example lists for the fast and full integration tests (both ESP-IDF build systems).

NOTE: Full integration tests are not yet implemented for neither build system.
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
# Curated list of primary targets to test:
# * esp32: staple chip
# * esp32c6: BT, LP core...
# * esp32p4: most problematic due to second chip for WiFi etc.
FAST_TARGETS: Tuple[str, ...] = ("esp32", "esp32c6", "esp32p4")

FAST_EXAMPLES: Tuple[ExampleEntry, ...] = (
    ExampleEntry(
        path="examples/get-started/hello_world",  # baseline
        fast_targets=("esp32",),
    ),
    ExampleEntry(
        path="examples/get-started/blink",  # baseline, but with components
        fast_targets=FAST_TARGETS,
    ),
    ExampleEntry(
        path="examples/openthread/ot_br",  # repeated regressions in this project
        fast_targets=("esp32c6",),  # doesn't really matter, problems weren't chip specific
    ),
    ExampleEntry(
        path="examples/system/ulp/lp_core/build_system",  # LP core test
        fast_targets=("esp32c6",),
    ),
    ExampleEntry(
        path="examples/wifi/getting_started/softAP",  # WiFi test
        fast_targets=FAST_TARGETS,
    ),
    ExampleEntry(
        path="examples/bluetooth/nimble/bleprph",
        fast_targets=("esp32", "esp32c6"),  # esp32p4 is not supported
    ),
)


# ---------------------------------------------------------------------------
# cmakev2 fast integration tests (per-MR)
# ---------------------------------------------------------------------------
CMAKEV2_FAST_EXAMPLES: Tuple[ExampleEntry, ...] = (
    ExampleEntry(
        path="examples/build_system/cmakev2/get-started/hello_world",
        fast_targets=("esp32",),
        build_system="cmakev2",
    ),
    ExampleEntry(
        path="examples/build_system/cmakev2/features/conditional_component",
        fast_targets=FAST_TARGETS,
        build_system="cmakev2",
    ),
    ExampleEntry(
        path="examples/build_system/cmakev2/features/multi_config",
        fast_targets=FAST_TARGETS,
        build_system="cmakev2",
    ),
)


# ---------------------------------------------------------------------------
# Classic CMake full (manual)
# ---------------------------------------------------------------------------
FULL_EXAMPLES: Tuple[ExampleEntry, ...] = FAST_EXAMPLES
"""Full tier is a superset of fast; extra entries added in a follow-up MR."""


# ---------------------------------------------------------------------------
# cmakev2 full (manual)
# ---------------------------------------------------------------------------
CMAKEV2_FULL_EXAMPLES: Tuple[ExampleEntry, ...] = CMAKEV2_FAST_EXAMPLES
"""Full tier is a superset of cmakev2 fast; extra entries added in a follow-up MR."""
