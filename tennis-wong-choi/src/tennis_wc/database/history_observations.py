"""Preserve history generations when source ordinals or source facts change."""
from __future__ import annotations

import hashlib
import json
import re

from tennis_wc.features.history_values import clean_history_row
from tennis_wc.features.round_labels import normalise_round
from tennis_wc.ingestion.raw_response_store import utc_now

PUBLIC = {'jeff_sackmann','tennismylife_history'}
KNOCKOUT = {'F','SF','QF','R16','R32','R64','R128'}
IGNORED = {'id','provider_match_id','raw_response_id','created_at','opponent_elo',
           'history_status','canonical_event_key','source_match_ref','supersedes_history_id'}


def ensure_history_schema(conn):
    columns={r['name'] for r in conn.execute('PRAGMA table_info(player_match_history)')}
    for key,definition in {
        'history_status':"TEXT NOT NULL DEFAULT 'ACTIVE'",'canonical_event_key':'TEXT',
        'source_match_ref':'TEXT','supersedes_history_id':'INTEGER'}.items():
        if key not in columns:
            conn.execute(f'ALTER TABLE player_match_history ADD COLUMN {key} {definition}')
    conn.execute('''CREATE INDEX IF NOT EXISTS idx_history_current_event
        ON player_match_history(source_provider,canonical_event_key,player_id,history_status)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS history_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,history_id INTEGER NOT NULL,
        observation_kind TEXT NOT NULL,observed_at TEXT NOT NULL,
        raw_response_id INTEGER,payload_json TEXT NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_history_observations_row ON history_observations(history_id,id)')
    for action in ('UPDATE','DELETE'):
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS history_observations_no_{action.lower()}
            BEFORE {action} ON history_observations BEGIN
            SELECT RAISE(ABORT,'history observations are append-only'); END''')


def history_active_clause(conn, alias=''):
    columns={r['name'] for r in conn.execute('PRAGMA table_info(player_match_history)')}
    prefix = alias+'.' if alias else ''
    valid_pair = f'{prefix}player_id <> {prefix}opponent_id'
    if 'history_status' not in columns:
        return valid_pair
    return f"{prefix}history_status='ACTIVE' AND {valid_pair}"


def _observe(conn, row, kind, now, raw_id=None):
    conn.execute('''INSERT INTO history_observations
        (history_id,observation_kind,observed_at,raw_response_id,payload_json) VALUES (?,?,?,?,?)''',
        (row['id'],kind,now,raw_id if raw_id is not None else row.get('raw_response_id'),
         json.dumps(dict(row),sort_keys=True,allow_nan=False)))


def upsert_history_observation(conn, data, *, observed_at=None):
    """The caller's transaction owns both perspectives of a source match."""
    ensure_history_schema(conn)
    data=clean_history_row(data)
    if data['player_id']==data['opponent_id']:
        raise ValueError('history cannot list a player against themselves')
    now=observed_at or utc_now()
    stage=normalise_round(data.get('round'))
    strong=data['source_provider'] in PUBLIC and stage in KNOCKOUT and bool(data.get('tournament_external_id'))
    reference=str(data['provider_match_id'])
    base_ref=reference.removesuffix('-winner').removesuffix('-loser')
    pair=sorted((int(data['player_id']),int(data['opponent_id'])))
    tournament = str(data.get('tournament_external_id') or '')
    tournament_year = re.match(r'^(\d{4})-', tournament) if strong else None
    event_year = tournament_year[1] if tournament_year else str(data['match_date'])[:4]
    identity=[data['source_provider'],data['tour'],data.get('tournament_external_id'),
              event_year,stage,pair]
    if not strong:
        identity += [data['match_date'],base_ref]
    event='hc1-'+hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:32]
    key=event+('-winner' if data['won'] else '-loser')
    data['round']=stage if stage!='UNKNOWN' else data.get('round','UNKNOWN')
    columns={r['name'] for r in conn.execute('PRAGMA table_info(player_match_history)')}
    data={k:v for k,v in data.items() if k in columns and k not in {'id','history_status','canonical_event_key','source_match_ref','supersedes_history_id'}}
    prior=conn.execute('''SELECT * FROM player_match_history WHERE source_provider=?
        AND canonical_event_key=? AND player_id=? AND history_status='ACTIVE' ORDER BY id''',
        (data['source_provider'],event,data['player_id'])).fetchall()
    if not prior:
        legacy=conn.execute('''SELECT * FROM player_match_history WHERE source_provider=?
            AND player_id=? AND opponent_id=? AND tour=? AND tournament_external_id=?
            AND history_status='ACTIVE' ORDER BY id''',
            (data['source_provider'],data['player_id'],data['opponent_id'],data['tour'],data['tournament_external_id'])).fetchall()
        prior=[r for r in legacy if (normalise_round(r['round'])==stage and
                 ((strong and str(r['match_date'])[:4]==str(data['match_date'])[:4]) or
                  (not strong and r['match_date']==data['match_date'] and (r['source_match_ref'] or r['provider_match_id'])==reference)))]
    comparable=[k for k in data if k not in IGNORED]
    if len(prior)==1 and prior[0]['canonical_event_key']==event:
        old=dict(prior[0])
        if (old.get('raw_response_id') is not None
                and old.get('raw_response_id') == data.get('raw_response_id')
                and any(old.get(k) != data.get(k) for k in comparable)):
            raise ValueError('conflicting facts for one event in the same history response')
        if all(old.get(k)==data.get(k) for k in comparable):
            if old.get('source_match_ref')!=reference:
                _observe(conn,{**old,'new_source_match_ref':reference},'SOURCE_REFERENCE_CHANGED',now,data.get('raw_response_id'))
                conn.execute('UPDATE player_match_history SET source_match_ref=? WHERE id=?',(reference,old['id']))
            return int(old['id'])
    supersedes=None
    for previous in prior:
        old=dict(previous)
        _observe(conn,old,'SUPERSEDED' if old.get('canonical_event_key') else 'LEGACY_CAPTURE',now)
        conn.execute("UPDATE player_match_history SET history_status='SUPERSEDED',provider_match_id=? WHERE id=?",
                     (f"{old['provider_match_id']}::retired::{old['id']}",old['id']))
        supersedes=supersedes or old['id']
    current={**data,'provider_match_id':key,'created_at':now,'history_status':'ACTIVE',
             'canonical_event_key':event,'source_match_ref':reference,'supersedes_history_id':supersedes}
    keys=list(current)
    cursor=conn.execute(f'INSERT INTO player_match_history({",".join(keys)}) VALUES ({",".join("?" for _ in keys)})',
                        [current[k] for k in keys])
    current['id']=cursor.lastrowid
    _observe(conn,current,'CREATED',now)
    return int(current['id'])
