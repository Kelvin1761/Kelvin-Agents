#!/usr/bin/env python3
"""Read-only Tennis warehouse/model audit; never ingest, reprice or settle.

Usage: PYTHONPATH=src python scripts/audit_model_data.py --db PATH [--with-roi]
ROI reuses the existing paper-book evaluator, including its bootstrap; it can
take longer than the coverage scan. A failed integrity check returns exit 1.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))


QUERIES = {
    "history_sources": """
        SELECT source_provider,tour,COUNT(*) n,MAX(match_date) latest,
               SUM(hold_rate IS NOT NULL) hold_n,SUM(ace_count IS NOT NULL) ace_n
        FROM player_match_history GROUP BY source_provider,tour
    """,
    "possible_history_duplicates": """
        SELECT COUNT(*) groups_with_copies,COALESCE(SUM(n-1),0) extra_rows
        FROM (SELECT player_id,opponent_id,match_date,COUNT(*) n
              FROM player_match_history WHERE opponent_id IS NOT NULL
              GROUP BY player_id,opponent_id,match_date HAVING COUNT(*)>1)
    """,
    "history_input_defects": """
        SELECT source_provider,COUNT(*) n,SUM(player_id=opponent_id) self_rows,
               SUM(hold_rate<0 OR hold_rate>1) invalid_hold,
               SUM(first_serve_points_won_pct<0 OR first_serve_points_won_pct>1) invalid_first_serve,
               SUM(return_points_won_pct<0 OR return_points_won_pct>1) invalid_return
        FROM player_match_history GROUP BY source_provider
    """,
    "result_sources": """
        SELECT COUNT(*) matches,SUM(n-1) extra_source_rows,SUM(w>1) conflicting_winners
        FROM (SELECT match_id,COUNT(*) n,COUNT(DISTINCT winner_player_id) w
              FROM match_results GROUP BY match_id)
    """,
    "latest_prediction_timing": """
        SELECT COUNT(*) n,
               SUM(julianday(m.start_time_utc) IS NULL) unknown_start,
               SUM(julianday(p.created_at)<julianday(m.start_time_utc)) pre_start,
               SUM(julianday(p.created_at)>=julianday(m.start_time_utc)) post_start
        FROM predictions p JOIN matches m ON m.id=p.match_id
        WHERE p.id IN (SELECT MAX(id) FROM predictions GROUP BY match_id)
    """,
    "live_prop_bets": "SELECT COUNT(*) n FROM prop_live_bets",
    "prediction_query_indexes": "PRAGMA index_list(predictions)",
    "odds_query_indexes": "PRAGMA index_list(odds_snapshots)",
}


def audit(conn, *, with_roi: bool = False) -> dict:
    from tennis_wc.evaluation.corpus import corpus_summary
    from tennis_wc.props.settlement import model_vs_market_scorecard, prop_roi_report
    from tennis_wc.props.strategy import recommendation_gate
    from tennis_wc.validation.checks import critical_failures, run_checks

    version_before = conn.execute("PRAGMA data_version").fetchone()[0]
    out = {"captured_at": datetime.now(timezone.utc).isoformat()}
    for name, query in QUERIES.items():
        out[name] = [dict(row) for row in conn.execute(query)]
    wta_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wta_match_stats'"
    ).fetchone()
    out["wta_official_feed"] = [dict(row) for row in conn.execute(
        "SELECT stats_status,COUNT(*) n,MIN(match_date) earliest,MAX(match_date) latest,"
        "SUM(hold_rate IS NOT NULL) hold_n FROM wta_match_stats GROUP BY stats_status"
    )] if wta_exists else None
    out["corpus"] = corpus_summary(conn)
    out["scorecard"] = model_vs_market_scorecard(conn)
    checks = run_checks(conn)
    out["checks"] = [asdict(result) for result in checks]
    out["critical_failures"] = [result.name for result in critical_failures(checks)]
    if with_roi:
        out["roi"] = prop_roi_report(conn)
        out["strategy"] = recommendation_gate(out["scorecard"], out["roi"])
    out["warehouse_changed_during_audit"] = (
        conn.execute("PRAGMA data_version").fetchone()[0] != version_before
    )
    out["status"] = (
        "attention" if out["critical_failures"] or out["warehouse_changed_during_audit"]
        else "checks_passed"
    )
    out["note"] = (
        "Stored pre-match forecasts are a paper record, not live-bet profit. "
        "A checks_passed status is not model validation or promotion evidence. "
        "Possible duplicate history requires event/source reconciliation before removal."
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--with-roi", action="store_true")
    args = parser.parse_args()
    with sqlite3.connect(args.db.expanduser().resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        payload = audit(conn, with_roi=args.with_roi)
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if payload["status"] == "checks_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
