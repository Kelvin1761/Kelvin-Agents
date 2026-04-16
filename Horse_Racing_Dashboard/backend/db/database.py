"""
SQLite database for bet records and results.
"""
import sqlite3
from pathlib import Path
import config


def get_db():
    """Get a database connection."""
    db_path = config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize database schema."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date TEXT NOT NULL,
            venue TEXT NOT NULL,
            region TEXT NOT NULL DEFAULT 'hkjc',
            race_number INTEGER NOT NULL,
            horse_number INTEGER NOT NULL,
            horse_name TEXT NOT NULL,
            jockey TEXT,
            trainer TEXT,
            bet_type TEXT NOT NULL DEFAULT 'place',
            stake REAL NOT NULL DEFAULT 1,
            odds REAL,
            consensus_type TEXT,
            kelvin_grade TEXT,
            heison_grade TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            result_position INTEGER,
            payout REAL,
            net_profit REAL,
            notes TEXT,
            track_type TEXT,
            going TEXT
        );

        CREATE TABLE IF NOT EXISTS roi_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            region TEXT NOT NULL,
            total_bets INTEGER,
            total_stake REAL,
            total_payout REAL,
            total_profit REAL,
            win_rate REAL,
            roi_pct REAL
        );

        CREATE INDEX IF NOT EXISTS idx_bets_date ON bets(date);
        CREATE INDEX IF NOT EXISTS idx_bets_region ON bets(region);
        CREATE INDEX IF NOT EXISTS idx_bets_status ON bets(status);
    """)
    conn.commit()
    conn.close()


# Auto-init on import
init_db()
