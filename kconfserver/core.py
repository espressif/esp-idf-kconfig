#!/usr/bin/env python
# SPDX-FileCopyrightText: 2024-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
#
# Long-running server process uses stdin & stdout to communicate JSON
# with a caller
#
import argparse
import json
import os
import sys
import tempfile
from json import JSONDecodeError
from typing import Dict
from typing import List

import esp_kconfiglib.core as kconfiglib
import kconfgen.core as kconfgen
from esp_idf_kconfig import __version__

# Min/Max supported protocol versions
MIN_PROTOCOL_VERSION = 1
MAX_PROTOCOL_VERSION = 3


def main():
    parser = argparse.ArgumentParser(
        description="kconfserver.py v%s - Config Generation Tool" % __version__,
        prog=os.path.basename(sys.argv[0]),
    )

    parser.add_argument("--config", help="Project configuration settings", required=True)

    parser.add_argument("--kconfig", help="Kconfig file with config item definitions", required=True)

    parser.add_argument(
        "--sdkconfig-rename",
        help="File with deprecated Kconfig options",
        required=False,
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
        "--version",
        help="Set protocol version to use on initial status",
        type=int,
        default=MAX_PROTOCOL_VERSION,
    )

    args = parser.parse_args()

    if args.version < MIN_PROTOCOL_VERSION:
        print(
            "Version %d is older than minimum supported protocol version %d. Client is much older than ESP-IDF version?"
            % (args.version, MIN_PROTOCOL_VERSION)
        )

    if args.version > MAX_PROTOCOL_VERSION:
        print(
            "Version %d is newer than maximum supported protocol version %d. Client is newer than ESP-IDF version?"
            % (args.version, MAX_PROTOCOL_VERSION)
        )

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

    run_server(args.kconfig, args.config, args.sdkconfig_rename)


def run_server(kconfig, sdkconfig, sdkconfig_rename, default_version=MAX_PROTOCOL_VERSION):
    config = kconfiglib.Kconfig(kconfig)
    sdkconfig_renames = [sdkconfig_rename] if sdkconfig_rename else []
    sdkconfig_renames_from_env = os.environ.get("COMPONENT_SDKCONFIG_RENAMES")
    if sdkconfig_renames_from_env:
        sdkconfig_renames += sdkconfig_renames_from_env.split(";")
    deprecated_options = kconfgen.DeprecatedOptions(config.config_prefix, path_rename_files=sdkconfig_renames)
    f_o = tempfile.NamedTemporaryFile(mode="w+b", delete=False)
    try:
        with open(sdkconfig, mode="rb") as f_i:
            f_o.write(f_i.read())
        f_o.close()  # need to close as DeprecatedOptions will reopen, and Windows only allows one open file
        deprecated_options.replace(sdkconfig_in=f_o.name, sdkconfig_out=sdkconfig)
    finally:
        os.unlink(f_o.name)
    config.load_config(sdkconfig)

    print("Server running, waiting for requests on stdin...", file=sys.stderr)

    config_dict = kconfgen.get_json_values(config)
    ranges_dict = get_ranges(config)
    visible_dict = get_visible(config)
    if default_version >= 3:
        defaults_dict = get_sym_default_value_dict(config)

    if default_version == 1:
        # V1: no 'visibility' key, send value None for any invisible item
        values_dict = dict((k, v if visible_dict[k] else False) for (k, v) in config_dict.items())
        json.dump({"version": 1, "values": values_dict, "ranges": ranges_dict}, sys.stdout)
    else:
        # V2 onwards: separate visibility from version
        resp = {
            "version": default_version,
            "values": config_dict,
            "ranges": ranges_dict,
            "visible": visible_dict,
        }

        # V3 onwards: send which values have default values
        if default_version >= 3:
            resp["defaults"] = defaults_dict

        json.dump(
            resp,
            sys.stdout,
        )
    print("\n")
    sys.stdout.flush()

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            req = json.loads(line)
        except JSONDecodeError as e:
            response = {
                "version": default_version,
                "error": [f"JSON formatting error: {e}"],
            }
            json.dump(response, sys.stdout)
            print("\n")
            sys.stdout.flush()
            continue
        before = kconfgen.get_json_values(config)
        before_ranges = get_ranges(config)
        before_visible = get_visible(config)

        if req["version"] >= 3:
            before_defaults = get_sym_default_value_dict(config)

        if "load" in req:  # load a new sdkconfig
            if req.get("version", default_version) == 1:
                # for V1 protocol, send all items when loading new sdkconfig.
                # (V2+ will only send changes, same as when setting an item)
                before = {}
                before_ranges = {}
                before_visible = {}

            # if no new filename is supplied, use existing sdkconfig path, otherwise update the path
            if req["load"] is None:
                req["load"] = sdkconfig
            else:
                sdkconfig = req["load"]

        if "save" in req:
            if req["save"] is None:
                req["save"] = sdkconfig
            else:
                sdkconfig = req["save"]

        error = handle_request(deprecated_options, config, req)

        after = kconfgen.get_json_values(config)
        after_ranges = get_ranges(config)
        after_visible = get_visible(config)
        if req["version"] >= 3:
            after_defaults = get_sym_default_value_dict(config)

        values_diff = diff(before, after)
        ranges_diff = diff(before_ranges, after_ranges)
        visible_diff = diff(before_visible, after_visible)
        if req["version"] >= 3:
            defaults_diff = diff(before_defaults, after_defaults)

        if req["version"] == 1:
            # V1 response, invisible items have value None
            for k in (k for (k, v) in visible_diff.items() if not v):
                values_diff[k] = None
            response = {"version": 1, "values": values_diff, "ranges": ranges_diff}
        else:
            # V2+ response, separate visibility values
            response = {
                "version": req["version"],
                "values": values_diff,
                "ranges": ranges_diff,
                "visible": visible_diff,
            }
            if req["version"] >= 3:
                # V3 onwards: send which values have default values
                response["defaults"] = defaults_diff

        if error:
            for err in error:
                print(f"Error: {err}", file=sys.stderr)
            response["error"] = error
        json.dump(response, sys.stdout)
        print("\n")
        sys.stdout.flush()


def get_sym_default_value_dict(config: kconfiglib.Kconfig) -> Dict[str, bool]:
    """
    Returns a dict with <config symbol>:<has active default value?> pairs.
    """
    defaults = dict()
    for sym in config.syms.values():
        defaults[sym.name] = sym.has_active_default_value()
    return defaults


def handle_request(deprecated_options, config, req):
    if "version" not in req:
        return ["All requests must have a 'version'"]

    if req["version"] < MIN_PROTOCOL_VERSION or req["version"] > MAX_PROTOCOL_VERSION:
        return [
            "Unsupported request version %d. Server supports versions %d-%d"
            % (req["version"], MIN_PROTOCOL_VERSION, MAX_PROTOCOL_VERSION)
        ]

    error = []

    if "load" in req:
        print("Loading config from %s..." % req["load"], file=sys.stderr)
        try:
            config.load_config(req["load"])
        except Exception as e:
            error += ["Failed to load from %s: %s" % (req["load"], e)]

    if "set" in req:
        handle_set(config, error, req["set"])

    if "reset" in req:
        if req["version"] >= 3:
            handle_reset(config, error, req["reset"])
        else:
            error += [f"Resetting config symbols is not supported in protocol version {req['version']}"]

    if "save" in req:
        try:
            print("Saving config to %s..." % req["save"], file=sys.stderr)
            kconfgen.write_config(deprecated_options, config, req["save"])
        except Exception as e:
            error += ["Failed to save to %s: %s" % (req["save"], e)]

    return error


def handle_reset(config: kconfiglib.Kconfig, error: List[str], to_reset: List[str]) -> None:
    """
    Reset the config symbols to their default values.
    If a symbol is not found, add an error message to the error list.

    Special name "all" can be used to reset all symbols at once.
    """
    # Reset the whole configuration to default values
    if "all" in to_reset:
        if kconfiglib._recursively_perform_action(config.top_node, kconfiglib._restore_default):
            print("Reset the whole configuration to default values")
        else:
            error.append("Failed to reset the whole configuration to default values")
        return

    # Theoretically, both menu ID and config symbol names can be uppercase, but "-" will always be in menu IDs
    # and never in config symbol names; in symbol name, it is forbidden by the grammar. And menu ID has a signature of
    # <parent-menu-names>-<menu-name>-<filename>-<linenr> => at least one dash (between filename and linenr) will always
    # be present.
    sym_names_to_reset = set(sym_name for sym_name in to_reset if "-" not in sym_name)
    menu_ids_to_reset = set(menu_name for menu_name in to_reset if "-" in menu_name)
    remainder = set(to_reset) - sym_names_to_reset - menu_ids_to_reset
    if remainder:
        error.append(f"Some items to reset were not symbols nor menus: {','.join(remainder)}")

    missing_syms = [sym_name for sym_name in sym_names_to_reset if sym_name not in config.syms]
    missing_menus = [menu_name for menu_name in menu_ids_to_reset if menu_name not in config.menu_ids]

    if missing_syms:
        error.append(f"The following config symbol(s) were not found: {', '.join(missing_syms)}")
    if missing_menus:
        error.append(f"The following menu(s) were not found: {', '.join(missing_menus)}")

    # replace name keys with the full config symbol for each key:
    syms = list(config.syms[sym] for sym in sym_names_to_reset if sym not in missing_syms)
    menus = list(config.menu_ids[menu] for menu in menu_ids_to_reset if menu not in missing_menus)

    for sym in syms:
        if kconfiglib._restore_default(sym.nodes[0]):
            print(f"Reset {sym.name} to default value")
        else:
            error.append(f"Failed to reset {sym.name} to default value")

    for menu in menus:
        if kconfiglib._recursively_perform_action(menu, kconfiglib._restore_default):
            print(f"Reset menu {menu.id} to default values")
        else:
            error.append(f"Failed to reset menu {menu.id} to default values")


def handle_set(config, error, to_set):
    missing = [k for k in to_set if k not in config.syms]
    if missing:
        error.append("The following config symbol(s) were not found: %s" % (", ".join(missing)))
    # replace name keys with the full config symbol for each key:
    to_set = dict((config.syms[k], v) for (k, v) in to_set.items() if k not in missing)

    # Work through the list of values to set, noting that
    # some may not be immediately applicable (maybe they depend
    # on another value which is being set). Therefore, defer
    # knowing if any value is unsettable until then end

    while len(to_set):
        set_pass = [(k, v) for (k, v) in to_set.items() if k.visibility]
        if not set_pass:
            break  # no visible keys left
        for sym, val in set_pass:
            if sym.type == kconfiglib.BOOL:
                if val is True:
                    sym.set_value(2)
                elif val is False:
                    sym.set_value(0)
                else:
                    error.append("Boolean symbol %s only accepts true/false values" % sym.name)
            elif sym.type == kconfiglib.HEX:
                try:
                    if not isinstance(val, int):
                        val = int(val, 16)  # input can be a decimal JSON value or a string of hex digits
                    sym.set_value(hex(val))
                except ValueError:
                    error.append("Hex symbol %s can accept a decimal integer or a string of hex digits, only")
            else:
                sym.set_value(str(val))
            print("Set %s" % sym.name)
            del to_set[sym]

    if len(to_set):
        error.append(
            "The following config symbol(s) were not visible so were not updated: %s"
            % (", ".join(s.name for s in to_set))
        )


def diff(before, after):
    """
    Return a dictionary with the difference between 'before' and 'after',
    for items which are present in 'after' dictionary
    """
    diff = dict((k, v) for (k, v) in after.items() if before.get(k, None) != v)
    return diff


def get_ranges(config):
    ranges_dict = {}

    def is_base_n(i, n):
        try:
            int(i, n)
            return True
        except ValueError:
            return False

    def get_active_range(sym):
        """
        Returns a tuple of (low, high) integer values if a range
        limit is active for this symbol, or (None, None) if no range
        limit exists.
        """
        base = kconfiglib._TYPE_TO_BASE[sym.orig_type] if sym.orig_type in kconfiglib._TYPE_TO_BASE else 0

        try:
            for low_expr, high_expr, cond in sym.ranges:
                if kconfiglib.expr_value(cond):
                    low = int(low_expr.str_value, base) if is_base_n(low_expr.str_value, base) else 0
                    high = int(high_expr.str_value, base) if is_base_n(high_expr.str_value, base) else 0
                    return (low, high)
        except ValueError:
            pass
        return (None, None)

    def handle_node(node):
        sym = node.item
        if not isinstance(sym, kconfiglib.Symbol):
            return
        active_range = get_active_range(sym)
        if active_range[0] is not None:
            ranges_dict[sym.name] = active_range

    for n in config.node_iter():
        handle_node(n)
    return ranges_dict


def get_visible(config):
    """
    Return a dict mapping node IDs (config names or menu node IDs) to True/False for their visibility
    """
    result = {}
    menus = []

    # when walking the menu the first time, only
    # record whether the config symbols are visible
    # and make a list of menu nodes (that are not symbols)
    def handle_node(node):
        sym = node.item
        try:
            visible = sym.visibility != 0
            result[node] = visible
        except AttributeError:
            menus.append(node)

    for n in config.node_iter():
        handle_node(n)

    # now, figure out visibility for each menu. A menu is visible if any of its children are visible
    for m in reversed(menus):  # reverse to start at leaf nodes
        result[m] = any(v for (n, v) in result.items() if n.parent == m)

    # return a dict mapping the node ID to its visibility.
    result = dict((n.id, v) for (n, v) in result.items())

    return result
