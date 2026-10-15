#!/usr/bin/env python3
"""Read-only GPS vs race-header time-origin diagnostic; never a scoring input."""

import argparse
from collections import Counter
from io import BytesIO
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import numpy as np
from au_phase_speed_20261015 import source_events
from au_contextual_gps_speed_20261015 import seconds, norm


def audit(cache):
    events, _ = source_events(cache)
    keys = {e["rows"][0]["source"]: {r["horse"] for r in e["rows"]} for e in events}
    flags, counts = Counter(), Counter()
    offsets = []
    examples = []
    for record in json.loads((cache / "xml_manifest.json").read_text()):
        if record.get("status"):
            continue
        raw = (cache / record["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record["sha256"]
        with ZipFile(BytesIO(raw)) as archive:
            for filename in archive.namelist():
                source = record["url"] + "#" + filename
                if source not in keys:
                    continue
                root = ET.fromstring(archive.read(filename))
                header = seconds(root.find("FinishTime").attrib["Time"])
                horses = []
                for h in root.findall("./Horses/HorseSummary"):
                    if norm(h.attrib["Name"]) not in keys[source]:
                        continue
                    if h.find("FinishTime") is None:
                        continue
                    try:
                        rank = int(h.attrib["FinalRank"])
                        time = seconds(h.find("FinishTime").attrib["Time"])
                    except (KeyError, ValueError):
                        continue
                    if rank <= 0 or time <= 0:
                        continue
                    flags[h.attrib.get("IsFinishTimeOfficial", "missing")] += 1
                    horses.append((rank, time, h.attrib["Name"]))
                winner = [h for h in horses if h[0] == 1]
                if len(winner) != 1:
                    counts["no_unique_winner"] += 1
                    continue
                offset = header - winner[0][1]
                offsets.append(offset)
                counts["races_with_winner_and_header"] += 1
                counts["offset_abs_gt_0p05"] += abs(offset) > 0.05
                counts["offset_abs_gt_0p5"] += abs(offset) > 0.5
                ordered = sorted(horses)
                counts["rank_time_inversion_races"] += any(
                    a[1] > b[1] + 0.05 for a, b in zip(ordered, ordered[1:]) if a[0] < b[0]
                )
                if len(examples) < 5 and abs(offset) > 0.5:
                    examples.append(
                        {
                            "source": source,
                            "header_seconds": header,
                            "winner_gps_seconds": winner[0][1],
                            "difference_seconds": offset,
                            "winner": winner[0][2],
                        }
                    )
    return {
        "status": "DIAGNOSTIC_ONLY_HEADER_SEMANTICS_NOT_CERTIFIED",
        "counts": dict(counts),
        "horse_official_flags": dict(flags),
        "header_minus_winner_gps_seconds_quantiles": dict(
            zip(("min", "p05", "median", "p95", "max"), np.quantile(offsets, [0, 0.05, 0.5, 0.95, 1]).tolist())
        ),
        "examples": examples,
        "interpretation": "A nonzero difference flags noninterchangeable clocks, not proof that either is wrong. No anchoring correction or scoring change.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(audit(args.cache), indent=2))
