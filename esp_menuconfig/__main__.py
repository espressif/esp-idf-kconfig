# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os

from esp_pylib.excepthook import install_exception_reporting
from esp_pylib.logger import log
from rich.markup import escape


def _main() -> None:
    """Entry point for ``python -m esp_menuconfig``."""
    from esp_kconfiglib.core import standard_kconfig
    from esp_kconfiglib.deprecated import load_rename_files_from_env

    from . import menuconfig

    kconf = standard_kconfig()
    load_rename_files_from_env(
        kconf,
        sdkconfig_rename=os.environ.get("SDKCONFIG_RENAME"),
        list_separator=os.environ.get("SDKCONFIG_RENAMES_LIST_SEPARATOR", "space"),
    )
    headless = os.environ.get("MENUCONFIG_HEADLESS") == "1"
    menuconfig(kconf, headless=headless)


if __name__ == "__main__":
    install_exception_reporting()
    try:
        _main()
    except Exception as e:
        log.die(f"A fatal error occurred: {escape(str(e))}", exit_code=2)
