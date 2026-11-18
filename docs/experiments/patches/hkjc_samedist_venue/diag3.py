"""Kelvin 2026-11-19：一仗馬／沙田直路1000→谷草／同程上名分場地／馬齡代理 —— live 之上殘差。"""
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
meta = {(x["date"], x["race"]): (x.get("distance"), x.get("venue"), x.get("awt")) for x in rows}
imp = {}
for hid, v in idx["horses"].items():
    m = re.match(r"HK_(\d{4})_([A-Z]\d{3})", hid)
    if m:
        cat = v["profile"].get("進口類別") or ""
        imp[m.group(2)] = (int(m.group(1)), 3 if "新馬" in cat else 4)
hist = defaultdict(list); code_of = {}
for (d, n), race in idx["results"].items():
    dist, ven, awt = meta.get((d, n), (None, race.get("venue"), None))
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if not m or not b._started(row): continue
        try: p = int(row.get("pos"))
        except Exception: p = None
        hist[m.group(1)].append((d, dist, ven, awt, p))
        code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
for v in hist.values(): v.sort(key=lambda t: t[0])

def straight(t): return t[2] == "沙田" and t[1] == 1000 and not t[3]

def feats(c, d0, dist, ven, awt):
    prev = [t for t in hist[c] if t[0] < d0]
    if not prev: return None
    gap = (date.fromisoformat(d0) - date.fromisoformat(prev[-1][0])).days
    n = len(prev); last = prev[-1]
    hv_today = ven == "跑馬地"
    sd = [t for t in prev if t[1] == dist]
    sd_pl = [t for t in sd if t[4] and t[4] <= 3]
    sd_pl_same_ven = [t for t in sd_pl if t[2] == ven and t[3] == awt]
    f = {
        "前出賽 1 仗": n == 1, "前出賽 2 仗": n == 2, "前出賽 3–5 仗": 3 <= n <= 5, "前出賽 6+ 仗（對照）": n >= 6,
        "前 1 仗且上仗贏": n == 1 and last[4] == 1,
        "前 1 仗且休 >180 日": n == 1 and gap > 180,
        "前 ≤2 仗且休 >180 日": n <= 2 and gap > 180,
        "今仗谷草1000、上仗沙田直路1000": hv_today and dist == 1000 and straight(last),
        "今仗谷草1000、上仗谷草1000（對照）": hv_today and dist == 1000 and last[2] == "跑馬地" and last[1] == 1000,
        "今仗谷草（任何程）、上仗沙田直路1000": hv_today and straight(last),
        "今仗谷草1000、同程上名全喺沙田直路": hv_today and dist == 1000 and sd_pl and not sd_pl_same_ven,
        "今仗谷草1000、同程有喺谷草上名": hv_today and dist == 1000 and bool(sd_pl_same_ven),
        "同程上名但全喺另一場地（任何程）": bool(sd_pl) and not sd_pl_same_ven,
        "同程上名有喺同場地（任何程）": bool(sd_pl_same_ven),
        "今仗沙田直路1000、上仗彎路": straight((d0, dist, ven, awt, None)) and not straight(last),
    }
    if c in imp:
        y = int(d0[:4]) + (1 if int(d0[5:7]) >= 8 else 0)   # 馬齡 8 月 1 日加一
        age = y - imp[c][0] + imp[c][1] - (1 if int(d0[5:7]) >= 8 else 0)
        age = int(d0[:4]) - imp[c][0] + imp[c][1]
        for lo, hi, lab in ((0, 4, "馬齡≈≤4"), (5, 5, "馬齡≈5"), (6, 6, "馬齡≈6"), (7, 7, "馬齡≈7"), (8, 8, "馬齡≈8"), (9, 99, "馬齡≈9+")):
            f[lab] = lo <= age <= hi
        f["馬齡≈9+、評分落後（季內冇上名）"] = age >= 9 and not any(t[4] and t[4] <= 3 for t in prev[-6:])
    return f

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
        f = feats(c, x["date"], x.get("distance"), x.get("venue"), x.get("awt"))
        if f is None: continue
        recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1/(1+np.exp(-(a+bb*z))), f=f))
print(f"馬次 {len(recs)}")
rng = np.random.default_rng(0)
keys = []
for r in recs:
    for k in r["f"]:
        if k not in keys: keys.append(k)
for k in keys:
    out = []
    for lo, hi in ((2020, 2023), (2024, 2025)):
        sel = [r for r in recs if lo <= r["s"] <= hi and r["f"].get(k)]
        y = np.array([r["y"] - r["p"] for r in sel])
        if len(y) < 30: out.append(f"n={len(y)}"); continue
        bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(500)]
        out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] 實{100*np.mean([r['y'] for r in sel]):.0f}%/估{100*np.mean([r['p'] for r in sel]):.0f}% n={len(y)}")
    print(f"{k}｜dev {out[0]}｜holdout {out[1]}")
