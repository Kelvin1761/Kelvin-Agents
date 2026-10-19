import json,sys
from collections import defaultdict
rows=[json.loads(l) for l in open(sys.argv[1])]; rows=[r for r in rows if "horses" in r]
# bucket by draw_score prior level (75/65/49 turn; straight 77/65/50) via raw draw score rounding is unavailable -> use draw_score band
agg=defaultdict(lambda:[0,0,0.0])
risk=defaultdict(int); tot=0
for r in rows:
    n=len([h for h in r["horses"] if h.get("pos")])
    for h in r["horses"]:
        if not h.get("pos"): continue
        d=h["f"]["draw_score"]; b="high(>=70)" if d>=70 else "mid(58-70)" if d>=58 else "low(<58)"
        k=(r["venue"], "1000直" if r["distance"]==1000 and r["venue"]=="沙田" and not r["awt"] else "彎", b)
        a=agg[k]; a[0]+=1; a[1]+= h["pos"]<=3; a[2]+= 3/n
        if not h.get("debut"):
            tot+=1; risk["draw<55"]+= d<55; risk["dist<58"]+= h["f"]["distance_score"]<58
for k in sorted(agg):
    n,p,e=agg[k]; print(k, n, f"place {p/n:.3f}  expected(3/field) {e/n:.3f}  ratio {p/e:.2f}")
print({k:round(v/tot,3) for k,v in risk.items()}, tot)
