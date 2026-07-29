#!/usr/bin/env python3
"""Evidence-first AU signal ablation on a fixed, labelled archive snapshot.

This stage works from archived scoring rows, so it can test matrix and leaf
signals without reading post-race data into the model.  SP/barrier remain
outcome-only labels used exclusively for retrospective slices.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))
sys.path.insert(0, str(PROJECT_ROOT / ".agents" / "skills" / "shared_racing"))

from au_cached_walkforward_ml import group_races, load_dataset
from eval_metrics import race_metrics, summarize_races
from io_utils import write_json_atomic, write_text_atomic
from matrix_mapper import MATRIX_FORMULAS, MATRIX_KEYS, map_features_to_matrix_scores
from scoring import MATRIX_WEIGHTS


PRE_CLEAN_MATRIX_FORMULAS = {
    **MATRIX_FORMULAS,
    "class_weight": (
        ("class_score", 0.159),
        ("rating_score", 0.70),
        ("weight_score", 0.141),
    ),
}
AUDIT_LEAVES = tuple(
    dict.fromkeys(
        leaf
        for matrix, components in PRE_CLEAN_MATRIX_FORMULAS.items()
        if MATRIX_WEIGHTS.get(matrix, 0.0) > 0
        for leaf, _weight in components
    )
)


def _horse_id(row: dict) -> tuple[int, str]:
    return int(row["horse_number"]), str(row["horse_name"])


def _matrix_total(matrix: dict) -> float:
    return sum(float(matrix.get(key, 60.0)) * MATRIX_WEIGHTS[key] for key in MATRIX_KEYS)


def _map_with_formulas(features: dict, formulas: dict) -> dict:
    return {
        key: 60.0
        + sum(
            (max(0.0, min(100.0, float(features.get(leaf, 60.0)))) - 60.0) * weight
            for leaf, weight in components
        )
        for key, components in formulas.items()
    }


def score_rows(
    races: list[list[dict]],
    *,
    neutral_matrices: frozenset[str] = frozenset(),
    neutral_leaves: frozenset[str] = frozenset(),
    stored_production: bool = False,
    signal_cleaned: bool = False,
) -> list[list[dict]]:
    scored = []
    for race in races:
        race_rows = []
        for source in race:
            row = dict(source)
            if stored_production:
                score = float(row["ability_score"])
            elif neutral_leaves or signal_cleaned:
                features = {
                    leaf: 60.0 if leaf in neutral_leaves else float(row.get(leaf, 60.0))
                    for leaf in AUDIT_LEAVES
                }
                mapper = (
                    map_features_to_matrix_scores(features)
                    if signal_cleaned
                    else _map_with_formulas(features, PRE_CLEAN_MATRIX_FORMULAS)
                )
                score = _matrix_total(mapper)
                score += float(row.get("wet_form_feature", 0.0))
            else:
                matrix = {
                    key: 60.0 if key in neutral_matrices else float(row.get(f"mx_{key}", 60.0))
                    for key in MATRIX_KEYS
                }
                score = _matrix_total(matrix)
                score += float(row.get("wet_form_feature", 0.0))
            row["_audit_score"] = score
            race_rows.append(row)
        scored.append(race_rows)
    return scored


def evaluation_rows(races: list[list[dict]]) -> list[dict]:
    output = []
    for race in races:
        ranked = sorted(
            race,
            key=lambda row: (-float(row["_audit_score"]), int(row["horse_number"])),
        )
        positions = {_horse_id(row): int(row["actual_pos"]) for row in race}
        actual_top3 = {horse for horse, position in positions.items() if position <= 3}
        output.append(
            race_metrics(
                [_horse_id(row) for row in ranked],
                actual_top3,
                actual_pos=positions,
                field_size=len(positions),
            )
        )
    return output


def score_separation(races: list[list[dict]]) -> dict:
    race_sd = []
    top1_top3 = []
    top3_top5 = []
    compressed = 0
    for race in races:
        scores = sorted((float(row["_audit_score"]) for row in race), reverse=True)
        if len(scores) < 3:
            continue
        sd = pstdev(scores)
        race_sd.append(sd)
        top1_top3.append(scores[0] - scores[2])
        if len(scores) >= 5:
            top3_top5.append(scores[2] - scores[4])
        if sd < 2.0:
            compressed += 1
    return {
        "mean_within_race_sd": mean(race_sd) if race_sd else None,
        "median_within_race_sd": sorted(race_sd)[len(race_sd) // 2] if race_sd else None,
        "mean_top1_top3_gap": mean(top1_top3) if top1_top3 else None,
        "mean_top3_top5_gap": mean(top3_top5) if top3_top5 else None,
        "compressed_races_sd_lt_2": compressed,
        "compressed_rate": compressed / len(race_sd) if race_sd else None,
    }


def outsider_slice(races: list[list[dict]], sp_floor: float = 31.0) -> dict:
    ranks = []
    top3_outsiders = 0
    captured_at5 = 0
    winners = 0
    winners_at5 = 0
    for race in races:
        ranked = sorted(
            race,
            key=lambda row: (-float(row["_audit_score"]), int(row["horse_number"])),
        )
        model_rank = {_horse_id(row): index for index, row in enumerate(ranked, 1)}
        for row in race:
            sp = row.get("result_sp_label")
            if sp is None or float(sp) < sp_floor or int(row["actual_pos"]) > 3:
                continue
            rank = model_rank[_horse_id(row)]
            ranks.append(rank)
            top3_outsiders += 1
            captured_at5 += rank <= 5
            if int(row["actual_pos"]) == 1:
                winners += 1
                winners_at5 += rank <= 5
    return {
        "sp_floor": sp_floor,
        "actual_top3_outsiders": top3_outsiders,
        "captured_at5": captured_at5,
        "capture_at5_rate": captured_at5 / top3_outsiders if top3_outsiders else None,
        "mean_model_rank": mean(ranks) if ranks else None,
        "outsider_winners": winners,
        "outsider_winners_at5": winners_at5,
        "outsider_winner_at5_rate": winners_at5 / winners if winners else None,
    }


def compact_metrics(summary: dict) -> dict:
    rates = summary["rates"]
    comp = summary["competitiveness"]
    return {
        "races": summary["races"],
        "gold": rates["gold"],
        "good_any2": rates["good_any2"],
        "pass_any1": rates["pass_any1"],
        "zero_hit": summary["hit_distribution"]["0hit"] / max(1, summary["races"]),
        "one_hit": summary["hit_distribution"]["1hit"] / max(1, summary["races"]),
        "winner_top3": rates["winner_in_top3"],
        "winner_top5": rates["winner_in_top5"],
        "mrr": summary["mrr"],
        "top3_capture_at5": comp["mean_top3_capture_at5"],
        "competitive_recall_at5": comp["mean_competitive_recall_at5"],
        "competitive_precision_at5": comp["mean_competitive_precision_at5"],
        "ndcg_at5": comp["mean_ndcg_at5"],
        "top_pick_blowout": comp["top_pick_blowout"]["rate"],
        "mean_top3_model_rank": comp["mean_top3_model_rank"],
    }


def evaluate(races: list[list[dict]]) -> dict:
    return {
        "metrics": compact_metrics(summarize_races(evaluation_rows(races))),
        "separation": score_separation(races),
        "outsiders_sp31": outsider_slice(races, 31.0),
        "outsiders_sp51": outsider_slice(races, 51.0),
    }


def split_dev_holdout(races: list[list[dict]], holdout_fraction: float) -> tuple[list, list]:
    dates = sorted({str(race[0]["date"]) for race in races})
    holdout_dates = max(1, math.ceil(len(dates) * holdout_fraction))
    terminal = set(dates[-holdout_dates:])
    return (
        [race for race in races if str(race[0]["date"]) not in terminal],
        [race for race in races if str(race[0]["date"]) in terminal],
    )


def chronological_folds(races: list[list[dict]], count: int = 5) -> list[list[list[dict]]]:
    dates = sorted({str(race[0]["date"]) for race in races})
    # Contiguous date folds, not interleaved future/past windows.
    size = math.ceil(len(dates) / count)
    buckets = [dates[index : index + size] for index in range(0, len(dates), size)]
    return [
        [race for race in races if str(race[0]["date"]) in set(bucket)]
        for bucket in buckets
        if bucket
    ]


def delta(candidate: dict, baseline: dict) -> dict:
    return {
        key: candidate["metrics"][key] - baseline["metrics"][key]
        for key in candidate["metrics"]
        if key != "races"
        and candidate["metrics"].get(key) is not None
        and baseline["metrics"].get(key) is not None
    }


def variant_rows(
    races: list[list[dict]],
    kind: str,
    signal: str | tuple[str, ...] = "",
) -> list[list[dict]]:
    if kind == "production":
        return score_rows(races, stored_production=True)
    if kind == "recomposed":
        return score_rows(races)
    if kind == "signal_cleaned":
        return score_rows(races, signal_cleaned=True)
    if kind == "matrix":
        signals = signal if isinstance(signal, tuple) else (signal,)
        return score_rows(races, neutral_matrices=frozenset(signals))
    if kind == "leaf":
        signals = signal if isinstance(signal, tuple) else (signal,)
        return score_rows(races, neutral_leaves=frozenset(signals))
    raise ValueError(f"Unknown variant kind: {kind}")


def build_audit(races: list[list[dict]], holdout_fraction: float = 0.15) -> dict:
    dev, holdout = split_dev_holdout(races, holdout_fraction)
    folds = chronological_folds(dev)
    variants = [
        ("archived_production", "production", ""),
        ("recomposed_pre_clean", "recomposed", ""),
        ("signal_cleaned", "signal_cleaned", ""),
        *[(f"drop_matrix:{key}", "matrix", key) for key in MATRIX_KEYS],
        *[(f"drop_leaf:{key}", "leaf", key) for key in AUDIT_LEAVES],
        (
            "drop_group:class_and_weight",
            "leaf",
            ("class_score", "weight_score"),
        ),
        (
            "drop_group:text_pace_support",
            "leaf",
            ("sectional_score", "trial_score"),
        ),
        (
            "drop_group:race_context",
            "leaf",
            ("pace_map_score", "track_score"),
        ),
        (
            "drop_group:people",
            "leaf",
            ("jockey_score", "trainer_score", "jockey_horse_fit_score"),
        ),
    ]
    output = {
        "design": {
            "archive_races": len(races),
            "development_races": len(dev),
            "terminal_holdout_races": len(holdout),
            "holdout_fraction": holdout_fraction,
            "fold_races": [len(fold) for fold in folds],
            "outcome_only_fields": ["actual_pos", "result_sp_label", "result_barrier_label"],
            "pre_clean_direct_model_inputs": list(AUDIT_LEAVES),
            "signal_cleaned_direct_model_inputs": [
                leaf for leaf in AUDIT_LEAVES if leaf != "class_score"
            ],
        },
        "variants": {},
    }
    baseline_dev = evaluate(variant_rows(dev, "recomposed"))
    baseline_holdout = evaluate(variant_rows(holdout, "recomposed"))
    for name, kind, signal in variants:
        dev_eval = evaluate(variant_rows(dev, kind, signal))
        holdout_eval = evaluate(variant_rows(holdout, kind, signal))
        fold_deltas = []
        for fold in folds:
            candidate_fold = evaluate(variant_rows(fold, kind, signal))
            baseline_fold = evaluate(variant_rows(fold, "recomposed"))
            fold_deltas.append(delta(candidate_fold, baseline_fold))
        output["variants"][name] = {
            "development": dev_eval,
            "terminal_holdout": holdout_eval,
            "delta_development_vs_recomposed": delta(dev_eval, baseline_dev),
            "delta_holdout_vs_recomposed": delta(holdout_eval, baseline_holdout),
            "fold_deltas_vs_recomposed": fold_deltas,
        }
    return output


def _pct(value) -> str:
    return "n/a" if value is None else f"{100 * value:.2f}%"


def render_markdown(audit: dict) -> str:
    lines = [
        "# AU Signal Simplification Audit",
        "",
        "## Guardrails",
        "",
        f"- Archive races: {audit['design']['archive_races']}",
        f"- Development / terminal holdout: {audit['design']['development_races']} / {audit['design']['terminal_holdout_races']}",
        "- SP、barrier、actual finish 只作賽後切片，從未進入任何候選分數。",
        "- `drop_*` 代表將該訊號設回中性 60；正 delta 代表刪除後改善。",
        "",
        "## Development and terminal holdout",
        "",
        "| Variant | Dev Comp R@5 Δ | Dev NDCG@5 Δ | Dev W@5 Δ | Dev 0-hit Δ | Hold Comp R@5 Δ | Hold NDCG@5 Δ | Hold W@5 Δ | Hold 0-hit Δ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in audit["variants"].items():
        dev = result["delta_development_vs_recomposed"]
        hold = result["delta_holdout_vs_recomposed"]
        lines.append(
            "| {name} | {dcr} | {dn} | {dw} | {dz} | {hcr} | {hn} | {hw} | {hz} |".format(
                name=name,
                dcr=_pct(dev.get("competitive_recall_at5")),
                dn=_pct(dev.get("ndcg_at5")),
                dw=_pct(dev.get("winner_top5")),
                dz=_pct(dev.get("zero_hit")),
                hcr=_pct(hold.get("competitive_recall_at5")),
                hn=_pct(hold.get("ndcg_at5")),
                hw=_pct(hold.get("winner_top5")),
                hz=_pct(hold.get("zero_hit")),
            )
        )
    base = audit["variants"]["recomposed_pre_clean"]
    lines.extend(
        [
            "",
            "## Re-composed baseline",
            "",
            f"- Dev competitive recall@5: {_pct(base['development']['metrics']['competitive_recall_at5'])}",
            f"- Dev NDCG@5: {_pct(base['development']['metrics']['ndcg_at5'])}",
            f"- Dev winner top-5: {_pct(base['development']['metrics']['winner_top5'])}",
            f"- Dev zero-hit: {_pct(base['development']['metrics']['zero_hit'])}",
            f"- Holdout competitive recall@5: {_pct(base['terminal_holdout']['metrics']['competitive_recall_at5'])}",
            f"- Holdout NDCG@5: {_pct(base['terminal_holdout']['metrics']['ndcg_at5'])}",
            f"- Holdout winner top-5: {_pct(base['terminal_holdout']['metrics']['winner_top5'])}",
            f"- Holdout zero-hit: {_pct(base['terminal_holdout']['metrics']['zero_hit'])}",
            "",
            "完整 fold、outsider 同 score-separation 數值見 JSON companion。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("/private/tmp/au_wong_choi_ml_cache/au_labelled_horse_rows.csv"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/private/tmp/au_signal_simplification_audit.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("/private/tmp/au_signal_simplification_audit.md"),
    )
    parser.add_argument("--holdout-fraction", type=float, default=0.15)
    args = parser.parse_args()

    races = group_races(load_dataset(args.dataset))
    if not races:
        raise SystemExit("No aligned labelled races in dataset.")
    audit = build_audit(races, args.holdout_fraction)
    write_json_atomic(args.output_json, audit)
    write_text_atomic(args.output_md, render_markdown(audit))
    print(f"Races: {len(races)}")
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
