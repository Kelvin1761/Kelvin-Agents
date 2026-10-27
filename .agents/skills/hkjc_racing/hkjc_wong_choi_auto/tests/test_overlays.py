"""情境 overlay registry（EXP-20261027-13）：PIT、shadow 唔加分、驗證計埋 overlay。"""
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_racing_engine import overlays  # noqa: E402


def _write_day(root: Path, day: str, winners: list[str]) -> None:
    folder = root / "hkjc results 2026 27" / day
    folder.mkdir(parents=True)
    races = {str(i + 1): {"racedate": day, "results": [{"pos": "1", "jockey": j}, {"pos": "2", "jockey": "路人"}]}
             for i, j in enumerate(winners)}
    (folder / "full_day_results.json").write_text(json.dumps(races, ensure_ascii=False), encoding="utf-8")


class FakeEngine:
    def __init__(self, race_date, today, history):
        self.race_context = {"race_date": race_date}
        self.horse_data = {"jockey": today}
        self._history = history

    def _clean(self, value):
        return str(value or "").strip()

    def _current_declared_jockey(self):
        return ""

    def _recent_jockey_history_rows(self):
        return self._history


class OverlayTests(unittest.TestCase):
    def setUp(self):
        overlays._jockey_wins_by_day.cache_clear()
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        _write_day(root, "2026-10-01", ["甲"] * 3 + ["乙"] * 2 + ["丙", "丁", "戊", "己"])
        # 賽日當日 —— 唔准計入（PIT）
        _write_day(root, "2026-10-28", ["庚"] * 9)
        self.patch = mock.patch.object(overlays, "RESULTS_DB", root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(overlays._jockey_wins_by_day.cache_clear)
        self.root = str(root)

    def test_top_jockeys_exclude_race_day(self):
        top, wins = overlays.top_jockeys_as_of(date(2026, 10, 28), self.root)
        self.assertNotIn("庚", top)
        self.assertEqual(wins["甲"], 3)
        self.assertEqual(len(top), overlays.TOP_JOCKEY_COUNT)

    def test_upgrade_and_today_flags(self):
        engine = FakeEngine("2026-10-28", "甲", [{"date": "11/10/2026", "jockey": "路人"}])
        hits = overlays.evaluate_overlays(engine)
        self.assertEqual(hits["top_jockey_today"]["value"], 1.0)
        self.assertEqual(hits["top_jockey_upgrade"]["value"], 1.0)

        stay = FakeEngine("2026-10-28", "甲", [{"date": "11/10/2026", "jockey": "乙"}])
        hits = overlays.evaluate_overlays(stay)
        self.assertEqual(hits["top_jockey_today"]["value"], 1.0)
        self.assertEqual(hits["top_jockey_upgrade"]["value"], 0.0)

    def test_history_row_on_race_day_is_ignored(self):
        same_day = FakeEngine("2026-10-28", "甲", [{"date": "28/10/2026", "jockey": "路人"}])
        hits = overlays.evaluate_overlays(same_day)
        self.assertEqual(hits["top_jockey_upgrade"]["value"], 0.0)

    def test_missing_results_database_never_fires(self):
        with mock.patch.object(overlays, "RESULTS_DB", Path(self.root) / "nope"):
            overlays._jockey_wins_by_day.cache_clear()
            hits = overlays.evaluate_overlays(FakeEngine("2026-10-28", "甲", []))
        self.assertTrue(all(hit["value"] == 0.0 for hit in hits.values()))

    def test_shadow_weight_adds_nothing_and_live_weight_adds_raw_points(self):
        hits = {key: {"value": 1.0, "evidence": "x"} for key in overlays.OVERLAYS}
        record = overlays.overlay_record(hits)
        self.assertTrue(all(item["applied_delta"] == 0.0 and item["status"] == "shadow" for item in record.values()))
        with mock.patch.dict(overlays.OVERLAY_WEIGHTS, {"top_jockey_today": 0.75}):
            record = overlays.overlay_record(hits)
        self.assertEqual(record["top_jockey_today"]["applied_delta"], 0.75)
        self.assertEqual(overlays.applied_total({"overlays": record}), 0.75)


class ValidationCountsOverlay(unittest.TestCase):
    def test_score_004_includes_overlay_delta(self):
        from hkjc_racing_engine import validation
        from hkjc_racing_engine.scoring import MATRIX_WEIGHTS, to_display_scale

        matrix = {key: 60.0 for key in MATRIX_WEIGHTS}
        raw = sum(60.0 * w for w in MATRIX_WEIGHTS.values()) + 0.5
        auto = {"ability_score_raw": raw, "ability_score": round(to_display_scale(raw), 2),
                "matrix_scores": matrix, "overlays": {"top_jockey_today": {"applied_delta": 0.5}}}
        self.assertFalse([e for e in validation._validate_auto_namespace("1", auto) if "SCORE-004" in e])
        auto["overlays"]["top_jockey_today"]["applied_delta"] = 0.0
        self.assertTrue([e for e in validation._validate_auto_namespace("1", auto) if "SCORE-004" in e])


if __name__ == "__main__":
    unittest.main()
