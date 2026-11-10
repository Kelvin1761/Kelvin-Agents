"""Freeze the day's card as evidence, then publish the dashboard if the run is complete.

The deploy is downstream of the card: a failed deploy never fails the run
(2026-08-13 a Drive error there erased a valid card). The dashboard itself
reads the database (Horse_Racing_Dashboard/backend/services/tennis_tracking.py).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILLS = REPO_ROOT / ".agents" / "skills"
for extra in (SKILLS, SKILLS / "shared_racing" / "post_success_hooks" / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


def record_evidence(match_date: str, report_path: Path) -> dict:
    """Immutable snapshot of the report + the 精選 as the day's recommendations."""
    from shared_wong_choi.contracts import Domain
    from shared_wong_choi.domain_evidence import record_prediction_decision_if_configured
    from shared_wong_choi.evidence import DecisionState
    from shared_wong_choi.immutable_snapshot import create_immutable_snapshot

    from tennis_wc.store.db import get_connection

    with get_connection() as conn:
        picks = [dict(r) for r in conn.execute(
            "SELECT prop_id AS id, market_key, selection, odds, edge FROM featured_picks "
            "WHERE match_date = ? ORDER BY rank", (match_date,))]
    snapshot = create_immutable_snapshot(
        report_path.parent, domain=Domain.TENNIS.value, event_id=match_date,
        patterns=[report_path.name], recommendations=picks, at=datetime.now(timezone.utc))
    return record_prediction_decision_if_configured(
        domain=Domain.TENNIS, event_id=match_date, snapshot=snapshot,
        evidence_root=Path(os.environ.get("WC_EVIDENCE_ROOT", "~/WongChoiData/WongChoiControl/evidence")).expanduser(),
        decision_state=DecisionState.RECOMMEND if picks else DecisionState.NO_BET,
        recommendations=picks)


def deploy(match_date: str, payload: dict) -> dict:
    """Cloudflare deploy, only when readiness says the run is complete."""
    from cloudflare_deploy_hook import run_post_success_cloudflare_deploy

    from tennis_wc.publish.report import drive_dir

    reasons = (payload.get("readiness") or {}).get("reasons") or []
    if reasons:
        return {"attempted": False, "status": "blocked_by_completeness_gate", "reasons": reasons}
    try:
        deployed = run_post_success_cloudflare_deploy(
            source="Tennis Wong Choi", target_dir=drive_dir(match_date), skip=False, allow_failure=True)
    except Exception as exc:  # noqa: BLE001 - deploy is non-fatal
        return {"attempted": True, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    return {"attempted": True, "status": "deployed" if deployed else "failed"}


def deploy_settled(match_date: str) -> dict:
    """Redeploy after the hourly tick settled a 精選: results only, no new card.

    Not gated by analysis readiness, because nothing was analysed; the
    dashboard reads the same database either way.
    """
    from cloudflare_deploy_hook import run_post_success_cloudflare_deploy

    from tennis_wc.publish.report import drive_dir

    try:
        deployed = run_post_success_cloudflare_deploy(
            source="Tennis Wong Choi 精選結算", target_dir=drive_dir(match_date), skip=False, allow_failure=True)
    except Exception as exc:  # noqa: BLE001 - deploy is non-fatal
        return {"attempted": True, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    return {"attempted": True, "status": "deployed" if deployed else "failed"}
