"""Check today's priced fixtures without turning old archive errors into outages."""
from __future__ import annotations

from tennis_wc.ingestion.fixture_versions import quarantine_fixture
from tennis_wc.database.market_captures import current_market_clause
from tennis_wc.ingestion.raw_response_store import utc_now


def audit_current_slate(conn, match_date: str, *, apply: bool = False) -> dict:
    candidates = conn.execute(f'''SELECT m.* FROM matches m
        WHERE m.match_date=? AND m.fixture_status IN ('ACTIVE','DISPUTED')
          AND (EXISTS(SELECT 1 FROM odds_snapshots o WHERE o.match_id=m.id
                       AND (m.fixture_status='DISPUTED' OR {current_market_clause(conn,'o','odds_snapshots')}))
               OR EXISTS(SELECT 1 FROM market_odds_snapshots o WHERE o.match_id=m.id
                         AND (m.fixture_status='DISPUTED' OR {current_market_clause(conn,'o')})))
        ORDER BY m.id''', (match_date,)).fetchall()
    from tennis_wc.database.result_consensus import conflicting_result_matches
    conflicts = conflicting_result_matches(conn)
    findings = []
    for match in candidates:
        issues = []
        if match['fixture_status'] == 'DISPUTED':
            issues.append('fixture_already_disputed')
        if match['player_a_id'] == match['player_b_id']:
            issues.append('same_player_on_both_sides')
        if conn.execute('''SELECT 1 FROM match_results WHERE match_id=?
            AND (winner_player_id IS NULL OR winner_player_id NOT IN (?,?)) LIMIT 1''',
            (match['id'], match['player_a_id'], match['player_b_id'])).fetchone():
            issues.append('winner_not_in_fixture')
        if conn.execute('''SELECT 1 FROM prop_tracker WHERE match_id=?
            AND subject_player_id IS NOT NULL AND subject_player_id NOT IN (?,?) LIMIT 1''',
            (match['id'], match['player_a_id'], match['player_b_id'])).fetchone():
            issues.append('prop_subject_not_in_fixture')
        if match['fixture_status'] == 'ACTIVE' and int(match['id']) in conflicts and 'winner_not_in_fixture' not in issues:
            issues.append('result_sources_disagree')
        if issues:
            findings.append({'match_id': int(match['id']), 'issues': issues})
            if apply and match['fixture_status'] != 'DISPUTED':
                quarantine_fixture(conn, int(match['id']), {'integrity_issues': issues},
                                   utc_now(), reason='CURRENT_SLATE_INTEGRITY_HOLD')
    return {'date': match_date, 'checked': len(candidates), 'held': findings}
