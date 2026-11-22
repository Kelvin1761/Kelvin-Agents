"""頭二尺驗證：PL 全場 vs PL 爭勝馬（兩個模型頭四嘅聯集）vs 舊頭二選有中。
控制組（dev，base = live）：剷維度（明知有害）、同幅度雜訊、真候選。功效 = 效應 / CI 半闊（z）。"""
from collections import defaultdict
import numpy as np
from scipy.optimize import minimize_scalar
import top2_ruler as T
V = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history"
B = T.load(f"{V}/analysis/replay_all/v4/cons/base_live_20261122.jsonl")
keys = [k for k in sorted(B) if "2021-09-01" <= B[k]["date"] <= "2024-07-31" and T.ok_race(B[k])]
devk = [k for k in sorted(B) if "2020-09-01" <= B[k]["date"] <= "2024-07-31"]
def season(d): return T.season(d)
def contender_loss(r, pos, n_ids, cset, b):
    idx = [i for i, n in enumerate(n_ids) if n in cset]
    rr = r[idx]; pp = pos[idx]
    order = np.argsort(pp, kind="stable"); i1, i2 = order[0], order[1]
    z = b * (rr - rr.mean()); z -= z.max(); e = np.exp(z); s = e.sum()
    return -(np.log(e[i1] / s) + np.log(e[i2] / (s - e[i1])))
def prep(x, raws=None):
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]) if raws is None else raws
    return r, np.array([h["pos"] for h in hs]), [h["n"] for h in hs]
def picks(r, n_ids): return [n_ids[i] for i in np.argsort(-r, kind="stable")]
def fit_b(rows, kind):
    def f(b):
        t = 0.0
        for r, pos, ids, cset in rows:
            if kind == "all": t += T.pl_loss(r - r.mean(), pos, b)
            else: t += contender_loss(r, pos, ids, cset, b)
        return t
    return minimize_scalar(f, bounds=(0.0, 2.0), method="bounded").x
def evaluate(delta_fn):
    """delta_fn(x, n_ids) -> raw Δ for horses with pos. 返回三個指標嘅 (mean, lo, hi)。"""
    per = {"all": [], "cont": [], "hit2": []}; dates = []
    cache = {}
    # β：每季 walk-forward，baseline／候選各自（候選 Δ 已知所以可以 fit）
    for ts in (2021, 2022, 2023):
        tr = [k for k in devk if season(B[k]["date"]) < ts]
        rows_b, rows_c = [], []
        for k in tr:
            if not T.ok_race(B[k]): continue
            r, pos, ids = prep(B[k]); rc = r + delta_fn(B[k], ids)
            cset = set(picks(r, ids)[:4]) | set(picks(rc, ids)[:4])
            rows_b.append((r, pos, ids, cset)); rows_c.append((rc, pos, ids, cset))
        cache[ts] = {kind: (fit_b(rows_b, kind), fit_b(rows_c, kind)) for kind in ("all", "cont")}
    for k in keys:
        x = B[k]; ts = season(x["date"]); r, pos, ids = prep(x); rc = r + delta_fn(x, ids)
        cset = set(picks(r, ids)[:4]) | set(picks(rc, ids)[:4])
        (ba, ca), (bc_, cc) = cache[ts]["all"], cache[ts]["cont"]
        per["all"].append(T.pl_loss(rc - rc.mean(), pos, ca) - T.pl_loss(r - r.mean(), pos, ba))
        per["cont"].append(contender_loss(rc, pos, ids, cset, cc) - contender_loss(r, pos, ids, cset, bc_))
        top3 = {n for n, p in zip(ids, pos) if p <= 3}
        h = lambda rr: float(sum(n in top3 for n in picks(rr, ids)[:2]))   # 頭二入面入頭三幾多匹（0–2）
        per["hit2"].append(h(rc) - h(r)); dates.append(x["date"])
    days = sorted(set(dates)); byd = defaultdict(list)
    for i, d in enumerate(dates): byd[d].append(i)
    rng = np.random.default_rng(0); out = {}
    for kname, v in per.items():
        v = np.array(v); bs = [v[np.concatenate([byd[days[j]] for j in rng.integers(0, len(days), len(days))])].mean() for _ in range(600)]
        lo, hi = np.percentile(bs, [2.5, 97.5]); out[kname] = (v.mean(), lo, hi, v.mean() / ((hi - lo) / 3.92 + 1e-12))
    return out
def show(lab, o):
    s = "｜".join(f"{n} {m:+.4f} [{lo:+.4f},{hi:+.4f}] z={z:+.1f}" for n, (m, lo, hi, z) in o.items())
    print(f"{lab}｜{s}", flush=True)
C = lambda p: T.load(p)
def cand(path):
    Cd = T.load(path)
    def f(x, ids):
        c = Cd.get((x["meeting"], x["race"]))
        if not c: return np.zeros(len(ids))
        bh = {h["n"]: h["raw"] for h in x["horses"]}; ch = {h["n"]: h["raw"] for h in c["horses"]}
        return np.array([ch.get(n, bh[n]) - bh[n] for n in ids])
    return f
W = {"stability": 0.2451, "trainer_signal": 0.3296, "sectional": 0.1285, "race_shape": 0.1925}
def drop(dim, frac):
    def f(x, ids):
        m = {h["n"]: h["m"][dim] for h in x["horses"]}
        return np.array([-frac * W[dim] * (m[n] - 60) for n in ids])
    return f
print("（hit2 = 頭二入面入頭三嘅匹數差，負＝差咗；all／cont = PL 損失差，負＝好咗）")
show("J3", evaluate(cand(f"{V}/scratch/joint_plus/jl_J3.jsonl")))
show("剷騎練 25%", evaluate(drop("trainer_signal", 0.25)))
show("剷騎練 50%", evaluate(drop("trainer_signal", 0.5)))
show("剷檔位 50%", evaluate(drop("race_shape", 0.5)))
show("剷狀態 50%", evaluate(drop("stability", 0.5)))
jf = cand(f"{V}/scratch/joint_plus/jl_J3.jsonl"); rng2 = np.random.default_rng(5)
for i in range(3):
    show(f"J3 幅度雜訊 #{i+1}", evaluate(lambda x, ids: rng2.permutation(jf(x, ids))))
