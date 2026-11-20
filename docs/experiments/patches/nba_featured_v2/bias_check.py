import json,glob,os,collections,math,statistics as st
L=os.path.expanduser('~/WongChoiData/NBA_Market_Eval/ledger')
rows=[]
for f in sorted(glob.glob(L+'/2026-11-0[5-9].jsonl')+glob.glob(L+'/2026-11-1[0-9].jsonl')):
    prod={}; act={}; ou=collections.defaultdict(list)
    for line in open(f):
        if '"ou_two_way"' in line:
            r=json.loads(line)
            if r.get('post_tip') or r.get('tip_unknown'): continue
            o,u=(r['price'],r['complement_price']) if r['side']=='over' else (r['complement_price'],r['price'])
            if o and u: ou[(r['game_tag'],r['player'],r['market'],float(r['ou_line']))].append((r['captured_at'],o,u))
        elif '"row_type": "settlement"' in line:
            r=json.loads(line)
            if r.get('actual') is not None and r.get('outcome')!='void': act[(r['game_tag'],r['player'],r['market'])]=float(r['actual'])
        elif '"row_type": "model_obs"' in line and '"snapshot_role": "production"' in line:
            r=json.loads(line)
            if r.get('post_tip') or r.get('p_final') is None: continue
            k=(r['game_tag'],r['player'],r['market'],float(r['line']))
            if k not in prod or r['recorded_at']<prod[k][0]: prod[k]=(r['recorded_at'],r['p_final'],r.get('odds_captured_at'),r.get('price_at_model'))
    for (g,p,m,l),obs in ou.items():
        a=act.get((g,p,m)); mo=prod.get((g,p,m,float(math.ceil(l))))
        if a is None or not mo: continue
        use=[x for x in obs if mo[2] and x[0]<=mo[2]] or [min(obs)]
        _,o,u=max(use); fair=(1/o)/(1/o+1/u)
        rows.append(dict(m=m,l=l,p=mo[1],fair=fair,y=a>l,o=o,u=u,mp=mo[3]))
print('lines',len(rows))
print('平均 模型P(大) %.3f | 比例去水 P(大) %.3f | 實際大 %.3f | milestone 1/價 %.3f'%(st.mean(r['p'] for r in rows),st.mean(r['fair'] for r in rows),st.mean(r['y'] for r in rows),st.mean(1/r['mp'] for r in rows if r['mp'])))
print('-- 按去水 P(大) 分組')
for lo,hi in ((0,.4),(.4,.47),(.47,.53),(.53,.6),(.6,1)):
    g=[r for r in rows if lo<=r['fair']<hi]
    if g: print(f"  去水 [{lo},{hi}) n={len(g):5d} 去水 {st.mean(r['fair'] for r in g):.3f} 模型 {st.mean(r['p'] for r in g):.3f} 實際 {st.mean(r['y'] for r in g):.3f}")
print('-- 線嘅高低')
for lo,hi in ((0,2),(2,5),(5,10),(10,99)):
    g=[r for r in rows if lo<=r['l']<hi]
    if g: print(f"  線 [{lo},{hi}) n={len(g):5d} 去水 {st.mean(r['fair'] for r in g):.3f} 模型 {st.mean(r['p'] for r in g):.3f} 實際 {st.mean(r['y'] for r in g):.3f}")
ll=lambda p,y: -math.log(max(min(p if y else 1-p,1-1e-4),1e-4))
print('log-loss 模型 %.4f 去水 %.4f'%(st.mean(ll(r['p'],r['y']) for r in rows),st.mean(ll(r['fair'],r['y']) for r in rows)))
import numpy as np
lg=lambda p: math.log(min(max(p,.02),.98)/(1-min(max(p,.02),.98)))
delta={}
for m in ('pts','reb','ast','fg3m'):
    g=[r for r in rows if r['m']==m]; x=np.array([lg(r['p']) for r in g]); y=np.array([r['y'] for r in g],float); d=0.0
    for _ in range(50):
        p=1/(1+np.exp(-(x+d))); d+= (y-p).sum()/max((p*(1-p)).sum(),1e-9)
    delta[m]=round(float(d),4)
print('\nδ（logit 修正，令平均對返實際）',delta)
for r in rows: r['p2']=1/(1+math.exp(-(lg(r['p'])+delta[r['m']])))
print('修正後 平均模型 %.3f 實際 %.3f；log-loss %.4f（修正前 %.4f，去水 %.4f）'%(st.mean(r['p2'] for r in rows),st.mean(r['y'] for r in rows),st.mean(ll(r['p2'],r['y']) for r in rows),st.mean(ll(r['p'],r['y']) for r in rows),st.mean(ll(r['fair'],r['y']) for r in rows)))
c=collections.Counter()
for r in rows:
    if r['l']<=1.5: continue
    eo=r['p2']-r['fair']; eu=-eo
    if max(eo,eu)>=.05: c['over' if eo>eu else 'under']+=1
print('修正後 edge≥5pp（剔 ≤1.5 線）嘅候選：',dict(c),' 修正前：',dict(collections.Counter(('over' if r['p']-r['fair']>0 else 'under') for r in rows if r['l']>1.5 and abs(r['p']-r['fair'])>=.05)))
