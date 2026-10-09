#!/usr/bin/env python3
"""Blind prospective monitor for EXP-20260927-02.

Before the locked sample reaches 2,000 races, this command writes data-health
only: sample size, race days and WinningTime coverage.  It deliberately omits
all baseline/candidate outcomes so nobody can tune the fixed candidate while
the terminal sample is accumulating.

On the first complete race day that takes the sample to at least 2,000 races,
the exact race keys are frozen in the status file and the Stage-4 evidence is
revealed.  Later runs reuse those keys and cannot silently extend the terminal.
Production ranking is never changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AU_RACING = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(AU_RACING))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

from au_leaf_power import norm  # noqa: E402
from au_speed_venue_audit import (  # noqa: E402
    MEETING_RE,
    METRICS,
    GLOBAL_SPEED_K,
    SPEED_MIN_CELL_RACES,
    SPEED_MIN_GOING_RACES,
    SPEED_MIN_RUNNER_RUNS,
    _delta,
    _rate,
    build_asof_standards,
    collect_reference_races,
    load_races,
    paired_ci,
    race_rows,
    scored_meeting_index,
)
from model_evaluation_decision import (  # noqa: E402
    EvaluationInput,
    MetricEvidence,
    evaluate_candidate,
)


EXPERIMENT_ID = "EXP-20260927-02"
START_DATE = "2026-09-27"
TARGET_RACES = 2000
CANDIDATE = "global_add"
SPEED_K = GLOBAL_SPEED_K
MIN_CELL_RACES = SPEED_MIN_CELL_RACES
MIN_GOING_RACES = SPEED_MIN_GOING_RACES
MIN_RUNNER_RUNS = SPEED_MIN_RUNNER_RUNS
WATCH_VENUES = (
    "Kalgoorlie",
    "Ballarat Synthetic",
    "Randwick",
    "Caulfield",
)
DEVELOPMENT_EVIDENCE = {
    "source": "docs/experiments/EXP-20260927-02-au-pit-speed-and-venue-audit.md",
    "races": 2081,
    "date_from": "2026-06-06",
    "date_to": "2026-09-26",
    "gold_delta_pp": 0.43,
    "gold_ci95_pp": [0.05, 0.86],
    "good_positional_delta_pp": 0.48,
}
MIN_AUTO_GATE_COVERAGE_PCT = 70.0
MIN_COHORT_RACES = 100
MIN_COHORT_DAYS = 5
FIELD_BUCKETS = (
    ("le8", lambda size: size <= 8),
    ("9_10", lambda size: 9 <= size <= 10),
    ("11_12", lambda size: 11 <= size <= 12),
    ("ge13", lambda size: size >= 13),
)


def race_key(row: dict) -> str:
    return f"{row['date']}|{norm(row['venue'])}|{int(row['race'])}"


def config() -> dict:
    values = {
        "experiment_id": EXPERIMENT_ID,
        "start_date": START_DATE,
        "target_races": TARGET_RACES,
        "candidate": CANDIDATE,
        "speed_k": SPEED_K,
        "min_cell_races": MIN_CELL_RACES,
        "min_going_races": MIN_GOING_RACES,
        "min_runner_runs": MIN_RUNNER_RUNS,
        "watch_venues": list(WATCH_VENUES),
    }
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    values["config_sha256"] = hashlib.sha256(encoded).hexdigest()
    return values


def select_complete_date_sample(rows: list[dict], target: int) -> list[dict]:
    """Stop on the first whole race day that reaches ``target`` races."""
    by_date = defaultdict(list)
    for row in sorted(rows, key=lambda item: (item["date"], item["venue"], item["race"])):
        by_date[row["date"]].append(row)
    selected = []
    for day in sorted(by_date):
        selected.extend(by_date[day])
        if len(selected) >= target:
            break
    return selected


def select_locked_sample(rows: list[dict], locked_keys: list[str]) -> list[dict]:
    by_key = {race_key(row): row for row in rows}
    missing = [key for key in locked_keys if key not in by_key]
    if missing:
        raise ValueError(f"locked terminal missing {len(missing)} races; first={missing[0]}")
    return [by_key[key] for key in locked_keys]


def _coverage(rows: list[dict]) -> dict:
    return {
        "runner_coverage_pct": round(
            100.0 * statistics.mean(row["coverage"] for row in rows), 3
        ) if rows else 0.0,
        "zero_coverage_races": sum(row["coverage"] == 0 for row in rows),
    }


def _evaluation(rows: list[dict]) -> dict:
    return {
        "races": len(rows),
        "baseline": {metric: _rate(rows, "baseline", metric) for metric in METRICS},
        "candidate": {metric: _rate(rows, CANDIDATE, metric) for metric in METRICS},
        "delta": {metric: _delta(rows, CANDIDATE, metric) for metric in METRICS},
        "paired_ci": {
            "gold": list(paired_ci(rows, CANDIDATE, "gold")),
            "good_positional": list(paired_ci(rows, CANDIDATE, "good_positional")),
        },
    }


def _supported_cohort_regressions(cohorts: dict[str, list[dict]]) -> tuple[list[str], list[str]]:
    """Return supported harms and cohorts too small for an automatic verdict."""
    regressions = []
    unresolved = []
    for label, rows in cohorts.items():
        race_days = len({row["date"] for row in rows})
        if len(rows) < MIN_COHORT_RACES or race_days < MIN_COHORT_DAYS:
            unresolved.append(label)
            continue
        for metric in ("gold", "good_positional"):
            delta = _delta(rows, CANDIDATE, metric)
            ci_low, ci_high = paired_ci(rows, CANDIDATE, metric)
            if delta < 0 and ci_high < 0:
                regressions.append(f"{label}:{metric}")
    return regressions, unresolved


def stage4_decision(terminal: list[dict], sample_hash: str) -> dict:
    """Apply the pre-registered primary gate to one frozen prospective sample."""
    evaluation = _evaluation(terminal)
    field_cohorts = {
        f"field_size:{label}": [row for row in terminal if predicate(int(row["field_size"]))]
        for label, predicate in FIELD_BUCKETS
    }
    venue_cohorts = {
        f"venue:{venue}": [
            row for row in terminal if norm(row["venue"]) == norm(venue)
        ]
        for venue in WATCH_VENUES
    }
    cohort_regressions, unresolved = _supported_cohort_regressions(
        {**field_cohorts, **venue_cohorts}
    )
    coverage = _coverage(terminal)["runner_coverage_pct"]
    if coverage < MIN_AUTO_GATE_COVERAGE_PCT:
        cohort_regressions.append(
            f"overall_speed_coverage<{MIN_AUTO_GATE_COVERAGE_PCT:.0f}%"
        )

    primary = {
        "gold": MetricEvidence(
            development_delta=DEVELOPMENT_EVIDENCE["gold_delta_pp"],
            terminal_delta=evaluation["delta"]["gold"],
            terminal_ci_low=evaluation["paired_ci"]["gold"][0],
            terminal_ci_high=evaluation["paired_ci"]["gold"][1],
        ),
        "good_positional": MetricEvidence(
            development_delta=DEVELOPMENT_EVIDENCE["good_positional_delta_pp"],
            terminal_delta=evaluation["delta"]["good_positional"],
            terminal_ci_low=evaluation["paired_ci"]["good_positional"][0],
            terminal_ci_high=evaluation["paired_ci"]["good_positional"][1],
        ),
    }
    result = evaluate_candidate(EvaluationInput(
        domain="au",
        baseline_sample_hash=sample_hash,
        candidate_sample_hash=sample_hash,
        baseline_races=len(terminal),
        candidate_races=len(terminal),
        holdout_locked=True,
        leakage_audit_passed=True,
        primary=primary,
        ranking={},
        cohort_regressions=tuple(sorted(cohort_regressions)),
    ))
    eligible = result["verdict"] == "PRIMARY_WIN"
    decision = {
        **result,
        "eligible_for_candidate_release": eligible,
        "production_changed": False,
        "development_evidence": DEVELOPMENT_EVIDENCE,
        "terminal_primary": {
            "gold_delta_pp": evaluation["delta"]["gold"],
            "gold_ci95_pp": evaluation["paired_ci"]["gold"],
            "good_positional_delta_pp": evaluation["delta"]["good_positional"],
            "good_positional_ci95_pp": evaluation["paired_ci"]["good_positional"],
        },
        "guardrails": {
            "minimum_runner_coverage_pct": MIN_AUTO_GATE_COVERAGE_PCT,
            "actual_runner_coverage_pct": coverage,
            "minimum_cohort_races": MIN_COHORT_RACES,
            "minimum_cohort_days": MIN_COHORT_DAYS,
            "supported_regressions": sorted(cohort_regressions),
            "unresolved_cohorts": sorted(unresolved),
        },
        "approval": {
            "candidate_pr_may_be_prepared_automatically": eligible,
            "automatic_merge": False,
            "automatic_activation": False,
            "required_command": "/approve SHA",
        },
    }
    proposal_core = {
        "experiment_id": EXPERIMENT_ID,
        "status": "passed" if eligible else "rejected",
        "verdict": result["verdict"],
        "reason": result["reason"],
        "sample_sha256": sample_hash,
        "config_sha256": config()["config_sha256"],
        "candidate": {
            "name": CANDIDATE,
            "formula": "final_rank_score + 0.5 * within_race_z(speed_best3)",
            "speed_k": SPEED_K,
            "min_cell_races": MIN_CELL_RACES,
            "min_going_races": MIN_GOING_RACES,
            "min_runner_runs": MIN_RUNNER_RUNS,
        },
        "production_changed": False,
        "approval_required": True,
        "approval_command": "/approve SHA",
    }
    proposal_sha = hashlib.sha256(
        json.dumps(proposal_core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    decision["release_proposal"] = {
        **proposal_core,
        "proposal_sha256": proposal_sha,
    }
    return decision


def _cohort(rows: list[dict]) -> dict:
    if not rows:
        return {"races": 0, "race_days": 0, **_coverage(rows)}
    return {
        "races": len(rows),
        "race_days": len({row["date"] for row in rows}),
        "date_from": min(row["date"] for row in rows),
        "date_to": max(row["date"] for row in rows),
        **_coverage(rows),
    }


def build_status(rows: list[dict], *, reference_races: int, reference_conflicts: int,
                 target: int = TARGET_RACES, locked_keys: list[str] | None = None) -> dict:
    """Build a blind collecting status or a frozen terminal evaluation."""
    rows = sorted(rows, key=lambda row: (row["date"], row["venue"], row["race"]))
    status = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": config(),
        "state": "collecting",
        "outcomes_visible": False,
        "races_collected": len(rows),
        "races_remaining": max(0, target - len(rows)),
        "race_days": len({row["date"] for row in rows}),
        "date_from": rows[0]["date"] if rows else None,
        "date_to": rows[-1]["date"] if rows else None,
        "reference_races": reference_races,
        "reference_conflicts": reference_conflicts,
        **_coverage(rows),
        "watch_venues": {
            venue: _cohort([row for row in rows if norm(row["venue"]) == norm(venue)])
            for venue in WATCH_VENUES
        },
    }
    if len(rows) < target and not locked_keys:
        return status

    terminal = (select_locked_sample(rows, locked_keys) if locked_keys
                else select_complete_date_sample(rows, target))
    frozen_keys = [race_key(row) for row in terminal]
    sample_hash = hashlib.sha256("\n".join(frozen_keys).encode()).hexdigest()
    status.update({
        "state": "ready_for_manual_stage4_review",
        "outcomes_visible": True,
        "races_collected": len(terminal),
        "races_remaining": 0,
        "race_days": len({row["date"] for row in terminal}),
        "date_from": terminal[0]["date"],
        "date_to": terminal[-1]["date"],
        "locked_through_date": terminal[-1]["date"],
        "locked_race_keys": frozen_keys,
        "sample_sha256": sample_hash,
        **_coverage(terminal),
        "evaluation": _evaluation(terminal),
        "field_size_cohorts": {
            label: {**_cohort(bucket), "evaluation": _evaluation(bucket)}
            for label, predicate in FIELD_BUCKETS
            if (bucket := [row for row in terminal if predicate(int(row["field_size"]))])
        },
        "venue_guardrails": {
            venue: {**_cohort(bucket), "evaluation": _evaluation(bucket)}
            for venue in WATCH_VENUES
            if (bucket := [row for row in terminal
                           if norm(row["venue"]) == norm(venue)])
        },
    })
    status["stage4_decision"] = stage4_decision(terminal, sample_hash)
    return status


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def validate_existing_config(existing: dict) -> None:
    """Reject config drift once any prospective race has been collected."""
    old_hash = ((existing.get("config") or {}).get("config_sha256"))
    if not old_hash or old_hash == config()["config_sha256"]:
        return
    if existing.get("races_collected", 0) == 0 and not existing.get("outcomes_visible"):
        return
    raise ValueError("shadow config changed after collection started")


def run(data_root: Path, output: Path) -> dict:
    existing = {}
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        validate_existing_config(existing)
    meeting_dates = []
    for name in scored_meeting_index(data_root):
        match = MEETING_RE.match(name)
        if match and match.group(1) >= START_DATE:
            meeting_dates.append(match.group(1))
    observations, conflicts = collect_reference_races(data_root)
    standards = build_asof_standards(observations, meeting_dates)
    races = load_races(data_root, START_DATE, standards)
    rows = race_rows(races)
    locked_keys = existing.get("locked_race_keys")
    status = build_status(
        rows,
        reference_races=len(observations),
        reference_conflicts=conflicts,
        locked_keys=locked_keys,
    )
    atomic_write(output, status)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    status = run(args.data_root, args.output)
    print(
        f"{EXPERIMENT_ID}: {status['state']} — "
        f"{status['races_collected']}/{TARGET_RACES} races, "
        f"{status['race_days']} days, coverage {status['runner_coverage_pct']:.1f}%"
    )
    if status["outcomes_visible"]:
        print("Terminal locked; outcome evidence is available for manual Stage-4 review.")
    else:
        print("Blind collection: outcome metrics remain sealed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
