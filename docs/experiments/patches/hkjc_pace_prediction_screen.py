"""HKJC 步速篩選（唔係 A/B）：賽前「習慣放頭馬數目」預測全場步速，準唔準？跑法 × 步速有冇模型以外嘅訊號？

實際步速：Facts「完整賽績檔案」短評開頭（極慢／慢／中等偏慢／中等／中等偏快／快／極快），(馬, 日期) join 賽果庫場次。
賽前習慣：賽果庫 RunningPos 第一個沿途位，只用目標賽日之前嘅往績（PIT）。目標窗 < 2026-10-11。
"""
import glob
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT, ROWS = sys.argv[1], sys.argv[2]
PACE = {"極慢步速": 0, "慢步速": 1, "中等偏慢步速": 2, "中等步速": 3, "中等偏快步速": 4, "快步速": 5, "極快步速": 6}

# 1. actual pace label per (horse, date) from Facts tables
label = {}
for f in glob.glob(ROOT + "/2026-*/* Race * Facts.md"):
    t = open(f, encoding="utf-8").read()
    for blk in re.split(r"^### 馬號 \d+ — ", t, flags=re.M)[1:]:
        name = blk.split()[0].strip()
        for row in re.finditer(r"^\|\s*\d+\s*\|\s*(\d{2})/(\d{2})/(\d{4})\s*\|.*?\|\s*([^|;]{1,8}步速);", blk, re.M):
            lab = row.group(4).strip()
            if lab in PACE:
                label[(name, f"{row.group(3)}-{row.group(2)}-{row.group(1)}")] = PACE[lab]

rows = pd.read_pickle(ROWS)
rows = rows[rows["Rank"].notna()].copy()
rows["Horse"] = rows["Horse"].astype(str).str.replace(r"\([A-Z]\d+\)$", "", regex=True).str.strip()
rows["date"] = rows["Date"].astype(str).str[:10]
rows["race"] = rows["date"] + "|" + rows["Venue"].astype(str) + "|" + rows["RaceNo"].astype(str)
rows["field"] = rows.groupby("race")["Horse"].transform("size")
rows["first"] = rows["RunningPos"].astype(str).str.extract(r"^(\d+)")[0].astype(float)
rows = rows.sort_values(["date", "RaceNo"])

race_pace = {}
for race, g in rows.groupby("race"):
    labs = [label[(h, d)] for h, d in zip(g.Horse, g.date) if (h, d) in label]
    if labs:
        race_pace[race] = Counter(labs).most_common(1)[0][0]
print(f"races with actual pace label: {len(race_pace)}")

# 2. PIT habit per runner
hist = defaultdict(list)
recs = []
for date, day in rows.groupby("date", sort=True):
    for r in day.itertuples():
        past = [x for x in hist[r.Horse][-3:] if x == x]
        recs.append(dict(race=r.race, date=date, venue=r.Venue, dist=r.Distance, horse=r.Horse,
                         placed=0 < r.Rank <= 3, rank=r.Rank, first=r.first, field=r.field,
                         habit=st.mean(past) if len(past) >= 2 else None))
    for r in day.itertuples():
        hist[r.Horse].append(r.first)
df = pd.DataFrame(recs)
df = df[(df.date < "2026-10-11") & df.race.isin(race_pace)]
df["pace"] = df.race.map(race_pace)

agg = df.groupby("race").agg(pace=("pace", "first"), venue=("venue", "first"), dist=("dist", "first"),
                             n=("horse", "size"), known=("habit", lambda s: s.notna().sum()),
                             leaders=("habit", lambda s: (s <= 2.5).sum()),
                             front4=("habit", lambda s: (s <= 4).sum()),
                             minhab=("habit", "min"))
agg = agg[agg.known >= agg.n * 0.6]
print(f"races evaluated: {len(agg)}  (≥60% runners with ≥2 prior runs)")
print("actual pace distribution:", agg.pace.value_counts().sort_index().to_dict())


def spearman(a, b):
    return a.rank().corr(b.rank())


print("\n=== 1. 預測步速準唔準（全場層面）===")
for c in ("leaders", "front4", "minhab"):
    print(f"  Spearman({c}, 實際步速) = {spearman(agg[c], agg.pace):+.3f}")
for v, g in agg.groupby("venue"):
    print(f"  [{v}] Spearman(leaders, pace) = {spearman(g.leaders, g.pace):+.3f}  n={len(g)}")
agg["pred3"] = pd.cut(agg.leaders, [-1, 0, 1, 99], labels=["0匹", "1匹", "≥2匹"])
agg["act3"] = pd.cut(agg.pace, [-1, 2, 3, 6], labels=["偏慢", "中等", "偏快"])
print("\n  習慣放頭馬數 × 實際步速（行 %）")
print((pd.crosstab(agg.pred3, agg.act3, normalize="index") * 100).round(1).to_string())
print(pd.crosstab(agg.pred3, agg.act3).to_string())

print("\n=== 2. 實際步速 × 實際跑法（事後，上名率）===")
d = df[df["first"].notna()].copy()
d["style"] = pd.cut(d["first"] / d["field"], [0, 0.25, 0.6, 1.01], labels=["前置", "中置", "後上"])
d["act3"] = pd.cut(d.pace, [-1, 2, 3, 6], labels=["偏慢", "中等", "偏快"])
print((d.pivot_table(index="style", columns="act3", values="placed", aggfunc="mean") * 100).round(1).to_string())

print("\n=== 3. 賽前習慣 × 預測步速（上名率，同模型無關）===")
h = df[df.habit.notna()].copy()
h["hstyle"] = pd.cut(h.habit / h.field, [0, 0.25, 0.6, 1.01], labels=["習慣前置", "習慣中置", "習慣後上"])
h = h.join(agg[["pred3"]], on="race", how="inner")
print((h.pivot_table(index="hstyle", columns="pred3", values="placed", aggfunc="mean") * 100).round(1).to_string())
print(h.pivot_table(index="hstyle", columns="pred3", values="placed", aggfunc="size").to_string())
df.to_pickle(ROWS.replace("hk_rows.pkl", "hk_pace_runners.pkl")); agg.to_pickle(ROWS.replace("hk_rows.pkl", "hk_pace_races.pkl"))
