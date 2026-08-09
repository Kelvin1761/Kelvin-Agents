#!/usr/bin/env python3
"""Small adapter from ranked AU rows to the shared Gold/Good/Pass ruler.

Research scripts used to reimplement these metrics independently and several
quietly kept the retired Good-any-2 / Pass-any-1 meanings.  Keep row-shape
handling here, while leaving the metric definitions in shared_racing.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_RACING = SCRIPT_DIR.parents[2] / "shared_racing"
sys.path.insert(0, str(SHARED_RACING))

from eval_metrics import race_metrics  # noqa: E402


def ranked_performance(
    ranked: Sequence[Mapping[str, Any]],
    *,
    horse_key: str = "horse_number",
    position_key: str = "actual_pos",
) -> dict[str, Any]:
    """Return canonical metrics for rows already ordered best-to-worst."""
    picks = [int(row[horse_key]) for row in ranked]
    actual_pos = {int(row[horse_key]): int(row[position_key]) for row in ranked}
    actual_top3 = [horse for horse, position in actual_pos.items() if position <= 3]
    winner = next((horse for horse, position in actual_pos.items() if position == 1), None)
    return race_metrics(
        picks,
        actual_top3,
        winner=winner,
        actual_pos=actual_pos,
        field_size=len(ranked),
    )
