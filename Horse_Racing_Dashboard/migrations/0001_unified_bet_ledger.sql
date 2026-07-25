PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    sport TEXT NOT NULL CHECK (sport IN ('horses', 'nba', 'tennis')),
    generated_at TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    source_files_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    analysis_run_id TEXT NOT NULL,
    sport TEXT NOT NULL CHECK (sport IN ('horses', 'nba', 'tennis')),
    event_date TEXT NOT NULL,
    event_name TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    odds REAL,
    bet_type TEXT NOT NULL DEFAULT 'single',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (analysis_run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bets (
    id TEXT PRIMARY KEY,
    sport TEXT NOT NULL CHECK (sport IN ('horses', 'nba', 'tennis')),
    source_id TEXT,
    event_date TEXT NOT NULL,
    event_name TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    bet_type TEXT NOT NULL DEFAULT 'single',
    odds REAL NOT NULL CHECK (odds >= 0),
    settlement_odds REAL,
    stake REAL NOT NULL CHECK (stake > 0),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'won', 'lost', 'void')),
    payout REAL NOT NULL DEFAULT 0,
    profit REAL NOT NULL DEFAULT 0,
    bookmaker TEXT,
    note TEXT,
    analysis_snapshot TEXT NOT NULL DEFAULT '{}',
    settlement_source TEXT,
    settlement_ref TEXT,
    settlement_reason TEXT,
    idempotency_key TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    settled_at INTEGER,
    deleted_at INTEGER
);

CREATE TABLE IF NOT EXISTS bet_legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id TEXT NOT NULL,
    leg_index INTEGER NOT NULL,
    event_name TEXT,
    market TEXT,
    selection TEXT NOT NULL,
    line REAL,
    odds REAL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'won', 'lost', 'void')),
    result_value REAL,
    settlement_source TEXT,
    settlement_ref TEXT,
    settled_at INTEGER,
    UNIQUE (bet_id, leg_index),
    FOREIGN KEY (bet_id) REFERENCES bets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settlements (
    id TEXT PRIMARY KEY,
    bet_id TEXT NOT NULL,
    previous_status TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'won', 'lost', 'void')),
    payout REAL NOT NULL,
    profit REAL NOT NULL,
    effective_odds REAL,
    source TEXT NOT NULL,
    source_ref TEXT,
    reason TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL,
    FOREIGN KEY (bet_id) REFERENCES bets(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    actor TEXT NOT NULL DEFAULT 'dashboard',
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS migration_state (
    migration_key TEXT PRIMARY KEY,
    source_count INTEGER NOT NULL,
    imported_count INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    completed_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bets_sport_event_date
    ON bets (sport, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_bets_status_updated
    ON bets (status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_bets_source_id
    ON bets (source_id);
CREATE INDEX IF NOT EXISTS idx_bet_legs_bet
    ON bet_legs (bet_id, leg_index);
CREATE INDEX IF NOT EXISTS idx_settlements_bet_created
    ON settlements (bet_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entity_created
    ON audit_log (entity_type, entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recommendations_run
    ON recommendations (analysis_run_id, sport);
