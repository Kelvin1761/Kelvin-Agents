"""前置習慣超額（對模型同排名區間）按賽前情況分層，同埋當晚偏差持續性（研究用，唔入分）。< 2026-10-11。"""
import json, re, sys, random, statistics as st
from collections import defaultdict
from pathlib import Path
import pandas as pd
sys.path[:0] = [sys.argv[3] + "/.agents/skills/shared_racing/scripts", sys.argv[3]]
from corpus_paths import logic_files
rows = pd.read_pickle(sys.argv[2] + "/hk_rows.pkl"); rows = rows[rows["Rank"].notna()].copy()
rows["Horse"] = rows["Horse"].astype(str).str.replace(r"\([A-Z]\d+\)$", "", regex=True).str.strip()
rows["date"] = rows["Date"].astype(str).str[:10]; rows["race"] = rows["date"] + "|" + rows["Venue"].astype(str) + "|" + rows["RaceNo"].astype(str)
rows["field"] = rows.groupby("race")["Horse"].transform("size")
rows["fc"] = rows["RunningPos"].astype(str).str.extract(r"^(\d+)")[0].astype(float)
rows["rail"] = rows["Course"].astype(str).str.extract(r'"([^"]+)"')[0].fillna(rows["Track"].astype(str))
rows = rows.sort_values(["date", "RaceNo"]); hist = defaultdict(list); recs = []
for date, day in rows.groupby("date", sort=True):
    for r in day.itertuples():
        p = [x for x in hist[r.Horse][-3:] if x == x]
        recs.append(dict(race=r.race, date=date, raceno=r.RaceNo, venue=r.Venue, track=r.Track, rail=r.rail, going=r.Going, dist=r.Distance,
                         horse=r.Horse, placed=0 < r.Rank <= 3, field=r.field, fc=r.fc, habit=st.mean(p) if len(p) >= 2 else None))
    for r in day.itertuples(): hist[r.Horse].append(r.fc)
df = pd.DataFrame(recs); df = df[(df.date >= "2026-04-01") & (df.date < "2026-10-11")]
rank = {}
for lf in logic_files(sys.argv[1]):
    lf = Path(lf); m = re.match(r"(\d{4}-\d{2}-\d{2})", lf.parent.name)
    if not m or m.group(1) >= "2026-10-11": continue
    try: lg = json.load(open(lf, encoding="utf-8"))
    except Exception: continue
    sc = []
    for h in (lg.get("horses") or {}).values():
        pa = (h or {}).get("python_auto") or {}; v = pa.get("ability_score_raw", pa.get("ability_score"))
        if v is not None: sc.append((float(v), re.sub(r"\s*\(退出\)$", "", str(h.get("horse_name") or "")).strip()))
    for i, (_, n) in enumerate(sorted(sc, reverse=True)): rank[(n, m.group(1))] = i + 1
df["mrank"] = [rank.get((h, d)) for h, d in zip(df.horse, df.date)]
d = df[df.mrank.notna()].copy()
d["bucket"] = pd.cut(d.mrank, [0, 3, 6, 99]); d["exp"] = d.groupby("bucket", observed=True).placed.transform("mean"); d["resid"] = d.placed - d.exp
d["hstyle"] = pd.cut(d.habit / d.field, [0, 0.25, 0.6, 1.01], labels=["前置", "中置", "後上"])
h = d[d.habit.notna()].copy()
dates = sorted(h.date.unique()); g = {x: h[h.date == x] for x in dates}
def gap(s): return (s[s.hstyle == "前置"].resid.mean() - s[s.hstyle == "後上"].resid.mean()) * 100
def boot(sub, fn=gap, n=600):
    ds = sorted(sub.date.unique()); gg = {x: sub[sub.date == x] for x in ds}; rng = random.Random(11)
    xs = sorted(fn(pd.concat([gg[rng.choice(ds)] for _ in ds])) for _ in range(n)); return xs[int(n*.025)], xs[int(n*.975)]
print(f"全部：前置 − 後上 超額 {gap(h):+.1f}pp {tuple(round(x,1) for x in boot(h))}  ({h.race.nunique()} 場)")
h["dband"] = pd.cut(h.dist.astype(float), [0, 1200, 1650, 9999], labels=["≤1200", "1201-1650", "≥1800"])
h["going2"] = h.going.astype(str).where(h.going.astype(str).isin(["好地", "好地至快地"]), "其他")
for col in ("venue", "track", "rail", "dband", "going2"):
    print(f"\n按 {col}：")
    for k, s in h.groupby(col, observed=True):
        if s.race.nunique() < 25: continue
        lo, hi = boot(s); print(f"  {str(k):12s} {gap(s):+6.1f}pp [{lo:+.1f}, {hi:+.1f}]  {s.race.nunique()} 場")
# 當晚持續性（研究用，用事後賽果，唔可以入分）
print("\n當晚持續性（研究用）：之前已跑場次實際前置（第一沿途位 ≤3）上名率超額 → 今場前置習慣超額")
d2 = d.sort_values(["date", "raceno"]).copy(); d2["front_act"] = d2.fc <= 3
prior = {}
for date, day in d2.groupby("date"):
    acc_r = acc_n = 0.0
    for rn, race in day.groupby("raceno"):
        prior[(date, rn)] = (acc_r / acc_n) if acc_n >= 6 else None
        f = race[race.front_act]; acc_r += f.resid.sum(); acc_n += len(f)
h["night_bias"] = [prior.get((dt, rn)) for dt, rn in zip(h.date, h.raceno)]
x = h[h.night_bias.notna()].copy()
x["nb"] = pd.qcut(x.night_bias, 3, labels=["當晚前置唔著數", "中性", "當晚前置著數"]); print("tercile cuts:", [round(v,4) for v in x.night_bias.quantile([1/3, 2/3])], "n races", x.race.nunique())
for k, s in x.groupby("nb", observed=True):
    lo, hi = boot(s); print(f"  {k:10s} 前置−後上 {gap(s):+6.1f}pp [{lo:+.1f}, {hi:+.1f}]  {s.race.nunique()} 場")
