"""au_early_prices：只用賽日 10:30 前最後一張快照；配對馬號；冇檔／冇價 = None。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "au_wong_choi_auto" / "scripts"))

import au_early_prices as ep  # noqa: E402


class EarlyPriceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name) / "2026-11-24 Tamworth Race 1-8"
        d.mkdir()
        snaps = [
            {"captured_at": "2026-11-23T22:15:00+11:00", "races": {"1": {"1": {"Sportsbet-FixedWin": 5.0}}}},
            {"captured_at": "2026-11-24T10:05:00+11:00", "races": {"1": {"1": {"Sportsbet-FixedWin": 4.0},
                                                                         "2": {"Sportsbet-FixedWin": 3.0}}}},
            {"captured_at": "2026-11-24T12:10:00+11:00", "races": {"1": {"1": {"Sportsbet-FixedWin": 1.5}}}},
        ]
        (d / "Odds.json").write_text(json.dumps({"snapshots": snaps}))
        self.index = {d.name: d / "Odds.json"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_last_snapshot_before_cutoff_wins(self):
        prices = ep.early_prices(self.index["2026-11-24 Tamworth Race 1-8"], "2026-11-24")
        self.assertEqual(prices["1"], {"1": 4.0, "2": 3.0})           # 12:10（可能已開跑）唔用

    def test_attach_marks_missing(self):
        races = [{"date": "2026-11-24", "meeting": "2026-11-24 Tamworth Race 1-8", "race": 1,
                  "rows": [{"n": 1}, {"n": 2}, {"n": 3}]},
                 {"date": "2026-11-24", "meeting": "2026-11-24 Nowhere Race 1-8", "race": 1, "rows": [{"n": 1}]}]
        stats = ep.attach(races, self.index)
        self.assertEqual([x["early"] for x in races[0]["rows"]], [4.0, 3.0, None])
        self.assertIsNone(races[1]["rows"][0]["early"])
        self.assertEqual((stats["races_complete"], stats["no_odds_file"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
