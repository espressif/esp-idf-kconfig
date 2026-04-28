#!/usr/bin/env python
#
# Command line tool to take in ESP-IDF sdkconfig files with project
# settings and output data in multiple formats (update config, generate
# header file, generate .cmake include file, documentation, etc).
#
# Used internally by the ESP-IDF build system. But designed to be
# non-IDF-specific.
#
# SPDX-FileCopyrightText: 2018-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
import os.path
import sys
import tempfile
import textwrap
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Union

import esp_idf_kconfig.gen_kconfig_doc as gen_kconfig_doc
import esp_kconfiglib.core as kconfiglib
from esp_idf_kconfig import __version__
from esp_kconfiglib.constants import build_idf_min_config_header
from esp_kconfiglib.constants import build_idf_sdkconfig_header
from esp_kconfiglib.deprecated import DeprecatedOptions
from esp_kconfiglib.deprecated import load_rename_files_from_env


def write_config(config: kconfiglib.Kconfig, filename: str, write_deprecated: bool = True) -> None:
    """Write symbol values in sdkconfig format, optionally with deprecated compatibility block."""
    config.write_config(filename, header=build_idf_sdkconfig_header(), write_deprecated=write_deprecated)


def write_min_config(config: kconfiglib.Kconfig, filename: str, write_deprecated: bool = True) -> None:
    """
    Write a minimal (savedefconfig) configuration file.

    Builds the ESP-IDF header and delegates to
    :meth:`Kconfig.write_min_config`.
    """
    header = build_idf_min_config_header(config)
    use_labels = os.environ.get("ESP_IDF_KCONFIG_MIN_LABELS", "") == "1"
    config.write_min_config(filename, header=header, labels=use_labels, normalize_unset=True)


def write_header(config: kconfiglib.Kconfig, filename: str, write_deprecated: bool = True) -> None:
    """Write symbol values as a C header file, optionally with deprecated #define aliases."""
    idf_version = os.environ.get("IDF_VERSION", "")
    CONFIG_HEADING = f"""/*
 * Automatically generated file. DO NOT EDIT.
 * Espressif IoT Development Framework (ESP-IDF) {idf_version} Configuration Header
 */
#pragma once
"""
    config.write_autoconf(filename, header=CONFIG_HEADING, write_deprecated=write_deprecated)


def write_cmake(config: kconfiglib.Kconfig, filename: str, write_deprecated: bool = True) -> None:
    """Write symbol values as a CMake include file, optionally with deprecated variables."""
    deprecated_options = config.deprecated_options

    with open(filename, "w", encoding=config._encoding) as f:
        tmp_dep_list = []
        prefix = config.config_prefix

        f.write(
            textwrap.dedent(
                """\
                #
                # Automatically generated file. DO NOT EDIT.
                # Espressif IoT Development Framework (ESP-IDF) Configuration cmake include file
                #
                """
            )
        )

        configs_list = list()

        def write_node(node: kconfiglib.MenuNode) -> None:
            sym = node.item
            if not isinstance(sym, kconfiglib.Symbol):
                return

            if sym.config_string:
                val = sym.str_value
                if sym.orig_type == kconfiglib.BOOL and val == "n":
                    val = ""
                elif sym.orig_type == kconfiglib.STRING:
                    val = kconfiglib.escape(val)
                elif sym.orig_type == kconfiglib.HEX:
                    val = hex(int(val, 16))
                f.write(f'set({prefix}{sym.name} "{val}")\n')

                configs_list.append(prefix + sym.name)
                if write_deprecated and deprecated_options:
                    dep_opts = deprecated_options.get_deprecated_option(sym.name)
                    for opt in dep_opts:
                        if deprecated_options.is_inversion(opt) and sym.orig_type == kconfiglib.BOOL:
                            val = "y" if not val else ""
                        tmp_dep_list.append('set({}{} "{}")\n'.format(prefix, opt, val))
                        configs_list.append(prefix + opt)

        for n in config.node_iter():
            write_node(n)
        f.write("set(CONFIGS_LIST {})".format(";".join(configs_list)))

        if len(tmp_dep_list) > 0:
            f.write("\n# List of deprecated options for backward compatibility\n")
            f.writelines(tmp_dep_list)


def get_json_values(config: kconfiglib.Kconfig) -> dict:
    """Extract symbol values as a Python dict with typed values."""
    config_dict = {}

    def write_node(node: kconfiglib.MenuNode) -> None:
        sym = node.item
        if not isinstance(sym, kconfiglib.Symbol):
            return

        if sym.config_string:
            candidate_val: str = sym.str_value
            if not candidate_val and sym.type in (
                kconfiglib.INT,
                kconfiglib.HEX,
                kconfiglib.FLOAT,
            ):
                print(
                    f"warning: {sym.name} has no value set in the configuration."
                    " This can be caused e.g. by missing default value for the current chip version."
                )
                val: Optional[Union[str, bool, int, float]] = None
            elif sym.type == kconfiglib.BOOL:
                val = candidate_val != "n"
            elif sym.type == kconfiglib.HEX:
                val = int(candidate_val, 16)
            elif sym.type == kconfiglib.INT:
                val = int(candidate_val)
            elif sym.type == kconfiglib.FLOAT:
                val = float(candidate_val)
            else:
                val = candidate_val
            config_dict[sym.name] = val

    for n in config.node_iter(False):
        write_node(n)
    return config_dict


def write_json(config: kconfiglib.Kconfig, filename: str, write_deprecated: bool = True) -> None:
    """Write symbol values as a JSON file."""
    config_dict = get_json_values(config)
    with open(filename, "w", encoding=config._encoding) as f:
        json.dump(config_dict, f, indent=4, sort_keys=True)


def write_json_menus(config: kconfiglib.Kconfig, filename: str, write_deprecated: bool = True) -> None:
    """Write the full menu tree structure as a JSON file."""
    existing_ids: Set[str] = set()
    result: List = []
    node_lookup: Dict = {}

    def write_node(node: kconfiglib.MenuNode) -> None:
        try:
            json_parent = node_lookup[node.parent]["children"]
        except KeyError:
            assert node.parent not in node_lookup
            json_parent = result

        if node.dep is node.kconfig.y:
            depends = None
        else:
            depends = kconfiglib.expr_str(node.dep)

        try:
            is_menuconfig = node.is_menuconfig and isinstance(node.item, kconfiglib.Symbol)
        except AttributeError:
            is_menuconfig = False

        new_json: Dict[str, Any] = {}
        if node.item == kconfiglib.MENU or is_menuconfig:
            new_json = {
                "type": "menu",
                "title": node.prompt[0] if node.prompt else "",
                "depends_on": depends,
                "children": [],
            }
            if is_menuconfig and isinstance(node.item, kconfiglib.Symbol):
                sym = node.item
                new_json["name"] = sym.name
                new_json["help"] = node.help
                new_json["is_menuconfig"] = is_menuconfig
                greatest_range = None
                if isinstance(sym, (kconfiglib.Symbol, kconfiglib.MenuNode)) and len(sym.ranges) > 0:
                    for min_range, max_range, cond_expr in sym.ranges:
                        if kconfiglib.expr_value(cond_expr):
                            greatest_range = [min_range, max_range]
                new_json["range"] = greatest_range

        elif isinstance(node.item, kconfiglib.Symbol):
            sym = node.item
            greatest_range = None
            if len(sym.ranges) > 0:
                for min_range, max_range, cond_expr in sym.ranges:
                    if kconfiglib.expr_value(cond_expr):
                        if sym.type == kconfiglib.FLOAT:
                            greatest_range = [
                                float(min_range.str_value),
                                float(max_range.str_value),
                            ]
                        else:
                            base = 16 if sym.type == kconfiglib.HEX else 10
                            greatest_range = [
                                int(min_range.str_value, base),
                                int(max_range.str_value, base),
                            ]
                        break

            new_json = {
                "type": kconfiglib.TYPE_TO_STR[sym.type],
                "name": sym.name,
                "title": node.prompt[0] if node.prompt else None,
                "depends_on": depends,
                "help": node.help,
                "range": greatest_range,
                "children": [],
            }
        elif isinstance(node.item, kconfiglib.Choice):
            choice = node.item
            new_json = {
                "type": "choice",
                "title": node.prompt[0] if node.prompt else "",
                "name": choice.name,
                "depends_on": depends,
                "help": node.help,
                "children": [],
            }

        if new_json:
            if node.id in existing_ids:
                raise RuntimeError(
                    "Config file contains two items with the same id: "
                    f" {node.id} ({node.prompt[0] if node.prompt else ''}). "
                    "Please rename one of these items to avoid ambiguity."
                )
            new_json["id"] = node.id

            json_parent.append(new_json)
            node_lookup[node] = new_json

    for n in config.node_iter():
        write_node(n)
    with open(filename, "w", encoding=config._encoding) as f:
        f.write(json.dumps(result, sort_keys=True, indent=4))


def append_deprecated_doc(
    deprecated_options: DeprecatedOptions,
    config: kconfiglib.Kconfig,
    visibility: gen_kconfig_doc.ConfigTargetVisibility,
    path_output: str,
) -> None:
    """Append deprecated options documentation section to an RST docs file."""

    def option_was_written(opt: str) -> bool:
        if opt in config.named_choices:
            syms = config.named_choices[opt].syms
            for s in syms:
                if any(visibility.visible(node) for node in s.nodes):
                    return True
            return False
        else:
            try:
                return any(visibility.visible(node) for node in config.syms[opt].nodes)
            except KeyError:
                return False

    if deprecated_options.has_entries:
        with open(path_output, "a", encoding=deprecated_options.encoding) as f_o:
            header = "Deprecated options and their replacements"
            f_o.write(".. _configuration-deprecated-options:\n\n{}\n{}\n\n".format(header, "-" * len(header)))
            for dep_opt in sorted(deprecated_options.r_dic):
                new_opt = deprecated_options.r_dic[dep_opt]
                if option_was_written(new_opt) and (new_opt not in config.syms or config.syms[new_opt].choice is None):
                    f_o.write(
                        "- {}{} ({}:ref:`{}{}`)\n".format(
                            config.config_prefix,
                            dep_opt,
                            "inversion of " if dep_opt in deprecated_options.inversions else "",
                            config.config_prefix,
                            new_opt,
                        )
                    )

                    if new_opt in config.named_choices:
                        syms = config.named_choices[new_opt].syms
                        for sym in syms:
                            if sym.name in deprecated_options.rev_r_dic:
                                dep_names = deprecated_options.rev_r_dic[sym.name]
                                dep_names = [config.config_prefix + name for name in dep_names]
                                f_o.write("    - {}\n".format(", ".join(dep_names)))


def write_docs(config: kconfiglib.Kconfig, filename: str, write_deprecated: bool = True) -> None:
    """Write Kconfig documentation in RST format, optionally with deprecated options section."""
    try:
        target = os.environ["IDF_TARGET"]
    except KeyError:
        print("IDF_TARGET environment variable must be defined!")
        sys.exit(1)

    visibility = gen_kconfig_doc.ConfigTargetVisibility(config, target)
    gen_kconfig_doc.write_docs(config, visibility, filename)
    if write_deprecated and config.deprecated_options:
        append_deprecated_doc(config.deprecated_options, config, visibility, filename)


def write_report(config: kconfiglib.Kconfig, filename: str, write_deprecated: bool = True) -> None:
    """Write the Kconfig parse report to a JSON file."""
    config.report.output_json(filename)


def write_cdep_tree(config: kconfiglib.Kconfig, path: str, write_deprecated: bool = True) -> None:
    """Write the cdep_tree file structure for incremental rebuild tracking.

    Creates e.g. path/feature/enable.cdep for FEATURE_ENABLE.
    When deprecated options are loaded, also touches cdep files for deprecated aliases.
    """
    config.sync_deps(path)


def update_if_changed(source: str, destination: str, encoding: str) -> None:
    """Copy source to destination only if the content differs."""
    with open(source, "r", encoding=encoding) as f:
        source_contents = f.read()

    if os.path.exists(destination):
        with open(destination, "r", encoding=encoding) as f:
            dest_contents = f.read()
        if source_contents == dest_contents:
            return

    with open(destination, "w", encoding=encoding) as f:
        f.write(source_contents)


OUTPUT_FORMATS = {
    "config": write_config,
    "header": write_header,
    "cmake": write_cmake,
    "docs": write_docs,
    "json": write_json,
    "json_menus": write_json_menus,
    "savedefconfig": write_min_config,
    "report": write_report,
    "cdep_tree": write_cdep_tree,
}


def main():
    parser = argparse.ArgumentParser(
        description="kconfgen.py v%s - Config Generation Tool" % __version__,
        prog=os.path.basename(sys.argv[0]),
    )

    parser.add_argument("--config", help="Project configuration settings", nargs="?", default=None)

    parser.add_argument(
        "--defaults",
        help="Optional project defaults file, used if --config file doesn't exist. "
        "Multiple files can be specified using multiple --defaults arguments.",
        nargs="?",
        default=[],
        action="append",
    )

    parser.add_argument("--kconfig", help="Kconfig file with config item definitions", required=True)

    parser.add_argument(
        "--sdkconfig-rename",
        help="File with deprecated Kconfig options",
        required=False,
    )

    parser.add_argument(
        "--dont-write-deprecated",
        help="Do not write compatibility statements for deprecated values",
        action="store_true",
    )

    parser.add_argument(
        "--menuconfig",
        help="Launch interactive menuconfig before generating output files",
        action="store_true",
    )

    parser.add_argument(
        "--output",
        nargs=2,
        action="append",
        help="Write output file (format and output filename)",
        metavar=("FORMAT", "FILENAME"),
        default=[],
    )

    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Environment to set when evaluating the config file",
        metavar="NAME=VAL",
    )

    parser.add_argument(
        "--env-file",
        type=argparse.FileType("r"),
        help="Optional file to load environment variables from. Contents "
        "should be a JSON object where each key/value pair is a variable.",
    )

    parser.add_argument(
        "--list-separator",
        choices=["space", "semicolon"],
        default="space",
        help="Separator used in environment list variables (COMPONENT_SDKCONFIG_RENAMES)",
    )
    args = parser.parse_args()

    for fmt, _ in args.output:
        if fmt not in OUTPUT_FORMATS.keys():
            print(f"Format '{fmt}' not recognized. Known formats: {list(OUTPUT_FORMATS.keys())}")
            sys.exit(1)

    try:
        args.env = [(name, value) for (name, value) in (e.split("=", 1) for e in args.env)]
    except ValueError:
        print("--env arguments must each contain =. To unset an environment variable, use 'ENV='")
        sys.exit(1)

    for name, value in args.env:
        os.environ[name] = value

    if args.env_file is not None:
        env = json.load(args.env_file)
        os.environ.update(env)
    parser_version = int(os.environ.get("KCONFIG_PARSER_VERSION", "1"))
    # TODO Once ESP-IDF will fully support kconfig report, we should switch to "quiet" as default
    #      to avoid printing the report several times during the build.
    print_report = os.environ.get("KCONFIG_REPORT_VERBOSITY", "default") != "quiet"
    config = kconfiglib.Kconfig(
        args.kconfig,
        parser_version=parser_version,
        print_report=(
            print_report
            and not (
                args.config and os.path.exists(args.config)
            )  # if sdkconfig file exists, we'll report after it is loaded
            and len(args.defaults) == 0  # if defaults are loaded, report will be printed after that
        ),
    )
    kconfig_encoding = config._encoding

    load_rename_files_from_env(
        config,
        sdkconfig_rename=args.sdkconfig_rename,
        list_separator=args.list_separator,
    )

    if len(args.defaults) > 0:

        def _replace_empty_assignments(path_in, path_out):  # empty assignment: CONFIG_FOO=
            with open(path_in, "r", encoding=kconfig_encoding) as f_in, open(
                path_out, "w", encoding=kconfig_encoding
            ) as f_out:
                for line_num, line in enumerate(f_in, start=1):
                    line = line.strip()
                    if line.endswith("="):
                        line += "n"
                        print("{}:{} line was updated to {}".format(path_out, line_num, line))
                    f_out.write(line)
                    f_out.write("\n")

        for name in args.defaults:
            print("Loading defaults file %s..." % name)
            if not os.path.exists(name):
                raise RuntimeError("Defaults file not found: %s" % name)
            try:
                with tempfile.NamedTemporaryFile(
                    prefix="kconfgen_tmp", mode="w+", delete=False, encoding=kconfig_encoding
                ) as f:
                    temp_file = f.name
                _replace_empty_assignments(name, temp_file)
                config.load_config(temp_file, replace=False)

                for symbol, value in config.missing_syms:
                    print(f"warning: unknown kconfig symbol '{symbol}' assigned to '{value}' in {name}")
            finally:
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
        if print_report and not (args.config and os.path.exists(args.config)):
            config.report.print_report()

    if args.config and os.path.exists(args.config):
        config.load_config(args.config, replace=False, print_report=print_report)

    if args.menuconfig:
        # Local import keeps non-interactive kconfgen runs free of curses.
        from esp_menuconfig import menuconfig as run_menuconfig

        run_menuconfig(config)

    write_deprecated = not args.dont_write_deprecated

    for output_type, filename_or_path in args.output:
        if output_type == "cdep_tree":
            write_cdep_tree(config, filename_or_path)
            continue
        with tempfile.NamedTemporaryFile(
            prefix="kconfgen_tmp",
            mode="w+",
            delete=False,
            encoding=kconfig_encoding,
        ) as f:
            temp_file = f.name
        try:
            output_function = OUTPUT_FORMATS[output_type]
            output_function(config, temp_file, write_deprecated=write_deprecated)
            update_if_changed(temp_file, filename_or_path, encoding=kconfig_encoding)
        finally:
            try:
                os.remove(temp_file)
            except OSError:
                pass
