# SPDX-FileCopyrightText: 2024-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple


def _parse_path(path: str, sep: Optional[str] = None) -> Set:
    ret = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("#") and len(line) > 0:
                ret.add(line.split(sep)[0])
    return ret


def _prepare_deprecated_options(
    includes: List[str], exclude_submodules: List[str], files: List[str]
) -> Tuple[List[str], Set[str], Tuple]:
    deprecated_options = set()

    # used as "startswith" pattern to match sdkconfig.[ci|defaults] variants
    files_to_check_pattern = ("sdkconfig.ci", "sdkconfig.defaults")

    # Ignored directories (makes sense only when run on IDF_PATH)
    # Note: ignore_dirs is a tuple in order to be able to use it directly with the startswith() built-in function which
    # accepts tuples but no lists.
    ignore_dirs: Tuple = tuple(exclude_submodules) if exclude_submodules else tuple()

    # sdkconfig.rename files can be explicitly specified in the command line as well,
    # but they are not checked, only used as a source of deprecated options.
    for file in tuple(files):
        if "sdkconfig.rename" in file:
            deprecated_options.update(_parse_path(file))
            files.remove(file)

    # Recursively search for sdkconfig files in the specified directories
    # sdkconfig.rename: used as a source of deprecated options
    # sdkconfig.[ci|defaults]: added to list of files to be checked
    if includes:
        for directory in includes:
            for root, _, filenames in os.walk(directory):
                for filename in filenames:
                    full_path = os.path.join(root, filename)
                    if filename.startswith(files_to_check_pattern) and not full_path.startswith(ignore_dirs):
                        files.append(full_path)
                    elif filename == "sdkconfig.rename":
                        deprecated_options.update(_parse_path(full_path))
                    elif full_path.startswith(ignore_dirs):
                        print(f"{full_path}: Ignored")

    # Ignoring includes/excludes, we still want to gather all the deprecated values.
    # IDF_PATH should be set most of the time, but if not, use the current directory as a fallback.
    # When running kconfcheck as a pre-commit hook in ESP-IDF repo, os.getcwd() will be the same as IDF_PATH.
    project_path = os.environ.get("IDF_PATH", None)
    if not project_path:
        project_path = os.getcwd()
        print(f"kconfcheck: IDF_PATH is not set. Using {project_path} as a fallback.")
    for root, _, filenames in os.walk(project_path):
        for filename in filenames:
            if filename == "sdkconfig.rename":
                deprecated_options.update(_parse_path(os.path.join(root, filename)))

    return files, deprecated_options, ignore_dirs


def check_deprecated_options(
    file_full_path: str,
    deprecated_options: Set[str] = set(),
    ignore_dirs: Tuple = tuple(),
) -> Optional[bool]:
    if file_full_path in ignore_dirs:
        print(f"{file_full_path}: Ignored")
        return None
    used_options = _parse_path(file_full_path, "=")
    used_deprecated_options = deprecated_options.intersection(used_options)
    if len(used_deprecated_options) > 0:
        print(f"{file_full_path}: The following options are deprecated: {', '.join(used_deprecated_options)}")
        return False
    else:
        print(f"{file_full_path}: OK")
        return True
