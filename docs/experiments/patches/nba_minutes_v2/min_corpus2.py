"""Minutes corpus v2: adds starter flag, pre-game spread/total (ESPN pickcenter) and absences. As-of unless marked."""
import sys,os,pickle,collections,statistics as st
from datetime import date
NBA=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','..','..','.agents','skills','nba'); sys.path.insert(0,NBA)
import nba_espn_league as L, nba_espn_lineups as U
from nba_schedule import canonical_team_abbr
HL=3.0
def extras(event_id,day):
    s=U.fetch_summary(event_id,date.fromisoformat(day))
    starters=set(); out_inj=collections.defaultdict(set); played=collections.defaultdict(set)
    for side in (s.get('boxscore') or {}).get('players') or []:
        t=canonical_team_abbr(((side.get('team') or {}).get('abbreviation')) or '')
        for a in ((side.get('statistics') or [{}])[0].get('athletes') or []):
            pid=str((a.get('athlete') or {}).get('id') or '')
            if a.get('starter'): starters.add(pid)
            if a.get('didNotPlay'):
                if 'COACH' not in str(a.get('reason') or '').upper(): out_inj[t].add(pid)
            else: played[t].add(pid)
    spread=total=fav=None
    for pc in s.get('pickcenter') or []:
        if pc.get('spread') is not None:
            spread=abs(float(pc['spread'])); total=pc.get('overUnder')
            comp=((s.get('header') or {}).get('competitions') or [{}])[0].get('competitors') or []
            ids={str((c.get('team') or {}).get('id')):canonical_team_abbr((c.get('team') or {}).get('abbreviation') or '') for c in comp}
            for key in ('awayTeamOdds','homeTeamOdds'):
                o=pc.get(key) or {}
                if o.get('favorite'): fav=ids.get(str(o.get('teamId')))
            break
    return starters,out_inj,spread,total,fav
def build(season,to):
    games=sorted(L.season_games(season,to),key=lambda g:(g['date'],g['event_id']))
    hist=collections.defaultdict(list)       # pid -> [(date, team, MIN, started)]
    tlast={}                                 # team -> (date, set(played pids))
    tcount=collections.Counter()
    rows=[]; by_day=collections.defaultdict(list)
    for g in games: by_day[g['date']].append(g)
    for day in sorted(by_day):
        pend=[]
        for g in by_day[day]:
            starters,out_inj,spread,total,fav=extras(g['event_id'],day)
            teams=list(g['teams'])
            for t in teams:
                roster=[p for p in g['players'] if p['team']==t and p['espn_id']]
                def avg(pid):
                    h=[m for _,tt,m,_ in hist[pid][-10:] if tt==t]; return st.mean(h) if len(h)>=3 else 0.0
                prev=tlast.get(t)
                # regulars = anyone with >=15 avg on this team who appeared in the team's last 5 games
                pool_prev=sum(avg(pid) for pid in tlast.get((t,'regs'),set()) if prev and pid not in prev[1])       # as-of: missed previous team game
                pool_today=sum(avg(pid) for pid in out_inj[t] if avg(pid)>=15)                                       # same-day injury/rest DNP (pre-game-knowable in principle)
                for p in roster:
                    if p['MIN']<=0: continue
                    h=hist[p['espn_id']]
                    if len(h)>=5:
                        mins=[x[2] for x in h][::-1]; w=[0.5**(i/HL) for i in range(len(mins))]
                        st5=[x[3] for x in h][-5:]
                        rows.append(dict(season=season,day=day,gid=g['event_id'],pid=p['espn_id'],team=t,y=p['MIN'],
                            m_hl=sum(a*b for a,b in zip(w,mins))/sum(w),m_season=st.mean(mins),m_l10=st.mean(mins[:10]),m_last=mins[0],sd5=st.pstdev(mins[:5]),n=len(mins),
                            started_prev=bool(h[-1][3]),start_share=sum(st5)/len(st5),starts_today=p['espn_id'] in starters,
                            spread=spread,total=total,is_fav=(fav==t) if fav else None,
                            rest=(date.fromisoformat(day)-date.fromisoformat(prev[0])).days if prev else 9,
                            gap_last=(date.fromisoformat(day)-date.fromisoformat(h[-1][0])).days,
                            missed_prev=bool(prev) and p['espn_id'] not in prev[1],
                            pool_prev=pool_prev,pool_today=pool_today))
                    pend.append((p['espn_id'],day,t,p['MIN'],p['espn_id'] in starters))
                pend.append(('T',t,day,{p['espn_id'] for p in roster if p['MIN']>0}))
        for x in pend:
            if x[0]=='T':
                t=x[1]; tlast[t]=(x[2],x[3]); tcount[t]+=1
            else: hist[x[0]].append((x[1],x[2],x[3],x[4]))
        for t in {x[1] for x in pend if x[0]=='T'}:
            tlast[(t,'regs')]={pid for pid,h in hist.items() if h and h[-1][1]==t and len([1 for z in h[-10:] if z[1]==t])>=3 and st.mean([z[2] for z in h[-10:] if z[1]==t])>=15 and (date.fromisoformat(day)-date.fromisoformat(h[-1][0])).days<=14}
    return rows
if __name__=='__main__':
    out=build('2025-26','04/20/2026')+build('2026-27','11/10/2026')
    pickle.dump(out,open(os.path.dirname(os.path.abspath(__file__))+'/min_corpus2.pkl','wb'))
    print(len(out),collections.Counter(r['season'] for r in out),'spread有',sum(r['spread'] is not None for r in out))
