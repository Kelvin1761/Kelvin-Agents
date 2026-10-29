"""§7 strata (field size ×4, base top-pick SP ×5): Gold / Good deltas, meeting-day bootstrap."""
import json, glob, random, sys
from collections import defaultdict
ROOT = "/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing"
base, cand = sys.argv[1], sys.argv[2]
B = {(r["meeting"], r["race"]): r for r in map(json.loads, open(base)) if "picks" in r and "speed_score" not in (r.get("meeting_dead_fields") or [])}
C = {(r["meeting"], r["race"]): r for r in map(json.loads, open(cand)) if "picks" in r}
sp = {}
for f in glob.glob(ROOT + "/*/*全日賽果.json"):
    m = f.split("/")[-2]
    for rn, rr in json.load(open(f)).items():
        for x in rr.get("results", []):
            try: sp[(m, int(rn), str(x["horse_no"]))] = float(x["win_odds"])
            except Exception: pass
def fbucket(n): return "≤8" if n <= 8 else "9-10" if n <= 10 else "11-12" if n <= 12 else "13+"
def sbucket(o):
    if o is None: return "SP?"
    return "≤2" if o <= 2 else "2-4" if o <= 4 else "4-7" if o <= 7 else "7-12" if o <= 12 else ">12"
rows = []
for k, b in B.items():
    c = C.get(k)
    if not c: continue
    top = str(b["picks"][0]) if b["picks"] else None
    o = sp.get((k[0], int(k[1]), top))
    rows.append(dict(day=b["date"], f=fbucket(b["field"]), s=sbucket(o),
                     dg=c["gold"] - b["gold"], dd=c["good_positional"] - b["good_positional"]))
random.seed(20261029)
def boot(sub, key):
    days = defaultdict(list)
    for r in sub: days[r["day"]].append(r[key])
    ds = list(days); est = sum(r[key] for r in sub) / len(sub)
    sims = []
    for _ in range(2000):
        pick = [random.choice(ds) for _ in ds]; vals = [v for d in pick for v in days[d]]
        sims.append(sum(vals) / len(vals))
    sims.sort(); return est, sims[50], sims[1949]
bad = 0
for col, order in (("f", ["≤8", "9-10", "11-12", "13+"]), ("s", ["≤2", "2-4", "4-7", "7-12", ">12", "SP?"])):
    for g in order:
        sub = [r for r in rows if r[col] == g]
        if len(sub) < 5: continue
        out = []
        for key, name in (("dg", "Gold"), ("dd", "Good")):
            e, lo, hi = boot(sub, key); out.append(f"{name} {e*100:+.2f}pp [{lo*100:+.2f},{hi*100:+.2f}]")
            if hi < 0: bad += 1; out[-1] += " ❌"
        print(f"  {('馬匹數' if col=='f' else '首選SP')} {g:6s} n={len(sub):3d}  " + "  ".join(out))
print("strata with CI fully negative:", bad)
