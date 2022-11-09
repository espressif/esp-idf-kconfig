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
        print("A fatal error occurred: %s" % e)
        sys.exit(2)
