import sqlite3, sys, random, collections, bisect
import numpy as np
sys.path.insert(0,"/Users/imac/Antigravity-repo/tennis-wong-choi/src")
from tennis_wc.pricing.families import family_for_market
c=sqlite3.connect("file:/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db?mode=ro",uri=True); c.row_factory=sqlite3.Row
ms={r['id']:r for r in c.execute("select id,player_a_id,player_b_id,start_time_utc from matches where start_time_utc is not null")}
snaps=collections.defaultdict(list)
for r in c.execute("select match_id,player_a_odds a,player_b_odds b,fetched_at t,id from odds_snapshots where match_id is not null and market in ('match_winner','h2h','head_to_head') or match_id is not null order by id"):
    m=ms.get(r['match_id'])
    if not m or not (r['t']<m['start_time_utc']) or r['a']<=1 or r['b']<=1: continue
    pa=(1/r['a'])/((1/r['a'])+(1/r['b'])); snaps[r['match_id']].append((r['t'],pa))
print("markets in odds_snapshots:",c.execute("select market,count(*) from odds_snapshots group by 1").fetchall())
print("matches w/ prestart ML snaps",len(snaps),"with>=2",sum(len(v)>=2 for v in snaps.values()))
mv=[v[-1][1]-v[0][1] for v in snaps.values() if len(v)>=2]
print("abs move pctiles (pp)",[round(float(x)*100,1) for x in np.percentile(np.abs(mv),[50,75,90,95,99])])
LIVE={'player_game_handicap','first_set_winner','player_win_a_set','player_first_set_game_handicap','player_set_handicap','player_total_games'}
rows=[]
for r in c.execute("""select p.id,p.match_id,p.market_key,p.feed_market_name,p.decimal_odds o,p.result_status rs,p.subject_player_id sp,p.updated_at,p.priced_at,p.recorded_at,p.side,p.is_value v,p.market_prob_fair mk
 from prop_tracker p where p.is_point_in_time=1 and p.result_status in ('WON','LOST') and p.subject_player_id is not null"""):
    fam=family_for_market(r['market_key'],r['feed_market_name'] or '')
    if fam not in LIVE or fam=='player_total_games': continue
    s=snaps.get(r['match_id']); m=ms.get(r['match_id'])
    if not s or len(s)<2 or not m: continue
    T=r['priced_at'] or r['recorded_at']
    upto=[x for x in s if x[0]<=T]
    if len(upto)<2: continue
    d=upto[-1][1]-upto[0][1]
    if r['sp']==m['player_b_id']: d=-d
    elif r['sp']!=m['player_a_id']: continue
    if r['side']=='under': d=-d
    y=1 if r['rs']=='WON' else 0
    rows.append(dict(match_id=r['match_id'],fam=fam,o=r['o'],y=y,pl=(r['o']-1 if y else -1.0),d=d,v=r['v'],mk=r['mk'],hrs=0))
print("prop rows with ML move known at pricing time:",len(rows),"matches",len({r['match_id'] for r in rows}))
roi=lambda s: sum(r['pl'] for r in s)/len(s) if s else 0
def boot(rs,n=1000):
    by=collections.defaultdict(list)
    for r in rs: by[r['match_id']].append(r)
    k=list(by); rng=random.Random(20260826); out=[]
    for _ in range(n):
        s=[]
        for x in rng.choices(k,k=len(k)): s+=by[x]
        out.append(roi(s))
    out.sort(); return out[25],out[974]
def line(nm,s):
    if len(s)<30: print(f"  {nm:28s} n={len(s)} thin roi={roi(s):+.3f}"); return
    lo,hi=boot(s); print(f"  {nm:28s} n={len(s):5d} m={len({r['match_id'] for r in s}):4d} win={np.mean([r['y'] for r in s]):.3f} exp={np.mean([r['mk'] for r in s if r['mk']]):.3f} avgO={np.mean([r['o'] for r in s]):.2f} ROI={roi(s):+.3f} [{lo:+.3f},{hi:+.3f}]")
bk=[(-1,-.05),(-.05,-.02),(-.02,-.005),(-.005,.005),(.005,.02),(.02,.05),(.05,1)]
print("ALL live player-side props by subject-player ML move (open -> pricing time)")
for a,b in bk: line(f"move {a:+.3f}..{b:+.3f}",[r for r in rows if a<=r['d']<b])
for f in ['first_set_winner','player_win_a_set','player_game_handicap','player_set_handicap']:
    print(f)
    for a,b in [(-1,-.02),(-.02,.02),(.02,1)]: line(f"move {a:+.2f}..{b:+.2f}",[r for r in rows if r['fam']==f and a<=r['d']<b])
