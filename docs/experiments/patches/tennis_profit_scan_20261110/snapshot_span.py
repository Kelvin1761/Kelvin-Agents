import sqlite3, collections, numpy as np
from datetime import datetime
c=sqlite3.connect("file:/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db?mode=ro",uri=True)
f=lambda s: datetime.fromisoformat(s.replace('Z','+00:00'))
d=collections.defaultdict(list)
for mid,a,b,t,st in c.execute("select o.match_id,o.player_a_odds,o.player_b_odds,o.fetched_at,m.start_time_utc from odds_snapshots o join matches m on m.id=o.match_id where m.start_time_utc is not null and o.fetched_at<m.start_time_utc and m.match_date>='2026-08-17' order by o.id"):
    d[mid].append((t,a,b,st))
span=[];last=[];moved=[];n=[]
for v in d.values():
    if len(v)<2: continue
    span.append((f(v[-1][0])-f(v[0][0])).total_seconds()/3600); last.append((f(v[-1][3])-f(v[-1][0])).total_seconds()/3600)
    moved.append(v[0][1]!=v[-1][1] or v[0][2]!=v[-1][2]); n.append(len(v))
print("matches",len(span),"snaps/match median",np.median(n))
print("span first->last prestart snap hrs pctiles 25/50/75",np.percentile(span,[25,50,75]).round(1))
print("last snap to start hrs pctiles 25/50/75",np.percentile(last,[25,50,75]).round(1))
span=np.array(span);moved=np.array(moved)
for lo,hi in[(0,1),(1,6),(6,12),(12,24),(24,999)]:
    k=(span>=lo)&(span<hi); print(f"span {lo}-{hi}h n={k.sum()} price changed={moved[k].mean() if k.sum() else 0:.3f}")
