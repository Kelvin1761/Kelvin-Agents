#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev

import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from matrix_mapper import map_features_to_matrix_scores
from scoring import MATRIX_WEIGHTS as LIVE_MATRIX_WEIGHTS

ARCHIVE_ROOT = AU_RACING
HISTORICAL_RESULTS_CSV = ARCHIVE_ROOT / "AU_Historical_Raw_Race_Results.csv"
OUTPUT_MD = ARCHIVE_ROOT / "AU_Auto_Archive_Calibration_Report.md"
OUTPUT_CSV = ARCHIVE_ROOT / "AU_Auto_Section_Diagnostics.csv"
OUTPUT_CONDITION_CSV = ARCHIVE_ROOT / "AU_Auto_Condition_Diagnostics.csv"

MATRIX_KEYS = (
    "stability",
    "sectional",
    "race_shape",
    "jockey_trainer",
    "class_weight",
    "track",
    "form_line",
)

MATRIX_LABELS = {
    "stability": "狀態與穩定性",
    "sectional": "段速與引擎",
    "race_shape": "檔位形勢",
    "jockey_trainer": "騎練訊號",
    "class_weight": "級數與負重",
    "track": "場地適性",
    "form_line": "賽績線",
}

CURRENT_MATRIX_WEIGHTS = dict(LIVE_MATRIX_WEIGHTS)
FEATURE_SCORE_KEYS = (
    "form_score",
    "trial_score",
    "sectional_score",
    "pace_map_score",
    "jockey_score",
    "trainer_score",
    "jockey_horse_fit_score",
    "class_score",
    "rating_score",
    "weight_score",
    "distance_score",
    "track_score",
    "formline_score",
    "consistency_score",
    "health_score",
    "confidence_score",
)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())



def get_true_horse_name(horse: dict) -> str:
    data = horse.get("_data") or {}
    facts = data.get("facts_section") or ""
    match = re.search(r"^\[\d+\]\s+([^(]+?)(?:\s+\(\d+\))?\n", facts)
    if match:
        return match.group(1).strip()
    name = horse.get("horse_name") or horse.get("name") or ""
    return str(name).strip()

def normalize_horse_name(name: str) -> str:
    clean = re.sub(r"\s*\([^)]*\)", "", str(name or ""))
    return slug(clean)


def normalize_track_name(name: str) -> str:
    clean = str(name or "").strip().lower()
    clean = clean.replace(" race 1-10", "").replace(" race 1-9", "").replace(" race 1-8", "").replace(" race 1-7", "")
    clean = clean.replace(" gardens", "")
    return slug(clean)


def normalize_condition_bucket(condition: str) -> str:
    text = str(condition or "").strip().lower()
    if not text:
        return "Unknown"
    if text.startswith(("good", "firm")):
        return "Good/Firm"
    if text.startswith("soft"):
        return "Soft"
    if text.startswith("heavy"):
        return "Heavy"
    if any(token in text for token in ("synthetic", "poly", "all weather", "all-weather")):
        return "Synthetic"
    return "Other"


def parse_int(value, default=None):
    match = re.search(r"-?\d+", str(value or ""))
    return int(match.group(0)) if match else default


def parse_float(value, default=None):
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return float(match.group(0)) if match else default


def scoring_path_for_race(meeting_dir: Path, race_no: int) -> Path | None:
    path = meeting_dir / f"Race_{race_no}_Auto_Scoring.csv"
    return path if path.exists() else None


def load_scoring_rows(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            horse_number = parse_int(row.get("horse_number"))
            if horse_number is None:
                continue
            feature_scores = {}
            for key in FEATURE_SCORE_KEYS:
                source_value = row.get(key)
                if key == "health_score" and source_value in (None, ""):
                    source_value = row.get("readiness_score")
                value = parse_float(source_value, 60.0)
                feature_scores[key] = value if value is not None else 60.0
            rows.append(
                {
                    "horse_number": horse_number,
                    "horse_slug": normalize_horse_name(row.get("horse_name") or ""),
                    "horse_name": str(row.get("horse_name") or "").strip(),
                    "ability_score": parse_float(row.get("ability_score"), 0.0) or 0.0,
                    "rank_score": (
                        parse_float(row.get("rank_score"), None)
                        if row.get("rank_score") not in (None, "")
                        else parse_float(row.get("ability_score"), 0.0)
                    ) or 0.0,
                    "rank": parse_int(row.get("rank")),
                    "grade": str(row.get("grade") or "").strip(),
                    "model_pick_status": str(row.get("model_pick_status") or "").strip(),
                    "feature_scores": feature_scores,
                    "matrix_scores": {
                        key: float(score)
                        for key, score in map_features_to_matrix_scores(feature_scores).items()
                        if key in MATRIX_KEYS
                    },
                }
            )
    return rows


def archive_snapshot(
    horse_num: str,
    horse: dict,
    scoring_lookup_by_num: dict[int, dict],
    scoring_lookup_by_name: dict[str, dict],
) -> dict | None:
    python_auto = horse.get("python_auto") or {}
    matrix_scores = python_auto.get("matrix_scores") or {}
    if matrix_scores:
        feature_scores = dict(python_auto.get("feature_scores") or {})
        if "health_score" not in feature_scores and "readiness_score" in feature_scores:
            feature_scores["health_score"] = feature_scores["readiness_score"]
        return {
            "ability_score": float(python_auto.get("ability_score") or 0.0),
            "rank_score": float(python_auto.get("rank_score") or python_auto.get("ability_score") or 0.0),
            "rank": parse_int(python_auto.get("rank")),
            "grade": str(python_auto.get("grade") or "").strip(),
            "model_pick_status": str(python_auto.get("model_pick_status") or "").strip(),
            "feature_scores": {key: float(feature_scores.get(key) or 60.0) for key in FEATURE_SCORE_KEYS},
            "matrix_scores": {key: float(matrix_scores.get(key) or 60.0) for key in MATRIX_KEYS},
            "risk_flags": list(python_auto.get("risk_flags") or []),
            "reason_codes": list(python_auto.get("reason_codes") or []),
            "matrix_reasoning": python_auto.get("matrix_reasoning") or {},
        }
    num = parse_int(horse_num)
    if num is not None and num in scoring_lookup_by_num:
        return scoring_lookup_by_num[num]
    return scoring_lookup_by_name.get(normalize_horse_name(get_true_horse_name(horse)))


def rank_items_desc(items):
    return sorted(items, key=lambda item: (-float(item["score"]), item["horse_number"]))


def load_historical_results(path: Path):
    by_date_race = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            race_no = parse_int(row.get("Race"))
            pos = parse_int(row.get("Pos"))
            if not race_no or not pos:
                continue
            record = {
                "date": str(row.get("Date") or "").strip(),
                "track": str(row.get("Track") or "").strip(),
                "track_slug": normalize_track_name(row.get("Track") or ""),
                "race": race_no,
                "horse": str(row.get("Horse") or "").strip(),
                "horse_slug": normalize_horse_name(row.get("Horse") or ""),
                "pos": pos,
                "barrier": parse_int(row.get("Barrier")),
                "sp": parse_float(row.get("SP")),
                "condition": str(row.get("Condition") or "").strip(),
            }
            by_date_race[(record["date"], race_no)].append(record)
    return by_date_race


def detect_meeting_date(meeting_dir: Path) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", meeting_dir.name)
    return match.group(1) if match else ""


def detect_meeting_track(meeting_dir: Path, sample_logic: dict) -> str:
    race_analysis = sample_logic.get("race_analysis", {})
    meeting = race_analysis.get("meeting_intelligence") or {}
    track_profile = race_analysis.get("track_profile") or {}
    for value in (
        meeting.get("venue"),
        track_profile.get("venue"),
        race_analysis.get("venue"),
    ):
        if value:
            return str(value).strip()
    name = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", meeting_dir.name)
    name = re.sub(r"\s+Race\s+\d+-\d+$", "", name)
    return name.strip()


def choose_track_rows(rows, meeting_track: str):
    target_slug = normalize_track_name(meeting_track)
    exact = [row for row in rows if row["track_slug"] == target_slug]
    if exact:
        return exact
    loose = [row for row in rows if row["track_slug"] in target_slug or target_slug in row["track_slug"]]
    # BUGFIX: never fall back to ALL rows. When a meeting's track does not match any
    # result-row track, returning every track's race-N rows silently joins scoring
    # against the WRONG track's results. Return [] so the race is (correctly) treated
    # as un-evaluable instead of contaminating metrics/training data.
    return loose


def iter_logic_rows(archive_root: Path, historical_results):
    for meeting_dir in sorted(path for path in archive_root.iterdir() if path.is_dir()):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        sample_logic = json.loads(logic_files[0].read_text(encoding="utf-8"))
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = detect_meeting_track(meeting_dir, sample_logic)
        if not meeting_date or not meeting_track:
            continue
        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_no = parse_int(logic.get("race_analysis", {}).get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            rows_for_race = choose_track_rows(historical_results.get((meeting_date, race_no), []), meeting_track)
            if not rows_for_race:
                continue
            scoring_path = scoring_path_for_race(meeting_dir, race_no)
            scoring_rows = load_scoring_rows(scoring_path) if scoring_path else []
            scoring_lookup_by_num = {row["horse_number"]: row for row in scoring_rows}
            scoring_lookup_by_name = {row["horse_slug"]: row for row in scoring_rows}
            race_lookup = {row["horse_slug"]: row for row in rows_for_race}
            race_rows = []
            for horse_num, horse in logic.get("horses", {}).items():
                snapshot = archive_snapshot(horse_num, horse, scoring_lookup_by_num, scoring_lookup_by_name)
                if not snapshot:
                    continue
                horse_slug = normalize_horse_name(get_true_horse_name(horse))
                result_row = race_lookup.get(horse_slug)
                if not result_row:
                    continue
                race_rows.append({
                    "meeting": meeting_dir.name,
                    "date": meeting_date,
                    "track": meeting_track,
                    "race": race_no,
                    "race_class": str(logic.get("race_analysis", {}).get("race_class") or "").strip(),
                    "condition": str(result_row.get("condition") or "").strip(),
                    "condition_bucket": normalize_condition_bucket(result_row.get("condition") or ""),
                    "horse_number": parse_int(horse_num) or 999,
                    "horse_name": str(get_true_horse_name(horse) or "").strip(),
                    "ability_score": float(snapshot.get("ability_score") or 0.0),
                    "rank_score": float(snapshot.get("rank_score") or snapshot.get("ability_score") or 0.0),
                    "model_score": float(snapshot.get("ability_score") or snapshot.get("rank_score") or 0.0),
                    "rank": snapshot.get("rank"),
                    "grade": snapshot.get("grade", ""),
                    "model_pick_status": snapshot.get("model_pick_status", ""),
                    "actual_pos": int(result_row["pos"]),
                    "sp": result_row["sp"],
                    "feature_scores": {key: float(snapshot.get("feature_scores", {}).get(key) or 60.0) for key in FEATURE_SCORE_KEYS},
                    "matrix_scores": {key: float(snapshot.get("matrix_scores", {}).get(key) or 60.0) for key in MATRIX_KEYS},
                    "risk_flags": list(snapshot.get("risk_flags") or []),
                    "reason_codes": list(snapshot.get("reason_codes") or []),
                    "matrix_reasoning": snapshot.get("matrix_reasoning") or {},
                    "data": horse.get("_data") or {},
                    "horse": horse,
                })
            if len(race_rows) >= 4:
                yield race_rows


def pairwise_concordance(race_rows, score_key):
    pairs = 0
    concordant = 0.0
    for i, left in enumerate(race_rows):
        for right in race_rows[i + 1:]:
            if left["actual_pos"] == right["actual_pos"]:
                continue
            pairs += 1
            left_better = left["actual_pos"] < right["actual_pos"]
            left_score = left[score_key]
            right_score = right[score_key]
            if left_score == right_score:
                concordant += 0.5
            elif (left_score > right_score and left_better) or (left_score < right_score and not left_better):
                concordant += 1.0
    return concordant / pairs if pairs else 0.5


def top_n_hits(race_rows, score_key, n=3):
    ranked = sorted(race_rows, key=lambda row: (-row[score_key], row["horse_number"]))
    picks = ranked[:n]
    top3_hits = sum(1 for row in picks if row["actual_pos"] <= 3)
    winner_hit = any(row["actual_pos"] == 1 for row in picks)
    return picks, top3_hits, winner_hit


def has_complete_result(race_rows):
    if not race_rows:
        return False
    has_winner = any(row["actual_pos"] == 1 for row in race_rows)
    top3_count = sum(1 for row in race_rows if row["actual_pos"] <= 3)
    return has_winner and top3_count >= 3


def summarize_archive(archive_root: Path, historical_results):
    all_races = list(iter_logic_rows(archive_root, historical_results))
    section_stats = {
        key: {
            "race_count": 0,
            "winner_top1_hits": 0,
            "winner_top3_hits": 0,
            "top3_hits": 0,
            "top3_slots": 0,
            "pairwise": [],
            "winner_lifts": [],
            "score_spreads": [],
        }
        for key in MATRIX_KEYS
    }
    overall = {
        "races": 0,
        "horses": 0,
        "ability_top1_wins": 0,
        "ability_top3_winner_hits": 0,
        "ability_top3_place_hits": 0,
        "ability_top3_slots": 0,
        "favourite_wins": 0,
        "favourite_top3_places": 0,
    }
    clean_overall = {
        "races": 0,
        "horses": 0,
        "ability_top1_wins": 0,
        "ability_top3_winner_hits": 0,
        "ability_top3_place_hits": 0,
        "ability_top3_slots": 0,
        "favourite_wins": 0,
        "favourite_top3_places": 0,
    }
    condition_overall = defaultdict(
        lambda: {
            "races": 0,
            "horses": 0,
            "ability_top1_wins": 0,
            "ability_top3_winner_hits": 0,
            "ability_top3_place_hits": 0,
            "ability_top3_slots": 0,
            "favourite_wins": 0,
            "favourite_top3_places": 0,
        }
    )
    clean_condition_overall = defaultdict(
        lambda: {
            "races": 0,
            "horses": 0,
            "ability_top1_wins": 0,
            "ability_top3_winner_hits": 0,
            "ability_top3_place_hits": 0,
            "ability_top3_slots": 0,
            "favourite_wins": 0,
            "favourite_top3_places": 0,
        }
    )
    missing_notes = defaultdict(int)

    for race_rows in all_races:
        overall["races"] += 1
        overall["horses"] += len(race_rows)
        condition_bucket = race_rows[0].get("condition_bucket") or "Unknown"
        condition_stats = condition_overall[condition_bucket]
        condition_stats["races"] += 1
        condition_stats["horses"] += len(race_rows)
        complete_result = has_complete_result(race_rows)
        if not complete_result:
            missing_notes["historical result gap races"] += 1
        winner = min(race_rows, key=lambda row: row["actual_pos"])

        ability_ranked = sorted(race_rows, key=lambda row: (-row["model_score"], row["horse_number"]))
        if ability_ranked[0]["actual_pos"] == 1:
            overall["ability_top1_wins"] += 1
            condition_stats["ability_top1_wins"] += 1
        ability_top3 = ability_ranked[:3]
        if any(row["actual_pos"] == 1 for row in ability_top3):
            overall["ability_top3_winner_hits"] += 1
            condition_stats["ability_top3_winner_hits"] += 1
        overall["ability_top3_place_hits"] += sum(1 for row in ability_top3 if row["actual_pos"] <= 3)
        overall["ability_top3_slots"] += len(ability_top3)
        condition_stats["ability_top3_place_hits"] += sum(1 for row in ability_top3 if row["actual_pos"] <= 3)
        condition_stats["ability_top3_slots"] += len(ability_top3)

        favourite = min((row for row in race_rows if row["sp"] is not None), key=lambda row: row["sp"], default=None)
        if favourite:
            if favourite["actual_pos"] == 1:
                overall["favourite_wins"] += 1
                condition_stats["favourite_wins"] += 1
            if favourite["actual_pos"] <= 3:
                overall["favourite_top3_places"] += 1
                condition_stats["favourite_top3_places"] += 1

        if not complete_result:
            continue

        clean_overall["races"] += 1
        clean_overall["horses"] += len(race_rows)
        clean_condition_stats = clean_condition_overall[condition_bucket]
        clean_condition_stats["races"] += 1
        clean_condition_stats["horses"] += len(race_rows)
        if ability_ranked[0]["actual_pos"] == 1:
            clean_overall["ability_top1_wins"] += 1
            clean_condition_stats["ability_top1_wins"] += 1
        if any(row["actual_pos"] == 1 for row in ability_top3):
            clean_overall["ability_top3_winner_hits"] += 1
            clean_condition_stats["ability_top3_winner_hits"] += 1
        clean_overall["ability_top3_place_hits"] += sum(1 for row in ability_top3 if row["actual_pos"] <= 3)
        clean_overall["ability_top3_slots"] += len(ability_top3)
        clean_condition_stats["ability_top3_place_hits"] += sum(1 for row in ability_top3 if row["actual_pos"] <= 3)
        clean_condition_stats["ability_top3_slots"] += len(ability_top3)
        if favourite:
            if favourite["actual_pos"] == 1:
                clean_overall["favourite_wins"] += 1
                clean_condition_stats["favourite_wins"] += 1
            if favourite["actual_pos"] <= 3:
                clean_overall["favourite_top3_places"] += 1
                clean_condition_stats["favourite_top3_places"] += 1

        for key in MATRIX_KEYS:
            ranked = sorted(race_rows, key=lambda row: (-row["matrix_scores"][key], row["horse_number"]))
            top3 = ranked[:3]
            section_stats[key]["race_count"] += 1
            if ranked[0]["actual_pos"] == 1:
                section_stats[key]["winner_top1_hits"] += 1
            if any(row["actual_pos"] == 1 for row in top3):
                section_stats[key]["winner_top3_hits"] += 1
            section_stats[key]["top3_hits"] += sum(1 for row in top3 if row["actual_pos"] <= 3)
            section_stats[key]["top3_slots"] += len(top3)
            section_stats[key]["pairwise"].append(
                pairwise_concordance(
                    [{"actual_pos": row["actual_pos"], key: row["matrix_scores"][key]} for row in race_rows],
                    key,
                )
            )
            winner_score = next(row["matrix_scores"][key] for row in race_rows if row["horse_number"] == winner["horse_number"])
            field_score = mean(row["matrix_scores"][key] for row in race_rows)
            section_stats[key]["winner_lifts"].append(winner_score - field_score)
            section_stats[key]["score_spreads"].append(pstdev(row["matrix_scores"][key] for row in race_rows))

            for row in race_rows:
                data = row["data"]
                if key == "jockey_trainer" and not str(data.get("current_jockey_history_line") or "").strip():
                    missing_notes["jockey history missing"] += 1
                if key == "sectional" and not str(data.get("sectional_trend_line") or "").strip():
                    missing_notes["sectional trend missing"] += 1
                if key == "track" and not str(data.get("track_record_line") or "").strip():
                    missing_notes["track record missing"] += 1
                if key == "form_line" and not str(data.get("formline_line") or "").strip():
                    missing_notes["formline missing"] += 1

    diagnostics = []
    for key, stats in section_stats.items():
        race_count = max(1, stats["race_count"])
        winner_top1_rate = stats["winner_top1_hits"] / race_count
        winner_top3_rate = stats["winner_top3_hits"] / race_count
        top3_precision = stats["top3_hits"] / max(1, stats["top3_slots"])
        pairwise = mean(stats["pairwise"]) if stats["pairwise"] else 0.5
        lift = mean(stats["winner_lifts"]) if stats["winner_lifts"] else 0.0
        spread = mean(stats["score_spreads"]) if stats["score_spreads"] else 0.0
        signal = (
            max(0.0, pairwise - 0.5) * 2.0 * 0.35
            + winner_top1_rate * 0.25
            + winner_top3_rate * 0.25
            + top3_precision * 0.15
        )
        diagnostics.append({
            "key": key,
            "label": MATRIX_LABELS[key],
            "current_weight": CURRENT_MATRIX_WEIGHTS[key],
            "winner_top1_rate": winner_top1_rate,
            "winner_top3_rate": winner_top3_rate,
            "top3_precision": top3_precision,
            "pairwise": pairwise,
            "winner_lift": lift,
            "spread": spread,
            "signal": signal,
        })

    total_signal = sum(item["signal"] for item in diagnostics) or 1.0
    for item in diagnostics:
        item["suggested_weight"] = item["signal"] / total_signal
        item["weight_delta"] = item["suggested_weight"] - item["current_weight"]

    diagnostics.sort(key=lambda item: item["suggested_weight"], reverse=True)
    condition_diagnostics = []
    for bucket, stats in sorted(condition_overall.items(), key=lambda item: (-item[1]["races"], item[0])):
        races = max(1, stats["races"])
        condition_diagnostics.append({
            "condition_bucket": bucket,
            "races": stats["races"],
            "horses": stats["horses"],
            "ability_top1_rate": stats["ability_top1_wins"] / races,
            "ability_top3_winner_rate": stats["ability_top3_winner_hits"] / races,
            "ability_top3_place_precision": stats["ability_top3_place_hits"] / max(1, stats["ability_top3_slots"]),
            "favourite_win_rate": stats["favourite_wins"] / races,
            "favourite_place_rate": stats["favourite_top3_places"] / races,
        })
    clean_condition_diagnostics = []
    for bucket, stats in sorted(clean_condition_overall.items(), key=lambda item: (-item[1]["races"], item[0])):
        races = max(1, stats["races"])
        clean_condition_diagnostics.append({
            "condition_bucket": bucket,
            "races": stats["races"],
            "horses": stats["horses"],
            "ability_top1_rate": stats["ability_top1_wins"] / races,
            "ability_top3_winner_rate": stats["ability_top3_winner_hits"] / races,
            "ability_top3_place_precision": stats["ability_top3_place_hits"] / max(1, stats["ability_top3_slots"]),
            "favourite_win_rate": stats["favourite_wins"] / races,
            "favourite_place_rate": stats["favourite_top3_places"] / races,
        })
    return {
        "overall": overall,
        "clean_overall": clean_overall,
        "diagnostics": diagnostics,
        "condition_diagnostics": condition_diagnostics,
        "clean_condition_diagnostics": clean_condition_diagnostics,
        "missing_notes": dict(sorted(missing_notes.items(), key=lambda kv: kv[1], reverse=True)),
    }


def write_csv(path: Path, diagnostics):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "key", "label", "current_weight", "suggested_weight", "weight_delta",
            "winner_top1_rate", "winner_top3_rate", "top3_precision", "pairwise", "winner_lift", "spread",
        ])
        for item in diagnostics:
            writer.writerow([
                item["key"],
                item["label"],
                round(item["current_weight"], 4),
                round(item["suggested_weight"], 4),
                round(item["weight_delta"], 4),
                round(item["winner_top1_rate"], 4),
                round(item["winner_top3_rate"], 4),
                round(item["top3_precision"], 4),
                round(item["pairwise"], 4),
                round(item["winner_lift"], 4),
                round(item["spread"], 4),
            ])


def write_condition_csv(path: Path, diagnostics):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "condition_bucket",
            "races",
            "horses",
            "ability_top1_rate",
            "ability_top3_winner_rate",
            "ability_top3_place_precision",
            "favourite_win_rate",
            "favourite_place_rate",
        ])
        for item in diagnostics:
            writer.writerow([
                item["condition_bucket"],
                item["races"],
                item["horses"],
                round(item["ability_top1_rate"], 4),
                round(item["ability_top3_winner_rate"], 4),
                round(item["ability_top3_place_precision"], 4),
                round(item["favourite_win_rate"], 4),
                round(item["favourite_place_rate"], 4),
            ])


def render_report(summary):
    overall = summary["overall"]
    clean_overall = summary.get("clean_overall", overall)
    diagnostics = summary["diagnostics"]
    condition_diagnostics = summary.get("condition_diagnostics", [])
    clean_condition_diagnostics = summary.get("clean_condition_diagnostics", condition_diagnostics)
    races = max(1, overall["races"])
    clean_races = max(1, clean_overall["races"])
    ability_top1 = overall["ability_top1_wins"] / races
    ability_top3_winner = overall["ability_top3_winner_hits"] / races
    ability_top3_place = overall["ability_top3_place_hits"] / max(1, overall["ability_top3_slots"])
    favourite_win = overall["favourite_wins"] / races
    favourite_place = overall["favourite_top3_places"] / races
    clean_ability_top1 = clean_overall["ability_top1_wins"] / clean_races
    clean_ability_top3_winner = clean_overall["ability_top3_winner_hits"] / clean_races
    clean_ability_top3_place = clean_overall["ability_top3_place_hits"] / max(1, clean_overall["ability_top3_slots"])
    clean_favourite_win = clean_overall["favourite_wins"] / clean_races
    clean_favourite_place = clean_overall["favourite_top3_places"] / clean_races

    overweight = [item for item in diagnostics if item["weight_delta"] <= -0.025]
    underweight = [item for item in diagnostics if item["weight_delta"] >= 0.025]
    weak_sections = [item for item in diagnostics if item["pairwise"] < 0.54 or item["spread"] < 4.0]

    lines = [
        "# AU Auto Archive Calibration Report",
        "",
        f"- Raw sample races: **{overall['races']}**",
        f"- Raw sample horses: **{overall['horses']}**",
        f"- Clean sample races: **{clean_overall['races']}**",
        f"- Clean sample horses: **{clean_overall['horses']}**",
        f"- Excluded result-gap races: **{overall['races'] - clean_overall['races']}**",
        f"- Model top-1 win rate: **{ability_top1:.1%}** raw | **{clean_ability_top1:.1%}** clean",
        f"- Model top-3 contains winner: **{ability_top3_winner:.1%}** raw | **{clean_ability_top3_winner:.1%}** clean",
        f"- Model top-3 place precision: **{ability_top3_place:.1%}** raw | **{clean_ability_top3_place:.1%}** clean",
        f"- Market favourite win rate: **{favourite_win:.1%}** raw | **{clean_favourite_win:.1%}** clean",
        f"- Market favourite place rate: **{favourite_place:.1%}** raw | **{clean_favourite_place:.1%}** clean",
        f"- Analysis profile: **Market-agnostic horse analysis**",
        "",
        "## Condition Breakdown (Clean Sample)",
        "",
        "| Condition | Races | Horses | Model@1 | Model@Top3 | Top3 Precision | Fav@1 | Fav@Top3 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in clean_condition_diagnostics:
        lines.append(
            f"| {item['condition_bucket']} | {item['races']} | {item['horses']} | "
            f"{item['ability_top1_rate']:.1%} | {item['ability_top3_winner_rate']:.1%} | "
            f"{item['ability_top3_place_precision']:.1%} | {item['favourite_win_rate']:.1%} | "
            f"{item['favourite_place_rate']:.1%} |"
        )
    lines.extend([
        "",
        "## Section Diagnostics",
        "",
        "| Section | Current | Suggested | Delta | Pairwise | Winner@1 | Winner@Top3 | Top3 Precision | Winner Lift | Spread |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for item in diagnostics:
        lines.append(
            f"| {item['label']} | {item['current_weight']:.2f} | {item['suggested_weight']:.2f} | {item['weight_delta']:+.2f} | "
            f"{item['pairwise']:.3f} | {item['winner_top1_rate']:.1%} | {item['winner_top3_rate']:.1%} | "
            f"{item['top3_precision']:.1%} | {item['winner_lift']:.2f} | {item['spread']:.2f} |"
        )

    lines.extend([
        "",
        "## What To Raise",
        "",
    ])
    if underweight:
        for item in underweight:
            lines.append(
                f"- `{item['label']}` appears under-weighted: suggested {item['suggested_weight']:.2f} vs current {item['current_weight']:.2f}, "
                f"pairwise {item['pairwise']:.3f}, winner@top3 {item['winner_top3_rate']:.1%}."
            )
    else:
        lines.append("- No section cleared the under-weight threshold in this pass.")

    lines.extend([
        "",
        "## What To Trim",
        "",
    ])
    if overweight:
        for item in overweight:
            lines.append(
                f"- `{item['label']}` looks overweight: suggested {item['suggested_weight']:.2f} vs current {item['current_weight']:.2f}, "
                f"pairwise {item['pairwise']:.3f}, average spread {item['spread']:.2f}."
            )
    else:
        lines.append("- No section cleared the over-weight threshold in this pass.")

    lines.extend([
        "",
        "## Blind Spots",
        "",
    ])
    if weak_sections:
        for item in weak_sections:
            reason = []
            if item["pairwise"] < 0.54:
                reason.append(f"pairwise only {item['pairwise']:.3f}")
            if item["spread"] < 4.0:
                reason.append(f"score spread only {item['spread']:.2f}")
            lines.append(f"- `{item['label']}` still lacks discrimination: " + " and ".join(reason) + ".")
    else:
        lines.append("- No section was both weak and flat by this threshold.")

    lines.extend([
        "",
        "## Coverage Gaps",
        "",
    ])
    if summary["missing_notes"]:
        for label, count in list(summary["missing_notes"].items())[:8]:
            lines.append(f"- `{label}` observed **{count}** times in scanned archive horses.")
    else:
        lines.append("- No coverage gaps were logged in this pass.")

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- `Pairwise` 越高，代表該 section 單獨拿出來排 horses 時，越能跟實際名次方向對上。",
        "- `Winner@1` 代表該 section 自己的第一名直接中頭馬的比例。",
        "- `Winner@Top3` 代表該 section 的 top-3 至少包住頭馬。",
        "- `Top3 Precision` 代表該 section 揀出的 top-3，有幾多最終真係跑入前三。",
        "- `Winner Lift` 代表頭馬在該 section 分數平均比全場高幾多分。",
        "- `Spread` 太低通常代表該 section 太平，對排序幫助有限。",
        "",
    ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Calibrate AU Auto matrix weights from archive results")
    parser.add_argument("--archive-root", default=str(ARCHIVE_ROOT))
    parser.add_argument("--results-csv", default=str(HISTORICAL_RESULTS_CSV))
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    parser.add_argument("--output-csv", default=str(OUTPUT_CSV))
    parser.add_argument("--output-condition-csv", default=str(OUTPUT_CONDITION_CSV))
    args = parser.parse_args()

    archive_root = Path(args.archive_root)
    results_csv = Path(args.results_csv)
    if not archive_root.exists():
        raise FileNotFoundError(archive_root)
    if not results_csv.exists():
        raise FileNotFoundError(results_csv)

    summary = summarize_archive(archive_root, load_historical_results(results_csv))
    output_md = Path(args.output_md)
    output_csv = Path(args.output_csv)
    output_condition_csv = Path(args.output_condition_csv)
    output_md.write_text(render_report(summary), encoding="utf-8")
    write_csv(output_csv, summary["diagnostics"])
    write_condition_csv(output_condition_csv, summary["condition_diagnostics"])

    print(f"Scanned races: {summary['overall']['races']}")
    print(f"Scanned horses: {summary['overall']['horses']}")
    print(f"Report written: {output_md}")
    print(f"Diagnostics written: {output_csv}")
    print(f"Condition diagnostics written: {output_condition_csv}")


if __name__ == "__main__":
    main()
