import sys,os,json,collections
from datetime import date,timedelta
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','..','..','.agents','skills','nba'))
import nba_espn_league as L, nba_minutes as M
from nba_schedule import canonical_team_abbr
SNAP=os.path.expanduser('~/WongChoiData/NBA_ESPN_Snapshots')
cache={}
def snap(day):
    if day in cache: return cache[day]
    folder=f'{SNAP}/{day}'; out=None
    if os.path.isdir(folder):
        out={}
        out_ids=set()
        try:
            inj=json.load(open(folder+'/injuries.json'))
            for team in inj.get('injuries') or []:
                for i in team.get('injuries') or []:
                    if str(i.get('status','')).lower() in ('out',): out_ids.add(str(((i.get('athlete') or {}).get('links') or [{}])[0].get('href','')).split('/id/')[-1].split('/')[0])
        except Exception: pass
        for f in os.listdir(folder):
            if not f.startswith('depthchart_'): continue
            j=json.load(open(f'{folder}/{f}')); t=canonical_team_abbr(f[len('depthchart_'):-5])
            pos=(j.get('depthchart') or [{}])[0].get('positions') or {}
            lists={p:[str(a.get('id')) for a in (pos.get(p) or {}).get('athletes') or []] for p in ('pg','sg','sf','pf','c')}
            raw={l[0] for l in lists.values() if l}
            fill=set()
            for p,l in lists.items():
                for pid in l:
                    if pid not in out_ids and pid not in fill: fill.add(pid); break
            out[t]={'raw':raw,'fill':fill,'lists':lists}
        out['_out']=out_ids
    cache[day]=out; return out
games=sorted([g for g in L.season_games('2026-27','11/19/2026')],key=lambda g:(g['date'],g['event_id']))
prev={}; res=collections.defaultdict(lambda:[0,0,0,0])
for g in games:
    us=date.fromisoformat(g['date']); syd=us+timedelta(days=1)
    st=M.starters(g['event_id'],us)
    for t in g['teams']:
        act=st & {p['espn_id'] for p in g['players'] if p['team']==t}
        if g['date']>='2026-10-31' and len(act)==5:
            cands={'上一場正選':prev.get(t)}
            for lab,d in (('21:00',syd-timedelta(days=1)),('朝早',syd)):
                s=snap(d.isoformat())
                if s and t in s:
                    cands[f'{lab} depth chart']=s[t]['raw']; cands[f'{lab} depth chart 剔 Out']=s[t]['fill']
                    if prev.get(t):
                        keep={p for p in prev[t] if p not in s['_out']}; need=5-len(keep)
                        order=[pid for i in range(15) for l in s[t]['lists'].values() if len(l)>i for pid in [l[i]]]
                        for pid in order:
                            if need<=0: break
                            if pid not in keep and pid not in s['_out']: keep.add(pid); need-=1
                        cands[f'{lab} 上一場正選剔 Out＋depth chart 補']=keep
            for k,pred in cands.items():
                if not pred: continue
                r=res[k]; r[0]+=1; r[1]+=len(pred&act); r[2]+=len(pred); r[3]+=pred==act
        prev[t]=st & {p['espn_id'] for p in g['players'] if p['team']==t}
for k,(n,hit,tot,ex) in res.items(): print(f'  {k:22s} 球隊-場次 {n:4d}  正選命中 {100*hit/tot:5.1f}%  五個全中 {100*ex/n:4.0f}%')
print('傷停名單 Out 人數（樣本日）',len(snap('2026-11-15')['_out']))
