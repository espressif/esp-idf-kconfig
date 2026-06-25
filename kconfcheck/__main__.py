# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from esp_pylib.excepthook import install_exception_reporting

from esp_kconfiglib.errors import kconfig_error_handler

from .core import main

install_exception_reporting()

if __name__ == "__main__":
    with kconfig_error_handler():
        main()
