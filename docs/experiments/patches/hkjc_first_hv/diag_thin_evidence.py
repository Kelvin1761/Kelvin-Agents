"""通情達理型：薄／舊證據疊加診斷。殘差 = 入頭三 − 現行 live 校準 p（base_venue_age）。"""
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
hist = defaultdict(list); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if not m or not b._started(row): continue
        try: p = int(row.get("pos"))
        except Exception: p = None
        try: o = float(row.get("win_odds"))
        except Exception: o = None
        hist[m.group(1)].append((d, race.get("venue"), p, o, str(race.get("race_class") or race.get("class") or "")))
        code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
for v in hist.values(): v.sort(key=lambda t: t[0])
ex = next(iter(idx["results"].values())); print("race keys:", [k for k in ex if k != "results"])
def feats(c, d0, ven):
    prev = [t for t in hist[c] if t[0] < d0]
    if not prev: return None
    last = prev[-1]; n = len(prev)
    gap = (date.fromisoformat(d0) - date.fromisoformat(last[0])).days
    fav = last[3] is not None and last[3] <= 4.0
    long_ = gap > 180
    first_hv = ven == "跑馬地" and not any(t[1] == "跑馬地" for t in prev)
    st_to_hv = ven == "跑馬地" and last[1] == "沙田"
    return {
        "T0 前≤2仗＋休>180＋上仗≤$4（通情達理型）": n <= 2 and long_ and fav,
        "T1 前≤2仗＋上仗≤$4": n <= 2 and fav,
        "T2 休>180＋上仗≤$4（任何仗數）": long_ and fav,
        "T3 休>180＋上仗>$4（對照）": long_ and not fav and last[3] is not None,
        "T4 休61–180＋上仗≤$4": 60 < gap <= 180 and fav,
        "T5 休≤60＋上仗≤$4（對照）": gap <= 60 and fav,
        "T6 前≤2仗＋上仗贏＋休>180": n <= 2 and last[2] == 1 and long_,
        "T7 前≤2仗＋初次谷草＋田草轉谷草": n <= 2 and first_hv and st_to_hv,
        "T8 前≤2仗＋休>180＋初次谷草": n <= 2 and long_ and first_hv,
        "U1 休>180（任何）": long_,
        "U2 休>180＋前≤3仗": long_ and n <= 3,
        "U3 休91–180＋前≤3仗": 90 < gap <= 180 and n <= 3,
        "U4 前≤3仗＋初次谷草（任何上仗場地）": n <= 3 and first_hv,
        "U5 前4+仗＋初次谷草＋田草轉谷草（對照）": n >= 4 and first_hv and st_to_hv,
        "T9 三樣疊埋：前≤2仗＋休>180＋上仗≤$4＋初次谷草": n <= 2 and long_ and fav and first_hv,
    }
calib = calibrate(rows)
recs = []
for x in rows:
    s = season(x["date"])
    if s < 2020: continue
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
    a, bb = calib[s]
    order = {h["n"]: i + 1 for i, h in enumerate(sorted(hs, key=lambda h: -h["raw"]))}
    for h, z in zip(hs, rc):
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        if not c: continue
        f = feats(c, x["date"], x.get("venue"))
        if f is None: continue
        recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1/(1+np.exp(-(a+bb*z))), rk=order[h["n"]], f=f))
print("馬次", len(recs))
rng = np.random.default_rng(0)
for k in recs[0]["f"]:
    out = []
    for lo, hi in ((2020, 2023), (2024, 2025)):
        sel = [r for r in recs if lo <= r["s"] <= hi and r["f"][k]]
        if len(sel) < 20: out.append(f"n={len(sel)}"); continue
        y = np.array([r["y"] - r["p"] for r in sel])
        bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(1000)]
        top3 = [r for r in sel if r["rk"] <= 3]
        out.append(f"{100*y.mean():+.1f}pp[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] 實{100*np.mean([r['y'] for r in sel]):.0f}%/估{100*np.mean([r['p'] for r in sel]):.0f}% n={len(sel)} 模型頭三{len(top3)}匹入位{(100*np.mean([r['y'] for r in top3]) if top3 else 0):.0f}%")
    print(f"{k}\n   dev {out[0]}\n   ho  {out[1]}")
