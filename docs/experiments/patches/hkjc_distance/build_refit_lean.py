"""EXP-20261117-07（Kelvin Q1）：
  R1  現行模型外層權重修正：raw' = raw + Σ γ_k·(維度分_k − 場均)，9 個維度，L2 C=0.1，逐季 walk-forward（2019/20 起只用之前季）。
      即係加晒新組件（事件報告、檔位×跑法、大幅增程）之後，原本 9 個維度權重要唔要再調。base = dist_D1（live）。預先登記，dev 過先開 holdout。
  JL  J1 精簡版（ablation 揀：剷走匆匆再出、受阻、大幅減程、首次配備）→ 只計 2026/27 β 俾 forward shadow，唔做回放判決（holdout 已用過）。
用法：python3 build_refit_lean.py <dist_D1.jsonl> <old_incidents.json> <out_prefix>
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_joint as B  # noqa: E402

DIMS = ["stability", "trainer_signal", "sectional", "race_shape", "horse_health", "trackwork", "distance_fit", "form_line", "class_advantage"]
LEAN = [k for k in B.NAMES if k not in ("backup10", "blocked2", "dist_down", "gear_on")]


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    by = defaultdict(list)
    for x in rows:
        by[B.season(x["date"])].append(x)
    M = {}
    for x in rows:
        m = np.array([[float((h.get("m") or {}).get(k, 60.0) or 60.0) for k in DIMS] for h in x["horses"]])
        M[id(x)] = m - m.mean(axis=0)

    def fit(races, X, cols=None):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            z = X[id(x)] if cols is None else X[id(x)][:, cols]
            R.append((r - r.mean())[keep]); Z.append(z[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z = np.concatenate(R), np.vstack(Z)
        sd = Z.std(axis=0); sd[sd == 0] = 1
        c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / R.std(), Z / sd]), Y).coef_[0]
        return (c[1:] / sd) / (c[0] / R.std())
    gam = {s: fit([x for t in by if 2019 <= t < s for x in by[t]], M) for s in sorted(by) if s >= 2020}
    for s, g in gam.items():
        print("R1", s, {k: round(float(v), 3) for k, v in zip(DIMS, g)}, flush=True)
    with open(f"{sys.argv[3]}_R1.jsonl", "w") as f:
        for x in rows:
            g = gam.get(B.season(x["date"]))
            y = dict(x, arm="refit_R1")
            if g is not None:
                new = np.array([h["raw"] for h in x["horses"]]) + M[id(x)] @ g
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
    # JL：2026/27 β（fit 2019/20–2025/26）
    inc = B.load_runs(sys.argv[2])
    code_of = {(d, n, hn): c for c, v in inc.items() for d, n, _, hn in v}
    pages, _ = B.F.load()
    pidx = {c: {q["d"]: i for i, q in enumerate(rr)} for c, rr in pages.items()}
    X = {}
    for x in rows:
        mat = []
        for h in x["horses"]:
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            fz = dict.fromkeys(B.NAMES, 0.0)
            if c:
                fz.update(B.inc_feats([v for v in inc[c] if v[0] < x["date"]]))
                i = pidx.get(c, {}).get(x["date"])
                if i is not None:
                    fz.update(B.page_feats(pages[c], i))
            mat.append([fz[k] for k in LEAN])
        m = np.array(mat, dtype=float)
        X[id(x)] = m - m.mean(axis=0)
    b = fit([x for t in by if 2019 <= t < max(by) for x in by[t]], X)
    print("JL 2026/27 β", {k: round(float(v), 2) for k, v in zip(LEAN, b)})


if __name__ == "__main__":
    main()
