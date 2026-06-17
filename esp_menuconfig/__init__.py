# SPDX-FileCopyrightText: 2025-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""ESP-IDF menuconfig — Textual-based configuration interface."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING
from typing import Dict
from typing import Optional

from esp_pylib.logger import log

from esp_kconfiglib.core import standard_config_filename

# Keep stdout reserved for machine output: route note/hint/debug to stderr so all
# diagnostics land there, as they did before the esp_pylib migration.
log.set_info_stream(sys.stderr)

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


def menuconfig(kconf: "Kconfig", headless: bool = False) -> None:
    """Launch the Textual configuration interface, returning after the user exits."""
    global _module_state

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

    conf_changed, load_msg = state.load_config()
    state.conf_changed = conf_changed
    log.note(load_msg)

    if not state.shown:
        state.show_all = True
        state.shown = state.shown_nodes(state.cur_menu)
        if not state.shown:
            log.warn("Empty configuration -- nothing to configure.\nCheck that environment variables are set properly.")
            return

    kconf.warn = False
    _module_state = state

    if headless:
        return

    from .app import MenuConfigApp

    theme = _resolve_theme()
    app = MenuConfigApp(state, theme=theme)
    result = app.run()

    if result:
        log.print(result, file=sys.stderr)


def _needs_save() -> bool:
    """Check if config has unsaved changes."""
    if _module_state is not None:
        return _module_state.needs_save()
    return False


def reload_sdkconfig_file(filename: str) -> None:
    """Reload sdkconfig after a save to sync _needs_save() state."""
    if _module_state is not None:
        _module_state.reload_sdkconfig_file(filename)
