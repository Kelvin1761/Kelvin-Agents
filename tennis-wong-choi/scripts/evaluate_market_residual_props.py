#!/usr/bin/env python3
"""Frozen-holdout test of whether each prop model adds signal to the market.

The bookmaker's de-vigged probability is the baseline.  On the training
window only, fit the constrained residual model

    p = market + weight * (raw_model - market),  0 <= weight <= 1

then score that fixed weight on later matches.  A family which receives weight
zero has not shown information beyond the price; it should remain research
only even when a historical ROI slice happens to be positive.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

DEFAULT_EVIDENCE_PRIOR = 100.0


def fit_residual_weight(rows, evidence_prior: float = DEFAULT_EVIDENCE_PRIOR) -> dict:
    usable = [
        row for row in rows
        if row.get("raw") is not None and row.get("market") is not None
    ]
    numerator = denominator = 0.0
    for row in usable:
        raw = float(row["raw"])
        market = float(row["market"])
        actual = float(row["actual"])
        residual = raw - market
        numerator += (actual - market) * residual
        denominator += residual * residual
    raw_weight = max(0.0, min(1.0, numerator / denominator)) if denominator else 0.0
    n = len(usable)
    prior = max(0.0, float(evidence_prior))
    model_weight = raw_weight * n / (n + prior) if n + prior else 0.0
    return {
        "observations": n,
        "raw_weight": round(raw_weight, 6),
        "model_weight": round(model_weight, 6),
        "evidence_prior": prior,
    }


def brier_metrics(rows, model_weight: float) -> dict:
    usable = [
        row for row in rows
        if row.get("raw") is not None and row.get("market") is not None
    ]
    if not usable:
        return {"observations": 0, "raw": None, "market": None, "blended": None}
    raw_error = market_error = blended_error = 0.0
    weight = max(0.0, min(1.0, float(model_weight)))
    for row in usable:
        raw = float(row["raw"])
        market = float(row["market"])
        actual = float(row["actual"])
        blended = market + weight * (raw - market)
        raw_error += (raw - actual) ** 2
        market_error += (market - actual) ** 2
        blended_error += (blended - actual) ** 2
    n = len(usable)
    return {
        "observations": n,
        "raw": round(raw_error / n, 6),
        "market": round(market_error / n, 6),
        "blended": round(blended_error / n, 6),
    }


def fit_group_weights(rows, group_key: str,
                      evidence_prior: float = DEFAULT_EVIDENCE_PRIOR) -> dict:
    groups = sorted({str(row.get(group_key) or "unknown") for row in rows})
    return {
        group: fit_residual_weight(
            [row for row in rows if str(row.get(group_key) or "unknown") == group],
            evidence_prior=evidence_prior,
        )
        for group in groups
    }


def brier_metrics_grouped(rows, group_key: str, group_weights: dict,
                          fallback_weight: float, min_group: int = 50) -> dict:
    weighted_rows = []
    for row in rows:
        group = str(row.get(group_key) or "unknown")
        profile = group_weights.get(group) or {}
        weight = (
            float(profile.get("model_weight") or 0.0)
            if int(profile.get("observations") or 0) >= min_group
            else float(fallback_weight)
        )
        weighted_rows.append((row, weight))
    if not weighted_rows:
        return {"observations": 0, "raw": None, "market": None, "blended": None}
    raw_error = market_error = blended_error = 0.0
    for row, weight in weighted_rows:
        raw = float(row["raw"])
        market = float(row["market"])
        actual = float(row["actual"])
        blended = market + weight * (raw - market)
        raw_error += (raw - actual) ** 2
        market_error += (market - actual) ** 2
        blended_error += (blended - actual) ** 2
    n = len(weighted_rows)
    return {
        "observations": n,
        "raw": round(raw_error / n, 6),
        "market": round(market_error / n, 6),
        "blended": round(blended_error / n, 6),
    }


def _rows(conn) -> list[dict]:
    from tennis_wc.props.registry import family_for_market

    source = conn.execute(
        """
        SELECT p.match_id, p.match_date, p.market_key,
               p.model_prob_raw AS raw, p.market_prob_fair AS market,
               CASE p.result_status WHEN 'WON' THEN 1.0 ELSE 0.0 END AS actual,
               lower(COALESCE(
                   (SELECT tl.surface FROM tournament_levels tl
                    WHERE tl.tournament_id=m.tournament_id
                      AND tl.surface IS NOT NULL
                    ORDER BY tl.id DESC LIMIT 1),
                   'unknown'
               )) AS surface
        FROM prop_tracker p
        JOIN matches m ON m.id = p.match_id
        WHERE p.result_status IN ('WON','LOST')
          AND p.model_prob_raw IS NOT NULL
          AND p.market_prob_fair IS NOT NULL
          AND p.side = 'over'
          AND (p.prop_scope != 'player_first_set'
               OR p.subject_player_id = m.player_a_id)
        ORDER BY p.match_date, p.id
        """
    ).fetchall()
    return [
        {
            "match_id": int(row["match_id"]),
            "match_date": str(row["match_date"]),
            "family": family_for_market(str(row["market_key"])),
            "raw": float(row["raw"]),
            "market": float(row["market"]),
            "actual": float(row["actual"]),
            "surface": str(row["surface"] or "unknown"),
        }
        for row in source
    ]


def evaluate(rows: list[dict], split: str, evidence_prior: float) -> dict:
    families = sorted({row["family"] for row in rows})
    output = {}
    for family in families:
        family_rows = [row for row in rows if row["family"] == family]
        train = [row for row in family_rows if row["match_date"] < split]
        holdout = [row for row in family_rows if row["match_date"] >= split]
        fitted = fit_residual_weight(train, evidence_prior=evidence_prior)
        surface_weights = fit_group_weights(
            train, "surface", evidence_prior=evidence_prior
        )
        train_score = brier_metrics(train, fitted["model_weight"])
        holdout_score = brier_metrics(holdout, fitted["model_weight"])
        surface_holdout_score = brier_metrics_grouped(
            holdout, "surface", surface_weights, fitted["model_weight"]
        )
        if holdout_score["blended"] is None:
            verdict = "NO_HOLDOUT"
            delta = None
        else:
            delta = round(holdout_score["market"] - holdout_score["blended"], 6)
            verdict = "ADDS_SIGNAL" if delta > 0.002 else "MARKET_BASELINE"
        output[family] = {
            "weight_fitted_on_train": fitted,
            "train_brier": train_score,
            "holdout_brier": holdout_score,
            "surface_weights_fitted_on_train": surface_weights,
            "surface_conditioned_holdout_brier": surface_holdout_score,
            "surface_conditioned_gain_vs_market": (
                round(
                    surface_holdout_score["market"]
                    - surface_holdout_score["blended"], 6
                )
                if surface_holdout_score["blended"] is not None else None
            ),
            "holdout_brier_gain_vs_market": delta,
            "verdict": verdict,
        }
    return {
        "split": split,
        "contract": "weight fitted before split; all metrics after split are untouched OOS",
        "families": output,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    parser.add_argument("--split", required=True, help="First holdout date, YYYY-MM-DD")
    parser.add_argument("--evidence-prior", type=float, default=DEFAULT_EVIDENCE_PRIOR)
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        payload = evaluate(_rows(conn), args.split, args.evidence_prior)
    finally:
        conn.close()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
