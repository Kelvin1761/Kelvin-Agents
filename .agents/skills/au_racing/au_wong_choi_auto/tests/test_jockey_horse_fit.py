from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
ENGINE = (
    ROOT
    / ".agents"
    / "skills"
    / "au_racing"
    / "au_wong_choi_auto"
    / "scripts"
)
sys.path.insert(0, str(ENGINE))

from au_racing_engine.engine_core import RacingEngine, _surname_token_match


def _score(*, wins: int, places: int) -> float:
    horse = {
        "horse_name": "Test Horse",
        "horse_number": "1",
        "jockey": "Test Jockey",
        "trainer": "Test Trainer",
        "_data": {
            "current_jockey_formal_rides": 4,
            "current_jockey_formal_places": places,
            "current_jockey_formal_wins": wins,
        },
    }
    context = {
        "distance": "1400m",
        "field_summary": {"count": 10},
        "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"},
    }
    return RacingEngine(horse, context)._jockey_horse_fit_score()[0]


class JockeyHorseFitTests(unittest.TestCase):
    def test_formal_places_already_include_wins(self) -> None:
        # Both records have two top-three finishes.  A win is already included
        # in formal_places, so changing their composition must not add it twice.
        self.assertAlmostEqual(
            _score(wins=0, places=2),
            _score(wins=2, places=2),
        )

    def test_generic_stored_change_is_enriched_with_jockey_tiers(self) -> None:
        horse = {
            "horse_name": "Test Horse",
            "horse_number": "1",
            "jockey": "Current Rider",
            "_data": {
                "jockey_change_signal": "由 Previous Rider 轉配 Current Rider",
                "latest_official_jockey": "Previous Rider",
            },
        }
        engine = RacingEngine(
            horse,
            {
                "distance": "1400m",
                "field_summary": {"count": 10},
                "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"},
            },
        )
        with patch.object(
            engine,
            "_jockey_rank_value",
            side_effect=lambda name: 3 if "Current" in name else 1,
        ):
            self.assertIn("換上較強騎師", engine._jockey_change_signal())

    def test_specific_stored_change_is_not_overwritten(self) -> None:
        horse = {
            "horse_name": "Test Horse",
            "horse_number": "1",
            "jockey": "Current Rider",
            "_data": {
                "jockey_change_signal": "沿用上仗騎師",
                "latest_official_jockey": "Current Rider",
            },
        }
        engine = RacingEngine(
            horse,
            {
                "distance": "1400m",
                "field_summary": {"count": 10},
                "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"},
            },
        )
        self.assertEqual(engine._jockey_change_signal(), "沿用上仗騎師")


def _engine(*, jockey: str = "Test Jockey", trainer: str = "Test Trainer"):
    horse = {
        "horse_name": "Test Horse", "horse_number": "1",
        "jockey": jockey, "trainer": trainer, "_data": {},
    }
    return RacingEngine(horse, {
        "distance": "1400m", "field_summary": {"count": 10},
        "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"},
    })


class TopTierGateTests(unittest.TestCase):
    """頂級騎練由**評級 DB** 決定，唔再靠姓氏 substring。

    2026-09-05 審計（`docs/audits/AU_TRACK_JHF_DATA_QUALITY_2026-09-05.md`）：
    舊 fallback 用 `token in name`，836 場入面 190 個位判咗 T1，**189 個係錯** ——
    `Clark` 中 `Sheridan Clarke`、`Bott` 中 `Shane Bottomley`、
    `Rawiller` 中 Brad／Campbell（真嗰個係 Nash）。而九個 token 有六個指向嘅人
    **DB 明文評 T2**，即係 token 名單喺度推翻佢自己聲明嘅真相來源。
    """

    def test_the_db_still_decides_the_real_top_tier(self) -> None:
        self.assertTrue(_engine(jockey="Nash Rawiller")._is_top_jockey("Nash Rawiller"))
        self.assertTrue(_engine()._is_top_trainer("Chris Waller"))

    def test_a_shared_surname_no_longer_promotes_a_different_person(self) -> None:
        for name in ("Brad Rawiller", "Campbell Rawiller", "Lachlan King",
                     "Brooke King", "Margaret Collett"):
            self.assertFalse(_engine()._is_top_jockey(name), name)
        for name in ("Peter Maher", "Declan Maher", "Mitchell Freedman",
                     "Keith Dryden & Libby Snowden"):
            self.assertFalse(_engine()._is_top_trainer(name), name)

    def test_a_substring_of_a_surname_is_not_that_surname(self) -> None:
        # `Clarke` ⊃ `Clark`、`Bottomley` ⊃ `Bott` —— 舊 code 兩個都中。
        self.assertFalse(_engine()._is_top_jockey("Sheridan Clarke"))
        self.assertFalse(_engine()._is_top_trainer("Shane Bottomley"))

    def test_the_db_tier_wins_over_the_old_token_intent(self) -> None:
        # 六個舊 token 指向嘅人，DB 明文評 T2 —— 唔可以再當 T1。
        for name in ("Tim Clark", "Rachel King", "Jason Collett",
                     "Zac Lloyd", "Tyler Schiller", "Adam Hyeronimus"):
            self.assertFalse(_engine()._is_top_jockey(name), name)

    def test_the_one_genuine_alias_gap_is_covered_by_the_csv(self) -> None:
        # `Paul Snowden` 係 `Peter & Paul Snowden`（T1）嘅一半 —— 剷 token 之後
        # 要靠 CSV 別名補返，唔係靠 substring 撈。
        self.assertTrue(_engine()._is_top_trainer("Paul Snowden"))
        self.assertTrue(_engine()._is_top_trainer("Peter Snowden"))

    def test_an_unknown_name_is_simply_not_top_tier(self) -> None:
        self.assertFalse(_engine()._is_top_jockey("Nobody Atall"))
        self.assertFalse(_engine()._is_top_trainer("Nobody Atall"))
        self.assertFalse(_engine()._is_top_jockey(""))


class SurnameTokenMatchTests(unittest.TestCase):
    """`_jockey_rank_value` 嗰兩張名單係**純顯示**（rank 變化明文唔入分），
    但一樣要整個字比對 —— `Parr`⊃`Parry`、`Moore`⊃`Moorehouse` 係同一個隱患。"""

    def test_a_whole_word_matches(self) -> None:
        self.assertTrue(_surname_token_match("Jake Bayliss", ("Bayliss",)))
        self.assertTrue(_surname_token_match("Zac Moore", ("Moore", "Parr")))

    def test_a_longer_surname_does_not_match(self) -> None:
        self.assertFalse(_surname_token_match("Sheridan Clarke", ("Clark",)))
        self.assertFalse(_surname_token_match("Shane Bottomley", ("Bott",)))
        self.assertFalse(_surname_token_match("Jane Parry", ("Parr",)))
        self.assertFalse(_surname_token_match("Sam Moorehouse", ("Moore",)))

    def test_an_empty_name_is_no_match(self) -> None:
        self.assertFalse(_surname_token_match("", ("Moore",)))


if __name__ == "__main__":
    unittest.main()
