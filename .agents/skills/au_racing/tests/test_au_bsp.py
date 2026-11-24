"""au_bsp：CSV＋記錄器載入、記錄器覆蓋 CSV、PLACE 場次號、配對（精確／後備／miss）、退出馬。唔連網。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "au_wong_choi_auto" / "scripts"))

import au_bsp  # noqa: E402

HEADER = "event_id,menu_hint,event_name,event_dt,selection_id,selection_name,win_lose,bsp\n"


class AuBspTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.csv_dir = root / "betfair_bsp"
        self.csv_dir.mkdir()
        (self.csv_dir / "dwbfpricesauswin31082026.csv").write_text(HEADER + "\n".join([
            "1,Corowa (AUS) 31st Aug,R2 1600m CL1,31-08-2026 05:20,11,1. Barrett Reef,0,36.89",
            "1,Corowa (AUS) 31st Aug,R2 1600m CL1,31-08-2026 05:20,12,2. Fast One,1,2.10",
            "1,Corowa (AUS) 31st Aug,R2 1600m CL1,31-08-2026 05:20,13,3. Scratched,0,",
        ]) + "\n", encoding="utf-8")
        (self.csv_dir / "dwbfpricesausplace31082026.csv").write_text(HEADER + "\n".join([
            "2,Corowa (AUS) 31st Aug,To Be Placed,31-08-2026 05:20,11,1. Barrett Reef,0,8.5",
        ]) + "\n", encoding="utf-8")
        self.log = root / "log"
        day = self.log / "2026-08-31"
        day.mkdir(parents=True)
        cat = [{"market": "1.1", "type": "WIN", "event_id": "E", "name": "R2 1600m CL1", "start": "S",
                "event": "Corowa (AUS) 31st Aug", "venue": "Corowa",
                "runners": [{"id": 11, "name": "Barrett Reef"}, {"id": 12, "name": "Fast One"}]},
               {"market": "1.2", "type": "PLACE", "event_id": "E", "name": "To Be Placed", "start": "S",
                "venue": "Corowa", "runners": [{"id": 12, "name": "Fast One"}]}]
        settle = [{"market": "1.1", "status": "CLOSED", "runners": [
                      {"id": 11, "status": "LOSER", "bsp": None}, {"id": 12, "status": "WINNER", "bsp": None}]},
                  {"market": "1.1", "status": "CLOSED", "runners": [      # 重新結算嘅新行（最後一行贏）
                      {"id": 11, "status": "LOSER", "bsp": 40.0}, {"id": 12, "status": "WINNER", "bsp": 2.2}]},
                  {"market": "1.2", "status": "CLOSED", "runners": [{"id": 12, "status": "WINNER", "bsp": 1.3}]}]
        (day / "catalogue.jsonl").write_text("\n".join(json.dumps(c) for c in cat), encoding="utf-8")
        (day / "settle.jsonl").write_text("\n".join(json.dumps(s) for s in settle), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_csv_loads_win_and_place_by_race(self) -> None:
        idx = au_bsp.load_csv([self.csv_dir])
        self.assertEqual(idx[("2026-08-31", "corowa", 2, "barrettreef")], {"win": 36.89, "place": 8.5})
        self.assertIsNone(idx[("2026-08-31", "corowa", 2, "scratched")]["win"])

    def test_logger_overrides_csv_and_uses_last_settle_row(self) -> None:
        idx = au_bsp.load_all(self.log, [self.csv_dir])
        self.assertEqual(idx[("2026-08-31", "corowa", 2, "barrettreef")]["win"], 40.0)
        self.assertEqual(idx[("2026-08-31", "corowa", 2, "fastone")], {"win": 2.2, "place": 1.3})

    def test_attach_exact_fallback_and_miss(self) -> None:
        idx = au_bsp.load_all(self.log, [self.csv_dir])
        races = [{"date": "2026-08-31", "meeting": "2026-08-31 Corowa Race 1-8", "race": 2, "rows": [
                     {"name": "Barrett Reef"}, {"name": "Fast One"}]},
                 {"date": "2026-08-31", "meeting": "2026-08-31_Corowa Park_Race_2", "race": 2, "rows": [
                     {"name": "Fast One"}, {"name": "Nobody"}]}]
        stats = au_bsp.attach(races, idx)
        self.assertEqual(races[0]["rows"][1]["bsp"], 2.2)
        self.assertEqual(races[1]["rows"][0]["bsp"], 2.2)          # 場地名唔同 → 後備 (日期, 馬名, 場次)
        self.assertIsNone(races[1]["rows"][1]["bsp"])
        self.assertEqual((stats["exact"], stats["fallback"], stats["miss"]), (2, 1, 1))
        self.assertEqual(stats["races_complete"], 1)

    def test_norm_strips_saddle_number(self) -> None:
        self.assertEqual(au_bsp.norm("8. Can't Touch This"), "canttouchthis")


if __name__ == "__main__":
    unittest.main()
