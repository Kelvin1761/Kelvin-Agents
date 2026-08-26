from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.immutable_snapshot import create_immutable_snapshot  # noqa: E402


def test_snapshot_is_create_only_and_identical_retry_is_reused(tmp_path: Path) -> None:
    (tmp_path / "report.md").write_text("prediction\n", encoding="utf-8")
    at = datetime(2026, 8, 26, 10, tzinfo=timezone.utc)
    first = create_immutable_snapshot(
        tmp_path,
        domain="tennis",
        event_id="2026-08-26",
        patterns=["report.md"],
        recommendations=[{"id": 1, "decision": "BET"}],
        at=at,
    )
    second = create_immutable_snapshot(
        tmp_path,
        domain="tennis",
        event_id="2026-08-26",
        patterns=["report.md"],
        recommendations=[{"id": 1, "decision": "BET"}],
        at=datetime(2026, 8, 26, 11, tzinfo=timezone.utc),
    )
    assert first == second
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["append_only"] is True
    assert (first / "report.md").read_text(encoding="utf-8") == "prediction\n"


def test_material_change_creates_new_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "report.md"
    source.write_text("first\n", encoding="utf-8")
    first = create_immutable_snapshot(
        tmp_path,
        domain="tennis",
        event_id="2026-08-26",
        patterns=["*.md"],
    )
    source.write_text("second\n", encoding="utf-8")
    second = create_immutable_snapshot(
        tmp_path,
        domain="tennis",
        event_id="2026-08-26",
        patterns=["*.md"],
    )
    assert first != second
    assert (first / "report.md").read_text(encoding="utf-8") == "first\n"
