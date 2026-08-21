#!/usr/bin/env python3
"""全 PF 覆蓋下嘅矩陣權重重新配權 —— 兩條工作線都指向嘅同一個下一步。

背景（兩個對話合併）：
  另一邊：PF backfill 令 `pace_figure` 覆蓋 32.8% → 94.3%，數據真係有預測力
          （場內 AUC 0.572–0.599，僅次於近績 0.615 / 穩定 0.605），但喺現行權重下
          令模型變差（gold 37→34）。結論：`0.18831` 當初係喺呢個 leaf 對三分二
          馬匹失明嘅情況下 fit 出嚟，要**全矩陣重新配權**，唔係 flag flip。
  呢邊　：所有權重重新分配都平手到負 —— 但係喺 32.8% PF 覆蓋下量嘅，所以
          嗰個結論喺全覆蓋下唔成立。

方法：喺 PF 開／關兩份 live leaf dump 上面，用同一把尺（eval_metrics）
座標下降搜尋 7 個維度權重。dev 606 場搜尋、未碰過 holdout 107 場只做驗證，
絕不用 holdout 揀參數。

唯讀。
"""
from __future__ import annotations

import argparse
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

HOLDOUT = 0.15
KEYS = ("gold", "good_pos", "good_any2", "champ", "winT3", "t3prec", "mrr",
        "blowout", "compet", "ndcg5")


def dim_scores(race):
    """逐匹馬嘅 7 個維度分，只算一次（權重 sweep 唔會改變佢哋）。"""
    out = []
    for h in race["rows"]:
        # ⚠️ 用 `map_features_to_matrix_scores`（會套用 MATRIX_DISPLAY_GAINS）。
        # 自己砌維度會漏 gain → 等於偷偷用咗另一組權重。
        dims = map_features_to_matrix_scores(h["features"])
        out.append((dims, float(h["wet"] or 0.0), h["n"], h["pos"]))
    return out


def evaluate(prepared, weights):
    rows = []
    for field_size, horses in prepared:
        actual_pos = {n: p for _, _, n, p in horses}
        top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for dims, wet, n, _ in horses:
            total = 60.0 + sum((dims[k] - 60.0) * w for k, w in weights.items())
            scored.append((total + wet, n))
        picks = [n for _, n in sorted(scored, key=lambda kv: (-kv[0], kv[1]))]
        rows.append(race_metrics(picks, top3, winner=winners[0] if winners else None,
                                actual_pos=actual_pos, field_size=field_size))
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


def objective(d):
    """單一目標：包位為主（Gold/Good/Pass 係 KPI 重心），再加競爭力同排序質素。

    刻意用一條**寫死**嘅公式而唔係逐個指標睇 —— 唔係咁樣就會變成事後揀
    最靚嗰個數字。blowout 越細越好所以取負。
    """
    return (0.30 * d["good_any2"] + 0.25 * d["good_pos"] + 0.15 * d["t3prec"]
            + 0.10 * d["winT3"] + 0.10 * d["champ"] + 0.05 * d["compet"]
            - 0.05 * d["blowout"] + 40.0 * d["mrr"] + 20.0 * d["ndcg5"])


def normalise(w):
    total = sum(w.values())
    return {k: v / total * sum(MATRIX_WEIGHTS.values()) for k, v in w.items()} if total else dict(w)


def kfold(prepared, k=5):
    """按時間切 k 份（唔打亂）—— 賽馬數據有時間結構，隨機切會漏 lookahead。"""
    size = len(prepared) // k
    return [prepared[i * size:(i + 1) * size if i < k - 1 else len(prepared)]
            for i in range(k)]


def coordinate_descent(prepared, start, *, rounds=4, folds=5, verbose=True):
    """座標下降，但候選要通過 **每一個 dev fold 都改善** 先接受。

    純 dev 聚合擬合會嚴重過擬合：第一次跑（無 fold 閘）dev objective +3.28、
    gold +5，但 holdout −2.04、good_any2 −6.54。606 場上搵 7 個自由參數
    太易搵到只喺聚合層面靚嘅組合。全 fold 一致係 repo 一貫嘅 gate。
    """
    fold_sets = kfold(prepared, folds)
    def fold_scores(w):
        return [objective(digest(evaluate(f, w))) for f in fold_sets]

    best = dict(start)
    best_folds = fold_scores(best)
    keys = [k for k in best if k != "form_line"]
    for rnd in range(1, rounds + 1):
        improved = False
        for key in keys:
            for factor in (0.7, 0.85, 1.15, 1.4):
                cand = normalise({**best, key: best[key] * factor})
                cand_folds = fold_scores(cand)
                # 全部 fold 都要唔差過現狀，而且平均要有實質改善
                if (all(c >= b - 1e-9 for c, b in zip(cand_folds, best_folds))
                        and sum(cand_folds) > sum(best_folds) + 1e-6):
                    best, best_folds, improved = cand, cand_folds, True
        if verbose:
            print(f"  round {rnd}: fold objectives "
                  f"[{', '.join(f'{s:.2f}' for s in best_folds)}]")
        if not improved:
            break
    return best, sum(best_folds) / len(best_folds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    races = json.loads(Path(args.cache).read_text(encoding="utf-8"))["races"]
    prepared = [(r["field"], dim_scores(r)) for r in races]
    split = int(len(prepared) * (1 - HOLDOUT))
    dev, hold = prepared[:split], prepared[split:]
    print(f"{args.label}  races {len(races)}  dev {len(dev)} / holdout {len(hold)}")

    base_dev, base_hold = digest(evaluate(dev, MATRIX_WEIGHTS)), digest(evaluate(hold, MATRIX_WEIGHTS))
    print(f"\n現行權重 objective: dev {objective(base_dev):.4f} / holdout {objective(base_hold):.4f}")

    print("\n座標下降（只用 dev）:")
    fitted, _ = coordinate_descent(dev, MATRIX_WEIGHTS)
    print("\n擬合權重:")
    for k in MATRIX_WEIGHTS:
        print(f"   {k:14} {MATRIX_WEIGHTS[k]:.5f} → {fitted[k]:.5f}"
              f"  ({fitted[k] / MATRIX_WEIGHTS[k]:.2f}×)" if MATRIX_WEIGHTS[k] else
              f"   {k:14} {MATRIX_WEIGHTS[k]:.5f} → {fitted[k]:.5f}")

    for name, fold, base in (("dev", dev, base_dev), ("holdout", hold, base_hold)):
        new = digest(evaluate(fold, fitted))
        print(f"\n===== {name} =====")
        print(f"{'metric':12}{'現行':>10}{'擬合':>10}{'Δ':>9}")
        for k in KEYS:
            d = new[k] - base[k]
            print(f"{k:12}{base[k]:>10}{new[k]:>10}{d:>+9.2f}")
        print(f"{'objective':12}{objective(base):>10.4f}{objective(new):>10.4f}"
              f"{objective(new)-objective(base):>+9.4f}")


if __name__ == "__main__":
    main()
