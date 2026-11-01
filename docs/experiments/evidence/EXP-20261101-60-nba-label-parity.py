"""EXP-20261101-60 R1 gate: training labels from the ESPN-only results path.

usage: python3 EXP-20261101-60-nba-label-parity.py <verified_dataset_v2/dataset.csv> <scratch dir>

Re-fetches every US game date of the 49-event corpus through
build_nba_ml_dataset.fetch_results_for_date (ESPN only) into <scratch>, re-labels
the same rows with match_results, and compares hit/actual_value per row.
"""
import collections
import csv
import json
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo / ".agents/scripts/nba_ml"))
import build_nba_ml_dataset as B  # noqa: E402

dataset, scratch = Path(sys.argv[1]), Path(sys.argv[2])
scratch.mkdir(parents=True, exist_ok=True)
B.DATASET_DIR = str(scratch)
rows = [r for r in csv.DictReader(dataset.open()) if r.get("hit") not in ("", None)]
by_date = collections.defaultdict(list)
for r in rows:
    by_date[r["game_date"]].append(r)
compared = same = 0
diffs, missing = [], collections.Counter()
for day, group in sorted(by_date.items()):
    path = B.fetch_results_for_date(day)
    fresh = [{"game_tag": r["game_tag"], "game_date": r["game_date"], "team": r["team"], "player": r["player"],
              "stat_category": r["stat_category"], "line_value": float(r["line_value"])} for r in group]
    B.match_results(fresh, B.load_results_brief(path) if path else {})
    for old, new in zip(group, fresh):
        if "hit" not in new:
            missing[(day, old["game_tag"])] += 1
            continue
        compared += 1
        if int(float(old["hit"])) == new["hit"] and float(old["actual_value"]) == float(new["actual_value"]):
            same += 1
        else:
            diffs.append((day, old["game_tag"], old["player"], old["stat_category"], old["line_value"],
                          old["actual_value"], old["hit"], new["actual_value"], new["hit"]))
flips = [d for d in diffs if int(float(d[6])) != d[8]]
out = {"labelled_rows": len(rows), "dates": len(by_date), "relabelled": compared, "identical": same,
       "actual_differs": len(diffs), "hit_flips": len(flips), "not_relabelled": sum(missing.values()),
       "not_relabelled_by_event": {f"{d} {t}": n for (d, t), n in sorted(missing.items())},
       "differences": diffs}
(scratch / "label_parity.json").write_text(json.dumps(out, indent=1))
print(json.dumps({k: v for k, v in out.items() if k != "differences"}, indent=1))
for d in diffs[:30]:
    print(" ", d)
