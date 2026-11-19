"""Kelvin 2026-11-19「檔位計兩次」直接量度（只做診斷）。
綜合分有兩部分講檔位：維度「檔位與走位」（權重 0.1925）＋後置「檔位×跑法」（draw_style，跑法格＋逐檔格）。
問：兩部分喺模型入面嘅實際份量，係咪大過佢哋應得嘅？
做法：
  1. base（現行 live）嘅 raw 減走 live 凍結 draw_style 值（凍結格用晒 2026-11-11 前全部回放 → 舊季係 in-sample）。
  2. 用 build.py 同一套格（跑法 × 檔位段、逐檔）逐季 walk-forward（只用之前季殘差＋β）加返樣本外 DS。
  3. 每場置中後拆：RS = 0.1925·(檔位與走位 − 場均)、DS、OTHER = 其餘；logit(入頭三) ~ OTHER + RS + DS（dev／holdout 各自 fit）。
     RS／OTHER、DS／OTHER 嘅係數比 = 1 → 份量啱；< 1 → 計多咗；> 1 → 計少咗。按賽日 bootstrap。
用法：python3 diag_draw_double.py <base.jsonl>
"""
import json, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
K = 200
FZ = json.load(open("/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_wong_choi_auto/resources/hkjc_draw_style.json"))
W_RS = 0.1925
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def grp(x):
    g = "HV" if x["venue"] == "跑馬地" else ("AWT" if x["awt"] else ("STR" if x["distance"] == 1000 else "ST"))
    return g + ("S" if x["distance"] <= 1200 else "L")

import hkjc_history_replay_pit as p
df = p.load_all_rows_extended(); df = df[df["Rank"].notna()].copy()
df["d"] = df["Date"].astype(str).str[:10]; df = df.sort_values("d")
df["F"] = df.groupby(["d", "RaceNo"])["Rank"].transform("count")
hist = defaultdict(list); info = defaultdict(list)
for r in df.itertuples():
    h = hist[r.HorseID]; sty = np.mean(h[-6:]) if len(h) >= 2 else None
    info[(r.d, int(r.RaceNo), int(r.Rank))].append((sty, r.Draw))
    rp = str(r.RunningPos or "").split()
    if rp and rp[0].isdigit() and r.F: h.append(int(rp[0]) / r.F)
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x and x.get("distance")]
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def cells(x):
    F = sum(1 for h in x["horses"] if h["pos"]); sc, dc = [], []
    for h in x["horses"]:
        i = info.get((x["date"], x["race"], h["pos"])) if h["pos"] else None
        if not i or len(i) != 1 or i[0][1] != i[0][1]: sc.append(None); dc.append(None); continue
        sty, d = i[0]
        st = "U" if sty is None else ("F" if sty <= 0.3 else ("M" if sty <= 0.6 else "B"))
        db = "I" if d <= 4 else ("C" if d <= 9 else "O")
        sc.append((grp(x), st, db)); dc.append((grp(x), min(int(d), 13), F >= 12))
    return sc, dc
cache = {id(x): cells(x) for x in rows}
# 1. 減走凍結值
def frozen_delta(x):
    sc, dc = cache[id(x)]
    v1 = np.array([FZ["style_cells"].get(f"{c[0]}|{c[1]}|{c[2]}", 0.0) if c else 0.0 for c in sc])
    v2 = np.array([FZ["curve_cells"].get(f"{c[0]}|{c[1]}|{int(c[2])}", 0.0) if c else 0.0 for c in dc])
    return FZ["beta_style"] * (v1 - v1.mean()) + FZ["beta_curve"] * (v2 - v2.mean())
NODS = {id(x): np.array([h["raw"] for h in x["horses"]]) - frozen_delta(x) for x in rows}
hit = sum(1 for x in rows for c in cache[id(x)][0] if c and f"{c[0]}|{c[1]}|{c[2]}" in FZ["style_cells"])
print("凍結格配對到嘅馬次", hit, "／", sum(1 for x in rows for c in cache[id(x)][0] if c), flush=True)
# 2. walk-forward 格＋β（同 build.py SD）
def calib(races):
    X, Y = [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]; r = NODS[id(x)]
        X += list((r - r.mean())[keep]); Y += [x["horses"][i]["pos"] <= 3 for i in keep]
    m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
    return m.intercept_[0], m.coef_[0][0]
seasons = sorted(by); resid = {}
for s in seasons:
    a, b = calib([x for t in by if t < s for x in by[t]] or by[s])
    acc = [defaultdict(lambda: [0.0, 0]), defaultdict(lambda: [0.0, 0])]
    for x in by[s]:
        r = NODS[id(x)]; rc = r - r.mean(); sc, dc = cache[id(x)]
        for h, z, c1, c2 in zip(x["horses"], rc, sc, dc):
            if h["pos"] and c1:
                e = float(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z)))
                acc[0][c1][0] += e; acc[0][c1][1] += 1; acc[1][c2][0] += e; acc[1][c2][1] += 1
    resid[s] = acc
def table(s, j):
    acc = defaultdict(lambda: [0.0, 0])
    for t in seasons:
        if t < s:
            for c, (sm, n) in resid[t][j].items(): acc[c][0] += sm; acc[c][1] += n
    return {c: sm / (n + K) for c, (sm, n) in acc.items()}
tabs = {s: (table(s, 0), table(s, 1)) for s in seasons}
def feats(x):
    sc, dc = cache[id(x)]; t1, t2 = tabs[season(x["date"])]
    v1 = np.array([t1.get(c, 0.0) if c else 0.0 for c in sc]); v2 = np.array([t2.get(c, 0.0) if c else 0.0 for c in dc])
    return v1 - v1.mean(), v2 - v2.mean()
def fitb(races):
    R, Z1, Z2, Y = [], [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]; r = NODS[id(x)]; f1, f2 = feats(x)
        R.append((r - r.mean())[keep]); Z1.append(f1[keep]); Z2.append(f2[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z1, Z2 = map(np.concatenate, (R, Z1, Z2))
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z1 / Z1.std(), Z2 / Z2.std()]), Y).coef_[0]
    return (c[1] / Z1.std()) / (c[0] / R.std()), (c[2] / Z2.std()) / (c[0] / R.std())
betas = {s: fitb([x for t in by if 2020 <= t < s for x in by[t]]) for s in seasons if s >= 2021}
print("walk-forward β（跑法格, 逐檔格）", {s: (round(float(a), 1), round(float(b), 1)) for s, (a, b) in betas.items()},
      "｜凍結", round(FZ["beta_style"], 1), round(FZ["beta_curve"], 1), flush=True)
# 3. 拆分＋係數比
recs = defaultdict(list)   # window -> [(day, other, rs, ds, y)]
for x in rows:
    s = season(x["date"]); bb = betas.get(s)
    if bb is None or s > 2025: continue
    win = "dev" if s <= 2023 else "holdout"
    f1, f2 = feats(x); ds = f1 * bb[0] + f2 * bb[1]
    raw = NODS[id(x)] + ds
    rsm = np.array([float(h["m"].get("race_shape") or 60) for h in x["horses"]]); rs = W_RS * (rsm - rsm.mean())
    tot = raw - raw.mean(); other = tot - rs - ds
    for i, h in enumerate(x["horses"]):
        if h["pos"]: recs[win].append((x["date"], other[i], rs[i], ds[i], int(h["pos"] <= 3)))
rng = np.random.default_rng(0)
def ratios(rr):
    X = np.array([[o, r, d] for _, o, r, d, _ in rr]); Y = np.array([y for *_, y in rr])
    c = LogisticRegression(C=1e6, max_iter=5000).fit(X, Y).coef_[0]
    return c[1] / c[0], c[2] / c[0], c[0]
for win, rr in recs.items():
    base = ratios(rr)
    days = sorted({r[0] for r in rr}); byd = defaultdict(list)
    for r in rr: byd[r[0]].append(r)
    bs = []
    for _ in range(300):
        pick = rng.choice(len(days), len(days)); sample = [r for k in pick for r in byd[days[k]]]
        bs.append(ratios(sample)[:2])
    bs = np.array(bs)
    sd = {k: float(np.std([r[i] for r in rr])) for k, i in (("OTHER", 1), ("RS", 2), ("DS", 3))}
    print(f"{win}（{len(rr)} 匹、{len(days)} 日）：檔位與走位 / 其餘 = {base[0]:.2f} [{np.percentile(bs[:,0],2.5):.2f},{np.percentile(bs[:,0],97.5):.2f}]｜"
          f"檔位×跑法 / 其餘 = {base[1]:.2f} [{np.percentile(bs[:,1],2.5):.2f},{np.percentile(bs[:,1],97.5):.2f}]｜SD raw：其餘 {sd['OTHER']:.2f}、維度 {sd['RS']:.2f}、檔位×跑法 {sd['DS']:.2f}")
