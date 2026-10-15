#!/usr/bin/env python3
"""Joint pace-capacity discovery; no production engine writes."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import re
from pathlib import Path
import statistics

import numpy as np
import au_contextual_gps_speed_20261015 as previous
from au_phase_speed_20261015 import (
    PhaseStandard,
    aggregate,
    phase_history,
    source_events,
)

ARMS = ("A", "J800", "JAdaptive")


def variants(history, model, response, length):
    days = defaultdict(list)
    for event in history:
        residual = math.log(event[response] / length(event)) - model.predict(event)
        days[(event["track"], event["date"])].append((event["key"], residual))
    output = {}
    for event in history:
        others = [r for k, r in days[(event["track"], event["date"])] if k != event["key"]]
        output[event["key"]] = (
            float(np.clip(statistics.median(others), -0.05, 0.05)) * len(others) / (len(others) + 3)
            if len(others) >= 3
            else 0
        )
    return output


def design(p, q):
    p, q = np.clip([p, q], -3, 3)
    return np.array([p, p * p, q, q * q, p * q])


def fit_within_horse(observations):
    grouped = defaultdict(list)
    for identity, x, y in observations:
        grouped[identity].append((x, y))
    xs, ys = [], []
    for values in grouped.values():
        if len(values) < 2:
            continue
        x = np.array([x for x, y in values])
        y = np.array([y for x, y in values])
        xs.extend(x - x.mean(axis=0))
        ys.extend(y - y.mean())
    if len(xs) < 100:
        return np.zeros(5), len(xs)
    x, y = np.array(xs), np.array(ys)
    return np.linalg.solve(x.T @ x + 100 * np.eye(5), x.T @ y), len(xs)


def capacity_lookup(full_events, xml_events, day, phase):
    history = [e for e in full_events if e["date"] < day]
    early_history = phase_history(xml_events, day, phase)
    if len(history) < 100 or len(early_history) < 100:
        return {}, {"events": len(history), "repeat_observations": 0}
    total = previous.ContextStandard(history, "total")
    early = PhaseStandard(early_history)
    vt = variants(history, total, "total", lambda e: e["distance"])
    ve = variants(early_history, early, "phase_time", lambda e: e["length"])
    totals = {e["key"]: e for e in history}
    observations, pending = [], []
    for event in early_history:
        full = totals[event["key"]]
        by_horse = {r["horse"]: r for r in full["rows"]}
        p = -(math.log(event["phase_time"] / event["length"]) - early.predict(event) - ve[event["key"]]) / 0.03
        for row in event["rows"]:
            time = row["phases"][phase]["time"]
            q = -math.log(time / event["phase_time"]) / 0.03
            x = design(p, q)
            original = by_horse[row["horse"]]
            # Class is a nuisance when fitting within-horse pace response.
            y = -(math.log(original["time"] / event["distance"]) - total.predict(full) - vt[event["key"]]) * 1000
            a = -(math.log(original["time"] / event["distance"]) - total.predict(full, True) - vt[event["key"]]) * 1000
            identity = ("id", row["horse_code"]) if row.get("horse_code") else ("name", row["horse"])
            observations.append((identity, x, y))
            pending.append(((event["key"], row["horse"]), a, x, event["going"]))
    beta, repeats = fit_within_horse(observations)
    lookup = {key: (a - float(beta @ x), going) for key, a, x, going in pending}
    return lookup, {
        "events": len(history),
        "early_events": len(early_history),
        "repeat_observations": repeats,
        "beta": beta.tolist(),
        "train_through": max(e["date"] for e in history),
    }


def build(args):
    blocks, metadata, hashes = previous.load_form(args.root)
    full_events, _ = previous.load_xml_sources(args.cache, metadata)
    xml_events, quality = source_events(args.cache)
    obj = json.loads(args.reference.read_text())
    races = obj["races"]
    daily = defaultdict(list)
    for race in races:
        daily[race["date"]].append(race)
    states = []
    for day, meetings in sorted(daily.items()):
        lookups = {}
        for arm, phase in (("J800", "E800"), ("JAdaptive", "Adaptive")):
            lookups[arm], state = capacity_lookup(full_events, xml_events, day, phase)
            states.append({"date": day, "arm": arm, **state})
        for race in meetings:
            for row in race["rows"]:
                row["joint_raw"], row["joint_reliability"] = {}, {}
                for arm in ("J800", "JAdaptive"):
                    v, confidence, n = aggregate(
                        blocks.get((race["meeting"], race["race"], previous.norm(row["name"])), []),
                        previous.norm(row["name"]),
                        day,
                        int(re.search(r"\d+", str(row["distance"]))[0]),
                        previous.condition_key(row.get("going") or ""),
                        lookups[arm],
                    )
                    row["joint_raw"][arm] = v
                    row["joint_reliability"][arm] = confidence
            for arm in ("J800", "JAdaptive"):
                for row, z in zip(race["rows"], previous.zscores([r["joint_raw"][arm] for r in race["rows"]])):
                    row[arm] = z * row["joint_reliability"][arm]
        print("joint", day, {s["arm"]: s["beta"] for s in states[-2:]}, flush=True)
    args.out.write_text(
        json.dumps(
            {
                "races": races,
                "states": states,
                "source_quality": quality,
                "baseline_sha256": obj["baseline_sha256"],
                "source_manifest_sha256": obj["source_manifest_sha256"],
                "reference_sha256": hashlib.sha256(args.reference.read_bytes()).hexdigest(),
                "form_manifest_sha256": hashlib.sha256(json.dumps(hashes).encode()).hexdigest(),
            }
        )
    )


def evaluate(args):
    from au_eval import _counts, default_scorer
    from au_trial_cutoff_refit_20261015 import metric_table
    from model_evaluation_decision import holm_adjust

    obj = json.loads(args.features.read_text())
    races = obj["races"]
    allrows = [row for race in races for row in race["rows"]]
    assert max(abs(default_scorer(r) - r["ability"]) for r in allrows) < 0.00011
    canonical = _counts(races, lambda r: r["ability"])
    fast = metric_table(races, np.array([[r["ability"] for r in allrows]]))[0].mean(axis=0) * 100
    assert np.max(np.abs(fast - np.array([canonical[k] for k in ("gold", "good_positional", "pass", "t3prec")]))) < 1e-8
    dates = sorted({r["date"] for r in races})
    oos, windows = [], []
    for start in range(30, len(dates), 7):
        test = set(dates[start : start + 7])
        train = [r for r in races if r["date"] < dates[start]]
        daily = [r for r in races if r["date"] in test]
        state = {"test_dates": sorted(test), "fits": {}}
        for arm in ARMS:
            gain, metadata = previous.fit_gain(train, arm)
            assert metadata["train_through"] < min(test)
            state["fits"][arm] = {"gain": gain, **metadata}
            for race in daily:
                for row in race["rows"]:
                    row["candidate_" + arm] = round(row["ability"] + gain * row[arm], 4)
        windows.append(state)
        oos.extend(daily)
        print("gains", dates[start], {a: state["fits"][a]["gain"] for a in ARMS}, flush=True)
    old = json.loads(args.previous_predictions.read_text())["races"]

    def frozen_a(rows):
        return {(r["date"], r["meeting"], r["race"], x["n"]): x["candidate_A"] for r in rows for x in r["rows"]}

    assert frozen_a(old) == frozen_a(oos), "EXP-04 A predictions must reproduce exactly"
    report = {
        "status": "DISCOVERY_ONLY_NO_PROMOTION",
        "source_availability": "FLAG",
        "baseline_commit": "7a962be562ecb0af461daa71114b1dddf66ec8cd",
        "baseline_sha256": obj["baseline_sha256"],
        "source_manifest_sha256": obj["source_manifest_sha256"],
        "features_sha256": hashlib.sha256(args.features.read_bytes()).hexdigest(),
        "a_reproduced_exactly": True,
        "windows": windows,
        "comparisons": {a: previous.effects(oos, "ability", "candidate_" + a) for a in ARMS},
        "ablations": {a: previous.effects(oos, "candidate_A", "candidate_" + a) for a in ARMS[1:]},
        "feature_diagnostics_oos": {a: diagnostic(oos, a) for a in ARMS[1:]},
    }
    report["family_holm_primary_p"] = holm_adjust(
        {
            a + ":" + m: report["comparisons"][a]["evidence"][m]["p_two_sided"]
            for a in ARMS
            for m in ("gold", "good_positional")
        }
    )
    report["a_a"] = previous.effects(oos, "ability", "ability")
    assert all(x["delta"] == 0 for x in report["a_a"]["evidence"].values())
    args.out.write_text(json.dumps(report, indent=2))
    args.out.with_suffix(".predictions.json").write_text(json.dumps({"races": oos, "states": obj["states"]}))


def diagnostic(races, arm):
    from au_phase_speed_20261015 import summarize
    from au_phase_speed_20261015 import PHASES

    converted = []
    for race in races:
        rows = [
            {**r, "phase_raw": {p: r["joint_raw"][arm] for p in PHASES + ("Total_reference",)}} for r in race["rows"]
        ]
        converted.append({**race, "rows": rows})
    return summarize(converted)["E800"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "evaluate"))
    for option in ("root", "cache", "reference", "features", "previous-predictions", "out"):
        parser.add_argument("--" + option, type=Path, required=option == "out")
    args = parser.parse_args()
    (build if args.action == "build" else evaluate)(args)


if __name__ == "__main__":
    main()
