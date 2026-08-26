from __future__ import annotations

import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.command_adapter import last_json_object  # noqa: E402


def test_last_json_object_accepts_one_line_output() -> None:
    assert last_json_object('log line\n{"status":"complete"}\n') == {
        "status": "complete"
    }


def test_last_json_object_accepts_pretty_json_after_logs() -> None:
    output = 'before\n{\n  "status": "ok",\n  "detail": {"events": 3}\n}\n'
    assert last_json_object(output) == {"status": "ok", "detail": {"events": 3}}


def test_last_json_object_rejects_trailing_non_json() -> None:
    assert last_json_object('{"status":"ok"}\ntrailing log\n') is None

