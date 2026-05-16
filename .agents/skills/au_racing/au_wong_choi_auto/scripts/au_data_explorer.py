#!/usr/bin/env python3
"""
AU Data Explorer — catalogues all available data fields across the archive,
identifying which are used in scoring vs loaded-but-unused.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# Match other scripts' path resolution
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))
from au_archive_calibrator import ARCHIVE_ROOT as ARCHIVE_DIR

# Fields that enrich_logic_from_facts() loads into _data
LOADED_DATA_FIELDS = [
    "last10_raw", "recent_form", "career_record_line", "engine_line",
    "formline_line", "consumption_summary", "sectional_trend_line",
    "running_style_line", "style_confidence_line", "engine_type_line",
    "engine_confidence_line", "distance_profile_line", "target_distance_line",
    "class_move", "formal_count", "trial_count", "trial_top3_count",
    "track_record_line", "track_stats_line", "going_stats_line",
    "stage_stats_line", "facts_section", "last_finish_line", "warning_line",
    "sire_line", "current_market_line", "current_market_first",
    "current_market_last", "current_market_low", "current_market_trend",
    "latest_official_jockey", "latest_official_last_flucs",
    "latest_official_market_trend", "latest_official_jockey_formal_rides",
    "latest_official_jockey_formal_places", "latest_official_jockey_formal_wins",
    "latest_trial_jockey", "current_jockey_formal_rides",
    "current_jockey_formal_places", "current_jockey_formal_wins",
    "current_jockey_trial_rides", "current_jockey_trial_top3",
    "current_jockey_history_line", "best_formal_jockey",
    "best_formal_jockey_rides", "best_formal_jockey_places",
    "best_formal_jockey_wins", "best_jockey_history_line",
    "current_vs_best_jockey_line", "known_jockeys_line",
    "jockey_change_signal", "official_market_support_count",
    "official_market_miss_count", "recent_settled_pattern_line",
    "recent_400_pattern_line", "recent_shape_consensus",
    "recent_shape_entropy", "recent_shape_consensus_count",
    "recent_shape_front_count", "recent_shape_mid_count",
    "recent_shape_back_count", "recent_shape_inside_count",
    "recent_shape_wide_no_cover_count", "recent_shape_early_work_count",
    "recent_shape_summary_line",
]

# Fields that are USED in scoring functions (_form_score, _sectional_score, etc.)
USED_IN_SCORING = {
    "recent_form",           # _form_score, _stability_score, _health_score
    "career_record_line",    # _consistency_score
    "engine_line",           # _sectional_score, _distance_score
    "formline_line",         # _formline_score, _health_score, _formline_level, _formline_followup_counts
    "consumption_summary",   # _health_score, _consumption_summary, _consumption_weighted_score
    "sectional_trend_line",  # _sectional_trends (used in _form_score, _distance_score for display)
    "engine_type_line",      # _sectional_score (engine_type)
    "engine_confidence_line",# _sectional_score (engine_conf)
    "target_distance_line",  # _distance_score, _sectional_score
    "class_move",            # _class_score, _weight_score
    "trial_count",           # _class_score, _weight_score, _sectional_score
    "trial_top3_count",      # _class_score, _weight_score
    "track_record_line",     # _track_score
    "track_stats_line",      # _same_track_stats
    "going_stats_line",      # _going_stats, _track_score
    "stage_stats_line",      # _stage_stats
    "warning_line",          # _has_last10_warning, confidence
    "running_style_line",    # _running_style (fallback)
    "style_confidence_line", # _style_confidence
    # Jockey data
    "current_jockey_formal_rides",  # confidence, jockey_horse_fit
    "current_jockey_formal_places",
    "current_jockey_formal_wins",
    "current_jockey_trial_rides",
    "current_jockey_trial_top3",
    "latest_official_jockey",
    "best_formal_jockey",
    "current_jockey_history_line",
    "best_jockey_history_line",
    "current_vs_best_jockey_line",
    "jockey_change_signal",
}

# Fields loaded but NOT used in scoring
UNUSED_IN_SCORING = set(LOADED_DATA_FIELDS) - USED_IN_SCORING - {
    # Market odds fields (not allowed per user instructions)
    "current_market_line", "current_market_first", "current_market_last",
    "current_market_low", "current_market_trend",
    "latest_official_last_flucs", "latest_official_market_trend",
    "official_market_support_count", "official_market_miss_count",
}

# High-potential unused fields for scoring improvements
HIGH_POTENTIAL_UNUSED = [
    "recent_settled_pattern_line",   # settled positions in recent 4 races → race_shape
    "recent_400_pattern_line",       # position at 400m in recent 4 → race_shape/sectional
    "recent_shape_consensus",        # front/mid/back consensus → race_shape
    "recent_shape_entropy",          # positional entropy → race_shape
    "recent_shape_consensus_count",  # how many races match consensus → race_shape
    "recent_shape_front_count",      # front-running count → race_shape
    "recent_shape_mid_count",
    "recent_shape_back_count",
    "recent_shape_inside_count",     # inside runs → race_shape/track
    "recent_shape_wide_no_cover_count",  # wide/no cover → race_shape (forgiveness signal)
    "recent_shape_early_work_count",     # early work → race_shape (consumption signal)
    "recent_shape_summary_line",     # text summary
    "distance_profile_line",         # best distance / distance range
    "last10_raw",                    # raw last 10 form
    "formal_count",                  # formal race count
    "facts_section",                 # full facts text (rich, but unstructured)
    "sire_line",                     # breeding info → could inform track/going
]


def scan_archive():
    races = []
    horse_field_avail = Counter()
    horse_field_missing = Counter()
    total_horses = 0
    total_races = 0

    for meeting_dir in sorted(ARCHIVE_DIR.iterdir()):
        if not meeting_dir.is_dir():
            continue
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"))
        if not logic_files:
            continue

        for lf in logic_files:
            try:
                data = json.loads(lf.read_text(encoding="utf-8"))
            except Exception:
                continue

            horses = data.get("horses", {})
            if not horses:
                continue

            total_races += 1
            for hnum, hdata in horses.items():
                total_horses += 1
                hdata_data = hdata.get("_data", {}) if isinstance(hdata.get("_data"), dict) else {}

                for field in LOADED_DATA_FIELDS:
                    value = hdata_data.get(field)
                    if value not in (None, "", "N/A", "Unknown", 0, "0"):
                        horse_field_avail[field] += 1
                    else:
                        horse_field_missing[field] += 1

            races.append({"meeting": meeting_dir.name, "race": lf.stem})

    return races, total_horses, total_races, horse_field_avail, horse_field_missing


def main():
    print("=" * 80)
    print("AU DATA EXPLORER — Available vs Used Data Fields Audit")
    print("=" * 80)

    races, total_horses, total_races, avail, missing = scan_archive()
    print(f"\n📊 Total: {total_races} races, {total_horses} horse entries\n")

    # 1. Unused but available
    print("━" * 80)
    print("🔍 HIGH-POTENTIAL UNUSED FIELDS (loaded but not scored)")
    print("━" * 80)
    print(f"{'Field':<40} {'Available':>10} {'Avail%':>8} {'Missing':>10}")
    print("-" * 69)
    for field in HIGH_POTENTIAL_UNUSED:
        a = avail.get(field, 0)
        m = missing.get(field, 0)
        pct = (a / total_horses * 100) if total_horses else 0
        print(f"{field:<40} {a:>10} {pct:>7.1f}% {m:>10}")

    # 2. Used fields that are often missing (data gaps)
    print("\n" + "━" * 80)
    print("⚠️  SCORED FIELDS WITH HIGH MISSING RATES (data gaps)")
    print("━" * 80)
    print(f"{'Field':<40} {'Available':>10} {'Avail%':>8} {'Missing':>10}")
    print("-" * 69)
    scored_missing = [(f, missing.get(f, 0), avail.get(f, 0)) for f in USED_IN_SCORING]
    scored_missing.sort(key=lambda x: -x[1])
    for field, miss, avl in scored_missing[:20]:
        pct = (avl / total_horses * 100) if total_horses else 0
        print(f"{field:<40} {avl:>10} {pct:>7.1f}% {miss:>10}")

    # 3. Summary stats for key improvement areas
    print("\n" + "━" * 80)
    print("📋 IMPROVEMENT-READY STATS")
    print("━" * 80)

    # Shape stats
    for label, fields in [
        ("Race Shape (settled patterns)", ["recent_settled_pattern_line", "recent_shape_consensus", "recent_shape_entropy"]),
        ("Race Shape (counts)", ["recent_shape_front_count", "recent_shape_mid_count", "recent_shape_back_count"]),
        ("Race Shape (trip quality)", ["recent_shape_inside_count", "recent_shape_wide_no_cover_count", "recent_shape_early_work_count"]),
        ("Sectional Enhancement", ["sectional_trend_line", "distance_profile_line"]),
        ("Consumption/Health", ["consumption_summary"]),
    ]:
        total_avail = sum(avail.get(f, 0) for f in fields)
        avg_pct = (total_avail / (len(fields) * total_horses) * 100) if total_horses else 0
        print(f"  {label}: avg {avg_pct:.1f}% available across {len(fields)} fields")

    # 4. Output JSON for programmatic use
    output = {
        "total_races": total_races,
        "total_horses": total_horses,
        "high_potential_unused": {
            field: {"available": avail.get(field, 0), "missing": missing.get(field, 0)}
            for field in HIGH_POTENTIAL_UNUSED
        },
        "scored_missing": {
            field: {"available": avail.get(field, 0), "missing": missing.get(field, 0)}
            for field, _, _ in scored_missing[:20]
        },
    }

    out_path = ARCHIVE_DIR / "AU_Data_Explorer_Report.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n✅ Full report saved to {out_path}")


if __name__ == "__main__":
    main()