# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from esp_pylib.errors import FatalError
from esp_pylib.excepthook import install_exception_reporting
from esp_pylib.logger import log
from rich.markup import escape

from .core import main

if __name__ == "__main__":
    install_exception_reporting()
    try:
        main()
    except FatalError as e:
        log.die(f"A fatal error occurred: {escape(str(e))}", exit_code=2)
