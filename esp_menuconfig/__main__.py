# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os

import rich_click as click
from esp_pylib.excepthook import install_exception_reporting

from esp_kconfiglib.errors import kconfig_error_handler


@click.command()
@click.argument("kconfig", default="Kconfig", required=False)
def _main(kconfig: str) -> None:
    """Launch the ESP-IDF interactive menuconfig."""
    from esp_kconfiglib.core import Kconfig
    from esp_kconfiglib.deprecated import load_rename_files_from_env

    from . import menuconfig

    parser_version = int(os.environ.get("KCONFIG_PARSER_VERSION", "1"))
    kconf = Kconfig(kconfig, suppress_traceback=True, parser_version=parser_version)
    load_rename_files_from_env(
        kconf,
        sdkconfig_rename=os.environ.get("SDKCONFIG_RENAME"),
        list_separator=os.environ.get("SDKCONFIG_RENAMES_LIST_SEPARATOR", "space"),
    )
    headless = os.environ.get("MENUCONFIG_HEADLESS") == "1"
    menuconfig(kconf, headless=headless)


if __name__ == "__main__":
    install_exception_reporting()
    with kconfig_error_handler():
        _main(standalone_mode=False)
