#!/usr/bin/env python3
"""Point-in-time audit of recovered Sportsbet trial placings.

This is a correctness experiment, not a parameter search.  It only replaces a
cached runtime ``trial_score`` when the captured engine classified that leaf as
fallback but the target race page contains dated trial placings from before the
meeting.  Existing observed trial scores are left untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTO_SCRIPTS = (
    ROOT
    / ".agents"
    / "skills"
    / "au_racing"
    / "au_wong_choi_auto"
    / "scripts"
)
AU_RACING = ROOT / ".agents" / "skills" / "au_racing"
sys.path.insert(0, str(AUTO_SCRIPTS))
sys.path.insert(0, str(AU_RACING))

from au_eval import (  # noqa: E402
    _auc_indices,
    _pairs,
    compare,
    date_partitions,
    default_scorer,
    load_races,
    verdict_dict,
)
from au_racing_engine import matrix_mapper  # noqa: E402
from au_racing_engine.engine_core import RacingEngine  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402
from claw_sportsbet_form import BASE, parse_race, parse_runner_blocks, run_date  # noqa: E402


def identity(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def cache_path(cache_dir: Path, meeting_id: str, race_id: str) -> Path:
    url = f"{BASE}/{meeting_id}/{race_id}/"
    return cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()}.html"


def extract_trials(
    index_path: Path,
    cache_dir: Path,
    target_dates: set[str],
) -> tuple[dict[tuple[str, str, int, str], list[dict]], dict]:
    meetings = json.loads(index_path.read_text(encoding="utf-8"))
    output: dict[tuple[str, str, int, str], list[dict]] = {}
    counts = Counter()
    for meeting in meetings.values():
        target_date = str(meeting.get("date") or "")
        if target_date not in target_dates:
            continue
        counts["meetings_considered"] += 1
        meeting_id = str(meeting.get("meetingId") or "")
        for race_id in meeting.get("races") or []:
            path = cache_path(cache_dir, meeting_id, str(race_id))
            if not path.exists():
                counts["race_cache_missing"] += 1
                continue
            try:
                html = path.read_text(encoding="utf-8")
                parsed = parse_race(html)
                blocks = parse_runner_blocks(html)
            except Exception:  # noqa: BLE001 - research audit counts and continues
                counts["race_parse_error"] += 1
                continue
            race_number = int(parsed["meta"].get("race_number") or 0)
            track = identity(parsed["meta"].get("venue") or meeting.get("slug"))
            if not race_number or not track:
                counts["race_identity_missing"] += 1
                continue
            counts["race_pages"] += 1
            for block in blocks:
                trials = [
                    {
                        "date": run_date(run),
                        "place": int(run["pos"]),
                    }
                    for run in block.get("runs", [])
                    if run.get("is_trial")
                    and run.get("pos")
                    and run_date(run)
                    and run_date(run) < target_date
                ]
                if not trials:
                    continue
                key = (
                    target_date,
                    track,
                    race_number,
                    identity(block.get("name")),
                )
                output[key] = trials
                counts["runner_with_trial_placings"] += 1
                counts["trial_placing_rows"] += len(trials)
    return output, dict(counts)


def corrected_trial_score(row: dict, race: dict, trials: list[dict]) -> float:
    raw = dict(row.get("raw_pre_race") or {})
    raw["trial_count"] = len(trials)
    raw["trial_top3_count"] = sum(run["place"] <= 3 for run in trials)
    existing_facts = str(raw.get("facts_section") or "")
    formal_lines = [
        line for line in existing_facts.splitlines()
        if "| 試開 |" not in line
    ]
    trial_lines = [
        f"| {index} | 試開 | {run['date']} | Sportsbet | - | - | - | "
        f"{run['place']} | - |"
        for index, run in enumerate(trials, 1)
    ]
    horse = {
        "horse_name": row.get("horse_name"),
        "horse_number": row.get("horse_number"),
        "barrier": raw.get("barrier"),
        "weight": raw.get("weight"),
        "jockey": raw.get("jockey"),
        "trainer": raw.get("trainer"),
        "career_race_starts": raw.get("formal_count", 0),
        "_data": raw,
    }
    metadata = race.get("metadata") or {}
    context = {
        "race_class": metadata.get("race_class"),
        "distance": metadata.get("distance"),
        "field_summary": {"count": metadata.get("field_size") or len(race["rows"])},
        "meeting_intelligence": {
            "venue": metadata.get("track"),
            "going": metadata.get("going"),
        },
        "speed_map": race.get("speed_map") or {},
    }
    engine = RacingEngine(horse, context, facts_section="\n".join(formal_lines + trial_lines))
    score, _note, _source = engine._trial_score()
    return float(score)


def attach(races: list[dict], extracted: dict) -> dict:
    counts = Counter()
    for race in races:
        metadata = race.get("metadata") or {}
        date = str(race.get("date") or metadata.get("date") or "")
        track = identity(metadata.get("track"))
        race_number = int(metadata.get("race_number") or 0)
        race_touched = False
        for row in race["rows"]:
            state = (row.get("feature_evidence_state") or {}).get("trial_score")
            key = (date, track, race_number, identity(row.get("horse_name")))
            trials = extracted.get(key)
            if not trials:
                continue
            counts["runner_matched"] += 1
            if state != "fallback":
                counts["runner_already_observed"] += 1
                continue
            score = corrected_trial_score(row, race, trials)
            row["_corrected_trial_score"] = score
            counts["runner_fallback_corrected"] += 1
            if score != float(row["features"].get("trial_score", 60.0)):
                counts["runner_score_changed"] += 1
                race_touched = True
        counts["race_score_changed"] += race_touched
    return dict(counts)


def semantic_baseline_scorer(row: dict) -> float:
    features = dict(row["features"])
    if row.get("_corrected_trial_score") is not None:
        features["trial_score"] = float(row["_corrected_trial_score"])
    matrices = matrix_mapper.map_features_to_matrix_scores(features)
    return (
        sum(matrices.get(key, 60.0) * weight for key, weight in MATRIX_WEIGHTS.items())
        + float(row.get("wet") or 0.0)
    )


def poor_trial_scorer(mode: str):
    """Pre-registered risk interactions; no threshold search.

    The candidate is eligible only when a formerly-fallback runner has an
    observed Sportsbet trial score of 56 after recovery.  That is the exact
    established-horse state behind ``trial_no_recent_top3`` in fresh runs.
    """
    if mode not in {"pf_half", "wet_half", "both_half"}:
        raise ValueError(mode)

    def scorer(row: dict) -> float:
        features = dict(row["features"])
        corrected = row.get("_corrected_trial_score")
        poor_trial = corrected is not None and float(corrected) <= 56.005
        if corrected is not None:
            features["trial_score"] = float(corrected)
        if poor_trial and mode in {"pf_half", "both_half"}:
            pace = float(features.get("pace_figure_score", 60.0))
            if pace > 60.0:
                features["pace_figure_score"] = 60.0 + 0.5 * (pace - 60.0)
        wet = float(row.get("wet") or 0.0)
        if poor_trial and wet > 0 and mode in {"wet_half", "both_half"}:
            wet *= 0.5
        matrices = matrix_mapper.map_features_to_matrix_scores(features)
        return (
            sum(matrices.get(key, 60.0) * weight
                for key, weight in MATRIX_WEIGHTS.items())
            + wet
        )

    return scorer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--index",
        type=Path,
        default=AU_RACING / "data" / "sb_archive_meeting_ids.json",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=AU_RACING / ".sportsbet_cache",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    races = load_races(args.dataset)
    target_dates = {str(race.get("date") or "") for race in races}
    extracted, extraction = extract_trials(args.index, args.cache_dir, target_dates)
    attachment = attach(races, extracted)
    semantic_verdict = compare(
        races,
        default_scorer,
        semantic_baseline_scorer,
        label="recover observed Sportsbet trial placings",
    )
    dev_indices, _holdout_indices = date_partitions(races)
    baseline_pairs = _pairs(races, semantic_baseline_scorer, True)
    development_search = []
    for mode in ("pf_half", "wet_half", "both_half"):
        scorer = poor_trial_scorer(mode)
        pairs = _pairs(races, scorer, True)
        development_search.append({
            "mode": mode,
            "development_top5_auc_delta": (
                _auc_indices(pairs, dev_indices)
                - _auc_indices(baseline_pairs, dev_indices)
            ),
        })
    chosen = max(
        development_search,
        key=lambda item: (
            item["development_top5_auc_delta"],
            -{"pf_half": 1, "wet_half": 1, "both_half": 2}[item["mode"]],
        ),
    )
    interaction_verdict = None
    # Do not open the terminal holdout to rescue a candidate that already lost
    # on development.  If dev is positive, open it once for the locked winner.
    if chosen["development_top5_auc_delta"] > 0:
        interaction_verdict = verdict_dict(compare(
            races,
            semantic_baseline_scorer,
            poor_trial_scorer(chosen["mode"]),
            label=f"poor observed trials × {chosen['mode']}",
        ))
    report = {
        "design": {
            "point_in_time": "trial date < target meeting date",
            "replacement": "fallback trial_score only; observed scores untouched",
            "parameter_search": False,
        },
        "extraction": extraction,
        "attachment": attachment,
        "semantic_verdict": verdict_dict(semantic_verdict),
        "poor_trial_interaction": {
            "pre_registered": ["pf_half", "wet_half", "both_half"],
            "development_search": development_search,
            "chosen_on_development": chosen,
            "terminal_verdict": interaction_verdict,
        },
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
