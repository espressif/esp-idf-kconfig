# SPDX-FileCopyrightText: 2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0

from enum import Enum


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
