# ruff: noqa: F821  （exec 上一個腳本嘅變數）
"""護欄檢討第二部分：場內 AUC 做護欄 —— 靈敏度（剷維度）同誤殺率（J1 幅度洗牌）；同時報 Good 對照。"""
import numpy as np
exec(open(__import__("os").path.join(__import__("os").path.dirname(__file__), "guard_review.py")).read().split('print("== (1)')[0])
def auc_race(x, raws):
    hs = [(r, h) for r, h in zip(raws, x["horses"]) if h["pos"]]
    pos = [r for r, h in hs if h["pos"] <= 3]; neg = [r for r, h in hs if h["pos"] > 3]
    if not pos or not neg: return 0.5
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))
base_a = {k: auc_race(B[k], [h["raw"] for h in B[k]["horses"]]) for k in keys}
def evaluate2(delta_fn):
    D = []
    for k in keys:
        x = B[k]; raws = np.array([h["raw"] for h in x["horses"]]) + delta_fn(x)
        g, gd = metrics(x, raws); D.append((g - base_m[k][0], gd - base_m[k][1], auc_race(x, raws) - base_a[k]))
    return ci(np.array(D), 600)
print("== 靈敏度（剷走維度）：AUC vs Good")
for dim, w in (("stability", 0.2451), ("trainer_signal", 0.3296), ("sectional", 0.1285), ("race_shape", 0.1925)):
    for frac in (0.5, 0.25):
        m, lo, hi = evaluate2(lambda x, dim=dim, w=w, frac=frac: -frac * w * (np.array([h["m"][dim] for h in x["horses"]]) - 60))
        print(f"剷 {dim} {int(frac*100)}%｜Good {m[1]:+.2f} [{lo[1]:+.2f},{hi[1]:+.2f}]｜AUC×100 {m[2]:+.3f} [{lo[2]:+.3f},{hi[2]:+.3f}]")
print("== J1 幅度：真 J1 Δ（v4 joint_J1 對 dist_D1）同洗牌")
J1 = load(f"{V}/analysis/replay_all/v4/joint_J1.jsonl"); D1 = load(f"{V}/analysis/replay_all/v4/dist_D1.jsonl")
def j1d(x):
    a, b0 = J1.get((x["meeting"], x["race"])), D1.get((x["meeting"], x["race"]))
    if not a or not b0: return np.zeros(len(x["horses"]))
    ah = {h["n"]: h["raw"] for h in a["horses"]}; bh = {h["n"]: h["raw"] for h in b0["horses"]}
    return np.array([ah.get(h["n"], 0) - bh.get(h["n"], 0) for h in x["horses"]])
m, lo, hi = evaluate2(j1d); print(f"真 J1 Δ 套落現 base｜Gold {m[0]:+.2f} [{lo[0]:+.2f},{hi[0]:+.2f}]｜Good {m[1]:+.2f} [{lo[1]:+.2f},{hi[1]:+.2f}]｜AUC×100 {m[2]:+.3f} [{lo[2]:+.3f},{hi[2]:+.3f}]")
fails = [0, 0, 0]; NN = 30
for _ in range(NN):
    def shuf(x):
        d = j1d(x); keep = np.array([bool(h["pos"]) for h in x["horses"]]); d2 = d.copy(); d2[keep] = rng.permutation(d[keep]); return d2
    m, lo, hi = evaluate2(shuf)
    fails[0] += lo[0] <= -1.0; fails[1] += lo[1] <= -1.0; fails[2] += (lo[0] <= -1.0) or (lo[1] <= -1.0)
print(f"J1 幅度洗牌 {NN} 次：Gold 誤殺 {fails[0]}、Good 誤殺 {fails[1]}、任一 {fails[2]}")
