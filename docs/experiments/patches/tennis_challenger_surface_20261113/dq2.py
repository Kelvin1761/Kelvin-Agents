import os,sys,json,re,collections
D="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-dq-20261113/copy.db"
os.environ["DATABASE_URL"]="sqlite:///"+D
sys.path.insert(0,"/Users/imac/Antigravity-repo/tennis-wong-choi/src")
import sqlite3
from tennis_wc.model.features.feature_builder import assemble_match_feature_snapshot
c=sqlite3.connect(D)
mids=[r[0] for r in c.execute("select distinct p.match_id from prop_tracker p where p.priced_at>='2026-11-06' order by p.match_id desc limit 250")]
W=collections.Counter(); E=collections.Counter(); P=collections.Counter(); S=collections.Counter(); fail=collections.Counter(); per=[]
def norm(s): return re.sub(r'\[\d+\]','[i]',re.sub(r'player_[ab]\.','P.',s))
import tennis_wc.model.features.data_quality as dqm
for m in mids:
    try: snap,_=assemble_match_feature_snapshot(m,persist_derived=False)
    except Exception as e: fail[type(e).__name__+':'+str(e)[:60]]+=1; continue
    q=snap["data_quality"]; S[q["score"]]+=1
    ws=set(norm(w) for w in q["warnings"]);
    for w in ws: W[w]+=1
    for e in set(norm(e) for e in q["errors"]): E[e]+=1
print("matches",len(mids),"scored",sum(S.values()),"fails",dict(fail.most_common(5)))
print("score dist",sorted(S.items()))
print("ERRORS"); [print(f"  {v:4d} {k[:150]}") for k,v in E.most_common(10)]
print("WARNINGS (matches having it)"); [print(f"  {v:4d} {k[:150]}") for k,v in W.most_common(30)]
