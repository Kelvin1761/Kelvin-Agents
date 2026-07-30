#!/usr/bin/env python3
"""Audit unused HKJC pre-race signals after the current production rebalance.

This is discovery-only.  Direction is selected on the development meetings,
then reported unchanged on temporal holdout, adjusted races, recent meetings,
and the independent 2026-07-15 meeting.  No odds or post-race incident text is
used as a feature.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
ENGINE = (
    ROOT / ".agents" / "skills" / "hkjc_racing"
    / "hkjc_wong_choi_auto" / "scripts" / "racing_engine"
)
sys.path.insert(0, str(ENGINE))

from scoring import MATRIX_WEIGHTS  # noqa: E402


DEFAULT_INPUTS = [
    ROOT / "scratch" / "hkjc_ranking_dataset_current.csv",
    ROOT / "scratch" / "hkjc_ranking_dataset_2026_07_15_current.csv",
]
DEFAULT_MANIFEST = ROOT / "scratch" / "hkjc_zero_one_hit_manifest.csv"
DEFAULT_ANNOTATIONS = ROOT / "scratch" / "hkjc_anomaly_annotations.csv"
DEFAULT_JSON = ROOT / "scratch" / "hkjc_iterative_feature_audit.json"
DEFAULT_REPORT = ROOT / "scratch" / "hkjc_iterative_feature_audit_report.md"
MATRIX_NAMES = tuple(MATRIX_WEIGHTS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def as_int(value: Any, default: int = 0) -> int:
    value = as_float(value)
    return int(value) if value is not None else default


def race_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row["meeting_name"]), as_int(row["race_number"])


def horse_key(row: dict[str, Any]) -> tuple[str, int, int]:
    meeting, race = race_key(row)
    return meeting, race, as_int(row["horse_number"])


def ratio(
    row: dict[str, Any],
    numerator_columns: tuple[str, ...],
    denominator_column: str,
    *,
    prior_rate: float,
    prior_starts: float,
) -> float | None:
    starts = as_float(row.get(denominator_column))
    values = [as_float(row.get(column)) for column in numerator_columns]
    if starts is None or starts <= 0 or any(value is None for value in values):
        return None
    places = sum(float(value) for value in values if value is not None)
    return (places + prior_rate * prior_starts) / (starts + prior_starts)


def inverse(column: str) -> Callable[[dict[str, Any]], float | None]:
    return lambda row: (
        -float(value)
        if (value := as_float(row.get(column))) is not None
        else None
    )


def direct(column: str) -> Callable[[dict[str, Any]], float | None]:
    return lambda row: as_float(row.get(column))


def flag_balance(row: dict[str, Any]) -> float:
    positives = sum(
        as_int(row.get(column))
        for column in (
            "flag_engine_progressive",
            "flag_finish_competitive",
            "flag_energy_up",
            "flag_l400_up",
            "flag_margin_narrowing",
            "flag_hidden_form",
            "flag_forgiveness",
            "flag_track_bias_positive",
        )
    )
    negatives = sum(
        as_int(row.get(column))
        for column in (
            "flag_engine_fastslow",
            "flag_finish_slow",
            "flag_energy_down",
            "flag_l400_down",
            "flag_trackwork_slowing",
            "flag_medical_issue",
            "flag_margin_widening",
            "flag_track_bias_negative",
        )
    )
    return float(positives - negatives)


SIGNALS: dict[str, Callable[[dict[str, Any]], float | None]] = {
    "card_rating": direct("card_rating"),
    "card_rating_change": direct("card_rating_change"),
    "starts": direct("starts"),
    "career_win_rate_shrunk": lambda row: ratio(
        row, ("wins",), "starts", prior_rate=0.08, prior_starts=10
    ),
    "last6_mean_finish": inverse("last6_mean_finish"),
    "last6_best_finish": inverse("last6_best_finish"),
    "last6_top3_count": direct("last6_top3_count"),
    "last6_top5_count": direct("last6_top5_count"),
    "season_place_rate_k8": lambda row: ratio(
        row,
        ("season_wins", "season_seconds", "season_thirds"),
        "season_starts",
        prior_rate=0.25,
        prior_starts=8,
    ),
    "same_distance_place_rate_k6": lambda row: ratio(
        row,
        ("same_distance_wins", "same_distance_seconds", "same_distance_thirds"),
        "same_distance_starts",
        prior_rate=0.25,
        prior_starts=6,
    ),
    "same_venue_distance_place_rate_k6": lambda row: ratio(
        row,
        (
            "same_venue_distance_wins",
            "same_venue_distance_seconds",
            "same_venue_distance_thirds",
        ),
        "same_venue_distance_starts",
        prior_rate=0.25,
        prior_starts=6,
    ),
    "trackwork_entries": direct("tw_entries_count"),
    "trackwork_gallops": direct("tw_gallop_count"),
    "trackwork_jockey_present": direct("tw_jockey_present"),
    "raw_l400": inverse("raw_l400"),
    "raw_finish_time_adj": inverse("raw_finish_time_adj"),
    "raw_last_margin": inverse("raw_last_margin"),
    "raw_last_finish": inverse("raw_last_finish"),
    "prior_combo_place_edge": direct("prior_combo_place_edge"),
    "prior_jockey_cd_place_edge": direct("prior_jockey_cd_place_edge"),
    "prior_trainer_cd_place_edge": direct("prior_trainer_cd_place_edge"),
    "prior_class_distance_place_edge": direct("prior_class_distance_place_edge"),
    "prior_draw_class_place_edge": direct("prior_draw_class_place_edge"),
    "prior_weight_class_place_edge": direct("prior_weight_class_place_edge"),
    "prior_rest_bucket_place_edge": direct("prior_rest_bucket_place_edge"),
    "prior_runstyle_cd_place_edge": direct("prior_runstyle_cd_place_edge"),
    "prior_horse_cd_place_edge": direct("prior_horse_cd_place_edge"),
    "prior_horse_rest_place_edge": direct("prior_horse_rest_place_edge"),
    "prior_horse_style_place_edge": direct("prior_horse_style_place_edge"),
    "forensic_flag_balance": flag_balance,
    "hidden_form": direct("flag_hidden_form"),
    "forgiveness": direct("flag_forgiveness"),
    "progressive": direct("flag_engine_progressive"),
    "finish_competitive": direct("flag_finish_competitive"),
    "margin_narrowing": direct("flag_margin_narrowing"),
    "medical_issue_inverse": inverse("flag_medical_issue"),
}


def auc(pairs: list[tuple[float, bool]]) -> float | None:
    positives = [value for value, label in pairs if label]
    negatives = [value for value, label in pairs if not label]
    if not positives or not negatives:
        return None
    wins = ties = 0
    for positive in positives:
        for negative in negatives:
            wins += positive > negative
            ties += positive == negative
    return (wins + 0.5 * ties) / (len(positives) * len(negatives))


def live_ability(row: dict[str, Any]) -> float:
    return sum(
        float(as_float(row.get(f"matrix_{name}"), 60.0) or 60.0) * weight
        for name, weight in MATRIX_WEIGHTS.items()
    )


def split_meetings(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    dates: dict[str, str] = {}
    for row in rows:
        meeting = str(row["meeting_name"])
        date = str(row.get("date") or meeting[:10])
        dates[meeting] = min(date, dates.get(meeting, date))
    ordered = [meeting for meeting, _date in sorted(dates.items(), key=lambda item: (item[1], item[0]))]
    cut = max(1, math.floor(len(ordered) * 0.70))
    return {
        "development": set(ordered[:cut]),
        "temporal_holdout": set(ordered[cut:]),
        "recent": set(ordered[-8:]),
        "2026_07_15": {meeting for meeting in ordered if meeting.startswith("2026-07-15")},
        "all": set(ordered),
    }


def competitive_label(row: dict[str, Any]) -> bool:
    threshold = min(5, max(3, math.ceil(as_int(row["field_size"]) / 3)))
    return as_int(row["finish_pos"], 99) <= threshold


def evaluate_signal(
    rows: list[dict[str, Any]],
    extractor: Callable[[dict[str, Any]], float | None],
    *,
    meetings: set[str],
    abnormal_races: set[tuple[str, int]],
    adjusted: bool = False,
    top5_only: bool = False,
) -> dict[str, Any]:
    pairs = []
    available = 0
    total = 0
    for row in rows:
        if row["meeting_name"] not in meetings:
            continue
        if adjusted and race_key(row) in abnormal_races:
            continue
        if top5_only and as_int(row["live_rank"]) > 5:
            continue
        total += 1
        value = extractor(row)
        if value is None:
            continue
        available += 1
        pairs.append((float(value), competitive_label(row)))
    return {
        "auc": round(value, 6) if (value := auc(pairs)) is not None else None,
        "coverage": round(available / total, 6) if total else 0.0,
        "rows": total,
    }


def main() -> int:
    args = parse_args()
    sources = [Path(path) for path in args.input] or DEFAULT_INPUTS
    by_horse: dict[tuple[str, int, int], dict[str, Any]] = {}
    for source in sources:
        for row in read_csv(source):
            by_horse[horse_key(row)] = row
    rows = list(by_horse.values())

    if args.manifest.exists():
        valid = {
            (row["meeting"], as_int(row["race_number"]))
            for row in read_csv(args.manifest)
            if str(row.get("valid", "")).strip().lower() in ("true", "1", "yes")
        }
        rows = [row for row in rows if race_key(row) in valid]

    abnormal_races: set[tuple[str, int]] = set()
    if args.annotations.exists():
        for row in read_csv(args.annotations):
            if any(
                str(row.get(flag, "")).strip().lower() in ("true", "1", "yes")
                for flag in ("extreme_outsider", "major_incident", "interference", "injury", "abnormal")
            ):
                abnormal_races.add((row["meeting"], as_int(row["race_number"])))

    grouped: defaultdict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        row["live_ability"] = live_ability(row)
        grouped[race_key(row)].append(row)
    for race_rows in grouped.values():
        for rank, row in enumerate(
            sorted(
                race_rows,
                key=lambda item: (-float(item["live_ability"]), as_int(item["horse_number"])),
            ),
            start=1,
        ):
            row["live_rank"] = rank

    splits = split_meetings(rows)
    results: dict[str, Any] = {}
    for name, extractor in SIGNALS.items():
        result = {
            split: evaluate_signal(
                rows,
                extractor,
                meetings=meetings,
                abnormal_races=abnormal_races,
            )
            for split, meetings in splits.items()
        }
        result["adjusted_all"] = evaluate_signal(
            rows,
            extractor,
            meetings=splits["all"],
            abnormal_races=abnormal_races,
            adjusted=True,
        )
        result["adjusted_holdout"] = evaluate_signal(
            rows,
            extractor,
            meetings=splits["temporal_holdout"],
            abnormal_races=abnormal_races,
            adjusted=True,
        )
        result["top5_adjusted"] = evaluate_signal(
            rows,
            extractor,
            meetings=splits["all"],
            abnormal_races=abnormal_races,
            adjusted=True,
            top5_only=True,
        )
        dev_auc = result["development"]["auc"]
        holdout_auc = result["temporal_holdout"]["auc"]
        adjusted_auc = result["adjusted_all"]["auc"]
        top5_auc = result["top5_adjusted"]["auc"]
        result["stable"] = bool(
            result["all"]["coverage"] >= 0.30
            and dev_auc is not None
            and holdout_auc is not None
            and adjusted_auc is not None
            and top5_auc is not None
            and dev_auc >= 0.52
            and holdout_auc >= 0.52
            and adjusted_auc >= 0.52
            and top5_auc >= 0.52
        )
        results[name] = result

    ranked = sorted(
        results,
        key=lambda name: (
            not results[name]["stable"],
            -(results[name]["adjusted_all"]["auc"] or 0.0),
            -(results[name]["temporal_holdout"]["auc"] or 0.0),
        ),
    )
    payload = {
        "method": {
            "direction": "predefined from feature meaning; never flipped on result",
            "target": "leading-third competitive tier",
            "odds_in_feature": False,
            "post_race_incident_in_feature": False,
            "top5_boundary_audit": True,
        },
        "coverage": {
            "meetings": len(splits["all"]),
            "races": len(grouped),
            "runners": len(rows),
            "adjusted_exclusions": sum(key in abnormal_races for key in grouped),
        },
        "results": results,
        "ranked_signals": ranked,
        "stable_signals": [name for name in ranked if results[name]["stable"]],
    }
    args.json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# HKJC Iterative Feature Audit",
        "",
        f"- Coverage: {payload['coverage']['meetings']} meetings / {payload['coverage']['races']} races / {payload['coverage']['runners']} runners",
        f"- Adjusted exclusions: {payload['coverage']['adjusted_exclusions']}",
        f"- Stable signals: {', '.join(payload['stable_signals']) or 'none'}",
        "",
        "| Signal | Stable | Coverage | Dev AUC | Holdout AUC | Adjusted AUC | Adjusted Top5 AUC | 07-15 AUC |",
        "|---|:---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ranked:
        result = results[name]
        lines.append(
            f"| {name} | {'YES' if result['stable'] else 'NO'} | "
            f"{result['all']['coverage']:.1%} | "
            f"{(result['development']['auc'] or 0):.3f} | "
            f"{(result['temporal_holdout']['auc'] or 0):.3f} | "
            f"{(result['adjusted_all']['auc'] or 0):.3f} | "
            f"{(result['top5_adjusted']['auc'] or 0):.3f} | "
            f"{(result['2026_07_15']['auc'] or 0):.3f} |"
        )
    args.report_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload["coverage"], ensure_ascii=False))
    print(f"stable={payload['stable_signals']}")
    print(f"report={args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
