def merge(base, cand):
    ci={(r.get('meeting'), r.get('race')): r for r in cand}
    out=[]
    for r in base:
        c=ci.get((r.get('meeting'), r.get('race')))
        if c is None: continue
        cr={x['n']:x for x in c['rows']}
        rows=[]
        for x in r['rows']:
            y=cr.get(x['n'])
            if y is None: continue
            x=dict(x); x['_c']=y; rows.append(x)
        out.append({**r,'rows':rows})
    return out
