# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import sys


def _main():
    """Entry point that dispatches to legacy or textual based on env var."""
    from . import _use_legacy

    if _use_legacy():
        from .core import _main as _legacy_main

        _legacy_main()
    else:
        from esp_kconfiglib.core import standard_kconfig
        from esp_kconfiglib.deprecated import load_rename_files_from_env

        from . import menuconfig

        kconf = standard_kconfig()
        load_rename_files_from_env(
            kconf,
            sdkconfig_rename=os.environ.get("SDKCONFIG_RENAME"),
            list_separator=os.environ.get("SDKCONFIG_RENAMES_LIST_SEPARATOR", "space"),
        )
        menuconfig(kconf)


if __name__ == "__main__":
    try:
        _main()
    except Exception as e:
        print(f"A fatal error occurred: {e}", file=sys.stderr)
        sys.exit(2)
