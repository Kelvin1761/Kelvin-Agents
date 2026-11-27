"""EXP-20261127-40 secondary (report only): Brier, calibration, acc@0.5 for MS2 vs p_final on the frozen EXP-20261111-05 window."""
import json, sys, random
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import evaluate as ev
legs = ev.load(); used = ev.window(legs); days = sorted({x["day"] for x in used})
print("window", days[0], days[-1], len(days), len(used))
rows = []
for day in days:
    recs = ev._read(ev.LEDGER / f"{day}.jsonl")
    model, result = {}, {}
    for r in recs:
        if r.get("row_type") == "model_obs":
            if r.get("post_tip") or r.get("snapshot_role") != "production" or r.get("market") not in ev.STAT: continue
            if any(r.get(k) is None for k in ("p_final", "p_s", "p_s2", "price_at_model", "line")): continue
            k = (r["game_tag"], r["player"], r["market"], float(r["line"]))
            if k not in model or str(r["recorded_at"]) < str(model[k]["recorded_at"]): model[k] = r
        elif r.get("row_type") == "settlement" and r.get("y") is not None and r.get("line") is not None:
            result.setdefault((r["game_tag"], r["player"], r["market"], float(r["line"])), int(r["y"]))
    for k, r in model.items():
        if k not in result or float(r["price_at_model"]) <= 1: continue
        st = ev.STAT[k[2]]; pr = float(r["price_at_model"])
        rows.append({"day": day, "y": result[k], "pub": float(r["p_final"]),
                     "ms2": ev.blend("MS2", st, pr, float(r["p_s2"])), "msr": ev.blend("MSR", st, pr, float(r["p_s"])),
                     "mkt": min(1, 1 / pr)})
print("rows", len(rows), "(evaluator n", len(used), ")")
def brier(a): return sum((x[a] - x["y"]) ** 2 for x in rows) / len(rows)
for a in ("pub", "ms2", "msr"): print(a, "brier %.5f" % brier(a), "mean p %.4f" % (sum(x[a] for x in rows) / len(rows)))
print("base rate %.4f" % (sum(x["y"] for x in rows) / len(rows)))
by = defaultdict(list)
for x in rows: by[x["day"]].append((x["ms2"] - x["y"]) ** 2 - (x["pub"] - x["y"]) ** 2)
keys = sorted(by); rnd = random.Random(20261111); vals = []
for _ in range(2000):
    s = [v for k in (rnd.choice(keys) for _ in keys) for v in by[k]]; vals.append(sum(s) / len(s))
vals.sort(); print("brier delta ms2-pub %.5f CI [%.5f, %.5f]" % (sum(sum(v) for v in by.values()) / len(rows), vals[49], vals[1949]))
bins = [0, .2, .4, .6, .8, .9, 1.0001]
print("bin(by pub) | n | actual | pub | ms2")
for lo, hi in zip(bins, bins[1:]):
    s = [x for x in rows if lo <= x["pub"] < hi]
    if s: print(f"{lo:.1f}-{min(hi,1):.1f} | {len(s)} | {sum(x['y'] for x in s)/len(s):.3f} | {sum(x['pub'] for x in s)/len(s):.3f} | {sum(x['ms2'] for x in s)/len(s):.3f}")
print("bin(by ms2) | n | actual | ms2")
for lo, hi in zip(bins, bins[1:]):
    s = [x for x in rows if lo <= x["ms2"] < hi]
    if s: print(f"{lo:.1f}-{min(hi,1):.1f} | {len(s)} | {sum(x['y'] for x in s)/len(s):.3f} | {sum(x['ms2'] for x in s)/len(s):.3f}")
for a in ("pub", "ms2"):
    hit = sum((x[a] >= .5) == (x["y"] == 1) for x in rows) / len(rows); print(a, "acc@0.5 %.4f" % hit)
# banker zone
for thr in (0.7,):
    s = [x for x in rows if x["pub"] >= thr]
    print("pub>=0.7 n", len(s), "actual %.3f pub %.3f ms2 %.3f" % (sum(x['y'] for x in s)/len(s), sum(x['pub'] for x in s)/len(s), sum(x['ms2'] for x in s)/len(s)))
# per-day sign
neg = sum(1 for k in keys if sum(v for v in by[k]) < 0); print("days brier ms2 better", neg, "/", len(keys))
