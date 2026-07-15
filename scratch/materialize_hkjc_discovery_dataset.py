#!/usr/bin/env python3
"""Re-materialize the April-May discovery set with the fixed research schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
sys.path.insert(0, str(SCRIPTS))

from build_hkjc_ranking_dataset import build_rows, build_summary  # noqa: E402


MEETING_NAMES = [
    "2026-04-12_ShaTin",
    "2026-04-15_HappyValley",
    "2026-04-19_ShaTin",
    "2026-04-22_HappyValley",
    "2026-04-26_ShaTin",
    "2026-04-29_HappyValley",
    "2026-05-03_ShaTin",
    "2026-05-06_ShaTin",
    "2026-05-09_ShaTin",
    "2026-05-13_HappyValley",
    "2026-05-17_ShaTin",
    "2026-05-20_HappyValley",
    "2026-05-24_ShaTin",
]

MEETING_ROOT = ROOT / "Wong Choi Horse Race Analysis/HK_Racing"
OUTPUT = ROOT / "scratch/hkjc_discovery_20260412_20260524_dataset.csv"
SUMMARY = ROOT / "scratch/hkjc_discovery_20260412_20260524_dataset_summary.json"


def main() -> int:
    frames: list[pd.DataFrame] = []
    meeting_reports = []
    for index, name in enumerate(MEETING_NAMES, start=1):
        meeting = MEETING_ROOT / name
        print(f"[{index}/{len(MEETING_NAMES)}] materializing {name}", flush=True)
        frame, coverage = build_rows([meeting], [meeting])
        if frame.empty:
            raise RuntimeError(f"No rows materialized for {meeting}")
        frames.append(frame)
        combined = pd.concat(frames, ignore_index=True)
        combined.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
        meeting_reports.append({"meeting": name, **coverage, "rows": int(len(frame))})
        print(
            f"[{index}/{len(MEETING_NAMES)}] done races={coverage['races']} "
            f"rows={len(frame)} cumulative_rows={len(combined)}",
            flush=True,
        )

    combined = pd.concat(frames, ignore_index=True)
    total_coverage = {
        "meetings": len(frames),
        "races": int(combined[["meeting", "race_number"]].drop_duplicates().shape[0]),
        "horses": int(len(combined)),
        "meeting_reports": meeting_reports,
    }
    SUMMARY.write_text(
        json.dumps(build_summary(combined, total_coverage), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"dataset={OUTPUT}", flush=True)
    print(f"summary={SUMMARY}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
