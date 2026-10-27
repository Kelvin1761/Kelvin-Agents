import sys
from pathlib import Path
import math
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rank_prior as r


def test_rank_orientation_is_independent_of_winner():
    a, valid_a = r.rank_feature('10','50',1,2)
    b, valid_b = r.rank_feature('50','10',2,1)
    assert valid_a and valid_b
    assert a == pytest.approx(math.log(5))
    assert a == b


@pytest.mark.parametrize('a,b',[(None,1),('',1),('0','5'),('5','-1'),('10001','1'),('x','2')])
def test_missing_rank_is_neutral(a,b):
    assert r.rank_feature(a,b,1,2) == (0.,False)


def test_player_swap_changes_sign():
    a,_=r.rank_feature('10','50',1,2)
    b,_=r.rank_feature('10','50',2,1)
    assert a == -b


def test_ranking_not_used_to_choose_match_orientation():
    assert r.rank_feature('10','10',1,2) == (0.,True)


def test_confirmation_does_not_evaluate_rejected_arms():
    rows=[dict(date='2021-01-01', available='2021-01-22', x_binary=(i%5-2)*.1,
               x_games=(i%3-1)*.1, x_rank=(i%7-3)*.1, y=i%2,
               rank_present=True,tour='ATP',surface='Hard',level='A',best_of=3)
          for i in range(600)]
    rows += [dict(rows[0],date='2025-08-01',available='2025-08-22')]
    result, predictions=r.evaluate(rows,'2025-07-01','2026-01-01',eligible=['rank'])
    assert set(result['metrics']) == {'binary','rank','baseline'}
    assert set(result['deltas']) == {'rank_vs_binary'}
    assert 'combined_p' not in predictions[0]
