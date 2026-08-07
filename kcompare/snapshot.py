# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Build a ConfigurationSnapshot from a parsed Kconfig tree.
"""

import os
from contextlib import contextmanager
from typing import Dict
from typing import Iterator
from typing import List
from typing import Optional
from typing import Tuple

from esp_kconfiglib import Kconfig
from esp_kconfiglib.core import expr_str

from .errors import SnapshotError
from .models import ChoiceSnapshot
from .models import ConfigurationSnapshot
from .models import SymbolSnapshot


def _renames_from_kconfig(kconf: Kconfig) -> Dict[str, Tuple[str, bool]]:
    """
    Build ``{deprecated: (new, inverted)}`` from ``kconf.deprecated_options``.

    Returns an empty dict when no rename files have been loaded.
    """
    deprecated = kconf.deprecated_options
    if deprecated is None:
        return {}
    return {old: (new, deprecated.is_inversion(old)) for old, new in deprecated.r_dic.items()}


@contextmanager
def _temporary_environ(updates: Dict[str, str]) -> Iterator[None]:
    """
    Apply env updates for the duration of the context, then restore.
    """
    saved = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


@contextmanager
def _working_directory(path: str) -> Iterator[None]:
    """
    Temporarily chdir to ``path``.
    """
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


@contextmanager
def _cleared_environ_keys(keys: Tuple[str, ...]) -> Iterator[None]:
    """
    Temporarily remove the given keys from ``os.environ``.
    """
    saved = {}
    for key in keys:
        if key in os.environ:
            saved[key] = os.environ.pop(key)
    try:
        yield
    finally:
        os.environ.update(saved)


def _rel_location(idf_path: str, filename: str, linenr: int) -> str:
    """
    Return ``"relative/path:line"`` for a Kconfig node, relative to the IDF root.
    Falls back to the raw filename when the file lies outside ``idf_path``.
    """
    abs_idf = os.path.realpath(idf_path)
    abs_file = os.path.realpath(filename)
    if abs_file.startswith(abs_idf + os.sep):
        rel = abs_file[len(abs_idf) + 1 :]
    else:
        rel = filename
    return f"{rel}:{linenr}"


def _is_y(cond) -> bool:  # type: ignore[no-untyped-def]
    """
    True when ``cond`` is the Kconfig constant ``y`` (unconditional).
    """
    return type(cond) is not tuple and getattr(cond, "name", None) == "y"


def _format_default(default, cond) -> str:  # type: ignore[no-untyped-def]
    """
    Render one ``(default, condition)`` pair as a human-readable string,
    e.g. ``"y"`` or ``"y if SOC_WIFI_SUPPORTED"``.
    """
    default_s = str(expr_str(default))
    if _is_y(cond):
        return default_s
    return f"{default_s} if {expr_str(cond)}"


def _defaults_list(defaults) -> Tuple[str, ...]:  # type: ignore[no-untyped-def]
    """
    Convert a symbol's or choice's ``defaults`` sequence into ordered strings.
    """
    return tuple(_format_default(default, cond) for default, cond in defaults)


def _node_locations(nodes, idf_path: str) -> Tuple[str, ...]:  # type: ignore[no-untyped-def]
    """
    Return the ordered, de-duplicated ``file:line`` locations for a symbol's or
    choice's menu nodes, relative to the IDF root.
    """
    locations = [_rel_location(idf_path, node.filename, node.linenr) for node in nodes]
    return tuple(dict.fromkeys(locations))


def _choice_id(choice, idf_path: str) -> Tuple[str, Tuple[str, ...], Optional[str]]:  # type: ignore[no-untyped-def]
    """
    Return (id, locations, name).

    The id is the choice name when named, otherwise the first definition
    location ("file:line").
    """
    locations = _node_locations(choice.nodes, idf_path)
    if not locations:
        locations = ("<unknown>:0",)
    if choice.name:
        return str(choice.name), locations, str(choice.name)
    return locations[0], locations, None


def snapshot_from_kconfig(
    kconf: Kconfig,
    idf_path: str,
    commit_ref: str,
    commit_sha: str,
    target: str,
) -> ConfigurationSnapshot:
    """
    Build a ConfigurationSnapshot from an already-parsed Kconfig instance.

    Renames come from ``kconf.deprecated_options`` when rename files were
    previously loaded via ``kconf.load_rename_files``.
    """
    symbols: Dict[str, SymbolSnapshot] = {}
    choice_member_names = set()
    choices: Dict[str, ChoiceSnapshot] = {}

    for choice in kconf.unique_choices:
        choice_id, locations, name = _choice_id(choice, idf_path)
        default_defs = _defaults_list(choice.defaults)
        default_syms = tuple(
            default.name if hasattr(default, "name") else expr_str(default) for default, _cond in choice.defaults
        )
        choices[choice_id] = ChoiceSnapshot(
            id=choice_id,
            name=name,
            locations=locations,
            defaults=default_defs,
            default_symbol_names=default_syms,
            options=tuple(sym.name for sym in choice.syms),
        )
        for sym in choice.syms:
            choice_member_names.add(sym.name)

    for sym in kconf.unique_defined_syms:
        if sym.name in choice_member_names:
            continue
        if sym.choice is not None:
            continue
        symbols[sym.name] = SymbolSnapshot(
            name=sym.name,
            defaults=_defaults_list(sym.defaults),
            locations=_node_locations(sym.nodes, idf_path),
        )

    return ConfigurationSnapshot(
        commit=commit_ref,
        commit_sha=commit_sha,
        target=target,
        symbols=symbols,
        choices=choices,
        renames=_renames_from_kconfig(kconf),
    )


def build_snapshot(
    idf_path: str,
    commit_ref: str,
    commit_sha: str,
    target: str,
    env_updates: Dict[str, str],
    rename_paths: Optional[List[str]] = None,
    load_renames_flag: bool = False,
) -> ConfigurationSnapshot:
    """
    Parse root Kconfig under ``idf_path`` and return a ConfigurationSnapshot.

    ``env_updates`` must include COMPONENT_KCONFIGS_*_SOURCE_FILE and IDF_TARGET.
    When ``load_renames_flag`` is True, ``rename_paths`` are parsed into the snapshot.
    """
    rename_paths = rename_paths or []
    idf_path = os.path.abspath(idf_path)
    root_kconfig = os.path.join(idf_path, "Kconfig")
    if not os.path.isfile(root_kconfig):
        raise SnapshotError(f"root Kconfig not found: {root_kconfig}")

    # Do not use $srctree (legacy). Pin the checkout with an absolute root
    # Kconfig path and chdir so relative source/orsource paths resolve here.
    env_updates = {key: value for key, value in env_updates.items() if key != "srctree"}
    env_updates["IDF_PATH"] = idf_path

    with _temporary_environ(env_updates):
        with _cleared_environ_keys(("srctree",)):
            with _working_directory(idf_path):
                kconf = Kconfig(filename=root_kconfig, warn=False, print_report=False)

    if load_renames_flag and rename_paths:
        try:
            kconf.load_rename_files(rename_paths)
        except RuntimeError as exc:
            raise SnapshotError(str(exc)) from exc

    return snapshot_from_kconfig(
        kconf,
        idf_path=idf_path,
        commit_ref=commit_ref,
        commit_sha=commit_sha,
        target=target,
    )
