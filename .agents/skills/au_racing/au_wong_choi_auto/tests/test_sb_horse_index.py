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


class OpponentDerivedRecordsTests(unittest.TestCase):
    """對手名單砌出嚟嘅記錄（2026-08-04）。

    呢批記錄令對手命中由 12.8% 升到 99.9%，零額外請求。但佢哋有**系統性偏差**
    —— 只喺對手入前三嗰陣先見到佢 —— 所以一定要標記 `partial`，
    否則下游算上名率會永遠得出 100%，每隻對手都變「中組」以上。
    """

    def _blocks(self):
        return [{
            "name": "Our Runner",
            "runs": [{
                "pos": "6", "field": "8",
                "header": {"track": "Flemington", "date": "06/03/2026", "race": "7"},
                "opponents": [
                    {"ord": "1st", "name": "Emery"},
                    {"ord": "2nd", "name": "Beaumista"},
                    {"ord": "3rd", "name": "Gogmagog"},
                ],
            }],
        }]

    def test_opponents_become_dated_run_records(self):
        idx = {}
        stats = IDX.update(self._blocks(), index=idx, save_now=False)
        self.assertEqual(stats["opponent_runs_added"], 3)
        self.assertIn("emery", idx)
        run = idx["emery"]["runs"][0]
        self.assertEqual(run["finish"], 1)
        self.assertEqual(run["date"], "2026-03-06")
        self.assertEqual(run["venue"], "Flemington")

    def test_opponent_records_are_marked_partial(self):
        """冇呢個 flag，下游就會把「見到佢入前三 3 次」當成「出賽 3 次全部上名」。"""
        idx = {}
        IDX.update(self._blocks(), index=idx, save_now=False)
        self.assertTrue(all(r.get("partial") for r in idx["emery"]["runs"]))
        self.assertFalse(idx["our-runner"]["runs"][0].get("partial"))

    def test_a_complete_record_replaces_the_partial_one(self):
        """同一場如果之後抓到嗰匹馬自己嘅 runner block，要升級 —— 唔可以留住
        個 partial 版，否則佢個真實名次（可能係第 8）永遠見唔到。"""
        idx = {}
        IDX.update(self._blocks(), index=idx, save_now=False)
        self.assertTrue(idx["emery"]["runs"][0]["partial"])
        IDX.update([{
            "name": "Emery",
            "runs": [{"pos": "1", "field": "8",
                      "header": {"track": "Flemington", "date": "06/03/2026", "race": "7"},
                      "opponents": []}],
        }], index=idx, save_now=False)
        runs = idx["emery"]["runs"]
        self.assertEqual(len(runs), 1, "同一場唔應該有兩條記錄")
        self.assertFalse(runs[0].get("partial"))

    def test_opponents_can_be_switched_off(self):
        idx = {}
        stats = IDX.update(self._blocks(), index=idx, save_now=False,
                                      opponents=False)
        self.assertEqual(stats["opponent_runs_added"], 0)
        self.assertNotIn("emery", idx)


class OpponentFollowupStringTests(unittest.TestCase):
    """對手後續走勢字串有兩種寫法，四處 regex 一定要兩種都認。

    2026-08-04 加咗「見前三 N 次」呢個寫法畀 partial 記錄用（因為講「出 N 次」
    對只由對手名單推導出嚟嘅記錄係講大話）。加嗰陣四處獨立 regex 一齊變成
    只認舊寫法 —— 即係新增嗰 12,737 隻對手會**靜靜咁**被當成「冇後續走勢」。
    呢個 repo 已經有五次同款缺陷，所以釘死佢。
    """

    def test_both_wordings_yield_the_win_count(self):
        import sys as _sys
        from pathlib import Path as _P
        _sys.path.insert(0, str(_P(__file__).resolve().parents[1]
                                / "scripts" / "racing_engine"))
        from engine_core import RE_OPP_FOLLOWUP

        for text, expected in (("出 3 次: 1 勝", "1"),
                               ("見前三 2 次: 2 勝", "2"),
                               ("出 10 次: 0 勝", "0")):
            with self.subTest(text=text):
                m = RE_OPP_FOLLOWUP.search(text)
                self.assertIsNotNone(m, f"讀唔到「{text}」")
                self.assertEqual(m.group(1), expected)

    def test_no_evidence_wordings_do_not_match(self):
        """「未見前三」同「查冊失敗」都唔可以當成 0 勝 —— 冇證據唔係壞成績。"""
        import sys as _sys
        from pathlib import Path as _P
        _sys.path.insert(0, str(_P(__file__).resolve().parents[1]
                                / "scripts" / "racing_engine"))
        from engine_core import RE_OPP_FOLLOWUP

        for text in ("未見前三", "查冊失敗", "查冊不可用", "未有出賽"):
            with self.subTest(text=text):
                self.assertIsNone(RE_OPP_FOLLOWUP.search(text))
