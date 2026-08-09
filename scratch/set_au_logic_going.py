#!/usr/bin/env python3
"""Set going fields in scratch AU logic files for a counterfactual rerun."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1])
    going = sys.argv[2]
    for path in sorted(root.glob("Race_*_Logic.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        race = data.get("race_analysis", {})
        race["going"] = going
        speed_map = race.get("speed_map")
        if isinstance(speed_map, dict):
            speed_map["going"] = going
        meeting = race.get("meeting_intelligence")
        if isinstance(meeting, dict):
            meeting["going"] = going
            meeting["track_summary"] = going
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{path.name}: going={going}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
