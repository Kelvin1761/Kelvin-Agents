#!/usr/bin/env python3
"""Conservative time-ordered search for simpler AU matrix weights.

The search changes one pair of existing matrix weights at a time.  It selects
on the first four development folds, then reports the fifth fold and terminal
holdout without using either for selection.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from au_runtime_micro_ablation import (
    date_partitions,
    metric_delta,
    metrics_for_scored_races,
    score_diagnostics,
    select_indices,
)
from au_racing_engine.io_utils import write_json_atomic, write_text_atomic
from au_racing_engine.scoring import MATRIX_WEIGHTS


MATRIX_KEYS = tuple(
    key for key, weight in MATRIX_WEIGHTS.items() if weight > 0
)
PRIORITY_METRICS = (
    "good_positional",
    "top3_all_within_top4",
    "competitive_recall_at5",
    "ndcg_at5",
    "winner_top5",
    "zero_hit",
)


def candidate_weights() -> dict[str, dict[str, float]]:
    """Return current weights plus transparent one-pair transfers."""
    candidates = {"revised_current": dict(MATRIX_WEIGHTS)}
    for donor in MATRIX_KEYS:
        for recipient in MATRIX_KEYS:
            if donor == recipient:
                continue
            for basis_points in (100, 200, 300):
                amount = basis_points / 10_000
                if MATRIX_WEIGHTS[donor] <= amount:
                    continue
                weights = dict(MATRIX_WEIGHTS)
                weights[donor] -= amount
                weights[recipient] += amount
                name = f"{donor}_to_{recipient}_{basis_points}bp"
                candidates[name] = weights
    return candidates


def score_races(
    dataset: dict,
    weights: dict[str, float],
) -> list[list[dict]]:
    """Recompose only the matrix layer; preserve any external score feature."""
    output = []
    deltas = {
        key: weights[key] - MATRIX_WEIGHTS[key]
        for key in MATRIX_WEIGHTS
    }
    for race in dataset["races"]:
        rows = []
        for source in race["rows"]:
            matrices = source["matrix_scores"]
            score = float(source["score"])
            score += sum(
                deltas[key] * (float(matrices[key]) - 60.0)
                for key in MATRIX_WEIGHTS
            )
            rows.append({**source, "score": round(score, 4)})
        output.append(rows)
    return output


def deltas_for_indices(
    candidate: list[list[dict]],
    baseline: list[list[dict]],
    indices: set[int],
) -> dict[str, float]:
    candidate_metrics = metrics_for_scored_races(
        select_indices(candidate, indices)
    )
    baseline_metrics = metrics_for_scored_races(
        select_indices(baseline, indices)
    )
    return metric_delta(candidate_metrics, baseline_metrics)


def selection_summary(fold_deltas: list[dict[str, float]]) -> dict:
    means = {
        metric: mean(fold.get(metric, 0.0) for fold in fold_deltas)
        for metric in PRIORITY_METRICS
    }
    nonnegative = {
        metric: sum(
            (
                fold.get(metric, 0.0) >= 0
                if metric != "zero_hit"
                else fold.get(metric, 0.0) <= 0
            )
            for fold in fold_deltas
        )
        for metric in PRIORITY_METRICS
    }
    eligible = (
        means["good_positional"] >= 0
        and means["top3_all_within_top4"] >= 0
        and means["competitive_recall_at5"] >= 0
        and means["ndcg_at5"] >= 0
        and means["winner_top5"] >= 0
        and means["zero_hit"] <= 0
        and nonnegative["good_positional"] >= 3
        and nonnegative["top3_all_within_top4"] >= 3
        and nonnegative["competitive_recall_at5"] >= 3
        and nonnegative["ndcg_at5"] >= 3
        and nonnegative["winner_top5"] >= 3
        and nonnegative["zero_hit"] >= 3
    )
    # Recall and zero-hit carry the largest weight because the project goal is
    # competitive-horse coverage, not exact top-three order.
    objective = (
        4 * means["competitive_recall_at5"]
        + means["ndcg_at5"]
        + 2 * means["winner_top5"]
        - 4 * means["zero_hit"]
    )
    return {
        "mean_deltas": means,
        "nonnegative_fold_counts": nonnegative,
        "eligible": eligible,
        "objective": objective,
    }


def passes_confirmation(delta: dict[str, float]) -> bool:
    return (
        delta.get("good_positional", 0.0) >= 0
        and delta.get("top3_all_within_top4", 0.0) >= 0
        and delta.get("competitive_recall_at5", 0.0) >= 0
        and delta.get("ndcg_at5", 0.0) >= 0
        and delta.get("winner_top5", 0.0) >= 0
        and delta.get("zero_hit", 0.0) <= 0
    )


def run_search(dataset: dict, holdout_fraction: float = 0.15) -> dict:
    weights_by_name = candidate_weights()
    scored = {
        name: score_races(dataset, weights)
        for name, weights in weights_by_name.items()
    }
    baseline = scored["revised_current"]
    dates = [race["metadata"]["date"] for race in dataset["races"]]
    dev_indices, holdout_indices, folds = date_partitions(
        dates,
        holdout_fraction=holdout_fraction,
    )
    if len(folds) < 5:
        raise ValueError("Need five development folds for selection/validation.")
    selection_folds = folds[:4]
    validation_indices = folds[4]

    candidates = {}
    for name, candidate in scored.items():
        fold_deltas = [
            deltas_for_indices(candidate, baseline, indices)
            for indices in selection_folds
        ]
        selection = selection_summary(fold_deltas)
        validation = deltas_for_indices(
            candidate,
            baseline,
            validation_indices,
        )
        terminal = deltas_for_indices(
            candidate,
            baseline,
            holdout_indices,
        )
        candidates[name] = {
            "weights": weights_by_name[name],
            "selection": selection,
            "selection_fold_deltas": fold_deltas,
            "validation_fold_delta": validation,
            "terminal_holdout_delta": terminal,
            "validation_pass": passes_confirmation(validation),
            "terminal_pass": passes_confirmation(terminal),
            "score_diagnostics": score_diagnostics(candidate, baseline),
        }

    eligible = [
        name
        for name, result in candidates.items()
        if name != "revised_current" and result["selection"]["eligible"]
    ]
    selected = max(
        eligible,
        key=lambda name: candidates[name]["selection"]["objective"],
        default=None,
    )
    promoted = bool(
        selected
        and candidates[selected]["validation_pass"]
        and candidates[selected]["terminal_pass"]
    )
    return {
        "design": {
            "aligned_races": len(dates),
            "development_races": len(dev_indices),
            "terminal_holdout_races": len(holdout_indices),
            "selection_fold_races": [
                len(indices) for indices in selection_folds
            ],
            "validation_fold_races": len(validation_indices),
            "candidate_count": len(candidates) - 1,
            "selection_rule": (
                "One pair transfer only; select on folds 1-4. "
                "Fold 5 and terminal holdout are confirmation-only."
            ),
        },
        "selected_candidate": selected,
        "promoted": promoted,
        "recommendation": (
            selected
            if promoted
            else "retain revised_current weights"
        ),
        "candidates": candidates,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# AU Matrix Weight Search",
        "",
        f"- Aligned races: {report['design']['aligned_races']}",
        f"- Tested one-pair transfers: {report['design']['candidate_count']}",
        f"- Selected on folds 1-4: {report['selected_candidate'] or 'none'}",
        f"- Promotion verdict: {'PASS' if report['promoted'] else 'RETAIN CURRENT'}",
        f"- Recommendation: {report['recommendation']}",
        "",
        "| Candidate | Select objective | Select eligible | Fold 5 pass | Terminal pass | "
        "Fold 5 Good Δ | Fold 5 T3@4 Δ | Fold 5 Comp Δ | Fold 5 NDCG Δ | "
        "Fold 5 W@5 Δ | Fold 5 0-hit Δ | Hold Good Δ | Hold T3@4 Δ | "
        "Hold Comp Δ | Hold NDCG Δ | Hold W@5 Δ | Hold 0-hit Δ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    ranked = sorted(
        (
            (name, result)
            for name, result in report["candidates"].items()
            if name != "revised_current"
        ),
        key=lambda item: item[1]["selection"]["objective"],
        reverse=True,
    )[:20]
    for name, result in ranked:
        valid = result["validation_fold_delta"]
        hold = result["terminal_holdout_delta"]
        pct = lambda value: f"{value * 100:+.3f}%"
        lines.append(
            f"| {name} | {result['selection']['objective']:+.6f} | "
            f"{result['selection']['eligible']} | {result['validation_pass']} | "
            f"{result['terminal_pass']} | "
            f"{pct(valid.get('good_positional', 0))} | "
            f"{pct(valid.get('top3_all_within_top4', 0))} | "
            f"{pct(valid.get('competitive_recall_at5', 0))} | "
            f"{pct(valid.get('ndcg_at5', 0))} | "
            f"{pct(valid.get('winner_top5', 0))} | "
            f"{pct(valid.get('zero_hit', 0))} | "
            f"{pct(hold.get('good_positional', 0))} | "
            f"{pct(hold.get('top3_all_within_top4', 0))} | "
            f"{pct(hold.get('competitive_recall_at5', 0))} | "
            f"{pct(hold.get('ndcg_at5', 0))} | "
            f"{pct(hold.get('winner_top5', 0))} | "
            f"{pct(hold.get('zero_hit', 0))} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-json", type=Path, required=True)
    parser.add_argument("--holdout-fraction", type=float, default=0.15)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/private/tmp/au_matrix_weight_search.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("/private/tmp/au_matrix_weight_search.md"),
    )
    args = parser.parse_args()
    dataset = json.loads(args.dataset_json.read_text(encoding="utf-8"))
    report = run_search(dataset, args.holdout_fraction)
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render_markdown(report))
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_md}")
    return 0



# ─────────────────────────────────────────────────────────────────────────────
# 已退役（2026-08-21）。用 `au_matrix_refit.py` 代替。
#
# 呢個檔係 coordinate descent / argmax 搜索。實測會 overfit：dev good_pos +3.80
# 但 holdout 舊 any-one 指標 −5.61。`au_matrix_refit.py` 個 docstring 明文寫住
# 佢取代咗呢三個檔（本檔、`au_clean_7d_weight_search.py`、
# `au_weight_improvement_search.py`），並且改為取閘後候選嘅**逐維度中位數（共識）**
# 而唔係 argmax。
#
# 另一個更根本嘅理由：矩陣嘅收益係**五個維度一齊郁**出嚟嘅，所以逐對權重試會讀到
# 「已經最優」，其實佢讀到嘅係「平」。單獨郁一對過唔到閘 ≠ 呢個方向冇用。
#
# 保留呢個檔只為對照歷史結論。要跑就明確 opt in。
# ─────────────────────────────────────────────────────────────────────────────
import os as _os

_RETIRED_MSG = """
❌ {name} 已退役 —— 佢係 argmax／coordinate descent，實測 overfit
   （dev good_pos +3.80 / holdout −5.61）。

   用 au_matrix_refit.py 代替：
       python3 au_dump_engine_leaves.py --out /tmp/leaves.json
       python3 au_matrix_refit.py verify --data /tmp/leaves.json
       python3 au_matrix_refit.py refit  --data /tmp/leaves.json

   真係要跑舊工具做歷史對照：WC_ALLOW_RETIRED_WEIGHT_SEARCH=1
"""


def _refuse_if_retired():
    if _os.environ.get("WC_ALLOW_RETIRED_WEIGHT_SEARCH") == "1":
        print(f"⚠️  {__file__} 已退役，你用 WC_ALLOW_RETIRED_WEIGHT_SEARCH=1 強制跑。"
              " 結果唔可以當證據。")
        return
    import sys as _sys
    print(_RETIRED_MSG.format(name=Path(__file__).name), file=_sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    _refuse_if_retired()
    raise SystemExit(main())
