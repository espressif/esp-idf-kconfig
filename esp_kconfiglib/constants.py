# SPDX-FileCopyrightText: 2025-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0

import os
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from esp_kconfiglib.core import Kconfig


class DefaultsPolicy(Enum):
    USE_SDKCONFIG = "sdkconfig"
    INTERACTIVE = "interactive"
    USE_KCONFIG = "kconfig"

    @property
    def description(self) -> str:
        """Return a human-readable description of the policy."""
        if self == DefaultsPolicy.USE_SDKCONFIG:
            return "Using sdkconfig default values"
        elif self == DefaultsPolicy.INTERACTIVE:
            return "Default value mismatches resolved interactively by the user"
        elif self == DefaultsPolicy.USE_KCONFIG:
            return "Using Kconfig default values"
        else:
            return "Unknown policy"


# Start and end comment for deprecated options written into sdkconfig
DEP_OP_BEGIN = "# Deprecated options for backward compatibility"
DEP_OP_END = "# End of deprecated options"

# This pragma marks config options that have default value in sdkconfig file:
SDKCONFIG_DEFAULT_PRAGMA = "# default:"

# Suffix for header_tree dependency files (from esp-idf-configdep); avoids ambiguity with .config
HEADER_TREE_SUFFIX = ".cdep"

# Template for ESP-IDF-style minimal config file header (sdkconfig.defaults).
# Needs to be substituted with the actual IDF version and IDF_TARGET symbol's config_string (when not the default esp32)
MIN_CONFIG_HEADER_TEMPLATE = (
    "# This file was generated using idf.py save-defconfig or menuconfig [D] key. It can be edited manually.\n"
    "# Espressif IoT Development Framework (ESP-IDF) {idf_version} Project Minimal Configuration\n"
    "#\n"
    "{idf_target_config_string}"
)


# Template for ESP-IDF-style sdkconfig file header (sdkconfig).
SDKCONFIG_HEADER_TEMPLATE = (
    "#\n"
    "# Automatically generated file. DO NOT EDIT.\n"
    "# Espressif IoT Development Framework (ESP-IDF) {idf_version} Project Configuration\n"
    "#\n"
)


def build_idf_sdkconfig_header(idf_version: str = "") -> str:
    """
    Build the ESP-IDF sdkconfig header from ``SDKCONFIG_HEADER_TEMPLATE``.

    Reads ``IDF_VERSION`` from the environment when *idf_version* is not given
    (or empty).
    """

    if not idf_version:
        idf_version = os.environ.get("IDF_VERSION", "")
    return SDKCONFIG_HEADER_TEMPLATE.format(idf_version=idf_version)


def build_idf_min_config_header(config: "Kconfig", idf_version: str = "") -> str:
    """
    Build the ESP-IDF minimal-config header from ``MIN_CONFIG_HEADER_TEMPLATE``.

    Reads ``IDF_VERSION`` from the environment when *idf_version* is not given
    (or empty).  Prepends the ``IDF_TARGET`` assignment when the target is not
    the default ``esp32``.
    """

    if not idf_version:
        idf_version = os.environ.get("IDF_VERSION", "")
    idf_target_config_string = ""
    sym = config.syms.get("IDF_TARGET")
    if sym is not None and sym.str_value != "esp32":
        idf_target_config_string = sym.config_string
    return MIN_CONFIG_HEADER_TEMPLATE.format(
        idf_version=idf_version,
        idf_target_config_string=idf_target_config_string,
    )
