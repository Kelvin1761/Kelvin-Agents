import csv, json, random
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing")
LEAVES = ["form_score","consistency_score","jockey_score","trainer_score","speed_score","race_shape_context_score","risk_score",
          "weight_score","trackwork_trend_score","same_distance_signal_score","formline_strength_score","class_score","draw_score",
          "margin_trend_score","confidence_score","distance_score","track_going_score"]
rows = [json.loads(l) for l in open(__import__("sys").argv[1])]
rows = [r for r in rows if r.get("horses") and "speed_score" not in (r.get("meeting_dead_fields") or [])]
per = {k: [] for k in LEAVES}; rho = {k: ([], []) for k in LEAVES}; cov = {k: [0, 0] for k in LEAVES}
for r in rows:
    p = ROOT / r["meeting"] / f"Race_{r['race']}_Auto_Scoring.csv"
    if not p.exists(): continue
    pos = {h["n"]: h["pos"] for h in r["horses"] if h.get("pos")}
    raw = {h["n"]: h["raw"] for h in r["horses"]}
    recs = []
    for c in csv.DictReader(open(p, encoding="utf-8-sig")):
        n = c.get("horse_number") or c.get("horse_no") or c.get("number")
        try: n = int(float(n))
        except (TypeError, ValueError): continue
        if n in pos: recs.append((n, c))
    if len(recs) < 4: continue
    for k in LEAVES:
        vals = []
        for n, c in recs:
            try: vals.append((float(c[k]), pos[n] <= 3, raw[n]))
            except (KeyError, ValueError, TypeError): pass
        if len(vals) < 4: continue
        cov[k][0] += sum(1 for v in vals if v[0] != 60); cov[k][1] += len(vals)
        pz = [v for v in vals if v[1]]; ng = [v for v in vals if not v[1]]
        if not pz or not ng: continue
        per[k].append(np.mean([(a[0] > b[0]) + 0.5 * (a[0] == b[0]) for a in pz for b in ng]))
        rho[k][0].extend(v[0] for v in vals); rho[k][1].extend(v[2] for v in vals)
rng = random.Random(3)
for k in LEAVES:
    a = per[k]
    if not a: print(k, "n/a"); continue
    b = sorted(np.mean([a[rng.randrange(len(a))] for _ in a]) for _ in range(500))
    print(f"{k:28s} races {len(a):3d} AUC {np.mean(a):.4f} [{b[12]:.4f},{b[487]:.4f}]  non-60 {cov[k][0]/max(cov[k][1],1):.0%}  rho_vs_composite {spearmanr(*rho[k]).correlation:+.2f}")
