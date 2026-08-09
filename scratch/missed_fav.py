"""「走漏嘅熱門」cohort：$1–3 上名馬，我哋捉到 vs 走漏，有咩唔同。唯讀。"""
import json, statistics
from pathlib import Path
import numpy as np

races=json.loads(Path('scratch/fl_new.json').read_text())['races']
def sp(h):
    try: return float(str(h.get('sp') or '').replace('$','').strip())
    except ValueError: return None

caught, missed = [], []
for rc in races:
    order=sorted(rc['rows'], key=lambda h:(-h['ability'], h['n']))
    rank={h['n']:i+1 for i,h in enumerate(order)}
    # 場內賠率名次（市場點睇）
    prices=sorted([(sp(h), h['n']) for h in rc['rows'] if sp(h) is not None])
    mrank={n:i+1 for i,(s,n) in enumerate(prices)}
    for h in rc['rows']:
        s=sp(h)
        if h['pos']>3 or s is None or s>=3.0: continue
        rec={"race":rc, "h":h, "rank":rank[h['n']], "mrank":mrank.get(h['n']),
             "sp":s, "field":rc['field']}
        (caught if rank[h['n']]<=3 else missed).append(rec)

print(f"$1–3 上名馬：捉到 {len(caught)}，走漏 {len(missed)}\n")
print("走漏嗰批，我哋畀咗佢第幾名：")
import collections
c=collections.Counter(r['rank'] for r in missed)
for k in sorted(c): print(f"   第 {k:>2} 名 : {c[k]:>3} 匹  {'█'*c[k]}")
print(f"   中位排名 {statistics.median(r['rank'] for r in missed):.0f}"
      f"，平均場數 {statistics.mean(r['field'] for r in missed):.1f} 匹")

LEAVES=["form_score","consistency_score","pace_figure_score","sectional_score",
        "trial_score","pace_map_score","jockey_score","trainer_score",
        "jockey_horse_fit_score","rating_score","track_score","formline_score"]
print(f"\n{'leaf':26}{'捉到':>9}{'走漏':>9}{'差距':>9}{'走漏 vs 同場中位':>18}")
for lf in LEAVES:
    a=[r['h']['features'].get(lf,60) for r in caught]
    b=[r['h']['features'].get(lf,60) for r in missed]
    rel=[]
    for r in missed:
        med=statistics.median(x['features'].get(lf,60) for x in r['race']['rows'])
        rel.append(r['h']['features'].get(lf,60)-med)
    print(f"{lf:26}{statistics.mean(a):>9.1f}{statistics.mean(b):>9.1f}"
          f"{statistics.mean(b)-statistics.mean(a):>+9.1f}{statistics.mean(rel):>+18.1f}")

print(f"\n{'':26}{'捉到':>9}{'走漏':>9}")
print(f"{'綜合戰力分':26}{statistics.mean(r['h']['ability'] for r in caught):>9.2f}"
      f"{statistics.mean(r['h']['ability'] for r in missed):>9.2f}")
print(f"{'場內賠率名次':26}{statistics.mean(r['mrank'] for r in caught if r['mrank']):>9.2f}"
      f"{statistics.mean(r['mrank'] for r in missed if r['mrank']):>9.2f}")
print(f"{'馬群大細':26}{statistics.mean(r['field'] for r in caught):>9.2f}"
      f"{statistics.mean(r['field'] for r in missed):>9.2f}")
print(f"{'實際名次':26}{statistics.mean(r['h']['pos'] for r in caught):>9.2f}"
      f"{statistics.mean(r['h']['pos'] for r in missed):>9.2f}")
