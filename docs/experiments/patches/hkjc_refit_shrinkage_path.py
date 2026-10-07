#!/usr/bin/env python3
"""Conservative shrinkage paths for EXP-20260928-07."""
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


ALPHAS = (0.10, 0.20, 0.30, 0.40, 0.50)
FAMILIES = ("outer", "combined")


def _shrink(fit: dict[str, Any], family: str, alpha: float) -> dict[str, Any]:
    outer = base.CURRENT_OUTER.copy()
    st = base.CURRENT_ST.copy()
    hv = base.CURRENT_HV.copy()
    if family in {"outer", "combined"}:
        outer += alpha * (fit["outer"] - base.CURRENT_OUTER)
        outer = np.clip(outer, 0.0, 0.40)
        outer /= outer.sum()
    if family == "combined":
        st += alpha * (fit["st"] - base.CURRENT_ST)
        st = np.clip(st, 0.0, 1.0)
        st /= st.sum()
        hv += alpha * (fit["hv"] - base.CURRENT_HV)
        hv = np.clip(
            hv,
            np.asarray((0.5, 0.0, 0.0, 0.0)),
            np.asarray((1.25, 1.5, 1.5, 0.75)),
        )
    return {
        "outer": outer,
        "st": st,
        "hv": hv,
        "success": bool(fit["success"]),
        "loss": fit["loss"],
    }


def _dev_paths(df, dev_dates: list[str]) -> dict[str, Any]:
    folds = base._dev_folds(dev_dates)
    accum: dict[str, dict[str, list]] = {}
    for family in FAMILIES:
        variant = "outer_only" if family == "outer" else "combined"
        for alpha in ALPHAS:
            key = f"{family}_{alpha:.2f}"
            accum[key] = {"records": [], "candidate": [], "baseline": [], "folds": []}
        for fold_no, (train_dates, valid_dates) in enumerate(folds, start=1):
            train = df[df["date"].astype(str).isin(train_dates)].reset_index(drop=True)
            valid = df[df["date"].astype(str).isin(valid_dates)].reset_index(drop=True)
            full_fit = base._fit_variant(train, variant)
            for alpha in ALPHAS:
                key = f"{family}_{alpha:.2f}"
                fit = _shrink(full_fit, family, alpha)
                records, candidate, baseline = base._evaluate_block(valid, fit)
                paired = base._paired(candidate, baseline)
                accum[key]["records"].extend(records)
                accum[key]["candidate"].extend(candidate)
                accum[key]["baseline"].extend(baseline)
                accum[key]["folds"].append({
                    "fold": fold_no,
                    "alpha": alpha,
                    "train_dates": [train_dates[0], train_dates[-1]],
                    "valid_dates": [valid_dates[0], valid_dates[-1]],
                    "paired": paired,
                    "primary_nonnegative": bool(
                        paired["gold"]["delta"] >= 0.0 and paired["good"]["delta"] >= 0.0
                    ),
                })

    output = {}
    for key, payload in accum.items():
        paired = base._paired(payload["candidate"], payload["baseline"])
        primary_folds = sum(row["primary_nonnegative"] for row in payload["folds"])
        ranking_positive = sum(
            paired[name]["delta"] > 0.0
            for name in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
        )
        eligible = bool(
            paired["gold"]["delta"] >= 0.0
            and paired["good"]["delta"] >= 0.0
            and primary_folds >= 3
            and ranking_positive >= 2
        )
        output[key] = {
            "records": payload["records"],
            "folds": payload["folds"],
            "baseline": base._summarize(payload["baseline"]),
            "candidate": base._summarize(payload["candidate"]),
            "paired": paired,
            "primary_nonnegative_folds": primary_folds,
            "ranking_positive_metrics": ranking_positive,
            "eligible_for_terminal": eligible,
        }
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = base._prepare_frame(args.dataset)
    dev_dates, terminal_dates = base._date_split(df)
    dev = df[df["date"].astype(str).isin(dev_dates)].reset_index(drop=True)
    terminal = df[df["date"].astype(str).isin(terminal_dates)].reset_index(drop=True)
    paths = _dev_paths(df, dev_dates)

    selection_order = [f"{family}_{alpha:.2f}" for family in FAMILIES for alpha in ALPHAS]
    selected = next((key for key in selection_order if paths[key]["eligible_for_terminal"]), None)
    terminal_report: dict[str, Any] = {"opened": False, "selected": selected}
    stage4 = None
    if selected:
        family, alpha_text = selected.rsplit("_", 1)
        alpha = float(alpha_text)
        variant = "outer_only" if family == "outer" else "combined"
        consensus, bootstrap = base._bootstrap_consensus(dev, variant)
        terminal_report["bootstrap"] = bootstrap
        if consensus is not None:
            locked = _shrink(consensus, family, alpha)
            terminal_records, terminal_candidate, terminal_baseline = base._evaluate_block(terminal, locked)
            terminal_report.update({
                "opened": True,
                "fit": base._params_payload(locked),
                "baseline": base._summarize(terminal_baseline),
                "candidate": base._summarize(terminal_candidate),
                "paired": base._paired(terminal_candidate, terminal_baseline),
                "cohorts": base._cohort_report(terminal_records),
            })
            stage4_records = paths[selected]["records"] + terminal_records
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
            "families": list(FAMILIES),
            "alphas": list(ALPHAS),
            "selection_order": selection_order,
        },
        "development": paths,
        "selection": {"selected": selected, "terminal_opened": terminal_report["opened"]},
        "terminal": terminal_report,
        "stage4": stage4,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    compact = {
        "contract": report["contract"],
        "development": {
            key: {
                "paired": value["paired"],
                "primary_nonnegative_folds": value["primary_nonnegative_folds"],
                "ranking_positive_metrics": value["ranking_positive_metrics"],
                "eligible_for_terminal": value["eligible_for_terminal"],
            }
            for key, value in paths.items()
        },
        "selection": report["selection"],
        "terminal": terminal_report,
        "stage4": stage4,
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
