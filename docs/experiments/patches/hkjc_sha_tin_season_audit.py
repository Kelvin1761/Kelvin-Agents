#!/usr/bin/env python3
"""Compare Sha Tin turf signal health across the 2025/26 and 2026/27 seasons."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[3]
PATCHES = Path(__file__).resolve().parent
for path in (PATCHES, REPO):
    sys.path.insert(0, str(path))

import hkjc_surface_shape_ml as shared  # noqa: E402


SIGNALS = (
    "current_live_recomputed_ability",
    "matrix_sectional",
    "matrix_trainer_signal",
    "matrix_stability",
    "matrix_race_shape",
    "matrix_class_advantage",
    "matrix_horse_health",
    "matrix_form_line",
    "shape_draw",
    "shape_fit",
    "shape_trip",
)


def _pairwise_auc(frame: pd.DataFrame, column: str) -> tuple[float, int]:
    wins = 0.0
    pairs = 0
    for (_meeting, _race), race in frame.groupby(["meeting", "race_number"], sort=False):
        positive = race.loc[race["finish_pos"] <= 3, column].dropna().astype(float).to_numpy()
        negative = race.loc[race["finish_pos"] > 3, column].dropna().astype(float).to_numpy()
        for left in positive:
            for right in negative:
                pairs += 1
                wins += 1.0 if left > right else 0.5 if left == right else 0.0
    return (wins / pairs if pairs else 0.5), pairs


def _signal_summary(frame: pd.DataFrame, column: str) -> dict:
    values = pd.to_numeric(frame[column], errors="coerce")
    auc, pairs = _pairwise_auc(frame.assign(**{column: values}), column)
    within_sd = frame.assign(_value=values).groupby(["meeting", "race_number"])["_value"].std(ddof=0)
    winner_edges = []
    for (_meeting, _race), race in frame.assign(_value=values).groupby(["meeting", "race_number"], sort=False):
        winner = race.loc[race["finish_pos"] == 1, "_value"]
        if not winner.empty:
            winner_edges.append(float(winner.iloc[0] - race["_value"].mean()))
    return {
        "auc_top3_vs_rest": round(float(auc), 6),
        "pairs": int(pairs),
        "mean_within_race_sd": round(float(within_sd.mean()), 6),
        "neutral_60_rate": round(float(np.isclose(values, 60.0, atol=0.01).mean()), 6),
        "missing_rate": round(float(values.isna().mean()), 6),
        "mean_winner_edge": round(float(np.mean(winner_edges)), 6) if winner_edges else 0.0,
    }


def _period_summary(frame: pd.DataFrame) -> dict:
    return {
        "races": int(frame.groupby(["meeting", "race_number"]).ngroups),
        "runners": int(len(frame)),
        "date_min": str(frame["date"].min()),
        "date_max": str(frame["date"].max()),
        "signals": {column: _signal_summary(frame, column) for column in SIGNALS},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.dataset)
    df = shared._add_shape_components(df)
    surface = [shared._surface_key(v, t) for v, t in zip(df["venue"], df["track"])]
    st = df[np.asarray(surface) == "ST_TURF"].copy()
    st["date"] = st["date"].astype(str)
    old = st[st["date"] <= "2026-07-12"].copy()
    new = st[st["date"] >= "2026-09-06"].copy()
    old_summary = _period_summary(old)
    new_summary = _period_summary(new)
    delta = {
        signal: {
            key: round(new_summary["signals"][signal][key] - old_summary["signals"][signal][key], 6)
            for key in ("auc_top3_vs_rest", "mean_within_race_sd", "neutral_60_rate", "missing_rate", "mean_winner_edge")
        }
        for signal in SIGNALS
    }
    report = {
        "contract": {
            "old_season": "2026-04-12..2026-07-12",
            "new_season": "2026-09-06..2026-09-27",
            "scope": "ST_TURF only; diagnostic; no odds; no candidate fitting",
        },
        "old_season": old_summary,
        "new_season": new_summary,
        "new_minus_old": delta,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
