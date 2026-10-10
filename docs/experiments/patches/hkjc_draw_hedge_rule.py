"""Pre-registered: draw-hedge selection rule (fixed, nothing fitted)."""
import json, sys
sys.path.insert(0, "/private/tmp/wc-stage4v3-20261010/.agents/skills/shared_racing")
from eval_metrics import race_metrics
GAP = float(sys.argv[2]); OUT = sys.argv[3]
rows = [json.loads(l) for l in open(sys.argv[1])]
rows = [r for r in rows if r.get("horses") and "speed_score" not in (r.get("meeting_dead_fields") or [])]
def emit(r, picks, arm):
    pos = {h["n"]: h["pos"] for h in r["horses"] if h.get("pos")}
    m = race_metrics(picks, [n for n, p in pos.items() if p <= 3], actual_pos=pos)
    m["mean_top3_model_rank"] = m.get("top3_mean_model_rank")
    o = {k: r[k] for k in ("date", "meeting", "race", "venue", "awt", "distance", "field")}
    o.update({"arm": arm, "picks": picks, "meeting_dead_fields": r.get("meeting_dead_fields", [])})
    o.update({k: m.get(k) for k in ("gold", "gold_strict", "good_positional", "champion", "top3_capture_at5", "ndcg_at5", "competitive_recall_at5", "mean_top3_model_rank")})
    return o
base, cand, swaps = [], [], 0
for r in rows:
    hs = sorted(r["horses"], key=lambda h: -h["raw"])
    picks = [h["n"] for h in hs]
    base.append(emit(r, picks, "base"))
    shapes = sorted(h["m"].get("race_shape", 60) for h in hs); med = shapes[len(shapes) // 2]
    new = list(picks)
    if len(hs) >= 6 and all(h["m"].get("race_shape", 60) > med for h in hs[:3]):
        for i in range(3, 6):
            if hs[i]["m"].get("race_shape", 60) <= med and hs[2]["raw"] - hs[i]["raw"] <= GAP:
                new.insert(2, new.pop(i)); swaps += 1; break
    cand.append(emit(r, new, f"hedge{GAP}"))
for name, data in (("base", base), ("cand", cand)):
    with open(f"{OUT}_{name}.jsonl", "w") as f:
        f.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in data)
print("races", len(rows), "swaps", swaps)
