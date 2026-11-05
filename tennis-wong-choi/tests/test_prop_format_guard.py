"""A BO3 prop distribution cannot price a men's Slam main-draw match."""
from __future__ import annotations

import pytest

from tennis_wc.features.bo_format import detect_match_format


@pytest.mark.parametrize("round_name", ["Qualifying", "Q1", "Q2", "Q3", "QR1"])
def test_slam_qualifying_is_best_of_three(round_name):
    assert detect_match_format({"tour": "ATP", "level": "GRAND_SLAM", "round": round_name}) == "BO3"


def test_slam_main_draw_and_wta_have_distinct_formats():
    assert detect_match_format({"tour": "ATP", "level": "GRAND_SLAM", "round": "R128"}) == "BO5"
    assert detect_match_format({"tour": "WTA", "level": "GRAND_SLAM", "round": "F"}) == "BO3"




def _meta(**over):
    return {"tour": "ATP", "player_a_tour": "ATP", "player_b_tour": "ATP",
            "tournament_level": "GRAND_SLAM", "round": "R128", **over}


def test_props_price_only_verified_best_of_three():
    from tennis_wc.pricing.props import _is_best_of_three

    assert not _is_best_of_three(_meta())                                  # men's slam main draw
    assert _is_best_of_three(_meta(round="Q2"))                            # slam qualifying
    assert _is_best_of_three(_meta(tour="WTA"))                            # women's slam
    assert not _is_best_of_three(_meta(tour="UNKNOWN", player_a_tour=None))  # format unverified
    assert _is_best_of_three(_meta(tournament_level="ATP_250"))
