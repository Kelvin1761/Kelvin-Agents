#!/usr/bin/env python3
"""Evaluate HKJC rankings as a competitive field, not only Gold/Good/Pass.

The default 245-race replay contains outcome-isolated pre-race primitives and
the model ranking that was published for each race.  A companion rebuilt
dimension file supplies one common, outcome-free evidence vocabulary for
diagnosis.  Those rebuilt dimensions are diagnostic only and are never
represented as the production score.

Outputs:
  * JSON: complete metrics, provenance, cohort performance and weak-race rows
  * CSV: one structured row for every 0/1-hit race
  * Markdown: concise decision report

Optional anomaly annotations are deliberately external and auditable.  The
unfiltered benchmark is always reported; adjusted metrics never silently
remove a race.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[5]
SHARED_RACING = ROOT / ".agents" / "skills" / "shared_racing"
ENGINE_DIR = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_wong_choi_auto"
    / "scripts"
    / "racing_engine"
)
sys.path.insert(0, str(SHARED_RACING))
sys.path.insert(0, str(ENGINE_DIR))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402


DEFAULT_DATASET = ROOT / "scratch" / "hkjc_prerace_replay.csv"
DEFAULT_DIMENSIONS = ROOT / "scratch" / "hkjc_rebuilt_dimensions.csv"
DEFAULT_RICH_DATASET = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_reflector"
    / "artifacts"
    / "hkjc_ranking_dataset.csv"
)
DEFAULT_JSON = ROOT / "scratch" / "hkjc_competitiveness_review.json"
DEFAULT_CSV = ROOT / "scratch" / "hkjc_competitiveness_weak_races.csv"
DEFAULT_REPORT = ROOT / "scratch" / "hkjc_competitiveness_review_report.md"

DIMENSION_COLUMNS = {
    "段速": ("dim_speed_engine", "reliability_speed_engine"),
    "狀態穩定性": ("dim_stability", "reliability_stability"),
    "路程context": ("dim_distance_context", "reliability_distance_context"),
    "班次／負磅context": ("dim_class_weight", "reliability_class_weight"),
    "騎練訊號": ("dim_trainer_signal", "reliability_trainer_signal"),
    "備戰／風險": ("dim_readiness_risk", "reliability_readiness_risk"),
    "form line": ("dim_form_line", "reliability_form_line"),
}
ABNORMAL_FLAGS = (
    "extreme_outsider",
    "major_incident",
    "interference",
    "injury",
    "abnormal",
)


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def as_int(value: Any, default: int = 0) -> int:
    number = as_float(value)
    return int(round(number)) if number is not None else default


def as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "是"}


def meeting_name(row: dict[str, Any]) -> str:
    raw = str(row.get("meeting_name") or row.get("meeting") or "")
    return Path(raw).name


def race_key(row: dict[str, Any]) -> tuple[str, int]:
    return meeting_name(row), as_int(row.get("race_number"))


def horse_key(row: dict[str, Any]) -> tuple[str, int, int]:
    meeting, race = race_key(row)
    return meeting, race, as_int(row.get("horse_number"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_rich_context(path: Path | None) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[tuple[str, int, int], dict[str, Any]]]:
    if path is None or not path.exists():
        return {}, {}
    races: defaultdict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    horses: dict[tuple[str, int, int], dict[str, Any]] = {}
    for row in read_csv(path):
        key = race_key(row)
        if key[0] and key[1] > 0:
            races[key].append(row)
            horses[horse_key(row)] = row
    contexts = {}
    for key, rows in races.items():
        first = rows[0]
        race_class = str(first.get("race_class") or first.get("race_class_label") or "")
        contexts[key] = {
            "race_class": race_class,
            "is_new_horse_race": (
                "新馬" in race_class
                or race_class.strip().upper() in {"GR", "GRIFFIN", "MAIDEN"}
            ),
            "rich_runner_rows": len(rows),
        }
    return contexts, horses


def load_annotations(path: Path | None) -> dict[tuple[str, int], dict[str, Any]]:
    if path is None:
        return {}
    annotations = {}
    for row in read_csv(path):
        key = race_key(row)
        flags = [flag for flag in ABNORMAL_FLAGS if as_bool(row.get(flag))]
        annotations[key] = {
            "flags": flags,
            "excluded_from_adjusted": bool(flags),
            "notes": str(row.get("notes") or ""),
        }
    return annotations


def load_dimension_rows(path: Path | None) -> dict[tuple[str, int, int], dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    return {horse_key(row): row for row in read_csv(path)}


def load_rank_overrides(paths: list[Path]) -> dict[tuple[str, int, int], dict[str, float]]:
    """Re-rank complete fields from production matrix scores and live weights."""
    grouped: defaultdict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, int, int]] = set()
    for path in paths:
        if not path.exists():
            continue
        for row in read_csv(path):
            key = horse_key(row)
            if not key[0] or key[1] <= 0 or key[2] <= 0 or key in seen:
                continue
            seen.add(key)
            ability = sum(
                float(as_float(row.get(f"matrix_{name}"), 60.0) or 60.0) * weight
                for name, weight in MATRIX_WEIGHTS.items()
            )
            grouped[key[:2]].append(
                {
                    "horse_number": key[2],
                    "ability": ability,
                }
            )

    overrides: dict[tuple[str, int, int], dict[str, float]] = {}
    for race, rows in grouped.items():
        ranked = sorted(
            rows,
            key=lambda row: (-row["ability"], row["horse_number"]),
        )
        for rank, row in enumerate(ranked, start=1):
            overrides[(race[0], race[1], row["horse_number"])] = {
                "rank": rank,
                "score": round(row["ability"], 6),
            }
    return overrides


def normalise_races(
    dataset_path: Path,
    *,
    dimension_path: Path | None,
    rich_path: Path | None,
    annotation_path: Path | None,
    rank_override_paths: list[Path] | None = None,
) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(dataset_path):
        key = race_key(row)
        if key[0] and key[1] > 0:
            grouped[key].append(row)

    dimensions = load_dimension_rows(dimension_path)
    rich_contexts, rich_horses = load_rich_context(rich_path)
    annotations = load_annotations(annotation_path)
    rank_overrides = load_rank_overrides(rank_override_paths or [])
    races = []
    for key, rows in sorted(grouped.items()):
        first = rows[0]
        horses = []
        for row in rows:
            number = as_int(row.get("horse_number"))
            override = rank_overrides.get((key[0], key[1], number))
            rank = (
                as_int(override["rank"])
                if override
                else as_int(row.get("reference_original_rank") or row.get("current_live_rank"))
            )
            finish = as_int(row.get("label_finish_position") or row.get("finish_pos"))
            if number <= 0 or rank <= 0 or finish <= 0:
                continue
            dim = dimensions.get((key[0], key[1], number), {})
            rich = rich_horses.get((key[0], key[1], number), {})
            horses.append(
                {
                    "number": number,
                    "name": str(row.get("horse_name") or rich.get("horse_name") or ""),
                    "rank": rank,
                    "score": (
                        float(override["score"])
                        if override
                        else as_float(
                            row.get("reference_original_ability") or row.get("current_live_ability"),
                            60.0,
                        )
                    ),
                    "finish": finish,
                    "is_debut": as_bool(row.get("is_debut") or rich.get("is_debut")),
                    "is_import": as_bool(row.get("is_import") or rich.get("is_import")),
                    "is_foreign_runner": as_bool(
                        row.get("is_foreign_runner") or rich.get("is_foreign_runner")
                    ),
                    "dimensions": {
                        label: as_float(dim.get(score_column))
                        for label, (score_column, _reliability_column) in DIMENSION_COLUMNS.items()
                    },
                    "reliability": {
                        label: as_float(dim.get(reliability_column), 0.0)
                        for label, (_score_column, reliability_column) in DIMENSION_COLUMNS.items()
                    },
                    "uncertainty": as_float(dim.get("rebuild_uncertainty")),
                }
            )
        if len(horses) < 3:
            continue
        ranks = [horse["rank"] for horse in horses]
        positions = [horse["finish"] for horse in horses]
        if len(set(ranks)) != len(ranks) or not any(position == 1 for position in positions):
            continue
        context = rich_contexts.get(key, {})
        venue = str(first.get("venue") or "")
        track = str(first.get("track") or "")
        distance = as_int(first.get("distance_num") or first.get("distance"))
        races.append(
            {
                "meeting": key[0],
                "date": str(first.get("date") or key[0][:10]),
                "race_number": key[1],
                "dataset": str(first.get("dataset") or "archive"),
                "split": str(first.get("split") or first.get("dataset") or "archive"),
                "source_mode": str(first.get("source_mode") or "materialized_ranking_dataset"),
                "venue": venue,
                "track": track,
                "distance": distance,
                "race_class": context.get("race_class", ""),
                "is_straight_sprint": (
                    ("沙田" in venue or "shatin" in venue.lower())
                    and "turf" in track.lower()
                    and distance == 1000
                ),
                "has_debut_runner": any(horse["is_debut"] for horse in horses),
                "is_new_horse_race": bool(context.get("is_new_horse_race")),
                "has_foreign_runner": any(horse["is_foreign_runner"] for horse in horses),
                "foreign_label_available": any(
                    "is_foreign_runner" in row and str(row.get("is_foreign_runner") or "") != ""
                    for row in rows
                ),
                "horses": horses,
                "annotation": annotations.get(
                    key,
                    {"flags": [], "excluded_from_adjusted": False, "notes": ""},
                ),
            }
        )
    return races


def evaluate_race(race: dict[str, Any]) -> dict[str, Any]:
    ranked = sorted(race["horses"], key=lambda horse: (horse["rank"], horse["number"]))
    picks = [horse["number"] for horse in ranked]
    positions = {horse["number"]: horse["finish"] for horse in ranked}
    actual_top3 = [number for number, position in positions.items() if position <= 3]
    metrics = race_metrics(
        picks,
        actual_top3,
        actual_pos=positions,
        field_size=len(positions),
    )
    return {**race, "ranked": ranked, "actual_top3": actual_top3, "metrics": metrics}


def mean_dimension(horses: Iterable[dict[str, Any]], label: str) -> tuple[float | None, float]:
    values = []
    reliabilities = []
    for horse in horses:
        value = horse["dimensions"].get(label)
        if value is not None:
            values.append(value)
            reliabilities.append(horse["reliability"].get(label) or 0.0)
    return (mean(values) if values else None, mean(reliabilities) if reliabilities else 0.0)


def dimension_deltas(race: dict[str, Any]) -> list[dict[str, Any]]:
    top2 = race["ranked"][:2]
    actual = [horse for horse in race["ranked"] if horse["finish"] <= 3]
    deltas = []
    for label in DIMENSION_COLUMNS:
        model_mean, model_reliability = mean_dimension(top2, label)
        actual_mean, actual_reliability = mean_dimension(actual, label)
        if model_mean is None or actual_mean is None:
            continue
        deltas.append(
            {
                "dimension": label,
                "actual_minus_model_top2": round(actual_mean - model_mean, 3),
                "actual_mean": round(actual_mean, 3),
                "model_top2_mean": round(model_mean, 3),
                "actual_reliability": round(actual_reliability, 3),
                "model_top2_reliability": round(model_reliability, 3),
            }
        )
    return sorted(deltas, key=lambda row: row["actual_minus_model_top2"], reverse=True)


def classify_weak_race(race: dict[str, Any]) -> dict[str, Any]:
    metrics = race["metrics"]
    cutoff = metrics["competitive_cutoff"] or 3
    actual = sorted(
        (horse for horse in race["ranked"] if horse["finish"] <= 3),
        key=lambda horse: (horse["finish"], horse["number"]),
    )
    underrated = [horse for horse in actual if horse["rank"] > 2]
    severe_underrated = [horse for horse in actual if horse["rank"] > 5]
    overrated = [horse for horse in race["ranked"][:2] if horse["finish"] > cutoff]
    deltas = dimension_deltas(race)
    missed_signals = [
        row
        for row in deltas
        if row["actual_minus_model_top2"] >= 3.0 and row["actual_reliability"] >= 0.30
    ]
    actual_uncertainty = [
        horse["uncertainty"]
        for horse in actual
        if horse.get("uncertainty") is not None
    ]
    mean_uncertainty = mean(actual_uncertainty) if actual_uncertainty else None
    missed_debut = any(horse["is_debut"] and horse["rank"] > 5 for horse in actual)

    if race["annotation"]["excluded_from_adjusted"]:
        primary = "已標註異常賽果"
    elif missed_debut:
        primary = "初出馬備戰／不確定性轉化不足"
    elif race["is_straight_sprint"] and severe_underrated:
        primary = "直路賽專屬轉化不足"
    elif metrics["top3_all_within_top5"]:
        primary = "競爭層已捕捉但頭二排序不足"
    elif missed_signals:
        primary = f"{missed_signals[0]['dimension']}辨識不足"
    elif mean_uncertainty is not None and mean_uncertainty >= 0.65:
        primary = "資料稀薄／不確定性處理不足"
    else:
        primary = "整體競爭群辨識不足"

    if metrics["top2_hits"] == 0:
        what_wrong = "模型頭兩選全數落空"
    else:
        what_wrong = "模型頭兩選只捕捉一匹實際前三"
    if metrics["top3_all_within_top5"]:
        what_wrong += "，但實際前三仍全部位於模型前五"
    elif metrics["top3_capture_at5_count"]:
        what_wrong += f"，模型前五捕捉{metrics['top3_capture_at5_count']}匹實際前三"
    else:
        what_wrong += "，模型前五亦未捕捉任何實際前三"

    def horse_label(horse: dict[str, Any]) -> str:
        return f"#{horse['number']} {horse['name']}（模型{horse['rank']}／實際{horse['finish']}）"

    return {
        "meeting": race["meeting"],
        "date": race["date"],
        "race_number": race["race_number"],
        "dataset": race["dataset"],
        "split": race["split"],
        "venue": race["venue"],
        "distance": race["distance"],
        "field_size": len(race["ranked"]),
        "segments": [
            label
            for label, active in (
                ("沙田直路1000米", race["is_straight_sprint"]),
                ("有初出馬", race["has_debut_runner"]),
                ("新馬賽", race["is_new_horse_race"]),
                ("有外隊馬", race["has_foreign_runner"]),
            )
            if active
        ],
        "top2_hits": metrics["top2_hits"],
        "top3_hits": metrics["hits"],
        "top3_capture_at4": round(metrics["top3_capture_at4"], 4),
        "top3_capture_at5": round(metrics["top3_capture_at5"], 4),
        "top3_all_within_top5": metrics["top3_all_within_top5"],
        "winner_model_rank": metrics["winner_rank"],
        "ndcg_at5": round(metrics["ndcg_at5"], 4) if metrics["ndcg_at5"] is not None else None,
        "competitive_recall_at5": (
            round(metrics["competitive_recall_at5"], 4)
            if metrics["competitive_recall_at5"] is not None
            else None
        ),
        "what_model_got_wrong": what_wrong,
        "underrated_horses": [horse_label(horse) for horse in underrated],
        "severely_underrated_horses": [horse_label(horse) for horse in severe_underrated],
        "overrated_horses": [horse_label(horse) for horse in overrated],
        "missed_signals": [
            f"{row['dimension']} +{row['actual_minus_model_top2']:.2f}"
            for row in missed_signals
        ],
        "dimension_deltas": deltas,
        "mean_actual_top3_uncertainty": (
            round(mean_uncertainty, 4) if mean_uncertainty is not None else None
        ),
        "primary_cause": primary,
        "annotation_flags": race["annotation"]["flags"],
        "annotation_notes": race["annotation"]["notes"],
        "excluded_from_adjusted": race["annotation"]["excluded_from_adjusted"],
    }


def metric_summary(races: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [race["metrics"] for race in races]
    summary = summarize_races(rows)
    top2_distribution = Counter(row["top2_hits"] for row in rows)
    winner_ranks = [row["winner_rank"] for row in rows if row["winner_rank"] is not None]
    comp = summary["competitiveness"]
    return {
        "races": len(races),
        "top2_hit_distribution": {
            "0": top2_distribution[0],
            "1": top2_distribution[1],
            "2": top2_distribution[2],
        },
        "zero_or_one_rate": round(
            (top2_distribution[0] + top2_distribution[1]) / len(races), 4
        ) if races else None,
        "gold_good_pass_secondary": summary["exclusive_labels"],
        "top3_pick_precision": round(summary["top3_precision"], 4),
        "winner_top3_rate": round(summary["rates"]["winner_in_top3"], 4),
        "winner_top5_rate": round(summary["rates"]["winner_in_top5"], 4),
        "mean_winner_rank": round(mean(winner_ranks), 4) if winner_ranks else None,
        "mrr": round(summary["mrr"], 4),
        "top3_all_within_top4_rate": _rate(comp["top3_all_within_top4"]),
        "top3_all_within_top5_rate": _rate(comp["top3_all_within_top5"]),
        "mean_top3_capture_at4": _round(comp["mean_top3_capture_at4"]),
        "mean_top3_capture_at5": _round(comp["mean_top3_capture_at5"]),
        "mean_top3_model_rank": _round(comp["mean_top3_model_rank"]),
        "mean_top3_worst_model_rank": _round(comp["mean_top3_worst_model_rank"]),
        "mean_competitive_recall_at5": _round(comp["mean_competitive_recall_at5"]),
        "mean_competitive_precision_at5": _round(comp["mean_competitive_precision_at5"]),
        "mean_ndcg_at5": _round(comp["mean_ndcg_at5"]),
        "mean_model_top3_finish_percentile": _round(comp["mean_top3_pct"]),
    }


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _rate(payload: dict[str, Any]) -> float | None:
    return _round(payload.get("rate"))


def group_summaries(races: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for race in races:
        groups[f"dataset:{race['dataset']}"].append(race)
        groups[f"split:{race['split']}"].append(race)
        groups[f"venue:{race['venue']}"].append(race)
        if race["is_straight_sprint"]:
            groups["segment:沙田直路1000米"].append(race)
        if race["has_debut_runner"]:
            groups["segment:有初出馬"].append(race)
        if race["is_new_horse_race"]:
            groups["segment:新馬賽"].append(race)
        if race["has_foreign_runner"]:
            groups["segment:有外隊馬"].append(race)
    return {
        key: {
            **metric_summary(members),
            "sample_flag": "stable" if len(members) >= 30 else "small",
        }
        for key, members in sorted(groups.items())
    }


def add_systematic_assessment(cases: list[dict[str, Any]]) -> None:
    cause_meetings: defaultdict[str, set[str]] = defaultdict(set)
    cause_counts = Counter()
    for case in cases:
        cause_counts[case["primary_cause"]] += 1
        cause_meetings[case["primary_cause"]].add(case["meeting"])
    for case in cases:
        cause = case["primary_cause"]
        systematic = cause_counts[cause] >= 8 and len(cause_meetings[cause]) >= 3
        case["systematic_or_race_specific"] = "系統性" if systematic else "場次特定／樣本不足"
        if case["excluded_from_adjusted"]:
            recommendation = "保留作異常案例研究；唔以此場直接改模型"
        elif systematic:
            recommendation = "建立賽前訊號候選並做 temporal holdout；未通過前唔改主線"
        else:
            recommendation = "暫不改模型；單場修正過擬合風險高"
        case["model_change_assessment"] = recommendation


def render_report(payload: dict[str, Any]) -> str:
    baseline = payload["baseline_unfiltered"]
    adjusted = payload["baseline_adjusted"]
    lines = [
        "# HKJC 競爭力排序 Archive Review",
        "",
        "## 結論",
        "",
        "- Gold / Good / Pass 保留作輔助標籤；主評估改用 Top3@4/5、winner rank、NDCG@5、competitive-tier recall。",
        f"- 全樣本 {baseline['races']} 場；0/1-hit {baseline['zero_or_one_rate']:.1%}。",
        f"- 模型前四平均捕捉實際前三 {baseline['mean_top3_capture_at4']:.1%}；前五 {baseline['mean_top3_capture_at5']:.1%}。",
        f"- 實際前三全在模型前五：{baseline['top3_all_within_top5_rate']:.1%}；winner@5：{baseline['winner_top5_rate']:.1%}。",
        f"- NDCG@5：{baseline['mean_ndcg_at5']:.3f}；competitive-tier recall@5：{baseline['mean_competitive_recall_at5']:.1%}。",
        "",
        "## 異常結果處理",
        "",
        f"- 有可審核異常標註並從 adjusted 層排除：{payload['coverage']['adjusted_exclusions']} 場。",
        "- unfiltered baseline 永遠保留；無 incident／極冷門標註嘅賽事唔會自動排除。",
    ]
    if adjusted["races"] != baseline["races"]:
        lines.append(
            f"- Adjusted {adjusted['races']} 場：Top3@5 {adjusted['mean_top3_capture_at5']:.1%}，NDCG@5 {adjusted['mean_ndcg_at5']:.3f}。"
        )
    lines.extend(["", "## 0/1-hit 主因", "", "| 主因 | 場數 | 比例 |", "|---|---:|---:|"])
    weak_total = max(1, len(payload["weak_races"]))
    for cause, count in payload["weak_cause_counts"].items():
        lines.append(f"| {cause} | {count} | {count / weak_total:.1%} |")
    lines.extend(["", "## 專項", "", "| Cohort | 場數 | 樣本 | Top3@5 | 全部前三@5 | NDCG@5 | 0/1-hit |", "|---|---:|---|---:|---:|---:|---:|"])
    for key in ("segment:沙田直路1000米", "segment:有初出馬", "segment:新馬賽", "segment:有外隊馬"):
        row = payload["cohorts"].get(key)
        if row:
            lines.append(
                f"| {key.split(':', 1)[1]} | {row['races']} | {row['sample_flag']} | "
                f"{row['mean_top3_capture_at5']:.1%} | {row['top3_all_within_top5_rate']:.1%} | "
                f"{row['mean_ndcg_at5']:.3f} | {row['zero_or_one_rate']:.1%} |"
            )
        else:
            lines.append(f"| {key.split(':', 1)[1]} | 0 | unavailable | — | — | — | — |")
    lines.extend(
        [
            "",
            "## Data limitations",
            "",
            f"- 外隊馬標籤可用場次：{payload['coverage']['foreign_labelled_races']}；未有可驗證 archive sample，現階段只可做 pipeline／synthetic contract test，唔可宣稱實證已優化。",
            f"- 真正新馬賽（race-class 標籤）只有 {payload['coverage']['new_horse_races']} 場；「有初出馬」另有 {payload['coverage']['debut_runner_races']} 場，兩者不可混為一談。",
            "- 245 場 replay 分為 archived snapshot 與 current reconstructed primitives；cohort 報告保留 source split。",
            "",
            "## Files",
            "",
            f"- Structured weak-race CSV: `{payload['outputs']['csv']}`",
            f"- Full JSON: `{payload['outputs']['json']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def write_weak_csv(path: Path, cases: list[dict[str, Any]]) -> None:
    columns = [
        "meeting", "date", "race_number", "dataset", "split", "venue", "distance",
        "field_size", "segments", "top2_hits", "top3_hits", "top3_capture_at4",
        "top3_capture_at5", "top3_all_within_top5", "winner_model_rank", "ndcg_at5",
        "competitive_recall_at5", "what_model_got_wrong", "underrated_horses",
        "severely_underrated_horses", "overrated_horses", "missed_signals",
        "primary_cause", "systematic_or_race_specific", "model_change_assessment",
        "mean_actual_top3_uncertainty", "annotation_flags", "annotation_notes",
        "excluded_from_adjusted",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for case in cases:
            row = {column: case.get(column) for column in columns}
            for column in (
                "segments", "underrated_horses", "severely_underrated_horses",
                "overrated_horses", "missed_signals", "annotation_flags",
            ):
                row[column] = " | ".join(row[column] or [])
            writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--dimensions", type=Path, default=DEFAULT_DIMENSIONS)
    parser.add_argument("--rich-dataset", type=Path, default=DEFAULT_RICH_DATASET)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument(
        "--rank-override",
        type=Path,
        action="append",
        default=[],
        help="Rich matrix CSV; repeat to recompute ranks with live production weights",
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    races = [
        evaluate_race(race)
        for race in normalise_races(
            args.dataset,
            dimension_path=args.dimensions,
            rich_path=args.rich_dataset,
            annotation_path=args.annotations,
            rank_override_paths=args.rank_override,
        )
    ]
    weak = [classify_weak_race(race) for race in races if race["metrics"]["top2_hits"] <= 1]
    add_systematic_assessment(weak)
    adjusted = [race for race in races if not race["annotation"]["excluded_from_adjusted"]]
    cause_counts = Counter(case["primary_cause"] for case in weak)
    foreign_labelled = sum(race["foreign_label_available"] for race in races)
    payload = {
        "method": {
            "primary_metrics": [
                "Top3 capture @4/@5",
                "winner rank / MRR / winner@5",
                "actual Top3 mean and worst model rank",
                "NDCG@5",
                "observed competitive-tier recall/precision @5",
            ],
            "competitive_tier": "leading third of field, minimum 3 and maximum 5",
            "gold_good_pass_role": "secondary descriptive labels only",
            "weak_race_definition": "model Top 2 contains zero or one actual Top 3 finisher",
            "dimension_evidence": "outcome-free rebuilt common primitives; diagnostic, not production score",
            "odds_policy": "never used in scoring; only permitted in explicit external anomaly annotations",
            "adjusted_policy": "unfiltered always reported; adjusted excludes only explicit annotation flags",
            "ranking_source": (
                "live production matrix weights recomputed from rank override files"
                if args.rank_override
                else "published/materialized reference ranking"
            ),
        },
        "coverage": {
            "races": len(races),
            "meetings": len({race["meeting"] for race in races}),
            "date_range": [
                min((race["date"] for race in races), default=""),
                max((race["date"] for race in races), default=""),
            ],
            "weak_races": len(weak),
            "adjusted_exclusions": len(races) - len(adjusted),
            "straight_sprint_races": sum(race["is_straight_sprint"] for race in races),
            "debut_runner_races": sum(race["has_debut_runner"] for race in races),
            "new_horse_races": sum(race["is_new_horse_race"] for race in races),
            "foreign_runner_races": sum(race["has_foreign_runner"] for race in races),
            "foreign_labelled_races": foreign_labelled,
        },
        "baseline_unfiltered": metric_summary(races),
        "baseline_adjusted": metric_summary(adjusted),
        "cohorts": group_summaries(races),
        "weak_cause_counts": dict(cause_counts.most_common()),
        "weak_races": weak,
        "data_gaps": [
            *(
                [
                    "No complete incident/interference/injury/extreme-outsider annotations supplied."
                ]
                if args.annotations is None
                else [
                    "Conservative anomaly annotations supplied; unflagged minor racing incidents remain in adjusted results."
                ]
            ),
            "Foreign-runner archive label absent from the current materialized replay.",
            "True new-horse race class is only available where the richer archive context joins.",
            "Historical archive snapshots cannot be faithfully rescored by the current engine.",
        ],
        "outputs": {
            "json": str(args.json_output),
            "csv": str(args.csv_output),
            "report": str(args.report_output),
        },
    }
    for path in (args.json_output, args.csv_output, args.report_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    write_weak_csv(args.csv_output, weak)
    args.json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.report_output.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps(payload["coverage"], ensure_ascii=False))
    print(f"report={args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
