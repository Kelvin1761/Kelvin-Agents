"""Kelvin 2026-11-19「排名表手動情境同即場 option 合唔合理」。
問：真係強偏差日（用同日其他場次判斷，唔用本場），按「慣性跑法」／「檔位區」分組嘅馬，喺 live 之上實際多咗幾多入頭三？
手動情境假設 ±10pp（EXP-20261117-08，用實際走位量）。慣性 = 之前最多 3 仗第一個沿途位 ÷ 匹數平均，用 run_style.classify（同引擎一個標準）。
用法：python3 diag_scenario_magnitude.py <live dump>
"""
import gzip, json, re, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts")
from diag import season  # noqa: E402
from diag_full import calibrate  # noqa: E402
import hkjc_history_replay_build as b  # noqa: E402
from hkjc_racing_engine import run_style as rs  # noqa: E402

first = defaultdict(list)   # code -> [(date, frac)]
for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/sectionals.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line); hs = [h for h in r["horses"] if h.get("sections") and str(h.get("finish", "")).isdigit()]
    for h in hs:
        p = h["sections"][0].get("pos")
        if isinstance(p, int): first[h["code"]].append((r["date"], r["race_no"], rs.fraction(p, len(hs))))
for v in first.values(): v.sort()
idx = b.load_index(); meta = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        try: dr = int(row.get("draw"))
        except (TypeError, ValueError): dr = None
        meta[(d, n, str(row.get("horse_no")))] = (m.group(1) if m else None, dr)
def bucket(d): return None if d is None else ("內" if d <= 4 else "中" if d <= 9 else "外")
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
calib = calibrate(rows); recs = []
for x in rows:
    s = season(x["date"])
    if not 2020 <= s <= 2025: continue
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean(); a, bb = calib[s]
    for h, z in zip(hs, rc):
        code, dr = meta.get((x["date"], x["race"], str(h["n"])), (None, None))
        if not code: continue
        own = next((f for d, n, f in first[code] if d == x["date"] and n == x["race"]), None)
        prev = [f for d, n, f in first[code] if d < x["date"]][-3:]
        recs.append(dict(day=(x["date"], x.get("venue")), race=x["race"], s=s, res=int(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + bb * z))),
                         actual=rs.classify(own) if own is not None else None, habit=rs.classify(float(np.mean(prev))) if prev else None,
                         draw=bucket(dr)))
print("馬次", len(recs))
by_day = defaultdict(list)
for r in recs: by_day[r["day"]].append(r)
# 每匹：同日「其他場次」嘅實際偏差（某類實際走位／檔位區殘差均值）
def other_bias(r, key, val):
    g = [o["res"] for o in by_day[r["day"]] if o["race"] != r["race"] and o[key] == val]
    return np.mean(g) if len(g) >= 8 else None
for key_bias, key_horse, vals, lab in (("actual", "habit", ("放頭", "守中", "後上"), "跑法（日偏差用實際走位、馬用慣性）"),
                                       ("actual", "actual", ("放頭", "守中", "後上"), "跑法（馬用實際走位 = 賽後先知，上限）"),
                                       ("draw", "draw", ("內", "中", "外"), "檔位區")):
    print(f"\n== {lab}")
    for v in vals:
        out = []
        for lo, hi in ((2020, 2023), (2024, 2025)):
            sel = [r for r in recs if lo <= r["s"] <= hi and r[key_horse] == v]
            ob = [(other_bias(r, key_bias, v), r["res"]) for r in sel]
            ob = [(o, y) for o, y in ob if o is not None]
            strong = [y for o, y in ob if o >= 0.10]; weak = [y for o, y in ob if abs(o) < 0.03]
            out.append(f"強偏差日(+10pp) {100*np.mean(strong):+.1f}pp n={len(strong)}｜平常日 {100*np.mean(weak):+.1f} n={len(weak)}")
        print(f"  {v}：dev {out[0]} ‖ ho {out[1]}")
