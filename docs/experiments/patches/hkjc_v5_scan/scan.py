"""Kelvin 2026-11-22「模型有冇系統性高估／低估」：v5 校準（逐季 walk-forward，計馬匹數）殘差全面掃描。只做診斷。"""
import json, sys
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_replay_compare_v5 as v5
import hkjc_history_replay_build as b
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
idx = b.load_index()
cls = {}
for (d, n), race in idx["results"].items():
    c = str((race.get("_header") or {}).get("RaceClass") or "")
    cls[(d, n)] = c
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
par = {s: v5.fit([x for x in rows if 2019 <= season(x["date"]) < s]) for s in sorted({season(x["date"]) for x in rows}) if s >= 2020}
recs = []
DIMS = ["stability", "trainer_signal", "sectional", "race_shape", "horse_health", "form_line"]
LEAVES = ["form_score", "speed_score", "jockey_score", "trainer_score", "consistency_score", "weight_score", "class_score", "risk_score"]
for x in rows:
    s = season(x["date"])
    if s not in par: continue
    keep = [h for h in x["horses"] if h["pos"]]; n = len(keep)
    r = np.array([h["raw"] for h in keep]); rc = r - r.mean(); a, bb, g = par[s]
    p = 1 / (1 + np.exp(-(a + bb * rc + g * v5.field_logit(n))))
    rank = (-r).argsort().argsort() + 1
    rel = {k: np.array([h["m"][k] for h in keep]) for k in DIMS}
    rel.update({k: np.array([h["f"][k] for h in keep]) for k in LEAVES})
    rel = {k: v - v.mean() for k, v in rel.items()}
    dist = x.get("distance") or 0
    grp = ("谷草" if x["venue"] == "跑馬地" else ("泥地" if x.get("awt") else "田草")) + ("短途" if dist <= 1200 else ("一哩" if dist <= 1650 else "中長途"))
    c = cls.get((x["date"], x["race"]), "")
    for j, h in enumerate(keep):
        recs.append(dict(w="dev" if s <= 2023 else "hold", y=int(h["pos"] <= 3), p=p[j], rank=rank[j], n=n, debut=h.get("debut"),
                         grp=grp, cls=c, **{k: rel[k][j] for k in rel}))
print("馬次", len(recs))
rng = np.random.default_rng(0)
def show(lab, sel, flag=True):
    out = []; ms = []
    for w in ("dev", "hold"):
        v = np.array([r["y"] - r["p"] for r in recs if r["w"] == w and sel(r)])
        if len(v) < 50: out.append(f"n={len(v)}"); ms.append(None); continue
        bt = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(300)]
        lo, hi = np.percentile(bt, [2.5, 97.5]); ms.append((v.mean(), lo, hi))
        out.append(f"{100*v.mean():+.1f}[{100*lo:+.1f},{100*hi:+.1f}] n={len(v)}")
    both = all(m and ((m[1] > 0) or (m[2] < 0)) for m in ms) and ms[0] and ms[1] and np.sign(ms[0][0]) == np.sign(ms[1][0])
    print(("★ " if both else "  ") + f"{lab}｜dev {out[0]}｜holdout {out[1]}")
print("== 模型排名（校準係咪頭重尾輕）")
for k in (1, 2, 3, 4, 5, 6): show(f"模型排第 {k}", lambda r, k=k: r["rank"] == k)
show("模型排第 7–9", lambda r: 7 <= r["rank"] <= 9); show("模型排第 10+", lambda r: r["rank"] >= 10)
print("== 預測機率分段（可靠度）")
for lo, hi in ((0, .1), (.1, .2), (.2, .3), (.3, .45), (.45, .6), (.6, 1)): show(f"p {lo:.2f}–{hi:.2f}", lambda r, lo=lo, hi=hi: lo <= r["p"] < hi)
print("== 維度／細項相對全場：高三分一 vs 低三分一")
for k in DIMS + LEAVES:
    q = np.percentile([r[k] for r in recs], [33, 67])
    if q[0] == q[1]: continue
    show(f"{k} 高", lambda r, k=k, q=q: r[k] >= q[1]); show(f"{k} 低", lambda r, k=k, q=q: r[k] < q[0])
print("== 場地路程組")
for gname in sorted({r["grp"] for r in recs}): show(gname, lambda r, gname=gname: r["grp"] == gname)
print("== 班次")
for cname in sorted({r["cls"] for r in recs}): show(cname or "（冇）", lambda r, cname=cname: r["cls"] == cname)
print("== 馬匹數")
for lo, hi in ((4, 8), (9, 11), (12, 13), (14, 14)): show(f"{lo}–{hi} 匹", lambda r, lo=lo, hi=hi: lo <= r["n"] <= hi)
show("初出馬", lambda r: r["debut"])
