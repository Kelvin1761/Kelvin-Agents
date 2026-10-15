"""Odds-only updates must invalidate cache and leave model outputs intact."""
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_static as G
from services.au_market_odds import enrich_au_market_odds
from models.race import Region


def test_morning_prices_reach_cards_with_unchanged_analysis(tmp_path):
    report = tmp_path / "Race_1_Auto_Analysis.md"
    report.write_text("unchanged scored report")
    meeting = SimpleNamespace(region=Region.AU, date="2026-10-16", folder_paths={"Kelvin": str(tmp_path)})
    horse = SimpleNamespace(horse_number=1, ability_score=71.2, rank=2,
                            market_win_odds=None, market_place_odds=None,
                            market_win_prob=0.2)
    race = SimpleNamespace(race_number=1, horses=[horse])
    before = G._source_fingerprint(meeting)
    (tmp_path / "odds_history.json").write_text(json.dumps({"1": {
        "2026-10-15T23:00:00|analysis": {"1": ["5", "2"]},
        "2026-10-16T10:00:00|morning-refresh": {"1": ["3", "1.4"], "99": ["2", "1.2"]},
        "2026-10-17T10:00:00|morning-refresh": {"1": ["2", "1.2"]}}}))
    assert G._source_fingerprint(meeting) != before
    enrich_au_market_odds(meeting, {"Kelvin": [race]}, now=datetime(2026, 10, 16, 11, tzinfo=ZoneInfo("Australia/Sydney")))
    assert (horse.market_win_odds, horse.market_place_odds) == (3, 1.4)
    assert (horse.ability_score, horse.rank, horse.market_win_prob) == (71.2, 2, 0.2)
    assert horse.market_odds_captured_at.startswith("2026-10-16T10:00:00")
    assert len(race.horses) == 1 and report.read_text() == "unchanged scored report"


def test_corrupt_odds_history_does_not_erase_existing_report_prices(tmp_path):
    (tmp_path / "odds_history.json").write_text("[]")
    meeting = SimpleNamespace(region=Region.AU, date="2026-10-16", folder_paths={"Kelvin": str(tmp_path)})
    horse = SimpleNamespace(horse_number=1, market_win_odds=3, market_place_odds=1.5)
    enrich_au_market_odds(meeting, {"Kelvin": [SimpleNamespace(race_number=1, horses=[horse])]})
    assert (horse.market_win_odds, horse.market_place_odds) == (3, 1.5)
