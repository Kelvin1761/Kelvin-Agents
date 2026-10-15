#!/usr/bin/env python3
"""Research-only, frozen-family distance-aware GPS phase diagnostics."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import re
import statistics
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import numpy as np
from au_contextual_gps_speed_20261015 import (
    ContextStandard,
    load_form,
    norm,
    parse_xml,
    seconds,
    zscores,
)

PHASES = ("E800", "E600", "Adaptive", "Fraction", "Cruise")


def phase_geometry(points, splits, phase):
    """Return marked start/end/time, requiring actual boundaries (no interpolation)."""
    distance = points[-1]
    start = 0
    if phase == "Fraction":
        end = min(points[:-1], key=lambda p: (abs(p / distance - 0.4), p))
    else:
        tail = 600 if phase == "E600" or (phase in ("Adaptive", "Cruise") and distance <= 1200) else 800
        end = distance - tail
    if phase == "Cruise":
        start = points[0]
    boundaries = [0] + points
    if end <= start or start not in boundaries or end not in boundaries:
        return None
    time = sum(splits[boundaries.index(start) : boundaries.index(end)])
    return {"start": start, "end": end, "length": end - start, "time": time, "kmh": 3.6 * (end - start) / time}


def source_events(cache):
    events = []
    quality = Counter()
    manifest = json.loads((cache / "xml_manifest.json").read_text())
    for record in manifest:
        if record.get("status"):
            quality["csv_only_meetings_excluded_no_phase_boundaries"] += 1
            continue
        raw = (cache / record["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record["sha256"]
        with ZipFile(BytesIO(raw)) as archive:
            for filename in archive.namelist():
                content = archive.read(filename)
                event = parse_xml(content, record["url"] + "#" + filename)
                if event is None:
                    continue
                horses = {norm(h.attrib["Name"]): h for h in ET.fromstring(content).findall("./Horses/HorseSummary")}
                for row in event["rows"]:
                    sections = horses[row["horse"]].findall("./Sections/SectionSummary")
                    points = [float(s.attrib["CumulatedDistance"]) for s in sections]
                    splits = [seconds(s.find("SectionTime").attrib["Time"]) for s in sections]
                    row["phases"] = {phase: phase_geometry(points, splits, phase) for phase in PHASES}
                    quality["runners"] += 1
                    for phase in PHASES:
                        quality[phase + "_valid"] += row["phases"][phase] is not None
                events.append(event)
    quality["events"] = len(events)
    return events, dict(quality)


class PhaseStandard(ContextStandard):
    def __init__(self, events):
        super().__init__(events, "phase_time")

    def length(self, event):
        return event["length"]


def phase_history(events, target_date, phase):
    output = []
    for event in events:
        if event["date"] >= target_date:
            continue
        rows = [row for row in event["rows"] if row["phases"][phase] is not None]
        if len(rows) < 3:
            continue
        geometry = rows[0]["phases"][phase]
        assert all(
            (r["phases"][phase]["start"], r["phases"][phase]["end"]) == (geometry["start"], geometry["end"])
            for r in rows
        )
        output.append(
            {
                **event,
                "rows": rows,
                "length": geometry["length"],
                "phase_time": statistics.median(r["phases"][phase]["time"] for r in rows),
            }
        )
    return output


def phase_lookup(events, target_date, phase):
    history = phase_history(events, target_date, phase)
    if len(history) < 100:
        return {}, {"events": len(history)}
    model = PhaseStandard(history)
    days = defaultdict(list)
    for event in history:
        residual = math.log(event["phase_time"] / event["length"]) - model.predict(event)
        days[(event["track"], event["date"])].append((event["key"], residual))
    lookup = {}
    for event in history:
        others = [r for key, r in days[(event["track"], event["date"])] if key != event["key"]]
        variant = (
            float(np.clip(statistics.median(others), -0.05, 0.05)) * len(others) / (len(others) + 3)
            if len(others) >= 3
            else 0
        )
        par = model.predict(event, common_class=True) + variant
        for row in event["rows"]:
            geometry = row["phases"][phase]
            # 1000*log(speed/par_speed); positive means faster than contextual par.
            value = -(math.log(geometry["time"] / geometry["length"]) - par) * 1000
            lookup[(event["key"], row["horse"])] = (value, event["going"])
    return lookup, {"events": len(history), "train_through": max(e["date"] for e in history)}


def aggregate(runs, name, target_date, distance, going, lookup):
    usable = []
    for key in runs:
        if key[1] >= target_date or (key, name) not in lookup:
            continue
        value, oldgoing = lookup[(key, name)]
        days = (date.fromisoformat(target_date) - date.fromisoformat(key[1])).days
        w = 2 ** (-days / 90) * math.exp(-abs(math.log(key[3] / distance)) / 0.25)
        if going and oldgoing != going:
            w *= 0.5
        usable.append((w, value))
        if len(usable) == 6:
            break
    weight = sum(w for w, _ in usable)
    return (sum(w * v for w, v in usable) / weight if usable else None, weight / (weight + 3), len(usable))


def build(args):
    blocks, _, hashes = load_form(args.root)
    events, quality = source_events(args.cache)
    obj = json.loads(args.reference.read_text())
    # Retain EXP-04 total time A as a coverage-matched reference, not a new arm.
    races = obj["races"]
    grouped = defaultdict(list)
    for race in races:
        grouped[race["date"]].append(race)
    states = []
    for day, daily in sorted(grouped.items()):
        lookups = {}
        for phase in PHASES:
            lookups[phase], state = phase_lookup(events, day, phase)
            states.append({"date": day, "phase": phase, **state})
        for race in daily:
            for row in race["rows"]:
                distance = int(re.search(r"\d+", str(row["distance"]))[0])
                from au_contextual_gps_speed_20261015 import condition_key

                going = condition_key(row.get("going") or "")
                row["phase_raw"], row["phase_reliability"], row["phase_runs"] = {}, {}, {}
                for phase in PHASES:
                    v, reliability, n = aggregate(
                        blocks.get((race["meeting"], race["race"], norm(row["name"])), []),
                        norm(row["name"]),
                        day,
                        distance,
                        going,
                        lookups[phase],
                    )
                    row["phase_raw"][phase] = v
                    row["phase_reliability"][phase] = reliability
                    row["phase_runs"][phase] = n
                row["phase_raw"]["Total_reference"] = row["context_speed"]["A"]
            for phase in PHASES:
                for row, z in zip(race["rows"], zscores([r["phase_raw"][phase] for r in race["rows"]])):
                    row.setdefault("phase_signal", {})[phase] = z * row["phase_reliability"][phase]
        print("phases", day, flush=True)
    out = {
        "races": races,
        "states": states,
        "quality": quality,
        "reference_sha256": hashlib.sha256(args.reference.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256((args.cache / "xml_manifest.json").read_bytes()).hexdigest(),
        "form_sha256": hashlib.sha256(json.dumps(hashes).encode()).hexdigest(),
    }
    args.out.write_text(json.dumps(out))


def pair_counts(rows, phase):
    positives = [r["phase_raw"][phase] for r in rows if r["pos"] <= 3]
    negatives = [r["phase_raw"][phase] for r in rows if r["pos"] > 3]
    return np.array(
        [sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives), len(positives) * len(negatives)]
    )


def summarize(races, common=False):
    phases = PHASES + ("Total_reference",)
    days = sorted({r["date"] for r in races})
    daily = {p: np.zeros((len(days), 2)) for p in phases}
    dindex = {d: i for i, d in enumerate(days)}
    coverage, compared = Counter(), Counter()
    for race in races:
        for p in phases:
            rows = [
                r
                for r in race["rows"]
                if r["phase_raw"][p] is not None and (not common or all(r["phase_raw"][a] is not None for a in phases))
            ]
            counts = pair_counts(rows, p)
            coverage[p] += len(rows)
            compared[p] += bool(counts[1])
            daily[p][dindex[race["date"]]] += counts
    if not days:
        return {}
    chosen = np.random.default_rng(7).integers(0, len(days), (2000, len(days)))
    bootstrap = {}
    report = {}
    for p in phases:
        c, n = daily[p].sum(axis=0)
        sampled = daily[p][chosen].sum(axis=1)
        bootstrap[p] = np.divide(sampled[:, 0], sampled[:, 1], out=np.full(2000, np.nan), where=sampled[:, 1] > 0)
        report[p] = {
            "covered": coverage[p],
            "comparable_races": compared[p],
            "pairs": int(n),
            "auc": float(c / n) if n else None,
            "ci95": np.nanquantile(bootstrap[p], [0.025, 0.975]).tolist() if n else None,
        }
    if common:
        report["paired_differences_vs_E800"] = {
            p: {
                "delta": report[p]["auc"] - report["E800"]["auc"],
                "ci95": np.nanquantile(bootstrap[p] - bootstrap["E800"], [0.025, 0.975]).tolist(),
            }
            for p in phases
            if report[p]["auc"] is not None
        }
    return report


def evaluate(args):
    obj = json.loads(args.features.read_text())
    races = [r for r in obj["races"] if "2026-09-04" <= r["date"] <= "2026-10-14"]
    buckets = {
        "sprint_le1200": lambda d: d <= 1200,
        "1300_1700": lambda d: 1200 < d <= 1700,
        "staying_gt1700": lambda d: d > 1700,
    }
    report = {
        "status": "DISCOVERY_ONLY_NO_PROMOTION",
        "source_availability": "FLAG",
        "ranking_tested": False,
        "races": len(races),
        "dates": len({r["date"] for r in races}),
        "features_sha256": hashlib.sha256(args.features.read_bytes()).hexdigest(),
        "quality": obj["quality"],
        "natural_coverage": summarize(races),
        "common_coverage": summarize(races, True),
        "distance_buckets_common": {
            name: summarize([r for r in races if pred(int(re.search(r"\d+", str(r["rows"][0]["distance"]))[0]))], True)
            for name, pred in buckets.items()
        },
    }
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "evaluate"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--features", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    (build if args.action == "build" else evaluate)(args)


if __name__ == "__main__":
    main()
