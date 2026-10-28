"""Counterexamples and isolation of bounded quote-first banker research."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

NBA = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA))
sys.path.insert(0, str(NBA/'nba_wong_choi/scripts'))
import generate_nba_reports as report
import nba_orchestrator as orchestrator
import nba_sgm_quote as q
from nba_banker_search import audit_search, QUOTE_BUDGET

NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def source(n=4, price=1.5, probability=65):
    legs = [dict(market_type=report.PLAYER_MARKET, player=f'Test player {i}', team='BOS' if i%2 else 'LAL',
                 category='REB', line_val=4, avg=8, l3_avg=8, hit_l10=90, hit_l5=90, cov=.2,
                 estimated_prob=probability, edge=probability-100/price, odds=price,
                 season_phase='MID_SEASON', desc=f'Player {i} REB 4+') for i in range(n)]
    odds = {'sportsbet_event_id': 2, 'event_start_time': (NOW+timedelta(hours=8)).isoformat(),
            'sgm_pricing': {'class_external_id':16, 'competition_external_id':1, 'event_external_id':2,
                           'outcomes': {'rebounds': {c['player']:{'4':{'market_external_id':10+i,'outcome_external_id':20+i}}
                                                   for i,c in enumerate(legs)}}}}
    return odds, legs


def run(odds, legs, price=3.0, valid=None, quote=None, select=None):
    def actual_price(source, chosen):
        value = price(chosen) if callable(price) else price
        return q.quote_combo(source, chosen, now=NOW,
                             post=lambda body:(200,{'price':{'numerator':value-1,'denominator':1,'quoteId':'fixture'}}))
    return audit_search(legs, odds, pool=report.banker_pool,
                        select=select or report.select_combo_1, allowed=report._combo_is_allowed,
                        evaluate=report.compute_combo_ev, quote=quote or actual_price,
                        valid_quote=valid or (lambda qt, src, chosen:q.quote_valid(qt,src,chosen,now=NOW)))


def test_quote_first_recovers_product_ev_rejection_without_changing_formal():
    odds, legs = source(2)
    before = deepcopy(legs)
    assert not report.select_combo_1(legs)
    audit = run(odds, legs, price=3.0)
    assert not audit['stages']['Q0']['proposal_found']
    assert audit['stages']['Q1']['positive_ev_candidate']
    assert audit['stages']['Q2']['positive_ev_candidate']
    assert audit['decision']=='OBSERVE' and not audit['promotion_allowed']
    assert legs==before and not report.select_combo_1(legs)


def test_real_price_floor_is_not_replaced_by_product_price_floor():
    odds, legs = source(2, price=1.2, probability=70)
    audit = run(odds, legs, price=2.5)
    assert not audit['stages']['Q1']['proposal_found']  # product 1.44 below builder target
    assert audit['stages']['Q2']['positive_ev_candidate']
    assert audit['stages']['Q2']['candidate']['actual_price']==2.5


def test_broader_search_finds_alternative_when_incumbent_quote_fails():
    odds, legs = source(4)
    incumbent = report.select_combo_1(deepcopy(legs),require_leg_ev=False,require_combo_ev=False)
    key=q.legs_identity(incumbent)
    audit=run(odds, legs, price=lambda c:1.8 if q.legs_identity(c)==key else 3.5)
    assert not audit['stages']['Q1']['positive_ev_candidate']
    assert audit['stages']['Q2']['positive_ev_candidate']
    assert audit['stages']['Q2']['candidate']['legs_sha256']!=key


@pytest.mark.parametrize('price,verified',[(1.99,True),(2,False),(3,False)])
def test_unverified_or_low_quotes_never_create_positive_candidates(price,verified):
    odds, legs = source(3,probability=95)
    audit=run(odds,legs,price=price,valid=lambda *args:verified)
    assert not audit['stages']['Q2']['positive_ev_candidate']
    if not verified:
        assert all(r['actual_price'] is None and r['expected_value'] is None for r in audit['quote_attempts'])


def test_long_round_excludes_expired_winner():
    odds, legs = source(2)
    seen={}
    def valid(quote,src,chosen):
        key=quote['legs_sha256'];seen[key]=seen.get(key,0)+1
        return seen[key]==1 and q.quote_valid(quote,src,chosen,now=NOW)
    audit=run(odds,legs,valid=valid)
    assert audit['stages']['Q2']['positive_candidates_at_capture']>0
    assert audit['stages']['Q2']['positive_candidates_still_current']==0
    assert audit['stages']['Q2']['candidate'] is None


def test_shortlist_budget_dedup_and_order_are_fixed():
    odds,legs=source(22)
    first=run(odds,legs,price=2)
    second=run(odds,deepcopy(legs),price=2)
    assert first['new_search_quotes']==QUOTE_BUDGET and first['unique_quotes']<=QUOTE_BUDGET+2
    assert first['quote_budget_exhausted'] and first['unpriced_combinations']>0
    assert first['search_counts']['banker']['shortlisted_legs']==18
    assert first['search_counts']['banker']['shortlist_truncated']
    assert len({r['legs_sha256'] for r in first['quote_attempts']})==first['unique_quotes']
    assert [r['legs_sha256'] for r in first['quote_attempts']]==[r['legs_sha256'] for r in second['quote_attempts']]
    assert all(len({c['player'] for c in r['legs']})==len(r['legs']) for r in first['quote_attempts'])


def test_invalid_event_identity_cannot_pass():
    odds,legs=source(2)
    def quote(_,chosen):
        wrong=deepcopy(odds);wrong['sgm_pricing']['event_external_id']=999
        return q.quote_combo(wrong,chosen,now=NOW,post=lambda body:(200,{'price':{'numerator':3,'denominator':1,'quoteId':'wrong'}}))
    assert not run(odds,legs,quote=quote)['stages']['Q2']['positive_ev_candidate']


def test_default_report_does_not_run_new_research(monkeypatch):
    import nba_banker_search
    monkeypatch.setattr(nba_banker_search,'audit_search',lambda *a,**kw:pytest.fail('research must be opt-in'))
    capture={}
    report.gen_full_report({'away':{'abbr':'BOS'},'home':{'abbr':'LAL'},'date':'2026-10-25'},
                           {},{},{},{},[],'2026-10-24',capture=capture,sportsbet_odds={})
    assert 'banker_search_audit' not in capture


def test_orchestrator_rejects_research_with_compile_only(monkeypatch):
    monkeypatch.setattr(sys,'argv',['nba_orchestrator','--banker-search-audit','--compile-only'])
    with pytest.raises(SystemExit) as err:orchestrator.main()
    assert err.value.code==2


def test_q2_shortlist_ties_are_stable_without_legacy_incumbents():
    odds,legs=source(10)
    empty=lambda *a,**kw:[]
    first=run(odds,legs,select=empty)
    second=run(odds,list(reversed(legs)),select=empty)
    assert [r['legs_sha256'] for r in first['quote_attempts']]==[r['legs_sha256'] for r in second['quote_attempts']]


def test_future_quote_cannot_pass_as_of_validation():
    odds,legs=source(2)
    def quote(_,chosen):
        return q.quote_combo(odds,chosen,now=NOW+timedelta(seconds=1),
                             post=lambda body:(200,{'price':{'numerator':3,'denominator':1,'quoteId':'future'}}))
    audit=run(odds,legs,quote=quote)
    assert not audit['stages']['Q2']['positive_ev_candidate']
    assert all(not r['quote_verified_at_capture'] for r in audit['quote_attempts'])


def accuracy_row(key, joint=.4, price=2.1, probabilities=(.7, .6)):
    return dict(legs_sha256=key, quote_verified_at_capture=True, actual_price=price,
                adjusted_joint_probability=joint, expected_value=joint*price-1,
                legs=[dict(player=str(i), model_probability=p) for i,p in enumerate(probabilities)])


def test_accuracy_ranking_keeps_negative_ev_visible_without_promoting():
    from nba_banker_search import accuracy_review
    baseline=accuracy_row('old',joint=.3,price=4)
    candidate=accuracy_row('new')
    inputs=[baseline,candidate];before=deepcopy(inputs)
    out=accuracy_review(inputs,'old',is_current=lambda r:True)
    assert out['candidate_at_capture']['legs_sha256']=='new'
    assert out['baseline_at_capture']['expected_value']>0
    assert out['candidate_at_capture']['expected_value']<0
    assert out['candidate_at_capture']['weakest_leg_probability']==.6
    assert not out['candidate_at_capture']['formal_eligible'] and not out['promotion_allowed']
    assert not out['role_filter_applied'] and inputs==before


@pytest.mark.parametrize('change',[
    {'quote_verified_at_capture':False}, {'actual_price':1.99}, {'actual_price':float('inf')},
    {'adjusted_joint_probability':float('nan')}, {'adjusted_joint_probability':1},
    {'legs':[]}, {'legs':[{'model_probability':None}]}, {'legs':[{'model_probability':1}]},
    {'legs':[{'model_probability':.8}]}, {'legs':[{'model_probability':.8}]*5},
])
def test_accuracy_review_rejects_unverified_prices_or_probabilities(change):
    from nba_banker_search import accuracy_review
    row=accuracy_row('bad');row.update(change)
    out=accuracy_review([row],None,is_current=lambda r:True)
    assert out['eligible_quoted_combinations']==0
    assert out['candidate_at_capture'] is None and out['current_candidate'] is None


def test_accuracy_review_retains_capture_but_never_current_expired_quotes():
    from nba_banker_search import accuracy_review
    out=accuracy_review([accuracy_row('expired')],'expired',is_current=lambda r:False)
    assert out['candidate_at_capture'] and out['current_candidate'] is None


def test_accuracy_ties_use_weakest_leg_then_stable_identity_not_outcomes():
    from nba_banker_search import accuracy_review
    rows=[accuracy_row('z',probabilities=(.8,.5)),accuracy_row('b'),accuracy_row('a')]
    rows[0]['outcome']='hit';rows[2]['outcome']='miss'
    for items in (rows,list(reversed(rows))):
        out=accuracy_review(items,None,is_current=lambda r:True)
        assert out['candidate_at_capture']['legs_sha256']=='a'


def test_integrated_accuracy_review_reuses_quotes_and_exposes_leg_evidence():
    odds,legs=source(4)
    out=run(odds,legs,price=2.1)
    review=out['accuracy_review']
    assert review['current_candidate']
    assert review['candidate_at_capture']['adjusted_joint_probability']==max(
        r['adjusted_joint_probability'] for r in out['quote_attempts'] if r['actual_price']>=2)
    assert all('l10_hit_rate' in c and 'probability_model_id' in c
               for c in review['candidate_at_capture']['legs'])
    assert out['unique_quotes']<=QUOTE_BUDGET+2
    assert not report.select_combo_1(legs)
