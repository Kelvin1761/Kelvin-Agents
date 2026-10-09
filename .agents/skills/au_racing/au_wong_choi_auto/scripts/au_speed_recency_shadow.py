#!/usr/bin/env python3
"""Blind second arm for the AU speed terminal (EXP-20261009-05).

Candidate (locked): point-in-time WinningTime speed figures, newest first,
weights 1.0/0.8/0.64/0.51/0.41/0.33 (max 6, min 2 runs), within-race z,
residualised on within-race ``pace_figure_score`` z, added as
``final_rank_score + 0.5 × residual``.

Shares the EXP-20260927-02 terminal: races from 2026-09-27, the same 2,000-race
complete-day sample rule.  Until that sample exists this writes counts only —
no outcome metric — so nobody can tune the locked candidate on the terminal.
Production ranking is never changed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

from au_feature_ab import MEETING_RE, _historical_results  # noqa: E402
from au_leaf_power import norm  # noqa: E402
from au_speed_shadow_monitor import START_DATE, TARGET_RACES, select_complete_date_sample  # noqa: E402
from au_speed_venue_audit import (  # noqa: E402
    build_asof_standards,
    collect_reference_races,
    parse_run,
    scored_meeting_index,
)
from au_unused_field_power import RE_HDR_DIST, RE_RUNNER  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402

EXPERIMENT_ID = "EXP-20261009-05"
SPEED_K = 0.5
RECENCY_WEIGHTS = (1.0, 0.8, 0.64, 0.51, 0.41, 0.33)
MIN_RUNS = 2
ORTHOGONALISE_MIN_RUNNERS = 3
FIELD_BUCKETS = (("le8", 0, 8), ("9_10", 9, 10), ("11_12", 11, 12), ("ge13", 13, 99))


def config() -> dict:
    values = {
        "experiment_id": EXPERIMENT_ID, "start_date": START_DATE, "target_races": TARGET_RACES,
        "speed_k": SPEED_K, "recency_weights": list(RECENCY_WEIGHTS), "min_runs": MIN_RUNS,
        "orthogonalise_on": "pace_figure_score",
    }
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    values["config_sha256"] = hashlib.sha256(encoded).hexdigest()
    return values


def recency_speed(block: str, standards: tuple, target_date: str) -> float | None:
    base, going, _ = standards
    figures = []
    for line in block.splitlines():
        run = parse_run(line)
        if run is None or run["date"] >= target_date:
            continue
        standard = base.get((run["track"], run["distance"]))
        if standard is None:
            continue
        seconds_per_length = 2.4 / (run["distance"] / run["winning_time"])
        own = run["winning_time"] + run["margin"] * seconds_per_length
        adjusted = own - standard - going.get(run["condition"], 0.0)
        figures.append((run["date"], -adjusted / (run["distance"] / 1000.0)))
    if len(figures) < MIN_RUNS:
        return None
    values = [value for _, value in sorted(figures, reverse=True)][: len(RECENCY_WEIGHTS)]
    weights = RECENCY_WEIGHTS[: len(values)]
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


def _z(values: list) -> list[float]:
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return [0.0] * len(values)
    mean, spread = statistics.mean(present), statistics.pstdev(present)
    return [0.0 if v is None or spread <= 0 else (v - mean) / spread for v in values]


def residual(speed_z: list[float], has_speed: list[bool], pf_z: list[float]) -> list[float]:
    pairs = [(s, p) for s, p, h in zip(speed_z, pf_z, has_speed) if h]
    if len(pairs) < ORTHOGONALISE_MIN_RUNNERS:
        return speed_z
    ms, mp = statistics.mean(s for s, _ in pairs), statistics.mean(p for _, p in pairs)
    var = sum((p - mp) ** 2 for _, p in pairs)
    beta = sum((s - ms) * (p - mp) for s, p in pairs) / var if var > 0 else 0.0
    return [s - beta * p if h else 0.0 for s, p, h in zip(speed_z, pf_z, has_speed)]


def candidate_order(runners: list[dict]) -> list[int]:
    speeds = [r["speed"] for r in runners]
    adj = residual(_z(speeds), [s is not None for s in speeds], _z([r["pace_figure"] for r in runners]))
    ranked = sorted(zip(runners, adj), key=lambda item: (-(item[0]["score"] + SPEED_K * item[1]), item[0]["number"]))
    return [r["number"] for r, _ in ranked]


def load_terminal(root: Path) -> list[dict]:
    observations, _ = collect_reference_races(root)
    index = scored_meeting_index(root)
    results = _historical_results(root)
    dates = sorted({m.group(1) for name in index if (m := MEETING_RE.match(name)) and m.group(1) >= START_DATE})
    standards_by_date = build_asof_standards(observations, dates)
    rows = []
    for name, folder in sorted(index.items()):
        meeting = MEETING_RE.match(name)
        if not meeting or meeting.group(1) < START_DATE:
            continue
        date, venue = meeting.group(1), meeting.group(2).strip()
        actual_by_race, standards = results.get((date, norm(venue))), standards_by_date.get(date)
        if not actual_by_race or standards is None:
            continue
        scoring = defaultdict(dict)
        with open(folder / "Meeting_Auto_Scoring.csv", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                scoring[int(row["race_number"])][norm(row["horse_name"])] = row
        for formguide in sorted(folder.glob("*Formguide.md")):
            text = formguide.read_text(encoding="utf-8", errors="replace")
            header = RE_HDR_DIST.search(text)
            if not header:
                continue
            race_no = int(header.group(1))
            actual, score_rows = actual_by_race.get(race_no), scoring.get(race_no)
            if not actual or not score_rows:
                continue
            starts = [m.start() for m in RE_RUNNER.finditer(text)]
            runners = []
            for i, match in enumerate(RE_RUNNER.finditer(text)):
                end = starts[i + 1] if i + 1 < len(starts) else len(text)
                key = norm(match.group(2))
                score_row, position = score_rows.get(key), actual.get(key)
                if score_row is None or position is None:
                    continue
                runners.append({
                    "number": int(score_row["horse_number"]),
                    "score": float(score_row["final_rank_score"]),
                    "pace_figure": float(score_row["pace_figure_score"]),
                    "speed": recency_speed(text[match.start():end], standards, date),
                    "position": int(position),
                })
            if len(runners) >= 5:
                rows.append({"date": date, "venue": venue, "race": race_no, "runners": runners})
    return sorted(rows, key=lambda r: (r["date"], r["venue"], r["race"]))


def _metrics(race: dict, order: list[int]) -> dict | None:
    pos = {r["number"]: r["position"] for r in race["runners"]}
    top3 = [n for n, p in pos.items() if p <= 3]
    if len(top3) < 3:
        return None
    m = race_metrics(order, top3, None, pos, len(order))
    return {"gold": int(m["gold"]), "good": int(m["good_positional"])}


def _ci(deltas: list[int], seed: int = 7, boot: int = 2000) -> list[float]:
    rng, n = random.Random(seed), len(deltas)
    draws = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(boot))
    return [round(100 * draws[int(0.025 * boot)], 3), round(100 * draws[int(0.975 * boot) - 1], 3)]


def evaluate(sample: list[dict]) -> dict:
    pairs = []
    for race in sample:
        base = _metrics(race, [r["number"] for r in sorted(race["runners"], key=lambda r: (-r["score"], r["number"]))])
        cand = _metrics(race, candidate_order(race["runners"]))
        if base and cand:
            pairs.append((race, base, cand))
    out = {"races": len(pairs)}
    for key in ("gold", "good"):
        deltas = [c[key] - b[key] for _, b, c in pairs]
        out[key] = {"delta_pp": round(100 * sum(deltas) / len(deltas), 3), "ci95_pp": _ci(deltas)}
    cohorts = {}
    for label, lo, hi in FIELD_BUCKETS:
        sub = [(b, c) for race, b, c in pairs if lo <= len(race["runners"]) <= hi]
        if sub:
            cohorts[label] = {k: _ci([c[k] - b[k] for b, c in sub]) for k in ("gold", "good")} | {"races": len(sub)}
    out["field_cohorts"] = cohorts
    primary_ok = out["gold"]["delta_pp"] >= 0 and out["good"]["delta_pp"] >= 0
    ci_ok = out["gold"]["ci95_pp"][0] > 0 or out["good"]["ci95_pp"][0] > 0
    cohort_bad = [label for label, c in cohorts.items() if c["gold"][1] < 0 or c["good"][1] < 0]
    out["verdict"] = "PASS_CANDIDATE" if primary_ok and ci_ok and not cohort_bad else "REJECT"
    out["reason"] = ("ok" if out["verdict"] == "PASS_CANDIDATE" else
                     "primary_negative" if not primary_ok else
                     "no_primary_ci_above_zero" if not ci_ok else f"cohort_regression:{cohort_bad}")
    return out


def run(root: Path, output: Path) -> dict:
    rows = load_terminal(root)
    sample = select_complete_date_sample(rows, TARGET_RACES)
    cfg = config()
    status = {"config": cfg, "races_collected": len(sample) if len(sample) >= TARGET_RACES else len(rows),
              "race_days": len({r["date"] for r in rows}), "outcomes_visible": False, "state": "collecting"}
    if len(sample) >= TARGET_RACES:
        keys = [f"{r['date']}|{norm(r['venue'])}|{r['race']}" for r in sample]
        status.update({
            "state": "revealed", "outcomes_visible": True,
            "sample_sha256": hashlib.sha256("\n".join(keys).encode()).hexdigest(),
            "date_to": sample[-1]["date"], "evaluation": evaluate(sample),
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f".{output.name}.tmp")
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(output)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    status = run(args.data_root, args.output)
    print(f"{EXPERIMENT_ID}: {status['state']} — {status['races_collected']}/{TARGET_RACES} races, "
          f"{status['race_days']} days")
    if not status["outcomes_visible"]:
        print("Blind collection: outcome metrics remain sealed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
