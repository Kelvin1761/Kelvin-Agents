"""Keep disputed results out of settlement and decision evidence.

Do not pick a winning provider or rewrite an already recorded ledger. A
dispute stays visible until its source records are explicitly reconciled.
"""
from __future__ import annotations


def conflicting_result_matches(conn) -> set[int]:
    return {int(row[0]) for row in conn.execute(
        """
        SELECT r.match_id FROM match_results r JOIN matches m ON m.id=r.match_id
        GROUP BY r.match_id
        HAVING COUNT(DISTINCT r.winner_player_id)>1
            OR SUM(CASE WHEN r.winner_player_id IS NOT NULL
                         AND r.winner_player_id NOT IN (m.player_a_id,m.player_b_id)
                        THEN 1 ELSE 0 END)>0
        """
    )}


def result_agreement_clause(alias: str = "p", column: str = "match_id") -> str:
    """Internal SQL predicate; no result is allowed for history-settled aces."""
    return (
        f"NOT EXISTS (SELECT 1 FROM match_results rc "
        f"JOIN matches cm ON cm.id=rc.match_id WHERE rc.match_id={alias}.{column} "
        "GROUP BY rc.match_id HAVING COUNT(DISTINCT rc.winner_player_id)>1 "
        "OR SUM(CASE WHEN rc.winner_player_id IS NOT NULL "
        "AND rc.winner_player_id NOT IN (cm.player_a_id,cm.player_b_id) "
        "THEN 1 ELSE 0 END)>0)"
    )
