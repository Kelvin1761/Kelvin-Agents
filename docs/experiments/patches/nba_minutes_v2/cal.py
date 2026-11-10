import json,glob,os,collections,statistics as st,pickle
L=os.path.expanduser('~/WongChoiData/NBA_Market_Eval/ledger')
legs={}; act={}
for f in sorted(glob.glob(L+'/*.jsonl')):
    for line in open(f):
        if '"row_type": "model_obs"' in line and '"snapshot_role": "production"' in line:
            r=json.loads(line)
            if r.get('post_tip') or r.get('p_final') is None: continue
            k=(r['target_date'],r['game_tag'],r['player'],r['market'],float(r['line']))
            if k in legs and legs[k]['t']<=r['recorded_at']: continue   # first production = 21:00
            inp=((r.get('prop_training') or {}).get('inputs') or {})
            legs[k]=dict(t=r['recorded_at'],p=r['p_final'],price=r.get('price_at_model'),h10=inp.get('hit_l10',r.get('p_l10_base_rate')),h5=inp.get('hit_l5'),picked=bool(r.get('picked')),l10=inp.get('l10_values'),eng=r.get('engine'))
        elif '"row_type": "settlement"' in line:
            r=json.loads(line)
            if r.get('y') is not None: act[(r['target_date'],r['game_tag'],r['player'],r['market'],float(r['line']))]=r['y']
X=[dict(v,y=act[k],d=k[0],mk=k[3],line=k[4]) for k,v in legs.items() if k in act and v['price']]
pickle.dump(X,open(os.path.dirname(os.path.abspath(__file__))+'/cal.pkl','wb'))
print(len(X),collections.Counter(x['eng'] for x in X))
def tab(name,rows):
    if len(rows)<25: print(f'{name:44s} n={len(rows)}'); return
    a=st.mean(x['y'] for x in rows); p=st.mean(x['p'] for x in rows); m=st.mean(1/x['price'] for x in rows)
    print(f'{name:44s} n={len(rows):5d} 實際 {a*100:5.1f}% 模型 {p*100:5.1f}% (差 {100*(a-p):+5.1f}pp) 1/價 {m*100:5.1f}%')
for era,sel in (('全部日子',lambda x:True),('新引擎 11-05 起',lambda x:x['d']>='2026-11-05')):
    R=[x for x in X if sel(x)]; print('==',era)
    B=[x for x in R if 1.2<=x['price']<=1.6]
    tab('價 1.2–1.6 全部腿',B)
    tab('  其中 L10≥80% 而且 L5≥80%',[x for x in B if (x['h10'] or 0)>=.8 and (x['h5'] or 0)>=.8])
    tab('  其中 L10<80%',[x for x in B if x['h10'] is not None and x['h10']<.8])
    tab('  其中 L10=100%',[x for x in B if (x['h10'] or 0)>=1])
    tab('  被揀入組合 (picked)',[x for x in B if x['picked']])
    for mk in ('pts','reb','ast','fg3m'):
        tab(f'  {mk} 全部',[x for x in B if x['mk']==mk]); tab(f'  {mk} L10≥80%&L5≥80%',[x for x in B if x['mk']==mk and (x['h10'] or 0)>=.8 and (x['h5'] or 0)>=.8])
