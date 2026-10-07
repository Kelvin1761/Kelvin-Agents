#!/usr/bin/env python3
"""Strict PIT A/B for adding completed current-season HKJC results to priors.

Baseline excludes every 26/27 result. Candidate admits only results whose date
is strictly earlier than the target meeting. No production artifact is written.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[3]
REFLECTOR = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
SHARED = REPO / ".agents/skills/shared_racing/scripts"
for path in (REFLECTOR, SHARED, REPO):
    sys.path.insert(0, str(path))

import pit_backtest as pit  # noqa: E402
import rescore_backtest as bt  # noqa: E402
from corpus_paths import meeting_dirs  # noqa: E402
from wongchoi_paths import HK_RACING  # noqa: E402


CURRENT_SEASON = "26_27"


def _flags(race: dict) -> dict[str, float]:
    actual = race["actual"]
    best = min(actual.values())
    winners = {horse for horse, pos in actual.items() if pos == best}
    top3 = {horse for horse, pos in actual.items() if pos <= 3}
    order = [
        row["hn"]
        for row in sorted(race["scored"], key=lambda row: (-row["ability"], row["hn"]))
    ]
    picks = order[:4]
    hits3 = sum(horse in top3 for horse in picks[:3])
    return {
        "gold": float(hits3 == 3),
        "good": float(len(picks) >= 2 and picks[0] in top3 and picks[1] in top3),
        "min": float(hits3 >= 2),
        "single": float(hits3 >= 1),
        "champion": float(bool(picks) and picks[0] in winners),
        "top3_champ": float(bool(winners & set(picks[:3]))),
    }


def _summary(rows: list[dict[str, float]]) -> dict:
    if not rows:
        return {"races": 0}
    return {
        "races": len(rows),
        **{
            metric: round(100.0 * float(np.mean([row[metric] for row in rows])), 3)
            for metric in bt.METRICS
        },
    }


def _paired(candidate: list[dict[str, float]], baseline: list[dict[str, float]]) -> dict:
    if len(candidate) != len(baseline) or not candidate:
        return {"races": 0}
    rng = np.random.default_rng(20261004)
    output = {"races": len(candidate)}
    for metric in bt.METRICS:
        delta = np.asarray(
            [candidate[index][metric] - baseline[index][metric] for index in range(len(candidate))],
            dtype=float,
        )
        draws = np.empty(5000, dtype=float)
        for index in range(len(draws)):
            sample = rng.integers(0, len(delta), size=len(delta))
            draws[index] = float(delta[sample].mean())
        output[metric] = {
            "delta_pp": round(100.0 * float(delta.mean()), 3),
            "ci95_pp": [
                round(100.0 * float(np.quantile(draws, 0.025)), 3),
                round(100.0 * float(np.quantile(draws, 0.975)), 3),
            ],
        }
    return output


def _venue(path: Path) -> str:
    return "ST" if "ShaTin" in path.name else "HV"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    rows = pit.load_all_rows()
    baseline_rows = rows[rows["SeasonTag"] != CURRENT_SEASON].copy()
    targets = sorted(
        path
        for path in meeting_dirs(HK_RACING)
        if path.name.startswith(("2026-09", "2026-10"))
        and path.name[:10] <= "2026-10-01"
        and bt.find_results_json(path) is not None
    )
    arms: dict[str, dict[str, list[dict[str, float]]]] = {
        "baseline": defaultdict(list),
        "season_aware": defaultdict(list),
    }
    meetings = []
    errors = []
    for target in targets:
        meeting_date = pit.meeting_date_from_dir(target)
        venue = _venue(target)
        meeting_row = {"meeting": target.name, "venue": venue}
        for arm, source in (("baseline", baseline_rows), ("season_aware", rows)):
            prior_rows = pit.inject_as_of(source, meeting_date)
            races, race_errors = bt.rescore_meeting(target)
            errors.extend(f"{arm}: {error}" for error in race_errors)
            flags = [_flags(race) for race in races]
            arms[arm]["ALL"].extend(flags)
            arms[arm][venue].extend(flags)
            meeting_row[arm] = {"prior_rows": prior_rows, **_summary(flags)}
        meetings.append(meeting_row)

    report = {
        "experiment": "EXP-20261004-01",
        "current_season": CURRENT_SEASON,
        "cutoff_rule": "Date < target meeting date",
        "meetings": meetings,
        "cohorts": {},
        "errors": errors,
    }
    for cohort in ("ALL", "ST", "HV"):
        report["cohorts"][cohort] = {
            "baseline": _summary(arms["baseline"][cohort]),
            "season_aware": _summary(arms["season_aware"][cohort]),
            "paired_delta": _paired(
                arms["season_aware"][cohort], arms["baseline"][cohort]
            ),
        }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
