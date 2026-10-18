"""EXP-20261018-02：騎師／練馬師同程 prior 嘅路程鍵要係 "1200"，唔係 "1200.0"。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hkjc_racing_engine.live_priors import TrainerSignalPriors  # noqa: E402


class DistanceKeyTests(unittest.TestCase):
    def test_float_and_int_seasons_merge_under_integer_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "a.csv"
            new = Path(tmp) / "b.csv"
            old.write_text("Jockey,Distance,Wins,Starts,Places\n潘頓,1200,10,50,20\n", encoding="utf-8")
            new.write_text("Jockey,Distance,Wins,Starts,Places\n潘頓,1200.0,5,30,9\n", encoding="utf-8")
            priors = TrainerSignalPriors.__new__(TrainerSignalPriors)
            table = priors._load_grouped([old, new], ["Jockey", "Distance"])
        self.assertIn(("潘頓", "1200"), table)
        self.assertNotIn(("潘頓", "1200.0"), table)
        self.assertEqual(table[("潘頓", "1200")]["starts"], 80.0)

    def test_live_tables_use_integer_keys(self):
        priors = TrainerSignalPriors()
        for table in (priors.jockey_distance, priors.trainer_distance):
            if table:
                self.assertFalse(any(key[1].endswith(".0") for key in table), "distance key still float-formatted")


if __name__ == "__main__":
    unittest.main()
