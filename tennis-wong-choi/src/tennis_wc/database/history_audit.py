"""Find proven legacy header/source mismatches without guessing old statistics."""
from __future__ import annotations

from collections import Counter
import json
import re

from tennis_wc.database.history_observations import ensure_history_schema, _observe
from tennis_wc.features.round_labels import normalise_round
from tennis_wc.ingestion.name_matching import normalise_player_name

_REFERENCE = re.compile(r'^(ATP|WTA)-(.+)-([^-]+)-(winner|loser)$')
def history_state(row):
    values=dict(row)
    for key, default in {'history_status':'ACTIVE','canonical_event_key':None,
                         'source_match_ref':None,'supersedes_history_id':None}.items():
        values.setdefault(key,default)
    return values


def audit_legacy_history(conn):
    players={r['id']:dict(r) for r in conn.execute('SELECT * FROM players')}
    terminal_cache={}
    def terminal(pid):
        if pid in terminal_cache:return terminal_cache[pid]
        current,seen=pid,set()
        while current in players and current not in seen:
            seen.add(current);parent=players[current].get('canonical_player_id')
            if parent is None:break
            current=parent
        terminal_cache[pid]=current
        return current
    mapping={(r['provider_name'],str(r['provider_entity_id'])):terminal(r['internal_entity_id'])
             for r in conn.execute("SELECT * FROM provider_entities WHERE entity_type='player'")}
    columns={r['name'] for r in conn.execute('PRAGMA table_info(player_match_history)')}
    extra=" AND h.history_status='ACTIVE'" if 'history_status' in columns else ''
    if 'canonical_event_key' in columns:extra+=" AND h.canonical_event_key IS NULL"
    rows=conn.execute(f'''SELECT h.* FROM player_match_history h
        WHERE h.source_provider IN ('jeff_sackmann','tennismylife_history') {extra}
        ORDER BY h.raw_response_id,h.id''')
    counts=Counter();cases=[];raw_id=object();index={}
    for history in rows:
        h=dict(history);counts['legacy_rows']+=1
        ref=_REFERENCE.match(h['provider_match_id'])
        if not ref:
            counts['unknown_reference']+=1;continue
        if h['raw_response_id']!=raw_id:
            raw_id=h['raw_response_id'];index={}
            raw=conn.execute('SELECT provider_name,response_json FROM raw_api_responses WHERE id=?',(raw_id,)).fetchone()
            if raw and raw['provider_name']==h['source_provider']:
                try:payload=json.loads(raw['response_json'])
                except (ValueError,TypeError):payload=None
                if isinstance(payload,list):
                    for item in payload:
                        if isinstance(item,dict):
                            key=(str(item.get('tourney_id')),str(item.get('match_num')))
                            index.setdefault(key,[]).append(item)
        candidates=index.get((ref[2],ref[3]),[])
        if len(candidates)!=1:
            counts['unknown_raw_match']+=1;continue
        source=candidates[0];side,other=('winner','loser') if ref[4]=='winner' else ('loser','winner')
        own=mapping.get((h['source_provider'],str(source.get(side+'_id'))))
        opponent=mapping.get((h['source_provider'],str(source.get(other+'_id'))))
        def verified(pid,name):
            return (pid in players and normalise_player_name(name or '')
                    and normalise_player_name(players[pid]['name'])==normalise_player_name(name or ''))
        if own!=terminal(h['player_id']) or not verified(own,source.get(side+'_name')) or not verified(opponent,source.get(other+'_name')):
            counts['unknown_player_mapping']+=1;continue
        issues=[]
        actual_opponent=terminal(h['opponent_id'])
        if opponent!=actual_opponent and normalise_player_name(players.get(actual_opponent,{}).get('name',''))!=normalise_player_name(source.get(other+'_name','')):
            issues.append('source_opponent_differs_from_stored_header')
        raw_day=str(source.get('tourney_date') or '').replace('-','')[:8]
        known_day = len(raw_day)==8 and raw_day.isdigit()
        known_round = normalise_round(source.get('round')) != 'UNKNOWN'
        if known_day and h['match_date'].replace('-','')[:8]!=raw_day:
            issues.append('source_date_differs_from_stored_header')
        if normalise_round(h['round'])!=normalise_round(source.get('round')):
            issues.append('source_round_differs_from_stored_header')
        if issues:
            counts['proven_mismatches']+=1
            cases.append({'state':history_state(h),'issues':issues,'raw_response_id':raw_id,
                          'source_player_id':own,'source_opponent_id':opponent,
                          'source_player_name':source.get(side+'_name'),
                          'source_opponent_name':source.get(other+'_name'),
                          'source_match_num':source.get('match_num'),'source_round':source.get('round'),
                          'source_tourney_date':source.get('tourney_date')})
        elif known_day and known_round:
            counts['header_matches_saved_source']+=1
        else:
            counts['unknown_source_date_or_round']+=1
    return {'policy':'legacy-history-header-v1','counts':dict(counts),'cases':cases,
            'limitations':['Unknown/missing raw rows or player mappings are not declared safe or quarantined.',
                           'No old statistics are restored and no graded forecast is rewritten.']}


def quarantine_history_plan(conn,report,now):
    ensure_history_schema(conn)
    planned=[]
    for case in report['cases']:
        row=conn.execute('SELECT * FROM player_match_history WHERE id=?',(case['state']['id'],)).fetchone()
        if row is None or history_state(row)!=case['state']:
            raise ValueError('history audit plan is stale')
        planned.append((dict(row),case))
    for row,case in planned:
        _observe(conn,{**row,'integrity_case':case},'LEGACY_SOURCE_CONTEXT_HOLD',now)
        conn.execute("UPDATE player_match_history SET history_status='DISPUTED' WHERE id=?",(row['id'],))
    return len(planned)
