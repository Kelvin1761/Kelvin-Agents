"""速度重建第 1 步：`au_racing_engine.speed` 一定要同現行 `_pf_aggregates` + `_pace_figure_score` 一樣。

全語料 A/A（`scratch/au_speed_rebuild_aa_20261101.py`）證明逐匹一樣；呢度釘住細節，令之後改公式時知道自己郁咗乜。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))

from au_racing_engine import speed  # noqa: E402
from au_racing_engine.engine_core import L600_RECENCY_DECAY, _SEC_PER_LENGTH, _pf_aggregates  # noqa: E402

SB = speed.SPORTSBET


def _run(delta, margin, date, source=SB):
    return {"l600_delta": delta, "margin": margin, "run_date": date, "source": source}


class MatchesEngineAggregates(unittest.TestCase):
    def test_constants_are_the_engine_constants(self):
        self.assertEqual(speed.SEC_PER_LENGTH, _SEC_PER_LENGTH)
        self.assertEqual(speed.RECENCY_DECAY, L600_RECENCY_DECAY)

    def test_horse_values_equal_engine_avg(self):
        runs = [_run(0.4, 1.0, "2026-05-01"), _run(-0.2, None, "2026-09-01"), _run(1.1, 3.5, "2026-07-01", None)]
        agg = _pf_aggregates([dict(r) for r in runs], SB)
        h = speed.horse_speed(runs, SB)
        self.assertEqual(h.own, agg["own_l600_delta_avg"])
        self.assertEqual(h.race, agg["l600_delta_avg"])
        self.assertEqual(h.runs, 3)

    def test_non_sportsbet_horse_has_no_own_value(self):
        runs = [_run(0.4, 1.0, "2026-05-01", "racenet_formguide_cfb")]
        agg = _pf_aggregates([dict(r) for r in runs], "racenet_formguide_cfb")
        h = speed.horse_speed(runs, "racenet_formguide_cfb")
        self.assertIsNone(h.own)
        self.assertIsNone(agg.get("own_l600_delta_avg"))
        self.assertEqual(h.race, agg["l600_delta_avg"])


class FieldScores(unittest.TestCase):
    def _h(self, own, race=0.0):
        return speed.HorseSpeed(own, race, 1)

    def test_faster_than_field_scores_above_60(self):
        out = speed.field_scores({"1": self._h(-1.0), "2": self._h(0.0), "3": self._h(1.0)})
        self.assertGreater(out["1"].score, 60)
        self.assertLess(out["3"].score, 60)
        self.assertAlmostEqual(out["2"].score, 60.0)
        self.assertEqual(out["1"].basis, "own")

    def test_fewer_than_three_values_is_neutral(self):
        out = speed.field_scores({"1": self._h(-1.0, None), "2": self._h(1.0, None), "3": speed.HorseSpeed(None, None, 0)})
        self.assertTrue(all(s.score == 60.0 and s.state == "no_pf" for s in out.values()))

    def test_falls_back_to_race_level_when_own_too_thin(self):
        field = {"1": self._h(-1.0, -0.5), "2": self._h(None, 0.0), "3": self._h(None, 0.5)}
        out = speed.field_scores(field)
        self.assertEqual(out["1"].basis, "race")
        self.assertGreater(out["1"].score, 60)

    def test_no_spread_is_neutral(self):
        out = speed.field_scores({str(i): self._h(0.5) for i in range(4)})
        self.assertTrue(all(s.state == "no_spread" and s.score == 60.0 for s in out.values()))

    def test_score_is_clipped(self):
        field = {"1": self._h(-100.0), **{str(i): self._h(0.0) for i in range(2, 12)}}
        self.assertEqual(speed.field_scores(field)["1"].score, 100.0)


if __name__ == "__main__":
    unittest.main()
