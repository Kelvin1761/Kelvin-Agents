"""(1) 靈敏度：明知有害（剷走維度貢獻 25／50／100%）—— Gold／Good 護欄 vs 場內 AUC，連 Δlog-loss。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import BASE, SCRIPTS, Bench, fmt  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
from au_matrix_refit import DIMS, MATRIX_WEIGHTS  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402

b = Bench()
print(f"baseline {BASE}｜計分場次 {len(b.scored)}、賽日 {b.ndays}")
dim = {}
for i in b.scored:
    m = [map_features_to_matrix_scores(x["features"]) for x in b.races[i]["rows"]]
    dim[i] = {k: np.round(np.array([s[k] for s in m]), 2) for k in DIMS}
m, lo, hi = b.run(lambda i, r: np.zeros(len(r["rows"])))
print(f"A/A｜Gold {fmt(m, lo, hi, 0)}｜Good {fmt(m, lo, hi, 1)}｜AUC×100 {fmt(m, lo, hi, 2)}")
for k in DIMS:
    w = MATRIX_WEIGHTS[k]
    for frac in (1.0, 0.5, 0.25):
        f = lambda i, r, k=k, w=w, frac=frac: -frac * w * (dim[i][k] - 60) if i in dim else np.zeros(len(r["rows"]))  # noqa: E731
        m, lo, hi = b.run(f)
        ll = b.logloss(f)
        good = "捉到" if min(lo[0], lo[1]) <= -1.0 else "捉唔到"
        print(f"剷 {k} {int(frac*100)}%（w {w:.3f}）｜Gold {fmt(m, lo, hi, 0)}｜Good {fmt(m, lo, hi, 1)}｜舊護欄{good}"
              f"｜AUC×100 {fmt(m, lo, hi, 2)}｜Δlog-loss {ll[0]:+.5f} [{ll[1]:+.5f},{ll[2]:+.5f}]", flush=True)
