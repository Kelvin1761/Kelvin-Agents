#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from itertools import product
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from hkjc_no_regression_gate import evaluate_gate  # noqa: E402
from hkjc_results_db import get_analysis_archive_root, get_season_results_roots  # noqa: E402
from review_auto_weighting import (  # noqa: E402
    CURRENT_MATRIX_FORMULAS,
    CURRENT_MATRIX_WEIGHTS,
    build_results_index,
    compute_ability,
    compute_full_feature_scores,
    compute_matrix_scores,
    dedup_race_key,
    hk_meeting_dirs,
    load_results,
    meeting_date,
    race_num_from_path,
    summarize_model_races,
    venue_from_meeting_dir,
)


METRIC_ORDER = (
    "gold",
    "good",
    "min_threshold",
    "champion",
    "top3_has_champion",
    "mrr",
    "avg_top4_hits",
    "top5_all_top3",
    "top5_at_least2_top3",
    "winner_in_top5",
    "order_issue",
    "avg_winner_rank",
    "avg_pick1_finish",
)

WEIGHT_GRID = {
    "sectional": (0.14, 0.16, 0.18, 0.20),
    "trainer_signal": (0.18, 0.20, 0.22, 0.24),
    "stability": (0.10, 0.12, 0.14, 0.16),
    "race_shape": (0.16, 0.18, 0.20, 0.22, 0.24),
    "class_advantage": (0.10, 0.12, 0.14, 0.16),
    "horse_health": (0.04, 0.06, 0.08),
    "form_line": (0.04, 0.06, 0.08, 0.10),
}


def _load_archive_races() -> list[dict[str, Any]]:
    results_index = build_results_index(get_season_results_roots() + [get_analysis_archive_root()])
    races: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str, int]] = set()

    for meeting_dir in hk_meeting_dirs([get_analysis_archive_root()]):
        date = meeting_date(meeting_dir)
        result_path = results_index.get(date or "")
        if not result_path:
            continue
        actual_results = load_results(result_path)
        venue = venue_from_meeting_dir(meeting_dir)

        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=race_num_from_path):
            race_num = race_num_from_path(logic_path)
            actual_pos = actual_results.get(race_num)
            if not actual_pos:
                continue
            race_key = dedup_race_key(date, venue, race_num)
            if race_key in seen:
                continue
            seen.add(race_key)

            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_context = dict(logic.get("race_analysis", {}))
            race_context.setdefault("venue", venue)
            horses = []
            for horse_num_text, horse in logic.get("horses", {}).items():
                try:
                    horse_num = int(horse_num_text)
                except ValueError:
                    continue
                features = compute_full_feature_scores(horse, race_context)
                matrix_scores = compute_matrix_scores(features, CURRENT_MATRIX_FORMULAS)
                horses.append(
                    {
                        "horse_num": horse_num,
                        "horse_name": horse.get("horse_name", ""),
                        "matrix_scores": matrix_scores,
                    }
                )
            if horses:
                races.append(
                    {
                        "meeting": str(meeting_dir),
                        "date": date,
                        "venue": venue,
                        "race": race_num,
                        "actual_pos": actual_pos,
                        "horses": horses,
                    }
                )
    return races


def _evaluate_weights_for_race(race: dict[str, Any], weights: dict[str, float]) -> dict[str, Any]:
    actual_pos = race["actual_pos"]
    ranked = sorted(
        (
            {
                "horse_num": horse["horse_num"],
                "horse_name": horse["horse_name"],
                "ability": compute_ability(horse["matrix_scores"], weights),
                "matrix_scores": horse["matrix_scores"],
            }
            for horse in race["horses"]
        ),
        key=lambda row: (row["ability"], -row["horse_num"]),
        reverse=True,
    )
    picks = [row["horse_num"] for row in ranked[:4]]
    top5 = [row["horse_num"] for row in ranked[:5]]
    actual_top3 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:3]]
    actual_top4 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:4]]
    actual_top3_set = set(actual_top3)
    winner = actual_top3[0] if actual_top3 else None
    hits = sum(1 for horse in picks[:3] if horse in actual_top3_set)
    winner_rank = next((idx for idx, row in enumerate(ranked, start=1) if row["horse_num"] == winner), len(ranked) + 1)
    pick1_finish = actual_pos.get(picks[0], 99) if picks else 99
    top4_hits = sum(1 for horse in picks if horse in set(actual_top4))
    top5_top3_hits = sum(1 for horse in top5 if horse in actual_top3_set)
    order_issue = False
    if len(picks) >= 4:
        order_issue = min(actual_pos.get(picks[2], 99), actual_pos.get(picks[3], 99)) < min(
            actual_pos.get(picks[0], 99), actual_pos.get(picks[1], 99)
        )

    return {
        "picks": picks,
        "top5": top5,
        "gold": hits == 3,
        "good": len(picks) >= 2 and picks[0] in actual_top3_set and picks[1] in actual_top3_set,
        "min_threshold": hits >= 2,
        "single": hits >= 1,
        "champion": bool(picks and picks[0] == winner),
        "top3_has_champion": bool(winner in set(picks[:3])),
        "winner_rank": winner_rank,
        "mrr": 1.0 / winner_rank if winner_rank > 0 else 0.0,
        "pick1_finish": pick1_finish,
        "top4_hits": top4_hits,
        "order_issue": order_issue,
        "top5_actual_top3_hits": top5_top3_hits,
        "top5_all_top3": top5_top3_hits == 3,
        "top5_at_least2_top3": top5_top3_hits >= 2,
        "winner_in_top5": bool(winner in set(top5)),
        "ranked": ranked,
        "actual_top3": actual_top3,
    }


def _summarize_evals(evals: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_model_races(evals)
    total = len(evals)
    if not total:
        return summary
    summary.update(
        {
            "top5_all_top3": sum(item["top5_all_top3"] for item in evals),
            "top5_at_least2_top3": sum(item["top5_at_least2_top3"] for item in evals),
            "winner_in_top5": sum(item["winner_in_top5"] for item in evals),
            "avg_top5_actual_top3_hits": round(sum(item["top5_actual_top3_hits"] for item in evals) / total, 3),
        }
    )
    return summary


def _candidate_weight_sets() -> list[dict[str, float]]:
    keys = list(WEIGHT_GRID.keys())
    candidates: list[dict[str, float]] = []
    for values in product(*(WEIGHT_GRID[key] for key in keys)):
        weights = {key: round(value, 2) for key, value in zip(keys, values)}
        if abs(sum(weights.values()) - 1.0) > 1e-9:
            continue
        if weights["horse_health"] > weights["form_line"] + 0.04:
            continue
        if weights["race_shape"] > 0.24:
            continue
        candidates.append(weights)
    return candidates


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    return {
        key: round(float(candidate.get(key, 0)) - float(baseline.get(key, 0)), 4)
        for key in METRIC_ORDER
        if key in candidate or key in baseline
    }


def _score_candidate_tuple(summary: dict[str, Any], baseline: dict[str, Any]) -> tuple[Any, ...]:
    delta = _metric_delta(summary, baseline)
    return (
        delta.get("champion", 0),
        delta.get("top3_has_champion", 0),
        delta.get("min_threshold", 0),
        delta.get("mrr", 0),
        delta.get("avg_top4_hits", 0),
        delta.get("top5_at_least2_top3", 0),
        -delta.get("order_issue", 0),
        -delta.get("avg_winner_rank", 0),
    )


def _dimension_diagnostics(races: list[dict[str, Any]], baseline_evals: list[dict[str, Any]]) -> dict[str, Any]:
    top5_miss_edges: dict[str, list[float]] = defaultdict(list)
    top3_miss_edges: dict[str, list[float]] = defaultdict(list)
    winner_outside_top5 = []

    for race, evaluation in zip(races, baseline_evals):
        winner = evaluation["actual_top3"][0] if evaluation["actual_top3"] else None
        if winner is None:
            continue
        winner_row = next((row for row in evaluation["ranked"] if row["horse_num"] == winner), None)
        if not winner_row:
            continue
        field_mean = {
            key: sum(horse["matrix_scores"][key] for horse in race["horses"]) / len(race["horses"])
            for key in CURRENT_MATRIX_FORMULAS
        }
        target = top5_miss_edges if evaluation["winner_rank"] > 5 else top3_miss_edges if evaluation["winner_rank"] > 3 else None
        if target is not None:
            for key in CURRENT_MATRIX_FORMULAS:
                target[key].append(round(winner_row["matrix_scores"][key] - field_mean[key], 4))
        if evaluation["winner_rank"] > 5:
            winner_outside_top5.append(
                {
                    "meeting": race["meeting"],
                    "race": race["race"],
                    "winner": winner,
                    "winner_rank": evaluation["winner_rank"],
                    "picks": evaluation["picks"],
                    "top5": evaluation["top5"],
                }
            )

    def summarize_edges(values: dict[str, list[float]]) -> dict[str, float]:
        return {
            key: round(sum(items) / len(items), 3)
            for key, items in sorted(values.items())
            if items
        }

    return {
        "winner_outside_top5_count": len(winner_outside_top5),
        "winner_outside_top5_examples": winner_outside_top5[:12],
        "avg_winner_matrix_edge_when_outside_top3": summarize_edges(top3_miss_edges),
        "avg_winner_matrix_edge_when_outside_top5": summarize_edges(top5_miss_edges),
    }


def run_shadow_diagnostics(limit_candidates: int = 12) -> dict[str, Any]:
    races = _load_archive_races()
    baseline_evals = [_evaluate_weights_for_race(race, CURRENT_MATRIX_WEIGHTS) for race in races]
    baseline = _summarize_evals(baseline_evals)

    candidates = []
    for weights in _candidate_weight_sets():
        evals = [_evaluate_weights_for_race(race, weights) for race in races]
        summary = _summarize_evals(evals)
        gate = evaluate_gate(summary, baseline)
        candidates.append(
            {
                "weights": weights,
                "metrics": summary,
                "delta": _metric_delta(summary, baseline),
                "gate": gate,
                "score_tuple": _score_candidate_tuple(summary, baseline),
            }
        )

    candidates.sort(key=lambda item: item["score_tuple"], reverse=True)
    passing = [item for item in candidates if item["gate"]["status"] == "PASS"]
    improving = [
        item
        for item in passing
        if any(value > 0 for key, value in item["delta"].items() if key not in {"order_issue", "avg_winner_rank", "avg_pick1_finish"})
        or any(item["delta"].get(key, 0) < 0 for key in ("order_issue", "avg_winner_rank", "avg_pick1_finish"))
    ]

    for item in candidates:
        item.pop("score_tuple", None)

    return {
        "scope": {
            "races": len(races),
            "candidate_count": len(candidates),
            "contract": "shadow only; no odds/market data; no rank_score tie-break; ranking is weighted 7D ability only",
        },
        "baseline_weights": CURRENT_MATRIX_WEIGHTS,
        "baseline_metrics": baseline,
        "passing_candidates": passing[:limit_candidates],
        "improving_passing_candidates": improving[:limit_candidates],
        "top_candidates": candidates[:limit_candidates],
        "diagnostics": _dimension_diagnostics(races, baseline_evals),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "HKJC 7D shadow diagnostics",
        f"- Scope: {report['scope']['races']} races, {report['scope']['candidate_count']} clean 7D candidates",
        f"- Contract: {report['scope']['contract']}",
        "- Baseline:",
    ]
    baseline = report["baseline_metrics"]
    lines.append(
        f"  Gold {baseline.get('gold')}, Good {baseline.get('good')}, Pass {baseline.get('min_threshold')}, "
        f"Champion {baseline.get('champion')}, MRR {baseline.get('mrr')}, AvgTop4 {baseline.get('avg_top4_hits')}, "
        f"Top5>=2Top3 {baseline.get('top5_at_least2_top3')}, WinnerTop5 {baseline.get('winner_in_top5')}"
    )
    lines.append(f"- Improving candidates passing no-regression: {len(report['improving_passing_candidates'])}")
    for idx, item in enumerate(report["improving_passing_candidates"][:5], start=1):
        lines.append(f"  {idx}. weights={json.dumps(item['weights'], sort_keys=True)}")
        lines.append(f"     delta={json.dumps(item['delta'], sort_keys=True)}")
    if not report["improving_passing_candidates"]:
        lines.append("  none")

    diagnostics = report["diagnostics"]
    lines.extend(
        [
            "- Diagnostic notes:",
            f"  Winner outside model Top5: {diagnostics['winner_outside_top5_count']}",
            f"  Avg winner matrix edge when outside Top3: {json.dumps(diagnostics['avg_winner_matrix_edge_when_outside_top3'], ensure_ascii=False, sort_keys=True)}",
            f"  Avg winner matrix edge when outside Top5: {json.dumps(diagnostics['avg_winner_matrix_edge_when_outside_top5'], ensure_ascii=False, sort_keys=True)}",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="HKJC clean 7D shadow diagnostics without production scoring changes")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--limit-candidates", type=int, default=12)
    args = parser.parse_args()

    report = run_shadow_diagnostics(limit_candidates=args.limit_candidates)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
