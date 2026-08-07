# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Discover component Kconfig / Kconfig.projbuild / sdkconfig.rename files.
Other Kconfig files (Kconfig.in etc.) are not discovered
(same as in ESP-IDF CMake discovery).

Mirrors ESP-IDF CMake discovery in tools/cmake/kconfig.cmake
(__kconfig_component_init) plus prepare_kconfig_files.py output format.

Rename *paths* are collected here; parsing is done via
``Kconfig.load_rename_files`` in ``snapshot.py``.
"""

import os
from typing import Dict
from typing import Iterable
from typing import List
from typing import Sequence
from typing import Tuple


def _is_kconfig_name(name: str, expected_lower: str) -> bool:
    """
    Case-insensitive filename match, mirroring CMake's ``string(TOLOWER)`` check
    in ``__kconfig_component_init``.
    """
    return name.lower() == expected_lower


def _is_relevant_rename(basename: str, target: str) -> bool:
    """
    True when *basename* is the base ``sdkconfig.rename`` or the
    target-specific ``sdkconfig.rename.<target>``. Rename files for other
    targets (``sdkconfig.rename.<other_target>``) are not relevant here.
    """
    return basename == "sdkconfig.rename" or basename == f"sdkconfig.rename.{target}"


def _collect_in_component_dir(component_dir: str, target: str) -> Tuple[List[str], List[str], List[str]]:
    """
    Return (kconfigs, kconfig_projbuilds, renames) for one component directory.

    Only rename files relevant to *target* are returned (see
    :func:`_is_relevant_rename`).
    """
    kconfigs: List[str] = []
    projbuilds: List[str] = []
    renames: List[str] = []
    try:
        entries = os.listdir(component_dir)
    except OSError:
        return kconfigs, projbuilds, renames

    for entry in entries:
        path = os.path.join(component_dir, entry)
        if not os.path.isfile(path):
            continue
        if _is_kconfig_name(entry, "kconfig"):
            kconfigs.append(path)
        elif _is_kconfig_name(entry, "kconfig.projbuild"):
            projbuilds.append(path)
        elif _is_relevant_rename(entry, target):
            renames.append(path)

    kconfigs.sort()
    projbuilds.sort()
    renames.sort()
    return kconfigs, projbuilds, renames


def _iter_component_dirs(idf_path: str) -> Iterable[str]:
    """
    Yield component directories that may hold Kconfig files.

    Includes:
      * components/*
      * components/bootloader/subproject/components/*
      * components/bootloader/subproject/main (if present)
    """
    components_root = os.path.join(idf_path, "components")
    if os.path.isdir(components_root):
        for name in sorted(os.listdir(components_root)):
            path = os.path.join(components_root, name)
            if os.path.isdir(path):
                yield path

    bootloader_components = os.path.join(idf_path, "components", "bootloader", "subproject", "components")
    if os.path.isdir(bootloader_components):
        for name in sorted(os.listdir(bootloader_components)):
            path = os.path.join(bootloader_components, name)
            if os.path.isdir(path):
                yield path

    bootloader_main = os.path.join(idf_path, "components", "bootloader", "subproject", "main")
    if os.path.isdir(bootloader_main):
        yield bootloader_main


def collect_kconfig_files(idf_path: str, target: str) -> Tuple[List[str], List[str], List[str]]:
    """
    Collect Kconfig, Kconfig.projbuild, and sdkconfig.rename paths for the whole repo.

    Target-specific rename files (``sdkconfig.rename.<target>``) are included;
    rename files for other targets are skipped.
    """
    kconfigs: List[str] = []
    projbuilds: List[str] = []
    renames: List[str] = []

    root_rename = os.path.join(idf_path, "sdkconfig.rename")
    if os.path.isfile(root_rename):
        renames.append(root_rename)
    root_rename_target = os.path.join(idf_path, f"sdkconfig.rename.{target}")
    if os.path.isfile(root_rename_target):
        renames.append(root_rename_target)

    for component_dir in _iter_component_dirs(idf_path):
        kconfig_file, kconfig_projbuild_file, rename_file = _collect_in_component_dir(component_dir, target)
        kconfigs.extend(kconfig_file)
        projbuilds.extend(kconfig_projbuild_file)
        renames.extend(rename_file)

    return kconfigs, projbuilds, renames


def write_source_file(paths: Sequence[str], dest: str) -> str:
    """
    Write a prepare_kconfig_files-style ``source "..."`` list. Returns ``dest``.
    """
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    lines = [f'source "{path}"' for path in paths]
    content = "\n".join(lines)
    if content:
        content += "\n"
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
    return dest


def prepare_kconfig_env(
    idf_path: str,
    target: str,
    staging_dir: str,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Build environment variables needed to parse the IDF root Kconfig.

    Returns (env_updates, rename_paths).
    """
    kconfigs, projbuilds, renames = collect_kconfig_files(idf_path, target)

    kconfigs_in = write_source_file(kconfigs, os.path.join(staging_dir, "kconfigs.in"))
    projbuilds_in = write_source_file(projbuilds, os.path.join(staging_dir, "kconfigs_projbuild.in"))
    # Empty excluded lists (everything we found is included).
    excluded_in = write_source_file([], os.path.join(staging_dir, "kconfigs_excluded.in"))
    excluded_proj_in = write_source_file([], os.path.join(staging_dir, "kconfigs_projbuild_excluded.in"))

    env = {
        "IDF_PATH": idf_path,
        "IDF_TARGET": target,
        "IDF_TOOLCHAIN": os.environ.get("IDF_TOOLCHAIN", "gcc"),
        "COMPONENT_KCONFIGS_SOURCE_FILE": kconfigs_in,
        "COMPONENT_KCONFIGS_PROJBUILD_SOURCE_FILE": projbuilds_in,
        "COMPONENT_KCONFIGS_EXCLUDED_SOURCE_FILE": excluded_in,
        "COMPONENT_KCONFIGS_PROJBUILD_EXCLUDED_SOURCE_FILE": excluded_proj_in,
    }
    # IDF_INIT_VERSION: best-effort from version file if present
    version_file = os.path.join(idf_path, "version.txt")
    if os.path.isfile(version_file):
        with open(version_file, encoding="utf-8") as f:
            env["IDF_INIT_VERSION"] = f.read().strip()
    else:
        env.setdefault("IDF_INIT_VERSION", os.environ.get("IDF_INIT_VERSION", "0.0.0"))

    return env, renames
