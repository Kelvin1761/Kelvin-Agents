#!/usr/bin/env python3
"""
AU Wong Choi Comprehensive Improvement Shadow Test
====================================================
Tests multiple targeted improvement variants against the full archive.
Each variant patches specific engine components and measures impact.

Variants tested:
  V1: Matrix weight rebalancing (stability down, class_weight up, form_line up)
  V2: Form score going adjustment + finer placing granularity
  V3: Sectional PI averaging 2→4 entries + enable trial_extreme_bonus
  V4: Pace map running-style × barrier interaction
  V5: Barrier bias expansion (compute from archive data)
  V6: Combined V1+V2+V3 (safe subset)
  V7: Class weight baseline 3%→8% (surgical, not brute)

Usage:
    python3 au_comprehensive_improvement_test.py
    python3 au_comprehensive_improvement_test.py --output-md path/to/output.md
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]

import sys
sys.path = [p for p in sys.path if p]
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)
from au_sip_tester import (
    evaluate_races,
    report_summary,
    delta_report,
    new_bucket,
    rate,
    pct,
)
from re_score_archive import build_field_summary
from scoring import clip_score

import engine_core
import matrix_mapper
import scoring
from engine_core import RacingEngine

OUTPUT_MD = PROJECT_ROOT / "2026-05-31 AU Comprehensive Improvement Test.md"


# ── Barrier stats from historical CSV ─────────────────────

def _compute_barrier_stats_from_csv() -> dict:
    """Compute barrier win/place rates from historical results CSV."""
    barrier_stats = defaultdict(lambda: {"runs": 0, "wins": 0, "places": 0})
    try:
        with HISTORICAL_RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                barrier = parse_int(row.get("Barrier"))
                pos = parse_int(row.get("Pos"))
                if barrier is None or pos is None:
                    continue
                key = barrier
                barrier_stats[key]["runs"] += 1
                if pos == 1:
                    barrier_stats[key]["wins"] += 1
                if pos <= 3:
                    barrier_stats[key]["places"] += 1
    except Exception:
        pass
    return dict(barrier_stats)


def _compute_venue_barrier_stats_from_csv() -> dict:
    """Compute per-venue barrier win/place rates from historical results CSV."""
    venue_stats = defaultdict(lambda: defaultdict(lambda: {"runs": 0, "wins": 0, "places": 0}))
    try:
        with HISTORICAL_RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                barrier = parse_int(row.get("Barrier"))
                pos = parse_int(row.get("Pos"))
                track = str(row.get("Track", "")).strip().lower()
                if barrier is None or pos is None or not track:
                    continue
                venue_stats[track][barrier]["runs"] += 1
                if pos == 1:
                    venue_stats[track][barrier]["wins"] += 1
                if pos <= 3:
                    venue_stats[track][barrier]["places"] += 1
    except Exception:
        pass
    return dict(venue_stats)


# ── Loading ─────────────────────────────────────────────

def load_archive_races() -> list[dict]:
    """Load all archive races with actual results for backtest."""
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        logic_files = sorted(
            meeting_dir.glob("Race_*_Logic.json"),
            key=lambda p: parse_int(p.stem.split("_")[1], 999),
        )
        if not logic_files:
            continue
        sample_logic = json.loads(logic_files[0].read_text(encoding="utf-8"))
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = detect_meeting_track(meeting_dir, sample_logic)
        if not meeting_date or not meeting_track:
            continue
        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis") or {}
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(
                logic_path.stem.split("_")[1]
            )
            rows_for_race = choose_track_rows(
                historical_results.get((meeting_date, race_no), []), meeting_track
            )
            if not rows_for_race:
                continue
            race_lookup = {row["horse_slug"]: row for row in rows_for_race}
            race_context = dict(race_analysis)
            race_context["field_summary"] = build_field_summary(logic.get("horses", {}))
            horses = []
            for horse_num, horse in (logic.get("horses") or {}).items():
                result_row = race_lookup.get(
                    normalize_horse_name(horse.get("horse_name"))
                )
                if not result_row:
                    continue
                engine = RacingEngine(
                    horse,
                    race_context,
                    horse.get("_data", {}).get("facts_section", ""),
                    facts_path=str(meeting_dir / f"{meeting_date}_runtime.md"),
                )
                auto = engine.analyze_horse()
                horses.append(
                    {
                        "horse_number": parse_int(horse_num) or 999,
                        "horse_name": str(horse.get("horse_name") or "").strip(),
                        "rank_score": float(
                            auto.get("rank_score")
                            or auto.get("ability_score")
                            or 0.0
                        ),
                        "ability_score": float(auto.get("ability_score") or 0.0),
                        "actual_pos": int(result_row["pos"]),
                        "condition_bucket": _condition_bucket(
                            result_row.get("condition") or ""
                        ),
                        "risk_flags": list(auto.get("risk_flags") or []),
                        "matrix": auto.get("matrix") or {},
                        "matrix_scores": auto.get("matrix_scores") or {},
                        "feature_scores": auto.get("feature_scores") or {},
                        "barrier": parse_int(horse.get("barrier")),
                        "going": race_analysis.get("going", ""),
                        "meeting_track": meeting_track,
                        "jockey": horse.get("jockey", ""),
                        "trainer": horse.get("trainer", ""),
                        "data": horse.get("_data")
                        if isinstance(horse.get("_data"), dict)
                        else {},
                        "speed_map": race_analysis.get("speed_map")
                        if isinstance(race_analysis.get("speed_map"), dict)
                        else {},
                        "settled_pattern": (
                            horse.get("_data") or {}
                        ).get("recent_settled_pattern_line", ""),
                        # Raw dict for re-running engine
                        "_horse_dict": horse,
                    }
                )
            if len(horses) < 4:
                continue
            races.append(
                {
                    "meeting": meeting_dir.name,
                    "race_no": race_no,
                    "meeting_track": meeting_dir.name,
                    "race_class_bucket": _race_class_bucket(
                        race_analysis.get("race_class")
                    ),
                    "field_size_bucket": _field_size_bucket(len(horses)),
                    "condition_bucket": horses[0]["condition_bucket"],
                    "going": race_analysis.get("going", ""),
                    "race_class": race_analysis.get("race_class", ""),
                    "field_count": len(horses),
                    "horses": horses,
                    # Raw data for re-running engine
                    "horses_raw": [
                        {
                            "horse_dict": h["_horse_dict"],
                            "horse_number": h["horse_number"],
                            "actual_pos": h["actual_pos"],
                            "condition_bucket": h["condition_bucket"],
                            "going": h["going"],
                            "meeting_track": h["meeting_track"],
                            "barrier": h["barrier"],
                        }
                        for h in horses
                    ],
                    "race_analysis_raw": dict(race_analysis),
                    "speed_map_raw": race_analysis.get("speed_map")
                    if isinstance(race_analysis.get("speed_map"), dict)
                    else {},
                }
            )
    return races


def _condition_bucket(condition: str) -> str:
    c = str(condition).lower()
    if "heavy" in c:
        return "Heavy"
    if "soft" in c:
        return "Soft"
    return "Good/Firm"


def _race_class_bucket(cls: str) -> str:
    c = str(cls).lower()
    if "group 1" in c or "g1" in c:
        return "Group 1"
    if "group 2" in c or "group 3" in c or "g2" in c or "g3" in c:
        return "Group 2/3"
    if "listed" in c:
        return "Listed"
    if "maiden" in c or "mdn" in c:
        return "Maiden"
    if "bm" in c:
        m = re.search(r"bm(\d+)", c)
        if m:
            n = int(m.group(1))
            if n >= 88:
                return "BM88+"
            if n >= 72:
                return "BM72-84"
        return "BM58-70"
    return "Other"


def _field_size_bucket(n: int) -> str:
    if n <= 8:
        return "Field <=8"
    if n <= 12:
        return "Field 9-12"
    return "Field 13+"


def _running_style_from_pattern(pattern: str) -> str:
    p = str(pattern).lower()
    if not p or p == "none":
        return "unknown"
    if any(x in p for x in ["lead", "front", "prominent"]):
        return "front"
    if any(x in p for x in ["mid", "stalker"]):
        return "mid"
    if any(x in p for x in ["back", "clos", "rear"]):
        return "back"
    return "unknown"


# ── Variant patchers ───────────────────────────────────

@contextmanager
def patched_engine(variant: str, barrier_stats: dict, venue_barrier_stats: dict):
    """Context manager that patches engine for a specific variant."""
    # Save originals
    saved_matrix_weights = dict(scoring.MATRIX_WEIGHTS)
    saved_class_micro = dict(scoring.CLASS_MICRO_WEIGHTS)
    saved_sectional_micro = dict(scoring.SECTIONAL_MICRO_WEIGHTS)
    saved_fit_micro = dict(scoring.FIT_MICRO_WEIGHTS)
    saved_pace_micro = dict(scoring.PACE_MICRO_WEIGHTS)
    saved_place_weights = dict(scoring.PLACE_TIGHTENING_FEATURE_WEIGHTS)
    saved_engine_weights = engine_core.get_dynamic_matrix_weights
    saved_scoring_weights = scoring.get_dynamic_matrix_weights
    saved_formulas = deepcopy(matrix_mapper.MATRIX_FORMULAS)

    try:
        if variant == "V1_matrix_rebalance":
            # Stability 0.28→0.19, class_weight 0.03→0.12, form_line 0.06→0.13
            scoring.MATRIX_WEIGHTS["stability"] = 0.19
            scoring.MATRIX_WEIGHTS["class_weight"] = 0.12
            scoring.MATRIX_WEIGHTS["form_line"] = 0.13
            # Redistribute: take from stability (0.09) and form_line (-0.07)
            # Net: stability -0.09, class_weight +0.09, form_line +0.07
            # Compensate by reducing race_shape slightly
            scoring.MATRIX_WEIGHTS["race_shape"] = 0.18

        elif variant == "V2_form_going":
            # Patch form_score to include going adjustment
            _orig_form = engine_core.RacingEngine._form_score

            def _form_score_with_going(self):
                starts = self._career_starts()
                if starts == 0:
                    self.reason_codes.append("debut_form_neutral")
                    return 60, "初出馬無正式賽績，近績分按保守 60 分處理。", "career_tag"
                entries = self._official_entries()
                if not entries:
                    return 60, "缺乏正式賽績，近績分按 60 分處理。", "career_tag"
                today_class = self.race_context.get("race_class", "")
                today_tier = self._get_class_tier(today_class)
                today_going = str(self.race_context.get("going", "")).lower()
                total_weighted_score = 0.0
                total_applied_weights = 0.0
                notes = []
                for i, entry in enumerate(entries[:4]):
                    place = parse_float(entry.get("placing"))
                    if place is None:
                        continue
                    # Finer placing granularity: 4th≠5th
                    if place == 1:
                        base_pts = 100
                    elif place == 2:
                        base_pts = 85
                    elif place == 3:
                        base_pts = 75
                    elif place == 4:
                        base_pts = 65
                    elif place <= 5:
                        base_pts = 55
                    else:
                        base_pts = 40
                    decay = [1.0, 0.8, 0.6, 0.4][min(i, 3)]
                    entry_tier = self._get_class_tier(entry.get("class", ""))
                    delta = today_tier - entry_tier
                    if delta >= 2:
                        class_mult = 1.2
                    elif delta == 1:
                        class_mult = 1.1
                    elif delta == 0:
                        class_mult = 1.0
                    elif delta == -1:
                        class_mult = 0.85
                    else:
                        class_mult = 0.7
                    # Going adjustment
                    entry_going = str(entry.get("going", "")).lower()
                    going_mult = 1.0
                    if today_going and entry_going:
                        today_wet = "soft" in today_going or "heavy" in today_going
                        entry_wet = "soft" in entry_going or "heavy" in entry_going
                        if today_wet and not entry_wet:
                            going_mult = 0.92  # Penalty: proven on dry, not wet
                        elif not today_wet and entry_wet:
                            going_mult = 0.95  # Mild penalty: proven on wet, today dry
                        elif today_wet and entry_wet:
                            going_mult = 1.05  # Bonus: both wet
                    race_score = base_pts * class_mult * going_mult
                    total_weighted_score += race_score * decay
                    total_applied_weights += decay
                avg_score = (
                    total_weighted_score / total_applied_weights
                    if total_applied_weights > 0
                    else 60
                )
                score = min(100.0, max(0.0, avg_score))
                if self._is_maiden_race():
                    trial_count = int(
                        parse_float(self.data.get("trial_count")) or 0
                    )
                    trial_top3 = int(
                        parse_float(self.data.get("trial_top3_count")) or 0
                    )
                    if trial_count >= 4 and trial_top3 >= 3:
                        score += 5
                    elif trial_count >= 3 and trial_top3 >= 2:
                        score += 3
                note_str = "；".join(notes) if notes else "近績一般"
                return (
                    score,
                    f"form+going adjusted, {note_str}。近績分 {clip_score(score):.1f}。",
                    "recent_form+class_weighted+going",
                )

            engine_core.RacingEngine._form_score = _form_score_with_going

        elif variant == "V3_sectional_pi_avg":
            # Change PI averaging from 2 to 4 entries
            saved_pi_entries = scoring.SECTIONAL_MICRO_WEIGHTS.get(
                "pi_avg_entries", 2
            )
            scoring.SECTIONAL_MICRO_WEIGHTS["pi_avg_entries"] = 4
            # Enable trial_extreme_bonus (was 0.0)
            scoring.SECTIONAL_MICRO_WEIGHTS["trial_extreme_bonus"] = 8.0

            # Patch sectional breakdown to use 4 entries
            _orig_sb = engine_core.RacingEngine._sectional_breakdown

            def _sectional_breakdown_v3(self):
                if self._sectional_breakdown_cache is not None:
                    return self._sectional_breakdown_cache
                entries = self._official_entries()
                w = scoring.SECTIONAL_MICRO_WEIGHTS
                total_score = w.get("base", 40.0)
                notes = [f"基礎分 {total_score} 分"]
                pi_from_entries = []
                for entry in entries:
                    pi_val = parse_float(entry.get("pi"))
                    if pi_val is not None:
                        pi_from_entries.append(pi_val)
                if not pi_from_entries:
                    tw_trial = self.data.get("timing_trial_600m_avg_speed")
                    if tw_trial and tw_trial > 0:
                        trial_l600 = 600.0 / tw_trial
                        if trial_l600 <= 33.5:
                            total_score += w.get("trial_extreme_bonus", 8.0)
                            notes.append(
                                f"試閘 L600 ({trial_l600:.1f}s) 極速補償 (+{w.get('trial_extreme_bonus', 8.0)})"
                            )
                        elif trial_l600 <= 34.0:
                            total_score += w.get("trial_excellent_bonus", 0.0)
                        elif trial_l600 <= 34.8:
                            total_score += w.get("trial_pass_bonus", 3.97)
                else:
                    n = min(4, len(pi_from_entries))
                    recent_pi = sum(pi_from_entries[:n]) / n
                    avg_pi = sum(pi_from_entries) / len(pi_from_entries)
                    max_pi = max(pi_from_entries)
                    if avg_pi >= 4.0:
                        total_score += w.get("pi_extreme_bonus", 28.1)
                    elif avg_pi >= 2.0:
                        total_score += w.get("pi_excellent_bonus", 20.0)
                    elif avg_pi >= 0.0:
                        total_score += w.get("pi_pass_bonus", 3.64)
                    tw_best = self.data.get("timing_600m_best_speed")
                    if tw_best and tw_best > 0:
                        best_l600 = 600.0 / tw_best
                        race_dist = self._distance_from_text(
                            self.race_context.get("distance", "")
                        )
                        if race_dist and race_dist >= 600:
                            std_l600 = engine_core._lookup_standard_l600(
                                self._current_venue_name(), race_dist
                            )
                            if std_l600 and std_l600 > 0:
                                delta = best_l600 - std_l600
                                if delta <= -0.6:
                                    total_score += w.get("l600_extreme_bonus", 15.07)
                                elif delta <= -0.3:
                                    total_score += w.get("l600_excellent_bonus", 3.64)
                    if max_pi >= 6.0:
                        total_score += w.get("peak_pi_bonus", 1.1)
                    if recent_pi > avg_pi + 2.0:
                        total_score += w.get("trend_up_bonus", 1.93)
                    elif recent_pi < avg_pi - 3.0:
                        total_score = max(
                            0, total_score + w.get("trend_down_pen", -5.56)
                        )
                    if avg_pi > 0 and sum(
                        1 for e in entries[:3] if (parse_float(e.get("placing")) or 99) <= 4
                    ) > 0:
                        total_score += w.get("realization_bonus", 6.64)
                    elif avg_pi > 2.0 and self._forgiveness_count() >= 1:
                        total_score += w.get("forgiveness_bonus", 9.89)
                total_score = min(100.0, max(0.0, total_score))
                self._sectional_breakdown_cache = {
                    "score": total_score,
                    "notes": "；".join(notes) if notes else "-",
                    "label": "V3: Base 40 + PI(avg4)/L600",
                }
                return self._sectional_breakdown_cache

            engine_core.RacingEngine._sectional_breakdown = _sectional_breakdown_v3

        elif variant == "V4_pace_running_style":
            # Add running-style × barrier interaction to pace_map_score
            _orig_pace = engine_core.RacingEngine._pace_map_score

            def _pace_map_score_v4(self):
                base_score, base_note, base_source = _orig_pace(self)
                barrier = parse_int(self.horse_data.get("barrier"))
                if barrier is None:
                    return base_score, base_note, base_source
                settled = str(
                    (self.horse_data.get("_data") or {}).get(
                        "recent_settled_pattern_line", ""
                    )
                    or ""
                ).lower()
                style = "unknown"
                if any(x in settled for x in ["lead", "front", "prominent"]):
                    style = "front"
                elif any(x in settled for x in ["mid", "stalker"]):
                    style = "mid"
                elif any(x in settled for x in ["back", "clos", "rear"]):
                    style = "back"
                field_count = int(
                    (self.race_context.get("field_summary") or {}).get("count", 10)
                )
                adjustment = 0.0
                if style == "front" and barrier >= 10:
                    adjustment = -1.5  # Front-runner wide = bad
                    if field_count >= 13:
                        adjustment = -2.5
                elif style == "back" and barrier <= 3:
                    adjustment = +0.8  # Back-runner inside = mild advantage
                elif style == "back" and barrier >= 12:
                    adjustment = -0.5  # Back-runner wide = mild penalty
                new_score = max(0, min(100, base_score + adjustment))
                note = base_note
                if abs(adjustment) >= 0.5:
                    note += f"；[V4] 跑法×檔位修正 {adjustment:+.1f}"
                return new_score, note, base_source + "+running_style"

            engine_core.RacingEngine._pace_map_score = _pace_map_score_v4

        elif variant == "V5_barrier_expansion":
            # Expand barrier bias to use computed stats from archive data
            venue_adj = {}
            for venue, stats in venue_barrier_stats.items():
                adj = {}
                for barrier, s in stats.items():
                    if s["runs"] >= 15:
                        win_rate = s["wins"] / s["runs"]
                        expected = 1.0 / 14  # approximate
                        adj[barrier] = round((win_rate - expected) * 100 * 1.2, 1)
                if adj:
                    venue_adj[venue] = adj

            _orig_barrier = engine_core.RacingEngine._barrier_bias_adjustment

            def _barrier_bias_v4(self):
                barrier = parse_int(self.horse_data.get("barrier"))
                if barrier is None:
                    return 0.0
                venue = self._current_venue_name().lower().strip()
                adj_map = venue_adj.get(venue, {})
                if not adj_map:
                    return 0.0
                adj = adj_map.get(barrier, 0.0)
                field_count = int(
                    (self.race_context.get("field_summary") or {}).get("count", 10)
                )
                if field_count >= 13:
                    adj *= 1.5
                return max(-5.0, min(5.0, adj))

            engine_core.RacingEngine._barrier_bias_adjustment = _barrier_bias_v4

        elif variant == "V6_combined_safe":
            # V1 matrix rebalance + V2 form going + V3 sectional
            scoring.MATRIX_WEIGHTS["stability"] = 0.19
            scoring.MATRIX_WEIGHTS["class_weight"] = 0.12
            scoring.MATRIX_WEIGHTS["form_line"] = 0.13
            scoring.MATRIX_WEIGHTS["race_shape"] = 0.18
            scoring.SECTIONAL_MICRO_WEIGHTS["trial_extreme_bonus"] = 8.0

            # Apply V2 form patch
            _orig_form = engine_core.RacingEngine._form_score

            def _form_score_v6(self):
                starts = self._career_starts()
                if starts == 0:
                    self.reason_codes.append("debut_form_neutral")
                    return 60, "初出馬", "career_tag"
                entries = self._official_entries()
                if not entries:
                    return 60, "缺乏賽績", "career_tag"
                today_class = self.race_context.get("race_class", "")
                today_tier = self._get_class_tier(today_class)
                today_going = str(self.race_context.get("going", "")).lower()
                tw = 0.0
                aw = 0.0
                for i, entry in enumerate(entries[:4]):
                    place = parse_float(entry.get("placing"))
                    if place is None:
                        continue
                    if place == 1:
                        bp = 100
                    elif place == 2:
                        bp = 85
                    elif place == 3:
                        bp = 75
                    elif place == 4:
                        bp = 65
                    elif place <= 5:
                        bp = 55
                    else:
                        bp = 40
                    d = [1.0, 0.8, 0.6, 0.4][min(i, 3)]
                    et = self._get_class_tier(entry.get("class", ""))
                    dt = today_tier - et
                    cm = {2: 1.2, 1: 1.1, 0: 1.0, -1: 0.85}.get(dt, 0.7 if dt < -1 else 1.2)
                    eg = str(entry.get("going", "")).lower()
                    gm = 1.0
                    if today_going and eg:
                        tw_wet = "soft" in today_going or "heavy" in today_going
                        ew_wet = "soft" in eg or "heavy" in eg
                        if tw_wet and not ew_wet:
                            gm = 0.92
                        elif not tw_wet and ew_wet:
                            gm = 0.95
                        elif tw_wet and ew_wet:
                            gm = 1.05
                    tw += bp * cm * gm * d
                    aw += d
                avg = tw / aw if aw > 0 else 60
                score = min(100.0, max(0.0, avg))
                if self._is_maiden_race():
                    tc = int(parse_float(self.data.get("trial_count")) or 0)
                    tt3 = int(parse_float(self.data.get("trial_top3_count")) or 0)
                    if tc >= 4 and tt3 >= 3:
                        score += 5
                    elif tc >= 3 and tt3 >= 2:
                        score += 3
                return score, f"V6 form+going adj {score:.1f}", "form_v6"

            engine_core.RacingEngine._form_score = _form_score_v6

            # Apply V3 sectional patch (simplified)
            _orig_sb = engine_core.RacingEngine._sectional_breakdown

            def _sectional_breakdown_v6(self):
                if self._sectional_breakdown_cache is not None:
                    return self._sectional_breakdown_cache
                entries = self._official_entries()
                w = scoring.SECTIONAL_MICRO_WEIGHTS
                ts = w.get("base", 40.0)
                pi_vals = []
                for e in entries:
                    pv = parse_float(e.get("pi"))
                    if pv is not None:
                        pi_vals.append(pv)
                if not pi_vals:
                    tt = self.data.get("timing_trial_600m_avg_speed")
                    if tt and tt > 0:
                        tl = 600.0 / tt
                        if tl <= 33.5:
                            ts += w.get("trial_extreme_bonus", 8.0)
                        elif tl <= 34.0:
                            ts += 3.0
                        elif tl <= 34.8:
                            ts += w.get("trial_pass_bonus", 3.97)
                else:
                    n = min(4, len(pi_vals))
                    rpi = sum(pi_vals[:n]) / n
                    api = sum(pi_vals) / len(pi_vals)
                    mpi = max(pi_vals)
                    if api >= 4.0:
                        ts += w.get("pi_extreme_bonus", 28.1)
                    elif api >= 2.0:
                        ts += w.get("pi_excellent_bonus", 20.0)
                    elif api >= 0.0:
                        ts += w.get("pi_pass_bonus", 3.64)
                    tb = self.data.get("timing_600m_best_speed")
                    if tb and tb > 0:
                        bl = 600.0 / tb
                        rd = self._distance_from_text(self.race_context.get("distance", ""))
                        if rd and rd >= 600:
                            sl = engine_core._lookup_standard_l600(self._current_venue_name(), rd)
                            if sl and sl > 0:
                                dlt = bl - sl
                                if dlt <= -0.6:
                                    ts += w.get("l600_extreme_bonus", 15.07)
                                elif dlt <= -0.3:
                                    ts += w.get("l600_excellent_bonus", 3.64)
                    if mpi >= 6.0:
                        ts += w.get("peak_pi_bonus", 1.1)
                    if rpi > api + 2.0:
                        ts += w.get("trend_up_bonus", 1.93)
                    elif rpi < api - 3.0:
                        ts = max(0, ts + w.get("trend_down_pen", -5.56))
                    if api > 0 and sum(1 for e in entries[:3] if (parse_float(e.get("placing")) or 99) <= 4) > 0:
                        ts += w.get("realization_bonus", 6.64)
                    elif api > 2.0 and self._forgiveness_count() >= 1:
                        ts += w.get("forgiveness_bonus", 9.89)
                ts = min(100.0, max(0.0, ts))
                self._sectional_breakdown_cache = {"score": ts, "notes": "-", "label": "V6"}
                return self._sectional_breakdown_cache

            engine_core.RacingEngine._sectional_breakdown = _sectional_breakdown_v6

        elif variant == "V7_class_weight_8pct":
            # Surgical: only change class_weight baseline from 3% to 8%
            scoring.MATRIX_WEIGHTS["class_weight"] = 0.08
            # Compensate by reducing stability slightly
            scoring.MATRIX_WEIGHTS["stability"] = 0.24

        yield

    finally:
        # Restore all originals
        scoring.MATRIX_WEIGHTS.clear()
        scoring.MATRIX_WEIGHTS.update(saved_matrix_weights)
        scoring.CLASS_MICRO_WEIGHTS.clear()
        scoring.CLASS_MICRO_WEIGHTS.update(saved_class_micro)
        scoring.SECTIONAL_MICRO_WEIGHTS.clear()
        scoring.SECTIONAL_MICRO_WEIGHTS.update(saved_sectional_micro)
        scoring.FIT_MICRO_WEIGHTS.clear()
        scoring.FIT_MICRO_WEIGHTS.update(saved_fit_micro)
        scoring.PACE_MICRO_WEIGHTS.clear()
        scoring.PACE_MICRO_WEIGHTS.update(saved_pace_micro)
        scoring.PLACE_TIGHTENING_FEATURE_WEIGHTS.clear()
        scoring.PLACE_TIGHTENING_FEATURE_WEIGHTS.update(saved_place_weights)
        matrix_mapper.MATRIX_FORMULAS.clear()
        matrix_mapper.MATRIX_FORMULAS.update(saved_formulas)
        engine_core.get_dynamic_matrix_weights = saved_engine_weights
        scoring.get_dynamic_matrix_weights = saved_scoring_weights
        # Restore patched methods
        try:
            engine_core.RacingEngine._form_score = _orig_form
        except Exception:
            pass
        try:
            engine_core.RacingEngine._sectional_breakdown = _orig_sb
        except Exception:
            pass
        try:
            engine_core.RacingEngine._pace_map_score = _orig_pace
        except Exception:
            pass
        try:
            engine_core.RacingEngine._barrier_bias_adjustment = _orig_barrier
        except Exception:
            pass


def _rerun_races(races: list[dict], variant: str, barrier_stats: dict, venue_barrier_stats: dict) -> list[dict]:
    """Re-run engine on all races with variant patches applied.
    
    Uses the original horse dict from Logic.json (stored in race["horses_raw"])
    to re-create RacingEngine, just like the existing shadow test framework.
    """
    rerun_races = []
    for race in races:
        horses = []
        horses_raw = race.get("horses_raw", [])
        for h_raw in horses_raw:
            horse_dict = h_raw["horse_dict"]
            horse_num = h_raw["horse_number"]
            actual_pos = h_raw["actual_pos"]
            condition_bucket = h_raw["condition_bucket"]
            going = h_raw["going"]
            meeting_track = h_raw["meeting_track"]
            barrier = h_raw["barrier"]
            race_context = dict(race.get("race_analysis_raw", {}))
            race_context["field_summary"] = {"count": race["field_count"]}
            engine = RacingEngine(
                horse_dict,
                race_context,
                horse_dict.get("_data", {}).get("facts_section", ""),
                facts_path="",
            )
            auto = engine.analyze_horse()
            horses.append({
                "horse_number": horse_num,
                "horse_name": str(horse_dict.get("horse_name") or "").strip(),
                "rank_score": float(auto.get("rank_score") or auto.get("ability_score") or 0.0),
                "ability_score": float(auto.get("ability_score") or 0.0),
                "actual_pos": actual_pos,
                "condition_bucket": condition_bucket,
                "risk_flags": list(auto.get("risk_flags") or []),
                "matrix": auto.get("matrix") or {},
                "matrix_scores": auto.get("matrix_scores") or {},
                "feature_scores": auto.get("feature_scores") or {},
                "barrier": barrier,
                "going": going,
                "meeting_track": meeting_track,
                "jockey": horse_dict.get("jockey", ""),
                "trainer": horse_dict.get("trainer", ""),
                "data": horse_dict.get("_data") if isinstance(horse_dict.get("_data"), dict) else {},
                "speed_map": race.get("speed_map_raw", {}),
            })
        if len(horses) >= 4:
            rerun_races.append({
                "meeting": race["meeting"],
                "race_no": race["race_no"],
                "meeting_track": race["meeting_track"],
                "race_class_bucket": race["race_class_bucket"],
                "field_size_bucket": race["field_size_bucket"],
                "condition_bucket": race["condition_bucket"],
                "going": race["going"],
                "race_class": race["race_class"],
                "field_count": race["field_count"],
                "horses": horses,
            })
    return rerun_races


def _summary_block(label: str, summary: dict, delta: dict | None = None) -> list[str]:
    lines = [
        f"## {label}",
        "",
        f"- Races: `{summary['races']}`",
        f"- Champion: `{summary['champion']}`",
        f"- Gold: `{summary['gold']}`",
        f"- Good: `{summary['good']}`",
        f"- Pass: `{summary['pass']}`",
        f"- Top3 Place: `{summary['top3_place']}`",
        f"- 0-hit: `{summary['0hit']}`",
        f"- 1-hit: `{summary['1hit']}`",
        f"- 2-hit: `{summary['2hit']}`",
        f"- 3-hit: `{summary['3hit']}`",
    ]
    if delta:
        lines.append(
            f"- Delta: gold `{delta['gold_delta']:+.1f}pp`, good `{delta['good_delta']:+.1f}pp`, "
            f"pass `{delta['pass_delta']:+.1f}pp`, place `{delta['place_delta']:+.1f}pp`, "
            f"0-hit `{delta['0hit_delta']:+d}`, 1-hit `{delta['1hit_delta']:+d}`"
        )
    lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="AU comprehensive improvement shadow test")
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    args = parser.parse_args()

    print("📦 Loading archive races...")
    races = load_archive_races()
    print(f"   Loaded {len(races)} races")

    print("📊 Computing barrier stats from historical CSV...")
    barrier_stats = _compute_barrier_stats_from_csv()
    venue_barrier_stats = _compute_venue_barrier_stats_from_csv()
    print(f"   {len(barrier_stats)} barrier buckets, {len(venue_barrier_stats)} venues")

    # Baseline
    print("\n📊 BASELINE (current engine, runtime re-score):")
    bl_overall, bl_cond, bl_class, bl_field = evaluate_races(races, "Baseline")
    bl_summary = report_summary(bl_overall, "Baseline")
    print(f"  Races: {bl_summary['races']}  |  Gold: {bl_summary['gold']}  |  Good: {bl_summary['good']}  |  Pass: {bl_summary['pass']}")
    print(f"  Place: {bl_summary['top3_place']}  |  0H: {bl_summary['0hit']}  |  1H: {bl_summary['1hit']}  |  2H: {bl_summary['2hit']}  |  3H: {bl_summary['3hit']}")

    variants = [
        ("V1_matrix_rebalance", "V1: Matrix rebalance (stability↓ class_weight↑ form_line↑)"),
        ("V2_form_going", "V2: Form score going adjustment + finer placing"),
        ("V3_sectional_pi_avg", "V3: Sectional PI avg 2→4 + trial extreme bonus"),
        ("V4_pace_running_style", "V4: Pace map running-style × barrier interaction"),
        ("V5_barrier_expansion", "V5: Barrier bias expansion from archive data"),
        ("V6_combined_safe", "V6: Combined V1+V2+V3 (safe subset)"),
        ("V7_class_weight_8pct", "V7: class_weight 3%→8% (surgical)"),
    ]

    results_md = [
        "# AU Wong Choi Comprehensive Improvement Shadow Test",
        "",
        "Each variant is tested independently against the full archive.",
        "Only variants showing **positive Pass delta AND reduced 0-hit** should be considered.",
        "",
        f"Archive: `{len(races)}` races from `Wong Choi Horse Race Analysis/AU_Racing/`",
        "",
    ]

    for variant_key, variant_name in variants:
        print(f"\n🧪 Testing {variant_name}...")
        try:
            with patched_engine(variant_key, barrier_stats, venue_barrier_stats):
                variant_races = _rerun_races(races, variant_key, barrier_stats, venue_barrier_stats)
            ov, co, cl, fi = evaluate_races(variant_races, variant_key)
            summary = report_summary(ov, variant_key)
            delta = delta_report(bl_overall, ov)

            print(f"  Races: {summary['races']}  |  Gold: {summary['gold']}  |  Good: {summary['good']}  |  Pass: {summary['pass']}")
            print(f"  Place: {summary['top3_place']}  |  0H: {summary['0hit']}  |  1H: {summary['1hit']}")
            print(f"  ΔGold: {delta['gold_delta']:+.1f}pp  |  ΔGood: {delta['good_delta']:+.1f}pp  |  ΔPass: {delta['pass_delta']:+.1f}pp  |  ΔPlace: {delta['place_delta']:+.1f}pp  |  Δ0H: {delta['0hit_delta']:+d}")

            verdict = "✅ PASS" if delta["pass_delta"] > 0 and delta["0hit_delta"] <= 0 else "❌ FAIL"
            if delta["pass_delta"] > 0 and delta["0hit_delta"] > 0:
                verdict = "⚠️ MIXED"
            print(f"  Verdict: {verdict}")

            results_md.append(f"### {variant_name}")
            results_md.append("")
            results_md.append(f"**Verdict: {verdict}**")
            results_md.append("")
            results_md.append(_md_table(summary))
            results_md.append("")
            results_md.append(_md_delta_table(delta))
            results_md.append("")

        except Exception as exc:
            print(f"  ❌ ERROR: {exc}")
            import traceback
            traceback.print_exc()
            results_md.append(f"### {variant_name}")
            results_md.append("")
            results_md.append(f"**ERROR: {exc}**")
            results_md.append("")

    results_md.append("---")
    results_md.append("")
    results_md.append("## Summary Table")
    results_md.append("")
    results_md.append("| Variant | Pass Δ | Gold Δ | Good Δ | Place Δ | 0-hit Δ | Verdict |")
    results_md.append("|---|---:|---:|---:|---:|---:|---|")

    output_path = Path(args.output_md)
    output_path.write_text("\n".join(results_md), encoding="utf-8")
    print(f"\n📄 Report written: {output_path}")
    return 0


def _md_table(s):
    return (
        f"| Metric | Value |\n"
        f"|---|---|\n"
        f"| Races | {s['races']} |\n"
        f"| Champion | {s['champion']} |\n"
        f"| Gold | {s['gold']} |\n"
        f"| Good | {s['good']} |\n"
        f"| Pass | {s['pass']} |\n"
        f"| Top3 Place | {s['top3_place']} |\n"
        f"| 0-hit | {s['0hit']} |\n"
        f"| 1-hit | {s['1hit']} |\n"
        f"| 2-hit | {s['2hit']} |\n"
        f"| 3-hit | {s['3hit']} |"
    )


def _md_delta_table(d):
    return (
        f"| ΔGold | ΔGood | ΔPass | ΔPlace | Δ0-hit | Δ1-hit |\n"
        f"|---:|---:|---:|---:|---:|---:|\n"
        f"| {d['gold_delta']:+.1f}pp | {d['good_delta']:+.1f}pp | {d['pass_delta']:+.1f}pp | {d['place_delta']:+.1f}pp | {d['0hit_delta']:+d} | {d['1hit_delta']:+d} |"
    )


if __name__ == "__main__":
    raise SystemExit(main())
