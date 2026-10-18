"""Contract §8: a leaf-changing candidate is judged on live weights AND with both sides refit."""
from __future__ import annotations

import random
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHARED))

from model_evaluation_decision import evaluate_with_refit_arms  # noqa: E402

PROC = "sha256:same-procedure"


def _rows(n_days=60, races=10, seed=1):
    rng = random.Random(seed)
    dates, rows = [], []
    for d in range(n_days):
        day = f"2026-{8 + d // 28:02d}-{1 + d % 28:02d}"
        for _ in range(races):
            dates.append(day)
            rows.append({
                "gold": rng.random() < 0.2,
                "good_positional": rng.random() < 0.25,
                "top3_capture_at5": rng.random(),
                "ndcg_at5": rng.random(),
                "competitive_recall_at5": rng.random(),
                "mean_top3_model_rank": rng.uniform(2, 8),
            })
    return dates, rows


def _improve(rows, rate, seed):
    """Flip a steady fraction of Good misses to hits on every day."""
    rng = random.Random(seed)
    out = [dict(r) for r in rows]
    for row in out:
        if not row["good_positional"] and rng.random() < rate:
            row["good_positional"] = True
    return out


def _worsen(rows, rate, seed):
    rng = random.Random(seed)
    out = [dict(r) for r in rows]
    for row in out:
        if row["good_positional"] and rng.random() < rate:
            row["good_positional"] = False
    return out


def _judge(dates, a0, a1, b0, b1, base_hash=PROC, cand_hash=PROC):
    return evaluate_with_refit_arms(
        domain="au", dates=dates, live_baseline_rows=a0, live_candidate_rows=a1,
        refit_baseline_rows=b0, refit_candidate_rows=b1,
        baseline_refit_procedure_hash=base_hash, candidate_refit_procedure_hash=cand_hash,
        leakage_audit_passed=True, bootstrap=400)


def test_a_a_all_four_arms_identical_rejects():
    dates, rows = _rows()
    verdict = _judge(dates, rows, rows, rows, rows)
    assert verdict["verdict"] == "REJECT"
    assert verdict["reason"] == "both_arms_reject"
    assert verdict["detail"]["baseline_weights_stale"] is False


def test_asymmetric_refit_procedure_is_refused():
    dates, rows = _rows()
    verdict = _judge(dates, rows, rows, rows, rows, cand_hash="sha256:tuned-for-candidate")
    assert verdict["reason"] == "refit_procedure_not_symmetric"


def test_missing_refit_procedure_is_refused():
    dates, rows = _rows()
    verdict = _judge(dates, rows, rows, rows, rows, base_hash="", cand_hash="")
    assert verdict["reason"] == "refit_procedure_not_symmetric"


def test_fixed_arm_win_ships_on_live_weights():
    dates, a0 = _rows()
    a1 = _improve(a0, 0.10, seed=2)
    verdict = _judge(dates, a0, a1, a0, a1)
    assert verdict["reason"] == "fixed_arm_win"
    assert verdict["package"] == "candidate_with_live_weights"


def test_fix_that_only_shows_after_refit_ships_with_refit_weights():
    # The case §8 exists for: on live weights the fixed leaf is unheard (A1 == A0),
    # once each side gets its own weights the candidate is clearly better.
    dates, a0 = _rows()
    b0 = [dict(r) for r in a0]
    b1 = _improve(b0, 0.10, seed=3)
    verdict = _judge(dates, a0, [dict(r) for r in a0], b0, b1)
    assert verdict["reason"] == "refit_arm_win"
    assert verdict["package"] == "candidate_with_refit_weights"


def test_refit_gain_is_not_credited_to_the_candidate():
    # Refit alone helps (B0 > A0) and the candidate adds nothing on top (B1 == B0).
    # B1 beats live, but that gain belongs to the refit — the candidate is rejected
    # and the stale-weights flag is raised instead.
    dates, a0 = _rows()
    b0 = _improve(a0, 0.10, seed=4)
    verdict = _judge(dates, a0, [dict(r) for r in a0], b0, [dict(r) for r in b0])
    assert verdict["verdict"] == "REJECT"
    assert verdict["reason"] == "both_arms_reject"
    assert verdict["detail"]["baseline_weights_stale"] is True


def test_refit_win_that_regresses_live_is_rejected():
    # Refit harms the baseline badly; the candidate claws some back (B1 > B0) but
    # shipping B1 would still be worse than what is live.
    dates, a0 = _rows()
    b0 = _worsen(a0, 0.40, seed=5)
    b1 = _improve(b0, 0.06, seed=6)
    verdict = _judge(dates, a0, [dict(r) for r in a0], b0, b1)
    assert verdict["detail"]["arms"]["refit"]["verdict"] in ("PRIMARY_WIN", "RANKING_WIN")
    assert verdict["reason"] == "refit_package_regresses_live"
    assert verdict["package"] is None


def test_two_arms_are_holm_adjusted():
    dates, rows = _rows()
    verdict = _judge(dates, rows, _improve(rows, 0.10, seed=7), rows, rows)
    raw, adjusted = verdict["detail"]["arm_p_values"], verdict["detail"]["arm_p_holm"]
    assert adjusted["fixed"] >= raw["fixed"]
    assert adjusted["fixed"] == min(1.0, 2 * raw["fixed"])
