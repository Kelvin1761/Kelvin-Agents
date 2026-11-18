"""EXP-20261119-01 預先登記（Kelvin 2026-11-19「通情達理得一仗」；Holm 家族 2）
狀態與穩定性按香港前出賽數 n 收縮：stab' = 60 + (stab − 60) × n/(n+k)；raw += 0.2451 × (stab' − stab)。
  K1 k=1   K2 k=2   （冇擬合；初出馬唔郁）
"""
import json, re, sys
from collections import defaultdict
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
idx = b.load_index(); hist = defaultdict(list); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if not m: continue
        code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
        if b._started(row): hist[m.group(1)].append(d)
for k, arm in ((1, "K1"), (2, "K2")):
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            hs = []
            for h in x["horses"]:
                c = code_of.get((x["date"], x["race"], str(h["n"])))
                n = sum(1 for d in hist.get(c, []) if d < x["date"])
                st = h["m"]["stability"]
                add = 0.0 if (h.get("debut") or n == 0) else 0.2451 * ((60 + (st - 60) * n / (n + k)) - st)
                hs.append(dict(h, raw=round(h["raw"] + add, 4)))
            y = dict(x, arm=f"stab_shrink_{arm}", horses=hs)
            y["picks"] = [h["n"] for h in sorted(hs, key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
