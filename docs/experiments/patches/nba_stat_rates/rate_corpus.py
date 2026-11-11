"""Per-minute rate corpus: every feature uses games strictly before the game's US date."""
import sys,os,pickle,collections,math
NBA=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','..','..','.agents','skills','nba'); sys.path.insert(0,NBA)
import nba_espn_league as L
HM,HR,PRIOR=3.0,20.0,30.0
PK=('MIN','PTS','REB','OREB','DREB','AST','FG3M','FG3A','FGA','FGM','FTA','FTM','PF','TOV')
TK=('FGA','FGM','FG3A','FG3M','FTA','FTM','OREB','DREB','REB','AST','PTS','PF','TOV','POSS')
D=os.path.dirname(os.path.abspath(__file__))
totals={}
try:
    for r in pickle.load(open(D+'/../nba_minutes_v2/min_corpus2.pkl','rb')):
        if r.get('total') is not None: totals[r['gid']]=float(r['total'])
except Exception: pass
def build(season,to):
    games=sorted(L.season_games(season,to),key=lambda g:(g['date'],g['event_id']))
    ph=collections.defaultdict(list); th=collections.defaultdict(list)   # team -> [(own dict, opp dict)]
    lg=collections.Counter(); lgn=0
    by=collections.defaultdict(list)
    for g in games: by[g['date']].append(g)
    rows=[]
    for day in sorted(by):
        pend=[]
        for g in by[day]:
            tm=list(g['teams'])
            tt={t:{**{k:float(g['teams'][t].get(k,0) or 0) for k in TK if k!='POSS'},'POSS':L.possessions(g['teams'][t])} for t in tm}
            def tstat(t):
                h=th[t]; n=len(h)
                if n==0: return None
                own={k:sum(o[k] for o,_ in h)/n for k in TK}; opp={k:sum(x[k] for _,x in h)/n for k in TK}
                return n,own,opp
            league={k:lg[k]/lgn for k in TK} if lgn else None
            for p in g['players']:
                pid=p['espn_id']
                if not pid or p['MIN']<=0: continue
                h=ph[pid]
                t=p['team']; o=tm[1] if t==tm[0] else tm[0]
                if len(h)>=5 and league and th[t] and th[o] and h[-1]['team']==t:
                    hn=h[::-1]; mins=[x['MIN'] for x in hn]
                    wm=[0.5**(i/HM) for i in range(len(hn))]; m_hl=sum(a*b for a,b in zip(wm,mins))/sum(wm)
                    if m_hl>=15:
                        wr=[0.5**(i/HR) for i in range(len(hn))]; totm=sum(mins); swm=sum(a*b for a,b in zip(wr,mins))
                        def rate(k):
                            tot=sum(x[k] for x in hn); return (sum(a*x[k] for a,x in zip(wr,hn))+PRIOR*tot/totm)/(swm+PRIOR)
                        tots={k:sum(x[k] for x in hn) for k in PK}
                        rows.append(dict(season=season,day=day,gid=g['event_id'],pid=pid,team=t,opp=o,y={k:p.get(k,0.0) for k in PK},
                            rate={k:rate(k) for k in PK if k!='MIN'},tot=tots,n=len(hn),m_hl=m_hl,
                            own=tstat(t),oppt=tstat(o),league=league,total=totals.get(g['event_id'])))
                pend.append(('P',pid,{**{k:float(p.get(k,0) or 0) for k in PK},'team':t}))
            for t in tm:
                o=tm[1] if t==tm[0] else tm[0]; pend.append(('T',t,tt[t],tt[o]))
        for x in pend:
            if x[0]=='P': ph[x[1]].append(x[2])
            else:
                th[x[1]].append((x[2],x[3]))
                for k in TK: lg[k]+=x[2][k]
                lgn+=1
    return rows
out=build('2025-26','04/20/2026')+build('2026-27','11/10/2026')
pickle.dump(out,open(D+'/rate_corpus.pkl','wb'))
print(len(out),collections.Counter(r['season'] for r in out),'有總分盤',sum(r['total'] is not None for r in out))
