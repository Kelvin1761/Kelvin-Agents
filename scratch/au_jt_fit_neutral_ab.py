#!/usr/bin/env python3
"""`jockey_horse_fit_score`「冇證據」點位嘅 isolated A/B。

實測（713 場 / 7,547 匹，現行引擎）：
    高過 60（有正面配搭證據）  n=5,301  前三率 30.0%
    低過 60（被扣分）          n=  838  前三率 28.6%
    恰好 60（冇證據）          n=1,408  前三率 **21.7%**   ← 樣本平均 28.3%

即係排序錯咗：被扣分嗰批實際好過冇證據嗰批，但分數低過佢。
「冇人馬配搭證據」唔係「缺數據」—— 佢係一個真訊號（新／陌生騎師、
輕出賽馬），而且係負面訊號。所以佢唔應該坐喺中性 60。

⚠️ 呢個同 sectional 個案相反（嗰邊「冇 PI 數據」前三率 30.1% 高過平均，
所以要抬去 60）。唔可以照搬規則，要逐個 leaf 跟實測。

做法：只改「恰好 60」嗰批嘅值，掃唔同點位。其餘完全唔郁。
dev 85% / 未碰過 holdout 15%，同一把尺。唯讀。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/shared_racing"))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402

HERE = Path(__file__).resolve().parent
HOLDOUT = 0.15
LEAF = "jockey_horse_fit_score"
KEYS = ("gold", "good_pos", "good_any2", "champ", "winT3", "t3prec", "mrr",
        "blowout", "compet", "ndcg5")


def score_fold(races, no_evidence_value):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for h in race["rows"]:
            feats = dict(h["features"])
            if no_evidence_value is not None and abs(feats[LEAF] - 60.0) < 1e-6:
                feats[LEAF] = clip_score(no_evidence_value)
            mx = map_features_to_matrix_scores(feats)
            total = 60.0 + sum((mx[k] - 60.0) * w for k, w in MATRIX_WEIGHTS.items())
            scored.append((total + float(h["wet"] or 0.0), h["n"]))
        picks = [n for _, n in sorted(scored, key=lambda kv: (-kv[0], kv[1]))]
        out.append(race_metrics(picks, top3, winner=winners[0] if winners else None,
                               actual_pos=actual_pos, field_size=race["field"]))
    return summarize_races(out)


def digest(s):
    r, c = s["rates"], s["competitiveness"]
    return {"gold": s["counts"]["gold"], "good_pos": round(100 * r["good_positional"], 2),
            "good_any2": round(100 * r["good_any2"], 2),
            "champ": round(100 * r["champion"], 2),
            "winT3": round(100 * r["winner_in_top3"], 2),
            "t3prec": round(100 * s["top3_precision"], 2), "mrr": round(s["mrr"], 4),
            "blowout": round(100 * c["top_pick_blowout"]["rate"], 2),
            "compet": round(100 * c["top_pick_competitive"]["rate"], 2),
            "ndcg5": round(c["mean_ndcg_at5"], 4)}


def main():
    races = json.loads((HERE / "au_live_leaves_off.json").read_text(encoding="utf-8"))["races"]
    split = int(len(races) * (1 - HOLDOUT))
    n_affected = sum(1 for r in races for h in r["rows"]
                     if abs(h["features"][LEAF] - 60.0) < 1e-6)
    total = sum(len(r["rows"]) for r in races)
    print(f"races {len(races)}  runners {total}  「恰好 60」{n_affected} "
          f"({100*n_affected/total:.1f}%)")

    for name, fold in (("dev", races[:split]), ("holdout", races[split:])):
        base = digest(score_fold(fold, None))
        print(f"\n===== {name} ({len(fold)} races) =====")
        print(f"{'冇證據點位':14}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'60（現行）':14}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for value in (58.0, 56.0, 54.0, 52.0):
            d = digest(score_fold(fold, value))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += (f"{d[k]:>7}({delta:+d})".rjust(13) if k == "gold"
                          else f"{d[k]:>7}{delta:+.2f}".rjust(13))
            print(f"{f'{value:g}':14}" + cells)


if __name__ == "__main__":
    main()
