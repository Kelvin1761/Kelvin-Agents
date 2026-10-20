"""L400 絕對值 vs 按上仗(場地,跑道,路程)標準化：場內上名 AUC。cell 平均只用賽日之前嘅觀測（PIT）。"""
import sys, re, json, random
from pathlib import Path
from collections import defaultdict
import pandas as pd
sys.path[:0] = [".agents/skills/shared_racing/scripts", ".agents/skills/hkjc_racing/hkjc_reflector/scripts", ".", ".agents/scripts"]
from corpus_paths import logic_files
import build_comprehensive_stats as bcs
res = pd.read_pickle(sys.argv[1])
res = res[res["Rank"].notna()].copy()
res["Horse"] = res["Horse"].astype(str).str.replace(r"\([A-Z]\d+\)$", "", regex=True).str.strip()
cell_of = {(r.Horse, r.Date): (r.Venue, r.Track, int(r.Distance) if pd.notna(r.Distance) else None) for r in res.itertuples()}
rank_of = {(r.Horse, r.Date): int(r.Rank) for r in res.itertuples()}
recs = []
for lf in logic_files(bcs.HK_RACING):
    lf = Path(lf); m = re.match(r"(\d{4}-\d{2}-\d{2})", lf.parent.name); rn = re.search(r"Race_(\d+)_Logic", lf.name)
    if not m or not rn: continue
    date = m.group(1)
    try: logic = json.load(open(lf, encoding="utf-8"))
    except Exception: continue
    for h in (logic.get("horses") or {}).values():
        if not isinstance(h, dict): continue
        name = str(h.get("horse_name") or "").strip(); d = h.get("_data") or {}
        rk = rank_of.get((name, date))
        if rk is None: continue
        try: l4 = float(d.get("raw_l400"))
        except (TypeError, ValueError): l4 = None
        lm = re.search(r"第1仗\((\d{2})/(\d{2})/(\d{4})", str(d.get("recent_6_detail") or ""))
        last = f"{lm.group(3)}-{lm.group(2)}-{lm.group(1)}" if lm else None
        recs.append(dict(date=date, race=f"{date}_{rn.group(1)}", horse=name, placed=rk <= 3, l4=l4, cell=cell_of.get((name, last)) if last else None))
df = pd.DataFrame(recs).drop_duplicates(["race", "horse"])
print(f"runners {len(df)} races {df.race.nunique()} meetings {df.date.nunique()} | L400 有值 {df.l4.notna().mean():.1%} | 有值而搵到上仗 cell {df[df.l4.notna()].cell.notna().mean():.1%}")
v = df[df.l4.notna() & df.cell.notna()].copy()
# PIT cell mean: only observations from earlier race dates (a horse's latest-run L400 observed before today)
v = v.sort_values("date"); sums = defaultdict(lambda: [0.0, 0]); resid = []
for date, g in v.groupby("date", sort=True):
    for r in g.itertuples():
        s, n = sums[r.cell]; resid.append((r.Index, r.l4 - s / n if n >= 30 else None))
    for r in g.itertuples(): sums[r.cell][0] += r.l4; sums[r.cell][1] += 1
v["resid"] = pd.Series(dict(resid))
cells = v.groupby(v.cell.astype(str))["l4"].agg(["mean", "count"]).sort_values("count", ascending=False)
print("上仗 cell L400 平均（頭 10）:\n", cells.head(10).round(2).to_string())
w = v[v.resid.notna()]
print(f"可比較 runners {len(w)} races {w.race.nunique()}")
def auc(sub, col):
    num = den = 0
    for _, g in sub.groupby("race"):
        P = g[g.placed][col].tolist(); U = g[~g.placed][col].tolist()
        for a in P:
            for b in U:
                den += 1; num += 1 if a < b else .5 if a == b else 0   # 細 = 快 = 好
    return num / den if den else float("nan")
def bands(x):  # engine thresholds
    return 0 if x <= 22.4 else 1 if x <= 23.0 else 2 if x <= 23.6 else 3 if x < 24.0 else 4 if x < 24.6 else 5
w = w.copy(); w["band_raw"] = w.l4.map(bands)
# residual bands with the same marginal proportions as the raw bands
qs = w.band_raw.value_counts(normalize=True).sort_index().cumsum().tolist()
cuts = [w.resid.quantile(q) for q in qs[:-1]]
w["band_resid"] = w.resid.map(lambda x: sum(x > c for c in cuts))
base = {c: auc(w, c) for c in ("l4", "resid", "band_raw", "band_resid")}
print("AUC:", {k: round(x, 4) for k, x in base.items()})
races = {d: g for d, g in w.groupby("date")}; dates = list(races); rng = random.Random(3); diffs = defaultdict(list)
for _ in range(500):
    s = pd.concat([races[rng.choice(dates)].assign(race=lambda x, i=i: x.race + f"#{i}") for i in range(len(dates))])
    a = {c: auc(s, c) for c in ("l4", "resid", "band_raw", "band_resid")}
    diffs["cont"].append(a["resid"] - a["l4"]); diffs["band"].append(a["band_resid"] - a["band_raw"])
for k, xs in diffs.items():
    xs.sort(); print(f"Δ AUC 標準化 − 絕對 ({k}): {base['resid' if k=='cont' else 'band_resid'] - base['l4' if k=='cont' else 'band_raw']:+.4f} [{xs[12]:+.4f}, {xs[487]:+.4f}]")
