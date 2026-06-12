# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Exercise esp-idf-kconfig's sdkconfig.defaults merge path: a project-level
defaults file must override the Kconfig-computed defaults, under both parsers.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import pytest

from .helpers.env import parser_versions
from .test_build import _set_target_and_build


@pytest.mark.fast
@pytest.mark.cmakev2_fast
@pytest.mark.parametrize("parser_version", parser_versions())
def test_sdkconfig_defaults_merged(
    parser_version: str,
    idf_py: Callable[..., "subprocess.CompletedProcess[str]"],
    test_app_copy: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A project-level sdkconfig.defaults must be merged on top of the
    Kconfig-computed defaults by esp-idf-kconfig, identically under both
    parser versions.
    """
    monkeypatch.setenv("KCONFIG_PARSER_VERSION", parser_version)
    app_dir = test_app_copy("examples/get-started/hello_world")

    # Force non-default values the kconfig layer must merge in:
    #  * a choice member (log level)  * an int within its range (tick rate)
    (app_dir / "sdkconfig.defaults").write_text(
        "CONFIG_LOG_DEFAULT_LEVEL_WARN=y\nCONFIG_FREERTOS_HZ=1000\n",
        encoding="utf-8",
    )

    _set_target_and_build(app_dir, "esp32", idf_py)

    sdkconfig = (app_dir / "sdkconfig").read_text(encoding="utf-8")
    assert "CONFIG_FREERTOS_HZ=1000" in sdkconfig
    assert "CONFIG_LOG_DEFAULT_LEVEL_WARN=y" in sdkconfig
