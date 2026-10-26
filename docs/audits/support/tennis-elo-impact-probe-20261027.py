"""Run the unchanged production Elo builder on an isolated history projection."""
import argparse, json, os, shutil, sqlite3, hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--arm',required=True);p.add_argument('--output',required=True);p.add_argument('--quarantine');p.add_argument('--allow-self-history',action='store_true');a=p.parse_args()
source=Path('/private/tmp/tennis-elo-source-projection-20261027.db')
working=Path('/private/tmp/tennis-elo-impact-'+a.arm+'.db')
assert not working.exists();shutil.copyfile(source,working)
os.environ['DATABASE_URL']='sqlite:///'+str(working)
from tennis_wc.database.migrations import init_db
from tennis_wc.database.db import get_connection
from tennis_wc.modelling.elo_builder import build_sackmann_elo
from tennis_wc.ingestion.raw_response_store import utc_now
init_db()
if a.allow_self_history:
 import tennis_wc.modelling.elo_builder as elo_builder
 elo_builder.history_active_clause=lambda conn: "history_status='ACTIVE'"
held=0
if a.quarantine:
 from tennis_wc.database.history_audit import quarantine_history_plan
 with get_connection() as c:held=quarantine_history_plan(c,json.load(open(a.quarantine)),utc_now())
summary=build_sackmann_elo()
c=get_connection()
ratings=[dict(r) for r in c.execute('SELECT id,overall_elo,surface_elo_json FROM players ORDER BY id')]
input_counts=dict(c.execute('SELECT source_provider,COUNT(*) FROM player_match_history GROUP BY source_provider').fetchall())
c.close()
result={'arm':a.arm,'source_projection_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'quarantined':held,'summary':summary,'input_counts':input_counts,'ratings':ratings,'note':'Input/rebuild impact only; not point-in-time predictive performance or profitability evidence.'}
Path(a.output).write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='ratings'}),flush=True)
