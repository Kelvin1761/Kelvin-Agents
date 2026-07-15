#!/usr/bin/env python3
"""Leakage-safe shadow backtest for official trial runner data.

No parameters are fitted from race outcomes.  Official trial records are only
used where their trial date is strictly earlier than the meeting being scored.
The script compares fixed, deliberately small replacements/overlays against the
current engine, then reports development and chronological holdout separately.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.extend([str(SCRIPT_DIR), str(SCRIPT_DIR / "racing_engine")])

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)
from au_official_trial_feature_enrich import build_features, load_records, normalise_name  # noqa: E402
from engine_core import RacingEngine  # noqa: E402
from matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402


OUTPUT_PATH = ARCHIVE_ROOT / "AU_Official_Trial_Shadow_Backtest.md"


def field_summary(horses: dict[str, dict]) -> dict[str, Any]:
    weights = []
    ratings = []
    for horse in horses.values():
        try:
            weights.append(float(horse.get("weight")))
        except (TypeError, ValueError):
            pass
        try:
            ratings.append(float(horse.get("rating")))
        except (TypeError, ValueError):
            pass
    return {
        "count": len(horses),
        "min_weight": min(weights) if weights else 0.0,
        "max_weight": max(weights) if weights else 0.0,
        "avg_weight": mean(weights) if weights else 0.0,
        "rated_count": len(ratings),
        "min_rating": min(ratings) if ratings else 0.0,
        "max_rating": max(ratings) if ratings else 0.0,
        "avg_rating": mean(ratings) if ratings else 0.0,
        "rating_stdev": pstdev(ratings) if len(ratings) > 1 else 0.0,
        "l600_delta_field_count": 0,
        "l600_delta_field_mean": 0.0,
        "l600_delta_field_stdev": 0.0,
    }


def rank_score(features: dict[str, float]) -> float:
    matrix = map_features_to_matrix_scores(features)
    return sum(float(matrix.get(name, 60.0)) * weight for name, weight in MATRIX_WEIGHTS.items())


def official_trial_score(features: dict[str, Any]) -> float | None:
    if not features or not features.get("official_trial_runner_match_count"):
        return None
    top3 = min(3, int(features.get("official_trial_top3_count") or 0))
    score = 56.0 + top3 * 9.0
    latest_finish = features.get("official_trial_latest_finish")
    if latest_finish == 1:
        score += 4.0
    elif latest_finish and latest_finish <= 3:
        score += 2.0
    return clip_score(score)


def metrics(races: list[dict], variant: str) -> dict[str, float | int]:
    winners = hits = 0
    for race in races:
        ranked = sorted(race["horses"], key=lambda row: (-row["scores"][variant], row["horse_number"]))
        winners += int(ranked[0]["actual_pos"] == 1)
        hits += sum(1 for row in ranked[:3] if row["actual_pos"] <= 3)
    count = len(races)
    return {
        "races": count,
        "winner_rate": round(winners / count * 100, 2) if count else 0.0,
        "top3_precision": round(hits / (count * 3) * 100, 2) if count else 0.0,
        "winner_count": winners,
        "top3_hits": hits,
    }


def load_races() -> list[dict]:
    records = load_records()
    historical = load_historical_results(HISTORICAL_RESULTS_CSV)
    races: list[dict] = []
    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir() and path.name != "Official_Free_Data"):
        date = detect_meeting_date(meeting_dir)
        if not date:
            continue
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        first = json.loads(logic_files[0].read_text(encoding="utf-8"))
        track = detect_meeting_track(meeting_dir, first)
        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_no = parse_int((logic.get("race_analysis") or {}).get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            result_rows = choose_track_rows(historical.get((date, race_no), []), track)
            if not result_rows:
                continue
            lookup = {row["horse_slug"]: row for row in result_rows}
            context = dict(logic.get("race_analysis") or {})
            context["field_summary"] = field_summary(logic.get("horses") or {})
            horses = []
            for horse_number, horse in (logic.get("horses") or {}).items():
                actual = lookup.get(normalize_horse_name(horse.get("horse_name") or ""))
                if not actual:
                    continue
                feature = build_features(
                    records.get((meeting_dir.name, logic_path.stem, normalise_name(horse.get("horse_name") or "")), []),
                    str(horse.get("jockey") or ""),
                    date,
                )
                if not feature:
                    continue
                auto = RacingEngine(horse, context, str((horse.get("_data") or {}).get("facts_section") or "")).analyze_horse()
                feature_scores = dict(auto.get("feature_scores") or {})
                baseline = rank_score(feature_scores)
                replacement = official_trial_score(feature)
                career_starts = parse_int(horse.get("career_race_starts"), 99)
                # Heat L600 is an event context, never a runner sectional.  A
                # field-relative z-score therefore receives only a tiny fixed
                # contribution and is tested separately.
                horses.append({
                    "horse_number": parse_int(horse_number, 999),
                    "actual_pos": int(actual["pos"]),
                    "features": feature,
                    "base_features": feature_scores,
                    "baseline": baseline,
                    "official_replacement": replacement,
                    "current_trial_jockey_rides": int((horse.get("_data") or {}).get("current_jockey_trial_rides") or 0),
                    "is_debut": career_starts == 0,
                })
            if len(horses) < 4 or sum(1 for row in horses if row["actual_pos"] <= 3) < 3:
                continue
            l600 = [row["features"].get("official_trial_l600_speed_avg") for row in horses]
            l600 = [float(value) for value in l600 if value is not None]
            l600_mean, l600_sd = (mean(l600), pstdev(l600)) if len(l600) >= 3 else (0.0, 0.0)
            for row in horses:
                base = dict(row["base_features"])
                replacement = row["official_replacement"]
                row["scores"] = {"baseline": row["baseline"]}
                time_delta = 0.0
                speed = row["features"].get("official_trial_l600_speed_avg")
                if speed is not None and l600_sd > 0:
                    time_delta = max(-3.0, min(3.0, (float(speed) - l600_mean) / l600_sd * 1.5))
                jockey_delta = 2.0 if (
                    row["features"].get("official_trial_jockey_match_count")
                    and not row["current_trial_jockey_rides"]
                ) else 0.0
                heat_only = dict(base)
                heat_only["trial_score"] = clip_score(heat_only.get("trial_score", 60.0) + time_delta)
                row["scores"]["official_heat_time_only"] = rank_score(heat_only)
                jockey_only = dict(base)
                jockey_only["jockey_horse_fit_score"] = clip_score(jockey_only.get("jockey_horse_fit_score", 60.0) + jockey_delta)
                row["scores"]["official_jockey_match_only"] = rank_score(jockey_only)
                debut_jockey = dict(base)
                debut_delta = jockey_delta if row["is_debut"] else 0.0
                debut_jockey["jockey_horse_fit_score"] = clip_score(debut_jockey.get("jockey_horse_fit_score", 60.0) + debut_delta)
                row["scores"]["official_debut_jockey_only"] = rank_score(debut_jockey)
                if replacement is not None:
                    place_features = dict(base)
                    place_features["trial_score"] = replacement
                    row["scores"]["official_place_replace"] = rank_score(place_features)
                    time_features = dict(place_features)
                    # Fixed ±3 point max in the *trial feature*, not fit to results.
                    time_features["trial_score"] = clip_score(replacement + time_delta)
                    row["scores"]["official_place_plus_heat_time"] = rank_score(time_features)
                    jockey_features = dict(place_features)
                    jockey_features["jockey_horse_fit_score"] = clip_score(jockey_features.get("jockey_horse_fit_score", 60.0) + jockey_delta)
                    row["scores"]["official_place_plus_jockey"] = rank_score(jockey_features)
                    combo_features = dict(jockey_features)
                    combo_features["trial_score"] = clip_score(replacement + time_delta)
                    row["scores"]["official_place_time_jockey"] = rank_score(combo_features)
                else:
                    for variant in ("official_place_replace", "official_place_plus_heat_time", "official_place_plus_jockey", "official_place_time_jockey"):
                        row["scores"][variant] = row["baseline"]
            races.append({"date": date, "meeting": meeting_dir.name, "race": race_no, "horses": horses})
    return races


def render_report(races: list[dict]) -> str:
    variants = ("baseline", "official_place_replace", "official_heat_time_only", "official_jockey_match_only", "official_debut_jockey_only", "official_place_plus_heat_time", "official_place_plus_jockey", "official_place_time_jockey")
    split = max(1, math.floor(len(races) * 0.7))
    sets = {"全樣本（只作描述）": races, "開發窗（較早 70%）": races[:split], "時間 holdout（較後 30%）": races[split:]}
    lines = ["# AU 官方試閘資料 Shadow 回測", "", "- 僅使用試閘日期早於該場賽事的官方紀錄。", "- 總時間／L600 是 heat-level context，不視為逐馬 sectional。", "- 所有候選為固定規則；未使用賽果調參。", ""]
    for label, subset in sets.items():
        base = metrics(subset, "baseline")
        lines.extend([f"## {label}", "", "| 變體 | 場數 | 頭馬命中率 | Top-3 命中率 | 相對 baseline |", "|---|---:|---:|---:|---:|"])
        for variant in variants:
            value = metrics(subset, variant)
            delta = value["top3_precision"] - base["top3_precision"]
            lines.append(f"| {variant} | {value['races']} | {value['winner_rate']:.2f}% | {value['top3_precision']:.2f}% | {delta:+.2f}pp |")
        lines.append("")
    flat = [horse for race in races for horse in race["horses"]]
    matched = [horse for horse in flat if horse["features"].get("official_trial_latest_jockey_match")]
    unmatched = [horse for horse in flat if not horse["features"].get("official_trial_latest_jockey_match")]
    debut_matched = [horse for horse in matched if horse["is_debut"]]
    debut_unmatched = [horse for horse in unmatched if horse["is_debut"]]
    def top3_rate(rows: list[dict]) -> str:
        return f"{sum(1 for row in rows if row['actual_pos'] <= 3) / len(rows) * 100:.1f}%" if rows else "n/a"
    lines.extend([
        "## 訊號描述（非因果結論）", "",
        f"- 最新官方試閘騎師＝今場騎師：{len(matched)} 匹，實際 Top-3 {top3_rate(matched)}。",
        f"- 其餘有官方試閘樣本：{len(unmatched)} 匹，實際 Top-3 {top3_rate(unmatched)}。",
        f"- 初出馬之中，同騎師：{len(debut_matched)} 匹，Top-3 {top3_rate(debut_matched)}；非同騎師：{len(debut_unmatched)} 匹，Top-3 {top3_rate(debut_unmatched)}。",
        "", "## 判定規則", "",
        "只會考慮在時間 holdout 的 Top-3 命中率不低於 baseline，且沒有頭馬命中率倒退的變體；否則維持現行試閘分。", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest official trial shadow features against AU historical results.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    races = load_races()
    report = render_report(races)
    args.output.write_text(report, encoding="utf-8")
    print(f"eligible races: {len(races)} | {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
