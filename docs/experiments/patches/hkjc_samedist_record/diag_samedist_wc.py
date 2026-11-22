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
            cl = str(q.get("class") or "").strip()
            if vk: runs[code].append((iso(q["date"]), float(q["distance"]), int(ps) if ps.isdigit() else None, vk, int(cl) if cl.isdigit() else (0 if cl else None)))
        except Exception: pass
idx = b.load_index(); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
CLS = {}
for (d, n), race in idx["results"].items():
    c = str((race.get("_header") or {}).get("RaceClass") or "")
    m = re.match(r"Class (\d)", c); CLS[(d, n)] = int(m.group(1)) if m else (0 if c.startswith(("Group", "Griffin")) else None)
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
        tc = CLS.get((x["date"], x["race"]))
        sdw = sum(1 for t in sd if t[2] == 1)
        plc = [t[4] for t in sd if t[2] and t[2] <= 3 and t[4] is not None]
        # 班次數字細 = 高班；0 = 分級／新馬（當最高）
        hi = tc is not None and any((c2 < tc) for c2 in plc)
        same = tc is not None and any(c2 == tc for c2 in plc)
        lo_only = tc is not None and plc and all(c2 > tc for c2 in plc)
        recs.append(dict(w="dev" if s <= 2023 else "hold", y=int(h["pos"] <= 3), p=p[j], n_all=len(prev), allpl=allpl,
                         sdn=sdn, sdp=sdp, svn=svn, svp=svp, sdw=sdw, hi=hi, same=same, lo_only=bool(lo_only)))
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
print("== 贏 vs 上名（同程任何場地）")
show("同程有贏過", lambda r: r["sdw"] >= 1)
show("同程贏過 ≥2 次", lambda r: r["sdw"] >= 2)
show("同程有上名但冇贏過", lambda r: r["sdp"] >= 1 and r["sdw"] == 0)
show("同程 1 次上名、冇贏", lambda r: r["sdp"] == 1 and r["sdw"] == 0)
show("同程 1 次贏、冇其他上名", lambda r: r["sdp"] == 1 and r["sdw"] == 1)
print("== 同程上名嗰陣嘅班次 vs 今仗班次（班次數字細 = 高班）")
show("同程喺更高班上過名（今仗降班）", lambda r: r["hi"])
show("同程喺同班上過名", lambda r: r["same"] and not r["hi"])
show("同程只喺更低班上過名（今仗升班）", lambda r: r["lo_only"])
show("同程有上名、但全部唔同班（只低班）且冇贏", lambda r: r["lo_only"] and r["sdw"] == 0)
