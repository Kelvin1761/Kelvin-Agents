"""Bounded review-only combinations. Never feeds the formal BET selectors."""
from copy import deepcopy
from itertools import combinations
import math
from nba_selection_policy import BANKER_FALLBACK, VALUE, HIGH

PROFILES = (("steady", "較低倍率", 1.5, 3.0),
            ("balanced", "中倍率", 3.0, 6.0),
            ("high", "較高倍率", 6.0, 15.0))
VERSION = "review-only-v1"


def build_review_candidates(candidates, odds, *, allowed, evaluate, quote, valid_quote):
    # A fixed 24-leg shortlist and 2/3-leg search keeps price requests bounded.
    # No fitted thresholds, no changes to formal probability or selection.
    pool = [deepcopy(c) for c in candidates if c.get('market_type') == 'PLAYER_MILESTONE'
            and not c.get('bench_minutes_risk') and not c.get('day_to_day')
            and isinstance(c.get('estimated_prob'), (int, float))
            and math.isfinite(c['estimated_prob']) and 0 < c['estimated_prob'] < 100
            and isinstance(c.get('odds'), (int, float)) and math.isfinite(c['odds'])
            and 1.1 <= c['odds'] <= 5.0]
    pool.sort(key=lambda c: (abs(math.log(c['odds']/1.6)), -c['estimated_prob'], c['desc']))
    pool = pool[:24]
    proposals = {}
    for count in (2, 3):
        for legs in combinations(pool, count):
            if not allowed(legs):
                continue
            product = math.prod(c['odds'] for c in legs)
            metrics = evaluate(legs)
            for key, label, low, high in PROFILES:
                if not low <= product <= high:
                    continue
                score = (metrics['adjusted_joint_prob'], metrics['combo_ev_pct'],
                         tuple(sorted(c['desc'] for c in legs)))
                if key not in proposals or score > proposals[key][0]:
                    proposals[key] = (score, label, list(legs))
    output = []
    for key, label, _, _ in PROFILES:
        if key not in proposals:
            continue
        _, label, legs = proposals[key]
        quoted = quote(odds, legs)
        verified = valid_quote(quoted.quote, odds, legs)
        metrics = evaluate(quoted if verified else legs)
        reasons = ['研究候選未經正式選腿規則及策略驗證，唔係正式投注建議。']
        if not verified:
            reasons.append('未取得有效 Sportsbet 組合價，唔顯示估算價為真實報價。')
        elif metrics['combo_ev_pct'] <= 0:
            reasons.append('按真實組合價計算 EV 非正，未通過正式投注閘。')
        policy = {'steady': BANKER_FALLBACK, 'balanced': VALUE, 'high': HIGH}[key]
        if any(c.get('hit_l10', 0) < policy.l10 or c.get('hit_l5', 0) < policy.l5 for c in legs):
            reasons.append(f'包含未達該層最近十場／五場命中率門檻（{policy.l10:g}%／{policy.l5:g}%）嘅選腿。')
        if any(c.get('cov', 0) > policy.max_cov for c in legs):
            reasons.append('包含波幅超出該層正式選腿門檻嘅球員。')
        if verified and quoted.quote['decimal_odds'] < policy.target_min:
            reasons.append(f'Sportsbet 實價低於該層正式組合最低賠率 {policy.target_min:g}。')
        if any(c.get('edge', -1) < 0 for c in legs):
            reasons.append('包含模型估計負 edge 選腿。')
        output.append({'candidate_id': key, 'label': label, 'version': VERSION,
                       'analysis_only': True, 'decision': 'OBSERVE',
                       'odds': quoted.quote.get('decimal_odds') if verified else None,
                       'sgm_quote': quoted.quote, 'quote_verified_at_generation': verified,
                       'model_probability': metrics['adjusted_joint_prob'],
                       'expected_value': metrics['combo_ev_pct']/100 if verified else None,
                       'correlation_penalty': metrics['correlation_penalty'],
                       'reasons': reasons,
                       'legs': [{'player': c['player'], 'team': c['team'], 'category': c['category'],
                                 'line': c['line_val'], 'selection': c['desc'], 'odds': c['odds'],
                                 'model_probability': c['estimated_prob']/100,
                                 'l10_hit_rate': c['hit_l10']/100} for c in legs]})
    return output


BANKER_SHADOW_VERSION = 'banker-ev-shadow-v1'
BANKER_SHADOW_ARMS = (('B0', True, True), ('B1', False, True), ('B2', False, False))


def banker_funnel(candidates, *, playoff, reflector):
    """Descriptive per-gate counts on copies; never changes selector inputs."""
    from nba_selection_policy import BANKER
    tiers = {}
    for name, policy in (('strict', BANKER), ('fallback', BANKER_FALLBACK)):
        pool = [deepcopy(c) for c in candidates if c.get('market_type') == 'PLAYER_MILESTONE']
        counts = {'player_markets': len(pool)}
        def buffer(c):
            line, avg = c.get('line_val', 0), c.get('avg', 0)
            return name == 'fallback' or line <= 0 or avg <= 0 or (avg-line)/line >= .15
        gates = (
            ('recent_hits', lambda c: c.get('hit_l10', 0) >= policy.l10 and c.get('hit_l5', 0) >= policy.l5),
            ('nonnegative_edge', lambda c: c.get('edge', -1) >= 0),
            ('leg_price', lambda c: c.get('odds', 0) >= policy.min_odds),
            ('volatility', lambda c: c.get('cov', 0) <= policy.max_cov),
            ('availability', lambda c: not c.get('bench_minutes_risk') and not c.get('day_to_day')),
            ('early_season_role', lambda c: not c.get('early_season_guard')),
            ('recent_form', lambda c: c.get('l3_avg', c.get('avg', 0)) >= c.get('line_val', 0) * (1 if name == 'strict' else .85)),
            ('buffer', buffer),
            ('playoff', lambda c: playoff(c, 'banker')),
            ('reflector', lambda c: reflector(c, 'banker')),
        )
        # Both a waterfall and independent failures: gate order cannot hide a
        # second bottleneck (e.g. high-hit legs also fail the model edge gate).
        failures = {key: sum(not check(deepcopy(c)) for c in pool) for key, check in gates}
        for key, check in gates:
            pool = [c for c in pool if check(c)]
            counts[key] = len(pool)
        tiers[name] = {'remaining': counts, 'independent_failures': failures,
                       'distinct_players': len({c.get('player') for c in pool})}
    return tiers


def build_banker_shadow(candidates, odds, *, select, quote, valid_quote, evaluate):
    """Frozen EV ablation. Returned rows are OBSERVE, never formal combos."""
    output = []
    markets = {'PTS': 'pts', 'REB': 'reb', 'AST': 'ast', '3PM': 'fg3m'}
    for arm, leg_ev, combo_ev in BANKER_SHADOW_ARMS:
        proposal = select(deepcopy(candidates), require_leg_ev=leg_ev, require_combo_ev=combo_ev)
        row = {'version': BANKER_SHADOW_VERSION, 'arm': arm, 'analysis_only': True,
               'decision': 'OBSERVE', 'eligible': False, 'legs': [], 'reasons': [],
               'selection_rule': getattr(proposal, 'selection_rule', None),
               'require_leg_ev': leg_ev, 'require_combo_ev': combo_ev}
        if not proposal:
            row['reasons'] = ['no_candidate']
            output.append(row)
            continue
        priced = quote(odds, proposal)
        verified = valid_quote(priced.quote, odds, proposal)
        metrics = evaluate(priced if verified else proposal)
        actual = priced.quote.get('decimal_odds') if verified else None
        ev = metrics.get('combo_ev_pct')
        if not verified:
            row['reasons'].append('quote_unverified')
        elif actual < BANKER_FALLBACK.target_min:
            row['reasons'].append('actual_price_below_2')
        if combo_ev and (not isinstance(ev, (int, float)) or not math.isfinite(ev) or ev <= 0):
            row['reasons'].append('nonpositive_combo_ev')
        row.update(eligible=not row['reasons'], sportsbet_sgm_price=actual,
                   sportsbet_sgm_status='ok' if verified else 'unverified',
                   sgm_quote=priced.quote, adjusted_joint_prob=metrics['adjusted_joint_prob'],
                   product_of_leg_prices=metrics['product_of_leg_prices'],
                   expected_value=ev/100 if verified else None,
                   legs=[{'player': c['player'], 'team': c['team'], 'market': markets[c['category']],
                          'line': c['line_val'], 'side': 'over', 'price': c['odds'],
                          'selection': c['desc'], 'category': c['category'],
                          'model_probability': c['estimated_prob']/100, 'l10_hit_rate': c['hit_l10']/100}
                         for c in proposal])
        output.append(row)
    return output


def banker_shadow_review(rows):
    """One public banker research candidate, always OBSERVE, with the real price."""
    proposal = next((r for r in rows if r.get('arm') == 'B2' and r.get('legs')), None)
    if not proposal:
        return []
    translations = {'quote_unverified': '未取得有效 Sportsbet 組合報價。',
                    'actual_price_below_2': '真實組合價低於穩膽最低2.0倍。',
                    'nonpositive_combo_ev': '模型組合 EV 非正。'}
    reasons = ['穩膽研究記錄：同正式組合 1（steady／B2）同一套揀法，用嚟追蹤；停損暫停期間照記錄。正式注以組合 1 為準。']
    reasons += [translations.get(reason, reason) for reason in proposal['reasons']]
    if proposal.get('expected_value') is not None and proposal['expected_value'] <= 0:
        reasons.append('按真實組合價計算模型 EV 非正：命中率產品線，見 EXP-20261027-21。')
    return [{'candidate_id': 'steady', 'label': '穩膽研究記錄', 'version': BANKER_SHADOW_VERSION,
             'analysis_only': True, 'decision': 'OBSERVE', 'odds': proposal.get('sportsbet_sgm_price'),
             'sgm_quote': proposal.get('sgm_quote') or {},
             'quote_verified_at_generation': proposal.get('sportsbet_sgm_status') == 'ok',
             'model_probability': proposal.get('adjusted_joint_prob'),
             'expected_value': proposal.get('expected_value'), 'reasons': reasons,
             'legs': [dict(leg, odds=leg['price']) for leg in proposal['legs']]}]
