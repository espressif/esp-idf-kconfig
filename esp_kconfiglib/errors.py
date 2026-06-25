# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import contextlib
from typing import Iterator

from esp_pylib.logger import log
from rich.markup import escape


@contextlib.contextmanager
def kconfig_error_handler(exit_code: int = 1) -> Iterator[None]:
    """
    Catch Kconfig-domain exceptions and exit cleanly via log.die
    instead of dumping a raw traceback.

    SystemExit and KeyboardInterrupt always propagate unchanged.
    Programming errors (AttributeError, TypeError, etc.) are not caught
    so they still produce tracebacks via install_exception_reporting().
    """
    from esp_kconfiglib.core import KconfigError
    from esp_kconfiglib.core import _KconfigIOError
    from esp_kconfiglib.kconfig_grammar import KconfigParseError

    try:
        yield
    except (KconfigError, KconfigParseError, _KconfigIOError) as e:
        log.die(escape(str(e)), exit_code=exit_code)
    except (RuntimeError, ValueError, OSError) as e:
        log.die(escape(str(e)), exit_code=exit_code)
