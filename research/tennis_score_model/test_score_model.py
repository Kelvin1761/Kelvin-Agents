import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('score_model_research', Path(__file__).with_name('score_model.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.mark.parametrize('score,best,expected', [
    ('6-2 7-6(4)', 3, (13, 8)),
    ('0-6 7-6(4) 7-6(3)', 3, (14, 18)),
    ('6-4 3-6 6-1', 3, (15, 11)),
    ('6-4 6-4 6-4', 5, (18, 12)),
    ('6-4 4-6 70-68', 3, (80, 78)),
    ('6-4 1-0 RET', 3, None),
    ('W/O', 3, None),
    ('6-4 [10-7]', 3, None),
    ('6-4', 3, None),
    ('4-6 4-6', 3, None),
    ('6-4 6-4 6-4', 3, None),
    ('6-5 6-4', 3, None),
])
def test_scores(score, best, expected):
    assert m.score_games(score, best) == expected


def record(day, key, winner=1, loser=2):
    from datetime import date, timedelta
    return dict(date=day, available=(date.fromisoformat(day)+timedelta(days=21)).isoformat(),
                key=key, tour='ATP', winner=winner, loser=loser, surface='Hard',
                winner_games=12, loser_games=5)


def test_no_result_before_strict_availability():
    rows = [record('2020-01-01','a'), record('2020-01-22','b'),
            record('2020-01-23','c'), record('2020-01-23','d')]
    features = m.make_features(rows)
    assert [r['key'] for r in features] == ['c', 'd']
    assert features[0]['x_binary'] == features[1]['x_binary']
    assert features[0]['x_games'] == features[1]['x_games']


def test_target_score_does_not_enter_own_prediction():
    rows = [record('2020-01-01','a'), record('2020-02-01','b')]
    a = m.make_features(rows)[0]
    changed = dict(rows[-1], winner=2, loser=1, winner_games=18, loser_games=0)
    b = m.make_features([rows[0], changed])[0]
    assert a['x_binary'] == b['x_binary']
    assert a['x_games'] == b['x_games']
    assert a['y'] == 1-b['y']


def test_future_rows_do_not_change_past_features():
    rows = [record('2020-01-01','a'), record('2020-02-01','b')]
    a = m.make_features(rows)
    b = m.make_features(rows+[record('2020-03-01','c')])
    assert a == b[:len(a)]


def test_rating_side_swap_symmetry_and_tour_isolation():
    rating = m.Rating()
    a, b = ('ATP',1), ('ATP',2)
    rating.update(a,b,'Hard',.6)
    assert rating.feature(a,b,'Hard') == -rating.feature(b,a,'Hard')
    assert rating.feature(('WTA',1),('WTA',2),'Hard') == 0


def test_logistic_fit_identifies_signal_without_intercept():
    rng = np.random.default_rng(8)
    x = rng.normal(size=(20000,2))
    y = (rng.random(len(x)) < m.sigmoid(x @ np.array([1.,.5]))).astype(float)
    beta = m.fit(x,y)
    assert beta == pytest.approx([1.,.5], abs=.08)
    assert m.sigmoid(x[:10] @ beta) == pytest.approx(1-m.sigmoid(-x[:10] @ beta))


def test_small_training_population_refused():
    with pytest.raises(ValueError,match='insufficient'):
        m.fit(np.zeros((599,2)),np.ones(599))
