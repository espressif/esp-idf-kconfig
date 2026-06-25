# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from esp_pylib.excepthook import install_exception_reporting

from esp_kconfiglib.errors import kconfig_error_handler

from .core import main

if __name__ == "__main__":
    install_exception_reporting()
    with kconfig_error_handler():
        main()
