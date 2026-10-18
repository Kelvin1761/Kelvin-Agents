"""騎練調整項逐週出現率（EXP-20261018-04）：重演 2026-10-07 起騎師同程／練馬師同程全死。"""
from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))

import field_health as fh  # noqa: E402

WEEK_DAYS = ["2026-07-20", "2026-07-27", "2026-08-03", "2026-08-10", "2026-08-17", "2026-08-24"]
TODAY = dt.date(2026, 8, 31)  # 最近完整週 W35
ALL = ("人馬歷史", "騎練組合", "騎師同程", "練馬師同程", "換騎")


def _race(factors) -> dict:
    horses = {}
    for i in range(1, 13):
        horses[str(i)] = {"python_auto": {
            "feature_scores": {"jockey_score": 55.0 + i},
            "trainer_signal_detail": {"adjustments": [{"factor": f, "delta": 0.0} for f in factors]},
        }}
    return {"horses": horses}


def _corpus(tmp: Path, dead_week: str | None = None) -> Path:
    """每週一個沙田賽日 × 10 場 × 12 匹 = 120 匹（只過調整項門檻）。"""
    root = tmp / "HK_Racing"
    for day in WEEK_DAYS:
        week = fh.iso_week(day)
        meeting = root / f"{day}_ShaTin"
        meeting.mkdir(parents=True)
        factors = [f for f in ALL if not (week == dead_week and f in ("騎師同程", "練馬師同程"))]
        for race in range(1, 11):
            (meeting / f"Race_{race}_Logic.json").write_text(json.dumps(_race(factors)), encoding="utf-8")
    return root


class AdjustmentCoverageTests(unittest.TestCase):
    def _trend(self, platform="hkjc", **kw):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            ledger = tmp / "l.jsonl"
            rows = fh.record(platform, _corpus(tmp, **kw), "2026-07-01", ledger)
            return rows, fh.trend(fh.read_ledger(ledger), today=TODAY)

    def test_records_one_row_per_factor_per_week(self):
        rows, _ = self._trend()
        adj = [r for r in rows if r["source"] == "adjustment"]
        self.assertEqual(len(adj), len(ALL) * len(WEEK_DAYS))
        self.assertTrue(all(r["fill_rate"] == 1.0 for r in adj))

    def test_healthy_is_quiet(self):
        _rows, (week, findings) = self._trend()
        self.assertEqual(week, "2026-W35")
        self.assertEqual([f for f in findings if f["source"] == "adjustment"], [])

    def test_distance_adjustments_going_dead_is_caught(self):
        _rows, (_week, findings) = self._trend(dead_week="2026-W35")
        dead = {f["field"] for f in findings if f["source"] == "adjustment" and f["status"] == "dead"}
        self.assertEqual(dead, {"騎師同程", "練馬師同程"})
        text = fh.format_findings("hkjc", "2026-W35", findings)
        self.assertIn("騎練調整項", text)
        self.assertIn("出現率 0%", text)

    def test_au_records_no_adjustment_rows(self):
        rows, _ = self._trend(platform="au")
        self.assertFalse(any(r["source"] == "adjustment" for r in rows))


if __name__ == "__main__":
    unittest.main()
