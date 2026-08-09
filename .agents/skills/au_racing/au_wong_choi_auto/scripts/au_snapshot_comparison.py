#!/usr/bin/env python3
"""Canonical paired comparison of two aligned AU runtime snapshots."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_eval import baseline_report, compare, default_scorer, verdict_dict  # noqa: E402
from io_utils import write_json_atomic, write_text_atomic  # noqa: E402


def race_key(race: dict) -> tuple:
    meta = race.get("metadata") or {}
    return meta.get("date"), meta.get("track"), int(meta.get("race_number") or 0)


def row_key(row: dict) -> tuple:
    return int(row.get("horse_number") or 0), str(row.get("horse_name") or "").lower()


def align(base: dict, candidate: dict) -> list[dict]:
    candidates = {race_key(race): race for race in candidate["races"]}
    aligned = []
    for base_race in base["races"]:
        key = race_key(base_race)
        candidate_race = candidates.get(key)
        if candidate_race is None:
            raise ValueError(f"Candidate is missing race {key}")
        candidate_rows = {row_key(row): row for row in candidate_race["rows"]}
        rows = []
        for base_row in base_race["rows"]:
            candidate_row = candidate_rows.get(row_key(base_row))
            if candidate_row is None:
                raise ValueError(f"Candidate is missing runner {key} / {row_key(base_row)}")
            if int(base_row["actual_pos"]) != int(candidate_row["actual_pos"]):
                raise ValueError(f"Outcome mismatch {key} / {row_key(base_row)}")
            rows.append({
                **base_row,
                "features": base_row.get("features", base_row.get("feature_scores", {})),
                "wet": base_row.get("wet", base_row.get("wet_form_feature", 0.0)),
                "pos": base_row.get("pos", base_row.get("actual_pos")),
                "candidate_features": candidate_row.get("feature_scores", {}),
                "candidate_wet": candidate_row.get("wet_form_feature", 0.0),
            })
        aligned.append({
            **base_race,
            "date": key[0],
            "rows": rows,
        })
    if len(aligned) != len(candidate["races"]):
        raise ValueError("Snapshot race counts differ")
    return aligned


def candidate_scorer(row: dict) -> float:
    return default_scorer({
        **row,
        "features": row["candidate_features"],
        "wet": row["candidate_wet"],
    })


def render(report: dict) -> str:
    verdict = report["verdict"]
    ci = verdict["top_hold_ci"]
    lines = [
        "# AU Runtime Snapshot Comparison",
        "",
        f"Base: `{report['design']['base']}`",
        f"Candidate: `{report['design']['candidate']}`",
        "",
        f"- Development Top-5 AUC Δ: {verdict['top_dev']:+.5f}",
        f"- Terminal Top-5 AUC Δ: {verdict['top_hold']:+.5f} "
        f"(95% CI [{ci[0]:+.5f}, {ci[1]:+.5f}])",
        f"- Canonical promotion: {'PASS' if verdict['ship'] else 'NO PASS'} — {verdict['reason']}",
        "- Context metric deltas: " + ", ".join(
            f"{key} {value:+.2f}pp" for key, value in verdict["counts"].items()
        ),
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-json", type=Path, required=True)
    parser.add_argument("--candidate-json", type=Path, required=True)
    parser.add_argument("--label", default="runtime snapshot candidate")
    parser.add_argument("--output-json", type=Path, default=Path("/private/tmp/au_snapshot_comparison.json"))
    parser.add_argument("--output-md", type=Path, default=Path("/private/tmp/au_snapshot_comparison.md"))
    args = parser.parse_args()
    base = json.loads(args.base_json.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate_json.read_text(encoding="utf-8"))
    races = align(base, candidate)
    verdict = compare(races, default_scorer, candidate_scorer, label=args.label)
    report = {
        "design": {
            "base": str(args.base_json),
            "candidate": str(args.candidate_json),
            "races": len(races),
        },
        "base": baseline_report(races, scorer=default_scorer),
        "candidate": baseline_report(races, scorer=candidate_scorer),
        "verdict": verdict_dict(verdict),
    }
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render(report))
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
