# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
CLI for ``python -m kcompare``.
"""

import os
import sys
from typing import Optional
from typing import Union

import rich_click as click
from esp_pylib.excepthook import install_exception_reporting
from esp_pylib.logger import log
from rich.markup import escape

from .aggregate import merge_report
from .detect import is_idf_root
from .emitter import emit_codeowner_split
from .emitter import emit_report
from .errors import KcompareError
from .models import MergedDiffReport
from .models import MultiTargetDiffReport
from .pipeline import run_repo_compare
from .split_codeowners import split_by_codeowner


@click.command(
    help="kcompare - Compare Kconfig options between two ESP-IDF commits",
    context_settings=dict(help_option_names=["-h", "--help"]),
)
@click.argument("commit1")
@click.argument("commit2")
@click.argument("output_file", required=False, default=None)
@click.option(
    "-t",
    "--target",
    default=None,
    help="Chip target to provide the comparison for. If omitted, compares every "
    "target common to both commits (via 'idf.py --list-targets') and combines the results",
)
@click.option(
    "-o",
    "--output",
    type=click.Choice(["human", "json", "markdown"], case_sensitive=False),
    default="human",
    show_default=True,
    help="Output format",
)
@click.option(
    "-a",
    "--aggregation",
    type=click.Choice(["change", "target", "aggregated"], case_sensitive=False),
    default="change",
    show_default=True,
    help="How to group changes: 'change' = one entry per change with an 'affected targets' field; "
    "'target' = one section per target (not aggregated); "
    "'aggregated' = grouped by the exact target set affected ('all' plus each combination)",
)
@click.option(
    "--skip-install",
    is_flag=True,
    default=False,
    help="Skip 'eim install' (still captures the environment via 'eim run'); "
    "useful when the checkout is already set up with eim",
)
@click.option(
    "--keep-worktrees",
    is_flag=True,
    default=False,
    help="Do not remove temporary git worktrees under .kcompare/worktrees/",
)
@click.option(
    "--by-codeowner",
    is_flag=True,
    default=False,
    help="Split the report by codeowner group, using .gitlab/CODEOWNERS from the newer commit. "
    "Without an output file, group reports are printed one after another (JSON as a single "
    "object); with an output file the path is used as a template (e.g. report.json -> "
    "report_<group>.json)",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Show raw eim / idf.py output and Kconfig parser notes (suppressed by default)",
)
def main(
    commit1: str,
    commit2: str,
    output_file: Optional[str],
    target: Optional[str],
    output: str,
    aggregation: str,
    skip_install: bool,
    keep_worktrees: bool,
    by_codeowner: bool,
    verbose: bool,
) -> None:
    """
    Compare Kconfig options between two ESP-IDF commits.

    The current working directory must be an ESP-IDF repository root.

    OUTPUT_FILE is an optional destination path for the report; when
    omitted, the report is written to stdout.
    """
    install_exception_reporting()
    log.set_info_stream(sys.stderr)
    # esp_kconfiglib's KconfigReport (singleton, created on the first
    # Kconfig() build) installs its own logger and sets esp_pylib's global
    # verbosity from this envvar, overriding anything set via log.set_verbosity()
    # beforehand. This is the actual hook for suppressing its parser
    # notes/warnings, independent of kcompare's own progress messages.
    os.environ["KCONFIG_REPORT_VERBOSITY"] = "verbose" if verbose else "quiet"

    cwd = os.getcwd()

    try:
        if not is_idf_root(cwd):
            log.die(f"'{escape(cwd)}' is not an ESP-IDF repository root (missing Kconfig + tools/cmake/project.cmake)")
        report: MultiTargetDiffReport = run_repo_compare(
            repo=cwd,
            commit1=commit1,
            commit2=commit2,
            target=target,
            skip_install=skip_install,
            keep_worktrees=keep_worktrees,
            quiet=not verbose,
            by_codeowner=by_codeowner,
        )
    except KcompareError as exc:
        log.die(escape(str(exc)))

    report_to_emit: Union[MultiTargetDiffReport, MergedDiffReport]
    if aggregation == "target":
        report_to_emit = report
    else:
        report_to_emit = merge_report(report, aggregation)

    if by_codeowner:
        codeowners = report_to_emit.codeowners
        if codeowners is None:
            log.die("codeowner split requested but CODEOWNERS could not be loaded")
        assert codeowners is not None
        groups = split_by_codeowner(report_to_emit, codeowners)
        if not groups:
            log.print("no changes to report for any codeowner group", file=sys.stderr, markup=False)
            return
        emit_codeowner_split(groups, output, output_file)
        return

    if output_file and output_file != "-":
        with open(output_file, "w", encoding="utf-8") as f:
            emit_report(report_to_emit, output, file=f)
    else:
        emit_report(report_to_emit, output, file=sys.stdout)
