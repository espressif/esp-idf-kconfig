# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0

import re
from collections import defaultdict
from typing import TYPE_CHECKING
from typing import DefaultDict
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from .constants import DEP_OP_BEGIN
from .constants import DEP_OP_END

if TYPE_CHECKING:
    from .core import Kconfig
    from .core import Symbol


class DeprecatedOptions:
    """Manages deprecated-to-new config option rename mappings from sdkconfig.rename files.

    Parses rename files and provides lookup methods for mapping deprecated option names
    to their replacements (and vice versa), with support for boolean inversion.
    Also generates deprecated compatibility blocks for sdkconfig and C header output.
    """

    _RENAME_FILE_NAME = "sdkconfig.rename"

    def __init__(self, config_prefix: str, path_rename_files: List[str] = [], encoding: str = "utf-8"):
        self.config_prefix = config_prefix
        self.encoding = encoding
        # sdkconfig.renames specification: each line contains a pair of config options separated by whitespace(s).
        # The first option is the deprecated one, the second one is the new one.
        # The new option can be prefixed with '!' to indicate inversion (n/not set -> y, y -> n).
        self.rename_line_regex = re.compile(
            rf"#.*|\s*\n|(?P<old>{self.config_prefix}[a-zA-Z_0-9]+)\s+(?P<new>!?{self.config_prefix}[A-Z_0-9]+)"
        )

        # r_dic maps deprecated options to new options; rev_r_dic maps in the opposite direction
        # inversions is a list of deprecated options which will be inverted (n/not set -> y, y -> n)
        self.r_dic: Dict[str, str]
        self.rev_r_dic: DefaultDict[str, List]
        self.inversions: List
        self.r_dic, self.rev_r_dic, self.inversions = self._parse_replacements(path_rename_files)

    def parse_line(self, line: str) -> Optional[re.Match]:
        """Parse a single line from a sdkconfig.rename file. Returns a match or None on syntax error."""
        return self.rename_line_regex.match(line)

    def remove_config_prefix(self, string: str) -> str:
        """Strip the CONFIG_ (or !CONFIG_) prefix from an option name."""
        if string.startswith(self.config_prefix):
            return string[len(self.config_prefix) :]
        elif string.startswith("!" + self.config_prefix):
            return string[len("!" + self.config_prefix) :]
        else:
            return ""

    def _parse_replacements(
        self, rename_paths: List[str]
    ) -> Tuple[Dict[str, str], DefaultDict[str, List[str]], List[str]]:
        """Parse all sdkconfig.rename files and build the rename dictionaries."""
        rep_dic: Dict[str, str] = {}
        rev_rep_dic: DefaultDict[str, List[str]] = defaultdict(list)
        inversions: List[str] = []

        for rename_path in rename_paths:
            with open(rename_path, encoding=self.encoding) as rename_file:
                for line_number, line in enumerate(rename_file, start=1):
                    parsed_line = self.parse_line(line)
                    if not parsed_line:
                        raise RuntimeError(f"Syntax error in {rename_path} (line {line_number})")
                    if not parsed_line["old"]:
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
                                f"Error in {rename_path} (line {line_number}): "
                                f"Config {opt} is not prefixed with {self.config_prefix}"
                            )
                    if dep_opt == new_opt:
                        raise RuntimeError(
                            f"Error in {rename_path} (line {line_number}): "
                            f"Replacement name is the same as original name ({dep_opt})."
                        )
                    rep_dic[dep_opt] = new_opt
                    rev_rep_dic[new_opt].append(dep_opt)
                    if parsed_line["new"].startswith("!"):
                        inversions.append(dep_opt)

        return rep_dic, rev_rep_dic, inversions

    @property
    def has_entries(self) -> bool:
        """True if any deprecated-to-new mappings exist."""
        return len(self.r_dic) > 0

    def is_inversion(self, deprecated_option: str) -> bool:
        """True if the deprecated option uses boolean inversion (n <-> y)."""
        return deprecated_option in self.inversions

    def get_deprecated_option(self, new_option: str) -> list:
        """Return all deprecated aliases that map to the given new option name."""
        return self.rev_r_dic.get(new_option, [])

    def get_new_option(self, deprecated_option: str) -> Optional[str]:
        """Return the new option name for a deprecated option, or None if not found."""
        return self.r_dic.get(deprecated_option, None)

    def _deprecated_config_string(self, sym: "Symbol", dep_name: str) -> str:
        """Generate a sdkconfig line for a deprecated alias based on the symbol's type and value.

        Uses the symbol's actual type and value rather than text manipulation,
        producing the correct config line format (e.g., CONFIG_DEP=y, CONFIG_DEP="val").
        For inverted boolean mappings, the value is flipped.
        """
        from .core import BOOL  # noqa: I001
        from .core import HEX
        from .core import STRING
        from .core import escape

        prefix = self.config_prefix
        val = sym.str_value
        is_inv = dep_name in self.inversions

        if sym.orig_type == BOOL:
            if is_inv:
                val = "n" if val == "y" else "y"
            if val == "n":
                return f"# {prefix}{dep_name} is not set\n"
            return f"{prefix}{dep_name}={val}\n"

        elif sym.orig_type == STRING:
            return f'{prefix}{dep_name}="{escape(val)}"\n'

        elif sym.orig_type == HEX:
            if not val.startswith(("0x", "0X")):
                val = "0x" + val
            return f"{prefix}{dep_name}={val}\n"

        else:
            return f"{prefix}{dep_name}={val}\n"

    def deprecated_config_contents(self, config: "Kconfig") -> str:
        """Generate the deprecated options block for sdkconfig output.

        Iterates all defined symbols that have deprecated aliases and produces
        config lines using deprecated names, wrapped in DEP_OP_BEGIN/END markers.
        """
        from .core import Symbol

        tmp_list = []

        for n in config.node_iter():
            item = n.item
            if isinstance(item, Symbol) and item.env_var is None:
                if item.name in self.rev_r_dic:
                    if item.config_string:
                        for dep_name in self.rev_r_dic[item.name]:
                            tmp_list.append(self._deprecated_config_string(item, dep_name))

        if tmp_list:
            return "\n{}\n{}{}\n".format(DEP_OP_BEGIN, "".join(tmp_list), DEP_OP_END)
        return ""

    def deprecated_header_contents(self, config: "Kconfig") -> str:
        """Generate the deprecated #define section for C header output.

        Produces #define aliases mapping deprecated names to their new names
        (with ! prefix for inverted booleans). Only emits defines for symbols
        that are actually set (non-default).
        """
        from .core import BOOL  # noqa: I001
        from .core import FLOAT
        from .core import HEX
        from .core import INT
        from .core import STRING

        def _opt_defined(opt):
            if opt.orig_type == BOOL and opt.str_value != "n":
                return True
            elif opt.orig_type in (INT, STRING, HEX, FLOAT) and opt.str_value != "":
                return True
            return False

        if not self.r_dic:
            return ""

        chunks = ["\n/* List of deprecated options */\n"]
        has_defines = False
        for dep_opt in sorted(self.r_dic):
            new_opt = self.r_dic[dep_opt]
            if new_opt in config.syms and _opt_defined(config.syms[new_opt]):
                has_defines = True
                chunks.append(
                    "#define {}{} {}{}{}\n".format(
                        self.config_prefix,
                        dep_opt,
                        "!" if dep_opt in self.inversions else "",
                        self.config_prefix,
                        new_opt,
                    )
                )

        return "".join(chunks) if has_defines else ""
