import gzip,json
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime
from contextlib import contextmanager
from hashlib import sha256
from tennis_wc.features import feature_builder as fb
from tennis_wc.ingestion.ingest_odds import _sportsbet_in_play

def v(x):
    return x.get('value') if isinstance(x,dict) else x
def pair(a,b):
    return tuple(sorted((' '.join(str(v(x)).casefold().split()) for x in (a,b))))
f=Path.home()/'wongchoi-scheduler/2026-11-05 Tennis Analysis/_prediction_snapshots/20261104T222916.029764+0000-05bfd5e3152f/Tennis_Research_Diagnostics_2026-11-05.json.gz'
assert sha256(f.read_bytes()).hexdigest()=='c52e10f46e2d0be6884b07aedf2f3a4178ea24168cdc062d581e4f0e2839a69d'
data=json.loads(gzip.decompress(f.read_bytes()))
status=defaultdict(list)
for r in data['raw_responses']:
    if r['provider_name']!='sportsbet':continue
    body=json.loads(r['response_json'])
    for row in body if isinstance(body,list) else [body]:
        if isinstance(row,dict) and row.get('player_a_name') and row.get('player_b_name'):
            status[pair(row['player_a_name'],row['player_b_name'])].append((r,row))
@contextmanager
def fake_conn():
    yield None
fb.get_connection=fake_conn
counts=Counter()
identity_before=[]
identity_after=[]
for o in data['observations']:
    s=o['snapshot']
    row={'id':v(s['match_id']),'tournament_name':v(s['match_context']['tournament']),
         'start_time_utc':v(s['match_context']['start_time_utc'])}
    fb._sportsbet_priced_matches=lambda conn,day:[row]
    fb.build_match_feature_snapshot=lambda match_id:s
    fb.utc_now=lambda:o['prediction_created_at']
    skipped=[]
    got=fb.build_sportsbet_feature_snapshots_for_date('2026-11-05',skipped)
    counts['observations']+=1
    counts['accepted']+=len(got)
    for reason in skipped:
        counts[reason['reason']]+=1
    candidates=[(r,row) for r,row in status[pair(s['player_a']['name'],s['player_b']['name'])] if datetime.fromisoformat(r['fetched_at'].replace('Z','+00:00'))<datetime.fromisoformat(o['prediction_created_at'].replace('Z','+00:00'))]
    _,book=min(candidates,key=lambda item:datetime.fromisoformat(item[0]['fetched_at'].replace('Z','+00:00')))
    live=_sportsbet_in_play('sportsbet',book)
    counts['raw_live_rejected']+=live and not got
    assert not (live and got)
    if got:
        identity_before.append(s)
        identity_after.extend(got)
assert counts['accepted']==45 and counts['match_already_started']==12 and counts['raw_live_rejected']==12
left=sha256(json.dumps(identity_before,sort_keys=True).encode()).hexdigest()
right=sha256(json.dumps(identity_after,sort_keys=True).encode()).hexdigest()
assert left==right
print(json.dumps(dict(counts=counts,accepted_snapshot_sha256=left,accepted_payload_parity=True,production_updates=0),indent=2))
