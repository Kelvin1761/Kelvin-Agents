"""Research replay is explicit; a late backfill cannot become a PIT forecast."""
from __future__ import annotations

import json

import pytest

from tennis_wc.research.wta_history import WtaHistoryOverlay


@pytest.fixture
def db(tmp_path, monkeypatch):
    from conftest import configure_test_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.ingest_wta_stats import ensure_wta_stats_schema

    configure_test_db(tmp_path, monkeypatch)
    init_db()
    conn = get_connection()
    ensure_wta_stats_schema(conn)
    for pid, name in ((1, "Ana Test"), (2, "Béa Test")):
        conn.execute("INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
                     "VALUES (?,?,'WTA','test','now','now')", (pid, name))
        for day in range(1, 6):
            conn.execute(
                "INSERT INTO player_match_history (provider_match_id,player_id,opponent_id,tour,"
                "match_date,tournament_external_id,tournament_level,round,format,won,source_provider,"
                "raw_response_id,created_at,surface,hold_rate,return_points_won_pct,opponent_elo) "
                "VALUES (?,?,?,'WTA',?,'T','WTA_250','R1','BO3',1,'jeff_sackmann',0,"
                "'2026-05-10T00:00:00Z','hard',0.6,0.35,1500)",
                (f"h{pid}-{day}",pid,3-pid,f"2026-05-{day:02d}"),
            )
    for day in range(1, 6):
        match_id = f"M{day}"
        body = {"matches": [{"MatchID": match_id, "MatchTimeStamp": f"2026-06-{day:02d}T10:00:00Z"}]}
        raw_id = conn.execute(
            "INSERT INTO raw_api_responses (provider_name,endpoint,request_url_hash,request_params_json,"
            "response_json,status_code,fetched_at,created_at) "
            "VALUES ('wta_official_stats','test','h','{}',?,200,'2026-10-26T00:00:00Z','now')",
            (json.dumps(body),),
        ).lastrowid
        for side, name, opponent in (("A", "Ana Test", "Bea Test"), ("B", "Bea Test", "Ana Test")):
            conn.execute(
                "INSERT INTO wta_match_stats (tournament_id,year,wta_match_id,side,player_name,"
                "opponent_name,match_date,score,stats_status,source_provider,raw_response_id,fetched_at,"
                "surface,hold_rate,break_rate,return_points_won_pct,service_games_played,ace_count) "
                "VALUES ('T',2026,?,?,?,?,?,'6-4 6-4','OK','wta_official_stats',?,"
                "'2026-10-26T00:00:00Z','hard',0.8,0.2,0.36,10,4)",
                (match_id,side,name,opponent,f"2026-06-{day:02d}",raw_id),
            )
    conn.commit()
    yield conn
    conn.close()


def test_late_official_backfill_needs_explicit_counterfactual_mode(db):
    overlay = WtaHistoryOverlay(db)
    strict = overlay.profile(1, "2026-06-10", window=5)
    replay = overlay.profile(1, "2026-06-10", window=5, allow_historical_backfill=True)
    assert strict.profile.serve["hold_rate"] == pytest.approx(0.6)
    assert strict.captured_before_forecast
    assert replay.profile.serve["hold_rate"] == pytest.approx(0.8)
    assert replay.source_counts == {"wta_official_stats": 5}
    assert not replay.captured_before_forecast


def test_same_day_and_future_results_are_never_profile_inputs(db):
    profile = WtaHistoryOverlay(db).profile(
        1, "2026-06-03", window=5, allow_historical_backfill=True,
    )
    assert sum(key.startswith("wta:") for key in profile.observation_ids) == 2
    assert profile.latest_date == "2026-06-02"


def test_source_update_preserves_surface_fallback_and_reports_age_loss(db):
    overlay = WtaHistoryOverlay(db)
    pooled = overlay.profile(1, "2026-06-10", surface="clay", allow_historical_backfill=True)
    assert pooled.profile.surface is None and pooled.profile.matches == 10
    thin = overlay.profile(1, "2026-06-10", max_age_days=5, allow_historical_backfill=True)
    assert thin.profile.matches == 1 and not thin.profile.is_usable


def test_tournament_start_date_fallback_cannot_supply_replay_history(db):
    db.execute("UPDATE raw_api_responses SET response_json='{}'")
    overlay = WtaHistoryOverlay(db)
    assert overlay.issues["missing_or_inconsistent_actual_match_timestamp"] == 10
    assert overlay.profile(1, "2026-06-10", allow_historical_backfill=True).source_counts == {"jeff_sackmann": 5}


def test_ambiguous_full_name_is_not_fuzzily_assigned(db):
    db.execute("INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
               "VALUES (3,'Ana Test','WTA','test','now','now')")
    overlay = WtaHistoryOverlay(db)
    assert overlay.issues["unresolved_or_ambiguous_player_pair"] == 10
    assert not overlay.official


def test_overlapping_serve_sources_must_be_reconciled_before_merging(db):
    db.execute("UPDATE player_match_history SET match_date='2026-06-01' WHERE id=1")
    with pytest.raises(ValueError, match="overlap"):
        WtaHistoryOverlay(db)


@pytest.mark.parametrize('exposure',[float('inf'),1.5,-1])
def test_impossible_service_game_exposure_is_not_model_input(db,exposure):
    db.execute('UPDATE wta_match_stats SET service_games_played=? WHERE id=1',(exposure,))
    overlay=WtaHistoryOverlay(db)
    assert overlay.issues['invalid_serve_rates_or_exposure']==1
    assert sum(map(len,overlay.official.values()))==8


def test_in_range_rates_with_partial_match_exposure_cannot_enter_profiles(db):
    db.execute("UPDATE wta_match_stats SET service_games_played=1 WHERE wta_match_id='M1'")
    overlay=WtaHistoryOverlay(db)
    assert overlay.issues['inconsistent_service_exposure_with_score']==2
    assert sum(map(len,overlay.official.values()))==8


def test_local_fixture_date_cannot_admit_an_observation_after_its_utc_start(db):
    profile=WtaHistoryOverlay(db).profile(
        1,'2026-06-06',start_time='2026-06-04T00:00:00Z',
        allow_historical_backfill=True)
    assert profile.latest_date=='2026-06-03'
    assert sum(key.startswith('wta:') for key in profile.observation_ids)==3
