# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import re
import sys
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple


def _is_project_root(directory: str) -> bool:
    """
    Test whether a directory is an ESP-IDF project root.

    A "project root" is the directory whose ``CMakeLists.txt`` runs ``project(...)``.

    Detection is intentionally syntactic (regex-only, no CMake evaluation) so this module stays
    a pure Python check with no CMake dependency. Known false positives — ``project()`` inside
    a never-taken ``if(FALSE)`` block, or inside a multi-line string literal — are extreme
    edge cases in real Kconfig/CMake usage and are accepted as the price of avoiding a CMake
    parser; do not "fix" with a more elaborate parser.
    """
    cmake_path = os.path.join(directory, "CMakeLists.txt")
    if not os.path.isfile(cmake_path):
        return False
    with open(cmake_path, "r", encoding="utf-8", errors="ignore") as f:
        return bool(re.search(r"^\s*project\s*\(", f.read(), re.MULTILINE))


def _find_project_root(path: str, cache: Dict[str, Optional[str]]) -> Optional[str]:
    """
    Return the nearest project-root ancestor of ``path``, or ``None`` if there is none.

    This answers "which project does this file belong to?".

    Results are memoized in ``cache`` (shared across all classification and check calls within
    one kconfcheck invocation) so the same directory chain is walked at most once.
    """
    path = os.path.abspath(path)
    checked: List[str] = []
    while True:
        if path in cache:
            result = cache[path]
            for d in checked:
                cache[d] = result
            return result
        checked.append(path)
        if _is_project_root(path):
            for d in checked:
                cache[d] = path
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    for d in checked:
        cache[d] = None
    return None


def extract_lhs_from_file(path: str, sep: Optional[str] = None) -> Set:
    """
    Extracts LHS from sdkconfig.[ci|defaults|rename] files.
    Sep: whitespace (use None for split()) for rename files, "=" for ci and defaults files.
    """
    ret = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("#") and len(line) > 0:
                ret.add(line.split(sep)[0])
    return ret


def _build_global_deprecated(abs_idf_path: str) -> Set[str]:
    """
    Collect the **global** deprecated set: rename files that apply to every checked file.

    Only two locations are walked:

    * ``IDF_PATH/sdkconfig.rename`` itself (framework-wide deprecations), and
    * everything under ``IDF_PATH/components/`` (built-in components).

    This is the only mandatory walk per invocation; it touches a small, stable part of the tree
    and is therefore cheap even on full ESP-IDF checkouts.
    """
    global_dep: Set[str] = set()

    root_rename = os.path.join(abs_idf_path, "sdkconfig.rename")
    if os.path.isfile(root_rename):
        global_dep.update(extract_lhs_from_file(root_rename))

    components_dir = os.path.join(abs_idf_path, "components")
    if os.path.isdir(components_dir):
        for root, _, filenames in os.walk(components_dir):
            for filename in filenames:
                if filename == "sdkconfig.rename":
                    global_dep.update(extract_lhs_from_file(os.path.join(root, filename)))
    return global_dep


def _build_local_deprecated(project_root: str, project_root_cache: Dict[str, Optional[str]]) -> Set[str]:
    """
    Walk a single project subtree to collect the **local** deprecated set for that project.

    Only rename files whose nearest project root is ``project_root`` itself are counted —
    rename files inside a *nested* project (e.g. an inner host-test app) belong to that
    nested project, not this one, and will be discovered later if/when a file inside the
    nested project is actually checked.
    """
    local_dep: Set[str] = set()
    for root, _, filenames in os.walk(project_root):
        for filename in filenames:
            if filename == "sdkconfig.rename":
                nearest = _find_project_root(root, project_root_cache)
                if nearest == project_root:
                    local_dep.update(extract_lhs_from_file(os.path.join(root, filename)))
    return local_dep


def _prepare_deprecated_options(
    includes: List[str], exclude_submodules: List[str], files: List[str]
) -> Tuple[List[str], Set[str], Dict[str, Set[str]], Tuple, Dict[str, Optional[str]], str]:
    """
    One-shot setup step for the ``--check deprecated`` mode.

    Builds the **global** deprecated set up-front (IDF root + ``components/`` only) and returns
    an empty per-project cache. The per-project (local) sets are filled in lazily by
    :func:`check_deprecated_options` the first time a file in a given project is checked, so
    a pre-commit invocation that touches files in only one project never has to walk every
    example in ``IDF_PATH``.

    Explicitly-passed ``sdkconfig.rename`` files (positional args) and any ``sdkconfig.rename``
    discovered via ``--includes`` directories are treated as **global**: the user asked for
    them, so they apply to every checked file regardless of location.
    """
    global_deprecated: Set[str] = set()
    project_root_cache: Dict[str, Optional[str]] = {}
    # Filled lazily by check_deprecated_options: project_root -> local rename set.
    local_deprecated: Dict[str, Set[str]] = {}

    files_to_check_pattern = ("sdkconfig.ci", "sdkconfig.defaults")
    ignore_dirs: Tuple = tuple(exclude_submodules) if exclude_submodules else tuple()

    # IDF_PATH should be set most of the time, but if not, use the current directory as a fallback.
    # When running kconfcheck as a pre-commit hook in ESP-IDF repo, os.getcwd() will be the same as IDF_PATH.
    idf_path = os.environ.get("IDF_PATH", None)
    if not idf_path:
        idf_path = os.getcwd()
        print(f"kconfcheck: IDF_PATH is not set. Using {idf_path} as a fallback.", file=sys.stderr)
    abs_idf_path = os.path.abspath(idf_path)

    global_deprecated |= _build_global_deprecated(abs_idf_path)

    # Explicit rename files passed on the command line -> always global. They are not checked,
    # only used as a source of deprecated option names.
    for file in tuple(files):
        if "sdkconfig.rename" in file:
            global_deprecated.update(extract_lhs_from_file(file))
            files.remove(file)

    # --includes directories are scanned for files-to-check, and any sdkconfig.rename inside
    # them is also treated as global.
    if includes:
        for directory in includes:
            for root, _, filenames in os.walk(directory):
                for filename in filenames:
                    full_path = os.path.join(root, filename)
                    if filename.startswith(files_to_check_pattern) and not full_path.startswith(ignore_dirs):
                        files.append(full_path)
                    elif filename == "sdkconfig.rename":
                        global_deprecated.update(extract_lhs_from_file(full_path))
                    elif full_path.startswith(ignore_dirs):
                        print(f"{full_path}: Ignored")

    return files, global_deprecated, local_deprecated, ignore_dirs, project_root_cache, abs_idf_path


def check_deprecated_options(
    file_full_path: str,
    global_deprecated: Set[str],
    local_deprecated: Dict[str, Set[str]],
    ignore_dirs: Tuple,
    project_root_cache: Dict[str, Optional[str]],
    abs_idf_path: str,
) -> Optional[bool]:
    """
    Check one ``sdkconfig.[ci|defaults]`` file against the effective deprecated set.

    Effective set = ``global_deprecated`` plus, if the file lives inside a user project,
    ``local_deprecated[project_root]``. The local set is computed and cached the first time a
    file in a given project is encountered (lazy build), so files outside the staged change
    set never trigger a walk of their project tree.
    """
    if file_full_path in ignore_dirs:
        print(f"{file_full_path}: Ignored", file=sys.stderr)
        return None

    file_dir = os.path.dirname(os.path.abspath(file_full_path))
    project_root = _find_project_root(file_dir, project_root_cache)

    effective_deprecated = set(global_deprecated)
    if project_root is not None and project_root != abs_idf_path:
        if project_root not in local_deprecated:
            local_deprecated[project_root] = _build_local_deprecated(project_root, project_root_cache)
        effective_deprecated |= local_deprecated[project_root]

    used_options = extract_lhs_from_file(file_full_path, "=")
    used_deprecated_options = effective_deprecated.intersection(used_options)
    if len(used_deprecated_options) > 0:
        print(f"{file_full_path}: The following options are deprecated: {', '.join(used_deprecated_options)}")
        return False
    else:
        print(f"{file_full_path}: OK")
        return True
