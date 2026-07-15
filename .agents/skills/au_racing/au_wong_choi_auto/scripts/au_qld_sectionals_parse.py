#!/usr/bin/env python3
"""Normalise downloaded Racing Queensland sectional CSVs into runner rows.

It keeps the authority's original per-200m triplets and records only the
unambiguous time value as ``segment_time_seconds``.  The companion numeric
column is preserved as ``official_metric`` because its label is not carried in
the CSV itself; a research job must identify and document its semantics before
using it as a feature.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from au_official_free_data import OUT_DIR


RAW_DIR = OUT_DIR / "qld_sectionals"
OUTPUT = OUT_DIR / "qld_race_sectional_runners.jsonl"


def _seconds(value: str) -> float | None:
    try:
        hours, minutes, seconds = value.strip().split(":")
        parsed = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        return parsed if parsed > 0 else None
    except (ValueError, AttributeError):
        return None


def _parse_payload(payload: str) -> dict[str, Any] | None:
    values = [item.strip() for item in payload.split(";")]
    if len(values) < 5 or not values[1].isdigit():
        return None
    segments = []
    for offset in range(2, len(values) - 2, 3):
        try:
            marker = int(values[offset])
            metric = float(values[offset + 1])
        except ValueError:
            continue
        time_value = values[offset + 2]
        segments.append({
            "marker_m": marker,
            "official_metric": metric,
            "segment_time": time_value,
            "segment_time_seconds": _seconds(time_value),
        })
    if not segments:
        return None
    return {"horse_name": values[0], "finish_position": int(values[1]), "segments_200m": segments}


def _records_for_file(path: Path) -> list[dict[str, Any]]:
    match = re.match(r"(\d{8})_(.+?)_T\.csv$", path.name)
    if not match:
        return []
    day, track_token = match.groups()
    output = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 3 or row[0] == "Date":
                continue
            parsed = _parse_payload(row[2])
            if not parsed:
                continue
            output.append({
                "record_type": "official_qld_race_sectional_runner_shadow",
                "authority": "racing_queensland",
                "date": f"{day[:4]}-{day[4:6]}-{day[6:]}",
                "track_token": track_token,
                "race_number": int(row[1]) if row[1].isdigit() else None,
                "source_file": str(path.relative_to(OUT_DIR)),
                **parsed,
                "model_rule": "Use only pre-race history in walk-forward joins; the raw metric is unlabelled in the source CSV and must not be assumed to be speed.",
            })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalise downloaded QLD sectional CSVs into runner-level shadow records.")
    parser.add_argument("--raw-file", type=Path, help="Optional one CSV; otherwise parse all downloaded QLD CSVs")
    args = parser.parse_args()
    files = [args.raw_file] if args.raw_file else sorted(RAW_DIR.glob("*_T.csv"))
    records = [record for path in files if path.exists() for record in _records_for_file(path)]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"parsed {len(files)} CSV files into {len(records)} runner sectional records | {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
