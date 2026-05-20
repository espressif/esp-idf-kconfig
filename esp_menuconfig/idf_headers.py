# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""IDF-specific sdkconfig / minimal-config file header builders."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING
from typing import Optional

from esp_kconfiglib.constants import build_idf_min_config_header
from esp_kconfiglib.constants import build_idf_sdkconfig_header
from esp_kconfiglib.core import standard_config_filename

if TYPE_CHECKING:
    from esp_kconfiglib import Kconfig


def _idf_version_from_build_config_env() -> str:
    """If ``IDF_VERSION`` is not in the environment, try ``build/config.env`` (JSON)."""
    try:
        config_path = os.path.abspath(standard_config_filename())
        project_dir = os.path.dirname(config_path)
        build_env_path = os.path.join(project_dir, "build", "config.env")
        with open(build_env_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            val = data.get("IDF_VERSION")
            if isinstance(val, str):
                return val
    except (OSError, ValueError, TypeError):
        pass
    return ""


def idf_sdkconfig_header() -> Optional[str]:
    """Build the sdkconfig file header for :meth:`Kconfig.write_config`."""
    if "IDF_TARGET" not in os.environ and "IDF_INIT_VERSION" not in os.environ:
        return None
    idf_version = os.environ.get("IDF_VERSION", "")
    if not idf_version:
        idf_version = _idf_version_from_build_config_env()
    return build_idf_sdkconfig_header(idf_version=idf_version)


def idf_min_config_save_header(kconf: "Kconfig") -> str:
    """Build the ESP-IDF minimal-config file header."""
    idf_version = os.environ.get("IDF_VERSION", "")
    if not idf_version:
        idf_version = _idf_version_from_build_config_env()
    return build_idf_min_config_header(kconf, idf_version=idf_version)
