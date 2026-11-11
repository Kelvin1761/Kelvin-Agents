"""Engine-exact test: FG3M as attempts x shrunk accuracy, computed inside the live S recipe."""
import json,glob,os,sys,math,pickle,collections,random
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','..','..','.agents','skills','nba'))
from nba_engine import model
from nba_identity import player_name_key
from nba_schedule import canonical_team_abbr
s=model.config()['season_rate']
A=os.path.expanduser("~/WongChoiData/Wong Choi NBA Analysis"); L=os.path.expanduser('~/WongChoiData/NBA_Market_Eval/ledger')
def mu3(season_log,opponent,season,team,K,opp_key):
    games=model._games(season_log)
    if games is None or len(games)<s['min_games'] or not isinstance(opponent,dict) or opponent.get('status')!='available': return None
    try: allowed=[float(v) for v in opponent['allowed'][opp_key]]; league=float(opponent['league_avg'][opp_key])
    except (KeyError,TypeError,ValueError): return None
    previous=[g['season']!=season for g in games]; moved=False
    if any(previous):
        last=next(g['team'] for g,p in zip(games,previous) if p)
        if last is None: return None
        moved=canonical_team_abbr(last)!=canonical_team_abbr(team)
    w,mf=s['previous_season_weight']['FG3M']; f=[w*(mf if moved else 1.0) if p else 1.0 for p in previous]
    mins=[g['MIN'] for g in games]
    wm=[0.5**(i/s['minutes_half_life'])*f[i] for i in range(len(games))]; wr=[0.5**(i/s['rate_half_life'])*f[i] for i in range(len(games))]
    minutes=sum(a*b for a,b in zip(wm,mins))/sum(wm); totm=sum(a*b for a,b in zip(f,mins)); prior=s['prior_minutes']
    tot=lambda k: sum(a*g[k] for a,g in zip(f,games))
    rate=lambda k:(sum(a*g[k] for a,g in zip(wr,games))+prior*tot(k)/totm)/(sum(a*b for a,b in zip(wr,mins))+prior)
    e3=(tot('FG3M')+0.36*K)/(tot('FG3A')+K)
    mu=minutes*rate('FG3A')*e3
    shrink=s['opponent_shrink_games']; mu*=((sum(allowed)+shrink*league)/(len(allowed)+shrink))/league
    return max(mu,0.05)
def kfor(mu):
    sc,pw=s['dispersion']['FG3M']; return s['dispersion_k']['FG3M']*sc*(max(mu,.3)/s['dispersion_ref']['FG3M'])**pw
rows=[]; seen_keys=collections.Counter()
for f in sorted(glob.glob(L+'/*.jsonl')):
    d=os.path.basename(f)[:10]; folder=f"{A}/{d} NBA Analysis"
    if not os.path.isdir(folder): continue
    legs={}; setl={}
    for line in open(f):
        if '"row_type": "model_obs"' in line and '"snapshot_role": "production"' in line and '"fg3m"' in line:
            r=json.loads(line)
            if r.get('post_tip') or r.get('market')!='fg3m': continue
            k=(r['game_tag'],r['player'],float(r['line']))
            if k not in legs or r['recorded_at']<legs[k]['recorded_at']: legs[k]=r
        elif '"row_type": "settlement"' in line and '"fg3m"' in line:
            r=json.loads(line)
            if r.get('y') is not None: setl[(r['game_tag'],r['player'],float(r['line']))]=r['y']
    pk={}
    for (g,pl,line),v in legs.items():
        if (g,pl,line) not in setl or not v.get('price_at_model'): continue
        if g not in pk:
            try: pk[g]=json.load(open(f"{folder}/nba_game_data_{g}.json"))
            except Exception: pk[g]=None
        j=pk[g]
        if not j: continue
        season=(j.get('meta') or {}).get('roster_season')
        for team,plist in (j.get('players') or {}).items():
            m=[p for p in plist if player_name_key(p.get('name',''))==player_name_key(pl)]
            if len(m)!=1: continue
            sl=(m[0].get('gamelog') or {}).get('season_log'); opp=(j.get('opponent_context') or {}).get(team)
            if isinstance(opp,dict): seen_keys.update((opp.get('allowed') or {}).keys())
            pS=model.s_prob(sl,'FG3M',line,opp,season,team)
            if pS is None: break
            out=dict(d=d,y=setl[(g,pl,line)],price=float(v['price_at_model']),pS=pS)
            for K in (100,200,400):
                for ok in ('FG3M','FG3A'):
                    mu=mu3(sl,opp,season,team,K,ok)
                    out[f'K{K}_{ok}']=None if mu is None else model.nb_tail(line,mu,kfor(mu))
            rows.append(out); break
print('legs',len(rows),'days',len({r['d'] for r in rows}),'opponent allowed keys',dict(seen_keys))
def ll(p,y): p=min(max(p,1e-4),1-1e-4); return -(math.log(p) if y else math.log(1-p))
def ci(pairs):
    dd=collections.defaultdict(list)
    for d,v in pairs: dd[d].append(v)
    ks=sorted(dd); rnd=random.Random(4); o=[]
    for _ in range(1000):
        z=[v for k in (rnd.choice(ks) for _ in ks) for v in dd[k]]; o.append(sum(z)/len(z))
    o.sort(); return o[25],o[974]
base=[r for r in rows]
print(f"市場 {sum(ll(1/r['price'],r['y']) for r in base)/len(base):.4f}  S現行 {sum(ll(r['pS'],r['y']) for r in base)/len(base):.4f}")
for key in [k for k in rows[0] if k.startswith('K') and k.endswith('FG3M')]:
    R=[r for r in rows if r[key] is not None]
    pr=[(r['d'],ll(r[key],r['y'])-ll(r['pS'],r['y'])) for r in R]; lo,hi=ci(pr)
    early=[(r['d'],ll(r[key],r['y'])-ll(r['pS'],r['y'])) for r in R if r['d']<'2026-11-01']; late=[(r['d'],ll(r[key],r['y'])-ll(r['pS'],r['y'])) for r in R if r['d']>='2026-11-01']
    print(f"  {key:10s} n={len(R)} S新 {sum(ll(r[key],r['y']) for r in R)/len(R):.4f}  Δ對S {sum(v for _,v in pr)/len(pr):+.4f} [{lo:+.4f},{hi:+.4f}]  10月 {sum(v for _,v in early)/max(len(early),1):+.4f}(n={len(early)}) 11月 {sum(v for _,v in late)/max(len(late),1):+.4f}(n={len(late)})")
pickle.dump(rows,open(os.path.dirname(os.path.abspath(__file__))+'/dec3.pkl','wb'))
