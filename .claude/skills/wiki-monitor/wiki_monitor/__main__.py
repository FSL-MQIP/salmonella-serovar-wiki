"""Entry point for ``python -m wiki_monitor``."""

import sys

from wiki_monitor.cli import main

if __name__ == "__main__":
    sys.exit(main())
