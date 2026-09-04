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


class RacecardMetadataTests(unittest.TestCase):
    """冇 Logic 嘅場次要由排位表補 distance／class。

    一個從來冇評分過嘅場次冇 `Race_*_Logic.json`，所以 Logic 那一 pass 會令佢
    每一匹馬嘅距離同班次都空白 —— 2026-07-15（跑馬地，107 行）就係咁：賽果有，
    metadata 100% 空，而賽果 payload 本身根本冇距離欄
    （`racedate/race_no/venue/results/sectional_times/...`）。排位表有、係賽前
    資料、而且一直喺硬碟上面。實測補完之後全庫缺距離由 119 行跌到 12 行。
    """

    CARD = "\n".join([
        "場次: 第1場",
        "地點: 跑馬地",
        "路程: 1650米",
        "班次: 第五班",
        "",
        "馬號: 1",
        "馬名: 測試馬",
        "騎師: J",
        "",
        "馬號: 2",
        "馬名: 第二馬",
        "騎師: K",
    ])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.md = Path(self.temp.name) / "2026-07-15_HappyValley"
        self.md.mkdir()
        self.card = self.md / "07-15 Race 1 排位表.md"
        self.card.write_text(self.CARD, encoding="utf-8")
        self.result_path = self.md / "全日賽果.json"
        self.result_path.write_text(json.dumps({"1": dict(
            racedate="2026-07-15", venue="HappyValley", race_no=1,
            results=[dict(horse_no="1", horse_name="測試馬(K543)", pos="1",
                          jockey="J", trainer="T")])}), encoding="utf-8")
        self.base = pd.DataFrame([dict(Date="2026-07-15", Horse="測試馬(K543)",
            Rank=1, Win=1, Place=1, Jockey="J", Trainer="T", Venue="跑馬地",
            Distance=None, RaceClass=None)])

    def merge(self, racecards=None):
        return supplement_rows(self.base, [self.result_path], [],
                               racecards if racecards is not None else [self.card])

    def test_without_a_racecard_the_metadata_stays_absent(self):
        out = self.merge(racecards=[])
        self.assertTrue(pd.isna(out.loc[0, "Distance"]))

    def test_racecard_fills_distance_and_class(self):
        out = self.merge()
        self.assertEqual(int(out.loc[0, "Distance"]), 1650)
        self.assertEqual(out.loc[0, "RaceClass"], "第五班")
        self.assertEqual(out.loc[0, "Venue"], "跑馬地")

    def test_the_racecard_is_never_written(self):
        before = self.card.read_bytes()
        self.merge()
        self.assertEqual(before, self.card.read_bytes())

    def test_a_race_number_disagreement_fails_closed(self):
        self.card.write_text(self.CARD.replace("場次: 第1場", "場次: 第7場"),
                             encoding="utf-8")
        with self.assertRaises(ValueError):
            self.merge()

    def test_a_missing_field_is_left_absent_not_invented(self):
        self.card.write_text("\n".join(l for l in self.CARD.splitlines()
                                       if not l.startswith("路程:")), encoding="utf-8")
        out = self.merge()
        self.assertTrue(pd.isna(out.loc[0, "Distance"]))
        self.assertEqual(out.loc[0, "RaceClass"], "第五班")

    def test_a_horse_absent_from_the_racecard_gets_nothing(self):
        """後加／替補馬唔喺當時抽到嘅排位表上面 —— 實測 5 行係咁，
        要留空，唔可以攞同場其他馬嘅距離硬套上去。"""
        self.base = pd.DataFrame([dict(Date="2026-07-15", Horse="後加馬(K999)",
            Rank=1, Win=1, Place=1, Jockey="J", Trainer="T", Venue="跑馬地",
            Distance=None, RaceClass=None)])
        self.result_path.write_text(json.dumps({"1": dict(
            racedate="2026-07-15", venue="HappyValley", race_no=1,
            results=[dict(horse_no="9", horse_name="後加馬(K999)", pos="1",
                          jockey="J", trainer="T")])}), encoding="utf-8")
        out = self.merge()
        self.assertTrue(pd.isna(out.loc[0, "Distance"]))

    def test_logic_wins_when_both_exist(self):
        """Logic 係權威來源；排位表只補佢冇覆蓋到嘅 key。"""
        logic = self.md / "Race_1_Logic.json"
        logic.write_text(json.dumps(dict(
            race_analysis=dict(distance="1200m", venue="跑馬地", race_number=1,
                               race_class="第三班"),
            horses={"1": dict(horse_name="測試馬")})), encoding="utf-8")
        out = supplement_rows(self.base, [self.result_path], [logic], [self.card])
        self.assertEqual(int(out.loc[0, "Distance"]), 1200)
        self.assertEqual(out.loc[0, "RaceClass"], "第三班")
