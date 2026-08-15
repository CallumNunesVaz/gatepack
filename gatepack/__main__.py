"""Entry point for `python -m gatepack`.

The desktop application's session manager (C9) spawns the core as a child
process, and `python -m gatepack` is the invocation that works against a plain
checkout with no console script installed.
"""

from __future__ import annotations

import sys

from gatepack.cli import main

if __name__ == "__main__":
    sys.exit(main())
