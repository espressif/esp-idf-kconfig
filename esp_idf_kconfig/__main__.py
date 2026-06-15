# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import sys

from esp_pylib.excepthook import install_exception_reporting
from esp_pylib.logger import log

install_exception_reporting()

# Keep stdout reserved for machine output: route note/hint/debug to stderr so all
# diagnostics land there, as they did before the esp_pylib migration.
log.set_info_stream(sys.stderr)

log.print("ESP-IDF Kconfig tool")
msg = "Please select a tool to run with command:"
log.print(
    f"{msg}"
    f"\n{' ' * int(len(msg) / 2)}"
    f"Kconfig file checker. {' ' * 8} (python -m kconfcheck)"
    f"\n{' ' * int(len(msg) / 2)}"
    "Run JSON configuration server. (idf.py confserver or python -m kconfserver)"
    f"\n{' ' * int(len(msg) / 2)}"
    f"Config Generation Tool. {' ' * 6} (python -m kconfgen)",
)
