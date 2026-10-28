"""Review candidates cannot change formal recommendations or fake a price."""
from pathlib import Path
import sys
from copy import deepcopy
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from nba_review_candidates import build_review_candidates
from nba_sgm_quote import QuotedCombo


def leg(name,price=1.5,**kwargs):
    return dict(market_type='PLAYER_MILESTONE',player=name,team='BOS',category='PTS',
                line_val=10,desc=name+' PTS 10+',odds=price,estimated_prob=60,hit_l10=40,edge=-6,**kwargs)


def evaluate(legs):
    import math
    probability=math.prod(c['estimated_prob']/100 for c in legs)*.9
    price=getattr(legs,'quote',{}).get('decimal_odds') or math.prod(c['odds'] for c in legs)
    return dict(adjusted_joint_prob=probability,combo_ev_pct=(probability*price-1)*100,correlation_penalty=.1)


def build(pool,valid=True):
    calls=[]
    def quote(odds,legs):
        calls.append(legs)
        return QuotedCombo(legs,{'status':'ok','decimal_odds':2.1})
    result=build_review_candidates(pool,{},allowed=lambda legs:len({c['player'] for c in legs})==len(legs),
        evaluate=evaluate,quote=quote,valid_quote=lambda *a:valid)
    return result,calls


def test_negative_ev_and_low_hit_candidates_are_visible_but_never_bets():
    pool=[leg('A'),leg('B'),leg('C',2.5),leg('D',3)]
    before=deepcopy(pool);result,calls=build(pool)
    assert result and len(calls)<=3 and pool==before
    assert all(c['decision']=='OBSERVE' and c['analysis_only'] for c in result)
    assert all(c['expected_value']<0 for c in result)
    assert all(any('EV 非正' in reason for reason in c['reasons']) for c in result)
    assert len(result)==len({c['candidate_id'] for c in result})


def test_no_verified_quote_never_uses_leg_price_product_as_sgm_price():
    result,_=build([leg('A'),leg('B')],False)
    assert result and all(c['odds'] is None and c['expected_value'] is None for c in result)


@pytest.mark.parametrize('flag',['bench_minutes_risk','day_to_day'])
def test_risky_minutes_and_uncertain_availability_do_not_seed_candidates(flag):
    result,_=build([leg('A',**{flag:True}),leg('B')])
    assert result==[]


def test_same_player_cannot_supply_both_legs():
    assert build([leg('A'),leg('A',2)])[0]==[]


def test_search_is_deterministic_and_never_requests_more_than_three_quotes():
    pool=[leg(str(i),1.2+i*.1) for i in range(40)]
    a,calls=build(pool);b,_=build(list(reversed(pool)))
    assert a==b and len(calls)<=3


def test_even_positive_review_ev_does_not_become_formal_bet():
    pool=[leg('A'),leg('B')]
    result=build_review_candidates(pool,{},allowed=lambda legs:True,evaluate=evaluate,
        quote=lambda odds,legs:QuotedCombo(legs,{'status':'ok','decimal_odds':4}),valid_quote=lambda *a:True)
    assert result and result[0]['expected_value']>0
    assert result[0]['analysis_only'] is True and result[0]['decision']=='OBSERVE'
