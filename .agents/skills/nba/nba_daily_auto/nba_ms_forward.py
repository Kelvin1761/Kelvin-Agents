#!/usr/bin/env python3
"""Frozen forward test: market + season-rate S (MS) vs live Layer C. Read-only.

Protocol: docs/experiments/EXP-20261025-12-nba-ms-vs-c-forward-protocol.md. The MS
coefficients, checkpoints, criteria and bootstrap are fixed in that document and in
nba_ms_forward_v1.json; this module only applies them to the market ledger. It never
changes a probability, pick or bet. KEEP is not adoption: switching the live model
still needs model-regression-gate and the user's approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import nba_market_ledger as ledger

CONFIG_PATH = Path(__file__).with_name("nba_ms_forward_v1.json")  # sha256 pinned in the protocol and tests
MARKET_STAT = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M", "3pm": "FG3M"}

# Fixed in the protocol before any forward data existed. Changing any of these
# changes the test; do it only as a new, separately justified protocol.
HARM_CHECK_EVENTS = 150
PRIMARY_EVENTS = 400
FINAL_EVENTS = 800
MIN_DATES = {HARM_CHECK_EVENTS: 15, PRIMARY_EVENTS: 30, FINAL_EVENTS: 60}
SUCCESS_CI = 0.975        # two success looks (400, 800): 97.5% two-sided each
HARM_CI = 0.95
BOOTSTRAP_DRAWS = 4000
BOOTSTRAP_SEED = 20261026
SLOPE_RANGE = (0.85, 1.15)
HIGH_BAND = 0.70
MIN_S_COVERAGE = 0.85


def load_config(path: Path = CONFIG_PATH) -> tuple[dict, str]:
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def ms_prob(config: dict, stat: str, price: float, season_rate: float) -> float | None:
    coef = (config.get("coefficients") or {}).get(stat)
    try:
        price, season_rate = float(price), float(season_rate)
    except (TypeError, ValueError):
        return None
    if coef is None or not (math.isfinite(price) and price > 1.0) or not (0.0 <= season_rate <= 1.0):
        return None
    m_lo, m_hi = config["clip_market"]
    s_lo, s_hi = config["clip_season_rate"]
    z = (coef["intercept"] + coef["beta_market"] * _logit(min(max(1.0 / price, m_lo), m_hi))
         + coef["beta_season_rate"] * _logit(min(max(season_rate, s_lo), s_hi)))
    return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))


def collect(root: Path, since: str, until: str, config: dict) -> tuple[list[dict], dict]:
    """Latest published pre-tip model_obs per leg (ledger rules), settled hit/miss only."""
    rows = [r for day in ledger._iter_dates(since, until, root) for r in ledger.read_rows(root, day)]
    exclusions = ledger.no_prediction_exclusions(rows)
    rows = [r for r in rows if r.get("row_type") != "no_prediction" and not ledger._excluded(r, exclusions)
            and r.get("season_phase") != "PRESEASON"]
    models: dict[tuple, list[dict]] = defaultdict(list)
    settlements: dict[tuple, dict] = {}
    for r in rows:
        if r.get("row_type") == "model_obs":
            models[ledger._leg_key(r)].append(r)
        elif r.get("row_type") == "settlement":
            settlements.setdefault(ledger._leg_key(r), r)
    counts: dict[str, int] = defaultdict(int)
    legs = []
    for key, group in models.items():
        snap = ledger._choose_snapshot(group)
        if snap is None:
            counts["no_pretip_snapshot"] += 1
            continue
        m = next(r for r in group if r.get("snapshot_id") == snap)
        settle = settlements.get(key)
        if settle is None or settle.get("y") not in (0, 1):
            counts["unsettled_or_void"] += 1
            continue
        if (m.get("side") or "over") != "over":
            continue
        counts["settled_legs"] += 1
        if ledger.probability_model_id(m) != config["comparator_probability_model_id"]:
            counts["other_c_model"] += 1
            continue
        stat = MARKET_STAT.get(str(m.get("market")))
        if stat is None:
            counts["stat_unsupported"] += 1
            continue
        if "season_rate_status" not in m:
            # Snapshot written by code older than the S shadow (cf3c2960): outside the
            # test epoch, not an S failure, so it must not dilute the coverage guard.
            counts["pre_shadow_snapshot"] += 1
            continue
        counts["c_legs"] += 1
        if m.get("season_rate_status") != "ok" or m.get("season_rate_version") != config["season_rate_version"]:
            counts[f"s_{m.get('season_rate_status') or 'missing'}"] += 1
            continue
        p_c, p_s = m.get("p_final"), m.get("season_rate_prob_S")
        p_ms = ms_prob(config, stat, m.get("price_at_model"), p_s)
        if p_c is None or p_ms is None:
            counts["invalid_probability"] += 1
            continue
        inputs = m.get("season_rate_inputs") or {}
        legs.append({"date": key[0], "event": f"{key[0]}:{key[1]}", "player": key[2], "stat": stat,
                     "line": key[4], "y": int(settle["y"]), "p_c": float(p_c), "p_ms": p_ms,
                     "p_s": float(p_s), "price": float(m["price_at_model"]),
                     "picked": bool(m.get("picked")),
                     "leak": str(inputs.get("last_game_date") or "") >= str(key[0]),
                     "cross_season": len(inputs.get("seasons") or []) > 1})
    return legs, dict(counts)


def _weights(legs: list[dict]) -> list[float]:
    size = defaultdict(int)
    for leg in legs:
        size[(leg["event"], leg["player"], leg["stat"])] += 1
    return [1.0 / size[(leg["event"], leg["player"], leg["stat"])] for leg in legs]


def _wmean(values, weights):
    total = sum(weights)
    return sum(v * w for v, w in zip(values, weights)) / total if total else float("nan")


def _brier_delta(legs, weights):
    return _wmean([(l["p_ms"] - l["y"]) ** 2 - (l["p_c"] - l["y"]) ** 2 for l in legs], weights)


def _logloss_delta(legs, weights):
    def ll(p, y):
        p = min(max(p, 1e-6), 1 - 1e-6)
        return -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return _wmean([ll(l["p_ms"], l["y"]) - ll(l["p_c"], l["y"]) for l in legs], weights)


def _bootstrap(legs, weights, stat_fn, level):
    by_date = defaultdict(list)
    for i, leg in enumerate(legs):
        by_date[leg["date"]].append(i)
    dates = sorted(by_date)
    rng = random.Random(BOOTSTRAP_SEED)
    draws = []
    for _ in range(BOOTSTRAP_DRAWS):
        idx = [i for d in (rng.choice(dates) for _ in dates) for i in by_date[d]]
        draws.append(stat_fn([legs[i] for i in idx], [weights[i] for i in idx]))
    draws.sort()
    lo = draws[int((1 - level) / 2 * len(draws))]
    hi = draws[min(len(draws) - 1, int((1 + level) / 2 * len(draws)))]
    return [round(lo, 6), round(hi, 6)]


def _slope(legs, weights, key):
    """Weighted logistic recalibration slope of y on logit(p) (Newton, 2 params)."""
    a, b = 0.0, 1.0
    xs = [_logit(min(max(l[key], 1e-4), 1 - 1e-4)) for l in legs]
    for _ in range(50):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, l, w in zip(xs, legs, weights):
            p = 1 / (1 + math.exp(-(a + b * x)))
            r, v = l["y"] - p, p * (1 - p) * w
            g0 += w * r; g1 += w * r * x; h00 += v; h01 += v * x; h11 += v * x * x
        det = h00 * h11 - h01 * h01
        if det <= 0:
            return None
        da, db = (h11 * g0 - h01 * g1) / det, (h00 * g1 - h01 * g0) / det
        a, b = a + da, b + db
        if abs(da) + abs(db) < 1e-9:
            break
    return round(b, 4)


def _high_band_gap(legs, weights):
    sub = [(l, w) for l, w in zip(legs, weights) if l["p_ms"] >= HIGH_BAND]
    if not sub:
        return None
    return _wmean([l["p_ms"] - l["y"] for l, _ in sub], [w for _, w in sub])


def analyse(legs: list[dict], counts: dict, config_sha: str) -> dict:
    events = sorted({l["event"] for l in legs})
    dates = sorted({l["date"] for l in legs})
    n_events = len(events)
    report: dict[str, Any] = {
        "protocol": "EXP-20261025-12", "config_sha256": config_sha, "events": n_events,
        "dates": len(dates), "legs": len(legs), "counts": counts,
        "checkpoints": {"harm": HARM_CHECK_EVENTS, "primary": PRIMARY_EVENTS, "final": FINAL_EVENTS},
        "promotion_allowed": False,
    }
    c_legs = counts.get("c_legs", 0)
    coverage = (len(legs) / c_legs) if c_legs else None
    leaks = sum(l["leak"] for l in legs)
    report["guards"] = {"s_coverage": round(coverage, 4) if coverage is not None else None,
                        "s_coverage_ok": coverage is not None and coverage >= MIN_S_COVERAGE,
                        "leak_rows": leaks, "leak_ok": leaks == 0}
    if not legs:
        report["status"] = "AWAITING_DATA"
        return report
    w = _weights(legs)
    delta = _brier_delta(legs, w)
    report["descriptive"] = {
        "brier_ms_minus_c": round(delta, 6),
        "logloss_ms_minus_c": round(_logloss_delta(legs, w), 6),
        "slope_ms": _slope(legs, w, "p_ms") if len(legs) >= 50 else None,
        "slope_c": _slope(legs, w, "p_c") if len(legs) >= 50 else None,
        "high_band_gap_ms": (round(_high_band_gap(legs, w), 4) if _high_band_gap(legs, w) is not None else None),
        "by_stat": {s: round(_brier_delta([l for l in legs if l["stat"] == s],
                                          _weights([l for l in legs if l["stat"] == s])), 6)
                    for s in sorted({l["stat"] for l in legs})},
        "picked_legs": sum(l["picked"] for l in legs),
        "cross_season_legs": sum(l["cross_season"] for l in legs),
    }
    if not (report["guards"]["s_coverage_ok"] and report["guards"]["leak_ok"]):
        report["status"] = "INVALID_DATA"  # fix the pipeline; never judge on broken inputs
        return report
    if n_events >= FINAL_EVENTS and len(dates) >= MIN_DATES[FINAL_EVENTS]:
        look = "final"
    elif n_events >= PRIMARY_EVENTS and len(dates) >= MIN_DATES[PRIMARY_EVENTS]:
        look = "primary"
    elif n_events >= HARM_CHECK_EVENTS and len(dates) >= MIN_DATES[HARM_CHECK_EVENTS]:
        look = "harm"
    else:
        report["status"] = "ACCUMULATING"
        return report
    report["look"] = look
    if look == "harm":
        ci = _bootstrap(legs, w, _brier_delta, HARM_CI)
        report["brier_ci95"] = ci
        report["status"] = "REJECT_HARM" if ci[0] > 0 else "ACCUMULATING"
        return report
    ci = _bootstrap(legs, w, _brier_delta, SUCCESS_CI)
    report["brier_ci975"] = ci
    band = _bootstrap(legs, w, lambda ls, ws: (_high_band_gap(ls, ws) or 0.0), HARM_CI)
    report["high_band_gap_ci95"] = band
    slope = report["descriptive"]["slope_ms"]
    keep = (ci[1] < 0 and report["descriptive"]["logloss_ms_minus_c"] < 0
            and slope is not None and SLOPE_RANGE[0] <= slope <= SLOPE_RANGE[1]
            and band[0] <= 0 <= band[1])
    if keep:
        report["status"] = "KEEP"
    elif ci[0] > 0 or delta >= 0 or look == "final":
        report["status"] = "REJECT"
    else:
        report["status"] = "NEEDS_MORE_TESTING"  # only possible at the primary look
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--until", required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    config, sha = load_config()
    legs, counts = collect(args.root or ledger.ledger_root(), config["epoch"], args.until, config)
    report = analyse(legs, counts, sha)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
