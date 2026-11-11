"""Live-card date guards (2026-10-07 and 2026-11-11 Happy Valley).

Both nights a pre-race run finished after Sydney midnight while Hong Kong was
still mid-card.  The engine judged "live" with the Sydney host date, scored the
card as a historical replay (every jockey/trainer prior withheld) and the board
published it: 53/108 and 85/107 ranks moved.

Three lines of defence are pinned here:
1. live means the Hong Kong date (``hk_today``) — see test_jt_prior_as_of_guard;
2. a run the scheduler declares live (``WC_HKJC_LIVE_CARD=1``) raises instead of
   silently falling back to replay mode;
3. no engine module reads the host clock as a date.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from hkjc_racing_engine import live_priors  # noqa: E402
from hkjc_racing_engine.features import tier_loader  # noqa: E402

SCHEDULER = Path(__file__).resolve().parents[2] / "hkjc_daily_auto" / "hkjc_daily_schedule.py"


class _Snapshot:
    temporal_mode = "latest_season_snapshot"
    as_of_date = None


class LiveCardTripwireTest(unittest.TestCase):
    def test_declared_live_card_refuses_replay_scoring(self) -> None:
        yesterday = (live_priors.hk_today() - timedelta(days=1)).isoformat()
        with patch.dict(os.environ, {live_priors.LIVE_CARD_ENV: "1"}):
            for call in (
                lambda: live_priors.is_live_race_date(yesterday),
                lambda: live_priors.temporal_source_is_safe(_Snapshot(), yesterday),
                lambda: live_priors.temporal_source_is_safe(_Snapshot(), None),
                lambda: tier_loader.score_tier("jockey", "潘頓", "x", as_of_date=yesterday),
            ):
                with self.assertRaises(live_priors.LiveCardDateMismatch):
                    call()

    def test_declared_live_card_scores_today_normally(self) -> None:
        today = live_priors.hk_today().isoformat()
        with patch.dict(os.environ, {live_priors.LIVE_CARD_ENV: "1"}):
            self.assertTrue(live_priors.is_live_race_date(today))
            self.assertTrue(live_priors.temporal_source_is_safe(_Snapshot(), today))

    def test_replays_keep_the_fail_closed_path(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(live_priors.LIVE_CARD_ENV, None)
            self.assertFalse(live_priors.is_live_race_date("2026-04-12"))
            self.assertFalse(live_priors.temporal_source_is_safe(_Snapshot(), "2026-04-12"))

    def test_scheduler_declares_its_orchestrator_run_live(self) -> None:
        text = SCHEDULER.read_text(encoding="utf-8")
        self.assertIn('"WC_HKJC_LIVE_CARD": "1"', text)


def _host_clock_date_calls(path: Path) -> list[str]:
    """`date.today()`, `datetime.today()` and tz-less `datetime.now()`."""
    hits = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        owner = node.func.value
        owner_name = owner.id if isinstance(owner, ast.Name) else (
            owner.attr if isinstance(owner, ast.Attribute) else "")
        name = node.func.attr
        if owner_name == "date" and name == "today":
            hits.append(f"{path.name}:{node.lineno} date.today()")
        elif owner_name == "datetime" and name == "today":
            hits.append(f"{path.name}:{node.lineno} datetime.today()")
        elif owner_name == "datetime" and name == "now" and not (node.args or node.keywords):
            hits.append(f"{path.name}:{node.lineno} datetime.now() without tz")
    return hits


class NoHostClockDateTest(unittest.TestCase):
    def test_engine_never_reads_the_host_date(self) -> None:
        """HKJC race dates are Hong Kong dates; the host is a Sydney Mac.
        Use ``live_priors.hk_today()`` for anything compared with a race date."""
        hits = []
        for path in sorted((SCRIPTS / "hkjc_racing_engine").rglob("*.py")):
            hits.extend(_host_clock_date_calls(path))
        self.assertEqual(hits, [], "host-clock date calls in hkjc_racing_engine:\n" + "\n".join(hits))

    def test_detector_catches_the_original_bug(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.py"
            bad.write_text("from datetime import date, datetime\n"
                           "a = date.today()\nb = datetime.now()\nc = datetime.now(TZ)\n",
                           encoding="utf-8")
            hits = _host_clock_date_calls(bad)
        self.assertEqual(len(hits), 2, hits)


if __name__ == "__main__":
    unittest.main()
