#!/usr/bin/env python3
"""
Shadow benchmark for targeted AU formula bundles.

This does not change live engine behaviour. It re-ranks archive meetings by
monkey-patching imported engine_core helpers during the backtest run.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
from dataclasses import asdict

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(PROJECT_ROOT / ".agents" / "scripts"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"))

from reflector_auto_stats import compute_race_stats
from au_review_auto_weighting import (
    _build_field_summary,
    _facts_path_for_logic,
    _load_results_map,
    _logic_sort_key,
    find_au_meetings,
    meeting_results_file,
    summarize_race_stats,
)
from engine_core import RacingEngine, enrich_logic_from_facts
import engine_core
from matrix_mapper import MATRIX_FORMULAS
from scoring import clip_score


ARCHIVE_ROOT = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing"
OUTPUT_MD = ARCHIVE_ROOT / "AU_Shadow_Bundle_Benchmark.md"

ORIGINAL_FORMULAS = {key: tuple(value) for key, value in MATRIX_FORMULAS.items()}

FORMULA_PRESETS = {
    "sectional_speed_heavy": {
        "sectional": (("sectional_score", 0.75), ("distance_score", 0.15), ("trial_score", 0.10)),
    },
    "jt_fit_tempered": {
        "jockey_trainer": (
            ("jockey_score", 0.35),
            ("trainer_score", 0.25),
            ("jockey_horse_fit_score", 0.40),
        ),
    },
    "class_weight_class_only": {
        "class_weight": (("class_score", 1.0),),
    },
    "formline_purer": {
        "form_line": (("formline_score", 0.82), ("form_score", 0.18)),
    },
}

VARIANTS = {
    "baseline": {
        "formula_names": (),
        "place_scale": 1.4,
        "wet_only_sections": (),
    },
    "bundle_conservative": {
        "formula_names": ("sectional_speed_heavy", "jt_fit_tempered", "class_weight_class_only"),
        "place_scale": 0.7,
        "wet_only_sections": (),
    },
    "bundle_recommended": {
        "formula_names": ("sectional_speed_heavy", "jt_fit_tempered", "class_weight_class_only", "formline_purer"),
        "place_scale": 0.7,
        "wet_only_sections": (),
    },
    "bundle_wet_sectional": {
        "formula_names": ("sectional_speed_heavy", "jt_fit_tempered", "class_weight_class_only", "formline_purer"),
        "place_scale": 0.7,
        "wet_only_sections": ("sectional",),
    },
}


def merge_formulas(formula_names: tuple[str, ...]) -> dict[str, tuple[tuple[str, float], ...]]:
    formulas = {key: tuple(value) for key, value in ORIGINAL_FORMULAS.items()}
    for name in formula_names:
        overrides = FORMULA_PRESETS[name]
        for section, components in overrides.items():
            formulas[section] = tuple(components)
    return formulas


def build_formula_functions(
    formulas: dict[str, tuple[tuple[str, float], ...]],
    going: str,
    wet_only_sections: tuple[str, ...],
):
    is_wet = str(going or "").lower().startswith(("soft", "heavy"))

    def map_scores(features: dict) -> dict[str, float]:
        matrix_scores = {}
        for key, components in ORIGINAL_FORMULAS.items():
            use_components = formulas[key]
            if key in wet_only_sections and not is_wet:
                use_components = components
            score = 0.0
            for feature_name, weight in use_components:
                score += clip_score(features.get(feature_name, 60.0)) * weight
            matrix_scores[key] = round(clip_score(score), 2)
        return matrix_scores

    def map_matrix(features: dict) -> dict[str, str]:
        scores = map_scores(features)
        matrix = {}
        for key, score in scores.items():
            if score >= 85:
                matrix[key] = "✅✅"
            elif score >= 70:
                matrix[key] = "✅"
            elif score >= 55:
                matrix[key] = "➖"
            elif score >= 40:
                matrix[key] = "❌"
            else:
                matrix[key] = "❌❌"
        return matrix

    return map_scores, map_matrix


def _ranked_picks_from_logic(logic_path: pathlib.Path, variant: dict) -> list[tuple[int, int, str]]:
    logic_data = json.loads(logic_path.read_text(encoding="utf-8"))
    race = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
    race_number = race.get("race_number")
    facts_path = _facts_path_for_logic(logic_path, int(race_number) if str(race_number).isdigit() else None)
    if facts_path and facts_path.exists():
        logic_data = enrich_logic_from_facts(logic_data, facts_path)
        race = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
    race["field_summary"] = _build_field_summary(logic_data.get("horses", {}))

    formulas = merge_formulas(variant["formula_names"])
    map_scores, map_matrix = build_formula_functions(formulas, race.get("going", ""), tuple(variant.get("wet_only_sections", ())))

    original_map_scores = engine_core.map_features_to_matrix_scores
    original_map_matrix = engine_core.map_features_to_matrix
    original_place_scale = engine_core.PLACE_TIGHTENING_SCALE

    ranked = []
    engine_core.map_features_to_matrix_scores = map_scores
    engine_core.map_features_to_matrix = map_matrix
    engine_core.PLACE_TIGHTENING_SCALE = variant["place_scale"]
    try:
        for horse_num, horse in logic_data.get("horses", {}).items():
            try:
                horse_number = int(horse_num)
            except (TypeError, ValueError):
                horse_number = 999
            auto = RacingEngine(
                horse,
                race,
                facts_section=horse.get("_data", {}).get("facts_section", ""),
                facts_path=facts_path,
            ).analyze_horse()
            ranked.append(
                {
                    "horse_number": horse_number,
                    "horse_name": str(horse.get("horse_name") or "").strip(),
                    "rank_score": float(auto.get("rank_score", 0.0) or 0.0),
                    "ability_score": float(auto.get("ability_score", 0.0) or 0.0),
                }
            )
    finally:
        engine_core.map_features_to_matrix_scores = original_map_scores
        engine_core.map_features_to_matrix = original_map_matrix
        engine_core.PLACE_TIGHTENING_SCALE = original_place_scale

    ranked.sort(key=lambda row: (-row["rank_score"], -row["ability_score"], row["horse_number"]))
    return [(idx, row["horse_number"], row["horse_name"]) for idx, row in enumerate(ranked[:4], start=1)]


def run_variant(base_dir: pathlib.Path, variant_name: str, variant: dict) -> dict:
    meetings = find_au_meetings(base_dir)
    started = time.perf_counter()
    aggregate = {
        "meetings": len(meetings),
        "races": 0,
        "Champion": 0,
        "Gold": 0,
        "Good": 0,
        "Minimum": 0,
        "MRR": 0.0,
        "Order Issue": 0,
        "Avg Top4 Hits": 0.0,
    }
    mrr_weighted = 0.0
    top4_weighted = 0.0
    total_races = 0
    details = []

    for index, meeting in enumerate(meetings, start=1):
        meeting_started = time.perf_counter()
        print(f"🔍 AU bundle shadow [{variant_name}]: {index}/{len(meetings)} {meeting.name}", flush=True)
        results_file = meeting_results_file(meeting)
        if not results_file:
            continue
        results_map = _load_results_map(results_file)
        race_stats = []
        for logic_path in sorted(meeting.glob("Race_*_Logic.json"), key=_logic_sort_key):
            race_num = _logic_sort_key(logic_path)
            results = results_map.get(race_num, [])
            if not results:
                continue
            picks = _ranked_picks_from_logic(logic_path, variant)
            if not picks:
                continue
            stats = compute_race_stats(picks, results, {})
            stats.race_num = race_num
            race_stats.append(stats)

        summary = summarize_race_stats(race_stats)
        races = summary["races"]
        if not races:
            continue
        total_races += races
        aggregate["Champion"] += summary["Champion"]
        aggregate["Gold"] += summary["Gold"]
        aggregate["Good"] += summary["Good"]
        aggregate["Minimum"] += summary["Minimum"]
        aggregate["Order Issue"] += summary["Order Issue"]
        mrr_weighted += summary["MRR"] * races
        top4_weighted += summary["Avg Top4 Hits"] * races
        details.append(
            {
                "meeting": meeting.name,
                **summary,
                "races_detail": [asdict(item) for item in race_stats],
            }
        )
        print(
            f"✅ AU bundle shadow [{variant_name}]: {meeting.name} "
            f"({races} races, {time.perf_counter() - meeting_started:.2f}s, total {time.perf_counter() - started:.2f}s)",
            flush=True,
        )

    aggregate["races"] = total_races
    aggregate["MRR"] = round(mrr_weighted / total_races, 4) if total_races else 0.0
    aggregate["Avg Top4 Hits"] = round(top4_weighted / total_races, 3) if total_races else 0.0
    return {"variant": variant_name, "current_live": aggregate, "details": details}


def _pct(count: int, total: int) -> str:
    return f"{(count / total * 100.0):.1f}%" if total else "0.0%"


def main() -> int:
    base_dir = ARCHIVE_ROOT
    results = [run_variant(base_dir, name, config) for name, config in VARIANTS.items()]
    baseline = results[0]["current_live"]

    lines = [
        "# AU Shadow Bundle Benchmark",
        "",
        "## Baseline",
        f"- Races: **{baseline['races']}**",
        f"- Champion: **{baseline['Champion']} / {baseline['races']} = {_pct(baseline['Champion'], baseline['races'])}**",
        f"- Good: **{baseline['Good']} / {baseline['races']} = {_pct(baseline['Good'], baseline['races'])}**",
        f"- Pass: **{baseline['Minimum']} / {baseline['races']} = {_pct(baseline['Minimum'], baseline['races'])}**",
        f"- Order Issue: **{baseline['Order Issue']}**",
        "",
        "## Variants",
        "",
        "| Variant | Champion | Gold | Good | Pass | MRR | Order | Avg Top4 Hits | Delta |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for row in results:
        current = row["current_live"]
        delta_pass = current["Minimum"] - baseline["Minimum"]
        delta_good = current["Good"] - baseline["Good"]
        delta_champion = current["Champion"] - baseline["Champion"]
        delta_order = current["Order Issue"] - baseline["Order Issue"]
        lines.append(
            f"| {row['variant']} | {current['Champion']} | {current['Gold']} | {current['Good']} | {current['Minimum']} "
            f"| {current['MRR']:.4f} | {current['Order Issue']} | {current['Avg Top4 Hits']:.3f} "
            f"| C {delta_champion:+d} / Good {delta_good:+d} / Pass {delta_pass:+d} / Order {delta_order:+d} |"
        )

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    for line in lines:
        if "|" in line or line.startswith("- Races"):
            print(line)
    print(f"Wrote {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
