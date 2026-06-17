# SPDX-FileCopyrightText: 2025-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from esp_pylib.excepthook import install_exception_reporting
from esp_pylib.logger import log
from rich.markup import escape

from esp_menuconfig.__main__ import _main

if __name__ == "__main__":
    install_exception_reporting()
    try:
        _main()
    except Exception as e:
        log.die(f"A fatal error occurred: {escape(str(e))}", exit_code=2)
