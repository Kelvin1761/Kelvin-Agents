"""HKJC 段速 leaf 篩選（唔係 A/B）：上仗 L400 絕對值（現行）vs 標準化／近 6 仗加權。

來源：每個賽日 Facts「完整賽績檔案（近 6 場）」（賽前資料）。cell = (場地, 路程)，cell 平均
只用目標賽日之前嘅往績（PIT），每個 cell 要 ≥30 個觀測。目標窗 < 2026-10-11（forward holdout 唔用）。
"""
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(sys.argv[1]); rows = pd.read_pickle(sys.argv[2])
rows = rows[rows["Rank"].notna()]
rows["Horse"] = rows["Horse"].astype(str).str.replace(r"\([A-Z]\d+\)$", "", regex=True).str.strip()
rank_of = {(r.Horse, str(r.Date)[:10]): float(r.Rank) for r in rows.itertuples()}
NUM = re.compile(r"\d{2}\.\d{1,2}")
AU_W = (1.0, 0.8, 0.6, 0.4, 0.3, 0.2)


def parse_facts(path):
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^### 馬號 (\d+) — (\S+)", text, flags=re.M)
    out = {}
    for i in range(1, len(parts), 3):
        name, block = parts[i + 1], parts[i + 2]
        if "完整賽績檔案" not in block:
            continue
        cols, runs = None, []
        for line in block.split("完整賽績檔案", 1)[1].splitlines()[1:]:
            if cols is not None and not line.strip().startswith("|"):
                break
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if c and c[0] == "#":
                cols = {k: j for j, k in enumerate(c)}
                continue
            if cols and c and c[0].isdigit() and "L400" in cols and len(c) > cols["L400"]:
                l4 = c[cols["L400"]]
                d = re.match(r"(\d{2})/(\d{2})/(\d{4})", c[cols.get("日期", 1)])
                if not d:
                    continue
                runs.append(dict(date=f"{d.group(3)}-{d.group(2)}-{d.group(1)}",
                                 cell=(c[cols.get("場地", 2)], c[cols.get("距離", 3)]),
                                 l4=float(l4) if NUM.fullmatch(l4) else None))
        out[name.strip()] = runs
    return out


targets, allruns = [], {}
for meet in sorted(p for p in ROOT.iterdir() if p.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}_", p.name)):
    date = meet.name[:10]
    if date >= "2026-10-11":
        continue
    for facts in sorted(meet.glob("* Race * Facts.md")):
        rn = re.search(r"Race (\d+) Facts", facts.name).group(1)
        logic = meet / f"Race_{rn}_Logic.json"
        speed = {}
        if logic.exists():
            try:
                for h in json.load(open(logic, encoding="utf-8")).get("horses", {}).values():
                    fs = (h.get("python_auto") or {}).get("feature_scores") or {}
                    if "speed_score" in fs:
                        speed[str(h.get("horse_name") or "").strip()] = float(fs["speed_score"])
            except Exception:
                pass
        for name, runs in parse_facts(facts).items():
            rk = rank_of.get((name, date))
            if rk is None:
                continue
            past = [r for r in runs if r["date"] < date]
            for r in past:
                if r["l4"] is not None:
                    allruns[(name, r["date"])] = r
            targets.append(dict(date=date, race=f"{date}_{rn}", horse=name, placed=0 < rk <= 3,
                                runs=past, speed=speed.get(name)))
print(f"targets {len(targets)}  unique past runs with L400 {len(allruns)}")

# PIT cell means: for a target date, average of runs with run date < target date
runs_by_date = sorted(allruns.values(), key=lambda r: r["date"])
cell_stats_at = {}
sums = defaultdict(lambda: [0.0, 0]); j = 0
for date in sorted({t["date"] for t in targets}):
    while j < len(runs_by_date) and runs_by_date[j]["date"] < date:
        r = runs_by_date[j]; sums[r["cell"]][0] += r["l4"]; sums[r["cell"]][1] += 1; j += 1
    cell_stats_at[date] = {k: v[0] / v[1] for k, v in sums.items() if v[1] >= 30}

recs = []
for t in targets:
    means = cell_stats_at[t["date"]]
    l = [r for r in t["runs"] if r["l4"] is not None][:6]
    if not l:
        continue
    norm = [(r["l4"] - means[r["cell"]]) if r["cell"] in means else None for r in l]
    if norm[0] is None:
        continue
    nv = [(x, w) for x, w in zip(norm, AU_W) if x is not None]
    recs.append(dict(race=t["race"], date=t["date"], placed=t["placed"], speed=t["speed"],
                     abs_last=-l[0]["l4"], norm_last=-norm[0],
                     abs_wavg=-sum(r["l4"] * w for r, w in zip(l, AU_W)) / sum(AU_W[:len(l)]),
                     norm_wavg=-sum(x * w for x, w in nv) / sum(w for _, w in nv),
                     norm_best=-min(x for x, _ in nv),
                     norm_wavg3=-sum(x * w for x, w in nv[:3]) / sum(w for _, w in nv[:3]),
                     n=len(nv)))
df = pd.DataFrame(recs)
CANDS = ["abs_last", "norm_last", "abs_wavg", "norm_wavg", "norm_wavg3", "norm_best"]
have_speed = df.speed.notna()
print(f"comparable runners {len(df)} races {df.race.nunique()} meetings {df.date.nunique()} "
      f"| speed_score present {have_speed.mean():.1%}  | median runs used {df.n.median():.0f}")


def race_auc(g, col):
    import numpy as np
    x = g[col].to_numpy(float); y = g.placed.to_numpy(bool)
    if y.all() or not y.any():
        return 0.0, 0
    p, u = x[y], x[~y]
    return float((p[:, None] > u[None, :]).sum() + 0.5 * (p[:, None] == u[None, :]).sum()), p.size * u.size


def run(sub, cands, base, label):
    by_date = defaultdict(list)
    for race, g in sub.groupby("race"):
        by_date[g.date.iloc[0]].append({c: race_auc(g, c) for c in cands})
    def pooled(ds, c):
        n = d = 0.0
        for x in ds:
            for v in by_date[x]:
                n += v[c][0]; d += v[c][1]
        return n / d
    dates = sorted(by_date); pt = {c: pooled(dates, c) for c in cands}
    rng = random.Random(20261105); bs = defaultdict(list)
    for _ in range(1000):
        s = [rng.choice(dates) for _ in dates]
        a = {c: pooled(s, c) for c in cands}
        for c in cands:
            bs[c].append(a[c] - a[base])
    print(f"\n{label}（Δ 對 {base}）")
    for c in cands:
        xs = sorted(bs[c]); print(f"  {c:10s} {pt[c]:.4f}  Δ {pt[c]-pt[base]:+.4f} [{xs[25]:+.4f}, {xs[974]:+.4f}]")


run(df, CANDS, "abs_last", "L400 leaf 場內上名 AUC")
s = df[have_speed].copy()
for c in CANDS:
    s[c + "_rho"] = 0
run(s, CANDS + ["speed"], "speed", "同一批馬對現行 speed_score")
for c in CANDS:
    rho = s.groupby("race").apply(lambda g: g[c].rank().corr(g["speed"].rank())).mean()
    print(f"  ρ({c}, speed_score) = {rho:+.3f}")
