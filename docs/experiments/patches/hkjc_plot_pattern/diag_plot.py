"""EXP-20261123-05 診斷預先登記（Kelvin 轉嚟：「評分跌、近仗刻意轉程／轉配備、今仗返首本／戴返贏馬配備」三樣一齊睇）。
往績 = HKJC 馬匹頁（parsed/horses.jsonl.gz，日期嚴格早過今仗，香港賽事）；今仗評分／配備 = 馬匹頁今仗嗰行（賽前已公佈）。
  A  馬齡 4–6（進口年份＋類別推算，同 EXP-20261119-01）而且 今仗評分 ≤ 最近一次贏馬評分 − 10
  B  上 2–3 仗（最近 3 仗入面）有一仗路程 ≠ 首本，或者配備 ≠ 贏馬配備；首本 = 最近一次贏馬路程
  C  今仗路程 = 首本，或者今仗配備 = 贏馬配備而且上仗配備 ≠ 贏馬配備
  組合 = A∧B∧C；另報 A、B∧C、A∧C、A∧B
殘差 = 入頭三 − v5 校準 p（逐季 walk-forward，計馬匹數），同場置中版本一齊報。base = live（base_live_20261122）。只做診斷。
"""
import gzip, json, re, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b
import hkjc_replay_compare_v5 as v5
V = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history"
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def iso(dmy): d, m, y = dmy.split("/"); return f"{y}-{m}-{d}"
def num(x):
    try: return float(str(x).strip())
    except ValueError: return None
def gset(g): return frozenset(x for x in re.split(r"[/\s]+", re.sub(r"[-12]", "", str(g or "").upper())) if x and x != "")
runs, imp = defaultdict(list), {}
for line in gzip.open(f"{V}/parsed/horses.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line); m = re.match(r"HK_(\d{4})_([A-Z]\d{3})", r["horse_id"])
    if not m: continue
    code = m.group(2); cat = (r.get("profile") or {}).get("進口類別") or ""
    imp[code] = (int(m.group(1)), 3 if "新馬" in cat else 4)
    for q in r.get("runs") or []:
        vt = str(q.get("venue_track") or "")
        if not (vt.startswith("沙田") or vt.startswith("跑馬地")): continue
        try: d = iso(q["date"])
        except Exception: continue
        ps = str(q.get("pos") or "").strip()
        runs[code].append({"d": d, "dist": num(q.get("distance")), "pos": int(ps) if ps.isdigit() else None, "rating": num(q.get("rating")), "gear": gset(q.get("gear"))})
for v in runs.values(): v.sort(key=lambda t: t["d"])
idx = b.load_index(); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
def feats(c, d0, dist):
    rr = runs.get(c) or []
    today = next((t for t in rr if t["d"] == d0), None)
    prev = [t for t in rr if t["d"] < d0]
    if today is None or not prev or not dist: return None
    wins = [t for t in prev if t["pos"] == 1]
    if not wins: return None
    w = wins[-1]; home, wgear = w["dist"], w["gear"]
    age = int(d0[:4]) - imp[c][0] + imp[c][1] if c in imp else None
    A = bool(age and 4 <= age <= 6 and today["rating"] is not None and w["rating"] is not None and today["rating"] <= w["rating"] - 10)
    last3 = prev[-3:]
    B = any((t["dist"] != home) or (t["gear"] != wgear) for t in last3[-3:]) and len(last3) >= 2
    C = (dist == home) or (today["gear"] == wgear and prev[-1]["gear"] != wgear)
    return {"A": A, "B": B, "C": C}
rows = [x for x in map(json.loads, open(f"{V}/analysis/replay_all/v4/cons/base_live_20261122.jsonl")) if "horses" in x]
par = {s: v5.fit([x for x in rows if 2019 <= season(x["date"]) < s]) for s in sorted({season(x["date"]) for x in rows}) if s >= 2020}
recs = []
for x in rows:
    s = season(x["date"])
    if s not in par: continue
    keep = [h for h in x["horses"] if h["pos"]]; n = len(keep)
    r = np.array([h["raw"] for h in keep]); rc = r - r.mean(); a, bb, g = par[s]
    p = 1 / (1 + np.exp(-(a + bb * rc + g * v5.field_logit(n)))); y = np.array([int(h["pos"] <= 3) for h in keep]); res = y - p; resc = res - res.mean()
    rank = (-r).argsort().argsort() + 1
    for j, h in enumerate(keep):
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        f = feats(c, x["date"], x.get("distance")) if c else None
        if f is None: continue
        recs.append(dict(w="dev" if s <= 2023 else "hold", y=y[j], p=p[j], rc=resc[j], rank=rank[j], win=int(h["pos"] == 1), **f))
rng = np.random.default_rng(0)
def show(lab, sel):
    out = []
    for w in ("dev", "hold"):
        v = [r for r in recs if r["w"] == w and sel(r)]
        if len(v) < 30: out.append(f"n={len(v)}"); continue
        e = np.array([r["y"] - r["p"] for r in v]); ec = np.array([r["rc"] for r in v])
        bt = [e[rng.integers(0, len(e), len(e))].mean() for _ in range(400)]
        out.append(f"{100*e.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] 同場 {100*ec.mean():+.1f} 實{100*np.mean([r['y'] for r in v]):.0f}% 贏{100*np.mean([r['win'] for r in v]):.0f}% 模型排{np.mean([r['rank'] for r in v]):.1f} n={len(v)}")
    print(f"{lab}｜dev {out[0]}｜holdout {out[1]}")
print("有贏過嘅馬次", len(recs))
show("A 評分跌 ≥10（4–6 歲）", lambda r: r["A"])
show("B 近仗轉程／轉配備", lambda r: r["B"])
show("C 今仗返首本／戴返贏馬配備", lambda r: r["C"])
show("B∧C", lambda r: r["B"] and r["C"])
show("A∧C", lambda r: r["A"] and r["C"])
show("A∧B", lambda r: r["A"] and r["B"])
show("A∧B∧C（組合）", lambda r: r["A"] and r["B"] and r["C"])
show("A 但冇 C", lambda r: r["A"] and not r["C"])
