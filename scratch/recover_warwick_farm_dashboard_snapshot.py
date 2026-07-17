#!/usr/bin/env python3
"""Recover the 2026-07-15 Warwick Farm AU artifacts from a deployed snapshot.

This is deliberately a mechanical recovery: it preserves the dashboard order,
grades, scores, and report text without rerunning the racing engine.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path


MEETING_KEY = "2026-07-15|Warwick Farm"
FEATURE_KEYS = (
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
    "pace_figure_score",
)
FIELDS = (
    "race_number",
    "horse_number",
    "horse_name",
    "jockey",
    "trainer",
    "rank",
    "pure_7d_score",
    "base_7d_score",
    "final_rank_score",
    "ability_score",
    "wet_form_feature",
    "grade",
    "model_pick_status",
    "watchlist_level",
    "watchlist_reasons",
    *FEATURE_KEYS,
)
FEATURE_LABELS = {
    "form_score": "近績分",
    "trial_score": "試閘分",
    "sectional_score": "段速分",
    "pace_map_score": "形勢分",
    "jockey_score": "騎師分",
    "trainer_score": "練馬師分",
    "jockey_horse_fit_score": "人馬配搭分",
    "class_score": "級數分",
    "rating_score": "Rating 分",
    "weight_score": "負磅分",
    "distance_score": "路程分",
    "track_score": "場地分",
    "formline_score": "賽績線分",
    "consistency_score": "穩定性分",
    "health_score": "健康分",
    "confidence_score": "信心分",
    "pace_figure_score": "段速實速分",
}


def extract_dashboard_data(html_path: Path) -> dict:
    html = html_path.read_text(encoding="utf-8")
    match = re.search(r"const DASHBOARD_DATA = (.*?);\n", html, re.DOTALL)
    if not match:
        raise ValueError("DASHBOARD_DATA was not found in the downloaded snapshot")
    return json.loads(match.group(1))


def first_float(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def feature_value(text: str, label: str) -> float | None:
    patterns = (
        rf"(?:^|\n)\s*-\s*{re.escape(label)}\s+(-?\d+(?:\.\d+)?)\s*[←x×]",
        rf"{re.escape(label)}\s*[:：]?\s*(-?\d+(?:\.\d+)?)",
    )
    for pattern in patterns:
        value = first_float(text, pattern)
        if value is not None:
            return value
    return None


def recovered_row(race_num: int, rank: int, horse: dict) -> dict:
    raw = horse.get("raw_text") or ""
    ability = first_float(raw, r"綜合戰力分:\s*\*\*(-?\d+(?:\.\d+)?)")
    pure = first_float(raw, r"official 7D clean ranking score\s*=\s*(-?\d+(?:\.\d+)?)")
    if pure is None:
        pure = first_float(raw, r"官方 7D clean ranking score\s*=\s*(-?\d+(?:\.\d+)?)")
    if ability is None:
        raise ValueError(f"Missing ability score for R{race_num} #{horse.get('horse_number')}")
    if pure is None:
        pure = ability
    row = {
        "race_number": race_num,
        "horse_number": horse.get("horse_number"),
        "horse_name": horse.get("horse_name") or "",
        "jockey": horse.get("jockey") or "",
        "trainer": horse.get("trainer") or "",
        "rank": rank,
        "pure_7d_score": pure,
        "base_7d_score": pure,
        "final_rank_score": ability,
        "ability_score": ability,
        "wet_form_feature": round(ability - pure, 4),
        "grade": horse.get("final_grade") or "",
        "model_pick_status": horse.get("model_pick_status") or "",
        "watchlist_level": horse.get("underhorse_level") or "",
        "watchlist_reasons": horse.get("underhorse_reason") or "",
    }
    for key, label in FEATURE_LABELS.items():
        row[key] = feature_value(raw, label)
    return row


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} DASHBOARD_HTML OUTPUT_DIR")
    html_path = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data = extract_dashboard_data(html_path)
    races = data["races"][MEETING_KEY]["races_by_analyst"]["Kelvin"]
    all_rows: list[dict] = []
    manifest = {
        "source": "https://wongchoi-dashboard.pages.dev",
        "dashboard_generated_at": data.get("meta", {}).get("generated_at"),
        "meeting_key": MEETING_KEY,
        "recovery_method": "mechanical extraction; no model rerun or result-based score changes",
        "races": [],
    }
    for race in races:
        race_num = int(race["race_number"])
        rows = [
            recovered_row(race_num, rank, horse)
            for rank, horse in enumerate(race["horses"], start=1)
        ]
        all_rows.extend(rows)
        write_csv(output_dir / f"Race_{race_num}_Auto_Scoring.csv", rows)
        report = "\n\n---\n\n".join(horse.get("raw_text") or "" for horse in race["horses"])
        top = race.get("top_picks") or []
        report += "\n\n## Snapshot Top 4\n\n"
        for pick in top[:4]:
            report += f"Top {pick['rank']}: #{pick['horse_number']} {pick['horse_name']}\n"
        (output_dir / f"Race_{race_num}_Auto_Analysis.md").write_text(report, encoding="utf-8")
        manifest["races"].append(
            {
                "race_number": race_num,
                "top4": [
                    [pick["horse_number"], pick["horse_name"], pick.get("grade")]
                    for pick in top[:4]
                ],
                "runner_count": len(rows),
            }
        )
    write_csv(output_dir / "Meeting_Auto_Scoring.csv", all_rows)
    (output_dir / "Dashboard_Snapshot_Recovery.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Recovered {len(races)} races and {len(all_rows)} scoring rows into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
