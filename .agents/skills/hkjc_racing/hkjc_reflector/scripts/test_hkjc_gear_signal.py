#!/usr/bin/env python3
"""Evaluate HKJC first-time / removed-gear signals without changing live scoring.

The test reads pre-race gear declarations from archived racecards.  HKJC's
numeric suffix denotes the use count, therefore only an active ``*1`` token is
first-time; ``B2`` is deliberately not classified as first-time blinkers.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[5]
DEFAULT_DATASET = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "artifacts" / "hkjc_ranking_dataset.csv"
DEFAULT_REPORT = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "artifacts" / "hkjc_gear_signal_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test HKJC declared gear signals on archived races")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--min-train-meetings", type=int, default=6)
    parser.add_argument("--date-from", help="Inclusive ISO date filter")
    parser.add_argument("--date-to", help="Inclusive ISO date filter")
    parser.add_argument("--json", action="store_true", help="Print the full report")
    return parser.parse_args()


def _racecard_gears(meeting: str, race_number: int, cache: dict[tuple[str, int], dict[int, str]]) -> dict[int, str]:
    key = (meeting, race_number)
    if key in cache:
        return cache[key]
    files = sorted(Path(meeting).glob(f"*Race {race_number} 排位表.md"))
    gears: dict[int, str] = {}
    if files:
        content = files[0].read_text(encoding="utf-8")
        for block in re.split(r"(?=^馬號:\s*\d+\s*$)", content, flags=re.MULTILINE):
            horse_match = re.search(r"^馬號:\s*(\d+)\s*$", block, re.MULTILINE)
            gear_match = re.search(r"^配備:\s*(.*?)\s*$", block, re.MULTILINE)
            if horse_match:
                gears[int(horse_match.group(1))] = gear_match.group(1).strip() if gear_match else ""
    cache[key] = gears
    return gears


def classify_gear(value: object) -> dict[str, Any]:
    tokens = [token.strip().upper() for token in re.split(r"[/,]", str(value or "")) if token.strip()]
    active = [token for token in tokens if not token.endswith("-")]
    first_codes = [re.sub(r"\d+$", "", token) for token in active if re.search(r"1$", token)]
    removed_codes = [token[:-1] for token in tokens if token.endswith("-")]
    return {
        "gear": str(value or ""),
        "first_time_codes": first_codes,
        "first_time_any": bool(first_codes),
        "first_time_blinkers": "B" in first_codes,
        "first_time_visor": "V" in first_codes,
        "first_time_other": bool(set(first_codes) - {"B", "V"}),
        "gear_removed": bool(removed_codes),
        "gear_changed": bool(first_codes or removed_codes),
    }


def attach_gear(df: pd.DataFrame) -> pd.DataFrame:
    cache: dict[tuple[str, int], dict[int, str]] = {}
    pairs = {(str(row.meeting), int(row.race_number)) for row in df.itertuples(index=False)}
    for meeting, race_number in pairs:
        cache[(meeting, race_number)] = _racecard_gears(meeting, race_number, cache)
    rows = []
    for row in df.itertuples(index=False):
        gear = cache[(str(row.meeting), int(row.race_number))].get(int(row.horse_number), "")
        rows.append(classify_gear(gear))
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def _rate_summary(frame: pd.DataFrame) -> dict[str, Any]:
    count = len(frame)
    return {
        "runners": count,
        "wins": int(frame["is_win"].sum()),
        "top3": int(frame["is_top3"].sum()),
        "win_rate": round(float(frame["is_win"].mean()), 4) if count else None,
        "top3_rate": round(float(frame["is_top3"].mean()), 4) if count else None,
        "mean_finish": round(float(frame["finish_pos"].mean()), 3) if count else None,
    }


def observational_summary(df: pd.DataFrame) -> dict[str, Any]:
    groups = {
        "first_time_any": df["first_time_any"],
        "first_time_blinkers": df["first_time_blinkers"],
        "first_time_visor": df["first_time_visor"],
        "first_time_other": df["first_time_other"],
        "gear_removed": df["gear_removed"],
    }
    output: dict[str, Any] = {}
    for label, mask in groups.items():
        output[label] = {}
        for venue, venue_df in df.groupby("venue"):
            signal = venue_df[mask.loc[venue_df.index]]
            control = venue_df[~mask.loc[venue_df.index]]
            output[label][str(venue)] = {"signal": _rate_summary(signal), "control": _rate_summary(control)}
    return output


def _candidate_delta(frame: pd.DataFrame, name: str) -> pd.Series:
    delta = pd.Series(0.0, index=frame.index)
    if name == "baseline":
        return delta
    if name == "first_time_any_penalty_1":
        return delta.mask(frame["first_time_any"], -1.0)
    if name == "first_time_any_penalty_2":
        return delta.mask(frame["first_time_any"], -2.0)
    if name == "first_time_blinkers_hv_bonus_1":
        return delta.mask(frame["first_time_blinkers"] & (frame["venue"] == "跑馬地"), 1.0)
    if name == "first_time_blinkers_hv_bonus_2":
        return delta.mask(frame["first_time_blinkers"] & (frame["venue"] == "跑馬地"), 2.0)
    raise ValueError(f"Unknown candidate: {name}")


def _evaluate(frame: pd.DataFrame, candidate: str) -> dict[str, int]:
    totals = defaultdict(int)
    for _race, race in frame.groupby(["meeting", "race_number"], sort=False):
        race = race.copy()
        race["candidate_score"] = race["current_live_rank_score"].fillna(race["current_live_recomputed_ability"]).astype(float)
        race["candidate_score"] += _candidate_delta(race, candidate)
        ranked = race.sort_values(["candidate_score", "horse_number"], ascending=[False, True])
        picks = ranked.head(4)
        actual_top3 = set(race.loc[race["finish_pos"] <= 3, "horse_number"])
        winner = race.loc[race["finish_pos"] == 1, "horse_number"]
        totals["races"] += 1
        totals["champion"] += int(bool(len(picks)) and int(picks.iloc[0].horse_number) in set(winner))
        totals["top3_has_champion"] += int(bool(set(picks.head(3).horse_number) & set(winner)))
        totals["top3_hits"] += len(set(picks.head(3).horse_number) & actual_top3)
        totals["top4_hits"] += len(set(picks.horse_number) & actual_top3)
    return dict(totals)


def walk_forward(df: pd.DataFrame, min_train_meetings: int) -> dict[str, Any]:
    candidates = [
        "baseline",
        "first_time_any_penalty_1",
        "first_time_any_penalty_2",
        "first_time_blinkers_hv_bonus_1",
        "first_time_blinkers_hv_bonus_2",
    ]
    meetings = [(date, group) for date, group in df.groupby("date", sort=True)]
    results = {"baseline": defaultdict(int), "selected": defaultdict(int)}
    folds = []
    for index, (date, test) in enumerate(meetings):
        if index < min_train_meetings:
            continue
        train = pd.concat([group for _, group in meetings[:index]], ignore_index=True)
        train_scores = {candidate: _evaluate(train, candidate) for candidate in candidates}
        selected = max(
            candidates,
            key=lambda candidate: (
                train_scores[candidate]["champion"],
                train_scores[candidate]["top3_has_champion"],
                train_scores[candidate]["top3_hits"],
                -candidates.index(candidate),
            ),
        )
        baseline = _evaluate(test, "baseline")
        chosen = _evaluate(test, selected)
        for label, values in (("baseline", baseline), ("selected", chosen)):
            for key, value in values.items():
                results[label][key] += value
        folds.append({"date": str(date), "selected_candidate": selected, "baseline": baseline, "selected": chosen})
    return {"folds": folds, "aggregate": {label: dict(values) for label, values in results.items()}}


def run(dataset_path: Path, min_train_meetings: int, date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    frame = pd.read_csv(dataset_path, encoding="utf-8-sig")
    frame["date"] = frame["date"].astype(str)
    if date_from:
        frame = frame[frame["date"] >= date_from].copy()
    if date_to:
        frame = frame[frame["date"] <= date_to].copy()
    if frame.empty:
        raise ValueError("No rows remain after date filtering")
    frame = attach_gear(frame)
    return {
        "dataset": str(dataset_path),
        "coverage": {
            "meetings": int(frame["meeting"].nunique()),
            "races": int(frame[["meeting", "race_number"]].drop_duplicates().shape[0]),
            "runners": int(len(frame)),
            "date_range": [str(frame["date"].min()), str(frame["date"].max())],
            "racecard_gear_coverage": round(float((frame["gear"] != "").mean()), 4),
        },
        "observational": observational_summary(frame),
        "walk_forward": walk_forward(frame, min_train_meetings),
    }


def main() -> int:
    args = parse_args()
    report = run(Path(args.dataset), args.min_train_meetings, args.date_from, args.date_to)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        coverage = report["coverage"]
        aggregate = report["walk_forward"]["aggregate"]
        print(f"Gear study: {coverage['meetings']} meetings / {coverage['races']} races / {coverage['runners']} runners")
        print(f"Walk-forward baseline: {aggregate.get('baseline', {})}")
        print(f"Walk-forward selected: {aggregate.get('selected', {})}")
        print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
