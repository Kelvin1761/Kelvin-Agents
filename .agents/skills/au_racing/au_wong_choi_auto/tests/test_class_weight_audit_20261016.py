"""EXP-20261016-18 官方評分對位修正嘅回歸測試（R1x、R2x、R4x、R5a/b、R6x）。"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from au_racing_engine.dimensions import CLASS_SCORE_LIVE_WEIGHT, RATING_SCORE_SHARE  # noqa: E402
from au_racing_engine.engine_core import RacingEngine  # noqa: E402

K = CLASS_SCORE_LIVE_WEIGHT / RATING_SCORE_SHARE


def engine(race_class="BM64 Handicap", venue="Flemington"):
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 5, "weight": 58.0, "_data": {}}
    eng = RacingEngine(horse, {"race_class": race_class, "distance": "1400m",
                               "meeting_intelligence": {"venue": venue}})
    return eng


def rating_engine(rating, field, class_value=66.0, weight_proxy=(70.0, "負磅代理 70")):
    eng = engine()
    eng._horse_rating = lambda: rating
    eng._field_summary = lambda: field
    eng._class_score = lambda: (class_value, "", "")
    eng._handicap_weight_proxy = lambda: weight_proxy
    return eng


class TestRatingProxy:
    def test_mixed_field_unrated_uses_weight_ruler_only(self):
        eng = rating_engine(None, {"rated_count": 6})
        score, _note, src = eng._rating_score()
        assert src == "weight_proxy_mixed_field"
        assert score == pytest.approx(70.0 - K * (66.0 - 60.0))

    def test_unrated_field_class_counted_once(self):
        eng = rating_engine(None, {"rated_count": 0})
        score, _note, src = eng._rating_score()
        assert src == "class_weight_proxy"
        assert score == pytest.approx(0.5 * 66.0 + 0.5 * 70.0 - K * 6.0)
        # 維度入面 class_score 嘅總份額 = 0.70 × (0.5 − K) + 0.15 = 0.70 × 0.5
        assert RATING_SCORE_SHARE * (0.5 - K) + CLASS_SCORE_LIVE_WEIGHT == pytest.approx(0.35)

    def test_no_weight_proxy_falls_back_to_class_once(self):
        eng = rating_engine(None, {"rated_count": 0}, weight_proxy=(None, ""))
        score, _note, src = eng._rating_score()
        assert src == "class_proxy"
        assert score == pytest.approx(66.0 - K * 6.0)


class TestOfficialRatingNoHandTunedTerms:
    @pytest.mark.parametrize("race_class", ["BM58 Handicap", "Maiden Plate", "Class 3 Handicap"])
    def test_z_only(self, race_class):
        eng = engine(race_class)
        eng._horse_rating = lambda: 70.0
        eng._field_summary = lambda: {"rated_count": 8, "avg_rating": 64.0, "rating_stdev": 4.0,
                                      "top3_rating_cutoff": 68.0}
        score, _note, _src = eng._rating_score()
        assert score == pytest.approx(60.0 + 1.5 * 6.0)   # 冇前三門檻、冇 BM／處女乘數


class TestVenueTier:
    @pytest.mark.parametrize("venue", ["Morphettville", "Ascot", "Belmont", "The Valley", "Flemington"])
    def test_metro(self, venue):
        assert engine()._venue_tier(venue) == "metro"

    def test_country_is_provincial(self):
        assert engine()._venue_tier("Kalgoorlie") == "provincial"


class TestClassScoreRelativePlacing:
    def class_score(self, placing, field_size, starts):
        eng = engine()
        eng._career_starts = lambda: starts
        eng._class_move_today = lambda: ""
        eng._official_entry_cache = [{"placing": placing, "field_size": field_size, "venue": "Flemington",
                                      "is_trial": False}]
        return eng._class_score()[0]

    def test_third_of_five_is_not_placed_but_third_of_sixteen_is(self):
        # 5 匹第 3：pct 0.5 → 唔算上名；16 匹第 3：pct 0.13 → 上名
        assert self.class_score("3/5", 5, 3) < self.class_score("3/16", 16, 3)

    def test_without_field_size_keeps_absolute_rule(self):
        assert self.class_score("3", None, 3) > self.class_score("5", None, 3)
