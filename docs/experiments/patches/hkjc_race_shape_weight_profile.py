#!/usr/bin/env python3
"""Single-axis production race-shape weight profile for EXP-20260928-08."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


PATCHES = Path(__file__).resolve().parent
if str(PATCHES) not in sys.path:
    sys.path.insert(0, str(PATCHES))

import hkjc_hierarchical_refit as base  # noqa: E402
from hkjc_no_regression_gate import evaluate_stage4_candidate  # noqa: E402


SHAPE_GRID = (0.10, 0.14, 0.18, 0.20, 0.22, 0.24, 0.26)


def _outer_for_shape(shape_weight: float) -> np.ndarray:
    result = base.CURRENT_OUTER.copy()
    index = base.DIMS.index("race_shape")
    other_total = float(result.sum() - result[index])
    scale = (1.0 - shape_weight) / other_total
    result *= scale
    result[index] = shape_weight
    return result


def _fit_payload(shape_weight: float) -> dict[str, Any]:
    return {
        "outer": _outer_for_shape(shape_weight),
        "st": base.CURRENT_ST.copy(),
        "hv": base.CURRENT_HV.copy(),
        "success": True,
        "loss": 0.0,
    }


def _date_blocks(dev_dates: list[str]) -> list[list[str]]:
    return [list(block) for block in np.array_split(np.asarray(dev_dates, dtype=object), 5) if len(block)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = base._prepare_frame(args.dataset)
    dev_dates, terminal_dates = base._date_split(df)
    dev = df[df["date"].astype(str).isin(dev_dates)].reset_index(drop=True)
    terminal = df[df["date"].astype(str).isin(terminal_dates)].reset_index(drop=True)
    blocks = _date_blocks(dev_dates)

    profiles: dict[str, Any] = {}
    for shape_weight in SHAPE_GRID:
        fit = _fit_payload(shape_weight)
        all_records = []
        all_candidate = []
        all_baseline = []
        block_rows = []
        for block_no, dates in enumerate(blocks, start=1):
            subset = dev[dev["date"].astype(str).isin(dates)].reset_index(drop=True)
            records, candidate, baseline = base._evaluate_block(subset, fit)
            paired = base._paired(candidate, baseline)
            all_records.extend(records)
            all_candidate.extend(candidate)
            all_baseline.extend(baseline)
            block_rows.append({
                "block": block_no,
                "dates": [dates[0], dates[-1]],
                "races": int(subset["race_key"].nunique()),
                "paired": paired,
                "primary_nonnegative": bool(
                    paired["gold"]["delta"] >= 0.0 and paired["good"]["delta"] >= 0.0
                ),
            })
        paired = base._paired(all_candidate, all_baseline)
        primary_blocks = sum(row["primary_nonnegative"] for row in block_rows)
        ranking_positive = sum(
            paired[name]["delta"] > 0.0
            for name in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
        )
        eligible = bool(
            paired["gold"]["delta"] >= 0.0
            and paired["good"]["delta"] >= 0.0
            and primary_blocks >= 3
            and ranking_positive >= 2
        )
        key = f"shape_{shape_weight:.2f}"
        profiles[key] = {
            "weight": shape_weight,
            "outer": base._params_payload(fit)["outer"],
            "records": all_records,
            "blocks": block_rows,
            "baseline": base._summarize(all_baseline),
            "candidate": base._summarize(all_candidate),
            "paired": paired,
            "primary_nonnegative_blocks": primary_blocks,
            "ranking_positive_metrics": ranking_positive,
            "eligible_for_terminal": eligible,
        }

    selection_order = [f"shape_{weight:.2f}" for weight in reversed(SHAPE_GRID)]
    selected = next((key for key in selection_order if profiles[key]["eligible_for_terminal"]), None)
    terminal_report: dict[str, Any] = {"opened": False, "selected": selected}
    stage4 = None
    if selected:
        fit = _fit_payload(float(profiles[selected]["weight"]))
        records, candidate, baseline = base._evaluate_block(terminal, fit)
        terminal_report.update({
            "opened": True,
            "fit": base._params_payload(fit),
            "baseline": base._summarize(baseline),
            "candidate": base._summarize(candidate),
            "paired": base._paired(candidate, baseline),
            "cohorts": base._cohort_report(records),
        })
        stage4_records = profiles[selected]["records"] + records
        stage4 = evaluate_stage4_candidate(
            stage4_records,
            "candidate",
            leakage_audit_passed=True,
            holdout_fraction=len(terminal_dates) / len({row["date"] for row in stage4_records}),
        )
        terminal_report["stage4"] = stage4

    report = {
        "contract": {
            "rows": int(len(df)),
            "races": int(df["race_key"].nunique()),
            "meetings": int(df["meeting"].nunique()),
            "dev_dates": [dev_dates[0], dev_dates[-1]],
            "terminal_dates": [terminal_dates[0], terminal_dates[-1]],
            "dev_races": int(dev["race_key"].nunique()),
            "terminal_races": int(terminal["race_key"].nunique()),
            "grid": list(SHAPE_GRID),
            "selection_order": selection_order,
        },
        "profiles": profiles,
        "selection": {"selected": selected, "terminal_opened": terminal_report["opened"]},
        "terminal": terminal_report,
        "stage4": stage4,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    compact = {
        "contract": report["contract"],
        "profiles": {
            key: {
                "outer": value["outer"],
                "paired": value["paired"],
                "primary_nonnegative_blocks": value["primary_nonnegative_blocks"],
                "ranking_positive_metrics": value["ranking_positive_metrics"],
                "eligible_for_terminal": value["eligible_for_terminal"],
            }
            for key, value in profiles.items()
        },
        "selection": report["selection"],
        "terminal": terminal_report,
        "stage4": stage4,
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
