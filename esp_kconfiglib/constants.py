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
