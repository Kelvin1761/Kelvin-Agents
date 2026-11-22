"""Kelvin 2026-11-22：(1) 大幅增程扣分補緊邊個維度嘅高估？(2) 休後復出：休幾耐、休後第幾仗。v5 校準殘差（計馬匹數）。"""
import sys, numpy as np
sys.argv = [sys.argv[0], sys.argv[1], "/dev/null"]
ns = {"__name__": "bp"}; exec(open("build_prep.py").read().split("nd1 = nprep = 0")[0], ns)
rows, runs, code_of, date = ns["rows"], ns["runs"], ns["code_of"], ns["date"]
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_replay_compare_v5 as v5
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
seasons = sorted({season(x["date"]) for x in rows})
par = {s: v5.fit([x for x in rows if season(x["date"]) < s and season(x["date"]) >= 2019]) for s in seasons if s >= 2020}
recs = []
for x in rows:
    s = season(x["date"])
    if s not in par: continue
    keep = [h for h in x["horses"] if h["pos"]]; n = len(keep)
    r = np.array([h["raw"] for h in keep]); rc = r - r.mean(); a, b, g = par[s]
    p = 1 / (1 + np.exp(-(a + b * rc + g * v5.field_logit(n))))
    sec = np.array([h["m"]["sectional"] for h in keep]); stab = np.array([h["m"]["stability"] for h in keep])
    for j, h in enumerate(keep):
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        prev = [t for t in runs.get(c, []) if t[0] < x["date"] and t[1]]
        if not prev: continue
        dist = x.get("distance")
        gap = (date.fromisoformat(x["date"]) - date.fromisoformat(prev[-1][0])).days
        # 休後第幾仗：由最近一次 ≥60 日空檔之後計（今仗計埋）
        k = 1 if gap >= 60 else None
        if k is None:
            k = 1
            for i in range(len(prev) - 1, 0, -1):
                k += 1
                if (date.fromisoformat(prev[i][0]) - date.fromisoformat(prev[i - 1][0])).days >= 60: break
            else:
                k = None   # 由出道起冇長休
        d1 = bool(dist and dist - prev[-1][1] >= 400)
        recs.append(dict(w="dev" if s <= 2023 else "hold", y=int(h["pos"] <= 3), p=p[j], d1=d1,
                         secrel=sec[j] - sec.mean(), stabrel=stab[j] - stab.mean(), gap=gap, k=k))
def show(lab, sel):
    out = []
    rng = np.random.default_rng(0)
    for w in ("dev", "hold"):
        v = np.array([r["y"] - r["p"] for r in recs if r["w"] == w and sel(r)])
        if len(v) < 30: out.append(f"n={len(v)}"); continue
        bt = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(400)]
        out.append(f"{100*v.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(v)}")
    print(f"{lab}｜dev {out[0]}｜holdout {out[1]}")
print("== (1) 大幅增程（live 已扣）按段速／狀態相對全場")
q = np.percentile([r["secrel"] for r in recs], [33, 67]); qs = np.percentile([r["stabrel"] for r in recs], [33, 67])
for lab, f in (("段速低三分一", lambda r: r["secrel"] < q[0]), ("段速中", lambda r: q[0] <= r["secrel"] < q[1]), ("段速高三分一", lambda r: r["secrel"] >= q[1])):
    show("D1＆" + lab, lambda r, f=f: r["d1"] and f(r)); show("非D1＆" + lab, lambda r, f=f: (not r["d1"]) and f(r))
for lab, f in (("狀態低三分一", lambda r: r["stabrel"] < qs[0]), ("狀態高三分一", lambda r: r["stabrel"] >= qs[1])):
    show("D1＆" + lab, lambda r, f=f: r["d1"] and f(r))
print("== (2) 休幾耐（今仗距上仗）")
for lo, hi in ((0, 13), (14, 21), (22, 35), (36, 59), (60, 120), (121, 180), (181, 365), (366, 9999)):
    show(f"休 {lo}–{hi} 日", lambda r, lo=lo, hi=hi: lo <= r["gap"] <= hi)
print("== (3) 休後第幾仗（長休 = ≥60 日）")
for k in (1, 2, 3, 4, 5):
    show(f"休後第 {k} 仗", lambda r, k=k: r["k"] == k)
show("休後第 6 仗或以上", lambda r: r["k"] is not None and r["k"] >= 6)
show("出道至今冇長休", lambda r: r["k"] is None)
print("== (4) 休後第 2 仗 × 長休有幾長（第 1 仗前嘅空檔）—— 粗略：第 1 仗 gap 分組")
for lo, hi in ((60, 120), (121, 365), (366, 9999)):
    show(f"休後第 1 仗、休 {lo}–{hi}", lambda r, lo=lo, hi=hi: r["k"] == 1 and lo <= r["gap"] <= hi)
