"""Stage 4 v3: full-record paired verdict (fixed rules) / walk-forward OOS (fitted)."""
from __future__ import annotations

import random
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHARED))

from model_evaluation_decision import evaluate_full_record, holm_adjust  # noqa: E402


def _rows(n_days=60, races=10, gold_rate=0.2, good_rate=0.25, seed=1):
    rng = random.Random(seed)
    dates, rows = [], []
    for d in range(n_days):
        day = f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}"
        for _ in range(races):
            dates.append(day)
            rows.append({
                "gold": rng.random() < gold_rate,
                "good_positional": rng.random() < good_rate,
                "top3_capture_at5": rng.random(),
                "ndcg_at5": rng.random(),
                "competitive_recall_at5": rng.random(),
                "mean_top3_model_rank": rng.uniform(2, 8),
            })
    return dates, rows


def _judge(dates, base, cand, mode="fixed_rule"):
    return evaluate_full_record(domain="hkjc", mode=mode, dates=dates, baseline_rows=base,
                                candidate_rows=cand, leakage_audit_passed=True, bootstrap=400)


def test_identical_arms_never_pass():
    dates, rows = _rows()
    verdict = _judge(dates, rows, [dict(r) for r in rows])
    assert verdict["verdict"] == "REJECT"
    assert verdict["reason"] == "ranking_evidence_too_weak"


def test_fitted_candidate_without_walk_forward_is_refused():
    dates, rows = _rows()
    verdict = _judge(dates, rows, rows, mode="in_sample_fit")
    assert verdict["reason"] == "fitted_candidate_needs_walk_forward_predictions"


def test_consistent_primary_gain_wins():
    dates, base = _rows()
    rng = random.Random(2)
    cand = [dict(r) for r in base]
    for row in cand:                      # flip ~8% of misses to hits, everywhere
        if not row["good_positional"] and rng.random() < 0.08:
            row["good_positional"] = True
    verdict = _judge(dates, base, cand)
    assert verdict["verdict"] == "PRIMARY_WIN", verdict["reason"]


def test_gain_carried_by_one_block_with_losses_elsewhere_is_rejected():
    dates, base = _rows()
    cand = [dict(r) for r in base]
    days = sorted(set(dates))
    hot = set(days[:10])                  # first block: big gain
    rng = random.Random(3)
    for row, day in zip(cand, dates):
        if day in hot and not row["gold"]:
            row["gold"] = True
        elif day not in hot and row["gold"] and rng.random() < 0.15:
            row["gold"] = False           # small losses in every other block
    verdict = _judge(dates, base, cand)
    assert verdict["verdict"] == "REJECT"
    assert verdict["reason"] == "primary_regression"


def test_holm_is_monotone_and_bounded():
    adjusted = holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted["a"] == 0.03
    assert adjusted["c"] == 0.06
    assert adjusted["b"] == 0.06
    assert all(0 <= v <= 1 for v in adjusted.values())
