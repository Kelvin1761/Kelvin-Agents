#!/usr/bin/env python3
"""PF backfill 開 vs 關，喺**現行**引擎 + 現行權重下逐個指標比較。

點解要重測：另一條工作線 2026-08-01 早些時候量到「PF 開令模型變差」
（gold 37→34、champ −1.55、t3prec −0.94），但嗰個量度之後陸續落咗：
  * sectional base 35.8→60（bonus ×0.753864）、pace_map base 55.7→60
  * weight_score 移出 matrix、`_handicap_weight_proxy`
  * 矩陣權重重新配過（stability .299→.437、pace_perf .188→.261…）
  * 馬群大細百分位 base、PI 競爭力封頂、L600 改用平均、獎金班次調整、統一上名率
所以嗰個結論要喺新配置下重驗。

⚠️ holdout（最後 15%）係最近期 meeting，本身已經有 live Formguide PF，
backfill 對佢冇作用 —— 所以 holdout 應該完全唔郁。dev 先係真正嘅測試面。

唯讀。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/shared_racing"))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.matrix_mapper import MATRIX_FORMULAS, map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402

HERE = Path(__file__).resolve().parent
HOLDOUT = 0.15
KEYS = ("gold", "good_pos", "good_any2", "champ", "winT3", "t3prec", "mrr",
        "blowout", "compet", "ndcg5")


def score(races):
    rows = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for h in race["rows"]:
            # ⚠️ 一定要用 `map_features_to_matrix_scores` —— 佢會套用
            # `MATRIX_DISPLAY_GAINS`。自己用 MATRIX_FORMULAS 砌維度再乘
            # MATRIX_WEIGHTS 會漏咗 gain，變成一組同引擎唔同嘅權重
            # （w×gain 相對舊權重係常數 1.4225，唔套 gain 就唔係）。
            mx = map_features_to_matrix_scores(h["features"])
            total = 60.0 + sum((mx[key] - 60.0) * w for key, w in MATRIX_WEIGHTS.items())
            scored.append((total + float(h["wet"] or 0.0), h["n"]))
        picks = [n for _, n in sorted(scored, key=lambda kv: (-kv[0], kv[1]))]
        rows.append(race_metrics(picks, top3, winner=winners[0] if winners else None,
                                actual_pos=actual_pos, field_size=race["field"]))
    return summarize_races(rows)


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
    off = json.loads((HERE / "au_live_leaves_off.json").read_text(encoding="utf-8"))["races"]
    on = json.loads((HERE / "au_live_leaves_pf.json").read_text(encoding="utf-8"))["races"]
    assert len(off) == len(on), "兩份 cache 場次數唔同，唔可以直接比"
    split = int(len(off) * (1 - HOLDOUT))
    # 額外分一組：只計 backfill 真正有作用嘅場次（PF 分同 off 版唔同）
    changed = [i for i, (a, b) in enumerate(zip(off, on))
               if any(x["features"]["pace_figure_score"] != y["features"]["pace_figure_score"]
                      for x, y in zip(a["rows"], b["rows"]))]
    print(f"races {len(off)}；backfill 真正改動咗 {len(changed)} 場 "
          f"({100*len(changed)/len(off):.0f}%)")

    folds = (("dev", slice(0, split)), ("holdout", slice(split, len(off))))
    for name, sl in folds:
        a, b = digest(score(off[sl])), digest(score(on[sl]))
        n = len(off[sl])
        print(f"\n===== {name} ({n} races) =====")
        print(f"{'metric':12}{'PF 關':>10}{'PF 開':>10}{'Δ':>9}")
        for k in KEYS:
            print(f"{k:12}{a[k]:>10}{b[k]:>10}{b[k]-a[k]:>+9.2f}")

    sub_off = [off[i] for i in changed]
    sub_on = [on[i] for i in changed]
    if sub_off:
        a, b = digest(score(sub_off)), digest(score(sub_on))
        print(f"\n===== 只計 backfill 有作用嘅 {len(sub_off)} 場 =====")
        print(f"{'metric':12}{'PF 關':>10}{'PF 開':>10}{'Δ':>9}")
        for k in KEYS:
            print(f"{k:12}{a[k]:>10}{b[k]:>10}{b[k]-a[k]:>+9.2f}")


if __name__ == "__main__":
    main()
