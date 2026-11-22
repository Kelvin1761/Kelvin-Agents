"""EXP-20261122-26 預先登記（Kelvin 2026-11-22「長程馬會跑縮程熱身再返首本」，例：天將龍駒 1600→2000 贏；回放尺 v5；家族 1）
定義（寫喺跑之前，冇睇呢個子集嘅殘差）：熱身返首本 =
  今仗 − 上仗 ≥ 400（即 live D1 旗）而且 上仗係休後復出（上仗距再上一仗 ≥ 60 日；或者上仗係香港第一仗唔計）
  而且 今仗路程 ±100 米內香港往績上過名（日期嚴格早過今仗）。
  W1  呢類馬唔扣大幅增程（剷走佢哋嘅 D1 旗，其他馬 D1 照用 β −0.926），場內重新置中。零擬合參數。
判：hkjc_replay_compare_v5.py；dev 唔過唔開 holdout；唔准換門檻（60 日、±100 米）救。
"""
import gzip, json, re, sys
from collections import defaultdict
from datetime import date
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b
D1_BETA = -0.926
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
            if hk(q.get("venue_track")):
                ps = str(q.get("pos") or "").strip(); dist = float(str(q.get("distance")).strip())
                runs[code].append((iso(q["date"]), dist, int(ps) if ps.isdigit() else None))
        except Exception: pass
for v in runs.values(): v.sort()
idx = b.load_index(); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
nd1 = nprep = 0
with open(sys.argv[2], "w") as f:
    for x in rows:
        dist = x.get("distance"); d1 = []; keep = []
        for h in x["horses"]:
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            prev = [t for t in runs.get(c, []) if t[0] < x["date"] and t[1]]
            on = prep = False
            if prev and dist:
                on = dist - prev[-1][1] >= 400
                if on and len(prev) >= 2:
                    gap = (date.fromisoformat(prev[-1][0]) - date.fromisoformat(prev[-2][0])).days
                    proven = any(t[2] and t[2] <= 3 and abs(t[1] - dist) <= 100 for t in prev)
                    prep = gap >= 60 and proven
            d1.append(float(on)); keep.append(float(on and not prep)); nd1 += on; nprep += prep
        d1, keep = np.array(d1), np.array(keep)
        add = (-D1_BETA) * (d1 - d1.mean()) + D1_BETA * (keep - keep.mean())
        hs = [dict(h, raw=round(h["raw"] + float(a), 4)) for h, a in zip(x["horses"], add)]
        y = dict(x, arm="prep_W1", horses=hs); y["picks"] = [h["n"] for h in sorted(hs, key=lambda h: -h["raw"])]
        f.write(json.dumps(y, ensure_ascii=False) + "\n")
print("D1 馬次", nd1, "熱身返首本（豁免）", nprep)
