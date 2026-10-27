"""Adversarial checks for the offline diagnostic, with isolated toy databases."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tennis-wong-choi/tests'))
sys.path.insert(0,str(ROOT/'tennis-wong-choi/src'))
from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db

spec=importlib.util.spec_from_file_location('profit_diagnostic',Path(__file__).with_name('tennis-profit-feasibility-20261027.py'))
harness=importlib.util.module_from_spec(spec);spec.loader.exec_module(harness)


def seed(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    c=get_connection()
    c.execute("""INSERT INTO matches(id,provider_match_id,tour,match_date,tournament_id,player_a_id,
        player_b_id,round,source_provider,created_at,updated_at,start_time_utc)
        VALUES (1,'m','ATP','2026-06-01',1,1,2,'QF','sportsbet','now','now','2026-06-01T12:00:00Z')""")
    c.execute("""INSERT INTO odds_snapshots(id,event_id,match_id,bookmaker,market,player_a_odds,
        player_b_odds,source_provider,raw_response_id,fetched_at,created_at)
        VALUES (1,'m',1,'Sportsbet','match_winner',1.5,2.8,'sportsbet',1,'2026-06-01T10:00:00Z','2026-06-01T10:00:00Z')""")
    c.execute("""INSERT INTO predictions(id,match_id,feature_set_version,selection_player_id,
        model_probability,current_market_odds,decision,stake_units,confidence,risk,created_at,pricing_json)
        VALUES (1,1,'test',1,.75,1.5,'BET',1,80,'LOW','2026-06-01T10:01:00Z',?)""",
        (json.dumps({'fixture_at_prediction':{'player_a_id':1,'player_b_id':2,'start_time_utc':'2026-06-01T12:00:00Z'}}),))
    c.execute("""INSERT INTO match_results(match_id,winner_player_id,score_json,source_provider,created_at)
        VALUES (1,1,'{"player_a_sets":2,"player_b_sets":0}','test','2026-06-01T14:00:00Z')""")
    return c


def test_earliest_prematch_forecast_and_agreed_results_are_one_match(tmp_path,monkeypatch):
    c=seed(tmp_path,monkeypatch)
    try:
        c.execute("""INSERT INTO predictions(match_id,feature_set_version,selection_player_id,
            model_probability,current_market_odds,decision,stake_units,confidence,risk,created_at,pricing_json)
            VALUES (1,'test',1,.99,1.5,'BET',1,80,'LOW','2026-06-01T13:00:00Z','{}')""")
        c.execute("INSERT INTO match_results(match_id,winner_player_id,score_json,source_provider,created_at) VALUES (1,1,'{}','other','2026-06-01T15:00:00Z')")
        rows,counts=harness.load_rows(c)
        assert len(rows)==counts['eligible_unique_matches']==1
        assert rows[0]['model']==.75 and rows[0]['prediction_id']==1
        assert rows[0]['execution_timing_compatible'] and rows[0]['fixture_frozen']
    finally:c.close()


def test_conflicting_result_cannot_make_a_profitable_row(tmp_path,monkeypatch):
    c=seed(tmp_path,monkeypatch)
    try:
        c.execute("INSERT INTO match_results(match_id,winner_player_id,score_json,source_provider,created_at) VALUES (1,2,'{}','other','2026-06-01T15:00:00Z')")
        assert harness.load_rows(c)[0]==[]
    finally:c.close()


def test_disputed_fixture_is_not_evidence(tmp_path,monkeypatch):
    c=seed(tmp_path,monkeypatch)
    try:
        c.execute("UPDATE matches SET fixture_status='DISPUTED'")
        rows,counts=harness.load_rows(c)
        assert rows==[] and counts['disputed_fixture']==1
    finally:c.close()


def test_first_quote_ingested_post_start_has_no_later_fallback(tmp_path,monkeypatch):
    c=seed(tmp_path,monkeypatch)
    try:
        c.execute("UPDATE odds_snapshots SET created_at='2026-06-01T13:00:00Z'")
        c.execute("""INSERT INTO odds_snapshots(event_id,match_id,bookmaker,market,player_a_odds,
            player_b_odds,source_provider,raw_response_id,fetched_at,created_at)
            VALUES ('m',1,'Sportsbet','match_winner',1.4,3,'sportsbet',2,'2026-06-01T11:00:00Z','2026-06-01T11:00:00Z')""")
        rows,counts=harness.load_rows(c)
        assert rows==[] and counts['opening_ingested_after_start_or_unverifiable']==1
    finally:c.close()


def test_future_opening_is_not_execution_compatible_and_needs_later_quote(tmp_path,monkeypatch):
    c=seed(tmp_path,monkeypatch)
    try:
        c.execute("UPDATE odds_snapshots SET created_at='2026-06-01T10:02:00Z'")
        row=harness.load_rows(c)[0][0]
        assert not row['execution_timing_compatible']
        assert row['later_quote_id']==1  # observed after prediction, not proof it was available earlier
        assert row['same_book_movement']==0
    finally:c.close()


def test_zero_candidate_exposure_does_not_manufacture_positive_roi():
    row={'odds':2.,'won':1,'decision':'BET','execution_timing_compatible':True,'fixture_frozen':True,'later_quote_id':None}
    report=harness.policies([row])
    assert report['BET_and_short_candidate']['bets']==0
    assert report['BET_and_short_candidate']['roi']['mean'] is None
    assert report['paired_pnl_delta_per_eligible_match']['mean']==-1
