"""EXP-20261118-05 診斷（Kelvin 2026-11-18）：同程上名率分段＋長休分段 —— live 之上嘅殘差（同 EXP-20261117-02 把尺）。"""
import json, re, sys
from collections import defaultdict
from datetime import date
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
import hkjc_history_replay_build as b
from diag import season
from diag_full import calibrate

DUMP = sys.argv[1]
idx = b.load_index()
rows = [x for x in map(json.loads, open(DUMP)) if "horses" in x]
dist_of = {(x["date"], x["race"]): x.get("distance") for x in rows}
# per horse: [(date, distance, venue, pos_int or None)]
hist = defaultdict(list)
code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if not m or not b._started(row):
            continue
        try: p = int(row.get("pos"))
        except Exception: p = None
        hist[m.group(1)].append((d, dist_of.get((d, n)), p))
        code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
for v in hist.values(): v.sort(key=lambda t: t[0])

def feats(c, d0, dist):
    prev = [t for t in hist[c] if t[0] < d0]
    if not prev: return None
    gap = (date.fromisoformat(d0) - date.fromisoformat(prev[-1][0])).days
    sd = [t for t in prev if t[1] == dist]
    n = len(sd); pl = sum(1 for t in sd if t[2] and t[2] <= 3); w = sum(1 for t in sd if t[2] == 1)
    rate = pl / n if n else None
    return {
        "同程 0 戰": n == 0,
        "同程 有戰冇上名": n > 0 and pl == 0,
        "同程 有上名（現行加分組）": pl > 0,
        "  其中 1 次上名、≥4 戰（上名率 ≤25%）": pl == 1 and n >= 4,
        "  其中 上名率 <34%（≥3 戰）": pl > 0 and n >= 3 and rate < 0.34,
        "  其中 上名率 34–66%": pl > 0 and n >= 2 and 0.34 <= rate <= 0.66,
        "  其中 上名率 >66%（≥2 戰）": pl > 0 and n >= 2 and rate > 0.66,
        "  其中 有贏過": w > 0,
        "  其中 有上名但冇贏過": pl > 0 and w == 0,
        "休 22–45 日（對照）": 22 <= gap <= 45,
        "休 46–75 日": 46 <= gap <= 75,
        "休 76–120 日（現扣 −3 健康分）": 76 <= gap <= 120,
        "休 121–180 日": 121 <= gap <= 180,
        "休 181–270 日": 181 <= gap <= 270,
        "休 >270 日": gap > 270,
    }

calib = calibrate(rows)
recs = []
for x in rows:
    s = season(x["date"])
    if s < 2020: continue
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
    a, bb = calib[s]
    for h, z in zip(hs, rc):
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        if not c: continue
        f = feats(c, x["date"], x.get("distance"))
        if f is None: continue
        recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1/(1+np.exp(-(a+bb*z))), f=f))
print(f"馬次 {len(recs)}")
rng = np.random.default_rng(0)
for k in recs[0]["f"]:
    out = []
    for lo, hi in ((2020, 2023), (2024, 2025)):
        sub = [r for r in recs if lo <= r["s"] <= hi]
        sel = [r for r in sub if r["f"][k]]
        y = np.array([r["y"] - r["p"] for r in sel])
        if len(y) < 30: out.append(f"n={len(y)}"); continue
        bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(500)]
        hit = 100*np.mean([r["y"] for r in sel])
        out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] 上名率{hit:.0f}% n={len(y)}")
    seas = []
    for s in sorted({r["s"] for r in recs}):
        y = [r["y"] - r["p"] for r in recs if r["s"] == s and r["f"][k]]
        seas.append(f"{100*np.mean(y):+.0f}" if len(y) >= 20 else ".")
    print(f"{k}｜dev {out[0]}｜holdout {out[1]}｜逐季 {' '.join(seas)}")
