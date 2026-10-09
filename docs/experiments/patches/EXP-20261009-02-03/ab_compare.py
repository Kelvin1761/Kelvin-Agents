"""兩份 leaves dump（同一語料，base vs cand 引擎）→ au_eval.compare。"""
import json, sys
from pathlib import Path
SCRIPTS = Path(sys.argv[1])
sys.path.insert(0, str(SCRIPTS))
import au_eval as E
base = E.load_races(sys.argv[2]); cand = E.load_races(sys.argv[3])
key = lambda r: (r.get('meeting'), r.get('race'))
ci = {key(r): r for r in cand}
merged, changed_r, changed_h = [], 0, 0
for r in base:
    c = ci.get(key(r))
    if c is None: continue
    cr = {x['n']: x for x in c['rows']}
    rows = []
    for x in r['rows']:
        y = cr.get(x['n'])
        if y is None: continue
        x = dict(x); x['_c'] = y; rows.append(x)
        if y['features'] != x['features'] or y['wet'] != x['wet']: changed_h += 1
    if any(x['_c']['features'] != x['features'] for x in rows): changed_r += 1
    merged.append({**r, 'rows': rows})
print(f'races {len(merged)}  changed races {changed_r}  changed horses {changed_h}')
cand_scorer = lambda row: E.default_scorer(row['_c'])
v = E.compare(merged, E.default_scorer, cand_scorer, label=sys.argv[4] if len(sys.argv)>4 else 'cand', leakage_audit_passed=True)
d = E.verdict_dict(v)
print(json.dumps(d, ensure_ascii=False, indent=1, default=str)[:6000])
