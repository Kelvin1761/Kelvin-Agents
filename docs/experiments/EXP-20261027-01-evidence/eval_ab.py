"""Paired evaluation of old vs new engine replays (day-clustered bootstrap)."""
import csv, json, random, sys, collections
from pathlib import Path

S = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/claude-au-1016-replay-ab-20261027")
ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/Archive")
NEW = "/Users/imac/Antigravity-worktrees/claude-replay-new-20261027/.agents/skills/shared_racing"
sys.path.insert(0, NEW); sys.path.insert(0, NEW + "/race_reflector/scripts")
from eval_metrics import race_metrics  # noqa: E402
from unified_reflector_core import load_structured_results  # noqa: E402


def ranks(path):
    d = collections.defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        try:
            d[int(r["race_number"])].append((int(float(r["rank"])), int(r["horse_number"])))
        except (ValueError, KeyError):
            pass
    return {k: [h for _, h in sorted(v)] for k, v in d.items()}


rows = []
for name, _snap in json.load(open(S / "plan.json")):
    res_file = ROOT / name / "Race_Results_Reflector.md"
    o, n = S / "old" / name / "Meeting_Auto_Scoring.csv", S / "new" / name / "Meeting_Auto_Scoring.csv"
    if not (res_file.exists() and o.exists() and n.exists()):
        continue
    results = load_structured_results("au", res_file)
    old, new = ranks(o), ranks(n)
    for race, info in results.items():
        res = info.get("results") or []
        if len(res) < 3 or race not in old or race not in new:
            continue
        scratched = set(info.get("scratched_horse_numbers") or [])
        pos = {r["horse_no"]: int(r["placing"]) for r in res if str(r.get("placing", "")).isdigit()}
        top3 = {h for h, p in pos.items() if p <= 3}
        out = {}
        for arm, picks in (("old", old[race]), ("new", new[race])):
            picks = [h for h in picks if h not in scratched]
            m = race_metrics(picks, top3, actual_pos=pos)
            out[arm] = {
                "gold": bool(m["gold"]), "good": m["exclusive_label"] in ("Gold", "Good"),
                "pass": m["exclusive_label"] in ("Gold", "Good", "Pass"),
                "win": (m["pick_positions"][0] == 1), "top1_place": (m["pick_positions"][0] or 99) <= 3,
                "cap4": m["top3_capture_at4"] or 0.0, "ndcg5": m["ndcg_at5"] or 0.0, "rr": m["reciprocal_rank"] or 0.0,
                "top4": picks[:4],
            }
        rows.append({"date": name[:10], "meeting": name, "race": race, **out})

print(f"races {len(rows)}  meetings {len({r['meeting'] for r in rows})}  days {len({r['date'] for r in rows})}")
changed = sum(r["old"]["top4"] != r["new"]["top4"] for r in rows)
top1chg = sum(r["old"]["top4"][:1] != r["new"]["top4"][:1] for r in rows)
print(f"top-4 changed {changed}/{len(rows)}  top pick changed {top1chg}/{len(rows)}")
days = collections.defaultdict(list)
for r in rows:
    days[r["date"]].append(r)
random.seed(20261027)
print(f"{'metric':11} {'old':>7} {'new':>7} {'diff':>7}  95% CI (day-clustered)   P(new>old)")
for k in ("gold", "good", "pass", "top1_place", "win", "cap4", "ndcg5", "rr"):
    o = sum(float(r["old"][k]) for r in rows) / len(rows); n = sum(float(r["new"][k]) for r in rows) / len(rows)
    B = []
    keys = list(days)
    for _ in range(4000):
        s = [r for d in (random.choice(keys) for _ in keys) for r in days[d]]
        B.append(sum(float(r["new"][k]) - float(r["old"][k]) for r in s) / len(s))
    B.sort()
    sc = 100 if k in ("gold", "good", "pass", "top1_place", "win", "cap4") else 1
    print(f"{k:11} {o*sc:7.2f} {n*sc:7.2f} {(n-o)*sc:+7.2f}  [{B[100]*sc:+.2f}, {B[3900]*sc:+.2f}]   {sum(b > 0 for b in B)/len(B):.2f}")
print("\nby day (Gold+Good):")
for d in sorted(days):
    L = days[d]
    print(f"  {d} n={len(L):3}  old {100*sum(r['old']['good'] for r in L)/len(L):5.1f}  new {100*sum(r['new']['good'] for r in L)/len(L):5.1f}")
json.dump(rows, open(S / "paired_rows.json", "w"), ensure_ascii=False)
