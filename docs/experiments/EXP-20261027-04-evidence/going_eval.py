"""Stage 4 v3 verdict for the race-time going A/B (fixed_rule; unchanged races enter as identical pairs)."""
import collections, json, sys
from pathlib import Path

WT = "/Users/imac/Antigravity-worktrees/claude-going-ab-20261027/.agents/skills/shared_racing"
sys.path.insert(0, WT); sys.path.insert(0, WT + "/race_reflector/scripts")
from eval_metrics import race_metrics  # noqa: E402
from model_evaluation_decision import evaluate_full_record  # noqa: E402
from unified_reflector_core import load_structured_results  # noqa: E402

S = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/claude-au-going-ab-20261027")
AU = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing")
SCR = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/8642939c-b0ef-4bdf-8853-73c9f334012f/scratchpad")
KEYS = ("gold", "good_positional", "top3_capture_at5", "ndcg_at5", "competitive_recall_at5")

jobs = {(m, int(r)): g for m, r, g in json.load(open(S / "jobs.json"))}
res_cache = {}


def results(meeting):
    if meeting not in res_cache:
        d = AU / "Archive" / meeting
        if not d.exists():
            d = AU / meeting
        res_cache[meeting] = load_structured_results("au", d / "Race_Results_Reflector.md")
    return res_cache[meeting]


def metrics(meeting, race, arm):
    L = json.loads((S / arm / meeting / f"Race_{race}_Logic.json").read_text())
    info = results(meeting)[race]
    scratched = set(info.get("scratched_horse_numbers") or [])
    pos = {r["horse_no"]: int(r["placing"]) for r in info["results"] if str(r.get("placing", "")).isdigit()}
    ranked = sorted((h["python_auto"]["rank"], int(n)) for n, h in L["horses"].items()
                    if (h.get("python_auto") or {}).get("rank") and int(n) not in scratched)
    picks = [n for _, n in ranked]
    m = race_metrics(picks, {h for h, p in pos.items() if p <= 3}, actual_pos=pos)
    row = {k: m[k] for k in KEYS}
    row["mean_top3_model_rank"] = m["top3_mean_model_rank"]
    row["top1_win"] = m["pick_positions"][0] == 1
    row["top1_place"] = (m["pick_positions"][0] or 99) <= 3
    return row, picks[:4]


rows = json.load(open(SCR / "tier_rows.json"))
dates, base, cand, changed = [], [], [], []
skipped = 0
for r in sorted(rows, key=lambda x: (x["date"], x["meeting"], x["race"])):
    key = (r["meeting"], int(r["race"]))
    if key in jobs:
        a_ok = (S / "A" / r["meeting"] / f".done_{r['race']}").exists()
        b_ok = (S / "B" / r["meeting"] / f".done_{r['race']}").exists()
        if not (a_ok and b_ok):
            skipped += 1
            continue
        a, ta = metrics(r["meeting"], r["race"], "A")
        b, tb = metrics(r["meeting"], r["race"], "B")
        changed.append((r, a, b, ta != tb, ta[:1] != tb[:1]))
    else:
        a = b = {k: 0.0 for k in KEYS + ("mean_top3_model_rank", "top1_win", "top1_place")}
    dates.append(r["date"]); base.append(a); cand.append(b)

print(f"full record {len(dates)} races / {len(set(dates))} days; going-mismatch races {len(changed)} (skipped {skipped})")
print(f"  top-4 changed {sum(c[3] for c in changed)}  top pick changed {sum(c[4] for c in changed)}")
for k in ("gold", "good_positional", "top1_place", "top1_win", "top3_capture_at5"):
    A = sum(float(c[1][k]) for c in changed) / len(changed); B = sum(float(c[2][k]) for c in changed) / len(changed)
    print(f"  mismatch subset {k:18} A {100*A:5.1f}  B {100*B:5.1f}  Δ {100*(B-A):+5.2f}pp")
v = evaluate_full_record(domain="au", mode="fixed_rule", dates=dates, baseline_rows=base, candidate_rows=cand,
                         leakage_audit_passed=True)
print(json.dumps(v, ensure_ascii=False, indent=1, default=str)[:4000])
json.dump({"verdict": v, "n": len(dates)}, open(S / "verdict.json", "w"), ensure_ascii=False, default=str)
