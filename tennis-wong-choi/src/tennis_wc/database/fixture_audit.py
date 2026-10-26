"""Find legacy provider-key changes from surviving immutable raw fixture rows.

No fuzzy joins or guessed restores. A changed feed pair plus pre-change saved
artifacts proves that a single mutable match row could mix identities.
"""
from __future__ import annotations

import json


def audit_fixture_versions(conn) -> dict:
    fixtures={}
    for row in conn.execute('SELECT * FROM matches'):
        match=dict(row)
        if '::retired::' not in str(match['provider_match_id']):
            fixtures[(match['source_provider'],str(match['provider_match_id']))]=match
    seen={}
    scanned=0
    for raw in conn.execute("SELECT id,provider_name,fetched_at,response_json FROM raw_api_responses WHERE entity_type='match' ORDER BY id"):
        try:
            rows=json.loads(raw['response_json'])
        except (TypeError,ValueError):
            continue
        if not isinstance(rows,list):
            continue
        for row in rows:
            if not isinstance(row,dict):
                continue
            key=(raw['provider_name'],str(row.get('id')))
            if key not in fixtures or not row.get('player_a_id') or not row.get('player_b_id'):
                continue
            scanned+=1
            signature=(str(row['player_a_id']),str(row['player_b_id']))
            observation={'raw_id':raw['id'],'fetched_at':raw['fetched_at'],'pair':signature,
                         'names':[row.get('player_a_name'),row.get('player_b_name')]}
            previous=seen.get(key)
            if previous is None:
                seen[key]={'first':observation,'last':observation,'last_change':None,'change_kind':None}
            else:
                if signature!=tuple(previous['last']['pair']):
                    previous['last_change']=observation
                    previous['change_kind']='PAIR_CHANGED' if set(signature)!=set(previous['last']['pair']) else 'SIDE_ORDER_CHANGED'
                previous['last']=observation
    cases=[]
    has_observations=conn.execute("SELECT 1 FROM sqlite_master WHERE name='fixture_observations' AND type='table'").fetchone()
    artifact_times=dict(conn.execute('''SELECT match_id,MIN(julianday(stamp)) FROM (
        SELECT match_id,created_at AS stamp FROM predictions
        UNION ALL SELECT match_id,fetched_at FROM odds_snapshots
        UNION ALL SELECT match_id,created_at FROM match_results
        UNION ALL SELECT match_id,recorded_at FROM prop_tracker) GROUP BY match_id'''))
    for key,trace in seen.items():
        if trace['last_change'] is None:
            continue
        match=fixtures[key]
        if match.get('raw_response_id') is None or int(match['raw_response_id'])<trace['last_change']['raw_id']:
            continue  # a fetched but rejected change is not an applied identity mutation
        if has_observations and conn.execute("SELECT 1 FROM fixture_observations WHERE match_id=? AND observation_kind='CREATED' LIMIT 1",(match['id'],)).fetchone():
            continue  # generation was created under the immutable-pair writer
        first_artifact=artifact_times.get(match['id'])
        change_jd=conn.execute('SELECT julianday(?)',(trace['last_change']['fetched_at'],)).fetchone()[0]
        if first_artifact is None or change_jd is None or first_artifact>=change_jd:
            continue
        cases.append({'match_id':match['id'],'kind':trace['change_kind'],'current':match,'trace':trace})
    return {'raw_fixture_rows_checked':scanned,'keys_with_surviving_raw':len(seen),
            'legacy_identity_cases':len(cases),'cases':cases,
            'limitation':'Only surviving raw bodies and artifacts; no finding is not proof of a clean legacy identity chain.'}


def quarantine_plan(conn, report: dict, now: str) -> int:
    from tennis_wc.ingestion.fixture_versions import ensure_fixture_schema,_observe
    ensure_fixture_schema(conn)
    changed=0
    for case in report['cases']:
        expected=case['current']
        current=conn.execute('SELECT * FROM matches WHERE id=?',(case['match_id'],)).fetchone()
        if not current or any(current[k]!=expected[k] for k in
                              ('provider_match_id','player_a_id','player_b_id','match_date','updated_at')):
            raise ValueError(f"stale identity audit plan for match {case['match_id']}")
        if current['fixture_status']=='DISPUTED':
            continue
        _observe(conn,case['match_id'],{**dict(current),'identity_audit':case['trace']},'LEGACY_IDENTITY_QUARANTINE',now)
        conn.execute("UPDATE matches SET fixture_status='DISPUTED' WHERE id=?",(case['match_id'],))
        changed+=1
    return changed
