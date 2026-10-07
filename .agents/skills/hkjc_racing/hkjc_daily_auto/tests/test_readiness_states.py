"""警報要分得出「有數據但刷新失敗」同「完全冇數據」。

2026-09-05 09-06 沙田嘅通知寫住：

    ⏳ HKJC 未完成｜2026-09-06 ShaTin
    exit=75｜第1次｜資料未齊，30 分鐘後自動重試
    排位表 10/10 · 賽績 7/10 · 晨操 10/10 · PDF ✅
    未齊：R1賽績、R2賽績、R3賽績

讀落係「呢三場冇賽績」。真相係三份檔都喺碟上而且完整（每匹 14.5 / 12.7 / 12.5
條賽績線 —— 全日最高），只係 HKJC 嗰一次刷新回空 runner rows，而
`_keep_valid_candidate` 明文「failed refreshes never destroy last good data」
保留咗舊檔。09-04 同一形狀（8/10）。

兩個完全唔同嘅狀態印同一句 = 讀者冇辦法決定要唔要起身處理。
發佈閘本身冇放寬：仍然要全部刷新成功才 `ready`。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import hkjc_daily_schedule as sched


def _write(tmp: Path, races, **top):
    payload = {"expected_races": len(races), "starter_pdf_ready": True,
               "racecards_ready": sum(1 for r in races if r.get("racecard_ok")),
               "formguides_ready": sum(1 for r in races if r.get("formguide_ok")),
               "trackwork_ready": len(races), "races": races} | top
    (tmp / "Extraction_Readiness.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return tmp


class ReadinessDigestStates(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())

    def _digest(self, races, **top):
        return sched.readiness_digest(_write(self.tmp, races, **top))

    def test_kept_is_not_reported_as_missing(self):
        """呢個就係 09-06 嗰個 case。"""
        races = [{"race": n, "racecard_ok": True, "racecard_state": "fresh",
                  "formguide_ok": n > 3,
                  "formguide_state": "fresh" if n > 3 else "kept"}
                 for n in range(1, 11)]
        out = self._digest(races)
        self.assertIn("刷新失敗但有舊有效檔", out)
        self.assertIn("R1賽績", out)
        self.assertNotIn("冇有效檔", out)

    def test_missing_is_called_out_separately(self):
        races = [{"race": 1, "racecard_ok": True, "racecard_state": "fresh",
                  "formguide_ok": False, "formguide_state": "missing"}]
        out = self._digest(races)
        self.assertIn("冇有效檔（要人睇）", out)
        self.assertIn("R1賽績", out)
        self.assertNotIn("刷新失敗但有舊有效檔", out)

    def test_both_states_in_one_meeting_are_split(self):
        races = [
            {"race": 1, "racecard_ok": True, "racecard_state": "fresh",
             "formguide_ok": False, "formguide_state": "kept"},
            {"race": 2, "racecard_ok": True, "racecard_state": "fresh",
             "formguide_ok": False, "formguide_state": "missing"},
        ]
        out = self._digest(races)
        gone = [l for l in out.splitlines() if l.startswith("冇有效檔")][0]
        stale = [l for l in out.splitlines() if l.startswith("刷新失敗")][0]
        self.assertIn("R2賽績", gone)
        self.assertNotIn("R1賽績", gone)
        self.assertIn("R1賽績", stale)
        self.assertNotIn("R2賽績", stale)

    def test_all_fresh_says_nothing_extra(self):
        races = [{"race": n, "racecard_ok": True, "racecard_state": "fresh",
                  "formguide_ok": True, "formguide_state": "fresh"}
                 for n in range(1, 4)]
        out = self._digest(races)
        self.assertNotIn("冇有效檔", out)
        self.assertNotIn("刷新失敗", out)

    def test_a_legacy_readiness_file_without_states_is_treated_as_missing(self):
        """舊檔冇 `*_state`：分唔到就保守當「冇」，唔可以靜靜當成 kept 而唔嗌。"""
        races = [{"race": 1, "racecard_ok": True, "formguide_ok": False}]
        out = self._digest(races)
        self.assertIn("冇有效檔（要人睇）", out)

    def test_the_counts_line_still_reports_refresh_not_validity(self):
        """頭一行係刷新成功數 —— 呢個係發佈閘用嘅數，唔准改成有效數。"""
        races = [{"race": n, "racecard_ok": True, "racecard_state": "fresh",
                  "formguide_ok": n > 3,
                  "formguide_state": "fresh" if n > 3 else "kept"}
                 for n in range(1, 11)]
        self.assertIn("賽績 7/10", self._digest(races))


if __name__ == "__main__":
    unittest.main()
