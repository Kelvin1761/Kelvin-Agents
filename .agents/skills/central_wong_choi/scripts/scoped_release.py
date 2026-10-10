#!/usr/bin/env python3
"""Exact-scope save entry with expected Telegram results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.release_manager import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
