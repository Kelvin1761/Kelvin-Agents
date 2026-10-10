"""D12 pre-gate: can we predict early position? (pre-registered: rho>=0.6 and predicted-front hit>=70%)"""
import csv, sys
from collections import defaultdict
import numpy as np
from scipy.stats import spearmanr

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
races = defaultdict(list)
for r in rows:
    try:
        call = int(r["outcome_first_call"]); field = int(r["field"])
    except (ValueError, KeyError):
        continue
    if r["first_call_avg3"] in ("", "None") or field < 6:
        continue
    races[r["race_id"]].append((r["day"], float(r["first_call_avg3"]), float(r["draw_pct"] or 0.5), (call - 1) / (field - 1), call))
days = sorted({v[0][0] for v in races.values()})
cut = days[int(len(days) * 0.6)]
def fit_eval(use_draw):
    tr = [h for v in races.values() if v[0][0] < cut for h in v]
    X = np.array([[1, h[1]] + ([h[2]] if use_draw else []) for h in tr]); y = np.array([h[3] for h in tr])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    pred, act, hits, n = [], [], 0, 0
    for v in races.values():
        if v[0][0] < cut or len(v) < 6:
            continue
        p = [b[0] + b[1] * h[1] + (b[2] * h[2] if use_draw else 0) for h in v]
        pred += p; act += [h[3] for h in v]
        order = np.argsort(p)[:3]
        for i in order:
            n += 1; hits += v[i][4] <= 3
    rho = spearmanr(pred, act).correlation
    print(f"{'avg3+draw' if use_draw else 'avg3':10s} test horses {len(pred)}  rho {rho:.3f}  predicted-top3-front actually top3 at 1st call {hits/n:.1%} (n {n})")
print(f"races {len(races)}, test from {cut}")
fit_eval(False); fit_eval(True)
