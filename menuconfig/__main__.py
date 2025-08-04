# SPDX-FileCopyrightText: 2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import sys

from esp_menuconfig.core import _main

if __name__ == "__main__":
    try:
        _main()
    except Exception as e:
        print(f"A fatal error occurred: {e}", file=sys.stderr)
        sys.exit(2)
