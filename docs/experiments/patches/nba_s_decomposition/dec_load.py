import json,glob,os,sys,math,pickle,collections
NBA=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','..','..','.agents','skills','nba'); sys.path.insert(0,NBA)
from nba_engine import model
from nba_identity import player_name_key
from nba_schedule import canonical_team_abbr
cfg=model.config(); sr=cfg['season_rate']
A=os.path.expanduser("~/WongChoiData/Wong Choi NBA Analysis"); L=os.path.expanduser('~/WongChoiData/NBA_Market_Eval/ledger')
MK={'pts':'PTS','reb':'REB','ast':'AST','fg3m':'FG3M'}
def proj_minutes(season_log,season,team,stat):
    games=model._games(season_log)
    previous=[g['season']!=season for g in games]; moved=False
    if any(previous):
        last=next(g['team'] for g,p in zip(games,previous) if p)
        moved=canonical_team_abbr(last)!=canonical_team_abbr(team)
    w,mf=sr['previous_season_weight'][stat]
    f=[w*(mf if moved else 1.0) if p else 1.0 for p in previous]
    wm=[0.5**(i/sr['minutes_half_life'])*f[i] for i in range(len(games))]
    mins=[g['MIN'] for g in games]
    return sum(a*b for a,b in zip(wm,mins))/sum(wm), mins, sum(1 for p in previous if not p)
def kfor(stat,mu):
    scale,power=sr['dispersion'][stat]; return sr['dispersion_k'][stat]*scale*(max(mu,.3)/sr['dispersion_ref'][stat])**power
def pm(t):
    try:
        a,b=str(t).split(':'); return int(a)+int(b)/60
    except Exception:
        try: return float(t)
        except Exception: return None
out=[]; stats=collections.Counter()
for f in sorted(glob.glob(L+'/*.jsonl')):
    d=os.path.basename(f)[:10]; folder=f"{A}/{d} NBA Analysis"
    if not os.path.isdir(folder): continue
    legs={}; setl={}
    for line in open(f):
        if '"row_type": "model_obs"' in line and '"snapshot_role": "production"' in line:
            r=json.loads(line)
            if r.get('post_tip') or r.get('market') not in MK: continue
            k=(r['game_tag'],r['player'],r['market'],float(r['line']))
            if k not in legs or r['recorded_at']<legs[k]['recorded_at']: legs[k]={kk:r.get(kk) for kk in('recorded_at','price_at_model','p_final','team')}
        elif '"row_type": "settlement"' in line:
            r=json.loads(line)
            if r.get('y') is not None: setl[(r['game_tag'],r['player'],r['market'],float(r['line']))]=(r['y'],r['actual'],pm(r.get('minutes')))
    pk={}
    for g in {k[0] for k in legs}:
        p=f"{folder}/nba_game_data_{g}.json"
        if os.path.isfile(p):
            try: pk[g]=json.load(open(p))
            except Exception: pass
    cache={}
    for k,v in legs.items():
        if k not in setl or k[0] not in pk or not v['price_at_model']: stats['no_settle_or_pkg']+=1; continue
        g,pl,mk,line=k; j=pk[g]; stat=MK[mk]; y,actual,mins=setl[k]
        if not mins or mins<=0: stats['no_minutes']+=1; continue
        ck=(g,pl,stat)
        if ck not in cache:
            cache[ck]=None
            for team,plist in (j.get('players') or {}).items():
                m=[p for p in plist if player_name_key(p.get('name',''))==player_name_key(pl)]
                if len(m)==1:
                    sl=(m[0].get('gamelog') or {}).get('season_log'); season=(j.get('meta') or {}).get('roster_season')
                    fit=model.season_mu(sl,stat,(j.get('opponent_context') or {}).get(team),season,team)
                    if fit:
                        mh,hist,ncur=proj_minutes(sl,season,team,stat)
                        cache[ck]=dict(mu=fit[0],k=fit[1],mhat=mh,hist=hist[:10],ncur=ncur)
                    break
        c=cache[ck]
        if not c: stats['no_S']+=1; continue
        mu_o=c['mu']*mins/c['mhat']
        out.append(dict(d=d,g=g,pl=pl,stat=stat,line=line,price=v['price_at_model'],p_final=v['p_final'],y=y,actual=actual,mins=mins,mhat=c['mhat'],mu=c['mu'],hist=c['hist'],ncur=c['ncur'],
                        pS=model.nb_tail(line,c['mu'],c['k']),pO=model.nb_tail(line,mu_o,kfor(stat,mu_o))))
        stats['ok']+=1
pickle.dump(out,open(os.path.dirname(os.path.abspath(__file__))+'/dec.pkl','wb')); print(dict(stats)); print(collections.Counter(x['d'] for x in out))
