#!/usr/bin/env python
#
# Command line tool to take in ESP-IDF sdkconfig files with project
# settings and output data in multiple formats (update config, generate
# header file, generate .cmake include file, documentation, etc).
#
# Used internally by the ESP-IDF build system. But designed to be
# non-IDF-specific.
#
# SPDX-FileCopyrightText: 2018-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
import os.path
import re
import sys
import tempfile
import textwrap
from collections import OrderedDict
from collections import defaultdict
from typing import Any
from typing import DefaultDict
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple

import esp_idf_kconfig.gen_kconfig_doc as gen_kconfig_doc
import kconfiglib.core as kconfiglib
from esp_idf_kconfig import __version__


class DeprecatedOptions(object):
    _RENAME_FILE_NAME = "sdkconfig.rename"
    _DEP_OP_BEGIN = "# Deprecated options for backward compatibility"
    _DEP_OP_END = "# End of deprecated options"
    _RE_DEP_OP_BEGIN = re.compile(_DEP_OP_BEGIN)
    _RE_DEP_OP_END = re.compile(_DEP_OP_END)

    def __init__(self, config_prefix: str, path_rename_files: List[str] = []):
        self.config_prefix = config_prefix
        # sdkconfig.renames specification: each line contains a pair of config options separated by whitespace(s).
        # The first option is the deprecated one, the second one is the new one.
        # The new option can be prefixed with '!' to indicate inversion (n/not set -> y, y -> n).
        self.rename_line_regex = re.compile(
            rf"#.*|\s*\n|(?P<old>{self.config_prefix}[a-zA-Z_0-9]+)\s+(?P<new>!?{self.config_prefix}[A-Z_0-9]+)"
        )

        # r_dic maps deprecated options to new options; rev_r_dic maps in the opposite direction
        # inversion is a list of deprecated options which will be inverted (n/not set -> y, y -> n)
        self.r_dic, self.rev_r_dic, self.inversions = self._parse_replacements(path_rename_files)

        # note the '=' at the end of regex for not getting partial match of configs.
        # Also match if the config option is followed by a whitespace, this is the case
        # in sdkconfig.defaults files containing "# CONFIG_MMM_NNN is not set".
        self._RE_CONFIG = re.compile(rf"{self.config_prefix}(\w+)(=|\s+)")

    def parse_line(self, line: str) -> Optional[re.Match]:
        return self.rename_line_regex.match(line)

    def remove_config_prefix(self, string: str) -> str:
        if string.startswith(self.config_prefix):
            return string[len(self.config_prefix) :]
        elif string.startswith("!" + self.config_prefix):
            return string[len("!" + self.config_prefix) :]
        else:
            return ""

    def _parse_replacements(
        self, rename_paths: List[str]
    ) -> Tuple[Dict[str, str], DefaultDict[str, List[str]], List[str]]:
        rep_dic: Dict[str, str] = {}
        rev_rep_dic: DefaultDict[str, List[str]] = defaultdict(list)
        inversions: List[str] = []

        for rename_path in rename_paths:
            with open(rename_path) as rename_file:
                for line_number, line in enumerate(rename_file, start=1):
                    parsed_line = self.parse_line(line)
                    if not parsed_line:
                        raise RuntimeError(f"Syntax error in {rename_path} (line {line_number})")
                    if not parsed_line["old"]:
                        # empty line or comment
                        continue
                    if parsed_line["old"] in rep_dic:
                        raise RuntimeError(
                            "Error in {} (line {}): Replacement {} exist for {} and new "
                            "replacement {} is defined".format(
                                rename_path,
                                line_number,
                                rep_dic[parsed_line["old"]],
                                parsed_line["old"],
                                parsed_line["new"],
                            )
                        )

                    (dep_opt, new_opt) = (
                        self.remove_config_prefix(parsed_line["old"]),
                        self.remove_config_prefix(parsed_line["new"]),
                    )
                    for opt in (dep_opt, new_opt):
                        if not opt:
                            raise RuntimeError(
                                f"Error in {rename_path} (line {line_number}): Config {opt} is not prefixed with {self.config_prefix}"
                            )
                    if dep_opt == new_opt:
                        raise RuntimeError(
                            f"Error in {rename_path} (line {line_number}): Replacement name is the same as original name ({dep_opt})."
                        )
                    rep_dic[dep_opt] = new_opt
                    rev_rep_dic[new_opt].append(dep_opt)
                    if parsed_line["new"].startswith("!"):
                        inversions.append(dep_opt)

        return rep_dic, rev_rep_dic, inversions

    def is_inversion(self, deprecated_option: str) -> bool:
        return deprecated_option in self.inversions

    def get_deprecated_option(self, new_option: str) -> list:
        return self.rev_r_dic.get(new_option, [])

    def get_new_option(self, deprecated_option: str) -> Optional[str]:
        return self.r_dic.get(deprecated_option, None)

    def replace(self, sdkconfig_in: str, sdkconfig_out: str) -> None:
        replace_enabled = True
        with open(sdkconfig_in, "r") as input_file, open(sdkconfig_out, "w") as output_file:
            for line_number, line in enumerate(input_file, start=1):
                if self._RE_DEP_OP_BEGIN.search(line):  # Begin of deprecated options
                    replace_enabled = False
                elif self._RE_DEP_OP_END.search(line):  # End of deprecated options
                    replace_enabled = True
                elif replace_enabled:
                    m = self._RE_CONFIG.search(line)
                    if m and m.group(1) in self.r_dic:  # Deprecated option found
                        depr_opt = self.config_prefix + m.group(1)
                        new_opt = self.config_prefix + self.r_dic[m.group(1)]
                        line = self.replace_line(line, depr_opt=depr_opt, new_opt=new_opt)
                        print(
                            "{}:{} {} was replaced with {} {}".format(
                                sdkconfig_in,
                                line_number,
                                depr_opt,
                                new_opt,
                                "and inverted" if depr_opt[len(self.config_prefix) :] in self.inversions else "",
                            )
                        )
                output_file.write(line)

    def replace_line(self, line: str, depr_opt: str, new_opt: str, depr_to_new: bool = True) -> str:
        depr_name = self.remove_config_prefix(depr_opt)
        to_replace = depr_opt if depr_to_new else new_opt
        replace_with = new_opt if depr_to_new else depr_opt

        if depr_name in self.inversions:
            if any(substring in line for substring in ("is not set", "=n")):
                line = f"{replace_with}=y\n"
            else:
                line = f"{replace_with}=n\n"
        else:
            line = line.replace(to_replace, replace_with)
        return line

    def append_doc(
        self,
        config: kconfiglib.Kconfig,
        visibility: gen_kconfig_doc.ConfigTargetVisibility,
        path_output: str,
    ) -> None:
        def option_was_written(opt: str) -> bool:
            # named choices were written if any of the symbols in the choice were visible
            if new_opt in config.named_choices:
                syms = config.named_choices[new_opt].syms
                for s in syms:
                    if any(visibility.visible(node) for node in s.nodes):
                        return True
                return False
            else:
                try:
                    # otherwise if any of the nodes associated with the option was visible
                    return any(visibility.visible(node) for node in config.syms[opt].nodes)
                except KeyError:
                    return False

        if len(self.r_dic) > 0:
            with open(path_output, "a") as f_o:
                header = "Deprecated options and their replacements"
                f_o.write(".. _configuration-deprecated-options:\n\n{}\n{}\n\n".format(header, "-" * len(header)))
                for dep_opt in sorted(self.r_dic):
                    new_opt = self.r_dic[dep_opt]
                    if option_was_written(new_opt) and (
                        new_opt not in config.syms or config.syms[new_opt].choice is None
                    ):
                        # everything except config for a choice (no link reference for those in the docs)
                        f_o.write(
                            "- {}{} ({}:ref:`{}{}`)\n".format(
                                config.config_prefix,
                                dep_opt,
                                "inversion of " if dep_opt in self.inversions else "",
                                config.config_prefix,
                                new_opt,
                            )
                        )

                        if new_opt in config.named_choices:
                            # here are printed config options which were filtered out
                            syms = config.named_choices[new_opt].syms
                            for sym in syms:
                                if sym.name in self.rev_r_dic:
                                    # only if the symbol has been renamed
                                    dep_names = self.rev_r_dic[sym.name]
                                    dep_names = [config.config_prefix + name for name in dep_names]
                                    # config options doesn't have references
                                    f_o.write("    - {}\n".format(", ".join(dep_names)))

    def append_config(self, config: kconfiglib.Kconfig, path_output: str) -> None:
        tmp_list = []

        def append_config_node_process(node: kconfiglib.MenuNode) -> None:
            item = node.item
            if isinstance(item, kconfiglib.Symbol) and item.env_var is None:
                if item.name in self.rev_r_dic:
                    c_string = item.config_string
                    if c_string:
                        for dep_name in self.rev_r_dic[item.name]:
                            tmp_list.append(
                                self.replace_line(
                                    c_string,
                                    depr_opt=self.config_prefix + dep_name,
                                    new_opt=self.config_prefix + item.name,
                                    depr_to_new=False,
                                )
                            )

        for n in config.node_iter():
            append_config_node_process(n)

        if len(tmp_list) > 0:
            with open(path_output, "a") as f_o:
                f_o.write("\n{}\n".format(self._DEP_OP_BEGIN))
                f_o.writelines(tmp_list)
                f_o.write("{}\n".format(self._DEP_OP_END))

    def append_header(self, config: kconfiglib.Kconfig, path_output: str) -> None:
        def _opt_defined(opt):
            if opt.orig_type == kconfiglib.BOOL and opt.str_value != "n":
                opt_defined = True
            elif opt.orig_type in (kconfiglib.INT, kconfiglib.STRING, kconfiglib.HEX) and opt.str_value != "":
                opt_defined = True
            else:
                opt_defined = False
            return opt_defined

        if len(self.r_dic) > 0:
            with open(path_output, "a") as output_file:
                output_file.write("\n/* List of deprecated options */\n")
                for dep_opt in sorted(self.r_dic):
                    new_opt = self.r_dic[dep_opt]
                    if new_opt in config.syms and _opt_defined(config.syms[new_opt]):
                        output_file.write(
                            "#define {}{} {}{}{}\n".format(
                                self.config_prefix,
                                dep_opt,
                                "!" if dep_opt in self.inversions else "",
                                self.config_prefix,
                                new_opt,
                            )
                        )


def write_config(deprecated_options: DeprecatedOptions, config: kconfiglib.Kconfig, filename: str) -> None:
    idf_version = os.environ.get("IDF_VERSION", "")
    CONFIG_HEADING = textwrap.dedent(
        f"""\
    #
    # Automatically generated file. DO NOT EDIT.
    # Espressif IoT Development Framework (ESP-IDF) {idf_version} Project Configuration
    #
    """
    )
    config.write_config(filename, header=CONFIG_HEADING)
    deprecated_options.append_config(config, filename)


def min_config_with_labels(config: kconfiglib.Kconfig, header: str) -> str:
    """Return minimal config containing menu labels"""
    all_options = config._config_contents("").splitlines()
    min_options = config._min_config_contents("").splitlines()

    end_regex = re.compile(r"^# end of (.*)$").match
    # `label_path` marks the current path from the root; labels represent tree nodes.
    # The path is represented as an ordered Dict; the last element in the Dict is closest to the leaves.
    # The label name is the key, and a boolean value indicates whether the label was added to the output (i.e., the label is used in the output).
    # We need to track used labels to ensure correct timing when printing the label ending.
    # Note that label names are not necessarily unique, so the order is significant.
    label_path: OrderedDict[str, bool] = OrderedDict()
    output = [header]
    possibly_label = False
    current = None  # None stands for tree root
    comments = []

    # Using depth search first, we go down the tree and save the path from the root.
    # If we find an option from min config, we update the whole path to used (True) and print all menu labels.
    # When we go back up the tree, we print all label endings that were marked as used
    for line in all_options:
        end_match = end_regex(line)
        if end_match:
            # we have found an end of a menu section
            current = end_match.group(1)
            label = None
            while label != current and label_path:
                # remove any labels that appeared outside of used sections
                label, used = label_path.popitem()
                if used and label != current:
                    # used label without end -> comment
                    comments.append(label)
            if used:
                # menu label was used - print menu label ending
                output.append(f"{line}\n")
            # find the new current (the last in list); if tree is empty return back to the root
            current = next(reversed(label_path.keys())) if label_path else None
        elif line == "#":
            # starting/ending possible menu label
            possibly_label = not possibly_label
        elif possibly_label:
            current = line[2:]  # remove leading '# '
            label_path[current] = False  # label not yet used
        elif line in min_options:
            # minimal config option detected
            for label, used in label_path.items():
                # print all menu labels that were not printed yet
                if not used:
                    output.append(f"\n#\n# {label}\n#\n")
                # mark the whole path from root as 'used'
                label_path[label] = True
            output.append(line + "\n")
    # Remove comments from minimal config, while keeping menu labels
    for comment in comments:
        output.remove(f"\n#\n# {comment}\n#\n")
    return "".join(output)


def write_min_config(_, config: kconfiglib.Kconfig, filename: str) -> None:
    idf_version = os.environ.get("IDF_VERSION", "")
    target_symbol = config.syms["IDF_TARGET"]
    # 'esp32` is hardcoded here because the default value of IDF_TARGET is set on the first run from the environment
    # variable. I.E. `esp32  is not defined as default value.
    write_target = target_symbol.str_value != "esp32"

    CONFIG_HEADING = textwrap.dedent(
        f"""\
    # This file was generated using idf.py save-defconfig. It can be edited manually.
    # Espressif IoT Development Framework (ESP-IDF) {idf_version} Project Minimal Configuration
    #
    {target_symbol.config_string if write_target else ""}\
    """
    )

    if os.environ.get("ESP_IDF_KCONFIG_MIN_LABELS", False) == "1":
        lines = min_config_with_labels(config, CONFIG_HEADING).splitlines()
    else:
        lines = config._min_config_contents(header=CONFIG_HEADING).splitlines()

    # convert `# CONFIG_XY is not set` to `CONFIG_XY=n` to improve readability
    unset_match = re.compile(r"# {}([^ ]+) is not set".format(config.config_prefix)).match
    for idx, line in enumerate(lines):
        match = unset_match(line)
        if match:
            lines[idx] = f"{config.config_prefix}{match.group(1)}=n"
    lines[-1] += "\n"
    config._write_if_changed(filename, "\n".join(lines))


def write_header(deprecated_options: DeprecatedOptions, config: kconfiglib.Kconfig, filename: str) -> None:
    idf_version = os.environ.get("IDF_VERSION", "")
    CONFIG_HEADING = f"""/*
 * Automatically generated file. DO NOT EDIT.
 * Espressif IoT Development Framework (ESP-IDF) {idf_version} Configuration Header
 */
#pragma once
"""
    config.write_autoconf(filename, header=CONFIG_HEADING)
    deprecated_options.append_header(config, filename)


def write_cmake(deprecated_options: DeprecatedOptions, config: kconfiglib.Kconfig, filename: str) -> None:
    with open(filename, "w") as f:
        tmp_dep_list = []
        prefix = config.config_prefix

        f.write(
            textwrap.dedent(
                """#
                # Automatically generated file. DO NOT EDIT.
                # Espressif IoT Development Framework (ESP-IDF) Configuration cmake include file
                #
                """
            )
        )

        configs_list = list()

        def write_node(node: kconfiglib.MenuNode):
            sym = node.item
            if not isinstance(sym, kconfiglib.Symbol):
                return

            if sym.config_string:
                val = sym.str_value
                if sym.orig_type == kconfiglib.BOOL and val == "n":
                    val = ""  # write unset values as empty variables
                elif sym.orig_type == kconfiglib.STRING:
                    val = kconfiglib.escape(val)
                elif sym.orig_type == kconfiglib.HEX:
                    val = hex(int(val, 16))  # ensure 0x prefix
                f.write(f'set({prefix}{sym.name} "{val}")\n')

                configs_list.append(prefix + sym.name)
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
    config_dict = {}

    def write_node(node: kconfiglib.MenuNode) -> None:
        sym = node.item
        if not isinstance(sym, kconfiglib.Symbol):
            return

        if sym.config_string:
            val = sym.str_value
            if not val and sym.type in (
                kconfiglib.INT,
                kconfiglib.HEX,
            ):
                print(
                    f"warning: {sym.name} has no value set in the configuration."
                    " This can be caused e.g. by missing default value for the current chip version."
                )
                val = None
            elif sym.type == kconfiglib.BOOL:
                val = val != "n"
            elif sym.type == kconfiglib.HEX:
                val = int(val, 16)
            elif sym.type == kconfiglib.INT:
                val = int(val)
            config_dict[sym.name] = val

    for n in config.node_iter(False):
        write_node(n)
    return config_dict


def write_json(_, config: kconfiglib.Kconfig, filename: str) -> None:
    config_dict = get_json_values(config)
    with open(filename, "w") as f:
        json.dump(config_dict, f, indent=4, sort_keys=True)


def get_menu_node_id(node: kconfiglib.MenuNode) -> str:
    """Given a menu node, return a unique id
    which can be used to identify it in the menu structure

    Will either be the config symbol name, or a menu identifier
    'slug'

    """
    try:
        if not isinstance(node.item, kconfiglib.Choice):
            return str(node.item.name)  # type: ignore
    except AttributeError:
        pass

    result = []
    while node.parent is not None and node.prompt:
        slug = re.sub(r"\W+", "-", node.prompt[0]).lower()
        result.append(slug)
        node = node.parent

    return "-".join(reversed(result))


def write_json_menus(_, config: kconfiglib.Kconfig, filename: str) -> None:
    existing_ids: Set[str] = set()
    result: List = []  # root level items
    node_lookup: Dict = {}  # lookup from MenuNode to an item in result

    def write_node(node: kconfiglib.MenuNode) -> None:
        try:
            json_parent = node_lookup[node.parent]["children"]
        except KeyError:
            assert (
                node.parent not in node_lookup
            )  # if fails, we have a parent node with no "children" entity (ie a bug)
            json_parent = result  # root level node

        # node.kconfig.y means node has no dependency,
        if node.dep is node.kconfig.y:
            depends = None
        else:
            depends = kconfiglib.expr_str(node.dep)

        try:
            # node.is_menuconfig is True in newer kconfiglibs for menus and choices as well
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
            if is_menuconfig:
                sym = node.item
                new_json["name"] = sym.name  # type: ignore
                new_json["help"] = node.help
                new_json["is_menuconfig"] = is_menuconfig
                greatest_range = None
                if isinstance(sym, (kconfiglib.Symbol, kconfiglib.MenuNode)) and len(sym.ranges) > 0:
                    # Note: Evaluating the condition using kconfiglib's expr_value
                    # should have one condition which is true
                    for min_range, max_range, cond_expr in sym.ranges:
                        if kconfiglib.expr_value(cond_expr):
                            greatest_range = [min_range, max_range]
                new_json["range"] = greatest_range

        elif isinstance(node.item, kconfiglib.Symbol):
            sym = node.item
            greatest_range = None
            if len(sym.ranges) > 0:
                # Note: Evaluating the condition using kconfiglib's expr_value
                # should have one condition which is true
                for min_range, max_range, cond_expr in sym.ranges:
                    if kconfiglib.expr_value(cond_expr):
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
            node_id = get_menu_node_id(node)
            if node_id in existing_ids:
                raise RuntimeError(
                    f"Config file contains two items with the same id: {node_id} ({node.prompt[0] if node.prompt else ''}). "
                    "Please rename one of these items to avoid ambiguity."
                )
            new_json["id"] = node_id

            json_parent.append(new_json)
            node_lookup[node] = new_json

    for n in config.node_iter():
        write_node(n)
    with open(filename, "w") as f:
        f.write(json.dumps(result, sort_keys=True, indent=4))


def write_docs(deprecated_options: DeprecatedOptions, config: kconfiglib.Kconfig, filename: str) -> None:
    try:
        target = os.environ["IDF_TARGET"]
    except KeyError:
        print("IDF_TARGET environment variable must be defined!")
        sys.exit(1)

    visibility = gen_kconfig_doc.ConfigTargetVisibility(config, target)
    gen_kconfig_doc.write_docs(config, visibility, filename)
    deprecated_options.append_doc(config, visibility, filename)


def update_if_changed(source: str, destination: str) -> None:
    with open(source, "r") as f:
        source_contents = f.read()

    if os.path.exists(destination):
        with open(destination, "r") as f:
            dest_contents = f.read()
        if source_contents == dest_contents:
            return  # nothing to update

    with open(destination, "w") as f:
        f.write(source_contents)


OUTPUT_FORMATS = {
    "config": write_config,
    "header": write_header,
    "cmake": write_cmake,
    "docs": write_docs,
    "json": write_json,
    "json_menus": write_json_menus,
    "savedefconfig": write_min_config,
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

    parser.add_argument("--kconfig", help="KConfig file with config item definitions", required=True)

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

    for fmt, filename in args.output:
        if fmt not in OUTPUT_FORMATS.keys():
            print("Format '%s' not recognised. Known formats: %s" % (fmt, OUTPUT_FORMATS.keys()))
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
    config = kconfiglib.Kconfig(args.kconfig, parser_version=parser_version)
    config.warn_assign_redun = False
    config.warn_assign_override = False

    sdkconfig_renames_sep = ";" if args.list_separator == "semicolon" else " "
    sdkconfig_renames = [args.sdkconfig_rename] if args.sdkconfig_rename else []
    sdkconfig_renames_from_env = os.environ.get("COMPONENT_SDKCONFIG_RENAMES")
    if sdkconfig_renames_from_env:
        sdkconfig_renames += sdkconfig_renames_from_env.split(sdkconfig_renames_sep)
    deprecated_options = DeprecatedOptions(config.config_prefix, path_rename_files=sdkconfig_renames)

    if len(args.defaults) > 0:

        def _replace_empty_assignments(path_in, path_out):  # empty assignment: CONFIG_FOO=
            with open(path_in, "r") as f_in, open(path_out, "w") as f_out:
                for line_num, line in enumerate(f_in, start=1):
                    line = line.strip()
                    if line.endswith("="):
                        line += "n"
                        print("{}:{} line was updated to {}".format(path_out, line_num, line))
                    f_out.write(line)
                    f_out.write("\n")

        # always load defaults first, so any items which are not defined in the args.config
        # will have the default defined in the defaults file
        for name in args.defaults:
            print("Loading defaults file %s..." % name)
            if not os.path.exists(name):
                raise RuntimeError("Defaults file not found: %s" % name)
            try:
                with tempfile.NamedTemporaryFile(prefix="kconfgen_tmp", delete=False) as f:
                    temp_file1 = f.name
                with tempfile.NamedTemporaryFile(prefix="kconfgen_tmp", delete=False) as f:
                    temp_file2 = f.name
                deprecated_options.replace(sdkconfig_in=name, sdkconfig_out=temp_file1)
                _replace_empty_assignments(temp_file1, temp_file2)
                config.load_config(temp_file2, replace=False)

                for symbol, value in config.missing_syms:
                    if deprecated_options.get_new_option(symbol) is None:
                        print(f"warning: unknown kconfig symbol '{symbol}' assigned to '{value}' in {name}")
            finally:
                try:
                    os.remove(temp_file1)
                    os.remove(temp_file2)
                except OSError:
                    pass

    # If previous sdkconfig file exists, load it
    if args.config and os.path.exists(args.config):
        # ... but replace deprecated options before that
        with tempfile.NamedTemporaryFile(prefix="kconfgen_tmp", delete=False) as f:
            temp_file = f.name
        try:
            deprecated_options.replace(sdkconfig_in=args.config, sdkconfig_out=temp_file)
            config.load_config(temp_file, replace=False)
            update_if_changed(temp_file, args.config)
        finally:
            try:
                os.remove(temp_file)
            except OSError:
                pass

    if args.dont_write_deprecated:
        # The deprecated object was useful until now for replacements. Now it will be redefined with no configurations
        # and as the consequence, it won't generate output with deprecated statements.
        deprecated_options = DeprecatedOptions("", path_rename_files=[])

    # Output the files specified in the arguments
    for output_type, filename in args.output:
        with tempfile.NamedTemporaryFile(prefix="kconfgen_tmp", delete=False) as f:
            temp_file = f.name
        try:
            output_function = OUTPUT_FORMATS[output_type]
            output_function(deprecated_options, config, temp_file)
            update_if_changed(temp_file, filename)
        finally:
            try:
                os.remove(temp_file)
            except OSError:
                pass
