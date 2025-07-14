# SPDX-FileCopyrightText: 2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0

"""
New Kconfig Report class to log messages.

Instead of continuously logging messages,KconfigReport class will store
the messages and print them at the end of the parsing process as one report.
"""

import json
import textwrap
from typing import TYPE_CHECKING
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple
from typing import Union

if TYPE_CHECKING:
    from .core import Choice
    from .core import Kconfig
    from .core import Symbol

import os
from abc import ABC
from abc import abstractmethod

from rich import print as rprint
from rich.box import HORIZONTALS
from rich.console import Console
from rich.table import Table

PRAGMA_PREFIX = "# ignore:"

STATUS_NONE = 0
STATUS_OK = 1
STATUS_OK_WITH_INFO = 2
STATUS_WARNING = 3
STATUS_ERROR = 4

_INDENT = " " * 4
VERBOSITY_QUIET = "quiet"  # Report only if there is an error
VERBOSITY_DEFAULT = "default"  # Report standard information
VERBOSITY_VERBOSE = "verbose"  # Report everything every time

AREA_TITLE_STYLE = "bold blue"
INFO_STRING_STYLE = "italic"
SUBTITLE_STYLE = "bold"


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
            Dictionary of Symbol/Choice objects (not only names!) which should be ignored in the report.
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

    @abstractmethod
    def add_ignore(self, sym_or_choice: "Union[Symbol, Choice]") -> None:
        """
        Add a Symbol/Choice to the ignore list of the area.
        """
        pass

    @abstractmethod
    def report_severity(self) -> int:
        """
        If given area has nothing to report, STATUS_OK should be returned.
        Otherwise, STATUS_OK_WITH_INFO, STATUS_WARNING or STATUS_ERROR should be returned,
        depending how severe record in given area is.
        """
        pass

    @abstractmethod
    def print(self, verbosity: str) -> Optional[Table]:
        """
        Print the area sub-report.
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
    * Promptless default values with different values between sdkconfig and Kconfig files
      This is normally not a problem, but a feature. However, devs may want to know about it.
    """

    def __init__(self):
        super().__init__(
            title="Default Value Mismatch",
            ignore_codes=tuple(),
            info_string=textwrap.dedent(
                """\
                This area reports issues with default values of the config options.
                For more information, please visit https://docs.espressif.com/projects/esp-idf-kconfig/en/latest/kconfiglib/configuration-report.html#default-value-mismatch
                """
            ),
        )
        self.changed_defaults: Set[Tuple[str, str, str]] = set()
        # Changed configs without prompts should not be reported as it's not something user should care about.
        # However, it may be useful to report them in verbose mode for devs.
        self.changed_values_promptless: Set[Tuple[str, str, str, bool]] = set()

    def add_record(self, sym_or_choice: "Union[Symbol, Choice]", **kwargs: Optional[dict]) -> None:
        promptless: bool = kwargs.get("promptless", False)  # type: ignore
        record = (
            str(sym_or_choice.name),
            str(sym_or_choice.str_value),
            str(getattr(sym_or_choice, "_sdkconfig_value", "") or ""),
        )
        if not promptless:
            self.changed_defaults.add(record)
        else:
            # sdkconfig value is still set even for promptless symbols, so we can decide
            # if sdkconfig contained default value or not
            record_with_default_flag = record + (getattr(sym_or_choice, "_user_value", None) is not None,)
            self.changed_values_promptless.add(record_with_default_flag)

    def add_ignore(self, sym_or_choice: "Union[Symbol, Choice]") -> None:
        pass

    def report_severity(self) -> int:
        if not self.changed_defaults and not self.changed_values_promptless:
            return STATUS_OK
        if self.changed_defaults or self.changed_values_promptless:
            return STATUS_OK_WITH_INFO
        else:  # This should not happen, but just in case
            return STATUS_ERROR

    def _nothing_to_report(self, verbosity: str = VERBOSITY_VERBOSE) -> bool:
        """
        Check if there is nothing to report in the area.
        """
        return not self.changed_defaults and (verbosity != VERBOSITY_VERBOSE or not self.changed_values_promptless)

    def print(self, verbosity: str) -> Optional[Table]:
        # No changed defaults or only promptless changed defaults without verbosity VERBOSITY_VERBOSE
        # -> nothing to report
        if self._nothing_to_report(verbosity):
            return None

        table = Table(title=self.title, title_justify="left", show_header=False, title_style=AREA_TITLE_STYLE)
        table.box = HORIZONTALS
        table.add_column(
            "",
            justify="left",
            no_wrap=True,
        )
        if verbosity == VERBOSITY_VERBOSE:
            table.add_row(self.info_string, style=INFO_STRING_STYLE)

        if self.changed_defaults:
            table.add_row(
                "Config symbols with different default value between sdkconfig and Kconfig", style=SUBTITLE_STYLE
            )
            for sym_name, kconfig_value, sdkconfig_value in self.changed_defaults:
                table.add_row(
                    f"{sym_name}: Kconfig default value: {kconfig_value}, sdkconfig default value: {sdkconfig_value}"
                )
            table.add_row("")

        if verbosity == VERBOSITY_VERBOSE and self.changed_values_promptless:
            table.add_row(
                "Invisible (promptless) config symbols with different values between sdkconfig and Kconfig",
                style="bold",
            )
            for sym_name, kconfig_value, sdkconfig_value, sdkconfig_value_is_default in self.changed_values_promptless:
                table.add_row(
                    (
                        f"{sym_name}: Kconfig default value: {kconfig_value}, "
                        f"sdkconfig value {sdkconfig_value} "
                        f"{'(user-set)' if sdkconfig_value_is_default else '(default)'} "
                        "will be ignored"
                    )
                )
            table.add_row("")

        return table

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
            for sym_name, kconfig_value, sdkconfig_value in self.changed_defaults:
                ret_json["data"]["changed_defaults"].append(
                    {"name": sym_name, "kconfig_default": kconfig_value, "sdkconfig_default": sdkconfig_value}
                )
        if self.changed_values_promptless:  # There is all the info in json every time
            ret_json["data"]["mismatched_promptless"] = list()
            for sym_name, kconfig_value, sdkconfig_value, sdkconfig_value_is_default in self.changed_values_promptless:
                ret_json["data"]["mismatched_promptless"].append(
                    {
                        "name": sym_name,
                        "kconfig_value": kconfig_value,
                        "sdkconfig_value": sdkconfig_value,
                        "sdkconfig_value_is_default": sdkconfig_value_is_default,
                    }
                )
        return ret_json


class MultipleDefinitionArea(Area):
    """
    Multiple definition: having two or more definitions of the Symbol/Choice with the same name.
    NOTE: Currently, MutliplyDefinitionArea cause only info instead of warning. This will be changed in the future.
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

        self.multiple_definitions: Dict[str, Set[str]] = dict()

    def add_record(self, sym_or_choice: "Union[Symbol, Choice]", **kwargs: Optional[dict]) -> None:
        """
        kwargs:
            occurrences: Set[str]
        """
        occurrences: Set[str] = kwargs["occurrences"] if "occurrences" in kwargs else set()  # type: ignore
        # For backward compatibility, code and type annotations allow unnamed choices
        sym_or_choice_name = sym_or_choice.name or "unnamed choice"
        if sym_or_choice_name not in self.multiple_definitions:
            self.multiple_definitions[sym_or_choice_name] = occurrences
        self.multiple_definitions[sym_or_choice_name].update(occurrences)

    def add_ignore(self, sym_or_choice):
        if sym_or_choice.__class__.__name__ == "Symbol":
            self.ignored_sc["configs"].add(sym_or_choice.name)
        else:
            self.ignored_sc["choices"].add(sym_or_choice.name)

    def report_severity(self) -> int:
        return STATUS_OK if not self.multiple_definitions else STATUS_OK_WITH_INFO

    def print(self, verbosity: str) -> Optional[Table]:
        if not self.multiple_definitions:
            return None

        table = Table(title=self.title, title_justify="left", show_header=False, title_style=AREA_TITLE_STYLE)
        table.box = HORIZONTALS
        table.add_column(
            "",
            justify="left",
            no_wrap=True,
        )
        table.add_row(
            "Multiple definitions will have higher severity in the future. Please, visit "
            "https://docs.espressif.com/projects/esp-idf-kconfig/en/latest/kconfiglib/configuration-report.html#multiple-symbol-or-choice-definition "  # noqa: E501
            "for more information.",
            style=INFO_STRING_STYLE,
        )
        if verbosity == VERBOSITY_VERBOSE:
            table.add_row(self.info_string, style=INFO_STRING_STYLE)

        for sym_or_choice_name in self.multiple_definitions:
            table.add_row(sym_or_choice_name, style="bold")
            for definition in self.multiple_definitions[sym_or_choice_name]:
                table.add_row(_INDENT + definition)

        return table

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
        for sym_or_choice_name in self.multiple_definitions:
            ret_json["data"][sym_or_choice_name] = list()
            for definition in self.multiple_definitions[sym_or_choice_name]:
                ret_json["data"][sym_or_choice_name].append(definition)
        return ret_json


class MiscArea(Area):
    """
    All the messages not related to the other areas.
    """

    def __init__(self):
        super().__init__(
            title="Miscellaneous",
            ignore_codes=set(),
            info_string="",
        )

        self.messages: Set[str] = set()

    def add_record(self, sym_or_choice: "Union[Symbol, Choice]", **kwargs: Optional[dict]) -> None:
        """
        kwargs:
            message: str
        As the only Area, MiscArea does not care about the Symbol/Choice.
        """
        if "message" not in kwargs.keys():
            raise AttributeError("Message must be specified for MiscArea.")
        self.messages.add(str(kwargs["message"]))

    def add_ignore(self, sym_or_choice: "Union[Symbol, Choice]") -> None:
        raise AttributeError("MiscArea does not support ignore codes")

    def report_severity(self) -> int:
        return STATUS_OK if not self.messages else STATUS_OK_WITH_INFO

    def print(self, verbosity: str) -> Optional[Table]:
        if not self.messages:
            return None

        table = Table(title=self.title, title_justify="left", show_header=False, title_style=AREA_TITLE_STYLE)
        table.box = HORIZONTALS
        table.add_column("", justify="left", no_wrap=True)
        for message in self.messages:
            table.add_row(f"* {message}")
        return table

    def return_json(self) -> Optional[dict]:
        if not self.messages:
            return None
        ret_json = super().return_json()
        if not ret_json:
            ret_json = dict()
        ret_json["data"] = list(self.messages)
        return ret_json


class KconfigReport:
    """
    By add_record() method, new records are added to the report.
    Every time, it is needed to specify report area for given record.
    Every area is described by a class inheriting from Area class.

    NOTE: Full support will come in the future. Currently, only multiple-definition and misc areas are supported.
    """

    _instance = None
    _initialized: bool

    def __new__(cls, kconfig: "Kconfig") -> "KconfigReport":
        """Singleton class to log messages"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.kconfig = kconfig
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        kconfig: "Kconfig",
    ) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True

        self.kconfig: "Kconfig" = kconfig
        self.verbosity: str = os.getenv("KCONFIG_REPORT_VERBOSITY", VERBOSITY_DEFAULT)

        # Ignores
        self.lines_with_ignores: List[str] = list()

        # Areas
        self.areas = (MultipleDefinitionArea(), MiscArea(), DefaultValuesArea())

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

    def add_ignore_line(self, line: str) -> None:
        """
        Add line with ignore directive to ignored lines, which will be processed later.
        """
        if not self.kconfig:
            raise AttributeError("Kconfig object must be set before adding ignore lines.")
        parts = [part.strip() for part in line.split()]
        if parts[0] not in ["config", "choice", "menuconfig"]:
            self.add_record(
                MiscArea, message=f"Kconfig entry {parts[0]} does not support ignore directives. Directive ignored."
            )
            return
        sc_name = parts[1]
        for ignore_code in parts[4:]:  # config/choice NAME # ignore: CODE [CODE]* -> CODE is parts[4]
            try:
                self.ignore_code_to_area[ignore_code].add_ignore(self.kconfig._lookup_sym(sc_name))
            except KeyError:
                self.add_record(
                    MiscArea,
                    message=f'Ignoring ignore code "{ignore_code}" for {parts[0]} {sc_name} (unsupported ignore code).',
                )
                continue

    def add_record(self, area, **kwargs):
        """
        Adds a record for given area.
        Typically, record is related to the Symbol/Choice object (sym_or_choice from kwargs).
        However, some areas may not need sym_or_choice to be specified, thus it is not mandatory.
        """
        if "sym_or_choice" not in kwargs.keys():
            # E.g. MiscArea does not care about the Symbol/Choice
            self.area_to_instance[area].add_record(sym_or_choice=None, **kwargs)
        else:
            self.area_to_instance[area].add_record(**kwargs)

    def _make_header(self) -> Table:
        if not self.kconfig:
            raise AttributeError("Kconfig object must be set before printing report.")
        header_table = Table(title_style="bold", show_header=False)
        header_table.box = None
        header_table.add_column("Configuration", justify="left")
        header_table.add_row(f"Parser Version: {self.kconfig.parser_version}")
        header_table.add_row(f"Verbosity: {self.verbosity}")
        if self.verbosity == VERBOSITY_VERBOSE:
            header_table.add_row(f"Symbols parsed: {len(self.kconfig.unique_defined_syms)}")

        status = self.status
        if status == STATUS_OK:
            header_table.add_row("Status: Finished successfully", style="green")
        elif status == STATUS_OK_WITH_INFO:
            header_table.add_row("Status: Finished with notifications", style="green_yellow")
            if self.verbosity == VERBOSITY_VERBOSE:
                header_table.add_row(
                    "Configuration is successfully finished, but the system has identified situations that could "
                    "potentially cause some issues. Please check the relevant areas.",
                    style="green_yellow",
                )
        elif status == STATUS_WARNING:
            header_table.add_row("Status: Finished with warnings", style="yellow")
            if self.verbosity == VERBOSITY_VERBOSE:
                header_table.add_row(
                    "Configuration is successfully finished, but the system has identified situations that probably "
                    "will cause some issues. Please check the relevant areas.",
                    style="yellow",
                )
        else:  # NOTE: STATUS_ERROR is currently not used, so "failed" here is just a placeholder.
            header_table.add_row("Status: Failed", style="red")

        header_table.add_row("")

        return header_table

    def print_report(self, file: Optional[str] = None) -> None:
        if self.verbosity == VERBOSITY_QUIET and self.status in (STATUS_OK, STATUS_OK_WITH_INFO, STATUS_WARNING):
            return

        report_table = Table(title="Configuration Report", title_style="bold", show_header=False, title_justify="left")
        report_table.box = HORIZONTALS
        report_table.add_column("Configuration", justify="center", no_wrap=False)
        report_table.add_row(self._make_header())

        for area in self.areas:
            sub_report = area.print(verbosity=self.verbosity)
            if sub_report:
                report_table.add_row(sub_report)

        if not file:
            console = Console(force_terminal=True, stderr=True)
            console.print(report_table)
        else:
            with open(file, "w") as f:
                rprint(report_table, file=f)

    def output_json(self, file: Optional[str] = None) -> None:
        report_json: Dict = dict()
        report_json["header"] = dict()
        report_json["header"]["report_type"] = "kconfig"
        report_json["header"]["parser_version"] = self.kconfig.parser_version
        report_json["header"]["verbosity"] = self.verbosity
        report_json["header"]["status"] = Area.severity_to_str(self.status)
        report_json["header"]["unique_defined_syms"] = len(self.kconfig.unique_defined_syms)

        report_json["areas"] = list()
        for area in self.areas:
            # Status OK means that there is nothing to report in the area
            if area.report_severity() == STATUS_OK:
                continue
            report_json["areas"].append(area.return_json())

        if not file:
            console = Console(force_terminal=True, stderr=True)
            console.print(json.dumps(report_json, indent=4))
        else:
            with open(file, "w+") as f:
                json.dump(report_json, f, indent=4)
