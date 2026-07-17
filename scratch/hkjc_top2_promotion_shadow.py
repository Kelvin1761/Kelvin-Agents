#!/usr/bin/env python3
"""Market-free HKJC rank-3 to Top-2 promotion shadow diagnostic.

This script never changes live scores.  It evaluates a constrained decision:
keep the current rank 1, then choose either the current rank 2 or rank 3 as the
second recommendation using only speed, form-line, class, distance and
confidence/risk evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_reflector"
    / "artifacts"
    / "hkjc_ranking_dataset.csv"
)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Horse:
    number: int
    name: str
    rank: int
    score: float
    finish: int
    speed: float
    formline: float
    class_score: float
    distance: float
    risk: float
    confidence: float


@dataclass(frozen=True)
class Race:
    meeting: str
    date: str
    race_number: int
    horses: tuple[Horse, ...]

    @property
    def ranked(self) -> tuple[Horse, ...]:
        return tuple(sorted(self.horses, key=lambda row: (row.rank, -row.score, row.number)))

    @property
    def winner(self) -> Horse:
        return min(self.horses, key=lambda row: row.finish)


@dataclass(frozen=True)
class Candidate:
    name: str
    weights: tuple[float, float, float, float]
    minimum_advantage: float
    minimum_component_wins: int
    risk_floor: float = 60.0
    confidence_floor: float = 60.0
    uncertainty_penalty: bool = True
    absolute_support_floor: float | None = None
    minimum_distance_delta: float | None = None
    minimum_class_delta: float | None = None
    class_or_nonnegative_risk_confirmation: bool = False
    minimum_risk_delta_for_or: float = 0.0


PROFILES = {
    "balanced": (0.35, 0.30, 0.20, 0.15),
    "formline_class": (0.25, 0.35, 0.25, 0.15),
    "sectional": (0.45, 0.25, 0.20, 0.10),
    "class_distance": (0.10, 0.10, 0.40, 0.40),
    "distance_ceiling": (0.15, 0.10, 0.25, 0.50),
}


CANDIDATES = (
    Candidate("balanced_guarded_2", PROFILES["balanced"], 2.0, 2),
    Candidate("balanced_guarded_4", PROFILES["balanced"], 4.0, 2),
    Candidate("formline_class_guarded_2", PROFILES["formline_class"], 2.0, 2),
    Candidate("formline_class_guarded_4", PROFILES["formline_class"], 4.0, 2),
    Candidate("sectional_guarded_2", PROFILES["sectional"], 2.0, 2),
    Candidate("sectional_guarded_4", PROFILES["sectional"], 4.0, 2),
    Candidate("three_signal_guarded", PROFILES["balanced"], 0.0, 3),
    Candidate(
        "bounded_upside_guarded",
        PROFILES["balanced"],
        1.0,
        2,
        absolute_support_floor=67.0,
    ),
    Candidate("class_distance_guarded_3", PROFILES["class_distance"], 3.0, 1),
    Candidate("class_distance_guarded_5", PROFILES["class_distance"], 5.0, 1),
    Candidate("class_distance_guarded_7", PROFILES["class_distance"], 7.0, 1),
    Candidate("distance_ceiling_guarded_3", PROFILES["distance_ceiling"], 3.0, 1),
    Candidate("distance_ceiling_guarded_5", PROFILES["distance_ceiling"], 5.0, 1),
    Candidate(
        "distance_context_confirmed",
        PROFILES["class_distance"],
        0.0,
        1,
        minimum_distance_delta=10.0,
        minimum_class_delta=5.0,
        class_or_nonnegative_risk_confirmation=True,
    ),
    Candidate(
        "distance_class_strict",
        PROFILES["class_distance"],
        0.0,
        1,
        minimum_distance_delta=10.0,
        minimum_class_delta=5.0,
    ),
    Candidate(
        "distance_context_strong_confirmation",
        PROFILES["class_distance"],
        0.0,
        1,
        minimum_distance_delta=10.0,
        minimum_class_delta=5.0,
        class_or_nonnegative_risk_confirmation=True,
        minimum_risk_delta_for_or=10.0,
    ),
    Candidate("dual_signal_union", PROFILES["balanced"], 0.0, 1),
)


def load_archive_races(dataset: Path) -> list[Race]:
    grouped: defaultdict[tuple[str, str, int], list[Horse]] = defaultdict(list)
    with dataset.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rank = as_int(row.get("current_live_rank"))
            finish = as_int(row.get("finish_pos"))
            horse_number = as_int(row.get("horse_number"))
            race_number = as_int(row.get("race_number"))
            if min(rank, finish, horse_number, race_number) <= 0:
                continue
            key = (
                str(row.get("meeting_name") or Path(str(row.get("meeting") or "")).name),
                str(row.get("date") or ""),
                race_number,
            )
            grouped[key].append(
                Horse(
                    number=horse_number,
                    name=str(row.get("horse_name") or ""),
                    rank=rank,
                    score=as_float(row.get("current_live_rank_score"), as_float(row.get("current_live_ability"))),
                    finish=finish,
                    speed=as_float(row.get("feat_speed_score"), 60.0),
                    formline=as_float(row.get("feat_formline_strength_score"), 60.0),
                    class_score=as_float(row.get("feat_class_score"), 60.0),
                    distance=as_float(row.get("feat_distance_score"), 60.0),
                    risk=as_float(row.get("feat_risk_score"), 60.0),
                    confidence=as_float(row.get("feat_confidence_score"), 60.0),
                )
            )
    races = [
        Race(meeting=meeting, date=date, race_number=race_number, horses=tuple(horses))
        for (meeting, date, race_number), horses in grouped.items()
        if len(horses) >= 3
    ]
    return sorted(races, key=lambda race: (race.date, race.meeting, race.race_number))


def _result_positions(results_file: Path) -> dict[int, dict[int, int]]:
    payload = json.loads(results_file.read_text(encoding="utf-8"))
    out: dict[int, dict[int, int]] = {}
    for race_key, race_payload in payload.items():
        race_number = as_int(race_key)
        positions: dict[int, int] = {}
        for row in race_payload.get("results", []):
            horse_number = as_int(row.get("horse_no"))
            finish = as_int(str(row.get("pos") or "").replace("DH", ""))
            if horse_number > 0 and finish > 0:
                positions[horse_number] = finish
        if positions:
            out[race_number] = positions
    return out


def load_holdout_races(meeting_dir: Path, results_file: Path) -> list[Race]:
    positions = _result_positions(results_file)
    races: list[Race] = []
    for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json")):
        race_number = as_int(logic_path.stem.split("_")[1])
        actual = positions.get(race_number, {})
        if not actual:
            continue
        payload = json.loads(logic_path.read_text(encoding="utf-8"))
        horses: list[Horse] = []
        for horse_key, raw in (payload.get("horses") or {}).items():
            number = as_int(horse_key)
            auto = raw.get("python_auto") if isinstance(raw.get("python_auto"), dict) else {}
            features = auto.get("feature_scores") if isinstance(auto.get("feature_scores"), dict) else {}
            if number not in actual or not auto:
                continue
            horses.append(
                Horse(
                    number=number,
                    name=str(raw.get("horse_name") or ""),
                    rank=as_int(auto.get("rank"), 999),
                    score=as_float(auto.get("rank_score"), as_float(auto.get("ability_score"))),
                    finish=actual[number],
                    speed=as_float(features.get("speed_score"), 60.0),
                    formline=as_float(features.get("formline_strength_score"), 60.0),
                    class_score=as_float(features.get("class_score"), 60.0),
                    distance=as_float(features.get("distance_score"), 60.0),
                    risk=as_float(features.get("risk_score"), 60.0),
                    confidence=as_float(features.get("confidence_score"), 60.0),
                )
            )
        if len(horses) >= 3:
            races.append(
                Race(
                    meeting=meeting_dir.name,
                    date=meeting_dir.name[:10],
                    race_number=race_number,
                    horses=tuple(horses),
                )
            )
    return sorted(races, key=lambda race: race.race_number)


def load_independent_races(
    root: Path,
    excluded_meetings: set[str],
    minimum_date: str = "2026-05-25",
    maximum_date: str = "2026-07-14",
) -> tuple[list[Race], list[dict[str, str]]]:
    races: list[Race] = []
    skipped: list[dict[str, str]] = []
    for meeting_dir in sorted(root.iterdir()):
        if not meeting_dir.is_dir():
            continue
        date = meeting_dir.name[:10]
        if not (minimum_date <= date <= maximum_date):
            continue
        if meeting_dir.name in excluded_meetings:
            continue
        logic_paths = list(meeting_dir.glob("Race_*_Logic.json"))
        result_paths = sorted(meeting_dir.glob("*全日賽果.json"))
        if not logic_paths or not result_paths:
            skipped.append({"meeting": meeting_dir.name, "reason": "missing logic or local results"})
            continue
        try:
            races.extend(load_holdout_races(meeting_dir, result_paths[0]))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            skipped.append({"meeting": meeting_dir.name, "reason": str(exc)})
    return sorted(races, key=lambda race: (race.date, race.meeting, race.race_number)), skipped


def evidence_vector(horse: Horse) -> tuple[float, float, float, float]:
    return horse.speed, horse.formline, horse.class_score, horse.distance


def weighted_evidence(horse: Horse, weights: tuple[float, float, float, float]) -> float:
    return sum(value * weight for value, weight in zip(evidence_vector(horse), weights))


def should_promote(rank2: Horse, rank3: Horse, candidate: Candidate) -> tuple[bool, dict[str, Any]]:
    if candidate.name == "dual_signal_union":
        gate_names = {"balanced_guarded_4", "distance_context_strong_confirmation"}
        decisions = []
        for gate in CANDIDATES:
            if gate.name not in gate_names:
                continue
            promoted, decision = should_promote(rank2, rank3, gate)
            decisions.append((gate.name, promoted, decision))
        triggered = [row for row in decisions if row[1]]
        if triggered:
            gate_name, _promoted, decision = max(
                triggered,
                key=lambda row: float(row[2].get("adjusted_advantage", 0.0)),
            )
            return True, {**decision, "union_trigger": gate_name}
        return False, {
            "raw_advantage": 0.0,
            "uncertainty_penalty": 0.0,
            "adjusted_advantage": 0.0,
            "component_wins": 0,
            "absolute_support": weighted_evidence(rank3, PROFILES["balanced"]),
            "union_trigger": "none",
        }
    components2 = evidence_vector(rank2)
    components3 = evidence_vector(rank3)
    component_wins = sum(1 for value3, value2 in zip(components3, components2) if value3 >= value2 + 1.0)
    raw_advantage = weighted_evidence(rank3, candidate.weights) - weighted_evidence(rank2, candidate.weights)
    penalty = 0.0
    if candidate.uncertainty_penalty:
        penalty += max(0.0, candidate.confidence_floor - rank3.confidence) * 0.20
        penalty += max(0.0, candidate.risk_floor - rank3.risk) * 0.15
    adjusted_advantage = raw_advantage - penalty
    absolute_support = weighted_evidence(rank3, candidate.weights)
    distance_delta = rank3.distance - rank2.distance
    class_delta = rank3.class_score - rank2.class_score
    risk_delta = rank3.risk - rank2.risk
    distance_ok = (
        candidate.minimum_distance_delta is None
        or distance_delta >= candidate.minimum_distance_delta
    )
    if candidate.minimum_class_delta is None:
        confirmation_ok = True
    elif candidate.class_or_nonnegative_risk_confirmation:
        confirmation_ok = (
            class_delta >= candidate.minimum_class_delta
            or risk_delta >= candidate.minimum_risk_delta_for_or
        )
    else:
        confirmation_ok = class_delta >= candidate.minimum_class_delta
    promote = (
        rank3.confidence >= candidate.confidence_floor
        and rank3.risk >= candidate.risk_floor
        and component_wins >= candidate.minimum_component_wins
        and adjusted_advantage >= candidate.minimum_advantage
        and (
            candidate.absolute_support_floor is None
            or absolute_support >= candidate.absolute_support_floor
        )
        and distance_ok
        and confirmation_ok
    )
    return promote, {
        "raw_advantage": round(raw_advantage, 3),
        "uncertainty_penalty": round(penalty, 3),
        "adjusted_advantage": round(adjusted_advantage, 3),
        "component_wins": component_wins,
        "absolute_support": round(absolute_support, 3),
    }


def evaluate(races: Iterable[Race], candidate: Candidate | None = None) -> dict[str, Any]:
    races = list(races)
    totals = Counter()
    cases: list[dict[str, Any]] = []
    meeting_net: Counter[str] = Counter()
    for race in races:
        ranked = race.ranked
        if len(ranked) < 3:
            continue
        rank1, rank2, rank3 = ranked[:3]
        actual_top3 = {horse.number for horse in race.horses if horse.finish <= 3}
        winner = race.winner
        selected2 = rank2
        decision = {
            "raw_advantage": 0.0,
            "uncertainty_penalty": 0.0,
            "adjusted_advantage": 0.0,
            "component_wins": 0,
            "absolute_support": weighted_evidence(rank3, PROFILES["balanced"]),
        }
        promoted = False
        if candidate is not None:
            promoted, decision = should_promote(rank2, rank3, candidate)
            if promoted:
                selected2 = rank3

        baseline_top2 = {rank1.number, rank2.number}
        candidate_top2 = {rank1.number, selected2.number}
        totals["races"] += 1
        totals["baseline_winner_top2"] += int(winner.number in baseline_top2)
        totals["candidate_winner_top2"] += int(winner.number in candidate_top2)
        totals["baseline_top2_hits"] += len(baseline_top2 & actual_top3)
        totals["candidate_top2_hits"] += len(candidate_top2 & actual_top3)
        totals["baseline_both_top3"] += int(len(baseline_top2 & actual_top3) == 2)
        totals["candidate_both_top3"] += int(len(candidate_top2 & actual_top3) == 2)
        totals["winner_rank1"] += int(winner.number == rank1.number)
        totals["winner_rank2"] += int(winner.number == rank2.number)
        totals["winner_rank3"] += int(winner.number == rank3.number)
        if promoted:
            totals["promotions"] += 1
            helped = winner.number == rank3.number
            harmed = winner.number == rank2.number
            totals["helped_winner"] += int(helped)
            totals["harmed_winner"] += int(harmed)
            meeting_net[race.meeting] += int(helped) - int(harmed)
            cases.append(
                {
                    "meeting": race.meeting,
                    "race": race.race_number,
                    "winner": f"#{winner.number} {winner.name}",
                    "rank2": f"#{rank2.number} {rank2.name}",
                    "rank3": f"#{rank3.number} {rank3.name}",
                    "helped": helped,
                    "harmed": harmed,
                    "speed_delta": round(rank3.speed - rank2.speed, 3),
                    "formline_delta": round(rank3.formline - rank2.formline, 3),
                    "class_delta": round(rank3.class_score - rank2.class_score, 3),
                    "distance_delta": round(rank3.distance - rank2.distance, 3),
                    "risk_delta": round(rank3.risk - rank2.risk, 3),
                    "confidence_delta": round(rank3.confidence - rank2.confidence, 3),
                    **decision,
                }
            )
    count = totals["races"] or 1
    return {
        **dict(totals),
        "winner_top2_delta": totals["candidate_winner_top2"] - totals["baseline_winner_top2"],
        "top2_hits_delta": totals["candidate_top2_hits"] - totals["baseline_top2_hits"],
        "both_top3_delta": totals["candidate_both_top3"] - totals["baseline_both_top3"],
        "baseline_winner_top2_rate": round(totals["baseline_winner_top2"] / count * 100, 1),
        "candidate_winner_top2_rate": round(totals["candidate_winner_top2"] / count * 100, 1),
        "meeting_net": dict(sorted(meeting_net.items())),
        "positive_meetings": sum(1 for value in meeting_net.values() if value > 0),
        "negative_meetings": sum(1 for value in meeting_net.values() if value < 0),
        "cases": cases,
    }


def rank3_winner_diagnostics(races: Iterable[Race]) -> dict[str, Any]:
    rows = []
    for race in races:
        ranked = race.ranked
        if len(ranked) < 3 or race.winner.number != ranked[2].number:
            continue
        rank2, rank3 = ranked[1], ranked[2]
        rows.append(
            {
                "meeting": race.meeting,
                "race": race.race_number,
                "winner": f"#{rank3.number} {rank3.name}",
                "score_gap_to_rank2": round(rank2.score - rank3.score, 3),
                "speed_delta": round(rank3.speed - rank2.speed, 3),
                "formline_delta": round(rank3.formline - rank2.formline, 3),
                "class_delta": round(rank3.class_score - rank2.class_score, 3),
                "distance_delta": round(rank3.distance - rank2.distance, 3),
                "risk_delta": round(rank3.risk - rank2.risk, 3),
                "confidence_delta": round(rank3.confidence - rank2.confidence, 3),
            }
        )
    numeric_keys = (
        "score_gap_to_rank2",
        "speed_delta",
        "formline_delta",
        "class_delta",
        "distance_delta",
        "risk_delta",
        "confidence_delta",
    )
    averages = {
        key: round(statistics.mean(row[key] for row in rows), 3) if rows else 0.0
        for key in numeric_keys
    }
    return {"count": len(rows), "averages": averages, "cases": rows}


def split_archive(races: list[Race]) -> tuple[list[Race], list[Race]]:
    meetings = sorted({(race.date, race.meeting) for race in races})
    cut = max(1, math.floor(len(meetings) * 0.70))
    development_meetings = {name for _date, name in meetings[:cut]}
    return (
        [race for race in races if race.meeting in development_meetings],
        [race for race in races if race.meeting not in development_meetings],
    )


def model_payload(races: list[Race]) -> dict[str, Any]:
    development, temporal_holdout = split_archive(races)
    payload: dict[str, Any] = {
        "coverage": {
            "meetings": len({race.meeting for race in races}),
            "races": len(races),
            "development_meetings": len({race.meeting for race in development}),
            "development_races": len(development),
            "temporal_holdout_meetings": len({race.meeting for race in temporal_holdout}),
            "temporal_holdout_races": len(temporal_holdout),
        },
        "baseline_all": evaluate(races),
        "rank3_winner_diagnostics": rank3_winner_diagnostics(races),
        "candidates": {},
    }
    for candidate in CANDIDATES:
        payload["candidates"][candidate.name] = {
            "development": evaluate(development, candidate),
            "temporal_holdout": evaluate(temporal_holdout, candidate),
            "all_archive": evaluate(races, candidate),
        }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--holdout-meeting-dir", type=Path)
    parser.add_argument("--holdout-results-file", type=Path)
    parser.add_argument("--independent-root", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "scratch" / "hkjc_top2_promotion_shadow.json",
    )
    args = parser.parse_args()

    archive_races = load_archive_races(args.dataset)
    payload = {
        "method": {
            "market_free": True,
            "allowed_signals": ["speed", "formline", "class", "distance", "risk", "confidence"],
            "excluded_signals": ["odds", "market", "going", "draw", "rank4_to_rank7"],
            "decision_scope": "swap current rank 2 and current rank 3 only; rank 1 remains unchanged",
        },
        "archive": model_payload(archive_races),
    }
    if args.holdout_meeting_dir and args.holdout_results_file:
        holdout_races = load_holdout_races(args.holdout_meeting_dir, args.holdout_results_file)
        payload["external_holdout"] = {
            "coverage": {
                "meeting": args.holdout_meeting_dir.name,
                "races": len(holdout_races),
            },
            "baseline": evaluate(holdout_races),
            "rank3_winner_diagnostics": rank3_winner_diagnostics(holdout_races),
            "candidates": {
                candidate.name: evaluate(holdout_races, candidate)
                for candidate in CANDIDATES
            },
        }
    if args.independent_root:
        independent_races, independent_skipped = load_independent_races(
            args.independent_root,
            {race.meeting for race in archive_races},
        )
        payload["independent_holdout"] = {
            "coverage": {
                "meetings": len({race.meeting for race in independent_races}),
                "races": len(independent_races),
                "skipped": independent_skipped,
            },
            "baseline": evaluate(independent_races),
            "rank3_winner_diagnostics": rank3_winner_diagnostics(independent_races),
            "candidates": {
                candidate.name: evaluate(independent_races, candidate)
                for candidate in CANDIDATES
            },
        }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
