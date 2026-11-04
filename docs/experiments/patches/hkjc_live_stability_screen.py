"""用存檔 Logic 入面 live 嘅 form_score／consistency_score／stability，對賽果量場內上名 AUC（< 2026-10-11）。"""
import json, re, sys, random
from collections import defaultdict
from pathlib import Path
import pandas as pd
sys.path[:0] = [sys.argv[3] + "/.agents/skills/shared_racing/scripts", sys.argv[3]]
from corpus_paths import logic_files
rows = pd.read_pickle(sys.argv[2]); rows = rows[rows["Rank"].notna()]
rows["Horse"] = rows["Horse"].astype(str).str.replace(r"\([A-Z]\d+\)$", "", regex=True).str.strip()
rank_of = {(r.Horse, str(r.Date)[:10]): float(r.Rank) for r in rows.itertuples()}
LIN = lambda r: 100 - (min(r, 12) - 1) * 60 / 11
recs = []
for lf in logic_files(sys.argv[1]):
    lf = Path(lf); m = re.match(r"(\d{4}-\d{2}-\d{2})", lf.parent.name); rn = re.search(r"Race_(\d+)_Logic", lf.name)
    if not m or not rn or m.group(1) >= "2026-10-11": continue
    try: lg = json.load(open(lf, encoding="utf-8"))
    except Exception: continue
    for h in (lg.get("horses") or {}).values():
        pa = (h or {}).get("python_auto") or {}; fs = pa.get("feature_scores") or {}; ms = pa.get("matrix_scores") or {}
        name = str(h.get("horse_name") or "").strip(); rk = rank_of.get((name, m.group(1)))
        if rk is None or "form_score" not in fs or any("debut" in str(c).lower() for c in pa.get("reason_codes") or []): continue
        fin = [int(x) for x in re.findall(r"\b\d+\b", str(h.get("last_6_finishes") or ""))[:6] if int(x) > 0]
        if len(fin) < 2: continue
        w = [1 / (i + 1) for i in range(len(fin))]
        recs.append(dict(date=m.group(1), race=f"{m.group(1)}_{rn.group(1)}", placed=0 < rk <= 3,
                         form=fs["form_score"], cons=fs.get("consistency_score", 60), stab=ms.get("stability", 60),
                         lin=sum(LIN(x) * a for x, a in zip(fin, w)) / sum(w)))
df = pd.DataFrame(recs).drop_duplicates(["race", "form", "cons", "lin"])
C = ["stab", "form", "cons", "lin"]
print(f"runners {len(df)} races {df.race.nunique()} meetings {df.date.nunique()}")
def ra(g, c):
    import numpy as np
    x = g[c].to_numpy(float); y = g.placed.to_numpy(bool)
    if y.all() or not y.any(): return 0.0, 0
    p, u = x[y], x[~y]; return float((p[:, None] > u[None, :]).sum() + .5 * (p[:, None] == u[None, :]).sum()), p.size * u.size
by = defaultdict(list)
for r, g in df.groupby("race"): by[g.date.iloc[0]].append({c: ra(g, c) for c in C})
def pooled(ds, c):
    n = d = 0.0
    for x in ds:
        for v in by[x]: n += v[c][0]; d += v[c][1]
    return n / d
ds = sorted(by); pt = {c: pooled(ds, c) for c in C}; rng = random.Random(5); bs = defaultdict(list)
for _ in range(1000):
    s = [rng.choice(ds) for _ in ds]; a = {c: pooled(s, c) for c in C}
    for c in C: bs[c].append(a[c] - a["stab"])
for c in C:
    xs = sorted(bs[c]); print(f"  {c:5s} {pt[c]:.4f}  Δ對live穩定性 {pt[c]-pt['stab']:+.4f} [{xs[25]:+.4f}, {xs[974]:+.4f}]")
for c in ("form", "cons", "lin"):
    print(f"  ρ({c}, stab) = {df.groupby('race').apply(lambda g: g[c].rank().corr(g['stab'].rank())).mean():+.3f}")
