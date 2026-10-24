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
