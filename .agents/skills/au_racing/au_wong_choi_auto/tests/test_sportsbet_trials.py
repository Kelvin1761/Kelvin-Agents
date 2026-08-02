"""試閘（barrier trial）同「掃描範圍冇界」呢一類缺陷。

試閘係有用嘅數據 —— 有時間、有 600m 段速、有走位、有頭三名同負距。Sportsbet
全部都出，但我哋一路攞唔到，因為連續三個 regex 都收得太緊或者放得太闊：

  1. `RE_HDR` 要求場地括號入面最少一個字母，但試閘寫 `( )`（空）→ 成類試閘
     冇 header → 靜靜咁被丟。實測 109 段往績有 26 段（24%）冇 header，
     `trial_score` 只得 7% 有證據（現有數據源 54%）。
  2. 試閘標記一度掃成段文字，於是隔籬段嘅 "Barrier Trial" 漏過嚟，把一場
     14 匹、負 15.85L 嘅正式 Caulfield 賽事標成試閘。
  3. `RE_PRIZE` 要求 `$`，但試閘寫 `(of 0)` —— 冇 `$`。於是試閘 match 唔到，
     再喺較闊視窗撈到**下一仗**嘅獎金，試閘顯示 $175,000。

三個都係同一個病：**範圍冇界／條件太死，就會靜靜咁撈錯或者掉走數據**。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
AU_RACING = ROOT / ".agents" / "skills" / "au_racing"
sys.path.insert(0, str(AU_RACING))

from claw_sportsbet_form import parse_race, run_line  # noqa: E402

# 照 Sportsbet 真實排版：header → Finished → 頭三名，逐仗接落去。
TRIAL = ("Wyong ( ) 23/12/2025 Race 7 1000m OPEN-BT Barrier Trial "
         "Finished 1/5 (of 0), Jockey Mollie Fitzgerald, Barrier 4, Weight 57.0kg "
         "Sectionals 600m 35.560s "
         "1st Rivkin (Mollie Fitzgerald 57.0kg) Winning Time 1:01.540 "
         "2nd Zelestial (J Duggan 57.0kg) 0.37L 3rd Oui Flourish (R Jones 57.0kg) 0.85L ")
REAL = ("Dubbo ( Good ) 03/05/2026 Race 5 1100m BM82 "
        "Finished 2/13 0.43L $5,050 (of $27,000), Jockey Reece Jones, "
        "Barrier 10, Weight 57.0kg 5.50 "
        "In running 800m 4th, 400m 5th Sectionals 600m 34.630s "
        "1st Wave Breaker (J Penza 57.0kg) Winning Time 1:02.180 ")


def _runs(body):
    return parse_race(f"<html><head><title>Flemington Race 5</title></head>"
                      f"<body><div>{body}</div></body></html>")["runs"]


class TrialParsingTest(unittest.TestCase):
    def test_an_empty_going_still_yields_a_header(self):
        r = _runs(TRIAL)[0]
        self.assertIsNotNone(r["header"], "試閘 `( )` 空場地 → header 冇咗 → 成仗被丟")
        self.assertEqual(r["header"]["date"], "23/12/2025")

    def test_trial_is_flagged_and_marked_for_downstream(self):
        line, _ = run_line(_runs(TRIAL)[0])
        self.assertIn("**(TRIAL)**", line)     # inject_fact_anchors.TRIAL_MARKER

    def test_the_useful_parts_of_a_trial_survive(self):
        """試閘嘅價值就係呢啲 —— 段速同對手。冇咗就淨返一個日期。"""
        r = _runs(TRIAL)[0]
        self.assertEqual(r["l600"], "35.560")
        names = [o["name"].strip() for o in r["opponents"]]
        self.assertEqual(names[:3], ["Rivkin", "Zelestial", "Oui Flourish"])
        self.assertEqual(r["opponents"][1]["mgn"], "0.37")

    def test_trial_prize_is_zero_not_the_next_runs_prize(self):
        self.assertEqual((_runs(TRIAL)[0]["prize"] or "0").replace(",", ""), "0")

    def test_the_trial_label_does_not_leak_into_the_track_name(self):
        line, _ = run_line(_runs(TRIAL)[0])
        self.assertTrue(line.startswith("Wyong "), line[:60])


class ScanWindowTest(unittest.TestCase):
    """一仗嘅欄位唔可以撈到下一仗嘅。"""

    def test_a_real_race_next_to_a_trial_is_not_flagged_as_one(self):
        runs = _runs(TRIAL + REAL)
        self.assertEqual([r["is_trial"] for r in runs], [True, False])

    def test_a_trial_before_a_real_race_keeps_its_own_zero_prize(self):
        trial, real = _runs(TRIAL + REAL)
        self.assertEqual((trial["prize"] or "0").replace(",", ""), "0")
        self.assertEqual(real["prize"], "27,000")

    def test_in_running_does_not_bleed_backwards(self):
        # 試閘冇走位；後面嗰仗有。試閘唔可以攞到後面嗰仗嘅 800m/400m。
        trial, real = _runs(TRIAL + REAL)
        self.assertIsNone(trial["p800"])
        self.assertEqual((real["p800"], real["p400"]), ("4th", "5th"))

    def test_sectionals_stay_with_their_own_run(self):
        trial, real = _runs(TRIAL + REAL)
        self.assertEqual(trial["l600"], "35.560")
        self.assertEqual(real["l600"], "34.630")


if __name__ == "__main__":
    unittest.main()
