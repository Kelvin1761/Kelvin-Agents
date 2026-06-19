#!/usr/bin/env python3
"""
build_hkjc_ranking_dataset.py — materialize a horse-level HKJC ranking dataset.

This script is research-only. It does not modify mainline scoring.
It joins archived `Race_*_Logic.json` files with actual results and emits one row
per horse per race for downstream ranking-model experiments.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from hkjc_results_db import get_comprehensive_stats_root
from review_auto_weighting import (
    CURRENT_MATRIX_FORMULAS,
    CURRENT_MATRIX_WEIGHTS,
    _normalize_distance,
    _normalize_venue,
    build_results_index,
    clip_score,
    compute_ability,
    compute_full_feature_scores,
    compute_matrix_scores,
    dedup_race_key,
    default_meeting_roots,
    default_results_roots,
    hk_meeting_dirs,
    load_results,
    meeting_date,
    race_num_from_path,
    venue_from_meeting_dir,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "artifacts" / "hkjc_ranking_dataset.csv"
DEFAULT_SUMMARY = SCRIPT_DIR.parent / "artifacts" / "hkjc_ranking_dataset_summary.json"
PRIORS_ROOT = get_comprehensive_stats_root() / "24_25" / "general_pre_race_priors"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build HKJC horse-level ranking dataset from archive meetings")
    parser.add_argument("--meeting-root", action="append", default=[], help="Root folder to scan for HKJC meetings")
    parser.add_argument("--results-root", action="append", default=[], help="Root folder containing HKJC results")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path")
    parser.add_argument("--summary-output", default=str(DEFAULT_SUMMARY), help="Output summary JSON path")
    return parser.parse_args()


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        if math.isnan(float(value)):
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _coerce_int(value: object) -> int | None:
    number = _coerce_float(value)
    if number is None:
        return None
    return int(round(number))


def _distance_token(value: object) -> str:
    text = _normalize_distance(value)
    match = re.search(r"(\d{3,4})", text)
    return match.group(1) if match else text or "unknown"


def _race_class_number(value: object) -> int | None:
    text = str(value or "").strip()
    match = re.search(r"(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def _race_class_label(value: object) -> str:
    num = _race_class_number(value)
    return f"Class {num}" if num is not None else "Unknown"


def _normalize_track(value: object) -> str:
    text = str(value or "").strip().upper()
    if any(token in text for token in ("泥", "AWT", "DIRT", "ALL WEATHER")):
        return "AWT"
    return "Turf"


def _normalize_course(value: object) -> str:
    text = str(value or "").replace("賽道", "").strip()
    return text or "Unknown"


def _horse_id_from_name(value: object) -> str:
    text = str(value or "").strip()
    match = re.search(r"\(([A-Z]\d{3})\)", text)
    return match.group(1) if match else ""


def _rest_bucket(days_since_last: object) -> str:
    days = _coerce_float(days_since_last)
    if days is None:
        return "Unknown"
    if days <= 14:
        return "<=14d"
    if days <= 28:
        return "15-28d"
    if days <= 56:
        return "29-56d"
    if days <= 90:
        return "57-90d"
    return "91d+"


def _draw_bucket(draw: object) -> str:
    barrier = _coerce_int(draw)
    if barrier is None:
        return "Unknown"
    if barrier <= 3:
        return "1-3"
    if barrier <= 6:
        return "4-6"
    if barrier <= 9:
        return "7-9"
    return "10+"


def _weight_bucket(weight: object) -> str:
    pounds = _coerce_float(weight)
    if pounds is None:
        return "Unknown"
    if pounds <= 115:
        return "Light (<=115)"
    if pounds <= 120:
        return "Med-Light (116-120)"
    if pounds <= 126:
        return "Medium (121-126)"
    if pounds <= 130:
        return "Med-Heavy (127-130)"
    return "Heavy (131+)"


def _run_style_bucket(value: object) -> str:
    text = str(value or "")
    if any(token in text for token in ("前", "領放", "Type A", "Frontrunner")):
        return "Frontrunner"
    if any(token in text for token in ("後", "Closer", "Type C")):
        return "Closer"
    if text.strip():
        return "Midpack"
    return "Unknown"


def _gear_flags(value: object) -> dict[str, float | int | None]:
    gear = str(value or "").strip()
    tokens = [token for token in re.split(r"[\/,]", gear) if token.strip()]
    return {
        "card_gear_count": float(len(tokens)) if gear else 0.0,
        "card_gear_first_time": int(bool(re.search(r"\d", gear))),
        "card_gear_tt": int("TT" in gear),
        "card_gear_cp": int("CP" in gear),
        "card_gear_blinkers": int("B" in gear),
    }


def _priority_rank(value: object) -> float | None:
    text = str(value or "").strip()
    number = _coerce_float(text)
    if number is None:
        return None
    return number + 0.5 if "+" in text else number


def _claim_lbs(value: object) -> float:
    text = str(value or "")
    match = re.search(r"\(-(\d+)\)", text)
    return float(match.group(1)) if match else 0.0


def _line_value(block: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", block, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _dedup_meeting_dirs(meetings: list[Path]) -> list[Path]:
    chosen: dict[tuple[str | None, str], Path] = {}
    for meeting_dir in meetings:
        key = (meeting_date(meeting_dir), meeting_dir.name)
        current = chosen.get(key)
        if current is None or len(str(meeting_dir)) < len(str(current)):
            chosen[key] = meeting_dir
    return sorted(chosen.values(), key=lambda path: str(path))


@lru_cache(maxsize=None)
def _load_racecard_snapshot(meeting_dir: str, race_num: int) -> dict[str, Any]:
    meeting_path = Path(meeting_dir)
    candidates = sorted(meeting_path.glob(f"*Race {race_num} 排位表.md"))
    if not candidates:
        return {"race_info": {}, "horses": {}}

    content = candidates[0].read_text(encoding="utf-8")
    race_info = {
        "venue": _line_value(content, "地點"),
        "track": _line_value(content, "場地"),
        "course": _line_value(content, "賽道"),
        "distance": _line_value(content, "路程"),
        "race_class": _line_value(content, "班次"),
    }
    horses: dict[int, dict[str, Any]] = {}
    for block in re.split(r"(?=^馬號:\s*\d+\s*$)", content, flags=re.MULTILINE):
        number = _coerce_int(_line_value(block, "馬號"))
        if number is None:
            continue
        jockey_text = _line_value(block, "騎師")
        claim_lbs = _claim_lbs(jockey_text)
        entry = {
            "horse_id": _line_value(block, "烙號"),
            "rating": _coerce_float(_line_value(block, "評分")),
            "rating_change": _coerce_float(_line_value(block, "評分+/-")),
            "declared_bodyweight": _coerce_float(_line_value(block, "排位體重")),
            "age": _coerce_float(_line_value(block, "馬齡")),
            "priority_rank": _priority_rank(_line_value(block, "優先參賽次序")),
            "gear": _line_value(block, "配備"),
            "claim_lbs": claim_lbs,
            "has_claim": int(claim_lbs > 0),
        }
        entry.update(_gear_flags(entry["gear"]))
        horses[number] = entry
    return {"race_info": race_info, "horses": horses}


class HistoricalPriors:
    def __init__(self) -> None:
        self.combo = self._load_stats(PRIORS_ROOT / "jockey_trainer_combo_priors.csv", ["Jockey", "Trainer"])
        self.jockey_cd = self._load_stats(
            PRIORS_ROOT / "jockey_course_distance_priors.csv",
            ["Jockey", "Venue", "Track", "Distance"],
        )
        self.trainer_cd = self._load_stats(
            PRIORS_ROOT / "trainer_course_distance_priors.csv",
            ["Trainer", "Venue", "Track", "Distance"],
        )
        self.class_distance = self._load_stats(
            PRIORS_ROOT / "class_distance_priors.csv",
            ["RaceClass", "Venue", "Track", "Distance"],
        )
        self.draw_class = self._load_stats(
            PRIORS_ROOT / "draw_bucket_distance_class_priors.csv",
            ["RaceClass", "Venue", "Track", "Distance", "DrawBucket"],
        )
        self.weight_class = self._load_stats(
            PRIORS_ROOT / "weight_class_priors.csv",
            ["RaceClass", "WtBucket"],
        )
        self.rest_bucket = self._load_stats(PRIORS_ROOT / "rest_bucket_priors.csv", ["RestBucket"])
        self.runstyle_cd = self._load_stats(
            PRIORS_ROOT / "running_style_distance_priors.csv",
            ["RunStyle", "Venue", "Track", "Distance"],
        )
        self.horse_cd = self._load_stats(
            PRIORS_ROOT / "horse_course_distance_profile.csv",
            ["HorseID", "Venue", "Track", "Distance"],
        )
        self.horse_rest = self._load_stats(
            PRIORS_ROOT / "horse_rest_cycle_profile.csv",
            ["HorseID", "RestBucket"],
        )
        self.horse_style = self._load_stats(
            PRIORS_ROOT / "horse_running_style_profile.csv",
            ["HorseID", "RunStyle"],
        )

    def _load_stats(self, path: Path, keys: list[str]) -> dict[tuple[str, ...], dict[str, float]]:
        if not path.exists():
            return {}
        df = pd.read_csv(path, encoding="utf-8-sig")
        for column in ("Starts", "Wins", "Places", "WinRate", "PlaceRate", "ROI"):
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
        records: dict[tuple[str, ...], dict[str, float]] = {}
        for row in df.to_dict(orient="records"):
            key = tuple(str(row.get(item, "")).strip() for item in keys)
            records[key] = {
                "starts": float(row.get("Starts", 0.0) or 0.0),
                "wins": float(row.get("Wins", 0.0) or 0.0),
                "places": float(row.get("Places", 0.0) or 0.0),
                "win_rate": float(row.get("WinRate", 0.0) or 0.0),
                "place_rate": float(row.get("PlaceRate", 0.0) or 0.0),
                "roi": float(row.get("ROI", 0.0) or 0.0),
            }
        return records

    def _emit(self, prefix: str, record: dict[str, float] | None) -> dict[str, float | None]:
        if not record:
            return {
                f"{prefix}_starts": None,
                f"{prefix}_win_rate": None,
                f"{prefix}_place_rate": None,
                f"{prefix}_roi": None,
            }
        return {
            f"{prefix}_starts": record["starts"],
            f"{prefix}_win_rate": record["win_rate"],
            f"{prefix}_place_rate": record["place_rate"],
            f"{prefix}_roi": record["roi"],
        }

    def lookup(
        self,
        *,
        horse_id: str,
        jockey: str,
        trainer: str,
        venue: str,
        track: str,
        distance_num: int | None,
        race_class_label: str,
        barrier: int | None,
        weight_carried: float | None,
        days_since_last: float | None,
        running_style: str,
    ) -> dict[str, float | None]:
        distance_key = str(distance_num or "")
        draw_bucket = _draw_bucket(barrier)
        weight_bucket = _weight_bucket(weight_carried)
        rest_bucket = _rest_bucket(days_since_last)
        run_style = _run_style_bucket(running_style)
        class_distance = self.class_distance.get((race_class_label, venue, track, distance_key))

        payload: dict[str, float | None] = {}
        payload.update(self._emit("prior_combo", self.combo.get((jockey, trainer))))
        payload.update(self._emit("prior_jockey_cd", self.jockey_cd.get((jockey, venue, track, distance_key))))
        payload.update(self._emit("prior_trainer_cd", self.trainer_cd.get((trainer, venue, track, distance_key))))
        payload.update(self._emit("prior_class_distance", class_distance))
        payload.update(self._emit("prior_draw_class", self.draw_class.get((race_class_label, venue, track, distance_key, draw_bucket))))
        payload.update(self._emit("prior_weight_class", self.weight_class.get((race_class_label, weight_bucket))))
        payload.update(self._emit("prior_rest_bucket", self.rest_bucket.get((rest_bucket,))))
        payload.update(self._emit("prior_runstyle_cd", self.runstyle_cd.get((run_style, venue, track, distance_key))))
        payload.update(self._emit("prior_horse_cd", self.horse_cd.get((horse_id, venue, track, distance_key))))
        payload.update(self._emit("prior_horse_rest", self.horse_rest.get((horse_id, rest_bucket))))
        payload.update(self._emit("prior_horse_style", self.horse_style.get((horse_id, run_style))))

        baseline_place = class_distance["place_rate"] if class_distance else None
        baseline_win = class_distance["win_rate"] if class_distance else None
        for prefix in (
            "prior_combo",
            "prior_jockey_cd",
            "prior_trainer_cd",
            "prior_draw_class",
            "prior_weight_class",
            "prior_rest_bucket",
            "prior_runstyle_cd",
            "prior_horse_cd",
            "prior_horse_rest",
            "prior_horse_style",
        ):
            place_rate = payload.get(f"{prefix}_place_rate")
            win_rate = payload.get(f"{prefix}_win_rate")
            payload[f"{prefix}_place_edge"] = (
                round(float(place_rate) - float(baseline_place), 4)
                if place_rate is not None and baseline_place is not None
                else None
            )
            payload[f"{prefix}_win_edge"] = (
                round(float(win_rate) - float(baseline_win), 4)
                if win_rate is not None and baseline_win is not None
                else None
            )
        return payload


def _count_keywords(text: object, keywords: list[str]) -> int:
    value = str(text or "")
    return sum(1 for keyword in keywords if keyword in value)


def _flag_keywords(text: object, keywords: list[str]) -> int:
    return int(_count_keywords(text, keywords) > 0)


def _parse_last_finishes(value: object) -> list[int]:
    if isinstance(value, list):
        out: list[int] = []
        for item in value:
            num = _coerce_int(item)
            if num is not None and 1 <= num <= 99:
                out.append(num)
        return out[:6]
    if isinstance(value, str):
        out = []
        for token in re.findall(r"\d+", value):
            num = _coerce_int(token)
            if num is not None and 1 <= num <= 99:
                out.append(num)
        return out[:6]
    return []


def _last_finish_features(finishes: list[int]) -> dict[str, float | int | None]:
    if not finishes:
        return {
            "last6_runs": 0,
            "last6_mean_finish": None,
            "last6_best_finish": None,
            "last6_worst_finish": None,
            "last6_top3_count": 0,
            "last6_top5_count": 0,
        }
    return {
        "last6_runs": len(finishes),
        "last6_mean_finish": round(sum(finishes) / len(finishes), 4),
        "last6_best_finish": min(finishes),
        "last6_worst_finish": max(finishes),
        "last6_top3_count": sum(1 for finish in finishes if finish <= 3),
        "last6_top5_count": sum(1 for finish in finishes if finish <= 5),
    }


def _parse_triplet_stats(text: object, label: str, prefix: str) -> dict[str, float | None]:
    value = str(text or "")
    match = re.search(rf"{re.escape(label)}\s*\((\d+)-(\d+)-(\d+)-(\d+)\)", value)
    if not match:
        return {
            f"{prefix}_starts": None,
            f"{prefix}_wins": None,
            f"{prefix}_seconds": None,
            f"{prefix}_thirds": None,
        }
    return {
        f"{prefix}_starts": float(match.group(1)),
        f"{prefix}_wins": float(match.group(2)),
        f"{prefix}_seconds": float(match.group(3)),
        f"{prefix}_thirds": float(match.group(4)),
    }


def _season_stat_features(text: object) -> dict[str, float | None]:
    payload = {}
    payload.update(_parse_triplet_stats(text, "季內", "season"))
    payload.update(_parse_triplet_stats(text, "同程", "same_distance"))
    payload.update(_parse_triplet_stats(text, "同場同程", "same_venue_distance"))
    return payload


def _trackwork_features(trackwork: object) -> dict[str, float | int | None]:
    if not isinstance(trackwork, dict):
        return {
            "tw_entries_count": None,
            "tw_gallop_count": None,
            "tw_flags_count": None,
            "tw_confidence_high": 0,
            "tw_confidence_low": 0,
            "tw_jockey_present": 0,
            "tw_mode_barrier_trial": 0,
        }

    entries = trackwork.get("entries") or []
    flags = trackwork.get("flags") or []
    confidence = str(trackwork.get("confidence") or "").lower()
    mode = str(trackwork.get("mode") or "")
    gallop_count = 0
    if isinstance(entries, list):
        gallop_count = sum(1 for entry in entries if isinstance(entry, dict) and entry.get("type") == "gallop")
    return {
        "tw_entries_count": float(len(entries)) if isinstance(entries, list) else None,
        "tw_gallop_count": float(gallop_count),
        "tw_flags_count": float(len(flags)) if isinstance(flags, list) else None,
        "tw_confidence_high": int("high" in confidence or "高" in confidence),
        "tw_confidence_low": int("low" in confidence or "低" in confidence),
        "tw_jockey_present": int(bool(trackwork.get("jockey"))),
        "tw_mode_barrier_trial": int("試閘" in mode or "trial" in mode.lower()),
    }


def _forensic_features(horse: dict[str, Any]) -> dict[str, float | int | None]:
    data = horse.get("_data") or {}
    forensic = horse.get("sectional_forensic") or {}
    analytical = horse.get("analytical_breakdown") or {}

    weight_trend = str(data.get("weight_trend") or "")
    weight_span_match = re.search(r"波幅(\d+(?:\.\d+)?)lb", weight_trend)
    weight_span = float(weight_span_match.group(1)) if weight_span_match else None

    best_distance_text = str(horse.get("best_distance") or data.get("best_distance") or "")
    engine_text = str(horse.get("engine_type") or data.get("engine_type") or "")
    running_style = str(horse.get("running_style") or data.get("running_style") or "")
    draw_verdict = str(data.get("draw_verdict") or "")
    position_pi = str(data.get("position_pi") or "")
    finish_level = str(data.get("finish_time_adj_level") or "")
    trackwork_health = str(data.get("trackwork_health") or "")
    margin_trend = str(data.get("margin_trend") or "")
    medical_flags = str(data.get("medical_flags") or "")
    scenario_tags = str(horse.get("scenario_tags") or "")
    race_forgiveness = str(horse.get("race_forgiveness") or "")
    track_bias = str(data.get("track_bias") or "")
    trend_text = str(forensic.get("trend") or "")
    hidden_form = str(analytical.get("hidden_form") or "")
    class_assessment = str(analytical.get("class_assessment") or "")
    pace_adaptation = str(analytical.get("pace_adaptation") or "")

    return {
        "raw_formline_higher_win_count": _coerce_float(data.get("formline_higher_win_count")),
        "raw_formline_same_win_count": _coerce_float(data.get("formline_same_win_count")),
        "raw_formline_lower_win_count": _coerce_float(data.get("formline_lower_win_count")),
        "raw_l400": _coerce_float(data.get("raw_l400") or forensic.get("raw_L400")),
        "raw_finish_time_adj": _coerce_float(data.get("finish_time_adj")),
        "raw_total_starts": _coerce_float(data.get("total_starts")),
        "raw_total_wins": _coerce_float(data.get("total_wins")),
        "raw_last_margin": _coerce_float(data.get("last_margin")),
        "raw_last_finish": _coerce_float(data.get("last_finish")),
        "raw_weight_trend_span": weight_span,
        "flag_best_distance_match": int("今仗" in best_distance_text or "首本路程" in best_distance_text or "最強" in best_distance_text),
        "flag_best_distance_unproven": int("未跑過" in best_distance_text),
        "flag_engine_progressive": int("漸進加速型" in engine_text or "持續衝刺型" in engine_text),
        "flag_engine_steady": int("均速型" in engine_text),
        "flag_engine_fastslow": int("快開慢收型" in engine_text),
        "flag_running_style_front": int("前" in running_style or "領放" in running_style),
        "flag_running_style_back": int("後" in running_style),
        "flag_draw_good": int("✅有利" in draw_verdict),
        "flag_draw_bad": int("❌不利" in draw_verdict),
        "flag_position_up": int("上升" in position_pi or "上升軌" in position_pi),
        "flag_position_down": int("衰退" in position_pi or "微跌" in position_pi),
        "flag_finish_competitive": int("仍具競爭力" in finish_level or "持續快於標準" in finish_level),
        "flag_finish_slow": int("仍偏慢" in finish_level or "明顯落後" in finish_level),
        "flag_energy_up": int("上升" in str(data.get("energy_trend") or "")),
        "flag_energy_down": int("下降" in str(data.get("energy_trend") or "")),
        "flag_l400_up": int("上升" in str(data.get("l400_trend") or "")),
        "flag_l400_down": int("衰退" in str(data.get("l400_trend") or "")),
        "flag_trackwork_slowing": int("操練放緩" in trackwork_health),
        "flag_medical_issue": int(medical_flags not in {"", "N/A"} and "無醫療事故記錄" not in medical_flags),
        "flag_margin_narrowing": int("收窄" in margin_trend),
        "flag_margin_widening": int("擴大" in margin_trend),
        "flag_scenario_drop_class": int("降班" in scenario_tags or "降班" in class_assessment),
        "flag_scenario_hot_pace": int("快步速" in pace_adaptation or "偏快" in pace_adaptation),
        "flag_hidden_form": int(bool(hidden_form)),
        "flag_forgiveness": int(race_forgiveness not in {"", "N/A", "無"}),
        "flag_track_bias_positive": _flag_keywords(track_bias, ["利", "有利", "偏幫"]),
        "flag_track_bias_negative": _flag_keywords(track_bias, ["不利", "偏蝕"]),
        "trend_forensic_wave": int("波動" in trend_text),
    }


def _current_live_snapshot(horse: dict[str, Any]) -> dict[str, Any]:
    auto = horse.get("python_auto") or {}
    feature_scores = auto.get("feature_scores") or {}
    matrix_scores = auto.get("matrix_scores") or {}
    return {
        "current_live_ability": _coerce_float(auto.get("ability_score")),
        "current_live_rank": _coerce_int(auto.get("rank")),
        "current_live_rank_score": _coerce_float(auto.get("rank_score")),
        "current_live_grade": str(auto.get("grade") or ""),
        "current_live_model_pick_status": str(auto.get("model_pick_status") or ""),
        "stored_feature_score_count": len(feature_scores),
        "stored_matrix_score_count": len(matrix_scores),
    }


def build_rows(meeting_roots: list[Path], results_roots: list[Path]) -> tuple[pd.DataFrame, dict[str, Any]]:
    results_index = build_results_index(results_roots)
    meetings = _dedup_meeting_dirs(hk_meeting_dirs(meeting_roots))
    rows: list[dict[str, Any]] = []
    priors = HistoricalPriors()

    coverage = {
        "meetings": 0,
        "races": 0,
        "horses": 0,
        "duplicate_races_skipped": 0,
        "skipped_meetings": [],
    }
    seen_race_keys: set[tuple[str | None, str, int]] = set()

    for meeting_dir in meetings:
        date = meeting_date(meeting_dir)
        result_path = results_index.get(date or "")
        if not result_path:
            coverage["skipped_meetings"].append(str(meeting_dir))
            continue

        actual_results = load_results(result_path)
        meeting_had_race = False
        meeting_venue = venue_from_meeting_dir(meeting_dir)

        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=race_num_from_path):
            race_num = race_num_from_path(logic_path)
            actual_pos = actual_results.get(race_num)
            if not actual_pos:
                continue

            race_key = dedup_race_key(date, meeting_venue, race_num)
            if race_key in seen_race_keys:
                coverage["duplicate_races_skipped"] += 1
                continue
            seen_race_keys.add(race_key)

            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_context = dict(logic.get("race_analysis", {}))
            racecard_snapshot = _load_racecard_snapshot(str(meeting_dir), race_num)
            racecard_info = racecard_snapshot.get("race_info") or {}
            racecard_horses = racecard_snapshot.get("horses") or {}
            venue = _normalize_venue(race_context.get("venue") or racecard_info.get("venue") or meeting_venue)
            track = _normalize_track(race_context.get("track") or race_context.get("surface") or racecard_info.get("track"))
            course = _normalize_course(racecard_info.get("course"))
            distance_token = _distance_token(race_context.get("distance"))
            distance_num = _coerce_int(distance_token)
            race_class_num = _race_class_number(race_context.get("race_class"))
            race_class_label = _race_class_label(race_context.get("race_class") or racecard_info.get("race_class"))
            horses = logic.get("horses") or {}
            field_size = len(horses)
            if not horses:
                continue

            meeting_had_race = True
            coverage["races"] += 1

            for horse_num_text, horse in horses.items():
                horse_num = _coerce_int(horse_num_text)
                if horse_num is None:
                    continue

                finish_pos = _coerce_int(actual_pos.get(horse_num))
                if finish_pos is None:
                    continue

                feature_scores = compute_full_feature_scores(horse, race_context)
                matrix_scores = compute_matrix_scores(feature_scores, CURRENT_MATRIX_FORMULAS)
                ability = compute_ability(matrix_scores, CURRENT_MATRIX_WEIGHTS)
                last_finishes = _parse_last_finishes(horse.get("last_6_finishes"))
                horse_data = horse.get("_data") or {}
                racecard_horse = racecard_horses.get(horse_num) or {}
                horse_id = str(racecard_horse.get("horse_id") or _horse_id_from_name(horse.get("horse_name"))).strip()
                weight_carried = _coerce_float(horse_data.get("weight_carried"))
                days_since_last = _coerce_float(horse.get("days_since_last"))
                barrier = _coerce_int(horse.get("barrier"))
                running_style = horse.get("running_style") or horse_data.get("running_style") or horse.get("engine_type") or ""

                row: dict[str, Any] = {
                    "meeting": str(meeting_dir),
                    "meeting_name": meeting_dir.name,
                    "date": date,
                    "race_number": race_num,
                    "venue": venue,
                    "track": track,
                    "course": course,
                    "distance": distance_token,
                    "distance_num": distance_num,
                    "race_class": str(race_context.get("race_class") or ""),
                    "race_class_label": race_class_label,
                    "race_class_num": race_class_num,
                    "field_size": field_size,
                    "horse_number": horse_num,
                    "horse_name": str(horse.get("horse_name") or ""),
                    "horse_id": horse_id,
                    "jockey": str(horse.get("jockey") or ""),
                    "trainer": str(horse.get("trainer") or ""),
                    "finish_pos": finish_pos,
                    "is_win": int(finish_pos == 1),
                    "is_top3": int(finish_pos <= 3),
                    "is_top4": int(finish_pos <= 4),
                    "barrier": barrier,
                    "weight": _coerce_float(horse.get("weight")),
                    "weight_carried": weight_carried,
                    "days_since_last": days_since_last,
                    "base_rating": _coerce_float(horse.get("base_rating")),
                    "final_rating": _coerce_float(horse.get("final_rating")),
                    "starts": _coerce_float(horse.get("starts")),
                    "wins": _coerce_float(horse.get("wins")),
                    "hk_starts": _coerce_float(horse.get("hk_starts")),
                    "is_debut": int(bool(horse.get("is_debut") or horse.get("debut_runner") or horse.get("career_tag") == "DEBUT")),
                    "is_import": int(bool(horse.get("is_import"))),
                    "current_live_recomputed_ability": ability,
                    "card_age": _coerce_float(racecard_horse.get("age")),
                    "card_rating": _coerce_float(racecard_horse.get("rating")),
                    "card_rating_change": _coerce_float(racecard_horse.get("rating_change")),
                    "card_declared_bodyweight": _coerce_float(racecard_horse.get("declared_bodyweight")),
                    "card_priority_rank": _coerce_float(racecard_horse.get("priority_rank")),
                    "card_has_claim": int(racecard_horse.get("has_claim") or 0),
                    "card_claim_lbs": _coerce_float(racecard_horse.get("claim_lbs")),
                }
                row.update(_gear_flags(racecard_horse.get("gear")))
                row.update(_last_finish_features(last_finishes))
                row.update(_current_live_snapshot(horse))
                row.update(_season_stat_features(horse.get("season_stats")))
                row.update(_trackwork_features(horse.get("trackwork")))
                row.update(_forensic_features(horse))
                row.update(
                    priors.lookup(
                        horse_id=horse_id,
                        jockey=str(horse.get("jockey") or ""),
                        trainer=str(horse.get("trainer") or ""),
                        venue=venue,
                        track=track,
                        distance_num=distance_num,
                        race_class_label=race_class_label,
                        barrier=barrier,
                        weight_carried=weight_carried,
                        days_since_last=days_since_last,
                        running_style=running_style,
                    )
                )

                for name, value in feature_scores.items():
                    row[f"feat_{name}"] = round(float(clip_score(value)), 4)
                for name, value in matrix_scores.items():
                    row[f"matrix_{name}"] = round(float(value), 4)

                rows.append(row)
                coverage["horses"] += 1

        if meeting_had_race:
            coverage["meetings"] += 1

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["date", "meeting_name", "race_number", "horse_number"]).reset_index(drop=True)
    return df, coverage


def build_summary(df: pd.DataFrame, coverage: dict[str, Any]) -> dict[str, Any]:
    if df.empty:
        return {
            "coverage": coverage,
            "columns": [],
            "feature_columns": [],
            "matrix_columns": [],
            "label_summary": {},
            "slice_counts": {},
        }

    feature_columns = [column for column in df.columns if column.startswith("feat_")]
    matrix_columns = [column for column in df.columns if column.startswith("matrix_")]
    slice_counts = (
        df.groupby(["venue", "distance"]).size().reset_index(name="rows").sort_values("rows", ascending=False).to_dict(orient="records")
    )
    label_summary = {
        "win_rate": round(float(df["is_win"].mean()), 6),
        "top3_rate": round(float(df["is_top3"].mean()), 6),
        "top4_rate": round(float(df["is_top4"].mean()), 6),
        "mean_field_size": round(float(df["field_size"].mean()), 4),
    }
    return {
        "coverage": coverage,
        "columns": list(df.columns),
        "feature_columns": feature_columns,
        "matrix_columns": matrix_columns,
        "label_summary": label_summary,
        "slice_counts": slice_counts,
    }


def main() -> int:
    args = parse_args()
    meeting_roots = [Path(path) for path in args.meeting_root] or default_meeting_roots()
    results_roots = [Path(path) for path in args.results_root] or default_results_roots()
    output_path = Path(args.output)
    summary_path = Path(args.summary_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    df, coverage = build_rows(meeting_roots, results_roots)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    summary = build_summary(df, coverage)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"dataset_rows={len(df)}")
    print(f"dataset_path={output_path}")
    print(f"summary_path={summary_path}")
    print(json.dumps(summary["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
