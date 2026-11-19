import gzip, json, re, sys
from collections import defaultdict
from datetime import date
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
import hkjc_history_replay_build as b
from diag_full import calibrate
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def iso(dmy):
    d, m, y = dmy.split("/"); return f"{y}-{m}-{d}"
runs = defaultdict(list)
for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/horses.jsonl.gz", "rt"):
    r = json.loads(line); code = r["horse_id"].rsplit("_", 1)[-1]
    for q in r.get("runs") or []:
        if str(q.get("venue_track") or "").startswith(("沙田", "跑馬地")):
            try: runs[code].append((iso(q["date"]), q.get("pos"), q.get("class"), q.get("win_odds")))
            except Exception: pass
for v in runs.values(): v.sort()
idx = b.load_index(); meta = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        meta[(d, n, str(row.get("horse_no")))] = (m.group(1) if m else None, row.get("horse_name"), row.get("win_odds"), row.get("trainer"))
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
calib = calibrate(rows)
tcount = defaultdict(int)
for race in idx["results"].values():
    for row in race.get("results", []): tcount[str(row.get("trainer") or "").strip()] += 1
LOCAL = {t for t, c in tcount.items() if c >= 300}
print("本地練馬師（≥300 馬次）", len(LOCAL))
cases = []
for x in rows:
    if season(x["date"]) < 2020: continue
    a, bb = calib[season(x["date"])]
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
    rk = {h["n"]: i + 1 for i, h in enumerate(sorted(hs, key=lambda h: -h["raw"]))}
    for h, z in zip(hs, rc):
        code, name, odds, tr = meta.get((x["date"], x["race"], str(h["n"])), (None,) * 4)
        prev = [t for t in runs.get(code, []) if t[0] < x["date"]]
        if not prev or len(prev) > 2 or str(tr or "").strip() not in LOCAL: continue
        gap = (date.fromisoformat(x["date"]) - date.fromisoformat(prev[-1][0])).days
        if gap <= 180: continue
        lastwon = str(prev[-1][1]).strip().lstrip("0") == "1"
        cases.append(dict(d=x["date"], race=x["race"], name=name, tr=tr, n=len(prev), gap=gap, rk=rk[h["n"]], pos=h["pos"],
                          odds=odds, p=1/(1+np.exp(-(a+bb*z))), lastwon=lastwon, cls=prev[-1][2], field=len(hs)))
print("同類馬（≤2 仗、休 >180 日）", len(cases))
def summ(sel, lab):
    if not sel: print(lab, "n=0"); return
    y = [c["pos"] <= 3 for c in sel]; w = [c["pos"] == 1 for c in sel]
    print(f"{lab}: n={len(sel)}  入位 {100*np.mean(y):.0f}%（模型估 {100*np.mean([c['p'] for c in sel]):.0f}%）  贏 {100*np.mean(w):.0f}%")
summ(cases, "全部")
for lo, hi in ((1, 2), (3, 5), (6, 99)): summ([c for c in cases if lo <= c["rk"] <= hi], f"  模型排 {lo}-{hi}")
summ([c for c in cases if c["lastwon"]], "上仗贏")
summ([c for c in cases if c["lastwon"] and c["rk"] <= 2], "  上仗贏＋模型排 1-2")
summ([c for c in cases if c["n"] == 1], "得 1 仗")
summ([c for c in cases if c["n"] == 1 and c["rk"] <= 2], "  得 1 仗＋模型排 1-2")
print("\n模型排 1-2 嘅個案：")
for c in sorted([c for c in cases if c["rk"] <= 2], key=lambda c: c["d"]):
    print(f"  {c['d']} R{c['race']:<2} {c['name']:<12} {c['tr']:<5} 前{c['n']}仗 上仗{'贏' if c['lastwon'] else '輸'}({c['cls']}) 休{c['gap']}日  模型排{c['rk']}  ${c['odds']:<5} → 第{c['pos']}名")
