#!/usr/bin/env python3
"""
Shadow test for tactical matrix weight adjustments in AU Wong Choi Auto.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from unittest.mock import patch

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(PROJECT_ROOT / ".agents" / "scripts"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"))

from reflector_auto_stats import compute_race_stats
from au_review_auto_weighting import (
    _load_results_map,
    _logic_sort_key,
    find_au_meetings,
    meeting_results_file,
    summarize_race_stats,
    _build_field_summary,
    _facts_path_for_logic,
)
from engine_core import RacingEngine, enrich_logic_from_facts
import scoring

ARCHIVE_ROOT = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing"
OUTPUT_MD = ARCHIVE_ROOT / "AU_Tactical_Shadow_Test.md"

VARIANTS = {
    "baseline": {"tactical": False, "aggressive": False, "tightening": False},
    "tactical_only": {"tactical": True, "aggressive": False, "tightening": False},
    "tactical_aggressive": {"tactical": True, "aggressive": True, "tightening": False},
    "tightening_only": {"tactical": False, "aggressive": False, "tightening": True},
    "tactical_and_tightening": {"tactical": True, "aggressive": False, "tightening": True},
    "tactical_agg_and_tight": {"tactical": True, "aggressive": True, "tightening": True},
}

ORIGINAL_WEIGHTS_FUNC = scoring.get_dynamic_matrix_weights
ORIGINAL_TIGHTENING = dict(scoring.PLACE_TIGHTENING_FEATURE_WEIGHTS)

NEW_TIGHTENING = {
    "form_score": 0.103, "trial_score": 0.179, "trainer_score": 0.204,
    "jockey_horse_fit_score": 0.170, "consistency_score": 0.143,
    "distance_score": -0.033, "confidence_score": 0.027, "weight_score": -0.141,
    "sectional_score": 0.05
}

def get_simulated_weights(race_context, apply_tactical: bool, apply_aggressive: bool) -> dict:
    weights = dict(scoring.MATRIX_WEIGHTS)
    field_summary = race_context.get("field_summary",{})
    field_count = int(field_summary.get("count",0))
    going = str(race_context.get("going", race_context.get("meeting_intelligence", {}).get("going", "")) or "").lower()
    race_class = str(race_context.get("race_class","") or "").lower()
    
    scale = 2.0 if apply_aggressive else 1.0

    if field_count >= 13:
        weights["race_shape"] -= 0.02; weights["sectional"] -= 0.01; weights["stability"] += 0.02; weights["form_line"] += 0.01
    elif field_count >= 9:
        weights["race_shape"] -= 0.01; weights["sectional"] -= 0.005; weights["stability"] += 0.01; weights["form_line"] += 0.005
    elif apply_tactical and field_count <= 8:
        weights["race_shape"] += 0.02 * scale; weights["sectional"] += 0.015 * scale; weights["stability"] -= 0.01 * scale; weights["form_line"] -= 0.01 * scale

    if "soft" in going or "heavy" in going:
        weights["race_shape"] -= 0.005; weights["track"] += 0.01; weights["stability"] -= 0.005
    elif apply_tactical and ("good" in going or "firm" in going):
        weights["speed_performance"] += 0.015 * scale; weights["sectional"] += 0.01 * scale; weights["track"] -= 0.01 * scale

    if "bm" in race_class:
        bm_tokens = tuple(f"bm{n}" for n in range(50,100))
        if apply_tactical and any(t in race_class for t in ("bm58", "bm64", "bm68", "bm70")):
            weights["stability"] += 0.015 * scale
            weights["jockey_trainer"] += 0.01 * scale
            weights["class_weight"] -= 0.01 * scale
        elif any(t in race_class for t in bm_tokens): 
            weights["class_weight"] += 0.005

    total = sum(weights.values())
    if total > 0:
        for key in weights: weights[key] = weights[key] / total
    for key, floor_val in scoring._WEIGHT_FLOOR.items():
        if weights[key] < floor_val: weights[key] = floor_val
    for key, ceil_val in scoring._WEIGHT_CEILING.items():
        if weights[key] > ceil_val: weights[key] = ceil_val
    for key in weights: weights[key] = round(weights[key],4)
    return weights


def _ranked_picks_from_logic(logic_path: pathlib.Path, variant: dict) -> list:
    logic_data = json.loads(logic_path.read_text(encoding="utf-8"))
    race = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
    race_number = race.get("race_number")
    facts_path = _facts_path_for_logic(logic_path, int(race_number) if str(race_number).isdigit() else None)
    if facts_path and facts_path.exists():
        logic_data = enrich_logic_from_facts(logic_data, facts_path)
        race = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
    race["field_summary"] = _build_field_summary(logic_data.get("horses", {}))
    
    ranked = []
    
    # Monkey patch engine_core
    def mock_get_weights(ctx):
        return get_simulated_weights(ctx, variant["tactical"], variant["aggressive"])
    
    import engine_core
    original_get = engine_core.get_dynamic_matrix_weights
    original_tight = engine_core.PLACE_TIGHTENING_FEATURE_WEIGHTS
    
    engine_core.get_dynamic_matrix_weights = mock_get_weights
    if variant["tightening"]:
        engine_core.PLACE_TIGHTENING_FEATURE_WEIGHTS = NEW_TIGHTENING
        
    try:
        for horse_num, horse in logic_data.get("horses", {}).items():
            try: horse_number = int(horse_num)
            except: horse_number = 999
            
            engine = RacingEngine(horse, race, facts_section=horse.get("_data", {}).get("facts_section", ""), facts_path=facts_path)
            auto = engine.analyze_horse()
            
            ranked.append({
                "horse_number": horse_number,
                "horse_name": str(horse.get("horse_name", "")),
                "rank_score": float(auto.get("rank_score", 0)),
                "ability_score": float(auto.get("ability_score", 0)),
            })
    finally:
        engine_core.get_dynamic_matrix_weights = original_get
        engine_core.PLACE_TIGHTENING_FEATURE_WEIGHTS = original_tight

    ranked.sort(key=lambda row: (-row["rank_score"], -row["ability_score"], row["horse_number"]))
    picks = [(idx, row["horse_number"], row["horse_name"]) for idx, row in enumerate(ranked[:4], start=1)]
    return picks

def run_variant(base_dir: pathlib.Path, variant_name: str, variant: dict) -> dict:
    meetings = find_au_meetings(base_dir)
    aggregate = {
        "meetings": len(meetings),
        "races": 0, "Champion": 0, "Gold": 0, "Good": 0, "Minimum": 0,
        "MRR": 0.0, "Order Issue": 0, "Avg Top4 Hits": 0.0
    }
    mrr_weighted, top4_weighted, total_races = 0.0, 0.0, 0
    
    for meeting in meetings:
        results_file = meeting_results_file(meeting)
        if not results_file: continue
        results_map = _load_results_map(results_file)
        race_stats = []
        for logic_path in sorted(meeting.glob("Race_*_Logic.json"), key=_logic_sort_key):
            race_num = _logic_sort_key(logic_path)
            results = results_map.get(race_num, [])
            if not results: continue
            picks = _ranked_picks_from_logic(logic_path, variant)
            if not picks: continue
            stats = compute_race_stats(picks, results, {})
            stats.race_num = race_num
            race_stats.append(stats)
            
        summary = summarize_race_stats(race_stats)
        races = summary["races"]
        if not races: continue
        total_races += races
        aggregate["Champion"] += summary["Champion"]
        aggregate["Gold"] += summary["Gold"]
        aggregate["Good"] += summary["Good"]
        aggregate["Minimum"] += summary["Minimum"]
        aggregate["Order Issue"] += summary["Order Issue"]
        mrr_weighted += summary["MRR"] * races
        top4_weighted += summary["Avg Top4 Hits"] * races

    aggregate["races"] = total_races
    aggregate["MRR"] = round(mrr_weighted / total_races, 4) if total_races else 0.0
    aggregate["Avg Top4 Hits"] = round(top4_weighted / total_races, 3) if total_races else 0.0
    return {"variant": variant_name, "current_live": aggregate}

def _pct(count, total): return f"{(count / total * 100.0):.1f}%" if total else "0.0%"

def main():
    print("Running tactical shadow test for AU Wong Choi...")
    base_dir = ARCHIVE_ROOT
    results = [run_variant(base_dir, name, config) for name, config in VARIANTS.items()]
    
    baseline = results[0]["current_live"]
    lines = ["# AU Tactical Adjustments Shadow Test\n", "## Baseline"]
    lines.append(f"- Races: **{baseline['races']}**")
    lines.append(f"- Champion: **{baseline['Champion']} / {baseline['races']} = {_pct(baseline['Champion'], baseline['races'])}**")
    lines.append(f"- Good: **{baseline['Good']} / {baseline['races']} = {_pct(baseline['Good'], baseline['races'])}**")
    lines.append(f"- Pass: **{baseline['Minimum']} / {baseline['races']} = {_pct(baseline['Minimum'], baseline['races'])}**")
    lines.append(f"- Order Issue: **{baseline['Order Issue']}**\n")
    
    lines.append("## Variants\n| Variant | Champion | Gold | Good | Pass | MRR | Order | Avg Top4 Hits | Delta |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    
    for row in results:
        current = row["current_live"]
        dp = current['Minimum'] - baseline['Minimum']
        dc = current['Champion'] - baseline['Champion']
        do = current['Order Issue'] - baseline['Order Issue']
        lines.append(
            f"| {row['variant']} | {current['Champion']} | {current['Gold']} | {current['Good']} | {current['Minimum']} "
            f"| {current['MRR']:.4f} | {current['Order Issue']} | {current['Avg Top4 Hits']:.3f} "
            f"| C {dc:+d} / Pass {dp:+d} / Order {do:+d} |"
        )
        
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    for line in lines:
        if "|" in line or "Races" in line:
            print(line)

if __name__ == "__main__":
    main()
