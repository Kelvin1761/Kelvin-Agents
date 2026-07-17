#!/usr/bin/env python3
"""Research shadow test: fill default jockey/trainer scores with leak-free
as-of-date empirical ratings built from AU_Historical_Raw_Race_Results.csv.

Candidate: for horses whose stored jockey_score / trainer_score is the 60.0
default (name missing from the curated ratings CSVs), substitute an empirical
rating computed ONLY from results strictly before the meeting date (expanding
window, shrunk toward the global prior). Rated names are left untouched.
Ability is recomputed through the live matrix formula with only the
jockey_trainer dimension replaced. Baseline = plain matrix reconstruction.

Gate: same as Phase-5 (Good any-2 >= +1.5pp OOS, losses <= 0.5pp, Miss
non-regression, Top3 fold stability >= 4/5).
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")

from au_archive_calibrator import HISTORICAL_RESULTS_CSV, MATRIX_KEYS, normalize_horse_name  # noqa: E402
from au_cached_walkforward_ml import (  # noqa: E402
    as_float,
    date_folds,
    group_races,
    materialize_dataset,
    metrics_for_races,
)
from scoring import MATRIX_WEIGHTS  # noqa: E402

JT_FORMULA = (("jockey_score", 0.28), ("trainer_score", 0.20), ("jockey_horse_fit_score", 0.52))
MIN_RIDES = 5
SHRINK_K = 10.0
SCALE = 30.0  # rating points per unit of top3-rate deviation
CLAMP = (50.0, 72.0)


def load_results() -> list[dict]:
    with open(HISTORICAL_RESULTS_CSV, encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def build_join(results: list[dict]) -> dict[tuple, dict]:
    """(date, track-lower, race, normalized horse) -> {jockey, trainer}."""
    join = {}
    for row in results:
        key = (
            str(row.get("Date") or "").strip(),
            str(row.get("Track") or "").strip().lower(),
            str(row.get("Race") or "").strip(),
            normalize_horse_name(str(row.get("Horse") or "")),
        )
        join[key] = {
            "jockey": str(row.get("Jockey") or "").strip(),
            "trainer": str(row.get("Trainer") or "").strip(),
            "top3": str(row.get("Pos") or "").strip() in {"1", "2", "3"},
            "date": key[0],
        }
    return join


def empirical_tables(results: list[dict]) -> tuple[dict, dict, float]:
    """Per-name chronological (date, top3) events for expanding-window rating."""
    jockey_events: dict[str, list[tuple[str, int]]] = defaultdict(list)
    trainer_events: dict[str, list[tuple[str, int]]] = defaultdict(list)
    total = hits = 0
    for row in results:
        date = str(row.get("Date") or "").strip()
        top3 = 1 if str(row.get("Pos") or "").strip() in {"1", "2", "3"} else 0
        jockey = str(row.get("Jockey") or "").strip()
        trainer = str(row.get("Trainer") or "").strip()
        if jockey:
            jockey_events[jockey].append((date, top3))
        if trainer:
            trainer_events[trainer].append((date, top3))
        total += 1
        hits += top3
    prior = hits / max(1, total)
    for events in (jockey_events, trainer_events):
        for name in events:
            events[name].sort()
    return jockey_events, trainer_events, prior


def rating_asof(events: list[tuple[str, int]], asof: str, prior: float) -> float | None:
    rides = wins = 0
    for date, top3 in events:
        if date >= asof:
            break
        rides += 1
        wins += top3
    if rides < MIN_RIDES:
        return None
    rate = (wins + prior * SHRINK_K) / (rides + SHRINK_K)
    return max(CLAMP[0], min(CLAMP[1], 60.0 + SCALE * (rate - prior)))


def main() -> int:
    results = load_results()
    join = build_join(results)
    jockey_events, trainer_events, prior = empirical_tables(results)
    races = group_races(materialize_dataset())

    matched = filled_j = filled_t = 0
    unmatched = 0
    for race in races:
        first = race[0]
        for row in race:
            key = (
                str(first["date"]),
                str(first.get("track") or "").strip().lower(),
                str(first["race"]),
                normalize_horse_name(str(row.get("horse_name") or "")),
            )
            hit = join.get(key)
            row["_jt"] = hit
            if hit is None:
                unmatched += 1
                continue
            matched += 1

    def candidate_jt(row: dict, asof: str) -> float:
        parts = []
        for feat, weight in JT_FORMULA:
            value = as_float(row.get(feat), 60.0)
            if abs(value - 60.0) < 1e-9 and row.get("_jt"):
                name = row["_jt"]["jockey"] if feat == "jockey_score" else (
                    row["_jt"]["trainer"] if feat == "trainer_score" else "")
                if name:
                    events = jockey_events.get(name) if feat == "jockey_score" else trainer_events.get(name)
                    emp = rating_asof(events or [], asof, prior)
                    if emp is not None:
                        value = emp
            parts.append(weight * value)
        return sum(parts)

    def reconstruction(row: dict, jt_value: float | None = None) -> float:
        score = 0.0
        for key in MATRIX_KEYS:
            value = jt_value if (key == "jockey_trainer" and jt_value is not None) else as_float(
                row.get(f"mx_{key}"), 60.0)
            score += MATRIX_WEIGHTS.get(key, 0.0) * value
        return score

    def score_baseline(races_in):
        return [[{**row, "_score": reconstruction(row)} for row in race] for race in races_in]

    def score_candidate(races_in):
        out = []
        for race in races_in:
            asof = str(race[0]["date"])
            out.append([{**row, "_score": reconstruction(row, candidate_jt(row, asof))} for row in race])
        return out

    # count fills in OOS window
    folds = date_folds(races)
    valid = [race for _t, v in folds for race in v]
    for race in valid:
        asof = str(race[0]["date"])
        for row in race:
            if not row.get("_jt"):
                continue
            if abs(as_float(row.get("jockey_score"), 60.0) - 60.0) < 1e-9 and rating_asof(
                    jockey_events.get(row["_jt"]["jockey"], []), asof, prior) is not None:
                filled_j += 1
            if abs(as_float(row.get("trainer_score"), 60.0) - 60.0) < 1e-9 and rating_asof(
                    trainer_events.get(row["_jt"]["trainer"], []), asof, prior) is not None:
                filled_t += 1

    baseline = metrics_for_races(score_baseline(valid))
    candidate = metrics_for_races(score_candidate(valid))

    top3_non_worse = 0
    for _train, fold_valid in folds:
        b = metrics_for_races(score_baseline(fold_valid))
        c = metrics_for_races(score_candidate(fold_valid))
        top3_non_worse += c["top3_precision"] >= b["top3_precision"]

    def fmt(m):
        return (f"{m['races']}R {m['gold']}G/{m['good']}g2/{m['good_positional']}gp/"
                f"{m['pass']}P/{m['miss']}M Top3 {m['top3_precision']*100:.1f}% "
                f"WinT3 {m['winner_in_top3']*100:.1f}% Top1 {m['top1_win']*100:.1f}%")

    print(f"join: matched {matched} horses, unmatched {unmatched}")
    print(f"OOS fills: jockey {filled_j}, trainer {filled_t} (prior top3 rate {prior:.3f})")
    print(f"baseline : {fmt(baseline)}")
    print(f"candidate: {fmt(candidate)}")
    good_lift = (candidate['good'] - baseline['good']) / baseline['races'] * 100
    gp_lift = (candidate['good_positional'] - baseline['good_positional']) / baseline['races'] * 100
    print(f"good any-2 lift {good_lift:+.2f}pp; good positional lift {gp_lift:+.2f}pp; "
          f"miss Δ {candidate['miss']-baseline['miss']:+d}; folds top3 non-worse {top3_non_worse}/{len(folds)}")
    passed = (good_lift >= 1.5 and candidate['miss'] <= baseline['miss']
              and top3_non_worse >= 4
              and (baseline['top1_win'] - candidate['top1_win']) * 100 <= 0.5
              and (baseline['winner_in_top3'] - candidate['winner_in_top3']) * 100 <= 0.5
              and (baseline['gold'] - candidate['gold']) / baseline['races'] * 100 <= 0.5)
    print("DECISION:", "PASS" if passed else "FAIL / HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
