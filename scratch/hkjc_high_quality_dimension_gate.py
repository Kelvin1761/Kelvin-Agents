#!/usr/bin/env python3
"""Gate structured HKJC sectional/rating/class/form-line features.

All source features come from frozen pre-race Facts snapshots. Candidates
rebuild a matrix dimension before the production 7D outer weights; there are
no swaps, tie-break rules, odds, or post-race inputs.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ENGINE = (
    ROOT / ".agents" / "skills" / "hkjc_racing"
    / "hkjc_wong_choi_auto" / "scripts" / "racing_engine"
)
SHARED = ROOT / ".agents" / "skills" / "shared_racing"
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(SHARED))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402


ARCHIVE = ROOT / "scratch" / "hkjc_ranking_dataset_current.csv"
EXTERNAL = ROOT / "scratch" / "hkjc_ranking_dataset_2026_07_15_current.csv"
ARCHIVE_FEATURES = ROOT / "scratch" / "hkjc_archive_high_quality_features.json"
EXTERNAL_FEATURES = ROOT / "scratch" / "hkjc_0715_normalized_features.json"
EXTERNAL_RATINGS = ROOT / "scratch" / "hkjc_0715_rating_history.json"
EXTERNAL_CURRENT_RATINGS = ROOT / "scratch" / "hkjc_0715_current_ratings.json"
ANNOTATIONS = ROOT / "scratch" / "hkjc_anomaly_annotations.csv"
JSON_OUT = ROOT / "scratch" / "hkjc_high_quality_dimension_gate.json"
REPORT_OUT = ROOT / "scratch" / "hkjc_high_quality_dimension_gate_report.md"


def feature_rows(path: Path, external: bool = False) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    if external:
        meetings = {payload["meeting"]: payload["races"]}
    else:
        meetings = payload["races"]
    for meeting, races in meetings.items():
        for race, horses in races.items():
            for horse, values in horses.items():
                rows.append({
                    "meeting_name": meeting,
                    "race_number": int(race),
                    "horse_number": int(horse),
                    **values,
                })
    return pd.DataFrame(rows)


def class_rank(value: object) -> float | None:
    text = str(value or "").strip()
    direct = {
        "一級賽": 1, "二級賽": 2, "三級賽": 3,
        "第一班": 10, "第二班": 11, "第三班": 12,
        "第四班": 13, "第五班": 14,
    }
    if text in direct:
        return float(direct[text])
    group = re.search(r"(?:GROUP|GRADE|G)\s*([123])", text, re.I)
    if group:
        return float(group.group(1))
    cls = re.search(r"(?:CLASS|C)\s*([1-5])", text, re.I)
    if cls:
        return 9.0 + float(cls.group(1))
    if re.fullmatch(r"[1-5]", text):
        return 9.0 + float(text)
    return None


def prepare() -> pd.DataFrame:
    archive = pd.read_csv(ARCHIVE)
    archive["dataset"] = "archive"
    external = pd.read_csv(EXTERNAL)
    external["dataset"] = "external"
    data = pd.concat([archive, external], ignore_index=True)
    features = pd.concat([
        feature_rows(ARCHIVE_FEATURES),
        feature_rows(EXTERNAL_FEATURES, external=True),
    ], ignore_index=True)
    data = data.merge(
        features,
        on=["meeting_name", "race_number", "horse_number"],
        how="left",
        suffixes=("", "_hq"),
        validate="one_to_one",
    )
    external_ratings = json.loads(
        EXTERNAL_RATINGS.read_text(encoding="utf-8")
    )["ratings"]
    external_current_ratings = json.loads(
        EXTERNAL_CURRENT_RATINGS.read_text(encoding="utf-8")
    )["ratings"]
    external_mask = data["dataset"].eq("external")
    data.loc[external_mask, "rating_series"] = data.loc[external_mask].apply(
        lambda row: external_ratings.get(
            f"{int(row['race_number'])}-{int(row['horse_number'])}",
            [],
        ),
        axis=1,
    )
    data.loc[external_mask, "card_rating"] = data.loc[external_mask].apply(
        lambda row: external_current_ratings.get(
            f"{int(row['race_number'])}-{int(row['horse_number'])}",
            math.nan,
        ),
        axis=1,
    )

    def rating_list(value: object) -> list[float]:
        return [float(item) for item in value] if isinstance(value, list) else []

    data["rating_series"] = data["rating_series"].apply(rating_list)
    data["rating_delta_recent_hq"] = data["rating_series"].apply(
        lambda values: values[0] - values[-1] if len(values) >= 2 else math.nan
    )
    data["rating_peak_gap"] = data.apply(
        lambda row: (
            float(row["card_rating"]) - max(row["rating_series"])
            if row["rating_series"] and not pd.isna(row["card_rating"])
            else math.nan
        ),
        axis=1,
    )
    data["class_move"] = data.apply(
        lambda row: (
            class_rank(row["race_class"]) - class_rank(row["class_history"][0])
            if isinstance(row["class_history"], list) and row["class_history"]
            and class_rank(row["race_class"]) is not None
            and class_rank(row["class_history"][0]) is not None
            else math.nan
        ),
        axis=1,
    )
    label_map = {
        "極強": 2.0, "超強": 2.0, "強": 1.0,
        "中強": 0.4, "中弱": -0.4, "弱": -1.0,
    }
    data["formline_structured"] = data["formline_label"].fillna("").map(
        lambda text: next((value for key, value in label_map.items() if key in str(text)), math.nan)
    )
    required = [
        "dataset", "meeting_name", "date", "race_number", "horse_number",
        "horse_name", "finish_pos", "race_class",
        "sectional_normalized_l400_delta", "sectional_normalized_total_delta",
        "sectional_normalized_samples", "rating_series",
        "rating_delta_recent_hq", "rating_peak_gap", "class_history", "class_move",
        "formline_structured", "prior_jockey_cd_place_edge",
        "prior_jockey_cd_starts",
        *(f"matrix_{name}" for name in MATRIX_WEIGHTS),
    ]
    return data[required].copy()


def relative(
    rows: pd.DataFrame,
    column: str,
    higher_is_better: bool,
) -> dict[int, float | None]:
    values = {
        int(row.horse_number): float(getattr(row, column))
        for row in rows.itertuples()
        if not pd.isna(getattr(row, column))
    }
    output: dict[int, float | None] = {}
    for row in rows.itertuples():
        horse = int(row.horse_number)
        if horse not in values:
            output[horse] = None
            continue
        if len(values) < 2:
            output[horse] = 60.0
            continue
        value = values[horse]
        others = [item for other_horse, item in values.items() if other_horse != horse]
        worse = sum(item < value for item in others) if higher_is_better else sum(
            item > value for item in others
        )
        ties = sum(item == value for item in others)
        output[horse] = 45.0 + 30.0 * (worse + 0.5 * ties) / len(others)
    return output


def signal_score(rows: pd.DataFrame, signal: str) -> dict[int, float | None]:
    configs = {
        "sectional_l400": ("sectional_normalized_l400_delta", False),
        "sectional_total": ("sectional_normalized_total_delta", False),
        "rating_rising": ("rating_delta_recent_hq", True),
        "rating_falling": ("rating_delta_recent_hq", False),
        "rating_near_peak": ("rating_peak_gap", True),
        "rating_well_handicapped": ("rating_peak_gap", False),
        "class_drop": ("class_move", True),
        "formline_structured": ("formline_structured", True),
        "jockey_distance": ("prior_jockey_cd_place_edge", True),
    }
    if signal == "sectional_combo":
        left = signal_score(rows, "sectional_l400")
        right = signal_score(rows, "sectional_total")
        output: dict[int, float | None] = {}
        for horse in left:
            available = [
                (left[horse], 0.6),
                (right[horse], 0.4),
            ]
            available = [
                (value, weight) for value, weight in available if value is not None
            ]
            if not available:
                output[horse] = None
                continue
            total_weight = sum(weight for _, weight in available)
            output[horse] = sum(
                float(value) * weight for value, weight in available
            ) / total_weight
        return output
    column, higher = configs[signal]
    raw = relative(rows, column, higher)
    output: dict[int, float | None] = {}
    for row in rows.itertuples():
        horse = int(row.horse_number)
        if signal.startswith("sectional_"):
            samples = float(row.sectional_normalized_samples or 0.0)
            reliability = samples / (samples + 2.0)
        elif signal.startswith("rating_"):
            samples = len(row.rating_series)
            reliability = samples / (samples + 2.0)
        elif signal == "class_drop":
            reliability = 1.0 if not pd.isna(row.class_move) else 0.0
        elif signal == "formline_structured":
            reliability = 0.75 if not pd.isna(row.formline_structured) else 0.0
        else:
            starts = float(row.prior_jockey_cd_starts or 0.0)
            reliability = starts / (starts + 80.0)
        raw_score = raw[horse]
        output[horse] = (
            None
            if raw_score is None or reliability <= 0.0
            else 60.0 + reliability * (raw_score - 60.0)
        )
    return output


def score_race(rows: pd.DataFrame, spec: list[tuple[str, str, float]]) -> list[dict]:
    signals = {signal: signal_score(rows, signal) for _, signal, _ in spec}
    ranked = []
    for record in rows.to_dict("records"):
        matrices = {
            name: float(record.get(f"matrix_{name}", 60.0) or 60.0)
            for name in MATRIX_WEIGHTS
        }
        horse = int(record["horse_number"])
        for dimension, signal, alpha in spec:
            evidence = signals[signal][horse]
            if evidence is None:
                continue
            matrices[dimension] = (
                (1.0 - alpha) * matrices[dimension] + alpha * evidence
            )
        ability = sum(matrices[name] * weight for name, weight in MATRIX_WEIGHTS.items())
        ranked.append({**record, "_ability": ability})
    return sorted(ranked, key=lambda row: (-row["_ability"], int(row["horse_number"])))


def evaluate(groups: list[pd.DataFrame], spec: list[tuple[str, str, float]]) -> tuple[dict, dict]:
    race_metrics_rows, details = [], {}
    for rows in groups:
        ranked = score_race(rows, spec)
        picks = [int(row["horse_number"]) for row in ranked]
        positions = {int(row["horse_number"]): int(row["finish_pos"]) for row in ranked}
        actual = [horse for horse, position in positions.items() if position <= 3]
        metric = race_metrics(picks, actual, actual_pos=positions, field_size=len(rows))
        race_metrics_rows.append(metric)
        key = (ranked[0]["meeting_name"], int(ranked[0]["race_number"]))
        details[key] = {
            "top2_hits": metric["top2_hits"],
            "top5_capture": metric["top3_capture_at5"],
            "top2": picks[:2],
            "rank3": picks[2] if len(picks) >= 3 else None,
            "actual": actual,
        }
    summary = summarize_races(race_metrics_rows)
    distribution = Counter(row["top2_hits"] for row in race_metrics_rows)
    comp = summary["competitiveness"]
    return {
        "races": len(race_metrics_rows),
        "zero_hit": distribution[0],
        "one_hit": distribution[1],
        "two_hit": distribution[2],
        "top2_total_hits": sum(row["top2_hits"] for row in race_metrics_rows),
        "top3_capture_at5": comp["mean_top3_capture_at5"],
        "top3_all_within_top5": comp["top3_all_within_top5"]["rate"],
        "competitive_recall_at5": comp["mean_competitive_recall_at5"],
        "ndcg_at5": comp["mean_ndcg_at5"],
        "winner_in_top5": summary["rates"]["winner_in_top5"],
        "mrr": summary["mrr"],
    }, details


def delta(candidate: dict, baseline: dict) -> dict:
    return {key: candidate[key] - baseline[key] for key in candidate if key != "races"}


def specs() -> dict[str, list[tuple[str, str, float]]]:
    output = {"baseline": []}
    dimension = {
        "sectional_l400": "sectional",
        "sectional_total": "sectional",
        "sectional_combo": "sectional",
        "rating_rising": "class_advantage",
        "rating_falling": "class_advantage",
        "rating_near_peak": "class_advantage",
        "rating_well_handicapped": "class_advantage",
        "class_drop": "class_advantage",
        "formline_structured": "form_line",
        "jockey_distance": "trainer_signal",
    }
    for signal, target in dimension.items():
        for alpha in (0.05, 0.10, 0.15, 0.20):
            output[f"{signal}_{alpha:.2f}"] = [(target, signal, alpha)]
    for alpha in (0.05, 0.10, 0.15):
        output[f"sectional_formline_{alpha:.2f}"] = [
            ("sectional", "sectional_l400", alpha),
            ("form_line", "formline_structured", alpha),
        ]
        output[f"sectional_classdrop_{alpha:.2f}"] = [
            ("sectional", "sectional_l400", alpha),
            ("class_advantage", "class_drop", alpha),
        ]
    output["hq_rating_sectional"] = [
        ("class_advantage", "rating_near_peak", 0.15),
        ("sectional", "sectional_combo", 0.05),
    ]
    output["hq_conservative_rating_sectional"] = [
        ("class_advantage", "rating_near_peak", 0.05),
        ("sectional", "sectional_combo", 0.05),
    ]
    output["hq_rating_jockey"] = [
        ("class_advantage", "rating_near_peak", 0.15),
        ("trainer_signal", "jockey_distance", 0.05),
    ]
    output["hq_rating_sectional_jockey"] = [
        ("class_advantage", "rating_near_peak", 0.15),
        ("sectional", "sectional_combo", 0.05),
        ("trainer_signal", "jockey_distance", 0.05),
    ]
    return output


def main() -> int:
    data = prepare()
    archive = data[data["dataset"].eq("archive")].copy()
    external = data[data["dataset"].eq("external")].copy()
    dates = sorted(archive["date"].astype(str).unique())
    cut = max(1, math.floor(len(dates) * 0.70))
    annotations = pd.read_csv(ANNOTATIONS, encoding="utf-8-sig")
    abnormal = {
        (row.meeting, int(row.race_number))
        for row in annotations.itertuples()
        if any(bool(getattr(row, flag)) for flag in (
            "extreme_outsider", "major_incident", "interference", "injury", "abnormal"
        ))
    }

    def groups(frame: pd.DataFrame) -> list[pd.DataFrame]:
        return [
            rows.copy()
            for _, rows in frame.groupby(["meeting_name", "race_number"], sort=True)
        ]

    split_frames = {
        "development": archive[archive["date"].astype(str).isin(dates[:cut])],
        "temporal_holdout": archive[archive["date"].astype(str).isin(dates[cut:])],
        "all": archive,
        "all_adjusted": archive[
            ~archive.apply(lambda row: (row["meeting_name"], int(row["race_number"])) in abnormal, axis=1)
        ],
        "external": external,
    }
    split_groups = {name: groups(frame) for name, frame in split_frames.items()}
    baseline, baseline_details = {}, {}
    for split, race_groups in split_groups.items():
        baseline[split], baseline_details[split] = evaluate(race_groups, [])
    weak_keys = {
        key for key, item in baseline_details["all"].items() if item["top2_hits"] <= 1
    }
    split_groups["weak_zero_one"] = [
        rows for rows in split_groups["all"]
        if (rows.iloc[0]["meeting_name"], int(rows.iloc[0]["race_number"])) in weak_keys
    ]
    baseline["weak_zero_one"], baseline_details["weak_zero_one"] = evaluate(
        split_groups["weak_zero_one"], []
    )

    results = {}
    for name, spec in specs().items():
        if name == "baseline":
            continue
        result = {}
        candidate_details = {}
        for split, race_groups in split_groups.items():
            metrics, details = evaluate(race_groups, spec)
            result[split] = {
                "candidate": metrics,
                "delta": delta(metrics, baseline[split]),
            }
            candidate_details[split] = details
        helped = harmed = rescues = 0
        for key, before in baseline_details["all"].items():
            after = candidate_details["all"][key]
            helped += after["top2_hits"] > before["top2_hits"]
            harmed += after["top2_hits"] < before["top2_hits"]
            rescues += (
                before["rank3"] in before["actual"]
                and before["rank3"] in after["top2"]
            )
        result["comparison"] = {"helped": helped, "harmed": harmed, "rank3_rescues": rescues}
        results[name] = result

    ranked = sorted(
        results,
        key=lambda name: (
            -results[name]["temporal_holdout"]["delta"]["top2_total_hits"],
            -results[name]["all_adjusted"]["delta"]["ndcg_at5"],
            -results[name]["all"]["delta"]["ndcg_at5"],
        ),
    )
    payload = {
        "coverage": {
            "archive_meetings": int(archive["meeting_name"].nunique()),
            "archive_races": int(archive.groupby(["meeting_name", "race_number"]).ngroups),
            "archive_runners": int(len(archive)),
            "sectional_runners": int(archive["sectional_normalized_samples"].fillna(0).gt(0).sum()),
            "rating_runners": int(archive["rating_series"].map(bool).sum()),
            "class_runners": int(archive["class_history"].map(lambda x: isinstance(x, list) and bool(x)).sum()),
            "external_races": int(external["race_number"].nunique()),
            "weak_zero_one_races": len(weak_keys),
        },
        "baseline": baseline,
        "results": results,
        "ranked_candidates": ranked,
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# HKJC High-Quality Dimension Gate",
        "",
        f"- Coverage: {payload['coverage']}",
        "- Frozen pre-race facts only; full-field rerank; no blind swap or micro tie-break.",
        "",
        "| candidate | all 0hit Δ | all top2 Δ | all cap@5 Δ | all NDCG Δ | adjusted NDCG Δ | holdout top2 Δ | holdout NDCG Δ | weak top2 Δ | external top2 Δ | help/harm | R3 rescues |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ranked:
        row = results[name]
        all_delta = row["all"]["delta"]
        adj = row["all_adjusted"]["delta"]
        hold = row["temporal_holdout"]["delta"]
        weak = row["weak_zero_one"]["delta"]
        ext = row["external"]["delta"]
        comp = row["comparison"]
        lines.append(
            f"| {name} | {all_delta['zero_hit']:+.0f} | {all_delta['top2_total_hits']:+.0f} | "
            f"{all_delta['top3_capture_at5']:+.4f} | {all_delta['ndcg_at5']:+.4f} | "
            f"{adj['ndcg_at5']:+.4f} | {hold['top2_total_hits']:+.0f} | "
            f"{hold['ndcg_at5']:+.4f} | {weak['top2_total_hits']:+.0f} | "
            f"{ext['top2_total_hits']:+.0f} | {comp['helped']}/{comp['harmed']} | "
            f"{comp['rank3_rescues']} |"
        )
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
