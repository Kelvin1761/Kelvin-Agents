#!/usr/bin/env python3
"""R2 vs T3 正面對決（同一 baseline：現行綜合分 + 練馬師剩餘表現）。"""
import collections, csv, importlib.util, json, sys
from pathlib import Path
import numpy as np
S = Path(__file__).resolve().parent
def mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
E = mod("eps", S.parent / "au_people_prize/run.py"); J = mod("jtre", S.parent / "au_people_redesign/run.py"); L = J.L
R = "/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/"
base = L.eligible(json.loads(Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/BASE.json").read_text())["races"])
people = {}
for r in csv.DictReader(open(R + "AU_Historical_Raw_Race_Results.csv", encoding="utf-8-sig")):
    people[(r["Date"], r["Race"], E.norm(r["Horse"]))] = (E.norm(r["Jockey"]), E.norm(r["Trainer"]))
cache = json.loads(Path(R + "AU_Sportsbet_People_Cache.json").read_text())
E.MODE = "total"; snapsE = E.load_snaps(R + "AU_Sportsbet_People_Snapshots.jsonl", cache)
by = collections.defaultdict(list)
for i, r in enumerate(base):
    by[r["date"]].append(i)
feats, who_t = [], []
for r in base:
    F, tl = [], []
    for x in r["rows"]:
        j, t = people.get((r["date"], str(r["race"]), E.norm(x["name"])), (None, None))
        F.append([E.asof(snapsE, "jockey", j, r["date"]) if j else None, E.asof(snapsE, "trainer", t, r["date"]) if t else None]); tl.append(t)
    F = np.array([[np.nan if v is None else v for v in row] for row in F], float)
    for c in range(2):
        col = F[:, c]; m = np.nanmean(col) if np.isfinite(col).any() else 0.0; col[~np.isfinite(col)] = m; F[:, c] = col - col.mean()
    feats.append(F); who_t.append(tl)
ability = [[x["ability"] for x in r["rows"]] for r in base]
cal = L.calibrations(base); resid = collections.defaultdict(float); cnt = collections.defaultdict(int); tres = [None] * len(base)
for d in sorted(by):
    for i in by[d]:
        Rr = np.array([resid[t] / (cnt[t] + 50.0) if t else 0.0 for t in who_t[i]]); tres[i] = list(np.array(ability[i]) + 40.0 * (Rr - Rr.mean()))
    if d in cal:
        for i in by[d]:
            a = np.array(ability[i]); p = 1 / (1 + np.exp(-(cal[d][0] + cal[d][1] * (a - a.mean()))))
            for t, x, pp in zip(who_t[i], base[i]["rows"], p):
                if t:
                    resid[t] += int(x["pos"] <= 3) - pp; cnt[t] += 1
T3 = E.walk(tres, feats, base, by)
# R2 leaf change（jtre 同一做法）→ 加落 TRES
sys.argv = ["x", "", R + "AU_Historical_Raw_Race_Results.csv", R + "AU_Sportsbet_People_Snapshots.jsonl", R + "AU_Sportsbet_People_Cache.json", "/dev/null"]
snapsJ = J.load_snaps(R + "AU_Sportsbet_People_Snapshots.jsonl", cache)
rows = []
for ri, r in enumerate(base):
    for x in r["rows"]:
        j, t = people.get((r["date"], str(r["race"]), J.norm(x["name"])), (None, None))
        rows.append((ri, x, (J.asof(snapsJ["tot"].get(("jockey", j)), r["date"]) if j else None,
                             J.asof(snapsJ["tot"].get(("trainer", t)), r["date"]) if t else None)))
def st(v):
    v = np.array([a for a in v if a is not None], float); return v.mean(), v.std()
leaf = {"J": st([x["features"]["jockey_score"] for _, x, _ in rows]), "T": st([x["features"]["trainer_score"] for _, x, _ in rows])}
pz = {"J": st([v[0] for _, _, v in rows]), "T": st([v[1] for _, _, v in rows])}
R2 = [[None] * len(r["rows"]) for r in base]; k = 0
counter = collections.defaultdict(int)
for ri, x, v in rows:
    f = dict(x["features"])
    for who, key, val in (("J", "jockey_score", v[0]), ("T", "trainer_score", v[1])):
        if val is not None:
            pl = float(np.clip(leaf[who][0] + leaf[who][1] * (val - pz[who][0]) / pz[who][1], 0, 100)); f[key] = 0.5 * f[key] + 0.5 * pl
    j = counter[ri]; counter[ri] += 1
    R2[ri][j] = tres[ri][j] + (J.compose(f) - J.compose(x["features"]))
def races_of(ab):
    return [dict(r, rows=[dict(x, ability=float(v)) for x, v in zip(r["rows"], ab[i])]) for i, r in enumerate(base)]
LIVE = races_of(R2)
