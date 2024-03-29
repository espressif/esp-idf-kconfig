# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import sys

from .core import main


class FatalError(RuntimeError):
    """
    Class for runtime errors (not caused by bugs but by user input).
    """

    pass


if __name__ == "__main__":
    try:
        main()
    except FatalError as e:
        print(f"A fatal error occurred: {e}", file=sys.stderr)
        sys.exit(2)
