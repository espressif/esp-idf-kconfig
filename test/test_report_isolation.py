# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Regression tests for the autouse fixture in ``test/conftest.py`` that resets
the ``KconfigReport`` singleton between tests.

``KconfigReport`` is a process-wide singleton (see
``esp_kconfiglib/report.py``), so records left over from one test (e.g.
default-value mismatches) would otherwise leak into unrelated tests that
construct a ``Kconfig`` object later in the same pytest session. These two
tests must keep passing regardless of test order, and neither calls
``kconfig.report.reset()`` manually.
"""

import os

from esp_kconfiglib import Kconfig
from esp_kconfiglib.report import DefaultValuesArea

TEST_FILES_PATH = os.path.abspath(os.path.dirname(__file__))
KCONFIG_PATH = os.path.join(TEST_FILES_PATH, "kconfiglib", "kconfigs")
SDKCONFIGS_PATH = os.path.join(TEST_FILES_PATH, "kconfiglib", "sdkconfigs")


def test_report_records_mismatch_without_manual_reset() -> None:
    """Loading a differing sdkconfig records default-value mismatches."""
    kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.loading_defaults"))
    kconfig.load_config(os.path.join(SDKCONFIGS_PATH, "sdkconfig.differing_defaults"))

    area = kconfig.report.area_to_instance[DefaultValuesArea]
    assert isinstance(area, DefaultValuesArea)
    assert {sym.name for sym, _, _ in area.changed_defaults} >= {"DEPENDEE", "DEP"}
    # Deliberately no `kconfig.report.reset()` call here: the autouse fixture
    # in `test/conftest.py` is responsible for cleaning this up.


def test_report_is_reset_before_next_test() -> None:
    """The previous test's records must not leak into this one."""
    kconfig = Kconfig(os.path.join(KCONFIG_PATH, "Kconfig.default_validity"))

    area = kconfig.report.area_to_instance[DefaultValuesArea]
    assert isinstance(area, DefaultValuesArea)
    assert area.changed_defaults == []
    assert area.changed_choices == []
