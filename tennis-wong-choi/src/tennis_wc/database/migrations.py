from __future__ import annotations

from tennis_wc.database.db import get_connection


SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_api_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    request_url_hash TEXT NOT NULL,
    request_params_json TEXT NOT NULL,
    response_json TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    entity_type TEXT,
    entity_external_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    provider_entity_id TEXT NOT NULL,
    internal_entity_id INTEGER NOT NULL,
    entity_name TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider_name, entity_type, provider_entity_id)
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    tour TEXT NOT NULL,
    current_rank INTEGER,
    overall_elo REAL,
    surface_elo_json TEXT,
    source_provider TEXT NOT NULL,
    raw_response_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    tour TEXT NOT NULL,
    external_id TEXT NOT NULL,
    source_provider TEXT NOT NULL,
    raw_response_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_provider, external_id)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_match_id TEXT NOT NULL,
    market_event_id TEXT,
    tour TEXT NOT NULL,
    match_date TEXT NOT NULL,
    tournament_id INTEGER NOT NULL,
    player_a_id INTEGER NOT NULL,
    player_b_id INTEGER NOT NULL,
    round TEXT NOT NULL,
    source_provider TEXT NOT NULL,
    raw_response_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_provider, provider_match_id)
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    match_id INTEGER,
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    player_a_odds REAL NOT NULL,
    player_b_odds REAL NOT NULL,
    player_a_open_odds REAL,
    player_b_open_odds REAL,
    source_provider TEXT NOT NULL,
    raw_response_id INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    match_id INTEGER,
    bookmaker TEXT NOT NULL,
    market_key TEXT NOT NULL,
    market_name TEXT NOT NULL,
    selection_name TEXT NOT NULL,
    selection_side TEXT,
    line REAL,
    odds REAL NOT NULL,
    source_provider TEXT NOT NULL,
    raw_response_id INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_match_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_match_id TEXT NOT NULL,
    player_id INTEGER NOT NULL,
    opponent_id INTEGER NOT NULL,
    tour TEXT NOT NULL,
    match_date TEXT NOT NULL,
    surface TEXT,
    tournament_external_id TEXT NOT NULL,
    tournament_level TEXT NOT NULL,
    round TEXT NOT NULL,
    format TEXT NOT NULL,
    won INTEGER NOT NULL,
    opponent_elo REAL,
    hold_rate REAL,
    break_rate REAL,
    ace_count REAL,
    double_fault_count REAL,
    break_points_saved REAL,
    break_points_faced REAL,
    break_points_converted REAL,
    break_points_chances REAL,
    first_serve_points_won_pct REAL,
    second_serve_points_won_pct REAL,
    return_points_won_pct REAL,
    tiebreak_won INTEGER,
    deciding_set_won INTEGER,
    lost_first_set INTEGER,
    comeback_after_losing_first_set INTEGER,
    source_provider TEXT NOT NULL,
    raw_response_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_provider, provider_match_id, player_id)
);

CREATE TABLE IF NOT EXISTS rankings_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    ranking_date TEXT NOT NULL,
    tour TEXT NOT NULL,
    rank INTEGER NOT NULL,
    ranking_points INTEGER,
    source_provider TEXT NOT NULL,
    raw_response_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(player_id, ranking_date, tour, source_provider)
);

CREATE INDEX IF NOT EXISTS idx_player_match_history_player_date
ON player_match_history(player_id, match_date);

CREATE INDEX IF NOT EXISTS idx_player_match_history_player_surface_date
ON player_match_history(player_id, surface, match_date);

CREATE INDEX IF NOT EXISTS idx_player_match_history_player_level_surface_date
ON player_match_history(player_id, tournament_level, surface, match_date);

CREATE INDEX IF NOT EXISTS idx_player_match_history_player_round_level_surface_date
ON player_match_history(player_id, round, tournament_level, surface, match_date);

CREATE INDEX IF NOT EXISTS idx_player_match_history_player_format_surface_date
ON player_match_history(player_id, format, surface, match_date);

CREATE INDEX IF NOT EXISTS idx_player_match_history_pair_date
ON player_match_history(player_id, opponent_id, match_date);

CREATE INDEX IF NOT EXISTS idx_rankings_history_player_date
ON rankings_history(player_id, ranking_date);

CREATE INDEX IF NOT EXISTS idx_market_odds_snapshots_match_market_selection
ON market_odds_snapshots(match_id, market_key, selection_name, line, id);

CREATE TABLE IF NOT EXISTS tournament_levels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    tour TEXT NOT NULL,
    level TEXT NOT NULL,
    surface TEXT,
    indoor_outdoor TEXT,
    source_provider TEXT NOT NULL,
    raw_response_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tournament_id, tour, source_provider)
);

CREATE TABLE IF NOT EXISTS player_opponent_rank_bucket_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    tour TEXT NOT NULL,
    surface TEXT,
    bucket TEXT NOT NULL,
    time_window TEXT NOT NULL,
    matches INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    win_rate REAL,
    shrinked_win_rate REAL,
    avg_opponent_rank REAL,
    median_opponent_rank REAL,
    avg_opponent_elo REAL,
    source_match_count INTEGER NOT NULL,
    calculated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(player_id, tour, surface, bucket, time_window)
);

CREATE TABLE IF NOT EXISTS player_tournament_level_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    tour TEXT NOT NULL,
    surface TEXT,
    tournament_level TEXT NOT NULL,
    time_window TEXT NOT NULL,
    matches INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    win_rate REAL,
    shrinked_win_rate REAL,
    hold_rate REAL,
    break_rate REAL,
    first_serve_points_won_pct REAL,
    second_serve_points_won_pct REAL,
    return_points_won_pct REAL,
    tiebreak_win_rate REAL,
    deciding_set_win_rate REAL,
    avg_opponent_rank REAL,
    avg_opponent_elo REAL,
    calculated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(player_id, tour, surface, tournament_level, time_window)
);

CREATE TABLE IF NOT EXISTS player_round_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    tour TEXT NOT NULL,
    surface TEXT,
    round TEXT NOT NULL,
    tournament_level TEXT,
    time_window TEXT NOT NULL,
    matches INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    win_rate REAL,
    shrinked_win_rate REAL,
    avg_opponent_rank REAL,
    avg_opponent_elo REAL,
    tiebreak_win_rate REAL,
    deciding_set_win_rate REAL,
    calculated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(player_id, tour, surface, round, tournament_level, time_window)
);

CREATE TABLE IF NOT EXISTS player_big_match_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    tour TEXT NOT NULL,
    surface TEXT,
    time_window TEXT NOT NULL,
    matches INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    win_rate REAL,
    avg_opponent_rank REAL,
    avg_opponent_elo REAL,
    deciding_set_win_rate REAL,
    tiebreak_win_rate REAL,
    calculated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(player_id, tour, surface, time_window)
);

CREATE TABLE IF NOT EXISTS player_bo_format_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    tour TEXT NOT NULL,
    surface TEXT,
    format TEXT NOT NULL,
    time_window TEXT NOT NULL,
    matches INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    win_rate REAL,
    vs_top_50_matches INTEGER NOT NULL,
    vs_top_50_wins INTEGER NOT NULL,
    vs_top_50_win_rate REAL,
    deciding_set_matches INTEGER NOT NULL,
    deciding_set_wins INTEGER NOT NULL,
    deciding_set_win_rate REAL,
    comeback_after_losing_first_set_matches INTEGER NOT NULL,
    comeback_after_losing_first_set_wins INTEGER NOT NULL,
    comeback_after_losing_first_set_rate REAL,
    calculated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(player_id, tour, surface, format, time_window)
);

CREATE TABLE IF NOT EXISTS feature_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    feature_set_version TEXT NOT NULL,
    features_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    data_quality_score INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    feature_set_version TEXT NOT NULL,
    selection_player_id INTEGER,
    selection_name TEXT,
    model_probability REAL,
    fair_odds REAL,
    current_market_odds REAL,
    market_implied_probability REAL,
    no_vig_market_probability REAL,
    edge REAL,
    minimum_acceptable_odds REAL,
    decision TEXT NOT NULL,
    stake_units REAL NOT NULL,
    confidence INTEGER NOT NULL,
    risk TEXT NOT NULL,
    pricing_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    market_odds_snapshot_id INTEGER,
    market_key TEXT NOT NULL,
    market_name TEXT NOT NULL,
    selection_name TEXT NOT NULL,
    selection_side TEXT,
    line REAL,
    odds REAL NOT NULL,
    model_status TEXT NOT NULL,
    model_probability REAL,
    no_vig_market_probability REAL,
    edge REAL,
    minimum_acceptable_odds REAL,
    decision TEXT NOT NULL,
    banker_eligible INTEGER NOT NULL,
    confidence INTEGER NOT NULL,
    risk TEXT NOT NULL,
    reason TEXT,
    pricing_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS closing_odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    event_id TEXT,
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    player_a_closing_odds REAL,
    player_b_closing_odds REAL,
    source_provider TEXT NOT NULL,
    raw_response_id INTEGER,
    fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    winner_player_id INTEGER NOT NULL,
    score_json TEXT,
    source_provider TEXT NOT NULL,
    raw_response_id INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(match_id, source_provider)
);

CREATE TABLE IF NOT EXISTS bet_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INTEGER NOT NULL,
    match_id INTEGER NOT NULL,
    selection_player_id INTEGER,
    selection_name TEXT NOT NULL,
    market_key TEXT,
    market_name TEXT,
    tier TEXT,
    model_probability REAL,
    edge REAL,
    confidence INTEGER,
    odds_taken REAL NOT NULL,
    stake_units REAL NOT NULL,
    status TEXT NOT NULL,
    closing_odds REAL,
    clv REAL,
    profit_loss_units REAL,
    recorded_at TEXT NOT NULL,
    settled_at TEXT
);

CREATE TABLE IF NOT EXISTS clv_tracker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    match_id INTEGER NOT NULL,
    match_date TEXT NOT NULL,
    selection_name TEXT NOT NULL,
    selection_side TEXT,
    market_key TEXT NOT NULL,
    market_name TEXT NOT NULL,
    market_line REAL,
    tier TEXT NOT NULL,
    model_probability REAL,
    edge REAL,
    confidence INTEGER,
    odds_taken REAL NOT NULL,
    closing_odds REAL,
    clv REAL,
    result_status TEXT NOT NULL,
    profit_loss_units REAL,
    recorded_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(recommendation_type, source_id)
);

CREATE TABLE IF NOT EXISTS combo_tracker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    combo_key TEXT NOT NULL,
    match_id INTEGER NOT NULL,
    match_date TEXT NOT NULL,
    match_label TEXT NOT NULL,
    tier TEXT NOT NULL,
    legs_json TEXT NOT NULL,
    combo_odds REAL NOT NULL,
    adjusted_confidence INTEGER,
    adjusted_edge REAL,
    stake_units REAL NOT NULL,
    result_status TEXT NOT NULL,
    profit_loss_units REAL,
    recorded_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    settled_at TEXT,
    UNIQUE(combo_key)
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prop_tracker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prop_key TEXT NOT NULL,
    match_id INTEGER NOT NULL,
    match_date TEXT NOT NULL,
    match_label TEXT NOT NULL,
    market_key TEXT NOT NULL,
    line REAL NOT NULL,
    selection TEXT NOT NULL,
    decimal_odds REAL NOT NULL,
    model_prob REAL,
    market_prob_fair REAL,
    blended_prob REAL,
    edge REAL,
    ev REAL,
    predicted_mean REAL,
    stake_units REAL NOT NULL,
    is_value INTEGER NOT NULL DEFAULT 0,
    result_status TEXT NOT NULL DEFAULT 'PENDING',
    actual_value REAL,
    profit_loss_units REAL,
    recorded_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    settled_at TEXT,
    UNIQUE(prop_key)
);
"""


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_compat_columns(conn)


def _ensure_compat_columns(conn) -> None:
    history_columns = {row["name"] for row in conn.execute("PRAGMA table_info(player_match_history)").fetchall()}
    for name, ddl in {
        "ace_count": "ALTER TABLE player_match_history ADD COLUMN ace_count REAL",
        "double_fault_count": "ALTER TABLE player_match_history ADD COLUMN double_fault_count REAL",
        "break_points_saved": "ALTER TABLE player_match_history ADD COLUMN break_points_saved REAL",
        "break_points_faced": "ALTER TABLE player_match_history ADD COLUMN break_points_faced REAL",
        "break_points_converted": "ALTER TABLE player_match_history ADD COLUMN break_points_converted REAL",
        "break_points_chances": "ALTER TABLE player_match_history ADD COLUMN break_points_chances REAL",
    }.items():
        if name not in history_columns:
            conn.execute(ddl)
    result_columns = {row["name"] for row in conn.execute("PRAGMA table_info(match_results)").fetchall()}
    if "score_json" not in result_columns:
        conn.execute("ALTER TABLE match_results ADD COLUMN score_json TEXT")
