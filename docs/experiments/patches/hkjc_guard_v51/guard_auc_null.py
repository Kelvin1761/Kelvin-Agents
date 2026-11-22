# ruff: noqa: F821  （exec 上一個腳本嘅變數）
import numpy as np
exec(open(__import__("os").path.join(__import__("os").path.dirname(__file__), "guard_auc.py")).read().split('print("== 靈敏度')[0])
J1 = load(f"{V}/analysis/replay_all/v4/joint_J1.jsonl"); D1 = load(f"{V}/analysis/replay_all/v4/dist_D1.jsonl")
def j1d(x):
    a, b0 = J1.get((x["meeting"], x["race"])), D1.get((x["meeting"], x["race"]))
    if not a or not b0: return np.zeros(len(x["horses"]))
    ah = {h["n"]: h["raw"] for h in a["horses"]}; bh = {h["n"]: h["raw"] for h in b0["horses"]}
    return np.array([ah.get(h["n"], 0) - bh.get(h["n"], 0) for h in x["horses"]])
for scale in (1.0, 2.0):
    lows = []; pts = []
    for _ in range(30):
        def shuf(x):
            d = j1d(x) * scale; keep = np.array([bool(h["pos"]) for h in x["horses"]]); d2 = d.copy(); d2[keep] = rng.permutation(d[keep]); return d2
        m, lo, hi = evaluate2(shuf); lows.append(lo); pts.append(m)
    lows, pts = np.array(lows), np.array(pts)
    for thr in (-0.10, -0.15, -0.20):
        print(f"J1 幅度×{scale} 洗牌：AUC 下界 ≤ {thr} 誤殺 {(lows[:,2] <= thr).sum()}/30｜點估計 Gold/Good ≤ −1.0 誤殺 {((pts[:,0] <= -1) | (pts[:,1] <= -1)).sum()}/30｜AUC 下界中位 {np.median(lows[:,2]):+.3f}")
