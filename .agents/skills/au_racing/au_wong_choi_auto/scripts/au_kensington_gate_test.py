#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from copy import deepcopy
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from au_sip_tester import evaluate_races, load_all_races, report_summary  # noqa: E402


PROJECT_ROOT = SCRIPT_DIR.parents[4]
KENSINGTON_DIR = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2026-06-10 Kensington Race 1-7"


def place_rerank_candidate(horses: list[dict], race: dict) -> list[dict]:
    ranked = sorted(horses, key=lambda h: (-float(h.get("rank_score", 0.0)), int(h.get("horse_number", 999))))
    top3_score = float(ranked[2]["rank_score"]) if len(ranked) >= 3 else 0.0
    for idx, horse in enumerate(ranked, start=1):
        if idx < 4 or idx > 6:
            continue
        matrix = horse.get("matrix_scores") or {}
        features = horse.get("feature_scores") or {}
        risk_flags = set(horse.get("risk_flags") or [])
        stability = float(matrix.get("stability", 60.0) or 60.0)
        form_line = float(matrix.get("form_line", 60.0) or 60.0)
        class_weight = float(matrix.get("class_weight", 60.0) or 60.0)
        race_shape = float(matrix.get("race_shape", 60.0) or 60.0)
        sectional = float(matrix.get("sectional", 60.0) or 60.0)
        jt = float(matrix.get("jockey_trainer", 60.0) or 60.0)
        trial = float(features.get("trial_score", 60.0) or 60.0)
        consistency = float(features.get("consistency_score", 60.0) or 60.0)

        if "high_consumption_load" in risk_flags:
            continue
        if stability < 68.0 or form_line < 66.0:
            continue
        if class_weight < 61.5:
            continue
        if max(jt, trial, consistency) < 67.0:
            continue
        if sectional >= 67.0 and race_shape >= 64.0:
            continue

        gap_to_top3 = top3_score - float(horse.get("rank_score", 0.0))
        bonus = 0.0
        if gap_to_top3 <= 3.0:
            bonus += 0.45
        if class_weight >= 62.0:
            bonus += 0.25
        if stability >= 70.0:
            bonus += 0.20
        if jt >= 64.0 and trial >= 65.0:
            bonus += 0.15
        horse["rank_score"] = float(horse.get("rank_score", 0.0)) + min(bonus, 1.05)
        horse["gate_bonus"] = round(min(bonus, 1.05), 4)
    return horses


def kensington_race7_summary() -> list[str]:
    csv_path = KENSINGTON_DIR / "Race_7_Auto_Scoring.csv"
    results_path = KENSINGTON_DIR / "Race_Results_Kensington_2026-06-10.json"
    rows = []
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            row["horse_number_int"] = int(float(row["horse_number"]))
            row["ability_score_float"] = float(row["ability_score"])
            rows.append(row)

    results = json.loads(results_path.read_text(encoding="utf-8"))
    race_results = results["results"]["7"]
    starters = {
        int(item["competitor_number"])
        for item in race_results
        if not item.get("is_scratched") and int(item.get("finish_position") or 99) > 0
    }
    actual_top3 = [
        int(item["competitor_number"])
        for item in sorted(race_results, key=lambda item: int(item.get("finish_position") or 99))
        if int(item.get("finish_position") or 99) in {1, 2, 3}
    ]

    baseline = sorted(rows, key=lambda row: (-row["ability_score_float"], row["horse_number_int"]))
    filtered = [row for row in baseline if row["horse_number_int"] in starters]

    candidate_horses = [
        {
            "horse_number": row["horse_number_int"],
            "horse_name": row["horse_name"],
            "rank_score": row["ability_score_float"],
            "actual_pos": actual_top3.index(row["horse_number_int"]) + 1 if row["horse_number_int"] in actual_top3 else 99,
            "matrix_scores": {},
            "feature_scores": {},
            "risk_flags": [],
        }
        for row in filtered
    ]
    logic = json.loads((KENSINGTON_DIR / "Race_7_Logic.json").read_text(encoding="utf-8"))
    for horse in candidate_horses:
        auto = logic["horses"][str(horse["horse_number"])]["python_auto"]
        horse["matrix_scores"] = auto.get("matrix_scores") or {}
        horse["feature_scores"] = auto.get("feature_scores") or {}
        horse["risk_flags"] = auto.get("risk_flags") or []
    candidate_ranked = sorted(place_rerank_candidate(deepcopy(candidate_horses), {}), key=lambda h: (-h["rank_score"], h["horse_number"]))

    def fmt(items):
        return " / ".join(f"#{row['horse_number_int']} {row['horse_name']}({row['ability_score_float']:.3f})" for row in items[:5])

    def fmt_candidate(items):
        return " / ".join(
            f"#{row['horse_number']} {row['horse_name']}({row['rank_score']:.3f}{', +'+str(row.get('gate_bonus')) if row.get('gate_bonus') else ''})"
            for row in items[:5]
        )

    return [
        f"Actual Top3: {actual_top3}",
        f"Baseline raw Top5: {fmt(baseline)}",
        f"Scratch-filtered Top5: {fmt(filtered)}",
        f"Candidate Top5: {fmt_candidate(candidate_ranked)}",
    ]


def main() -> None:
    races = load_all_races()
    baseline, _, _, _ = evaluate_races(races, "baseline")
    candidate, _, _, _ = evaluate_races(races, "place_rerank_candidate", place_rerank_candidate)
    print("KENSINGTON_R7")
    for line in kensington_race7_summary():
        print(f"- {line}")
    print()
    print("HISTORICAL_GATE")
    print(f"- Baseline: {report_summary(baseline, 'baseline')}")
    print(f"- Candidate: {report_summary(candidate, 'candidate')}")
    print(
        "- Delta: "
        f"gold {candidate['gold'] - baseline['gold']}, "
        f"good {candidate['good'] - baseline['good']}, "
        f"pass {candidate['minimum'] - baseline['minimum']}, "
        f"0hit {candidate['hit_distribution'][0] - baseline['hit_distribution'][0]}, "
        f"top3_places {candidate['top3_places'] - baseline['top3_places']}"
    )


if __name__ == "__main__":
    main()
