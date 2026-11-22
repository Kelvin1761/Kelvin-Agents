"""Kelvin 2026-11-22「要好好整同程記錄」：live（V1 二元 ±、V2 同場地）之上，同程記錄仲漏咗乜。v5 校準殘差。"""
import gzip, json, re, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b
import hkjc_replay_compare_v5 as v5
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def iso(dmy):
    d, m, y = dmy.split("/"); return f"{y}-{m}-{d}"
def vkey(vt):
    vt = str(vt or "")
    if vt.startswith("跑馬地"): return "HV"
    if "全天候" in vt: return "AWT"
    if vt.startswith("沙田"): return "ST"
    return None
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
runs = defaultdict(list)
for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/horses.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line); code = r["horse_id"].rsplit("_", 1)[-1]
    for q in r.get("runs") or []:
        try:
            vk = vkey(q.get("venue_track")); ps = str(q.get("pos") or "").strip()
            if vk: runs[code].append((iso(q["date"]), float(q["distance"]), int(ps) if ps.isdigit() else None, vk))
        except Exception: pass
idx = b.load_index(); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
par = {s: v5.fit([x for x in rows if 2019 <= season(x["date"]) < s]) for s in sorted({season(x["date"]) for x in rows}) if s >= 2020}
recs = []
for x in rows:
    s = season(x["date"])
    if s not in par: continue
    keep = [h for h in x["horses"] if h["pos"]]; n = len(keep)
    r = np.array([h["raw"] for h in keep]); rc = r - r.mean(); a, bb, g = par[s]
    p = 1 / (1 + np.exp(-(a + bb * rc + g * v5.field_logit(n))))
    today = "HV" if x["venue"] == "跑馬地" else ("AWT" if x.get("awt") else "ST"); dist = x.get("distance")
    for j, h in enumerate(keep):
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        prev = [t for t in runs.get(c, []) if t[0] < x["date"]]
        if not prev or not dist: continue
        allpl = sum(1 for t in prev if t[2] and t[2] <= 3) / len(prev)
        sd = [t for t in prev if t[1] == dist]; sv = [t for t in sd if t[3] == today]
        sdn, sdp = len(sd), sum(1 for t in sd if t[2] and t[2] <= 3)
        svn, svp = len(sv), sum(1 for t in sv if t[2] and t[2] <= 3)
        recs.append(dict(w="dev" if s <= 2023 else "hold", y=int(h["pos"] <= 3), p=p[j], n_all=len(prev), allpl=allpl,
                         sdn=sdn, sdp=sdp, svn=svn, svp=svp))
rng = np.random.default_rng(0)
def show(lab, sel):
    out = []
    for w in ("dev", "hold"):
        v = np.array([r["y"] - r["p"] for r in recs if r["w"] == w and sel(r)])
        if len(v) < 40: out.append(f"n={len(v)}"); continue
        bt = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(300)]
        out.append(f"{100*v.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(v)}")
    print(f"{lab}｜dev {out[0]}｜holdout {out[1]}")
print("馬次", len(recs))
print("== A. 同程（任何場地）戰數 × 上名次數")
show("同程 0 戰", lambda r: r["sdn"] == 0)
show("同程 1 戰 冇上名", lambda r: r["sdn"] == 1 and r["sdp"] == 0)
show("同程 1 戰 上名", lambda r: r["sdn"] == 1 and r["sdp"] == 1)
for lo, hi in ((2, 3), (4, 6), (7, 99)):
    for name, f in (("0 上名", lambda r: r["sdp"] == 0), ("上名率 ≤1/3", lambda r: 0 < r["sdp"] / r["sdn"] <= 1/3),
                    ("1/3–2/3", lambda r: 1/3 < r["sdp"] / r["sdn"] <= 2/3), (">2/3", lambda r: r["sdp"] / r["sdn"] > 2/3)):
        show(f"同程 {lo}–{hi} 戰、{name}", lambda r, lo=lo, hi=hi, f=f: lo <= r["sdn"] <= hi and f(r))
print("== B. 同程上名率 對比 匹馬整體上名率（≥2 同程戰）")
for name, f in (("同程明顯好過整體（差 > +0.25）", lambda r: r["sdp"]/r["sdn"] - r["allpl"] > 0.25),
                ("同程略好（0～+0.25）", lambda r: 0 < r["sdp"]/r["sdn"] - r["allpl"] <= 0.25),
                ("同程略差（−0.25～0）", lambda r: -0.25 <= r["sdp"]/r["sdn"] - r["allpl"] <= 0),
                ("同程明顯差過整體（< −0.25）", lambda r: r["sdp"]/r["sdn"] - r["allpl"] < -0.25)):
    show(name, lambda r, f=f: r["sdn"] >= 2 and f(r))
print("== C. 整體上名率高、同程冇證據（≥2 同程戰）對照")
show("整體上名率 >50%、同程上名率 >2/3", lambda r: r["sdn"] >= 2 and r["allpl"] > .5 and r["sdp"]/r["sdn"] > 2/3)
show("整體上名率 ≤30%、同程上名率 >2/3", lambda r: r["sdn"] >= 2 and r["allpl"] <= .3 and r["sdp"]/r["sdn"] > 2/3)
print("== D. 同場地同程（今仗場地）")
show("同場同程 ≥2 戰 上名率 >2/3", lambda r: r["svn"] >= 2 and r["svp"]/r["svn"] > 2/3)
show("同程 ≥2 戰 上名率 >2/3 但同場同程 <2 戰", lambda r: r["sdn"] >= 2 and r["sdp"]/r["sdn"] > 2/3 and r["svn"] < 2)
