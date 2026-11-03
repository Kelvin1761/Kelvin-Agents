"""Compare A (starter PDF) vs B (PDF removed, fsc fallback) for one meeting."""
import json, sys, re, difflib
from pathlib import Path
root = Path(sys.argv[1]); m = sys.argv[2]
A, B = root / 'A' / m, root / 'B' / m
out = {'meeting': m, 'races': [], 'rank_diffs': [], 'score_diffs': [], 'facts_diff_lines': 0, 'facts_non_overseas_diff': []}
for la in sorted(A.glob('Race_*_Logic.json'), key=lambda p: int(re.search(r'\d+', p.name).group())):
    lb = B / la.name
    ja, jb = json.loads(la.read_text()), json.loads(lb.read_text())
    race = int(re.search(r'\d+', la.name).group())
    ha, hb = ja['horses'], jb['horses']
    same = 0
    for num in ha:
        pa, pb = ha[num].get('python_auto') or {}, (hb.get(num) or {}).get('python_auto') or {}
        if pa.get('rank') != pb.get('rank'):
            out['rank_diffs'].append({'race': race, 'horse': num, 'name': ha[num].get('horse_name'), 'A': pa.get('rank'), 'B': pb.get('rank')})
        fa, fb = pa.get('feature_scores') or {}, pb.get('feature_scores') or {}
        moved = {k: (fa.get(k), fb.get(k)) for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)}
        if pa.get('ability_score') != pb.get('ability_score') or moved:
            out['score_diffs'].append({'race': race, 'horse': num, 'name': ha[num].get('horse_name'),
                                       'ability': (pa.get('ability_score'), pb.get('ability_score')), 'features': moved,
                                       'ovs_A': len((ha[num].get('_data') or {}).get('pdf_overseas_races') or []),
                                       'ovs_B': len(((hb.get(num) or {}).get('_data') or {}).get('pdf_overseas_races') or [])})
        else:
            same += 1
    out['races'].append({'race': race, 'horses': len(ha), 'identical': same})
# Facts: which diff lines are outside the overseas table
for fa in sorted(A.glob('* Race * Facts.md')):
    fb = B / fa.name
    a, b = fa.read_text().splitlines(), fb.read_text().splitlines()
    for line in difflib.unified_diff(a, b, lineterm='', n=0):
        if line.startswith(('---', '+++', '@@')): continue
        out['facts_diff_lines'] += 1
        body = line[1:]
        # overseas table rows start with '| n | d/m/yyyy |'
        if not re.match(r'^\| \d+ \| \d{1,2}/\d{1,2}/\d{4} \|', body) and '海外賽績 (來自 PDF)' not in body and not body.startswith('| # | 日期 | 地區') and not body.startswith('|---|------|------|'):
            out['facts_non_overseas_diff'].append((fa.name, line[:220]))
print(json.dumps(out, ensure_ascii=False, indent=1))
