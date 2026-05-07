# SPDX-FileCopyrightText: 2025-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
ESP-IDF menuconfig entry point.

Dispatches between the legacy curses-based implementation and the new
Textual-based one based on the ``KCONFIG_LEGACY_MENUCONFIG`` environment
variable:

- Unset, "0", or "n" (case-insensitive) → Textual (new)
- Anything else → curses (legacy)
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING
from typing import Dict
from typing import Optional

from esp_kconfiglib.core import standard_config_filename

if TYPE_CHECKING:
    from esp_kconfiglib import Kconfig

    from .model import MenuConfigState

_module_state: Optional["MenuConfigState"] = None

_LEGACY_STYLE_MAP: Dict[str, str] = {
    "default": "gruvbox",
    "monochrome": "textual-ansi",
    "aquatic": "textual-dark",
}


def _resolve_theme() -> Optional[str]:
    """Map MENUCONFIG_STYLE env var to a Textual theme name.

    Legacy names (default, monochrome, aquatic) are mapped to their closest
    Textual counterparts.  Any other value is passed through as-is so users
    can use any built-in Textual theme directly (e.g. ``gruvbox``,
    ``tokyo-night``).  Returns *None* when the variable is unset.
    """
    style_env = os.environ.get("MENUCONFIG_STYLE", "").strip()
    if not style_env:
        return None

    first_token = style_env.split()[0]
    return _LEGACY_STYLE_MAP.get(first_token, first_token)


def _use_legacy() -> bool:
    val = os.environ.get("KCONFIG_LEGACY_MENUCONFIG", "").strip().lower()
    return val not in ("", "0", "n")


def menuconfig(kconf: "Kconfig", headless: bool = False) -> None:
    """
    Launch the configuration interface, returning after the user exits.

    Dispatches to the Textual-based UI by default, or falls back to the
    legacy curses-based UI when ``KCONFIG_LEGACY_MENUCONFIG`` is set to a
    truthy value.
    """
    global _module_state

    if _use_legacy():
        from .core import menuconfig as _legacy_menuconfig

        _legacy_menuconfig(kconf, headless=headless)
        # Legacy sets its own module-level _kconf; bridge _needs_save via core
        _module_state = None
        return

    _textual_menuconfig(kconf, headless=headless)


def _textual_menuconfig(kconf: "Kconfig", headless: bool = False) -> None:
    global _module_state

    from rich.console import Console

    from .model import MenuConfigState

    conf_filename = standard_config_filename()
    minconf_filename = os.path.join(os.path.dirname(conf_filename), "sdkconfig.defaults")

    write_deprecated = kconf.deprecated_options is not None and kconf.deprecated_options.has_entries

    state = MenuConfigState(
        kconf=kconf,
        conf_filename=conf_filename,
        minconf_filename=minconf_filename,
        conf_changed=False,
        write_deprecated=write_deprecated,
    )

    # Load existing config
    conf_changed, load_msg = state.load_config()
    state.conf_changed = conf_changed
    print(load_msg, file=sys.stderr)

    # Check for empty config
    if not state.shown:
        state.show_all = True
        state.shown = state.shown_nodes(state.cur_menu)
        if not state.shown:
            print(
                "Empty configuration -- nothing to configure.\nCheck that environment variables are set properly.",
                file=sys.stderr,
            )
            return

    kconf.warn = False
    _module_state = state

    # Sync legacy global for tests that inspect esp_menuconfig.core._write_deprecated
    from . import core as _core_module

    _core_module._write_deprecated = state.write_deprecated
    _core_module._kconf = kconf

    if headless:
        return

    from .app import MenuConfigApp

    theme = _resolve_theme()
    app = MenuConfigApp(state, theme=theme)
    result = app.run()

    if result:
        Console(file=sys.stderr).print(result)


def _needs_save() -> bool:
    """Check if config has unsaved changes."""
    if _module_state is not None:
        return _module_state.needs_save()
    # Fall back to legacy module-level check
    if _use_legacy():
        from .core import _needs_save as _legacy_needs_save

        return bool(_legacy_needs_save())
    return False


def reload_sdkconfig_file(filename: str) -> None:
    """Reload sdkconfig after a save to sync _needs_save() state."""
    if _module_state is not None:
        _module_state.reload_sdkconfig_file(filename)
    else:
        from .core import reload_sdkconfig_file as _legacy_reload

        _legacy_reload(filename)
