# SPDX-FileCopyrightText: 2025-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0

"""
Kconfig configuration report.

Some diagnostics (e.g. multiply-defined symbols) cannot be emitted on the fly
because the full picture is only available after parsing completes.
KconfigReport caches those records and emits a structured summary at the end.
"""

import json
import os
import textwrap
from abc import ABC
from abc import abstractmethod
from collections import defaultdict
from typing import TYPE_CHECKING
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple
from typing import Union

from esp_pylib.logger import EspLog
from esp_pylib.logger import Verbosity
from esp_pylib.logger import log
from rich.console import Console
from rich.markup import escape

from .constants import DefaultsPolicy

if TYPE_CHECKING:
    from .core import Choice
    from .core import Kconfig
    from .core import Symbol

PRAGMA_PREFIX = "# ignore:"

STATUS_NONE = 0
STATUS_OK = 1
STATUS_OK_WITH_INFO = 2
STATUS_WARNING = 3
STATUS_ERROR = 4

VERBOSITY_QUIET = "quiet"  # Report only if there is an error
VERBOSITY_DEFAULT = "default"  # Report standard information
VERBOSITY_VERBOSE = "verbose"  # Report everything every time

REPORT_TO_PYLIB_VERBOSITY = {
    VERBOSITY_QUIET: Verbosity.SILENT,
    VERBOSITY_DEFAULT: Verbosity.NORMAL,
    VERBOSITY_VERBOSE: Verbosity.VERBOSE,
}


class CachingLog(EspLog):
    """
    Logger that caches all diagnostic messages while delegating to the real
    EspLog output.  Installed via ``EspLog.set_logger()`` so existing
    ``log.note(...)`` / ``log.warn(...)`` call sites are captured transparently.
    """

    _cache: List[Dict[str, str]]

    def __init__(self, cache: List[Dict[str, str]]):
        # copy settings from the previous EspLog instance
        prev = EspLog.instance
        prev_info_stream = getattr(prev, "_info_stream", None) if prev else None
        prev_options = dict(prev._options) if prev and hasattr(prev, "_options") else None
        super().__init__()
        self._cache = cache
        if prev_info_stream is not None:
            self._info_stream = prev_info_stream
        if prev_options is not None:
            self.set_console_options(**{k: v for k, v in prev_options.items() if k != "emoji"})

    def note(self, *args: Any) -> None:
        self._cache.append({"level": "note", "message": " ".join(str(a) for a in args)})
        super().note(*args)

    def warn(self, *args: Any, suggestion: Optional[str] = None) -> None:
        self._cache.append({"level": "warning", "message": " ".join(str(a) for a in args)})
        super().warn(*args, suggestion=suggestion)

    def err(self, *args: Any, suggestion: Optional[str] = None) -> None:
        self._cache.append({"level": "error", "message": " ".join(str(a) for a in args)})
        super().err(*args, suggestion=suggestion)

    def debug(self, *args: Any) -> None:
        self._cache.append({"level": "debug", "message": " ".join(str(a) for a in args)})
        super().debug(*args)


class Area(ABC):
    """
    Abstract class holding the base structure of every area in the report.
    """

    def __init__(self, title: str, ignore_codes: Set[str], info_string: str):
        """
        title:
        info_string:
            Both are used to describe the area in the report.
            Title is printed every time specific area is printed, info string provides additional information
            about the area, which may further help to understand the issue.
        """
        self.title: str = title
        self.info_string: str = info_string

        """
        ignored_sc:
            Dictionary of Symbol/Choice names which should be ignored in the report.
        """
        self.ignored_sc: Dict[str, Set[str]] = {"configs": set(), "choices": set()}
        """
        ignore_codes:
            Ignore codes which are used to ignore reporting of certain areas for certain symbols
            (e.g. multiple-definition).
            Ignore codes are written after PRAGMA_PREFIX in the Kconfig files (e.g. # ignore: multiple-definition).
        """
        self.ignore_codes: Set[str] = ignore_codes

    @abstractmethod
    def add_record(self, sym_or_choice: "Union[Symbol, Choice]", **kwargs: Optional[dict]) -> None:
        """
        Adding a new record to the area.
        All records relates to the specific Symbol/Choice and may contain additional information in kwargs.
        """
        pass

    def _apply_ignores(self) -> None:
        """
        Apply ignores to the area. Can be called multiple times.
        If given area does not support ignore codes, this method does nothing.
        """
        pass

    def add_ignore(self, sym_or_choice: "Union[Symbol, Choice]") -> None:
        """
        Add a Symbol/Choice to the ignore list of the area.
        Raises AttributeError if the area does not support ignore codes.
        """
        raise AttributeError(f"{self.__class__.__name__} does not support ignore codes.")

    @abstractmethod
    def report_severity(self) -> int:
        """
        If given area has nothing to report, STATUS_OK should be returned.
        Otherwise, STATUS_OK_WITH_INFO, STATUS_WARNING or STATUS_ERROR should be returned,
        depending how severe record in given area is.
        """
        pass

    @abstractmethod
    def emit(self, verbosity: str) -> None:
        """
        Emit the area sub-report via the logger.
        """
        pass

    @abstractmethod
    def return_json(self) -> Optional[dict]:
        """
        Return the area report in JSON format.
        """
        ret_json = dict()
        ret_json["title"] = self.title
        ret_json["severity"] = self.severity_to_str(self.report_severity())
        return ret_json

    @abstractmethod
    def reset(self) -> None:
        """
        Reset the area to its initial state, clearing all records and data.
        """
        pass

    def _log_for_severity(self, message: str, suggestion: Optional[str] = None) -> None:
        """
        Print a single log message at the severity level of this area.
        """
        sev = self.report_severity()
        if sev == STATUS_ERROR:
            log.err(message, suggestion=suggestion)
        elif sev == STATUS_WARNING:
            log.warn(message, suggestion=suggestion)
        else:
            log.note(message)

    @staticmethod
    def severity_to_str(severity: int) -> str:
        if severity == STATUS_OK:
            return "OK"
        elif severity == STATUS_OK_WITH_INFO:
            return "Info"
        elif severity == STATUS_WARNING:
            return "Warning"
        else:
            return "Error"


class DefaultValuesArea(Area):
    """
    Area for reporting any problems with default values:
    * Different values between sdkconfig and Kconfig files
    * Promptless symbols with different values between sdkconfig and Kconfig files
      This may be intentional, but e.g. if a promptless symbol is attempted to be
      user-set via sdkconfig.defaults, it is something users should care about,
      because it won't work (promptless symbols cannot be user-set).
      There are some exceptions in a KCONFIG_PROMPTLESS_NO_WARN
      environment variable.
    """

    def __init__(self, verbosity: str):
        super().__init__(
            title="Default Value Mismatch",
            ignore_codes=set(),
            info_string=textwrap.dedent(
                """\
                This area reports issues with default values of the config options.
                For more information, please visit https://docs.espressif.com/projects/esp-idf-kconfig/en/latest/kconfiglib/configuration-report.html#default-value-mismatch
                """
            ),
        )
        self.verbosity: str = verbosity

        # (sym_name, kconfig_value, sdkconfig_value, loc)
        self.changed_defaults: Set[Tuple[str, str, str, str]] = set()
        # (sym_name, kconfig_value, sdkconfig_value, is_user_set, loc)
        self.changed_values_promptless: Set[Tuple[str, str, str, bool, str]] = set()
        # (choice_name, kconfig_selection, sdkconfig_selection, loc)
        self.changed_choices: Set[Tuple[str, str, str, str]] = set()

    @staticmethod
    def _first_loc(sym_or_choice: "Union[Symbol, Choice]") -> str:
        """
        Return ``file:line`` for the first definition node, or empty string.
        """
        if sym_or_choice.nodes:
            node = sym_or_choice.nodes[0]
            return f"{node.filename}:{node.linenr}"
        return ""

    def add_record(self, sym_or_choice: "Union[Symbol, Choice]", **kwargs: Optional[dict]) -> None:
        promptless: bool = kwargs.get("promptless", False)  # type: ignore
        record_type: str = kwargs.get("record_type", "symbol")  # type: ignore
        loc = self._first_loc(sym_or_choice)
        if record_type == "symbol":  # Symbol
            record = (
                str(sym_or_choice.name),
                str(sym_or_choice.str_value),
                str(getattr(sym_or_choice, "_sdkconfig_value", "") or ""),
                loc,
            )
            if not promptless:
                self.changed_defaults.add(record)
            else:
                # sdkconfig value is still set even for promptless symbols, so we can decide
                # if sdkconfig contained default value or not
                record_with_default_flag = record[:3] + (
                    getattr(sym_or_choice, "_user_value", None) is not None,
                    loc,
                )
                self.changed_values_promptless.add(record_with_default_flag)
        else:  # Choice
            record = (
                str(sym_or_choice.name or "nameless" + sym_or_choice.name_and_loc),
                str(sym_or_choice.selection.name if sym_or_choice.selection else "choice deselected"),  # type: ignore
                str(kwargs.get("sdkconfig_selection", False)),
                loc,
            )
            self.changed_choices.add(record)

    def report_severity(self) -> int:
        if self._nothing_to_report(self.verbosity):
            return STATUS_OK
        return STATUS_OK_WITH_INFO

    def _nothing_to_report(self, verbosity: str = VERBOSITY_VERBOSE) -> bool:
        """
        Check if there is nothing to report in the area.
        """
        return (
            not self.changed_defaults
            and not self.changed_choices
            and (verbosity != VERBOSITY_VERBOSE or not self.changed_values_promptless)
        )

    def emit(self, verbosity: str) -> None:
        if self._nothing_to_report(verbosity):
            return

        if self.changed_defaults:
            for sym_name, kconfig_value, sdkconfig_value, loc in self.changed_defaults:
                prefix = f"{escape(loc)}: " if loc else ""
                self._log_for_severity(
                    f"{prefix}{sym_name}: Kconfig default value: {kconfig_value}, "
                    f"sdkconfig default value: {sdkconfig_value}"
                )

        if self.changed_choices:
            for choice_name, kconfig_selection, sdkconfig_selection, loc in self.changed_choices:
                prefix = f"{escape(loc)}: " if loc else ""
                self._log_for_severity(
                    f"{prefix}{choice_name}: Kconfig default selection: {kconfig_selection}, "
                    f"sdkconfig default selection: {sdkconfig_selection}"
                )

        if verbosity == VERBOSITY_VERBOSE and self.changed_values_promptless:
            for sym_name, kconfig_value, sdkconfig_value, is_user_set, loc in self.changed_values_promptless:
                prefix = f"{escape(loc)}: " if loc else ""
                log.note(
                    f"{prefix}{sym_name} (promptless): Kconfig default value: {kconfig_value}, "
                    f"sdkconfig value {sdkconfig_value} "
                    f"{'(user-set)' if is_user_set else '(default)'} "
                    "will be ignored"
                )

        log.hint(self.info_string.strip())

    def return_json(self) -> Optional[dict]:
        """
        Return the area report in JSON format.
        """
        if self._nothing_to_report():
            return None
        ret_json = super().return_json()
        if not ret_json:
            ret_json = dict()
        ret_json["data"] = dict()

        if self.changed_defaults:
            ret_json["data"]["changed_defaults"] = list()
            for sym_name, kconfig_value, sdkconfig_value, _loc in self.changed_defaults:
                ret_json["data"]["changed_defaults"].append(
                    {"name": sym_name, "kconfig_default": kconfig_value, "sdkconfig_default": sdkconfig_value}
                )
        if self.changed_values_promptless:  # There is all the info in json every time
            ret_json["data"]["mismatched_promptless"] = list()
            for sym_name, kconfig_value, sdkconfig_value, is_user_set, _loc in self.changed_values_promptless:
                ret_json["data"]["mismatched_promptless"].append(
                    {
                        "name": sym_name,
                        "kconfig_value": kconfig_value,
                        "sdkconfig_value": sdkconfig_value,
                        "sdkconfig_value_is_default": is_user_set,
                    }
                )
        if self.changed_choices:
            ret_json["data"]["changed_choices"] = list()
            for choice_name, kconfig_selection, sdkconfig_selection, _loc in self.changed_choices:
                ret_json["data"]["changed_choices"].append(
                    {
                        "name": choice_name,
                        "kconfig_selection": kconfig_selection,
                        "sdkconfig_selection": sdkconfig_selection,
                    }
                )

        return ret_json

    def reset(self) -> None:
        """
        Reset the area to its initial state, clearing all records and data.
        """
        self.changed_defaults.clear()
        self.changed_values_promptless.clear()
        self.changed_choices.clear()


class MultipleDefinitionArea(Area):
    """
    Multiple definition: having two or more definitions of the Symbol/Choice with the same name.
    NOTE: Currently, MultipleDefinitionArea cause only info instead of warning. This will be changed in the future.
    """

    def __init__(self):
        super().__init__(
            title="Multiple Symbol/Choice Definitions",
            ignore_codes=("multiple-definition", "MD"),
            info_string=textwrap.dedent(
                """\
                Multiple definitions of the same Symbol name are allowed by the Kconfig syntax.
                However, it may happen that e.g. two different components accidentally define the same Symbol name,
                which may lead to unexpected behavior.
                """
            ),
        )

        # name -> set of (filename, linenr) tuples
        self.multiple_definitions: Dict[str, Set[Tuple[str, int]]] = dict()

    def add_record(self, sym_or_choice: "Union[Symbol, Choice]", **kwargs: Optional[dict]) -> None:
        """
        kwargs:
            occurrences: Set[Tuple[str, int]]  — (filename, linenr) pairs
        """
        occurrences: Set[Tuple[str, int]] = kwargs.get("occurrences", set())  # type: ignore
        sym_or_choice_name = sym_or_choice.name or "unnamed choice"
        if sym_or_choice_name not in self.multiple_definitions:
            self.multiple_definitions[sym_or_choice_name] = occurrences
        self.multiple_definitions[sym_or_choice_name].update(occurrences)

    def add_ignore(self, sym_or_choice):
        if sym_or_choice.__class__.__name__ == "Symbol":
            self.ignored_sc["configs"].add(sym_or_choice.name)
        else:
            self.ignored_sc["choices"].add(sym_or_choice.name)

    def _apply_ignores(self) -> None:
        """
        Apply ignored symbols and choices to the multiple definitions.
        Can be called multiple times.
        """
        for sc_names in self.ignored_sc.values():
            for name in sc_names:
                self.multiple_definitions.pop(name, None)

    def report_severity(self) -> int:
        self._apply_ignores()
        return STATUS_OK if not self.multiple_definitions else STATUS_OK_WITH_INFO

    def emit(self, verbosity: str) -> None:
        self._apply_ignores()

        if not self.multiple_definitions:
            return

        for name, locs in self.multiple_definitions.items():
            sorted_locs = sorted(locs)
            for filename, linenr in sorted_locs:
                others = [f"{escape(f)}:{ln}" for f, ln in sorted_locs if (f, ln) != (filename, linenr)]
                others_str = ", ".join(others)
                self._log_for_severity(
                    f"{escape(filename)}:{linenr}: {name} has multiple definitions (also at {others_str})"
                )

        log.hint(
            "Multiple definitions will have higher severity in the future. See "
            "https://docs.espressif.com/projects/esp-idf-kconfig/en/latest/kconfiglib/configuration-report.html"
            "#multiple-symbol-or-choice-definition"
        )

    def return_json(self) -> Optional[dict]:
        """
        Return the area report in JSON format.
        """
        if not self.multiple_definitions:
            return None
        ret_json = super().return_json()
        if not ret_json:
            ret_json = dict()
        ret_json["data"] = dict()
        for name, locs in self.multiple_definitions.items():
            ret_json["data"][name] = [f"    {f}:{ln}" for f, ln in sorted(locs)]
        return ret_json

    def reset(self) -> None:
        """
        Reset the area to its initial state, clearing all records and data.
        """
        self.multiple_definitions.clear()


class MultipleAssignmentArea(Area):
    """
    This area reports multiple assignments to the same symbol within a single file.
    """

    def __init__(self):
        super().__init__(
            title="Multiple Assignments",
            ignore_codes=set(),
            info_string=(
                "Under normal circumstances, there should be only one (or none) assignment per config option. "
                "Multiple assignments mean somebody manually altered the sdkconfig file. "
                "If you edited the sdkconfig file intentionally, this area can be ignored."
            ),
        )

        # CONFIG_NAME: [(val, is_default?), (val, is_default?), ...]
        self.multiple_assignments_sym: Dict[Symbol, List[Tuple[str, bool]]] = defaultdict(list)
        # CHOICE_NAME: [(val, is_default?), (val, is_default?), ...]
        self.multiple_assignments_choice: Dict[Choice, List[Tuple[str, bool]]] = defaultdict(list)

    def add_record(self, sym_or_choice, **kwargs):
        """
        kwargs:
            new_value: str
            is_default: bool
        """
        if "new_value" not in kwargs.keys() or "is_default" not in kwargs.keys():
            raise AttributeError("New value and is_default must be specified for MultipleAssignmentArea.")
        if sym_or_choice.__class__.__name__ == "Symbol":
            if not self.multiple_assignments_sym[sym_or_choice]:
                # If this is the first time we are logging the data, we also need to log the first value
                self.multiple_assignments_sym[sym_or_choice] = [
                    (sym_or_choice.str_value, sym_or_choice._user_value is None)
                ]
            self.multiple_assignments_sym[sym_or_choice].append((kwargs["new_value"], kwargs["is_default"]))
        elif sym_or_choice.__class__.__name__ == "Choice":
            if not self.multiple_assignments_choice[sym_or_choice]:
                # If this is the first time we are logging the data, we also need to log the first selection
                self.multiple_assignments_choice[sym_or_choice] = [
                    (
                        sym_or_choice.selection.name if sym_or_choice.selection else "choice deselected",
                        sym_or_choice._user_selection is None,
                    )
                ]
            self.multiple_assignments_choice[sym_or_choice].append((kwargs["new_value"], kwargs["is_default"]))

    def report_severity(self) -> int:
        return STATUS_OK_WITH_INFO if (self.multiple_assignments_sym or self.multiple_assignments_choice) else STATUS_OK

    def emit(self, verbosity: str) -> None:
        if self.report_severity() is STATUS_OK:
            return

        for sym in self.multiple_assignments_sym:
            loc = f"{escape(sym.nodes[0].filename)}:{sym.nodes[0].linenr}: " if sym.nodes else ""
            vals = ", ".join(
                f"{val} ({'default' if is_default else 'user-set'})"
                for val, is_default in self.multiple_assignments_sym[sym]
            )
            self._log_for_severity(f"{loc}{sym.name} assigned multiple times: {vals} -> using {sym.str_value}")
        for choice in self.multiple_assignments_choice:
            loc = f"{escape(choice.nodes[0].filename)}:{choice.nodes[0].linenr}: " if choice.nodes else ""
            vals = ", ".join(
                f"{val} ({'default' if is_default else 'user-set'})"
                for val, is_default in self.multiple_assignments_choice[choice]
            )
            final = choice.selection.name if choice.selection else "choice deselected"
            self._log_for_severity(f"{loc}{choice.name} assigned multiple times: {vals} -> using {final}")

        log.hint(self.info_string)

    def return_json(self) -> Optional[dict]:
        if not self.multiple_assignments_sym and not self.multiple_assignments_choice:
            return None
        ret_json = super().return_json()
        if not ret_json:
            ret_json = dict()
        ret_json["data"] = dict()
        ret_json["data"]["symbols"] = dict()
        ret_json["data"]["choices"] = defaultdict(list)

        for sym in self.multiple_assignments_sym:
            ret_json["data"]["symbols"][sym.name] = {"values": dict(), "final_value": sym.str_value}
            for val, is_default in self.multiple_assignments_sym[sym]:
                ret_json["data"]["symbols"][sym.name]["values"][val] = "default" if is_default else "user-set"

        for choice in self.multiple_assignments_choice:
            ret_json["data"]["choices"][choice.name] = {
                "values": dict(),
                "final_value": choice.selection.name if choice.selection else "choice deselected",
            }
            for val, is_default in self.multiple_assignments_choice[choice]:
                ret_json["data"]["choices"][choice.name]["values"][val] = "default" if is_default else "user-set"

        return ret_json

    def reset(self) -> None:
        """
        Reset the area to its initial state, clearing all records and data.
        """
        self.multiple_assignments_sym.clear()
        self.multiple_assignments_choice.clear()


class DisabledSymbolArea(Area):
    """
    This area reports symbols that are set via sdkconfig[.defaults], but are not visible.
    """

    def __init__(self):
        super().__init__(
            title="Disabled Symbols/Choices With User-Set Value",
            ignore_codes=set(),
            info_string=(
                "Disabled symbols/choices are not written into sdkconfig file. Setting their user value has no effect."
            ),
        )
        self.hidden_symbols: Dict[Symbol, str] = dict()
        # None: every choice symbol user-set to n (choice invisible). Otherwise the last y symbol name
        # from sdkconfig (same order as deferred load).
        self.hidden_choices: Dict[Choice, Optional[str]] = dict()

    def add_record(self, sym_or_choice: "Union[Symbol, Choice]", **kwargs: Optional[dict]) -> None:
        """
        kwargs:
            user_value: str for symbols; Optional[str] for choices (None = all choice symbols n, invisible).
        """
        if "user_value" not in kwargs.keys():
            raise AttributeError("User value must be specified for DisabledSymbolArea.")
        # Choice symbols are ignored; choice will be reported separately.
        if sym_or_choice.__class__.__name__ == "Symbol" and not sym_or_choice.choice:  # type: ignore
            self.hidden_symbols[sym_or_choice] = kwargs["user_value"]  # type: ignore
        elif sym_or_choice.__class__.__name__ == "Choice":
            self.hidden_choices[sym_or_choice] = kwargs["user_value"]  # type: ignore

    def report_severity(self) -> int:
        return STATUS_OK_WITH_INFO if self.hidden_symbols or self.hidden_choices else STATUS_OK

    def emit(self, verbosity: str) -> None:
        if self.report_severity() == STATUS_OK:
            return

        for symbol in self.hidden_symbols:
            loc = f"{escape(symbol.nodes[0].filename)}:{symbol.nodes[0].linenr}: " if symbol.nodes else ""
            self._log_for_severity(
                f"{loc}{symbol.name} has user-set value {self.hidden_symbols[symbol]} "
                f"from {escape(symbol._user_source or '')} but is not visible (disabled dependency)"
            )
        for choice in self.hidden_choices:
            loc = f"{escape(choice.nodes[0].filename)}:{choice.nodes[0].linenr}: " if choice.nodes else ""
            user_source = choice._user_source or getattr(choice._user_selection, "_user_source", "")
            y_name = self.hidden_choices[choice]
            if y_name is None:
                self._log_for_severity(
                    f"{loc}{choice.name or 'unnamed choice'} has all choice symbols disabled in sdkconfig; "
                    f"the choice is not visible. Source: {escape(user_source) if user_source else '(unknown)'}"
                )
            else:
                self._log_for_severity(
                    f"{loc}{choice.name or 'unnamed choice'} has user-set value {y_name} "
                    f"from {escape(user_source) if user_source else '(unknown)'} but is not visible"
                )

        log.hint(self.info_string)

    def return_json(self) -> Optional[dict]:
        if self.report_severity() == STATUS_OK:
            return None
        ret_json = super().return_json()
        if not ret_json:
            ret_json = dict()
        ret_json["data"] = dict()
        ret_json["data"]["symbols"] = dict()
        ret_json["data"]["choices"] = dict()
        for symbol in self.hidden_symbols:
            ret_json["data"]["symbols"][symbol.name] = {
                "value": self.hidden_symbols[symbol],
                "source": symbol._user_source,
            }
        for choice in self.hidden_choices:
            y_name = self.hidden_choices[choice]
            ret_json["data"]["choices"][choice.name] = {
                "value": y_name,
                "source": choice._user_source or getattr(choice._user_selection, "_user_source", ""),
            }

        return ret_json

    def reset(self) -> None:
        """
        Reset the area to its initial state, clearing all records and data.
        """
        self.hidden_symbols.clear()
        self.hidden_choices.clear()


class KconfigReport:
    """
    Deferred configuration report.

    Records are added via ``add_record(AreaClass, ...)`` during parsing and
    config loading.  ``print_report()`` emits the collected diagnostics after
    all work is done.
    """

    _instance = None
    _initialized: bool

    def __new__(cls, kconfig: "Kconfig", defaults_policy: DefaultsPolicy) -> "KconfigReport":
        """Singleton class to log messages"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.defaults_policy = defaults_policy
            cls._instance._initialized = False
        cls._instance.kconfig = kconfig
        cls._instance.defaults_policy = defaults_policy
        return cls._instance

    def __init__(
        self,
        kconfig: "Kconfig",
        defaults_policy: DefaultsPolicy,
    ) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True

        self.kconfig: "Kconfig" = kconfig
        self.verbosity: str = os.getenv("KCONFIG_REPORT_VERBOSITY", VERBOSITY_DEFAULT)
        self.defaults_policy: DefaultsPolicy = defaults_policy

        self._log_cache: List[Dict[str, str]] = []
        EspLog.set_logger(CachingLog(self._log_cache))
        log.set_verbosity(REPORT_TO_PYLIB_VERBOSITY[self.verbosity])

        # Ignores
        self.lines_with_ignores: List[str] = list()

        # Areas
        self.areas = (
            MultipleDefinitionArea(),
            DefaultValuesArea(verbosity=self.verbosity),
            MultipleAssignmentArea(),
            DisabledSymbolArea(),
        )

        # Mapping dictionaries
        """
        ignore_code_to_area:
            Mapping from ignore code to the Area object. It is used to quickly find the area for given ignore code.
        """
        self.ignore_code_to_area: Dict[str, Area] = {}
        for area in self.areas:
            for code in area.ignore_codes:
                self.ignore_code_to_area[code] = area

        """
        area_to_instance:
            Mapping from Area class to the Area object. It is used to quickly find the Area object for given Area class.
        """
        self.area_to_instance: Dict[type, Area] = {area.__class__: area for area in self.areas}

        """
        status (property):
            Status of the configuration report. It is calculated only once right before report is printed.
        """
        self._status: int = STATUS_NONE

    @property
    def status(self) -> int:
        """
        Get the status of the Configuration.
        """
        self._status = max(area.report_severity() for area in self.areas) or STATUS_OK

        return self._status

    def reset(self) -> None:
        """
        Reset the report to its initial state.
        """
        self._log_cache.clear()
        self.lines_with_ignores.clear()
        for area in self.areas:
            area.reset()
        self._status = STATUS_NONE

    def add_ignore_line(self, line: str) -> None:
        """
        Add line with ignore directive to ignored lines, which will be processed later.
        """
        if not self.kconfig:
            raise AttributeError("Kconfig object must be set before adding ignore lines.")
        parts = [part.strip() for part in line.split()]
        if parts[0] not in ["config", "choice", "menuconfig"]:
            log.note(f"Kconfig entry {parts[0]} does not support ignore directives - directive ignored")
            return
        sc_name = parts[1]
        for ignore_code in parts[4:]:  # config/choice NAME # ignore: CODE [CODE]* -> CODE is parts[4]
            try:
                self.ignore_code_to_area[ignore_code].add_ignore(self.kconfig._lookup_sym(sc_name))
            except KeyError:
                log.note(f'ignoring ignore code "{ignore_code}" for {parts[0]} {sc_name} (unsupported ignore code)')
                continue

    def add_record(self, area, **kwargs):
        """
        Add a record to the given area.

        ``sym_or_choice`` is required for most areas.  If omitted the area's
        ``add_record`` is called with ``sym_or_choice=None``.
        """
        if "sym_or_choice" not in kwargs.keys():
            self.area_to_instance[area].add_record(sym_or_choice=None, **kwargs)
        else:
            self.area_to_instance[area].add_record(**kwargs)

    def _emit_header(self) -> None:
        if not self.kconfig:
            raise AttributeError("Kconfig object must be set before printing report.")

        log.note(f"Kconfig parser version: {self.kconfig.parser_version}")
        log.note(f"Kconfig defaults policy: use {self.defaults_policy.value}")
        if self.verbosity == VERBOSITY_VERBOSE:
            log.note(f"Symbols parsed: {len(self.kconfig.unique_defined_syms)}")

        status = self.status
        if status == STATUS_OK:
            log.note("Status: Finished successfully")
        elif status == STATUS_OK_WITH_INFO:
            log.note("Status: Finished with notifications")
        elif status == STATUS_WARNING:
            log.warn("Status: Finished with warnings")
        else:
            log.err("Status: Failed")

    def _finalize_report_data(self) -> None:
        """
        Gather information available only after Kconfig files are parsed and sdkconfig files are loaded.
        NOTE: If possible, log the information on the fly. This method serves only for areas that
              cannot be logged that way.
        """
        # we cannot use BOOL_TO_STR here because it would lead to a circular import
        bool_to_str = {0: "n", 2: "y"}
        # Report symbols that have a user value but are not visible due to
        # unmet dependencies (i.e. they have a prompt whose condition is false).
        # Promptless symbols always have visibility 0 by design and are already
        # handled by DefaultValuesArea during config loading — they should not
        # appear here.
        for sym in self.kconfig.defined_syms:
            if sym._user_value is not None and sym.visibility == 0:
                if all(node.prompt is None for node in sym.nodes):
                    continue
                str_value = bool_to_str[sym._user_value] if sym._user_value in bool_to_str else sym._user_value
                self.add_record(DisabledSymbolArea, sym_or_choice=sym, user_value=str_value)

    def print_report(self) -> None:
        # Some areas (DisabledSymbolArea for instance) need to be finalized after Kconfig
        # files are parsed and sdkconfig files are loaded.
        self._finalize_report_data()

        if self.verbosity == VERBOSITY_QUIET and self.status in (STATUS_OK, STATUS_OK_WITH_INFO, STATUS_WARNING):
            return

        log.set_console_options(soft_wrap=True)
        self._emit_header()

        for area in self.areas:
            area.emit(verbosity=self.verbosity)

    def output_json(self, file: Optional[str] = None) -> None:
        report_json = self._return_json()

        if not file:
            console = Console(force_terminal=True, stderr=True)
            console.print(json.dumps(report_json, indent=4))
        else:
            with open(file, "w+") as f:
                json.dump(report_json, f, indent=4)

    def _return_json(self) -> Dict:
        """
        Return the report in JSON format.
        """
        self._finalize_report_data()
        report_json: Dict = dict()
        report_json["header"] = dict()
        report_json["header"]["report_type"] = "kconfig"
        report_json["header"]["parser_version"] = self.kconfig.parser_version
        report_json["header"]["verbosity"] = self.verbosity
        report_json["header"]["status"] = Area.severity_to_str(self.status)
        report_json["header"]["unique_defined_syms"] = len(self.kconfig.unique_defined_syms)
        report_json["header"]["defaults_policy"] = self.defaults_policy.value

        report_json["areas"] = list()
        for area in self.areas:
            # Status OK means that there is nothing to report in the area
            if area.report_severity() == STATUS_OK:
                continue
            report_json["areas"].append(area.return_json())

        report_json["messages"] = list(self._log_cache)

        return report_json
