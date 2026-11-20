"""A/B: Challenger match model with vs without the calendar surface. Read-only on a DB copy."""
import os,sys,json,math,random,collections
D="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-dq-20261113/copy.db"
os.environ["DATABASE_URL"]="sqlite:///"+D
WT="/Users/imac/wt/claude-tennis-surface-20261113/tennis-wong-choi/src"
sys.path.insert(0,WT)
import sqlite3
from datetime import datetime
import tennis_wc.model.features.feature_builder as fb
from tennis_wc.model.match import predict_match_probability
from tennis_wc.sources.challenger_calendar import parse_calendar,resolve
from tennis_wc.model.features.common import datapoint
wiki=json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'wiki.json')))['parse']['wikitext']
EV=parse_calendar(wiki,2026)
c=sqlite3.connect("file:"+D+"?mode=ro",uri=True); c.row_factory=sqlite3.Row
rows=c.execute("""select m.id,m.match_date,m.start_time_utc,m.player_a_id,m.player_b_id,tn.name tname from matches m join tournaments tn on tn.id=m.tournament_id
 where m.match_date between '2026-08-20' and '2026-11-11' and tn.name like '%Challenger%' and tn.name not like '%Doubles%'
 and m.fixture_status!='DISPUTED' and m.start_time_utc is not null""").fetchall()
pop=[]
for r in rows:
    ev=resolve(EV,r['tname'],r['match_date'])
    if not ev: continue
    w={x[0] for x in c.execute("select winner_player_id from match_results where match_id=?",(r['id'],))}
    if len(w)!=1: continue
    w=w.pop()
    if w not in (r['player_a_id'],r['player_b_id']): continue
    o=c.execute("select player_a_odds,player_b_odds from odds_snapshots where match_id=? and fetched_at<? and player_a_odds>1 and player_b_odds>1 order by id limit 1",(r['id'],r['start_time_utc'])).fetchone()
    if not o: continue
    ia,ib=1/o[0],1/o[1]; mk=ia/(ia+ib)
    pop.append(dict(id=r['id'],y=1 if w==r['player_a_id'] else 0,mk=mk,surface=ev.surface,date=r['match_date']))
print("population",len(pop),collections.Counter(p['surface'] for p in pop),flush=True)
orig=fb._match_context
OVR={}
def patched(match,tournament,tl):
    ctx=orig(match,tournament,tl)
    s=OVR.get(match['id'])
    if s: ctx['surface']=datapoint(s,ctx['surface'].get('provenance') if isinstance(ctx.get('surface'),dict) else None)
    return ctx
fb._match_context=patched
SHARD,NSHARD=int(sys.argv[1]),int(sys.argv[2])
path=os.path.join(os.path.dirname(os.path.abspath(__file__)),f'surface_ab.{SHARD}.jsonl')
done=set()
if os.path.exists(path):
    for line in open(path):
        try: done.add(json.loads(line)['id'])
        except Exception: pass
fh=open(path,'a')
pop=[p for k,p in enumerate(pop) if k%NSHARD==SHARD and p['id'] not in done]
print("shard",SHARD,"todo",len(pop),"already",len(done),flush=True)
for i,p in enumerate(pop):
    try:
        OVR.clear(); s0,_=fb.assemble_match_feature_snapshot(p['id'],persist_derived=False); a=predict_match_probability(s0)['player_a_probability']
        OVR[p['id']]=p['surface']; s1,_=fb.assemble_match_feature_snapshot(p['id'],persist_derived=False); b=predict_match_probability(s1)['player_a_probability']
        se=[x.get('value') if isinstance(x,dict) else x for x in (s1['player_a'].get('surface_elo'),s1['player_a'].get('overall_elo'))]
        rec=dict(p,base=a,cand=b,se_a=se[0],oe_a=se[1])
    except Exception as e:
        rec=dict(p,err=f"{type(e).__name__}: {e}"[:120])
    fh.write(json.dumps(rec)+"\n"); fh.flush()
    if i%25==0: print(i,len(pop),flush=True)
print("done",flush=True)
