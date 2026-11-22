"""Kelvin 2026-11-22「大幅增程 logic 唔合理」：路程概念拆解殘差（live base_venue_age 之上）。"""
import gzip, json, re, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
import hkjc_history_replay_build as b
from diag import season
from diag_full import calibrate
def num(x):
    try: return float(str(x).strip())
    except ValueError: return None
def pos(x):
    s = str(x or "").strip(); return int(s) if s.isdigit() else None
def iso(dmy):
    d, m, y = dmy.split("/"); return f"{y}-{m}-{d}"
def hk(vt):
    vt = str(vt or ""); return vt.startswith("跑馬地") or vt.startswith("沙田")
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
runs = defaultdict(list)
for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/horses.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line); code = r["horse_id"].rsplit("_", 1)[-1]
    for q in r.get("runs") or []:
        try:
            if hk(q.get("venue_track")): runs[code].append((iso(q["date"]), num(q.get("distance")), pos(q.get("pos"))))
        except Exception: pass
for v in runs.values(): v.sort()
idx = b.load_index(); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)

def feats(c, d0, dist):
    prev = [t for t in runs.get(c, []) if t[0] < d0 and t[1]]
    if not prev or not dist: return None
    last = prev[-1][1]; jump = dist - last
    mx = max(t[1] for t in prev)
    pl = [t[1] for t in prev if t[2] and t[2] <= 3]
    mxp = max(pl) if pl else None
    run_here = any(t[1] == dist for t in prev)
    run_pm100 = any(abs(t[1] - dist) <= 100 for t in prev)
    pl_pm100 = any(abs(x - dist) <= 100 for x in pl)
    d1 = jump >= 400
    f = {
        "對上仗 −400 或更少": jump <= -400, "對上仗 −200～−399": -399 <= jump <= -200, "對上仗 ±199": abs(jump) <= 199,
        "對上仗 +200～+399": 200 <= jump <= 399, "對上仗 +400～+599（D1）": 400 <= jump <= 599, "對上仗 ≥+600（D1）": jump >= 600,
        "D1＆今仗 ≤ 生涯最遠（返熟悉路程）": d1 and dist <= mx,
        "D1＆今仗 > 生涯最遠（新領域）": d1 and dist > mx,
        "D1＆±100 米內上過名": d1 and pl_pm100,
        "D1＆±100 米內冇上過名": d1 and not pl_pm100,
        "非D1＆今仗比生涯最遠多 ≥200": (not d1) and dist - mx >= 200,
        "非D1＆今仗比生涯最遠多 ≥400": (not d1) and dist - mx >= 400,
        "非D1＆今仗比上名最遠多 ≥400": (not d1) and mxp is not None and dist - mxp >= 400,
        "任何＆今仗比生涯最遠多 ≥200": dist - mx >= 200,
        "任何＆±100 米內從未跑過": not run_pm100,
        "任何＆±100 米內跑過但冇上名": run_pm100 and not pl_pm100,
        "任何＆±100 米內上過名": pl_pm100,
        "任何＆完全同程冇跑過、但±100 內上過名（如1650↔1600）": (not run_here) and pl_pm100,
        "今仗短過生涯最短 ≥200（首次縮短）": dist <= min(t[1] for t in prev) - 200,
    }
    return f

calib = calibrate(rows); recs = []
for x in rows:
    s = season(x["date"])
    if s < 2020: continue
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean(); a, bb = calib[s]
    for h, z in zip(hs, rc):
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        f = feats(c, x["date"], x.get("distance")) if c else None
        if f is None: continue
        recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1/(1+np.exp(-(a+bb*z))), f=f))
print("馬次", len(recs))
rng = np.random.default_rng(0)
for k in recs[0]["f"]:
    out = []
    for lo, hi in ((2020, 2023), (2024, 2025)):
        sel = [r for r in recs if lo <= r["s"] <= hi and r["f"][k]]
        y = np.array([r["y"] - r["p"] for r in sel])
        if len(y) < 30: out.append(f"n={len(y)}"); continue
        bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(500)]
        out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] 實{100*np.mean([r['y'] for r in sel]):.0f}% n={len(y)}")
    print(f"{k}｜dev {out[0]}｜holdout {out[1]}")
