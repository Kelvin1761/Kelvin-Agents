#!/usr/bin/env python3
"""
AU SIP Tester — Incremental improvement test harness.
Applies post-hoc score adjustments for each SIP and measures impact against archive.
Each SIP is tested independently so we can verify positive results before committing.

Usage:
    python3 au_sip_tester.py              # Run all SIPs, print comparison
    python3 au_sip_tester.py --sip sip1   # Run only SIP-1
    python3 au_sip_tester.py --sip sip2   # Run only SIP-2
"""
from __future__ import annotations

import json
import math
import sys
import csv
import re
from collections import defaultdict
from pathlib import Path
from copy import deepcopy

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]

# Import shared backtest logic
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
from au_target_gap_report import (
    condition_bucket,
    field_size_bucket,
    race_class_bucket,
)
from rank_adjustments import jt_sample_size_rank_cap, narrow_overrated_rank_shield

OUTPUT_MD = ARCHIVE_ROOT / "AU_Auto_SIP_Test_Results.md"
JT_COMBO_CSV = ARCHIVE_ROOT / "AU_Jockey_Trainer_Combo_Stats.csv"

TARGETS = {
    "gold_rate": 0.30,
    "good_rate": 0.40,
    "minimum_rate": 0.60,
    "top3_place_precision": 0.80,
}

_JT_COMBO_CACHE = None
_JT_TRAINER_CACHE = None


def _clean_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_track(value):
    text = _clean_text(value).lower()
    text = text.replace("*", " ")
    text = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", text)
    text = re.sub(r"\s+race\s+\d+(?:-\d+)?$", "", text)
    text = text.replace(" gardens", "")
    text = text.replace(" heath", "")
    text = text.replace(" lakeside", "")
    text = text.replace(" hillside", "")
    return _clean_text(text)


def _load_jt_combo_stats():
    global _JT_COMBO_CACHE, _JT_TRAINER_CACHE
    if _JT_COMBO_CACHE is not None and _JT_TRAINER_CACHE is not None:
        return _JT_COMBO_CACHE, _JT_TRAINER_CACHE
    combo_cache = {}
    trainer_cache = defaultdict(lambda: {"runs": 0, "wins": 0, "places": 0, "win_rate": 0.0, "place_rate": 0.0})
    with JT_COMBO_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            track = _normalize_track(row.get("Track"))
            jockey = _clean_text(row.get("Jockey")).lower()
            trainer = _clean_text(row.get("Trainer")).lower()
            if not track or not trainer:
                continue
            runs = int(float(row.get("Total Runs") or 0))
            wins = int(float(row.get("Wins") or 0))
            places = int(float(row.get("Places (Top 3)") or 0))
            win_rate = (wins / runs) if runs else 0.0
            place_rate = (places / runs) if runs else 0.0
            if jockey:
                combo_cache[(track, jockey, trainer)] = {
                    "runs": runs,
                    "wins": wins,
                    "places": places,
                    "win_rate": win_rate,
                    "place_rate": place_rate,
                }
            trainer_cache[(track, trainer)]["runs"] += runs
            trainer_cache[(track, trainer)]["wins"] += wins
            trainer_cache[(track, trainer)]["places"] += places
    for stats in trainer_cache.values():
        runs = stats["runs"] or 0
        stats["win_rate"] = (stats["wins"] / runs) if runs else 0.0
        stats["place_rate"] = (stats["places"] / runs) if runs else 0.0
    _JT_COMBO_CACHE = combo_cache
    _JT_TRAINER_CACHE = dict(trainer_cache)
    return _JT_COMBO_CACHE, _JT_TRAINER_CACHE


def _safe_int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0

# ── Data loading ────────────────────────────────────────

def load_all_races():
    """Load all race data from archived Logic.json files with actual results."""
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"),
                             key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        sample_logic = json.loads(logic_files[0].read_text(encoding="utf-8"))
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = detect_meeting_track(meeting_dir, sample_logic)
        if not meeting_date or not meeting_track:
            continue
        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis", {})
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            rows_for_race = choose_track_rows(historical_results.get((meeting_date, race_no), []), meeting_track)
            if not rows_for_race:
                continue
            race_lookup = {row["horse_slug"]: row for row in rows_for_race}
            horses = []
            for horse_num, horse in logic.get("horses", {}).items():
                python_auto = horse.get("python_auto") or {}
                result_row = race_lookup.get(normalize_horse_name(horse.get("horse_name")))
                if not result_row:
                    continue
                # Extract all needed fields for SIP evaluation
                going = str(race_analysis.get("going", "") or "")
                risk_flags = python_auto.get("risk_flags", [])
                matrix = python_auto.get("matrix", {})
                matrix_scores = python_auto.get("matrix_scores", {})
                feature_scores = python_auto.get("feature_scores", {})
                barrier = parse_int(horse.get("barrier"))

                horses.append({
                    "horse_number": parse_int(horse_num) or 999,
                    "horse_name": horse.get("horse_name", ""),
                    "rank_score": float(python_auto.get("rank_score") or python_auto.get("ability_score") or 0.0),
                    "ability_score": float(python_auto.get("ability_score") or 0.0),
                    "actual_pos": int(result_row["pos"]),
                    "condition_bucket": condition_bucket(result_row.get("condition")),
                    "risk_flags": risk_flags,
                    "matrix": matrix,
                    "matrix_scores": matrix_scores,
                    "feature_scores": feature_scores,
                    "barrier": barrier,
                    "going": going,
                    "meeting_track": meeting_track,
                    "jockey": horse.get("jockey", ""),
                    "trainer": horse.get("trainer", ""),
                    "data": horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {},
                })
            if len(horses) < 4:
                continue
            races.append({
                "meeting": meeting_dir.name,
                "race_no": race_no,
                "meeting_track": meeting_track,
                "meeting_track_normalized": _normalize_track(meeting_track),
                "race_class_bucket": race_class_bucket(race_analysis.get("race_class")),
                "field_size_bucket": field_size_bucket(len(horses)),
                "condition_bucket": horses[0]["condition_bucket"],
                "going": race_analysis.get("going", ""),
                "field_count": len(horses),
                "horses": horses,
            })
    return races


# ── Metrics ──────────────────────────────────────────────

def new_bucket():
    return {
        "races": 0,
        "champion": 0,
        "gold": 0,
        "good": 0,
        "minimum": 0,
        "winner_in_top3": 0,
        "top3_places": 0,
        "top3_slots": 0,
        "hit_distribution": {0: 0, 1: 0, 2: 0, 3: 0},
    }

def rate(n, d):
    return n / d if d else 0.0

def pct(v):
    return f"{v * 100:.1f}%"

def gap(target, count, total):
    return max(0, math.ceil(target * total) - count)

def evaluate_races(races, label="", sip_adjust_fn=None):
    """Evaluate races with optional SIP score adjustments."""
    overall = new_bucket()
    by_condition = defaultdict(new_bucket)
    by_class = defaultdict(new_bucket)
    by_field = defaultdict(new_bucket)

    for race in races:
        horses = deepcopy(race["horses"])
        if sip_adjust_fn:
            horses = sip_adjust_fn(horses, race)

        ranked = sorted(horses, key=lambda h: (-h["rank_score"], h["horse_number"]))
        top3 = ranked[:3]
        top2 = ranked[:2]
        hits_top3 = sum(1 for h in top3 if h["actual_pos"] <= 3)
        hits_top2 = sum(1 for h in top2 if h["actual_pos"] <= 3)

        for bucket in (overall,
                       by_condition[race["condition_bucket"]],
                       by_class[race["race_class_bucket"]],
                       by_field[race["field_size_bucket"]]):
            bucket["races"] += 1
            bucket["top3_places"] += hits_top3
            bucket["top3_slots"] += 3
            bucket["hit_distribution"][hits_top3] += 1
            if ranked[0]["actual_pos"] == 1:
                bucket["champion"] += 1
            if any(h["actual_pos"] == 1 for h in top3):
                bucket["winner_in_top3"] += 1
            if hits_top3 == 3:
                bucket["gold"] += 1
            if hits_top2 == 2:
                bucket["good"] += 1
            if hits_top3 >= 2:
                bucket["minimum"] += 1

    return overall, by_condition, by_class, by_field


def report_summary(bucket, label=""):
    r = bucket["races"]
    s = bucket["top3_slots"]
    return {
        "label": label,
        "races": r,
        "champion": pct(rate(bucket["champion"], r)),
        "gold": pct(rate(bucket["gold"], r)),
        "good": pct(rate(bucket["good"], r)),
        "pass": pct(rate(bucket["minimum"], r)),
        "top3_win": pct(rate(bucket["winner_in_top3"], r)),
        "top3_place": pct(rate(bucket["top3_places"], s)),
        "0hit": bucket["hit_distribution"][0],
        "1hit": bucket["hit_distribution"][1],
        "2hit": bucket["hit_distribution"][2],
        "3hit": bucket["hit_distribution"][3],
    }


def delta_report(before, after):
    return {
        "gold_delta": round((rate(after["hit_distribution"][3], after["races"]) - rate(before["hit_distribution"][3], before["races"])) * 100, 1),
        "good_delta": round((rate(after["good"], after["races"]) - rate(before["good"], before["races"])) * 100, 1),
        "pass_delta": round((rate(after["minimum"], after["races"]) - rate(before["minimum"], before["races"])) * 100, 1),
        "place_delta": round((rate(after["top3_places"], after["top3_slots"]) - rate(before["top3_places"], before["top3_slots"])) * 100, 1),
        "0hit_delta": after["hit_distribution"][0] - before["hit_distribution"][0],
        "1hit_delta": after["hit_distribution"][1] - before["hit_distribution"][1],
    }


# ═══════════════════════════════════════════════════════════
# SIP Implementations (post-hoc score adjustments)
# ═══════════════════════════════════════════════════════════

# ── SIP-1: high_consumption_load auto-penalty ──
# From the zero-hit audit, horses flagged high_consumption_load consistently
# over-perform stability but under-deliver place outcomes.
# Penalty: -6 to rank_score for horses with this flag.
# Escalated for BM58-70 races (where pattern is most severe).

def sip1_high_consumption_penalty(horses, race):
    for h in horses:
        if "high_consumption_load" in h["risk_flags"]:
            penalty = -3.0
            if race.get("race_class_bucket", "") == "BM58-70":
                penalty = -4.5
            h["rank_score"] = h["rank_score"] + penalty
    return horses


# ── SIP-2: Soft track independent calibration ──
# Soft track is 0% Gold in current baseline (59 races).
# Diagnosis: "stability" and "sectional" are massively overtrusted on wet tracks.
# Action: Apply a reshuffling where stability-heavy horses get penalized
# and track/jockey_trainer horses get boosted.

def sip2_soft_track_rebalance(horses, race):
    going = str(race.get("going", "")).lower()
    if "soft" not in going and "heavy" not in going:
        return horses  # Only applies to wet tracks

    is_soft = "soft" in going
    is_heavy = "heavy" in going

    for h in horses:
        # Boost: track suitability + jockey_trainer signal
        track_score = float(h.get("matrix_scores", {}).get("track", 60))
        jt_score = float(h.get("matrix_scores", {}).get("jockey_trainer", 60))
        stability_score = float(h.get("matrix_scores", {}).get("stability", 60))

        boost = 0.0
        penalty = 0.0

        # High track suitability on wet = strong positive signal
        if track_score >= 72:
            boost += 3.0
        elif track_score >= 66:
            boost += 1.5

        # High jockey_trainer on wet = strong positive
        if jt_score >= 72:
            boost += 2.5
        elif jt_score >= 66:
            boost += 1.0

        # High stability on wet = false positive source, penalize
        if stability_score >= 72:
            penalty += -4.0
        elif stability_score >= 66:
            penalty += -2.0

        # Heavy is more severe — double the adjustments
        if is_heavy:
            boost *= 1.5
            penalty *= 1.5

        h["rank_score"] = h["rank_score"] + boost + penalty

    return horses


# ── SIP-3: Barrier bias integration ──
# Based on AU_Racing_Historical_Stats.md:
# Flemington: Barrier 6 = 13.5% win/35.1% place (best), Barrier 8 = 5.1% win
# Randwick: Barrier 3 = 13.4% win/32.4% place (best), Barrier 14+ = ~0% win
# Action: Apply barrier bias adjustment based on venue.

# Barrier advantage lookup: (track_slug, barrier) -> adjustment
# Positive = advantage, negative = disadvantage
BARRIER_ADJUSTMENTS = {
    "flemington": {
        1: 1.0, 2: 0.5, 3: 0.0, 4: 3.0, 5: 2.0,
        6: 3.5, 7: 1.5, 8: -2.0, 9: -1.0, 10: 1.0,
        11: -0.5, 12: 0.0, 13: 0.5, 14: -0.5, 15: 0.0,
        16: 0.0, 17: -3.0,
    },
    "randwick": {
        1: 1.5, 2: 2.0, 3: 3.5, 4: 3.0, 5: 1.5,
        6: 0.0, 7: -0.5, 8: 1.0, 9: -1.0, 10: -3.0,
        11: -1.0, 12: -3.5, 13: -3.0, 14: -5.0, 15: -5.0,
        16: -5.0, 17: -2.0, 18: -5.0,
    },
}

def sip3_barrier_bias(horses, race):
    track = str(race.get("meeting_track", "")).lower().strip()
    adj_map = BARRIER_ADJUSTMENTS.get(track, {})
    if not adj_map:
        return horses

    for h in horses:
        barrier = h.get("barrier")
        if barrier is None:
            continue
        adj = adj_map.get(barrier, 0.0)
        # Scale: mild adjustments that compound with field size
        field_count = race.get("field_count", 10)
        scale = 1.0 if field_count <= 10 else 1.5
        h["rank_score"] = h["rank_score"] + (adj * scale)

    return horses


# ── SIP-4: Replace broken place tightening layer ──
# Current PLACE_TIGHTENING is proven zero-effect (0 races improved).
# New approach: Dynamic field-size conditioned place probability dampening.
# Large fields (13+): Top3 Place Precision is only 29.2% — aggressive narrowing needed.
# Small fields (≤8): Top3 Place Precision is 53.5% — already good.

def sip4_dynamic_place_dampening(horses, race):
    field_count = race.get("field_count", 10)
    going = str(race.get("going", "")).lower()

    if field_count <= 8:
        # Small fields: already performing well, light touch
        dampen_factor = 0.99
    elif field_count <= 12:
        # Medium fields: moderate tightening
        dampen_factor = 0.98
    else:
        # Large fields: aggressive — collapse the top-pack spread
        dampen_factor = 0.96
        if "soft" in going or "heavy" in going:
            dampen_factor = 0.94  # Even more aggressive on wet large fields

    # Apply dampening: bring mid-tier horses closer to top (reduce false confidence)
    # Strategy: compress rank_score towards mean for non-top horses
    scores = [h["rank_score"] for h in horses]
    mean_score = sum(scores) / len(scores) if scores else 0.0

    for h in horses:
        original = h["rank_score"]
        # Compress towards mean — the further from mean, the more dampening
        deviation = original - mean_score
        h["rank_score"] = mean_score + (deviation * dampen_factor)

    return horses


# ── SIP-5: Jockey/Trainer sample-size confidence cap ──
# If jockey_trainer is high but direct horse evidence / venue combo / trainer-track
# evidence is thin, pull the score back toward neutral so sparse AU databases do not
# overstate the signal.

def sip5_jt_sample_size_cap(horses, race):
    combo_cache, trainer_cache = _load_jt_combo_stats()
    venue = race.get("meeting_track_normalized", "")

    for h in horses:
        matrix_scores = h.get("matrix_scores", {})
        data = h.get("data", {})
        jockey = _clean_text(h.get("jockey")).lower()
        trainer = _clean_text(h.get("trainer")).lower()
        combo_stats = combo_cache.get((venue, jockey, trainer), {}) if venue and jockey and trainer else {}
        trainer_stats = trainer_cache.get((venue, trainer), {}) if venue and trainer else {}

        penalty = jt_sample_size_rank_cap(
            matrix_scores,
            _safe_int(data.get("current_jockey_formal_rides")),
            _safe_int(data.get("current_jockey_trial_rides")),
            _safe_int(data.get("best_formal_jockey_rides")),
            _safe_int(data.get("latest_official_jockey_formal_rides")),
            int(combo_stats.get("runs", 0)),
            int(trainer_stats.get("runs", 0)),
        )
        h["rank_score"] = h["rank_score"] + penalty

    return horses


# ── SIP-6: Overrated shield for form/stability traps ──
# Archive audit shows many crash cases are driven by high form_line/stability while
# race_shape / track / class_weight are materially weak. Cap those profiles before
# they float into the top-2.

def sip6_overrated_shield(horses, race):
    for h in horses:
        matrix_scores = h.get("matrix_scores", {})
        stability = float(matrix_scores.get("stability", 60))
        form_line = float(matrix_scores.get("form_line", 60))
        race_shape = float(matrix_scores.get("race_shape", 60))
        track = float(matrix_scores.get("track", 60))
        class_weight = float(matrix_scores.get("class_weight", 60))
        sectional = float(matrix_scores.get("sectional", 60))

        low_flags = sum(score < 64 for score in (race_shape, track, class_weight))
        very_low_flags = sum(score < 60 for score in (race_shape, track, class_weight))
        penalty = 0.0

        if stability >= 75 and form_line >= 75 and low_flags >= 2:
            penalty -= 2.5
        elif stability >= 72 and form_line >= 72 and low_flags >= 2:
            penalty -= 1.5

        if very_low_flags >= 2:
            penalty -= 1.0

        if stability >= 78 and form_line >= 76 and sectional < 66:
            penalty -= 0.8

        if race.get("condition_bucket") == "Good/Firm" and low_flags >= 2 and stability >= 72 and form_line >= 72:
            penalty -= 0.5

        h["rank_score"] = h["rank_score"] + penalty

    return horses


def sip7_jt_cap_plus_overrated_shield(horses, race):
    horses = sip5_jt_sample_size_cap(horses, race)
    horses = sip6_overrated_shield(horses, race)
    return horses


# ── SIP-8: Narrow overrated shield ──
# Same idea as SIP-6, but only hits the archetypal crash profile:
# dry track, field size not tiny, very high form/stability, at least two weak
# structural sections, and no strong sectional confirmation.

def sip8_narrow_overrated_shield(horses, race):
    condition_bucket_name = str(race.get("condition_bucket") or "")
    wet_state = ""
    if condition_bucket_name == "Soft":
        wet_state = "soft56"
    elif condition_bucket_name == "Heavy":
        wet_state = "heavy"
    for h in horses:
        matrix_scores = h.get("matrix_scores", {})
        penalty = narrow_overrated_rank_shield(
            matrix_scores,
            wet_state,
            int(race.get("field_count", 0)),
        )
        h["rank_score"] = h["rank_score"] + penalty

    return horses


def sip9_jt_cap_plus_narrow_shield(horses, race):
    horses = sip5_jt_sample_size_cap(horses, race)
    horses = sip8_narrow_overrated_shield(horses, race)
    return horses


# ═══════════════════════════════════════════════════════════
# Main runner
# ═══════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AU SIP Tester")
    parser.add_argument("--sip", choices=["sip1", "sip2", "sip3", "sip4", "sip5", "sip6", "sip7", "sip8", "sip9", "all"],
                        default="all", help="Which SIP to test")
    args = parser.parse_args()

    print("📦 Loading archive race data...")
    races = load_all_races()
    print(f"   Loaded {len(races)} races")

    # Baseline
    print("\n📊 BASELINE (current engine):")
    bl_overall, bl_cond, bl_class, bl_field = evaluate_races(races, "Baseline")
    bl_summary = report_summary(bl_overall, "Baseline")
    _print_summary(bl_summary)

    sips = {
        "sip1": ("SIP-1: high_consumption_load penalty", sip1_high_consumption_penalty),
        "sip2": ("SIP-2: Soft track rebalance", sip2_soft_track_rebalance),
        "sip3": ("SIP-3: Barrier bias", sip3_barrier_bias),
        "sip4": ("SIP-4: Dynamic place dampening", sip4_dynamic_place_dampening),
        "sip5": ("SIP-5: JT sample-size confidence cap", sip5_jt_sample_size_cap),
        "sip6": ("SIP-6: Overrated shield", sip6_overrated_shield),
        "sip7": ("SIP-7: JT cap + Overrated shield", sip7_jt_cap_plus_overrated_shield),
        "sip8": ("SIP-8: Narrow overrated shield", sip8_narrow_overrated_shield),
        "sip9": ("SIP-9: JT cap + Narrow shield", sip9_jt_cap_plus_narrow_shield),
    }

    results_md = [
        "# AU Auto SIP Test Results",
        "",
        "Each SIP is tested independently against the 315-race archive.",
        "Only SIPs showing positive results should be promoted to production.",
        "",
        f"## Baseline (Current Engine)",
        "",
        _md_table(bl_summary),
        "",
    ]

    sip_list = list(sips.items()) if args.sip == "all" else [(args.sip, sips[args.sip])]

    for sip_key, (sip_name, sip_fn) in sip_list:
        print(f"\n🧪 Testing {sip_name}...")
        ov, co, cl, fi = evaluate_races(races, sip_name, sip_fn)
        summary = report_summary(ov, sip_name)
        _print_summary(summary)

        delta = delta_report(bl_overall, ov)
        _print_delta(delta)

        results_md.append(f"## {sip_name}")
        results_md.append("")
        results_md.append(_md_table(summary))
        results_md.append("")
        results_md.append(_md_delta_table(delta))
        results_md.append("")

        # Also show condition breakdown for SIP-2 (soft track)
        if sip_key == "sip2":
            results_md.append("### Condition Breakdown (SIP-2)")
            results_md.append("")
            cond_rows = []
            for cond in ("Good/Firm", "Soft", "Heavy"):
                bucket = co.get(cond, new_bucket())
                if bucket["races"] == 0:
                    continue
                s = report_summary(bucket, cond)
                cond_rows.append(f"| {cond} | {s['races']} | {s['gold']} | {s['good']} | {s['pass']} | {s['top3_place']} | {s['0hit']} | {s['1hit']} | {s['2hit']} | {s['3hit']} |")
            if cond_rows:
                results_md.append("| Condition | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |")
                results_md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
                results_md.extend(cond_rows)
                results_md.append("")

        # Show field-size breakdown for SIP-4
        if sip_key == "sip4":
            results_md.append("### Field Size Breakdown (SIP-4)")
            results_md.append("")
            field_rows = []
            for fs in ("Field <=8", "Field 9-12", "Field 13+"):
                bucket = fi.get(fs, new_bucket())
                if bucket["races"] == 0:
                    continue
                s = report_summary(bucket, fs)
                field_rows.append(f"| {fs} | {s['races']} | {s['gold']} | {s['good']} | {s['pass']} | {s['top3_place']} | {s['0hit']} | {s['1hit']} | {s['2hit']} | {s['3hit']} |")
            if field_rows:
                results_md.append("| Field Size | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |")
                results_md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
                results_md.extend(field_rows)
                results_md.append("")

        # Show class breakdown for SIP-1
        if sip_key == "sip1":
            results_md.append("### Class Breakdown (SIP-1)")
            results_md.append("")
            class_rows = []
            for cls in ("BM58-70", "BM72-84", "BM88+", "Group 1", "Group 2/3", "Maiden", "Other"):
                bucket = cl.get(cls, new_bucket())
                if bucket["races"] == 0:
                    continue
                s = report_summary(bucket, cls)
                class_rows.append(f"| {cls} | {s['races']} | {s['gold']} | {s['good']} | {s['pass']} | {s['top3_place']} | {s['0hit']} | {s['1hit']} | {s['2hit']} | {s['3hit']} |")
            if class_rows:
                results_md.append("| Class | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |")
                results_md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
                results_md.extend(class_rows)
                results_md.append("")

        if sip_key in {"sip5", "sip6", "sip7", "sip8", "sip9"}:
            results_md.append("### Field Size Breakdown")
            results_md.append("")
            field_rows = []
            for fs in ("Field <=8", "Field 9-12", "Field 13+"):
                bucket = fi.get(fs, new_bucket())
                if bucket["races"] == 0:
                    continue
                s = report_summary(bucket, fs)
                field_rows.append(f"| {fs} | {s['races']} | {s['gold']} | {s['good']} | {s['pass']} | {s['top3_place']} | {s['0hit']} | {s['1hit']} | {s['2hit']} | {s['3hit']} |")
            if field_rows:
                results_md.append("| Field Size | Races | Gold | Good | Pass | Place Prec | 0-hit | 1-hit | 2-hit | 3-hit |")
                results_md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
                results_md.extend(field_rows)
                results_md.append("")

    results_md.append("---")
    results_md.append("")
    results_md.append("## Verdict")
    results_md.append("")
    results_md.append("SIPs with **positive Pass delta AND reduced 0-hit** should be promoted.")
    results_md.append("SIPs with negative or zero impact should be redesigned before promotion.")
    results_md.append("")

    OUTPUT_MD.write_text("\n".join(results_md), encoding="utf-8")
    print(f"\n📄 Report written: {OUTPUT_MD}")


def _print_summary(s):
    print(f"  Races: {s['races']:>5}  |  Gold: {s['gold']:>6}  |  Good: {s['good']:>6}  |  Pass: {s['pass']:>6}")
    print(f"  Champ: {s['champion']:>5}  |  Top3Win: {s['top3_win']:>5}  |  Place: {s['top3_place']:>5}")
    print(f"  0-hit: {s['0hit']:>3}  |  1-hit: {s['1hit']:>3}  |  2-hit: {s['2hit']:>3}  |  3-hit: {s['3hit']:>3}")


def _print_delta(d):
    signs = {
        "gold_delta": "+" if d["gold_delta"] >= 0 else "",
        "good_delta": "+" if d["good_delta"] >= 0 else "",
        "pass_delta": "+" if d["pass_delta"] >= 0 else "",
        "place_delta": "+" if d["place_delta"] >= 0 else "",
        "0hit_delta": "+" if d["0hit_delta"] >= 0 else "",
        "1hit_delta": "+" if d["1hit_delta"] >= 0 else "",
    }
    print(f"  ΔGold: {signs['gold_delta']}{d['gold_delta']:+.1f}pp  |  ΔGood: {signs['good_delta']}{d['good_delta']:+.1f}pp  |  ΔPass: {signs['pass_delta']}{d['pass_delta']:+.1f}pp  |  ΔPlace: {signs['place_delta']}{d['place_delta']:+.1f}pp")
    print(f"  Δ0hit: {signs['0hit_delta']}{d['0hit_delta']:+d}  |  Δ1hit: {signs['1hit_delta']}{d['1hit_delta']:+d}")


def _md_table(s):
    return f"| {s['label']} | {s['races']} | {s['gold']} | {s['good']} | {s['pass']} | {s['top3_win']} | {s['top3_place']} | {s['0hit']} | {s['1hit']} | {s['2hit']} | {s['3hit']} |\n| Races={s['races']} | Gold {s['gold']} | Good {s['good']} | Pass {s['pass']} | Win {s['top3_win']} | Place {s['top3_place']} | 0H {s['0hit']} | 1H {s['1hit']} | 2H {s['2hit']} | 3H {s['3hit']} |"


def _md_delta_table(d):
    return f"| ΔGold | ΔGood | ΔPass | ΔPlace Prec | Δ0-hit | Δ1-hit |\n|---:|---:|---:|---:|---:|---:|\n| {d['gold_delta']:+.1f}pp | {d['good_delta']:+.1f}pp | {d['pass_delta']:+.1f}pp | {d['place_delta']:+.1f}pp | {d['0hit_delta']:+d} | {d['1hit_delta']:+d} |"


if __name__ == "__main__":
    main()
