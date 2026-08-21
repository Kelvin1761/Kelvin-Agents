#!/usr/bin/env python3
"""矩陣權重檢討：權重同實際預測力嚴重錯配，測下重新配權有幾多免費 upside。

已量到（693 場，場內 Spearman ρ vs 實際名次）：

  leaf                     有效權重   ρ      錯配
  jockey_score              0.0543  0.163   權重細但訊號強
  rating_score              0.0317  0.159   權重細但訊號強
  trainer_score             0.0388  0.156   權重細但訊號強
  jockey_horse_fit_score    0.1009  0.071   權重大但訊號弱
  pace_map_score            0.1485  0.066   **第二大權重、第 13 弱訊號**
  track_score               0.1244  0.096   權重大但訊號中下

⚠️ 單獨 ρ 唔係全部：pace_map 係檔位偏差，可能同 form 正交，所以就算單獨弱
都可能有配搭價值。所以唔可以靠 ρ 直接改權重 —— 要實測。

兩組獨立實驗：
  W1  jockey_trainer 內部 sub-weight 重新分配（jockey ↑ / horse_fit ↓）
  W2  維度權重轉移（race_shape → class_weight / stability）

dev 85% / 未碰過 holdout 15%。唯讀，本地 cache。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine"))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/shared_racing"))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.matrix_mapper import MATRIX_FORMULAS  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402

HERE = Path(__file__).resolve().parent
HOLDOUT = 0.15


def score_fold(races, formulas, weights):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for h in race["rows"]:
            f = h["features"]
            total = 60.0
            for key, comps in formulas.items():
                dim = 60.0 + sum((clip_score(f.get(name, 60)) - 60.0) * w
                                 for name, w in comps)
                total += (clip_score(dim) - 60.0) * weights[key]
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


KEYS = ("gold", "good_pos", "good_any2", "champ", "winT3", "t3prec", "mrr",
        "blowout", "compet", "ndcg5")


def table(title, races, variants):
    print(f"\n########## {title} ##########")
    split = int(len(races) * (1 - HOLDOUT))
    for name, fold in (("dev", races[:split]), ("holdout", races[split:])):
        base = digest(score_fold(fold, MATRIX_FORMULAS, MATRIX_WEIGHTS))
        print(f"\n--- {name} ({len(fold)} races) ---")
        print(f"{'variant':30}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'現行':30}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for label, formulas, weights in variants:
            d = digest(score_fold(fold, formulas, weights))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += (f"{d[k]:>7}({delta:+d})".rjust(13) if k == "gold"
                          else f"{d[k]:>7}{delta:+.2f}".rjust(13))
            print(f"{label:30}" + cells)


def jt(jockey, trainer, fit):
    f = {k: tuple(v) for k, v in MATRIX_FORMULAS.items()}
    f["jockey_trainer"] = (("jockey_score", jockey), ("trainer_score", trainer),
                           ("jockey_horse_fit_score", fit))
    return f


def shift(src, dst, amount):
    w = dict(MATRIX_WEIGHTS)
    move = min(amount, w[src])
    w[src] -= move
    w[dst] += move
    return w


def main():
    races = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))["races"]

    table("W1 — jockey_trainer 內部 sub-weight（現行 .28/.20/.52）", races, [
        (f"jockey/trainer/fit {a}/{b}/{c}", jt(a, b, c), MATRIX_WEIGHTS)
        for a, b, c in ((0.40, 0.25, 0.35), (0.50, 0.30, 0.20),
                        (0.60, 0.40, 0.00), (0.34, 0.24, 0.42))
    ])

    table("W2 — 維度權重轉移（race_shape 0.1485 係第二大但 ρ 只 0.066）", races, [
        ("race_shape→class_weight .04", MATRIX_FORMULAS, shift("race_shape", "class_weight", 0.04)),
        ("race_shape→class_weight .08", MATRIX_FORMULAS, shift("race_shape", "class_weight", 0.08)),
        ("race_shape→stability .04", MATRIX_FORMULAS, shift("race_shape", "stability", 0.04)),
        ("race_shape→stability .08", MATRIX_FORMULAS, shift("race_shape", "stability", 0.08)),
        ("track→class_weight .04", MATRIX_FORMULAS, shift("track", "class_weight", 0.04)),
    ])


if __name__ == "__main__":
    main()
