import sys
from pathlib import Path
import copy
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import serve_model as m


def raw(w=(60,35,25,12),l=(65,40,28,11)):
    out={}
    for side,vals in [('w',w),('l',l)]:
        out.update({side+'_'+col:str(v) for col,v in zip(('svpt','1stIn','1stWon','2ndWon'),vals)})
    return out


def test_counts_use_service_wins_not_match_winner():
    assert m.point_counts(raw())==[(37,60),(39,65)]


@pytest.mark.parametrize('counts',[(0,0,0,0),(10,11,5,0),(10,5,6,0),(10,5,3,6),(10,-1,0,0)])
def test_invalid_counts_rejected(counts):
    assert m.point_counts(raw(w=counts)) is None


def test_missing_side_does_not_impute():
    x=raw();x.pop('l_svpt');assert m.point_counts(x) is None


def test_fractional_counts_rejected():
    x=raw();x['w_svpt']='10.5';assert m.point_counts(x) is None


def test_opponent_return_strength_changes_adjusted_update():
    a,b=('ATP',1),('ATP',2)
    strong=m.PointStrength({'ATP':0.},True); neutral=m.PointStrength({'ATP':0.},True)
    strong.state[(b,'','R')]=1.
    for model in (strong,neutral):model.update(a,b,'Hard',[(50,100),(50,100)])
    assert strong.state[(a,'','S')]>neutral.state[(a,'','S')]


def test_unadjusted_server_ignores_opponent_return_strength():
    a,b=('ATP',1),('ATP',2)
    strong=m.PointStrength({'ATP':0.},False);neutral=m.PointStrength({'ATP':0.},False)
    strong.state[(b,'','R')]=1.
    for model in (strong,neutral):model.update(a,b,'Hard',[(50,100),(50,100)])
    assert strong.state[(a,'','S')]==neutral.state[(a,'','S')]


def test_surface_initialization_uses_preupdate_overall():
    a,b=('ATP',1),('ATP',2);model=m.PointStrength({'ATP':0.},True)
    model.update(a,b,'Hard',[(60,100),(50,100)])
    assert model.state[(a,'','S')]==model.state[(a,'Hard','S')]


def test_symmetry_tour_isolation_and_update_counts():
    a,b=('ATP',1),('ATP',2);model=m.PointStrength({'ATP':0.},True)
    model.update(a,b,'Hard',[(60,100),(45,100)])
    for component in ('S','R'):
        assert model.difference(a,b,'Hard',component)==-model.difference(b,a,'Hard',component)
        assert model.difference(('WTA',1),('WTA',2),'Hard',component)==0
        assert model.count[(a,'',component)]==1


def record(day,key,tour='ATP',winner=1,loser=2):
    from datetime import date,timedelta
    return dict(date=day,available=(date.fromisoformat(day)+timedelta(days=21)).isoformat(),
                key=key,tour=tour,winner=winner,loser=loser,surface='Hard',
                winner_games=12,loser_games=6,point_counts=[(60,100),(50,100)],x_rank=.3)


def corpus():
    return {'rows':[record('2020-01-01','warm-atp'),record('2020-01-01','warm-wta','WTA'),
                    record('2021-01-01','past'),record('2021-01-22','boundary'),
                    record('2021-01-23','target'),record('2021-01-23','same_day')]}


def test_strict_availability_and_same_day_freeze():
    rows,_,_=m.features(corpus());by={r['key']:r for r in rows}
    for col in ('adjusted_S','adjusted_R','raw_S','raw_R'):
        assert by['past'][col]==by['boundary'][col]
        assert by['target'][col]==by['same_day'][col]
    assert by['target']['adjusted_S']!=by['boundary']['adjusted_S']


def test_own_and_future_points_cannot_enter_current_prediction():
    data=corpus();before,mu,_=m.features(data)
    modified=copy.deepcopy(data)
    modified['rows'][-2]['point_counts']=[(99,100),(1,100)]
    after,other_mu,_=m.features(modified)
    assert mu==other_mu
    for col in ('adjusted_S','adjusted_R','raw_S','raw_R','x_binary'):
        assert [r[col] for r in before]==[r[col] for r in after]


def test_warmup_mu_excludes_future_2021_points():
    data=corpus();_,mu,_=m.features(data)
    data['rows'][2]['point_counts']=[(99,100),(99,100)]
    _,other_mu,_=m.features(data)
    assert mu==other_mu


def test_missing_history_neutral_not_disadvantage():
    data=corpus();past=record('2020-01-01','new_history',winner=3,loser=4);past['point_counts']=None
    data['rows'].insert(2,past)
    data['rows'].append(record('2021-02-01','new',winner=3,loser=4))
    rows,_,_=m.features(data);r=rows[-1]
    assert not r['point_history_both']
    assert all(r[col]==0 for col in ('adjusted_S','adjusted_R','raw_S','raw_R'))


def test_zero_new_information_cannot_create_adjusted_gain():
    row=dict(date='2021-01-01',available='2021-01-22',x_binary=.1,x_rank=.3,
             raw_S=0.,raw_R=0.,adjusted_S=0.,adjusted_R=0.,y=0,
             point_history_both=False,tour='ATP',surface='Hard',level='A',best_of=3)
    rows=[dict(row,y=i%2) for i in range(600)]
    rows.append(dict(row,date='2023-02-01',available='2023-02-22'))
    result,_=m.evaluate(rows,'2023-01-01','2023-07-01')
    for control in ('raw','rank'):
        for metric in ('log_loss','brier'):
            assert abs(result['deltas'][control][metric]['mean'])<1e-12
