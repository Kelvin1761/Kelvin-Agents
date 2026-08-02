"""馬匹往績索引（賽績線嘅對手查冊）。

兩件事要封死：
  1. 輸出格式同 `claw_profile_scraper.py` 逐個 key 一樣，否則
     `compute_form_lines_via_api` 會靜靜當成查唔到。
  2. **as-of 閘。**索引係由賽後頁面砌，入面有埋當日賽果。賽績線數嘅係
     「對手喺呢條往績行之後有冇贏」，所以唔設上限的話，對手今日贏咗嗰場
     會被當成後續走勢 —— 同表格頁嗰個賽後洩漏一模一樣，由另一道門入。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
AU_RACING = ROOT / ".agents" / "skills" / "au_racing"
sys.path.insert(0, str(AU_RACING))

import sb_horse_index as IDX  # noqa: E402

# claw_profile_scraper 出嘅每條 run 都有呢啲 key，缺一個上游就會靜靜計錯
RUN_KEYS = {"date", "date_full", "venue", "finish", "starters", "is_placed", "class"}


def _blk(name, runs):
    return {"name": name, "runs": [
        {"header": {"track": v, "date": d, "race": "3", "dist": "1400"},
         "pos": str(p), "field": str(f)} for d, v, p, f in runs]}


class SlugTest(unittest.TestCase):
    def test_matches_the_old_scraper_slug_exactly(self):
        self.assertEqual(IDX.build_slug("Stage 'n' Screen (NZL)"), "stage-n-screen")
        self.assertEqual(IDX.build_slug("Smokin' Princess"), "smokin-princess")

    def test_metro_and_country_split(self):
        self.assertEqual(IDX.infer_class("Flemington"), "Metro")
        self.assertEqual(IDX.infer_class("Mornington"), "省賽")
        self.assertEqual(IDX.infer_class(""), "-")


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "idx.json"

    def _build(self):
        IDX.update([_blk("Stage 'n' Screen", [
            ("01/08/2026", "Flemington", 1, 11),
            ("08/07/2026", "Sandown Lakeside", 6, 13),
            ("08/06/2026", "Mornington", 3, 9)])], path=self.path)

    def test_run_shape_matches_the_old_scraper(self):
        self._build()
        run = IDX.lookup(["Stage 'n' Screen"], self.path)["stage-n-screen"]["runs"][0]
        self.assertEqual(set(run), RUN_KEYS)
        self.assertEqual(run["finish"], 1)
        self.assertTrue(run["is_placed"])

    def test_unknown_horse_errors_rather_than_reporting_no_runs(self):
        # 「查唔到」同「查到但冇後續出賽」係兩回事 —— 後者會扣分。
        self._build()
        self.assertIn("error", IDX.lookup(["Nobody"], self.path)["nobody"])

    def test_as_of_drops_the_race_being_predicted(self):
        self._build()
        runs = IDX.lookup(["Stage 'n' Screen"], self.path,
                          as_of="2026-08-01")["stage-n-screen"]["runs"]
        self.assertEqual([r["date"] for r in runs], ["2026-07-08", "2026-06-08"])

    def test_without_as_of_the_same_day_run_is_still_there(self):
        """呢個唔係「應該咁」—— 係記低個預設係唔設閘，所以呼叫者一定要傳。"""
        self._build()
        runs = IDX.lookup(["Stage 'n' Screen"], self.path)["stage-n-screen"]["runs"]
        self.assertEqual(runs[0]["date"], "2026-08-01")

    def test_rebuilding_is_idempotent(self):
        self._build()
        self._build()
        runs = IDX.lookup(["Stage 'n' Screen"], self.path)["stage-n-screen"]["runs"]
        self.assertEqual(len(runs), 3)

    def test_a_second_meeting_extends_the_same_horse(self):
        self._build()
        IDX.update([_blk("Stage 'n' Screen",
                         [("15/05/2026", "Caulfield", 2, 10)])], path=self.path)
        runs = IDX.lookup(["Stage 'n' Screen"], self.path)["stage-n-screen"]["runs"]
        self.assertEqual(len(runs), 4)
        self.assertEqual([r["date"] for r in runs], sorted(
            (r["date"] for r in runs), reverse=True), "要由新到舊")


class InjectorWiringTest(unittest.TestCase):
    """`inject_fact_anchors` 要識由路徑抽場次日期做 as-of。"""

    def test_derives_the_meeting_date_from_the_racecard_path(self):
        sys.path.insert(0, str(ROOT / ".agents" / "scripts"))
        from inject_fact_anchors import _derive_as_of
        self.assertEqual(_derive_as_of(
            "/x/2026-08-01 Flemington Race 1-9/08-01 Race 5 Racecard.md"),
            "2026-08-01")

    def test_returns_empty_when_the_path_carries_no_date(self):
        sys.path.insert(0, str(ROOT / ".agents" / "scripts"))
        from inject_fact_anchors import _derive_as_of
        self.assertEqual(_derive_as_of("/tmp/whatever/Racecard.md"), "")


if __name__ == "__main__":
    unittest.main()
