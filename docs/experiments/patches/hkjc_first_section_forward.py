"""EXP-20261016-33 forward 退回條件判定（預先登記，唔准改）。

用法：
  python3 hkjc_first_section_forward.py live.jsonl counterfactual.jsonl

live = 現行 code（有最快第一段）；counterfactual = `--arm hkjc_arm_no_first_section.py`。
兩個都要用 `hkjc_eval_harness.py run --since <登記嘅開始日>` 跑。
"""
import glob
import json
import sys

ROOT = open(".wongchoi_hk_data_root").read().strip()


def load(path):
    return {(r["meeting"], r["race"]): r for r in map(json.loads, open(path))
            if "error" not in r and "speed_score" not in r.get("meeting_dead_fields", [])}


live, cf = load(sys.argv[1]), load(sys.argv[2])
keys = sorted(k for k in live if k in cf)
placed = {}
for meeting in {k[0] for k in keys}:
    for rn, race in json.load(open(glob.glob(f"{ROOT}/{meeting}/*全日賽果.json")[0])).items():
        for x in race.get("results", []):
            try:
                placed[(meeting, int(rn), int(x["horse_no"]))] = int(x["pos"]) <= 3
            except (ValueError, KeyError, TypeError):
                pass

swap_net = 0
for k in keys:
    a, b = live[k]["picks"][:2], cf[k]["picks"][:2]
    swap_net += sum(placed.get((k[0], int(k[1]), h), False) for h in a if h not in b)
    swap_net -= sum(placed.get((k[0], int(k[1]), h), False) for h in b if h not in a)
n = len(keys)
good = sum(live[k]["good_positional"] - cf[k]["good_positional"] for k in keys) / n * 100 if n else 0.0
gold = sum(live[k]["gold"] - cf[k]["gold"] for k in keys) / n * 100 if n else 0.0
print(f"races={n}  頭2換馬淨上名={swap_net:+d}  Good Δ={good:+.2f}pp  Gold Δ={gold:+.2f}pp")

if n < 60:
    verdict = "WAIT（未夠 60 場）"
elif n < 150:
    verdict = "REVERT（中期止蝕：淨上名 ≤ −3）" if swap_net <= -3 else "CONTINUE（中期檢查通過，等夠 150 場）"
else:
    fail = swap_net <= 0 or good < 0 or gold < -1.0
    verdict = "REVERT" if fail else "KEEP（forward 同方向；仍然唔係已證實改善）"
print("判定:", verdict)
