"""Versioned evidence exclusions; recorded forecasts are never rewritten."""
from __future__ import annotations

from tennis_wc.props.registry import family_for_market

CONTRACT_POLICY = 'prop-contract-v1'


def exclusion_reason(row) -> str | None:
    values = dict(row)
    if str(values.get('market_key') or '').lower() == 'total_games' and not values.get('feed_market_name'):
        return 'legacy_match_total_contract_unverified'
    if (family_for_market(values.get('market_key', '')) == 'match_total_games'
            and values.get('feed_market_name')
            and family_for_market('', values['feed_market_name']) == 'player_total_games'):
        return 'named_player_total_priced_as_match_total'
    return None


def verified_contract_rows(rows):
    eligible, excluded = [], []
    for row in rows:
        reason = exclusion_reason(row)
        if reason:
            excluded.append({'prop_id': row['id'], 'reason': reason,
                             'feed_market_name': row['feed_market_name']})
        else:
            eligible.append(row)
    return eligible, {'policy': CONTRACT_POLICY, 'excluded': excluded}
