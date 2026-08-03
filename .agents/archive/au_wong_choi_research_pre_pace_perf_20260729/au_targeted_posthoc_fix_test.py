#!/usr/bin/env python3
"""
AU Wong Choi Targeted Post-Hoc Fix Test
========================================
Post-hoc approach: start from stored rank_score, apply targeted adjustments.

Based on diagnostics:
  - race_shape overestimated in 80% zero-hit → dampen when race_shape is dominant
  - track most underestimated → boost when track is strong
  - class_weight negative lift → penalize when class mismatch detected
  - Heavy 1.8× zero-hit → heavy-specific dampening

This approach is ADDITIVE to the existing engine, not replacing it.
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
)
from re_score_archive import build_field_summary

OUTPUT_MD = PROJECT_ROOT / "2026-05-31 AU Targeted Post-Hoc Fix Test.md"

MATRIX_KEYS = (
    "stability", "sectional", "race_shape", "jockey_trainer",
    "class_weight", "track", "form_line",
)


def load_races():
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
            horses = []
            for horse_num, horse in (logic.get("horses") or {}).items():
                python_auto = horse.get("python_auto") or {}
                matrix_scores = python_auto.get("matrix_scores") or {}
                feature_scores = python_auto.get("feature_scores") or {}
                if not matrix_scores or not feature_scores:
                    continue
                result_row = race_lookup.get(
                    normalize_horse_name(horse.get("horse_name"))
                )
                if not result_row:
                    continue
                horses.append({
                    "horse_number": parse_int(horse_num) or 999,
                    "horse_name": horse.get("horse_name", ""),
                    "rank_score": float(
                        python_auto.get("rank_score")
                        or python_auto.get("ability_score")
                        or 0.0
                    ),
                    "ability_score": float(python_auto.get("ability_score") or 0.0),
                    "actual_pos": int(result_row["pos"]),
                    "condition_bucket": _condition_bucket(result_row.get("condition") or ""),
                    "risk_flags": python_auto.get("risk_flags", []),
                    "matrix_scores": {
                        key: float(matrix_scores.get(key) or 60.0)
                        for key in MATRIX_KEYS
                    },
                    "feature_scores": feature_scores,
                    "barrier": parse_int(horse.get("barrier")),
                    "going": str(race_analysis.get("going", "") or ""),
                    "meeting_track": meeting_track,
                    "race_class": str(race_analysis.get("race_class") or ""),
                })
            if len(horses) < 4:
                continue
            races.append({
                "meeting": meeting_dir.name,
                "race_no": race_no,
                "meeting_track": meeting_track,
                "condition_bucket": horses[0]["condition_bucket"],
                "race_class_bucket": _race_class_bucket(str(race_analysis.get("race_class") or "")),
                "field_size_bucket": _field_size_bucket(len(horses)),
                "going": str(race_analysis.get("going", "") or ""),
                "race_class": str(race_analysis.get("race_class") or ""),
                "field_count": len(horses),
                "horses": horses,
            })
    return races


def _condition_bucket(condition):
    c = str(condition).lower()
    if "heavy" in c:
        return "Heavy"
    if "soft" in c:
        return "Soft"
    return "Good/Firm"


def _race_class_bucket(cls):
    c = str(cls).lower()
    if "group 1" in c or "g1" in c:
        return "Group 1"
    if "group 2" in c or "group 3" in c:
        return "Group 2/3"
    if "listed" in c:
        return "Listed"
    if "maiden" in c:
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


def _field_size_bucket(n):
    if n <= 8:
        return "Field <=8"
    if n <= 12:
        return "Field 9-12"
    return "Field 13+"


# ═══════════════════════════════════════════════════════════
# Post-Hoc Fix Functions
# ═══════════════════════════════════════════════════════════

def fix_P1_race_shape_dampen(horses, race):
    """When race_shape is the dominant signal (>72) but other hard signals are weak,
    dampen its contribution. Race_shape is overestimated in 80% of zero-hit races."""
    for h in horses:
        mx = h["matrix_scores"]
        rs = mx.get("race_shape", 60)
        stab = mx.get("stability", 60)
        trk = mx.get("track", 60)
        cw = mx.get("class_weight", 60)
        sec = mx.get("sectional", 60)

        # Count how many hard signals are weak
        hard_weak = sum(1 for s in (trk, cw, sec) if s < 63)

        if rs >= 72 and hard_weak >= 2:
            # Race_shape says "great draw" but track/class/sectional say otherwise
            penalty = -1.5
            if hard_weak >= 3:
                penalty = -2.5
            h["rank_score"] = h["rank_score"] + penalty
    return horses


def fix_P2_track_boost(horses, race):
    """Boost horses with strong track ability. Track is the most underestimated
    dimension (19.4% of zero-hits)."""
    for h in horses:
        mx = h["matrix_scores"]
        trk = mx.get("track", 60)
        if trk >= 72:
            h["rank_score"] = h["rank_score"] + 1.5
        elif trk >= 66:
            h["rank_score"] = h["rank_score"] + 0.8
    return horses


def fix_P3_class_weight_rebalance(horses, race):
    """When class_weight is weak (<60) but stability/form_line are high,
    the horse may be overrated on paper but outclassed today."""
    for h in horses:
        mx = h["matrix_scores"]
        cw = mx.get("class_weight", 60)
        stab = mx.get("stability", 60)
        fl = mx.get("form_line", 60)

        if cw < 58 and stab >= 72 and fl >= 72:
            h["rank_score"] = h["rank_score"] - 1.0
    return horses


def fix_P4_heavy_track_dampen(horses, race):
    """Heavy track: dampen stability/sectional (overestimated), boost track ability."""
    if race["condition_bucket"] != "Heavy":
        return horses
    for h in horses:
        mx = h["matrix_scores"]
        stab = mx.get("stability", 60)
        sec = mx.get("sectional", 60)
        trk = mx.get("track", 60)

        # Penalize overestimated signals on heavy
        if stab >= 70:
            h["rank_score"] = h["rank_score"] - (stab - 70) * 0.15
        if sec >= 70:
            h["rank_score"] = h["rank_score"] - (sec - 70) * 0.10

        # Boost underestimated track on heavy
        if trk >= 66:
            h["rank_score"] = h["rank_score"] + (trk - 60) * 0.12
    return horses


def fix_P5_soft_track_adjust(horses, race):
    """Soft track: similar to heavy but milder."""
    if race["condition_bucket"] != "Soft":
        return horses
    for h in horses:
        mx = h["matrix_scores"]
        stab = mx.get("stability", 60)
        trk = mx.get("track", 60)

        if stab >= 75:
            h["rank_score"] = h["rank_score"] - (stab - 75) * 0.10
        if trk >= 68:
            h["rank_score"] = h["rank_score"] + (trk - 62) * 0.08
    return horses


def fix_P6_near_miss_promote(horses, race):
    """Promote horses ranked 4-6 that have strong hard signals but low soft signals.
    These are the "hidden value" horses the model underrates."""
    ranked = sorted(horses, key=lambda x: -x["rank_score"])
    for h in ranked[3:6]:  # ranks 4, 5, 6
        mx = h["matrix_scores"]
        sec = mx.get("sectional", 60)
        cw = mx.get("class_weight", 60)
        trk = mx.get("track", 60)
        fl = mx.get("form_line", 60)
        stab = mx.get("stability", 60)

        hard_strong = sum(1 for s in (sec, cw, trk, fl) if s >= 68)
        soft_weak = stab < 65

        if hard_strong >= 3 and soft_weak:
            h["rank_score"] = h["rank_score"] + 1.2
    return horses


def fix_P7_overrated_shield(horses, race):
    """Stronger version of narrow_overrated_shield: when stability+form_line are
    high but race_shape+track+class_weight are all weak, penalize more aggressively."""
    for h in horses:
        mx = h["matrix_scores"]
        stab = mx.get("stability", 60)
        fl = mx.get("form_line", 60)
        rs = mx.get("race_shape", 60)
        trk = mx.get("track", 60)
        cw = mx.get("class_weight", 60)

        low_count = sum(1 for s in (rs, trk, cw) if s < 63)
        very_low = sum(1 for s in (rs, trk, cw) if s < 58)

        if stab >= 76 and fl >= 74 and low_count >= 2:
            penalty = -2.0
            if very_low >= 2:
                penalty -= 1.0
            h["rank_score"] = h["rank_score"] + penalty
    return horses


def fix_P8_field_size_adjust(horses, race):
    """In large fields (13+), dampen spread to reduce false confidence.
    In small fields (≤8), boost top horses slightly."""
    fc = race["field_count"]
    scores = [h["rank_score"] for h in horses]
    mean_s = sum(scores) / len(scores) if scores else 0

    if fc >= 13:
        # Compress towards mean
        for h in horses:
            dev = h["rank_score"] - mean_s
            h["rank_score"] = mean_s + dev * 0.95
    elif fc <= 8:
        # Slightly expand top
        for h in horses:
            if h["rank_score"] >= mean_s:
                h["rank_score"] += 0.5
    return horses


# ═══════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════

def run_variant(races, fix_fn, label):
    """Apply a fix function to all races and evaluate."""
    variant_races = []
    for race in races:
        horses = [dict(h) for h in race["horses"]]
        horses = fix_fn(horses, race)
        variant_races.append({**race, "horses": horses})
    overall, cond, cls, fld = evaluate_races(variant_races, label)
    return overall, cond, cls, fld


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    args = parser.parse_args()

    print("📦 Loading archive races...")
    races = load_races()
    print(f"   Loaded {len(races)} races")

    # Baseline
    print("\n📊 BASELINE:")
    bl_overall, _, _, _ = evaluate_races(races, "Baseline")
    bl_s = report_summary(bl_overall, "Baseline")
    print(f"  Gold: {bl_s['gold']}  |  Good: {bl_s['good']}  |  Pass: {bl_s['pass']}  |  Place: {bl_s['top3_place']}  |  0H: {bl_s['0hit']}")

    # Test individual fixes
    fixes = [
        ("P1: race_shape dampen", fix_P1_race_shape_dampen),
        ("P2: track boost", fix_P2_track_boost),
        ("P3: class_weight rebalance", fix_P3_class_weight_rebalance),
        ("P4: heavy dampening", fix_P4_heavy_track_dampen),
        ("P5: soft adjustment", fix_P5_soft_track_adjust),
        ("P6: near-miss promote", fix_P6_near_miss_promote),
        ("P7: overrated shield", fix_P7_overrated_shield),
        ("P8: field-size adjust", fix_P8_field_size_adjust),
    ]

    results = []
    for label, fn in fixes:
        print(f"\n🧪 {label}...")
        ov, cond, cls, fld = run_variant(races, fn, label)
        s = report_summary(ov, label)
        d = delta_report(bl_overall, ov)
        print(f"  Gold: {s['gold']}  |  Good: {s['good']}  |  Pass: {s['pass']}  |  Place: {s['top3_place']}  |  0H: {s['0hit']}")
        print(f"  ΔGold: {d['gold_delta']:+.1f}pp  |  ΔPass: {d['pass_delta']:+.1f}pp  |  ΔPlace: {d['place_delta']:+.1f}pp  |  Δ0H: {d['0hit_delta']:+d}")
        results.append((label, s, d))

    # Test best combo: all individual fixes that showed positive signal
    positive_fixes = [(l, f) for l, f in fixes if True]  # test all combos

    # Combo: P1+P2+P3+P4+P6+P7
    def combo_all(horses, race):
        horses = fix_P1_race_shape_dampen(horses, race)
        horses = fix_P2_track_boost(horses, race)
        horses = fix_P3_class_weight_rebalance(horses, race)
        horses = fix_P4_heavy_track_dampen(horses, race)
        horses = fix_P5_soft_track_adjust(horses, race)
        horses = fix_P6_near_miss_promote(horses, race)
        horses = fix_P7_overrated_shield(horses, race)
        horses = fix_P8_field_size_adjust(horses, race)
        return horses

    print(f"\n🧪 COMBO: All fixes...")
    ov, _, _, _ = run_variant(races, combo_all, "combo")
    s = report_summary(ov, "combo")
    d = delta_report(bl_overall, ov)
    print(f"  Gold: {s['gold']}  |  Good: {s['good']}  |  Pass: {s['pass']}  |  Place: {s['top3_place']}  |  0H: {s['0hit']}")
    print(f"  ΔGold: {d['gold_delta']:+.1f}pp  |  ΔPass: {d['pass_delta']:+.1f}pp  |  ΔPlace: {d['place_delta']:+.1f}pp  |  Δ0H: {d['0hit_delta']:+d}")
    results.append(("COMBO: All fixes", s, d))

    # Combo: only safe fixes (P1+P2+P4+P6)
    def combo_safe(horses, race):
        horses = fix_P1_race_shape_dampen(horses, race)
        horses = fix_P2_track_boost(horses, race)
        horses = fix_P4_heavy_track_dampen(horses, race)
        horses = fix_P6_near_miss_promote(horses, race)
        return horses

    print(f"\n🧪 COMBO: Safe subset (P1+P2+P4+P6)...")
    ov, _, _, _ = run_variant(races, combo_safe, "combo_safe")
    s = report_summary(ov, "combo_safe")
    d = delta_report(bl_overall, ov)
    print(f"  Gold: {s['gold']}  |  Good: {s['good']}  |  Pass: {s['pass']}  |  Place: {s['top3_place']}  |  0H: {s['0hit']}")
    print(f"  ΔGold: {d['gold_delta']:+.1f}pp  |  ΔPass: {d['pass_delta']:+.1f}pp  |  ΔPlace: {d['place_delta']:+.1f}pp  |  Δ0H: {d['0hit_delta']:+d}")
    results.append(("COMBO: Safe (P1+P2+P4+P6)", s, d))

    # Write report
    lines = [
        "# AU Wong Choi Targeted Post-Hoc Fix Test",
        "",
        "Post-hoc approach: start from stored rank_score, apply targeted adjustments.",
        "",
        f"Archive: `{len(races)}` races",
        "",
        "## Baseline",
        "",
        f"- Gold: `{bl_s['gold']}`",
        f"- Good: `{bl_s['good']}`",
        f"- Pass: `{bl_s['pass']}`",
        f"- Top3 Place: `{bl_s['top3_place']}`",
        f"- 0-hit: `{bl_s['0hit']}`",
        "",
        "## Results",
        "",
        "| Variant | Gold Δ | Pass Δ | Place Δ | 0-hit Δ | Verdict |",
        "|---|---:|---:|---:|---:|---|",
    ]

    for label, s, d in results:
        verdict = "✅" if d["pass_delta"] >= 0 and d["0hit_delta"] <= 0 else "❌"
        if d["gold_delta"] > 0 and d["0hit_delta"] <= 0:
            verdict = "✅✅"
        lines.append(f"| {label} | {d['gold_delta']:+.1f}pp | {d['pass_delta']:+.1f}pp | {d['place_delta']:+.1f}pp | {d['0hit_delta']:+d} | {verdict} |")

    lines.extend(["", "---", "", "## Fix Descriptions", ""])
    lines.append("- **P1**: Dampen race_shape when it's dominant but hard signals are weak (80% of zero-hit)")
    lines.append("- **P2**: Boost horses with strong track ability (most underestimated dimension)")
    lines.append("- **P3**: Penalize when class_weight is weak but stability/form_line are high")
    lines.append("- **P4**: Heavy track: dampen stability/sectional, boost track (1.8× zero-hit rate)")
    lines.append("- **P5**: Soft track: milder version of P4")
    lines.append("- **P6**: Promote horses ranked 4-6 with strong hard signals but weak soft signals")
    lines.append("- **P7**: Stronger overrated shield for stability+form_line traps")
    lines.append("- **P8**: Field-size based score compression/expansion")

    output_path = Path(args.output_md)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📄 Report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
