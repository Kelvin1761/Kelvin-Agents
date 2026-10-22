"""Injury exclusion: exact-string lookup and only literal 'Out' counted."""
from __future__ import annotations

import sys
from pathlib import Path

NBA = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA))
sys.path.insert(0, str(NBA / "nba_wong_choi/scripts"))
import generate_nba_reports as reports  # noqa: E402


def test_classify_statuses():
    out = ["Out", "OUT", "Out For Season", "Out (knee)", "Doubtful", "Suspension", "Injured Reserve"]
    dtd = ["Day-To-Day", "day-to-day", "DTD", "Questionable", "Game-Time Decision"]
    ok = ["", None, "Probable", "Active", "Available"]
    assert {reports.classify_injury_status(s) for s in out} == {"out"}
    assert {reports.classify_injury_status(s) for s in dtd} == {"dtd"}
    assert {reports.classify_injury_status(s) for s in ok} == {"ok"}


def test_lookup_is_accent_and_suffix_insensitive():
    injuries = {"DAL": {"Luka Dončić": "Out", "Jaime Jaquez Jr.": "Day-To-Day"}, "LAL": {"Other Guy": "Out"}}
    assert reports.injury_status_for(injuries, "DAL", "Luka Doncic") == "Out"
    assert reports.injury_status_for(injuries, "DAL", "Jaime Jaquez Jr") == "Day-To-Day"
    assert reports.injury_status_for(injuries, "DAL", "Luka Dončić") == "Out"
    assert reports.injury_status_for(injuries, "LAL", "Luka Doncic") == ""      # other team's feed never leaks
    assert reports.injury_status_for(injuries, "DAL", "Doncic") == ""           # never surname-only
    assert reports.injury_status_for({}, "DAL", "Luka Doncic") == ""


def _card(name, team="DAL"):
    la = {"odds": 1.5, "line": 20.0, "line_display": "20+", "hit_l10": 0.9, "hit_l10_count": 9,
          "hit_l5": 1.0, "hit_l5_count": 5, "hit_l3": 1.0, "hit_l3_count": 3,
          "implied_prob": 0.66, "estimated_prob": 0.8, "edge": 14, "edge_grade": "A"}
    return {"name": name, "team": team, "category": "points", "cov": 0.2, "avg": 25.0,
            "l10": [25] * 10, "min_avg": 34, "cov_grade": "A", "med": 25, "sd": 3,
            "trend": "flat", "weighted_avg": 25.0, "line_analysis": {"20": la}}


def test_candidates_drop_out_and_doubtful_and_flag_questionable():
    cards = [_card("Luka Doncic"), _card("Doubtful Guy"), _card("Quest Guy"), _card("Healthy Guy")]
    injuries = {"DAL": {"Luka Dončić": "Out For Season", "Doubtful Guy": "Doubtful", "Quest Guy": "Questionable"}}
    names = {c["player"] for c in reports.build_leg_candidates(cards, meta={}, injuries=injuries)}
    assert names == {"Quest Guy", "Healthy Guy"}
