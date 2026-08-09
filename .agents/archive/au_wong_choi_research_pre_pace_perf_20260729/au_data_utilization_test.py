#!/usr/bin/env python3
"""
AU Wong Choi Data Utilization Improvement Test
================================================
Tests 5 targeted improvements using stored rank_scores + post-hoc adjustments.

Each improvement is tested independently against the full archive.
Only improvements showing positive Pass delta AND non-positive 0-hit delta
should be considered for mainline implementation.
"""
from __future__ import annotations

import sys
import json
import re
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path = [p for p in sys.path if p]
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (
    ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV,
    choose_track_rows, detect_meeting_date, detect_meeting_track,
    load_historical_results, normalize_horse_name, parse_int,
)

OUTPUT_MD = PROJECT_ROOT / "2026-05-31 AU Data Utilization Test.md"


def load_all_data():
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    all_races = []

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
            horses = []
            for horse_num, horse in (logic.get("horses") or {}).items():
                python_auto = horse.get("python_auto") or {}
                data = horse.get("_data") or {}
                result_row = race_lookup.get(
                    normalize_horse_name(horse.get("horse_name"))
                )
                if not result_row:
                    continue
                horses.append({
                    "horse_number": parse_int(horse_num) or 999,
                    "stored_rank": float(
                        python_auto.get("rank_score")
                        or python_auto.get("ability_score")
                        or 0
                    ),
                    "actual_pos": int(result_row["pos"]),
                    "condition": str(result_row.get("condition", "") or "").lower(),
                    "barrier": parse_int(horse.get("barrier")),
                    "field_count": len(logic.get("horses", {})),
                    # Matrix scores
                    "mx": {
                        k: float((python_auto.get("matrix_scores") or {}).get(k, 60))
                        for k in ("stability", "sectional", "race_shape", "jockey_trainer", "class_weight", "track", "form_line")
                    },
                    # Raw data fields
                    "data": data,
                    "race_class": str(race_analysis.get("race_class", "") or ""),
                    "going": str(race_analysis.get("going", "") or ""),
                })
            if len(horses) >= 4:
                all_races.append({
                    "meeting": meeting_dir.name,
                    "race_no": race_no,
                    "condition": horses[0]["condition"],
                    "race_class": horses[0]["race_class"],
                    "field_count": len(horses),
                    "horses": horses,
                })
    return all_races


def evaluate(all_races, adjust_fn):
    """Evaluate a variant by applying adjust_fn to each horse's stored_rank."""
    hits = []
    for race in all_races:
        adjusted = []
        for h in race["horses"]:
            new_rank = adjust_fn(h, race)
            adjusted.append((new_rank, h["actual_pos"]))
        adjusted.sort(key=lambda x: -x[0])
        top3_hits = sum(1 for _, pos in adjusted[:3] if pos <= 3)
        hits.append(top3_hits)
    n = len(hits)
    gold = sum(1 for h in hits if h == 3) / n * 100
    pass_ = sum(1 for h in hits if h >= 2) / n * 100
    zero = sum(1 for h in hits if h == 0)
    return gold, pass_, zero


def parse_shape_pattern(pattern_str):
    """Parse settled pattern like '3→10→4→2' into position list."""
    if not pattern_str:
        return []
    nums = re.findall(r"\d+", str(pattern_str))
    return [int(n) for n in nums if n.isdigit()]


def get_shape_consensus(data):
    """Get running style consensus from data."""
    return str(data.get("recent_shape_consensus", "") or "").lower()


def get_shape_counts(data):
    """Get front/mid/back counts."""
    front = int(parse_float(data.get("recent_shape_front_count")) or 0)
    mid = int(parse_float(data.get("recent_shape_mid_count")) or 0)
    back = int(parse_float(data.get("recent_shape_back_count")) or 0)
    inside = int(parse_float(data.get("recent_shape_inside_count")) or 0)
    wide = int(parse_float(data.get("recent_shape_wide_no_cover_count")) or 0)
    return front, mid, back, inside, wide


def parse_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ═══════════════════════════════════════════════════════════
# Improvement Functions
# ═══════════════════════════════════════════════════════════

def IMP1_running_style_draw(h, race):
    """Running style × draw interaction on pace_map_score.

    If a front-runner is drawn wide (>=10), extra penalty.
    If a back-runner is drawn inside (<=4), mild bonus.
    If a back-runner is drawn wide (>=12), mild penalty.
    """
    barrier = h.get("barrier")
    if barrier is None:
        return 0.0

    data = h.get("data", {})
    consensus = get_shape_consensus(data)
    front, mid, back, _, _ = get_shape_counts(data)
    total = front + mid + back

    if total < 2:
        return 0.0  # Not enough data

    style = "unknown"
    if front / total >= 0.6:
        style = "front"
    elif back / total >= 0.6:
        style = "back"
    elif mid / total >= 0.5:
        style = "mid"

    fc = h.get("field_count", 10)
    delta = 0.0

    if style == "front":
        if barrier >= 12:
            delta = -2.0
            if fc >= 13:
                delta = -3.0
        elif barrier >= 10:
            delta = -1.0
    elif style == "back":
        if barrier <= 3:
            delta = +0.8
        elif barrier >= 14:
            delta = -1.0
        elif barrier >= 12:
            delta = -0.5
    elif style == "mid":
        if barrier >= 14:
            delta = -0.5

    return delta


def IMP2_readiness_activation(h, race):
    """Activate readiness_score using consumption + spell + trial data.

    Currently readiness_score is hardcoded 60. This uses:
    - consumption_summary (weighted consumption score)
    - spell_days (days since last run)
    - trial_count + trial_top3 (trial density)
    - stage cycle (first-up, second-up, etc.)
    """
    data = h.get("data", {})

    # Parse consumption
    consumption_text = str(data.get("consumption_summary", "") or "")
    consumption_score = None
    m = re.search(r"(\d+\.?\d*)/5\.0", consumption_text)
    if m:
        consumption_score = float(m.group(1))

    # Parse spell days
    spell_days = None
    stage_line = str(data.get("stage_stats_line", "") or "")
    # Try to get spell from stage cycle text
    status_cycle = ""
    if "First-up" in stage_line or "久休復出" in stage_line:
        status_cycle = "first_up"
    elif "Second-up" in stage_line or "二出" in stage_line:
        status_cycle = "second_up"
    elif "Third-up" in stage_line or "第三仗" in stage_line:
        status_cycle = "third_up"

    trial_count = int(parse_float(data.get("trial_count")) or 0)
    trial_top3 = int(parse_float(data.get("trial_top3_count")) or 0)

    score = 60.0  # base

    # Consumption adjustment
    if consumption_score is not None:
        if consumption_score <= 2.2:
            score += 4.0
        elif consumption_score <= 2.8:
            score += 2.0
        elif consumption_score >= 4.0:
            score -= 4.0
        elif consumption_score >= 3.4:
            score -= 2.0

    # Stage cycle adjustment
    if status_cycle == "first_up":
        if trial_count >= 2 and trial_top3 >= 1:
            score += 2.0  # Fresh with good trials
        elif trial_count == 0:
            score -= 3.0  # No trial prep
    elif status_cycle == "second_up":
        score += 2.0  #通常第二仗更好
    elif status_cycle == "third_up":
        score += 1.5

    # Trial density adjustment
    if trial_count >= 3 and trial_top3 >= 2:
        score += 2.0
    elif trial_count >= 2 and trial_top3 >= 1:
        score += 1.0

    # Return delta from baseline 60
    return score - 60.0


def IMP3_sectional_trend(h, race):
    """Add timing trend + recent speed to sectional_score.

    Uses:
    - timing_600m_trend (improving/stable/declining)
    - timing_600m_recent_speed vs timing_600m_avg_speed
    - timing_speed_variance
    """
    data = h.get("data", {})

    trend = str(data.get("timing_600m_trend", "") or "").lower()
    recent_speed = parse_float(data.get("timing_600m_recent_speed"))
    avg_speed = parse_float(data.get("timing_600m_avg_speed"))
    variance = parse_float(data.get("timing_speed_variance"))
    entries = int(parse_float(data.get("timing_l600_entries_count")) or 0)

    delta = 0.0

    # Trend signal
    if "improving" in trend and "sharp" not in trend:
        delta += 1.5
    elif "sharp_improving" in trend:
        delta += 2.5
    elif "declining" in trend and "sharp" not in trend:
        delta -= 1.5
    elif "sharp_declining" in trend:
        delta -= 2.5

    # Recent vs career average
    if recent_speed is not None and avg_speed is not None and avg_speed > 0:
        diff = recent_speed - avg_speed
        if diff >= 0.3:
            delta += 1.5  # Recent form better than career
        elif diff <= -0.3:
            delta -= 1.5  # Recent form worse than career

    # Variance penalty
    if variance is not None and variance >= 0.25:
        delta -= 1.0  # Inconsistent

    # Confidence weight (more entries = more reliable signal)
    if entries <= 2:
        delta *= 0.5  # Dampen signal for low-data horses

    return delta


def IMP4_distance_confidence(h, race):
    """Use engine_confidence to scale distance_score.

    Low confidence → dampen the distance-related ranking.
    """
    data = h.get("data", {})
    confidence = str(data.get("engine_confidence_line", "") or "").lower()

    if "低" in confidence or "low" in confidence:
        # Distance signal is less reliable → mild penalty
        return -1.0
    elif "高" in confidence or "high" in confidence:
        # Distance signal is reliable → mild bonus
        return +0.5
    return 0.0


def IMP5_speed_variance(h, race):
    """Penalize high speed variance in sectional_score.

    High variance = inconsistent sectional output = unreliable.
    """
    data = h.get("data", {})
    variance = parse_float(data.get("timing_speed_variance"))
    entries = int(parse_float(data.get("timing_l600_entries_count")) or 0)

    if variance is None or entries < 3:
        return 0.0

    delta = 0.0
    if variance >= 0.30:
        delta = -2.0
    elif variance >= 0.25:
        delta = -1.0
    elif variance <= 0.10:
        delta = +0.5  # Very consistent

    return delta


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    args = parser.parse_args()

    print("Loading archive data...")
    all_races = load_all_data()
    print(f"Loaded {len(all_races)} races")

    # Baseline
    bl_g, bl_p, bl_z = evaluate(all_races, lambda h, r: h["stored_rank"])
    print(f"\nBaseline: Gold={bl_g:.1f}% Pass={bl_p:.1f}% 0H={bl_z}")

    # Test each improvement
    improvements = [
        ("IMP1: Running style × draw", IMP1_running_style_draw),
        ("IMP2: Readiness activation", IMP2_readiness_activation),
        ("IMP3: Sectional trend + recent", IMP3_sectional_trend),
        ("IMP4: Distance confidence", IMP4_distance_confidence),
        ("IMP5: Speed variance penalty", IMP5_speed_variance),
    ]

    results = []
    for label, fn in improvements:
        def adj_fn(h, r, _fn=fn):
            return h["stored_rank"] + _fn(h, r)

        g, p, z = evaluate(all_races, adj_fn)
        d_g, d_p, d_z = g - bl_g, p - bl_p, z - bl_z
        verdict = "PASS" if d_p >= 0 and d_z <= 0 else "FAIL"
        if d_g > 0 and d_z <= 0:
            verdict = "BEST"
        print(f"\n{label}:")
        print(f"  Gold={g:.1f}% Pass={p:.1f}% 0H={z}")
        print(f"  Delta: Gold={d_g:+.1f}pp Pass={d_p:+.1f}pp 0H={d_z:+d} [{verdict}]")
        results.append((label, g, p, z, d_g, d_p, d_z, verdict))

    # Test best combo: all PASS improvements combined
    pass_improvements = [(l, f) for l, f, *_ in results if "FAIL" not in str(results[results.index((l, *_))][7])]

    def combo_adj(h, r):
        return h["stored_rank"] + IMP1_running_style_draw(h, r) + IMP2_readiness_activation(h, r) + IMP3_sectional_trend(h, r) + IMP4_distance_confidence(h, r) + IMP5_speed_variance(h, r)

    g, p, z = evaluate(all_races, combo_adj)
    d_g, d_p, d_z = g - bl_g, p - bl_p, z - bl_z
    print(f"\nCOMBO (all improvements):")
    print(f"  Gold={g:.1f}% Pass={p:.1f}% 0H={z}")
    print(f"  Delta: Gold={d_g:+.1f}pp Pass={d_p:+.1f}pp 0H={d_z:+d}")

    # Write report
    lines = [
        "# AU Data Utilization Improvement Test",
        "",
        f"Archive: `{len(all_races)}` races",
        "",
        "## Baseline",
        "",
        f"- Gold: `{bl_g:.1f}%`",
        f"- Pass: `{bl_p:.1f}%`",
        f"- 0-hit: `{bl_z}`",
        "",
        "## Results",
        "",
        "| Improvement | Gold Δ | Pass Δ | 0-hit Δ | Verdict |",
        "|---|---:|---:|---:|---|",
    ]

    for label, g, p, z, d_g, d_p, d_z, verdict in results:
        v = "✅" if verdict != "FAIL" else "❌"
        lines.append(f"| {label} | {d_g:+.1f}pp | {d_p:+.1f}pp | {d_z:+d} | {v} |")

    lines.extend([
        f"| **COMBO** | {d_g:+.1f}pp | {d_p:+.1f}pp | {d_z:+d} | {'✅' if d_p >= 0 and d_z <= 0 else '❌'} |",
        "",
        "## Improvement Descriptions",
        "",
        "### IMP1: Running Style × Draw Interaction",
        "- Front-runner drawn wide (>=10): extra penalty",
        "- Back-runner drawn inside (<=4): mild bonus",
        "- Data: `recent_shape_consensus`, `recent_shape_front/mid/back_count`",
        "",
        "### IMP2: Readiness Activation",
        "- Activate readiness_score (currently hardcoded 60)",
        "- Uses: `consumption_summary`, stage cycle, trial density",
        "",
        "### IMP3: Sectional Trend + Recent Speed",
        "- Uses: `timing_600m_trend`, `timing_600m_recent_speed` vs `avg_speed`",
        "- Improving trend = bonus, declining = penalty",
        "",
        "### IMP4: Distance Confidence Scaling",
        "- Uses: `engine_confidence_line`",
        "- Low confidence → dampen distance signal by -1.0",
        "",
        "### IMP5: Speed Variance Penalty",
        "- Uses: `timing_speed_variance`",
        "- High variance (>=0.25) = inconsistent = penalty",
    ])

    output_path = Path(args.output_md)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
