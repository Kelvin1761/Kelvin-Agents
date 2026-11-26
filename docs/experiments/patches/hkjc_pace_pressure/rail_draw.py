"""跑馬地／沙田 各賽道欄位 × 檔位段：上名率（6 季），同 live 回放模型殘差（v5 校準 walk-forward）。"""
import json, sys, ast, re
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
idx = b.load_index()
meta = {}
for (d, n), v in idx["results"].items():
    hdr = v.get("_header") or {}
    if isinstance(hdr, str): hdr = ast.literal_eval(hdr)
    course = v.get("course") or hdr.get("Course") or ""
    m = re.search(r'"([A-C](?:\+\d)?)"', course)
    rail = m.group(1) if m else ("AWT" if "全天候" in course else "?")
    draws = {}
    for row in (v["results"] if isinstance(v["results"], list) else []):
        try: draws[str(row.get("horse_no"))] = int(row.get("draw"))
        except (TypeError, ValueError): pass
    meta[(d, int(n))] = (rail, draws)
band = lambda dr: "內1–4" if dr <= 4 else ("中5–8" if dr <= 8 else "外9+")
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def feats(x):
    hs = [h for h in x["horses"] if h["pos"]]; r = np.array([h["raw"] for h in hs]); N = len(hs)
    return hs, r - r.mean(), np.full(N, np.log(3/(N-3)) if N > 3 else 0.0)
cal = {}
for s in sorted(by):
    if s < 2020: continue
    X, Y = [], []
    for t in by:
        if 2019 <= t < s:
            for x in by[t]:
                hs, dd, l = feats(x); X += list(zip(dd, l)); Y += [int(h["pos"] <= 3) for h in hs]
    cal[s] = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X), Y)
cell = defaultdict(list)
for x in rows:
    s = season(x["date"])
    if s not in cal: continue
    rail, draws = meta.get((x["date"], x["race"]), ("?", {}))
    hs, dd, l = feats(x); p = cal[s].predict_proba(np.column_stack([dd, l]))[:, 1]
    win = "dev" if s <= 2023 else "ho"
    dist = "短≤1200" if x["distance"] <= 1200 else "長"
    for h, pi in zip(hs, p):
        dr = draws.get(str(h["n"]))
        if not dr: continue
        cell[(x["venue"], rail, dist, band(dr), win)].append((int(h["pos"] <= 3), pi, x["date"]))
rng = np.random.default_rng(0)
def summ(v):
    y = np.array([a for a, _, _ in v]); p = np.array([b_ for _, b_, _ in v])
    bt = [np.mean((y - p)[rng.integers(0, len(y), len(y))]) for _ in range(500)]
    return 100*y.mean(), 100*(y-p).mean(), 100*np.percentile(bt, 2.5), 100*np.percentile(bt, 97.5), len(y)
for venue in ("跑馬地", "沙田"):
    rails = sorted({k[1] for k in cell if k[0] == venue})
    for rail in rails:
        for dist in ("短≤1200", "長"):
            ln = []
            for bd in ("內1–4", "中5–8", "外9+"):
                v = cell.get((venue, rail, dist, bd, "dev"), []) + cell.get((venue, rail, dist, bd, "ho"), [])
                if len(v) < 150: ln.append(f"{bd} n={len(v)}"); continue
                a, r_, lo, hi, n = summ(v)
                vd = cell.get((venue, rail, dist, bd, "dev"), []); vh = cell.get((venue, rail, dist, bd, "ho"), [])
                rd = 100*np.mean([y-p for y, p, _ in vd]) if vd else float('nan'); rh = 100*np.mean([y-p for y, p, _ in vh]) if vh else float('nan')
                ln.append(f"{bd} 上名{a:.0f}% 殘差{r_:+.1f}[{lo:+.1f},{hi:+.1f}](dev{rd:+.1f}/ho{rh:+.1f}) n={n}")
            print(f"{venue} {rail:<4} {dist:<6} | " + " | ".join(ln))
