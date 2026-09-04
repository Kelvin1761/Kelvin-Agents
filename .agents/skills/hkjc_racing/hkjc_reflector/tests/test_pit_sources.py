"""Regression coverage for read-only source supplementation and identity joins."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pit_sources import supplement_rows


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.md = Path(self.temp.name) / "2026-06-01_ShaTin"
        self.md.mkdir()
        self.result_path = self.md / "全日賽果.json"
        self.logic_path = self.md / "Race_1_Logic.json"
        self.result = {"1": dict(racedate="2026-06-01", venue="ShaTin", race_no=1,
            results=[dict(horse_no="1", horse_name="測試馬(H123)", pos="2",
                          jockey="J", trainer="T")])}
        self.logic = dict(race_analysis=dict(distance="1200m", venue="沙田", race_number=1),
                          horses={"1": dict(horse_name="測試馬")})
        self.base = pd.DataFrame([dict(Date="2026-06-01", Horse="測試馬(H123)",
            Rank=2, Win=0, Place=1, Jockey="J", Trainer="T", Venue="沙田", Distance=None)])

    def run_merge(self):
        self.result_path.write_text(json.dumps(self.result))
        self.logic_path.write_text(json.dumps(self.logic))
        before = self.result_path.read_bytes(), self.logic_path.read_bytes()
        result = supplement_rows(self.base, [self.result_path], [self.logic_path])
        self.assertEqual(before, (self.result_path.read_bytes(), self.logic_path.read_bytes()))
        return result

    def test_fills_metadata_without_double_counting_or_writing(self):
        actual = self.run_merge()
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual.iloc[0].Distance, 1200)
        self.assertEqual(actual.iloc[0].RaceNo, 1)
        self.assertEqual(actual.iloc[0].Horse, "測試馬(H123)")
        self.assertEqual(actual.attrs["source_audit"]["counts"]["filled_Distance"], 1)
        self.assertEqual(len(actual.attrs["source_audit"]["sources"]), 2)
        self.assertIsNone(self.base.iloc[0].Distance)

    def test_adds_missing_date(self):
        self.base.loc[0, "Date"] = "2026-05-01"
        actual = self.run_merge()
        self.assertEqual(len(actual), 2)
        self.assertEqual(actual.attrs["source_audit"]["added_dates"], ["2026-06-01"])

    def test_never_joins_by_number_without_name(self):
        self.logic["horses"]["1"]["horse_name"] = "另一匹馬"
        self.assertTrue(pd.isna(self.run_merge().iloc[0].Distance))

    def test_conflicting_result_rejected(self):
        self.result["1"]["results"][0]["pos"] = "1"
        with self.assertRaisesRegex(ValueError, "Conflicting result"):
            self.run_merge()

    def test_conflicting_distance_rejected(self):
        self.base.loc[0, "Distance"] = 1400
        with self.assertRaisesRegex(ValueError, "Conflicting metadata distance"):
            self.run_merge()

    def test_conflicting_date_rejected(self):
        self.result["1"]["racedate"] = "2026-06-02"
        with self.assertRaisesRegex(ValueError, "Conflicting result date"):
            self.run_merge()

    def test_duplicate_source_identity_rejected(self):
        self.base = pd.concat([self.base, self.base])
        with self.assertRaisesRegex(ValueError, "duplicate PIT base"):
            self.run_merge()

    def test_cross_date_ids_are_preserved(self):
        self.base.loc[0, "Date"] = "2026-05-01"
        self.base.loc[0, "Horse"] = "測試馬(H456)"
        actual = self.run_merge()
        self.assertEqual(set(actual.Horse), {"測試馬(H123)", "測試馬(H456)"})

    def test_same_date_conflicting_ids_rejected(self):
        self.base.loc[0, "Horse"] = "測試馬(H456)"
        with self.assertRaisesRegex(ValueError, "Conflicting horse ID"):
            self.run_merge()


if __name__ == "__main__":
    unittest.main()
