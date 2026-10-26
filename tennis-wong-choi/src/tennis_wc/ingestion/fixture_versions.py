"""Keep fixture pairing and positional history stable when providers reuse keys."""
from __future__ import annotations

import json


def ensure_fixture_schema(conn) -> None:
    columns={r['name'] for r in conn.execute('PRAGMA table_info(matches)')}
    if 'fixture_status' not in columns:
        conn.execute("ALTER TABLE matches ADD COLUMN fixture_status TEXT NOT NULL DEFAULT 'ACTIVE'")
    if 'supersedes_match_id' not in columns:
        conn.execute('ALTER TABLE matches ADD COLUMN supersedes_match_id INTEGER')
    conn.execute('''CREATE TABLE IF NOT EXISTS fixture_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER NOT NULL,
        source_provider TEXT NOT NULL, provider_match_id TEXT NOT NULL,
        observation_kind TEXT NOT NULL, fixture_json TEXT NOT NULL,
        raw_response_id INTEGER, observed_at TEXT NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_fixture_observations_match ON fixture_observations(match_id,id)')


def _observe(conn, match_id: int, data: dict, kind: str, now: str) -> None:
    data=dict(data)
    for side in ('a','b'):
        player=conn.execute('SELECT name FROM players WHERE id=?',(data.get(f'player_{side}_id'),)).fetchone()
        if player:
            data[f'player_{side}_name']=player['name']
    conn.execute('''INSERT INTO fixture_observations
        (match_id,source_provider,provider_match_id,observation_kind,fixture_json,raw_response_id,observed_at)
        VALUES (?,?,?,?,?,?,?)''',
        (match_id,data['source_provider'],data['provider_match_id'],kind,
         json.dumps(data,sort_keys=True),data.get('raw_response_id'),now))


def upsert_fixture(conn, data: dict, now: str) -> int:
    """Refresh metadata; a different pairing gets a fresh match and child history.

    Source order is not identity: reversing the same pair must never flip the
    meaning of old a/b probabilities, scores or odds. Completed fixtures on a
    different date are different events, even if the same players meet again.
    """
    from datetime import date

    data={**data,'provider_match_id':str(data.get('provider_match_id') or '').strip()}
    if data['provider_match_id'].lower() in {'','none','null','unknown','tbd'}:
        raise ValueError('missing provider fixture identity')
    if data['player_a_id']==data['player_b_id']:
        raise ValueError('self fixture identity')
    date.fromisoformat(data['match_date'])
    ensure_fixture_schema(conn)
    old=conn.execute('SELECT * FROM matches WHERE source_provider=? AND provider_match_id=?',
                     (data['source_provider'],str(data['provider_match_id']))).fetchone()
    old=dict(old) if old else None
    supersedes=None
    if old:
        from tennis_wc.identity.player_identity import terminal_canonical_id
        prior={terminal_canonical_id(conn,old[k]) for k in ('player_a_id','player_b_id')}
        incoming={terminal_canonical_id(conn,data[k]) for k in ('player_a_id','player_b_id')}
        resulted=conn.execute('SELECT 1 FROM match_results WHERE match_id=? LIMIT 1',(old['id'],)).fetchone()
        new_event=(prior!=incoming or (resulted and (
            old['match_date']!=data['match_date'] or old['tournament_id']!=data['tournament_id'])))
        if new_event:
            supersedes=int(old['id'])
            _observe(conn,supersedes,old,'SUPERSEDED',now)
            conn.execute("UPDATE matches SET provider_match_id=?,market_event_id=NULL,fixture_status='SUPERSEDED' WHERE id=?",
                         (f"{old['provider_match_id']}::retired::{supersedes}",supersedes))
            old=None
    if old:
        conn.execute('''UPDATE matches SET market_event_id=COALESCE(?,market_event_id),
            match_date=?,tournament_id=?,tour=?,round=CASE WHEN ? IN ('UNKNOWN','') THEN round ELSE ? END,
            raw_response_id=?,updated_at=?,start_time_utc=COALESCE(?,start_time_utc),
            fixture_status=CASE WHEN fixture_status='NOT_LISTED' THEN 'ACTIVE' ELSE fixture_status END WHERE id=?''',
            (data.get('market_event_id'),data['match_date'],data['tournament_id'],data['tour'],
             data['round'],data['round'],data.get('raw_response_id'),now,data.get('start_time_utc'),old['id']))
        match_id=int(old['id'])
    else:
        keys=('provider_match_id','market_event_id','tour','match_date','tournament_id',
              'player_a_id','player_b_id','round','source_provider','raw_response_id','start_time_utc')
        cursor=conn.execute(f'''INSERT INTO matches ({','.join(keys)},created_at,updated_at,supersedes_match_id)
            VALUES ({','.join('?' for _ in keys)},?,?,?)''',
            tuple(data.get(k) for k in keys)+(now,now,supersedes))
        match_id=int(cursor.lastrowid)
    _observe(conn,match_id,data,'REFRESH' if old else 'CREATED',now)
    return match_id


def active_fixture_clause(conn, alias: str = "m") -> str:
    columns={r['name'] for r in conn.execute('PRAGMA table_info(matches)')}
    return f"{alias}.fixture_status='ACTIVE'" if 'fixture_status' in columns else '1=1'


def quarantine_fixture(conn, match_id: int, incoming: dict, now: str, *, reason: str = 'EVENT_PAIR_CONFLICT') -> None:
    old=dict(conn.execute('SELECT * FROM matches WHERE id=?',(match_id,)).fetchone())
    _observe(conn,match_id,{**old,'incoming_odds_pair':incoming},reason,now)
    conn.execute("UPDATE matches SET fixture_status='DISPUTED' WHERE id=?",(match_id,))
