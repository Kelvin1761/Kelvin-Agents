"""官方傷患記錄頁（2026-10-20，EXP-20261020-02）：parser、point-in-time、顯示、預設唔入分。"""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import hkjc_official_injury as oi  # noqa: E402
from hkjc_racing_engine import scoring  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402

PAGE = """## --- PAGE 33 ---
傷患記錄
場次 馬號 馬名 烙印編號 日期 詳情 通過日期
2 後備 2 電訊驕陽 J332 23/09/2026 賽後內窺鏡檢查發現氣管內有大量血液 09/10/2026
5 5 豐勝多彩 L324 18/06/2026 試閘時表現欠佳 18/09/2026
10 超強六十 J071 16/07/2026 左前球節接受關節鏡手術（移除碎骨） 06/10/2026
6 2 太行美景 K111 25/02/2026 表現令人失望，賽後內窺鏡檢查發現氣管內有
大量血液 19/03/2026
24/10/2025 未能通過獸醫檢驗：右後腿脛骨受傷 12/03/2026
7 3 未來馬 K222 25/10/2026 賽後右前腿不良於行 01/11/2026
其他傷患記錄
場次 馬號 馬名 烙印編號 日期 詳情
由香港賽馬會賽事秘書處編制
"""


def _horse(records=None):
    data = {"medical_flags": "✅ 無醫療事故記錄", "weight_trend": "1065→1070 → 穩定"}
    if records is not None:
        data["official_injury_records"] = records
    return {"horse_name": "超強六十", "jockey": "X", "trainer": "Y", "barrier": "3", "weight": "124",
            "last_6_finishes": "5-4-6", "_data": data}


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.recs = oi.parse_injury_page(PAGE)
        self.by = {(r["name"], r["detail"][:6]): r for r in self.recs}

    def test_race_number_carries_to_rows_without_it(self):
        surgery = next(r for r in self.recs if r["name"] == "超強六十")
        self.assertEqual(surgery["race"], 5)
        self.assertEqual(surgery["horse_no"], "10")
        self.assertEqual(surgery["incident_date"], date(2026, 7, 16))
        self.assertEqual(surgery["passed_date"], date(2026, 10, 6))

    def test_standby_and_wrapped_detail_and_extra_record(self):
        standby = next(r for r in self.recs if r["name"] == "電訊驕陽")
        self.assertEqual((standby["race"], standby["horse_no"]), (2, "後備2"))
        wrapped = [r for r in self.recs if r["name"] == "太行美景"]
        self.assertEqual(len(wrapped), 2)
        self.assertTrue(wrapped[0]["detail"].endswith("大量血液"))
        self.assertEqual(wrapped[1]["incident_date"], date(2025, 10, 24))

    def test_performance_only_split(self):
        perf = {r["name"]: r["performance_only"] for r in self.recs}
        self.assertTrue(perf["豐勝多彩"])           # 試閘時表現欠佳
        self.assertFalse(perf["超強六十"])
        self.assertFalse(next(r for r in self.recs if r["name"] == "太行美景")["performance_only"])  # 表現差＋流血

    def test_point_in_time_drops_future_incidents(self):
        kept = {r["name"] for r in oi.records_as_of(self.recs, date(2026, 10, 21))}
        self.assertIn("超強六十", kept)
        self.assertNotIn("未來馬", kept)          # 事故日期遲過賽日


class EngineTests(unittest.TestCase):
    RECORD = [{"race": 5, "incident_date": "2026-07-16", "detail": "左前球節接受關節鏡手術（移除碎骨）",
               "passed_date": "2026-10-06", "section": "main", "performance_only": False}]
    CTX = {"race_date": "2026-10-21", "venue": "跑馬地", "distance": "1650m"}

    def tearDown(self):
        scoring.OFFICIAL_INJURY_SCORING = "off"

    def test_live_default_is_off(self):
        self.assertEqual(scoring.OFFICIAL_INJURY_SCORING, "off")

    def test_display_shows_record_without_moving_scores(self):
        plain = RacingEngine(json.loads(json.dumps(_horse())), dict(self.CTX)).analyze_horse()
        flagged = RacingEngine(json.loads(json.dumps(_horse(self.RECORD))), dict(self.CTX)).analyze_horse()
        self.assertEqual(plain["ability_score_raw"], flagged["ability_score_raw"])
        self.assertEqual(plain["matrix_scores"], flagged["matrix_scores"])
        self.assertTrue(any("關節鏡手術" in line for line in flagged["health_readout"]["lines"]))
        self.assertIn("賽會傷患記錄", flagged["matrix_reasoning"]["horse_health"]["text"])

    def test_arms_lower_health_only_when_switched_on(self):
        scores = {}
        for mode in ("off", "no_clear", "issue"):
            scoring.OFFICIAL_INJURY_SCORING = mode
            r = RacingEngine(json.loads(json.dumps(_horse(self.RECORD))), dict(self.CTX)).analyze_horse()
            scores[mode] = r["feature_scores"]["risk_score"]
        self.assertEqual(scores["off"] - scores["no_clear"], scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_clear_bonus"])
        self.assertLess(scores["issue"], scores["no_clear"])

    def test_performance_only_record_never_scores(self):
        perf = [{**self.RECORD[0], "detail": "表現令人失望", "performance_only": True}]
        scoring.OFFICIAL_INJURY_SCORING = "issue"
        a = RacingEngine(json.loads(json.dumps(_horse())), dict(self.CTX)).analyze_horse()
        b = RacingEngine(json.loads(json.dumps(_horse(perf))), dict(self.CTX)).analyze_horse()
        self.assertEqual(a["feature_scores"]["risk_score"], b["feature_scores"]["risk_score"])


if __name__ == "__main__":
    unittest.main()
