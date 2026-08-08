#!/usr/bin/env python3
"""Re-score aligned AU Logic snapshots with micro-weight families disabled.

Unlike cached leaf ablation, this executes the current RacingEngine from raw
pre-race Logic.  Result position/SP are joined only after scoring and are never
placed in race_context or horse data.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from statistics import mean

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))
sys.path.insert(0, str(PROJECT_ROOT / ".agents" / "skills" / "shared_racing"))

from au_archive_calibrator import (
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    get_true_horse_name,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)
from au_auto_orchestrator import _build_field_summary, _facts_path_for_logic
from eval_metrics import race_metrics, summarize_races
from engine_core import RacingEngine, backfill_pf_metrics, enrich_logic_from_facts
from io_utils import write_json_atomic, write_text_atomic
from scoring import (
    CLASS_MICRO_WEIGHTS,
    CONSISTENCY_MICRO_WEIGHTS,
    FIT_MICRO_WEIGHTS,
    PACE_MICRO_WEIGHTS,
    TRIAL_MICRO_WEIGHTS,
    TRACK_MICRO_WEIGHTS,
)


# 2026-08-04：`form_line` 同 `trainer` 兩族已經由 `scoring.py` 剷走 ——
# 呢個工具喺 718 場上量到佢哋**改動場次 0**，即係從未觸發，所以剷得。
# 剩返六族全部量過有代價（詳見 `scoring.py` 嘅審查表），唔可以順手剷。
#
# ⚠️ `form_line` 以前唔喺呢個表 —— 即係佢從未被 ablate 過，而佢正正係其中
# 一個剷得嘅。「預期惰性」同「量過係惰性」係兩件事。
MICRO_FAMILIES = {
    "class": CLASS_MICRO_WEIGHTS,
    "trial": TRIAL_MICRO_WEIGHTS,
    "consistency": CONSISTENCY_MICRO_WEIGHTS,
    "track": TRACK_MICRO_WEIGHTS,
    "pace": PACE_MICRO_WEIGHTS,
    "jockey_horse_fit": FIT_MICRO_WEIGHTS,
}


def neutral_value(key: str) -> float:
    return 60.0 if "base" in key else 0.0


def variant_patches(
    mode: str,
    families: set[str] | None = None,
    micro_keys: set[str] | None = None,
) -> list[tuple[str, list[tuple[dict, str, float]]]]:
    selected = {
        family: weights
        for family, weights in MICRO_FAMILIES.items()
        if families is None or family in families
    }
    variants: list[tuple[str, list[tuple[dict, str, float]]]] = [
        ("revised_current", [])
    ]
    if mode in {"groups", "all"}:
        for family, weights in selected.items():
            keys = [
                key
                for key in weights
                if micro_keys is None or f"{family}.{key}" in micro_keys
            ]
            variants.append(
                (
                    f"drop_group:{family}",
                    [
                        (weights, key, neutral_value(key))
                        for key in keys
                    ],
                )
            )
        variants.append(
            (
                "drop_group:all_micro",
                [
                    (weights, key, neutral_value(key))
                    for family, weights in selected.items()
                    for key in weights
                    if micro_keys is None or f"{family}.{key}" in micro_keys
                ],
            )
        )
    if mode in {"individual", "all"}:
        for family, weights in selected.items():
            for key in weights:
                if micro_keys is not None and f"{family}.{key}" not in micro_keys:
                    continue
                variants.append(
                    (
                        f"drop_micro:{family}.{key}",
                        [(weights, key, neutral_value(key))],
                    )
                )
    return variants


@contextmanager
def patched_weights(patches: list[tuple[dict, str, float]]):
    originals = [(weights, key, weights[key]) for weights, key, _value in patches]
    try:
        for weights, key, value in patches:
            weights[key] = value
        yield
    finally:
        for weights, key, value in originals:
            weights[key] = value


def discover_logic_files(archive_root: Path) -> tuple[list[Path], list[Path]]:
    # Completed meetings are moved under ``Archive/`` by the daily scheduler.
    # A one-level glob silently dropped every archived meeting from all runtime
    # audits, so discovery must follow the meeting files rather than assume one
    # fixed directory depth.
    files = sorted(
        archive_root.rglob("Race_*_Logic.json"),
        key=lambda path: (
            str(path.parent.relative_to(archive_root)),
            path.parent.name,
            parse_int(path.stem, 999),
        ),
    )
    materialized = []
    placeholders = []
    for path in files:
        try:
            downloaded = path.stat().st_blocks > 0
        except OSError:
            downloaded = False
        (materialized if downloaded else placeholders).append(path)
    return materialized, placeholders


def aligned_race(
    logic_path: Path,
    historical_results: dict,
) -> tuple[dict, list[dict]] | tuple[None, str]:
    try:
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"logic_read_error:{type(exc).__name__}"
    race_analysis = logic.get("race_analysis")
    horses = logic.get("horses")
    if not isinstance(race_analysis, dict) or not isinstance(horses, dict):
        return None, "invalid_logic_shape"
    meeting_date = detect_meeting_date(logic_path.parent)
    meeting_track = detect_meeting_track(logic_path.parent, logic)
    race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem)
    if not meeting_date or not meeting_track or not race_no:
        return None, "missing_race_identity"
    result_rows = choose_track_rows(
        historical_results.get((meeting_date, race_no), []),
        meeting_track,
    )
    if not result_rows:
        return None, "no_aligned_result_race"
    result_lookup = {row["horse_slug"]: row for row in result_rows}
    aligned = []
    for horse_number, horse in horses.items():
        result = result_lookup.get(
            normalize_horse_name(get_true_horse_name(horse))
        )
        if result is None:
            continue
        aligned.append(
            {
                "horse_number": parse_int(horse_number, 999),
                "horse": horse,
                "actual_pos": int(result["pos"]),
                "result_sp_label": result.get("sp"),
            }
        )
    if len(aligned) < 4 or sum(row["actual_pos"] <= 3 for row in aligned) < 3:
        return None, "insufficient_horse_or_top3_overlap"
    return logic, aligned


def iter_aligned_races(
    files: list[Path],
    historical_results: dict,
    *,
    prefetch_workers: int = 1,
):
    """Yield aligned Logic in file order with a small bounded read-ahead.

    File Provider placeholders can take seconds to materialize.  A bounded
    queue overlaps that I/O with scoring without holding the archive in memory.
    """
    workers = max(1, int(prefetch_workers))
    if workers == 1:
        for path in files:
            yield path, aligned_race(path, historical_results)
        return

    pending = deque()
    file_iter = iter(files)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for path in file_iter:
            pending.append(
                (path, executor.submit(aligned_race, path, historical_results))
            )
            if len(pending) >= workers * 2:
                queued_path, future = pending.popleft()
                yield queued_path, future.result()
        while pending:
            queued_path, future = pending.popleft()
            yield queued_path, future.result()


def prepare_logic_for_scoring(logic: dict, logic_path: Path) -> tuple[dict, Path | None]:
    """Build the same pre-score snapshot used by the live auto orchestrator.

    Archive Logic is only an intermediate snapshot.  The live path refreshes it
    from the matching Facts/Formguide before PF backfill and field-relative
    scoring.  Runtime audits must do the same or they silently evaluate stale
    going, form and sectional evidence.
    """
    prepared = copy.deepcopy(logic)
    analysis = prepared.get("race_analysis") or {}
    race_number = analysis.get("race_number") or parse_int(logic_path.stem)
    facts_path = _facts_path_for_logic(logic_path, race_number)
    if facts_path is not None:
        enrich_logic_from_facts(prepared, facts_path)
    backfill_pf_metrics(prepared, facts_path)
    return prepared, facts_path


def score_variant(
    logic: dict,
    aligned: list[dict],
    logic_path: Path,
    patches: list[tuple[dict, str, float]],
    *,
    include_details: bool = False,
    prepared_logic: dict | None = None,
    facts_path: Path | None = None,
) -> list[dict]:
    if prepared_logic is None:
        prepared_logic, facts_path = prepare_logic_for_scoring(logic, logic_path)
    race_context = copy.deepcopy(prepared_logic["race_analysis"])
    race_context["field_summary"] = _build_field_summary(prepared_logic["horses"])
    race_context["field_horse_names"] = [
        horse.get("horse_name")
        for horse in prepared_logic["horses"].values()
        if isinstance(horse, dict) and horse.get("horse_name")
    ]
    scores = []
    with patched_weights(patches):
        for source in aligned:
            horse_number = source["horse_number"]
            prepared_horse = (
                prepared_logic["horses"].get(str(horse_number))
                or prepared_logic["horses"].get(horse_number)
                or source["horse"]
            )
            horse = dict(prepared_horse)
            horse.setdefault("horse_number", source["horse_number"])
            data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
            result = RacingEngine(
                horse,
                race_context,
                facts_section=data.get("facts_section", ""),
                facts_path=facts_path,
            ).analyze_horse()
            row = {
                "horse_number": source["horse_number"],
                "horse_name": get_true_horse_name(horse),
                "score": float(result["ability_score"]),
                "actual_pos": source["actual_pos"],
                "result_sp_label": source["result_sp_label"],
            }
            if include_details:
                row.update(
                    {
                        "matrix_scores": result["matrix_scores"],
                        "feature_scores": result["feature_scores"],
                        "wet_form_feature": result["wet_form_feature"],
                        "feature_evidence_state": result["feature_evidence_state"],
                        "data_coverage": result["data_coverage"],
                        "reason_codes": result["reason_codes"],
                        "risk_flags": result["risk_flags"],
                    }
                )
            scores.append(row)
    return scores


def metrics_for_scored_races(races: list[list[dict]]) -> dict:
    evaluated = []
    outsider_ranks = []
    outsider_winners = []
    race_dates = []
    for race in races:
        ranked = sorted(
            race,
            key=lambda row: (-row["score"], row["horse_number"]),
        )
        identifiers = [
            (row["horse_number"], row["horse_name"])
            for row in ranked
        ]
        positions = {
            (row["horse_number"], row["horse_name"]): row["actual_pos"]
            for row in race
        }
        actual_top3 = {
            horse for horse, position in positions.items() if position <= 3
        }
        evaluated.append(
            race_metrics(
                identifiers,
                actual_top3,
                actual_pos=positions,
                field_size=len(positions),
            )
        )
        model_rank = {identifier: index for index, identifier in enumerate(identifiers, 1)}
        for row in race:
            sp = row.get("result_sp_label")
            if sp is None or float(sp) < 31 or row["actual_pos"] > 3:
                continue
            rank = model_rank[(row["horse_number"], row["horse_name"])]
            outsider_ranks.append(rank)
            if row["actual_pos"] == 1:
                outsider_winners.append(rank)
    summary = summarize_races(evaluated)
    rates = summary["rates"]
    comp = summary["competitiveness"]
    return {
        "races": summary["races"],
        "gold": rates["gold"],
        "good_positional": rates["good_positional"],
        "pass": rates["pass"],
        "zero_hit": summary["hit_distribution"]["0hit"] / max(1, summary["races"]),
        "one_hit": summary["hit_distribution"]["1hit"] / max(1, summary["races"]),
        "winner_top3": rates["winner_in_top3"],
        "winner_top5": rates["winner_in_top5"],
        "mrr": summary["mrr"],
        "top3_all_within_top4": comp["top3_all_within_top4"]["rate"],
        "top3_capture_at4": comp["mean_top3_capture_at4"],
        "top3_capture_at5": comp["mean_top3_capture_at5"],
        "competitive_recall_at5": comp["mean_competitive_recall_at5"],
        "competitive_precision_at5": comp["mean_competitive_precision_at5"],
        "ndcg_at5": comp["mean_ndcg_at5"],
        "top_pick_blowout": comp["top_pick_blowout"]["rate"],
        "mean_top3_model_rank": comp["mean_top3_model_rank"],
        "outsider_sp31_top3": len(outsider_ranks),
        "outsider_sp31_capture_at5": (
            sum(rank <= 5 for rank in outsider_ranks) / len(outsider_ranks)
            if outsider_ranks else None
        ),
        "outsider_sp31_mean_model_rank": (
            mean(outsider_ranks) if outsider_ranks else None
        ),
        "outsider_sp31_winner_at5": (
            sum(rank <= 5 for rank in outsider_winners) / len(outsider_winners)
            if outsider_winners else None
        ),
    }


def metric_delta(candidate: dict, baseline: dict) -> dict:
    return {
        key: candidate[key] - baseline[key]
        for key in candidate
        if key != "races"
        and isinstance(candidate.get(key), (int, float))
        and isinstance(baseline.get(key), (int, float))
    }


def score_diagnostics(
    candidate_races: list[list[dict]],
    baseline_races: list[list[dict]],
) -> dict:
    changed_horses = 0
    changed_races = 0
    ranking_changed_races = 0
    max_abs_score_delta = 0.0
    for candidate, baseline in zip(candidate_races, baseline_races):
        base_lookup = {
            (row["horse_number"], row["horse_name"]): row["score"]
            for row in baseline
        }
        race_changed = False
        for row in candidate:
            identifier = (row["horse_number"], row["horse_name"])
            delta = abs(row["score"] - base_lookup[identifier])
            max_abs_score_delta = max(max_abs_score_delta, delta)
            if delta > 1e-9:
                changed_horses += 1
                race_changed = True
        changed_races += int(race_changed)
        candidate_rank = [
            (row["horse_number"], row["horse_name"])
            for row in sorted(
                candidate,
                key=lambda row: (-row["score"], row["horse_number"]),
            )
        ]
        baseline_rank = [
            (row["horse_number"], row["horse_name"])
            for row in sorted(
                baseline,
                key=lambda row: (-row["score"], row["horse_number"]),
            )
        ]
        ranking_changed_races += int(candidate_rank != baseline_rank)
    return {
        "changed_horses": changed_horses,
        "changed_races": changed_races,
        "ranking_changed_races": ranking_changed_races,
        "max_abs_score_delta": round(max_abs_score_delta, 8),
    }


def date_partitions(
    race_dates: list[str],
    *,
    holdout_fraction: float,
    folds: int = 5,
) -> tuple[set[int], set[int], list[set[int]]]:
    dates = sorted(set(race_dates))
    holdout_date_count = max(1, math.ceil(len(dates) * holdout_fraction))
    holdout_dates = set(dates[-holdout_date_count:])
    dev_dates = dates[:-holdout_date_count]
    fold_size = max(1, math.ceil(len(dev_dates) / folds))
    fold_dates = [
        set(dev_dates[index : index + fold_size])
        for index in range(0, len(dev_dates), fold_size)
    ]
    dev_indices = {index for index, date in enumerate(race_dates) if date not in holdout_dates}
    holdout_indices = {index for index, date in enumerate(race_dates) if date in holdout_dates}
    fold_indices = [
        {index for index, date in enumerate(race_dates) if date in bucket}
        for bucket in fold_dates
    ]
    return dev_indices, holdout_indices, fold_indices


def select_indices(races: list[list[dict]], indices: set[int]) -> list[list[dict]]:
    return [race for index, race in enumerate(races) if index in indices]


def build_report(
    variants: list[tuple[str, list[tuple[dict, str, float]]]],
    scored: dict[str, list[list[dict]]],
    race_dates: list[str],
    rejections: dict[str, int],
    *,
    holdout_fraction: float,
) -> dict:
    dev_indices, holdout_indices, fold_indices = date_partitions(
        race_dates,
        holdout_fraction=holdout_fraction,
    )
    baseline_dev = metrics_for_scored_races(
        select_indices(scored["revised_current"], dev_indices)
    )
    baseline_holdout = metrics_for_scored_races(
        select_indices(scored["revised_current"], holdout_indices)
    )
    output = {
        "design": {
            "aligned_races": len(race_dates),
            "development_races": len(dev_indices),
            "terminal_holdout_races": len(holdout_indices),
            "fold_races": [len(indices) for indices in fold_indices],
            "outcome_only_fields": [
                "actual_pos",
                "result_sp_label",
            ],
            "rejections": rejections,
        },
        "variants": {},
    }
    for name, _patches in variants:
        dev = metrics_for_scored_races(select_indices(scored[name], dev_indices))
        holdout = metrics_for_scored_races(
            select_indices(scored[name], holdout_indices)
        )
        fold_deltas = []
        for indices in fold_indices:
            candidate_fold = metrics_for_scored_races(
                select_indices(scored[name], indices)
            )
            baseline_fold = metrics_for_scored_races(
                select_indices(scored["revised_current"], indices)
            )
            fold_deltas.append(metric_delta(candidate_fold, baseline_fold))
        output["variants"][name] = {
            "development": dev,
            "terminal_holdout": holdout,
            "delta_development_vs_current": metric_delta(dev, baseline_dev),
            "delta_holdout_vs_current": metric_delta(holdout, baseline_holdout),
            "fold_deltas_vs_current": fold_deltas,
            "score_diagnostics_all_races": score_diagnostics(
                scored[name],
                scored["revised_current"],
            ),
        }
    return output


def render_markdown(report: dict) -> str:
    def pct(value) -> str:
        return "n/a" if value is None else f"{value * 100:.2f}%"

    lines = [
        "# AU Runtime Micro-Ablation",
        "",
        f"- Aligned races: {report['design']['aligned_races']}",
        f"- Development / terminal holdout: {report['design']['development_races']} / {report['design']['terminal_holdout_races']}",
        "- Result/SP 只喺 engine 完成評分後先 join，從未放入 model input。",
        "",
        "| Variant | Changed races | Rank-changed races | Dev Comp R@5 Δ | Dev NDCG Δ | Dev W@5 Δ | Dev 0-hit Δ | Hold Comp R@5 Δ | Hold NDCG Δ | Hold W@5 Δ | Hold 0-hit Δ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in report["variants"].items():
        dev = result["delta_development_vs_current"]
        hold = result["delta_holdout_vs_current"]
        diagnostics = result["score_diagnostics_all_races"]
        lines.append(
            f"| {name} | {diagnostics['changed_races']} | "
            f"{diagnostics['ranking_changed_races']} | "
            f"{pct(dev.get('competitive_recall_at5'))} | "
            f"{pct(dev.get('ndcg_at5'))} | {pct(dev.get('winner_top5'))} | "
            f"{pct(dev.get('zero_hit'))} | {pct(hold.get('competitive_recall_at5'))} | "
            f"{pct(hold.get('ndcg_at5'))} | {pct(hold.get('winner_top5'))} | "
            f"{pct(hold.get('zero_hit'))} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--results-csv", type=Path, required=True)
    parser.add_argument("--mode", choices=("groups", "individual", "all"), default="groups")
    parser.add_argument(
        "--family",
        action="append",
        choices=tuple(MICRO_FAMILIES),
        help="Limit ablation to one or more repeatable signal families.",
    )
    parser.add_argument(
        "--micro-key",
        action="append",
        help="Limit ablation to repeatable FAMILY.KEY micro parameters.",
    )
    parser.add_argument("--limit-races", type=int)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument(
        "--materialize-on-demand",
        action="store_true",
        help=(
            "Include Drive placeholders and fetch each Logic file when read. "
            "Useful when macOS evicts cloud files under low disk space."
        ),
    )
    parser.add_argument(
        "--prefetch-workers",
        type=int,
        default=4,
        help="Bounded concurrent Logic reads used with --materialize-on-demand.",
    )
    parser.add_argument("--holdout-fraction", type=float, default=0.15)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/private/tmp/au_runtime_micro_ablation.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("/private/tmp/au_runtime_micro_ablation.md"),
    )
    args = parser.parse_args()

    files, placeholders = discover_logic_files(args.archive_root)
    if args.require_complete and placeholders and not args.materialize_on_demand:
        raise SystemExit(
            f"Archive incomplete: {len(files)} materialized, "
            f"{len(placeholders)} placeholders."
        )
    if args.materialize_on_demand:
        files = files + placeholders
        files.sort(
            key=lambda path: (
                path.parent.name,
                parse_int(path.stem, 999),
            )
        )
    if args.limit_races:
        files = files[: args.limit_races]
    historical_results = load_historical_results(args.results_csv)
    micro_keys = set(args.micro_key) if args.micro_key else None
    if micro_keys:
        valid_micro_keys = {
            f"{family}.{key}"
            for family, weights in MICRO_FAMILIES.items()
            for key in weights
        }
        invalid = sorted(micro_keys - valid_micro_keys)
        if invalid:
            raise SystemExit(f"Unknown --micro-key values: {invalid}")
    selected_families = set(args.family) if args.family else None
    if micro_keys and selected_families is None:
        selected_families = {key.split(".", 1)[0] for key in micro_keys}
    variants = variant_patches(
        args.mode,
        selected_families,
        micro_keys,
    )
    scored = {name: [] for name, _patches in variants}
    race_dates = []
    rejections: dict[str, int] = {}
    aligned_iter = iter_aligned_races(
        files,
        historical_results,
        prefetch_workers=(
            args.prefetch_workers if args.materialize_on_demand else 1
        ),
    )
    for index, (logic_path, aligned) in enumerate(aligned_iter, 1):
        if aligned[0] is None:
            reason = aligned[1]
            rejections[reason] = rejections.get(reason, 0) + 1
            continue
        logic, race_rows = aligned
        prepared_logic, facts_path = prepare_logic_for_scoring(logic, logic_path)
        race_dates.append(detect_meeting_date(logic_path.parent))
        for name, patches in variants:
            scored[name].append(
                score_variant(
                    logic,
                    race_rows,
                    logic_path,
                    patches,
                    prepared_logic=prepared_logic,
                    facts_path=facts_path,
                )
            )
        if index == 1 or index % 25 == 0:
            print(f"Scored {index}/{len(files)} Logic races", flush=True)

    if not race_dates:
        raise SystemExit("No aligned, materialized Logic races available.")
    read_failures = sum(
        count
        for reason, count in rejections.items()
        if reason.startswith("logic_read_error:")
    )
    if args.require_complete and read_failures:
        raise SystemExit(
            f"Archive read failed for {read_failures} Logic files: {rejections}"
        )
    report = build_report(
        variants,
        scored,
        race_dates,
        rejections,
        holdout_fraction=args.holdout_fraction,
    )
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render_markdown(report))
    print(f"Aligned races: {len(race_dates)}")
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
