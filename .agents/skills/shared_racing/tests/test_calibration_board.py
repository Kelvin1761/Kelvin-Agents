"""校準板（EXP-20261125-07）：分桶、Wilson CI、空集合、NBA 只讀唔重計、Tennis 讀 DB。"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "tests"))

import calibration_board as CB  # noqa: E402
from test_model_probability import fixture  # noqa: E402


class CalibrationBoardTests(unittest.TestCase):
    def test_wilson(self):
        lo, hi = CB.wilson(50, 100)
        self.assertAlmostEqual(lo, 0.4038, places=3)
        self.assertAlmostEqual(hi, 0.5962, places=3)
        self.assertEqual(CB.wilson(0, 10)[0], 0.0)
        self.assertEqual(CB.wilson(10, 10)[1], 1.0)
        self.assertIsNone(CB.wilson(0, 0))

    def test_buckets_edges_and_low_n(self):
        b = CB.buckets([(0.0, 0), (0.05, 1), (0.1, 1), (0.95, 1), (1.0, 1)])
        self.assertEqual(len(b), 10)
        self.assertEqual(b[0]["n"], 2)
        self.assertEqual(b[1]["n"], 1)                 # 0.1 入 [0.1, 0.2)
        self.assertEqual(b[9]["n"], 2)                 # 1.0 入最後一桶
        self.assertTrue(all(x["low_n"] for x in b))
        self.assertIsNone(b[5]["mean_p"])
        self.assertIsNone(b[5]["ci"])

    def test_empty_sets(self):
        s = CB.summary([])
        self.assertEqual(s["n"], 0)
        self.assertIsNone(s["logloss"])
        self.assertIsNone(s["hit_rate"])
        self.assertEqual(len(s["buckets"]), 10)
        empty = CB.racing_domain("au", [])
        self.assertEqual(empty["races"], 0)
        self.assertIsNone(empty["win"]["market"]["logloss_market"])

    def test_logloss(self):
        self.assertAlmostEqual(CB.logloss([(0.5, 1), (0.5, 0)]), 0.69315, places=4)

    def test_racing_domain_with_market(self):
        races = fixture()
        for r in races:
            for x in r["rows"]:
                x["sp"] = 0.8 * len(r["rows"])          # 等價、有水：市場 = 均勻
        out = CB.racing_domain("hkjc", races)
        self.assertGreater(out["races"], 0)
        self.assertEqual(out["top3"]["market"]["races"], out["races"])
        self.assertLess(out["win"]["market"]["logloss_model"], out["win"]["market"]["logloss_market"])
        self.assertEqual(sum(b["n"] for b in out["top3"]["buckets"]), out["top3"]["n"])

    def test_missing_price_skips_market_only(self):
        races = fixture()
        out = CB.racing_domain("au", races)              # 冇 sp
        self.assertGreater(out["top3"]["n"], 0)
        self.assertEqual(out["top3"]["market"]["n"], 0)

    def test_nba_reads_without_recompute(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "rel.json"
            p.write_text(json.dumps({"status": "ok", "overall": {"n": 10, "mean_p": 0.3},
                                     "buckets": [{"bucket": "0.0-0.1", "n": 40, "mean_p": 0.05, "hit_rate": 0.05}]}))
            out = CB.nba_domain(p)
            self.assertFalse(out["recomputed"])
            self.assertTrue(out["buckets"][0]["low_n"])
            self.assertEqual(out["buckets"][0]["ci"], CB.wilson(2, 40))
            self.assertEqual(CB.nba_domain(Path(tmp) / "nope.json")["status"], "missing")

    def test_tennis_featured_and_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            c = sqlite3.connect(db)
            c.execute("CREATE TABLE prop_tracker (id INTEGER PRIMARY KEY, model_prob_raw REAL, market_prob_fair REAL,"
                      " result_status TEXT)")
            c.execute("CREATE TABLE featured_picks (prop_id INTEGER, model_prob REAL)")
            c.executemany("INSERT INTO prop_tracker VALUES (?,?,?,?)",
                          [(1, 0.6, 0.5, "WON"), (2, 0.4, 0.5, "LOST"), (3, 0.5, None, "VOID"), (4, 0.7, 0.6, "PENDING")])
            c.execute("INSERT INTO featured_picks VALUES (1, 0.65)")
            c.commit()
            c.close()
            out = CB.tennis_domain(db)
            self.assertEqual(out["all"]["n"], 2)
            self.assertEqual(out["featured"]["n"], 1)
            self.assertEqual(out["featured"]["mean_p"], 0.65)
            self.assertLess(out["all"]["market"]["logloss_model"], out["all"]["market"]["logloss_market"])


if __name__ == "__main__":
    unittest.main()
