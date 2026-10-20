"""EXP-20261020-02 B1（官方傷患記錄 → 醫療事故 −12／+6）forward 一次性確認（預先登記，唔准改）。

用法：
  python3 hkjc_official_injury_forward.py live.jsonl candidate.jsonl

live = 現行 code（`OFFICIAL_INJURY_SCORING = "off"`）；candidate = `--arm hkjc_arm_official_injury_issue.py`。
兩個都要用 `hkjc_eval_harness.py run --since 2026-10-21` 跑。

規則（EXP-20261020-02 protocol「判決後」）：≥ 60 場**一次性**確認，Gold Δ、Good Δ、NDCG@5 Δ 三項全部 ≥ 0
→ CONFIRM（可以將預設改做 issue，要 Kelvin 用 保存.sh 發佈）；任何一項 < 0 → STAY_OFF。< 60 場 → WAIT。
"""
import json
import sys

FINAL_RACES = 60


def load(path):
    return {(r["meeting"], r["race"]): r for r in map(json.loads, open(path))
            if "error" not in r and "risk_score" not in (r.get("meeting_dead_fields") or [])}


live, cand = load(sys.argv[1]), load(sys.argv[2])
keys = sorted(k for k in live if k in cand)
n = len(keys)


def delta(metric):
    return sum(float(cand[k][metric]) - float(live[k][metric]) for k in keys) / n if n else 0.0


gold, good, ndcg = delta("gold") * 100, delta("good_positional") * 100, delta("ndcg_at5")
changed = sum(cand[k]["picks"] != live[k]["picks"] for k in keys)
print(f"races={n}  Gold Δ={gold:+.2f}pp  Good Δ={good:+.2f}pp  NDCG Δ={ndcg:+.4f}  排序改變={changed}場")

if n < FINAL_RACES:
    verdict = f"WAIT（未夠 {FINAL_RACES} 場）"
elif gold >= 0 and good >= 0 and ndcg >= 0:
    verdict = "CONFIRM（三項 ≥ 0；可以轉 issue，要你發佈；仍然唔係已證實改善）"
else:
    verdict = "STAY_OFF（有項 < 0；維持 off）"
print("判定:", verdict)
