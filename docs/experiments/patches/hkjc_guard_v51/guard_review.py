"""護欄檢討（Kelvin 2026-11-22）：v5 尺嘅 Gold／Good 護欄（95% CI 下界 > −1.0pp）
(1) 誤殺率：冇資訊嘅改動（候選 raw Δ 喺場內隨機洗牌，同幅度）有幾成會被護欄判死？
(2) 靈敏度：明知有害嘅改動（剷走核心維度）護欄捉唔捉到？
dev 窗、按賽日 bootstrap 1,000。"""
import json, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing/scripts")
from eval_metrics import race_metrics
V = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history"
BASE = f"{V}/analysis/replay_all/v4/cons/base_venue_age.jsonl"
def load(p): return {(x["meeting"], x["race"]): x for x in map(json.loads, open(p)) if "horses" in x}
B = load(BASE)
keys = [k for k in sorted(B) if "2021-09-01" <= B[k]["date"] <= "2024-07-31"
        and sum(1 for h in B[k]["horses"] if h["pos"] and h["pos"] <= 3) >= 3]
rng = np.random.default_rng(1)
def metrics(x, raws):
    hs = [h for h in x["horses"]]; ns = np.array([h["n"] for h in hs])
    picks = [int(v) for v in ns[np.lexsort((ns, -np.asarray(raws)))]]
    pos = {h["n"]: h["pos"] for h in hs if h["pos"]}; top = [n for n, p in pos.items() if p <= 3]
    m = race_metrics(picks, top, actual_pos=pos); return float(m["gold"]), float(m["good_positional"])
base_m = {k: metrics(B[k], [h["raw"] for h in B[k]["horses"]]) for k in keys}
days = sorted({B[k]["date"] for k in keys}); by_day = defaultdict(list)
for i, k in enumerate(keys): by_day[B[k]["date"]].append(i)
def ci(D, nb=1000):
    bs = []
    for _ in range(nb):
        ii = np.concatenate([by_day[days[j]] for j in rng.integers(0, len(days), len(days))]); bs.append(D[ii].mean(0))
    bs = np.array(bs); return D.mean(0) * 100, np.percentile(bs, 2.5, axis=0) * 100, np.percentile(bs, 97.5, axis=0) * 100
def evaluate(delta_fn):
    D = []
    for k in keys:
        x = B[k]; raws = np.array([h["raw"] for h in x["horses"]]) + delta_fn(x)
        g, gd = metrics(x, raws); D.append((g - base_m[k][0], gd - base_m[k][1]))
    return ci(np.array(D))
def cand_delta(path):
    C = load(path)
    def f(x):
        c = C.get((x["meeting"], x["race"]))
        if not c: return np.zeros(len(x["horses"]))
        ch = {h["n"]: h["raw"] for h in c["horses"]}
        return np.array([ch.get(h["n"], h["raw"]) - h["raw"] for h in x["horses"]])
    return f, C
print("== (1) 誤殺率：冇資訊改動（真候選嘅 raw Δ 場內洗牌）")
for name, path in (("A2 馬齡", f"{V}/scratch/samedist_venue/age_A2.jsonl"), ("R1 同程差過整體", f"{V}/scratch/samedist_rel/c_R1.jsonl"),
                   ("K1 同程高班", f"{V}/scratch/samedist_rel/k_K1.jsonl"), ("N3 增程 200", f"{V}/scratch/dist_territory/cand_N3.jsonl")):
    f, C = cand_delta(path)
    fails = {"Gold": 0, "Good": 0, "任一": 0}; los = []; NN = 40
    for _ in range(NN):
        def shuf(x, f=f):
            d = f(x); keep = np.array([bool(h["pos"]) for h in x["horses"]]); d2 = d.copy(); d2[keep] = rng.permutation(d[keep]); return d2
        m, lo, hi = evaluate(shuf); los.append(lo)
        fails["Gold"] += lo[0] <= -1.0; fails["Good"] += lo[1] <= -1.0; fails["任一"] += (lo[0] <= -1.0) or (lo[1] <= -1.0)
    los = np.array(los)
    print(f"{name}：洗牌 {NN} 次｜Gold 下界中位 {np.median(los[:,0]):+.2f}、Good 下界中位 {np.median(los[:,1]):+.2f}｜護欄誤殺 Gold {fails['Gold']}/{NN}、Good {fails['Good']}/{NN}、任一 {fails['任一']}/{NN}")
print("== (2) 靈敏度：明知有害（剷走維度貢獻）")
W = {"stability": 0.2451, "trainer_signal": 0.3296, "sectional": 0.1285, "race_shape": 0.1925}
for dim, w in W.items():
    for frac in (1.0, 0.5):
        m, lo, hi = evaluate(lambda x, dim=dim, w=w, frac=frac: -frac * w * (np.array([h["m"][dim] for h in x["horses"]]) - 60))
        print(f"剷走 {dim} {int(frac*100)}%：Gold {m[0]:+.2f} [{lo[0]:+.2f},{hi[0]:+.2f}]｜Good {m[1]:+.2f} [{lo[1]:+.2f},{hi[1]:+.2f}]｜護欄{'捉到' if min(lo) <= -1.0 else '捉唔到'}")
