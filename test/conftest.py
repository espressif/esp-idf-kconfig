# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Repo-wide test fixtures.
"""

import pytest

from esp_kconfiglib.report import KconfigReport


@pytest.fixture(autouse=True)
def _reset_kconfig_report():
    """
    ``KconfigReport`` is a process-wide singleton, so records added by one
    test (e.g. default-value mismatches) would otherwise leak into the next
    test that constructs a ``Kconfig`` object, regardless of test file.
    """
    yield
    if KconfigReport._instance is not None:
        KconfigReport._instance.reset()
