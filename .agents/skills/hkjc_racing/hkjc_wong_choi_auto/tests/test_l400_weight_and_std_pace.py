"""EXP-20261112-13：L400 按今仗負磅換算（入分）、輸頭馬差距改名、對馬會標準（只顯示）。"""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_racing_engine import past_runs, scoring  # noqa: E402
from hkjc_racing_engine.features import speed  # noqa: E402
from hkjc_racing_engine.renderer import _matrix_fact_lines  # noqa: E402

FORMGUIDE = """#### 賽事概覽 (Race Overview)
- 賽事日期 / 場次 / 跑道及場地狀況: 08/11/2026 / 第1場 / 沙田 草地 - C+3 賽道 第四班 060-040 1200米

#### 全場馬匹分析 (Full Field Analysis)
馬號: 1
馬名: 大輝煌
檔位: 9
騎師: 周俊樂
負磅: 133
排位體重: 1223

往績紀錄:
  [1] 28/10/2026 | 日數: 27 | 沙田 "AWT" 1650 好
      檔位: 10 | 馬重: 1217 | 負磅: 110 | 騎師: 黃寶妮 | 名次: 9 / 14
      能量: 86 | 分段時間: 28.95, 23.32, 23.52, 23.27
      短評: 中等偏慢步速。
  [2] 01/10/2026 | 日數: 96 | 沙田 "A" 1200 好/快
      檔位: 5 | 馬重: 1216 | 負磅: 118 | 騎師: 鍾易禮 | 名次: 3 / 14
      能量: 75 | 分段時間: 23.90, 22.50, 23.10
      短評: 極慢步速。
  [3] 09/11/2026 | 日數: 0 | 沙田 "A" 1200 好
      檔位: 5 | 馬重: 1216 | 負磅: 118 | 騎師: 鍾易禮 | 名次: 1 / 14
      能量: 75 | 分段時間: 23.00, 22.00, 22.00
      短評: 賽日之後（唔應該用）。

馬號: 2
馬名: 冇往績
檔位: 1
騎師: 甲
負磅: 120
排位體重: 1100

往績紀錄:
"""


def _horses():
    return {"1": {"horse_name": "大輝煌", "_data": {"raw_l400": "23.27",
                                                     "recent_6_detail": "第1仗(28/10/2026 第四班): 9名 | 第2仗(01/10/2026 第四班): 3名"}},
            "2": {"horse_name": "冇往績", "_data": {}}}


class PastRunsTests(unittest.TestCase):
    def test_parse_and_attach_only_uses_runs_before_race_day(self):
        horses = _horses()
        n = past_runs.attach(FORMGUIDE, horses, {"race_class": "第四班"}, date(2026, 11, 8))
        self.assertEqual(n, 2)
        data = horses["1"]["_data"]
        self.assertEqual(data["formguide_today_weight"], 133)
        self.assertEqual(data["l400_last_run"], {"date": "2026-10-28", "distance": 1650, "weight": 110, "l400": 23.27})
        pace = data["std_pace"]
        self.assertEqual(pace["n"], 2)
        self.assertEqual([r["date"] for r in pace["runs"]], ["2026-10-28", "2026-10-01"])   # 11-09 唔入
        # 沙田草地 1200m C4 標準 23.75／22.45／23.05：偏差 +0.15＋0.05＋0.05 = 0.25；早段 +0.20
        run2 = pace["runs"][1]
        self.assertAlmostEqual(run2["p0"], 0.25, places=2)
        self.assertAlmostEqual(run2["p1"], round(0.25 - (1 - past_runs.PACE_RECOVERY_RHO) * 0.20, 2), places=2)
        self.assertAlmostEqual(run2["weight_conversion"], round(0.01123 * 1.2 * (133 - 118), 2), places=2)
        self.assertNotIn("std_pace", horses["2"]["_data"])
        self.assertNotIn("l400_last_run", horses["2"]["_data"])

    def test_no_race_date_writes_nothing(self):
        horses = _horses()
        self.assertEqual(past_runs.attach(FORMGUIDE, horses, {}, None), 0)
        self.assertNotIn("l400_last_run", horses["1"]["_data"])


class L400WeightTests(unittest.TestCase):
    def _data(self, **kw):
        data = {"raw_l400": "23.27", "formguide_today_weight": 133, "energy_trend": "80→81 → 趨勢: 穩定",
                "l400_last_run": {"date": "2026-10-28", "distance": 1650, "weight": 110, "l400": 23.27}}
        data.update(kw)
        return data

    def test_coefficient_by_last_run_distance(self):
        self.assertEqual(scoring.l400_weight_seconds_per_lb(1200), 0.007)
        self.assertEqual(scoring.l400_weight_seconds_per_lb(1650), 0.016)
        self.assertEqual(scoring.l400_weight_seconds_per_lb(1800), 0.021)

    def test_heavier_today_makes_last_l400_slower(self):
        adj = speed.l400_weight_adjustment(self._data())
        self.assertEqual(adj["weight_diff"], 23)
        self.assertEqual(adj["adjusted"], round(23.27 + 0.016 * 23, 2))

    def test_mismatched_run_or_switch_off_means_no_conversion(self):
        self.assertIsNone(speed.l400_weight_adjustment(self._data(raw_l400="23.80")))
        self.assertIsNone(speed.l400_weight_adjustment(self._data(formguide_today_weight=None)))
        with mock.patch.object(scoring, "L400_WEIGHT_ADJUST", False):
            self.assertIsNone(speed.l400_weight_adjustment(self._data()))

    def test_scorer_bands_on_converted_value_and_shows_both(self):
        # 23.55 原本 ≤23.6 攞「末段偏快」；重 23 磅換算 +0.37 → 23.92 = 末段一般
        data = self._data(raw_l400="23.55", l400_last_run={"date": "2026-10-28", "distance": 1650, "weight": 110, "l400": 23.55})
        scorer = speed.SpeedScorer({"_data": data}, {})
        scorer.compute()
        row = next(d for d in scorer.detail if d["factor"] == "L400 絕對值")
        self.assertEqual(row["delta"], 0.0)
        self.assertIn("23.92s", row["value"])
        self.assertIn("上仗 23.55s", row["value"])
        with mock.patch.object(scoring, "L400_WEIGHT_ADJUST", False):
            scorer = speed.SpeedScorer({"_data": data}, {})
            scorer.compute()
            row = next(d for d in scorer.detail if d["factor"] == "L400 絕對值")
            self.assertEqual(row["delta"], round(scoring.SPEED_MICRO_WEIGHTS["l400_23_6_bonus"], 2))


class MarginRenameTests(unittest.TestCase):
    def test_margin_level_and_series_display(self):
        self.assertEqual(speed.margin_level_display("⚠️ 步速修正後仍偏慢 (近 3 仗修正平均: +1.23s)"),
                         "⚠️ 輸頭馬偏多（0.8–1.3 秒） (近 3 仗平均輸頭馬 1.23 秒)")
        self.assertEqual(speed.margin_series_display("（最舊 → 最新）+0.60s→+0.00s[偏慢]"), "（最舊 → 最新）0.60s→0.00s[偏慢]")

    def test_scorer_factor_is_margin_not_pace(self):
        data = {"finish_time_adj_level": "✅ 步速修正後仍具競爭力 (近 2 仗修正平均: +0.24s)", "raw_l400": "23.80"}  # 兩個訊號
        scorer = speed.SpeedScorer({"_data": data}, {})
        scorer.compute()
        row = next(d for d in scorer.detail if d["factor"] == "輸頭馬差距")
        self.assertEqual(row["value"], "近 2 仗平均 0.24 秒")
        self.assertEqual(row["delta"], round(scoring.SPEED_MICRO_WEIGHTS["finish_competitive_bonus"], 2))

    def test_report_fact_lines(self):
        horses = _horses()
        past_runs.attach(FORMGUIDE, horses, {"race_class": "第四班"}, date(2026, 11, 8))
        horse = horses["1"]
        horse["_data"].update({"finish_time_adj": "（最舊 → 最新）+0.60s→+0.26s",
                               "finish_time_adj_level": "➖ 步速修正後接近平均 (近 3 仗修正平均: +0.53s)"})
        text = "\n".join(_matrix_fact_lines("sectional", horse))
        self.assertIn("輸頭馬差距:", text)
        self.assertIn("輸頭馬中等", text)
        self.assertNotIn("步速修正", text)
        self.assertIn("L400 負磅換算: 上仗 23.27s（1650m 負 110 磅）；今仗負 133 磅，重 23 磅", text)
        self.assertIn("對馬會標準（未入分）: 近 2 仗加權", text)
        self.assertNotIn("→", next(l for l in text.splitlines() if l.startswith("L400 負磅換算")))


if __name__ == "__main__":
    unittest.main()
