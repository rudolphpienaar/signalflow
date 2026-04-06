"""Terminal-facing constants and optional readline support."""

from __future__ import annotations

import os

try:
    import readline
    import rlcompleter
except ImportError:  # pragma: no cover - platform dependent
    readline = None
    rlcompleter = None

HISTORY_FILE: str = os.path.expanduser("~/.signalflow_history")
HISTORY_LENGTH: int = 1000

ANSI_RESET: str = "\033[0m"
ANSI_BOLD: str = "\033[1m"
ANSI_CYAN: str = "\033[36m"
ANSI_GREEN: str = "\033[32m"
ANSI_YELLOW: str = "\033[33m"
ANSI_RED: str = "\033[31m"
ANSI_BLUE: str = "\033[34m"
ANSI_MAGENTA: str = "\033[35m"
ANSI_DIM: str = "\033[2m"
ANSI_WHITE: str = "\033[97m"
