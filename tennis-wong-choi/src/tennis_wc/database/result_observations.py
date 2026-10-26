"""Append-only result states with a real observation clock, not mutable labels."""
from __future__ import annotations


_NOW="strftime('%Y-%m-%dT%H:%M:%fZ','now')"
_FIELDS='result_id,match_id,source_provider,winner_player_id,score_json,raw_response_id,reported_created_at,observed_at,observation_kind,player_a_id,player_b_id'


def ensure_result_observations(conn) -> None:
    conn.execute('''CREATE TABLE IF NOT EXISTS result_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, result_id INTEGER NOT NULL,
        match_id INTEGER NOT NULL, source_provider TEXT NOT NULL, winner_player_id INTEGER,
        score_json TEXT,raw_response_id INTEGER,reported_created_at TEXT,observed_at TEXT NOT NULL,
        observation_kind TEXT NOT NULL,player_a_id INTEGER,player_b_id INTEGER)''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_result_observations_result ON result_observations(result_id,id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_result_observations_cutoff ON result_observations(observed_at,match_id,source_provider,id)')
    # A seed says "known now", never "known at the old row's mutable created_at".
    conn.execute(f'''INSERT INTO result_observations({_FIELDS})
        SELECT r.id,r.match_id,r.source_provider,r.winner_player_id,r.score_json,r.raw_response_id,
               r.created_at,{_NOW},'LEGACY_SEED',m.player_a_id,m.player_b_id
        FROM match_results r JOIN matches m ON m.id=r.match_id
        WHERE NOT EXISTS(SELECT 1 FROM result_observations o WHERE o.result_id=r.id)''')
    for action,ref,kind,condition in (
        ('INSERT','NEW','OBSERVED',''),
        ('UPDATE','NEW','OBSERVED','WHEN NEW.winner_player_id IS NOT OLD.winner_player_id OR NEW.score_json IS NOT OLD.score_json OR NEW.raw_response_id IS NOT OLD.raw_response_id OR NEW.source_provider IS NOT OLD.source_provider'),
        ('DELETE','OLD','DELETED',''),
    ):
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS result_observe_{action.lower()}
            AFTER {action} ON match_results {condition} BEGIN
            INSERT INTO result_observations({_FIELDS})
            SELECT {ref}.id,{ref}.match_id,{ref}.source_provider,{ref}.winner_player_id,
                   {ref}.score_json,{ref}.raw_response_id,{ref}.created_at,{_NOW},'{kind}',m.player_a_id,m.player_b_id
            FROM matches m WHERE m.id={ref}.match_id;
            END''')
    for action in ('UPDATE','DELETE'):
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS result_observations_no_{action.lower()}
            BEFORE {action} ON result_observations BEGIN
            SELECT RAISE(ABORT,'result observations are append-only'); END''')


def results_known_before(conn, cutoff: str) -> list:
    """Latest source state actually observed before cutoff; deletion is a state."""
    return conn.execute('''WITH latest AS (
        SELECT *,ROW_NUMBER() OVER(PARTITION BY match_id,source_provider ORDER BY id DESC) AS rn
        FROM result_observations WHERE julianday(observed_at)<julianday(?)
    ) SELECT result_id AS id,match_id,winner_player_id,score_json,observed_at AS created_at,
             reported_created_at,observation_kind,player_a_id,player_b_id
      FROM latest WHERE rn=1 AND observation_kind!='DELETED' ORDER BY result_id''',(cutoff,)).fetchall()
