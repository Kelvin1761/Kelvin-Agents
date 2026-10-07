#!/usr/bin/env python3
"""Diagnostic replay for the three frozen EXP-20260928-10 shadow arms.

The corpus has already informed the arm definitions.  This harness therefore
verifies wiring and interaction only; it cannot promote a candidate.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


PATCHES = Path(__file__).resolve().parent
if str(PATCHES) not in sys.path:
    sys.path.insert(0, str(PATCHES))

import hkjc_race_shape_v2_ab as v2  # noqa: E402
import hkjc_surface_shape_ml as shared  # noqa: E402


PROFILES = ("current_live", "weight_refit_t02", "race_shape_v3_hv", "race_shape_v3_hv_t02")


def _candidate_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["surface_score"] = (60.0 + 40.0 * out["surface_quality"]).clip(40.0, 80.0)
    is_hv = out["surface_key"].eq("HV_TURF")
    is_standard = ~out["is_debut"].astype(bool)
    current_shape = pd.to_numeric(out["matrix_race_shape"], errors="coerce").fillna(60.0)
    stability = pd.to_numeric(out["matrix_stability"], errors="coerce").fillna(60.0)
    v3_shape = np.where(
        is_hv,
        (out["shape_draw"] + 0.45 * (out["surface_score"] - 60.0)).clip(0.0, 100.0),
        current_shape,
    )
    shape_delta = np.where(is_standard, np.asarray(v3_shape) - current_shape, 0.0)
    transfer_delta = np.where(is_standard, 0.02 * (stability - current_shape), 0.0)
    live = pd.to_numeric(out["current_live_recomputed_ability"], errors="coerce").fillna(60.0)
    out["score_current_live"] = live
    out["score_weight_refit_t02"] = live + transfer_delta
    out["score_race_shape_v3_hv"] = live + 0.2737 * shape_delta
    out["score_race_shape_v3_hv_t02"] = live + transfer_delta + 0.2537 * shape_delta
    return out


def _evaluate(df: pd.DataFrame) -> dict:
    flags = defaultdict(list)
    by_surface = defaultdict(lambda: defaultdict(list))
    for _key, race in df.groupby("race_key", sort=False):
        actual_pos = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
        surface = str(race.iloc[0]["surface_key"])
        for profile in PROFILES:
            record = v2._model_record(race, f"score_{profile}")
            row = v2._ranking_flags(record, actual_pos)
            flags[profile].append(row)
            by_surface[profile][surface].append(row)
    summaries = {profile: v2._summary(rows) for profile, rows in flags.items()}
    paired = {
        profile: v2._paired(flags[profile], flags["current_live"])
        for profile in PROFILES
        if profile != "current_live"
    }
    surface = {
        profile: {
            name: {
                "summary": v2._summary(rows),
                "paired": v2._paired(rows, by_surface["current_live"][name]),
            }
            for name, rows in cohorts.items()
            if rows
        }
        for profile, cohorts in by_surface.items()
        if profile != "current_live"
    }
    return {"summaries": summaries, "paired_vs_current_live": paired, "surface": surface}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    df = pd.read_csv(args.dataset)
    df["race_key"] = df["meeting"].astype(str) + "::" + df["race_number"].astype(str)
    df = shared._add_shape_components(df)
    df = shared._add_surface_features(df, shared._load_prior_runs())
    df = _candidate_scores(df)
    report = {
        "contract": {
            "purpose": "diagnostic_replay_only",
            "promotion_eligible": False,
            "rows": int(len(df)),
            "races": int(df["race_key"].nunique()),
            "meetings": int(df["meeting"].nunique()),
            "debut_formula_locked": True,
            "sha_tin_v3": "production_noop",
            "happy_valley_v3": "draw+0.45*(pit_surface-60)",
        },
        **_evaluate(df),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
