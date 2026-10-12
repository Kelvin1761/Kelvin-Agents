from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import au_production_consensus_fit as fit
from au_prediction_intake import content_hash,PredictionValidationError
from au_racing_engine.scoring import MATRIX_WEIGHTS


def records():
    rows={}
    for n in range(1,7):
        matrix={k:60.0 for k in MATRIX_WEIGHTS}
        matrix['stability']=100-10*n;matrix['jockey_trainer']=30+10*n
        rows[str(n)]={'horse_name':f'H{n}','matrix_scores':matrix,'feature_scores':{},
                      'wet_raw':0.0,'class_raw':0.123456789}
    projection={'schema':'au-serving-training-projection/v1','runner_ids':list(rows),'rows':rows}
    out=[]
    for day in range(5,15):
        labels={str(n):n for n in range(1,7)}
        out.append({'race_id':f'd{day}','date':f'2026-08-{day:02d}',
                    'input':{'training_projection':deepcopy(projection),'training_projection_hash':content_hash(projection)},
                    'labels':labels,'labels_hash':content_hash(labels)})
    return out


def profile():
    return {'fit_spec':{'algorithm':'au-production-day-consensus/v1','search_budget':3000,
            'folds':5,'objective':'place','minimum_nonnegative_folds':5,'median_recheck':True,
            'seed':7,'baseline_weights':dict(MATRIX_WEIGHTS)}}


def test_folds_never_split_a_day_and_cover_all_races():
    r=records();r.append({**deepcopy(r[0]),'race_id':'other'})
    folds=fit._day_folds(r)
    assert sum(map(len,folds))==len(r)
    assert len({i for i,f in enumerate(folds) if any(x['date']==r[0]['date'] for x in f)})==1


def test_actual_projection_consensus_is_deterministic_and_keeps_budget():
    r=records();before=deepcopy(r)
    a=fit._consensus_search(r,dict(MATRIX_WEIGHTS),seed=7,budget=24)
    b=fit._consensus_search(r,dict(MATRIX_WEIGHTS),seed=7,budget=24)
    assert a==b and a is not None and r==before
    assert sum(a['matrix_weights'].values())==pytest.approx(sum(MATRIX_WEIGHTS.values()),abs=1e-12)
    assert fit._objective(r,a['matrix_weights'])>fit._objective(r,dict(MATRIX_WEIGHTS))
    assert all(fit._objective(f,a['matrix_weights'])>=fit._objective(f,dict(MATRIX_WEIGHTS)) for f in fit._day_folds(r))


def test_identical_ranking_returns_no_consensus():
    r=records()
    for x in r:
        for row in x['input']['training_projection']['rows'].values():row['matrix_scores']={k:60 for k in MATRIX_WEIGHTS}
    assert fit._consensus_search(r,dict(MATRIX_WEIGHTS),seed=7,budget=12) is None


def test_public_adapter_uses_registered_search_and_no_other_data(monkeypatch):
    seen={}
    def kernel(prefix,baseline,**kwargs):
        seen.update(kwargs);prefix[0]['labels']['1']=99;return None
    monkeypatch.setattr(fit,'_consensus_search',kernel)
    r=records();before=deepcopy(r)
    assert fit.fit_production_coefficients(r,profile()) is None
    assert seen=={'seed':7,'budget':3000} and r==before


@pytest.mark.parametrize('mutation,message',[
    ('projection','projection_hash'),('labels','labels_hash'),('duplicate','duplicate_training'),
    ('old_date','clean_window'),('budget','algorithm_not_registered'),('baseline','locked_baseline')])
def test_binding_errors_raise_instead_of_fallback(mutation,message):
    r=records();p=profile()
    if mutation=='projection':r[0]['input']['training_projection']['rows']['1']['wet_raw']=4
    elif mutation=='labels':r[0]['labels']['1']=2
    elif mutation=='duplicate':r.append(deepcopy(r[0]))
    elif mutation=='old_date':r[0]['date']='2026-08-04'
    elif mutation=='budget':p['fit_spec']['search_budget']=10
    elif mutation=='baseline':p['fit_spec']['baseline_weights']['track']+=.1
    with pytest.raises(PredictionValidationError,match=message):fit.fit_production_coefficients(r,p)


def test_insufficient_days_fails_without_empty_folds():
    with pytest.raises(PredictionValidationError,match='training_days'):fit._day_folds(records()[:4])


def test_draws_preserve_existing_refit_concentration_and_registry_order(monkeypatch):
    import random
    from au_matrix_refit import dirichlet
    observed=[]
    def objective(records,weights):
        observed.append(dict(weights));return 0.0
    monkeypatch.setattr(fit,'_objective',objective)
    baseline=dict(reversed(list(MATRIX_WEIGHTS.items())))
    assert fit._consensus_search(records(),baseline,seed=7,budget=2) is None
    rng=random.Random(7)
    expected=[dirichlet(rng,[1.0]*len(MATRIX_WEIGHTS)),
              dirichlet(rng,[max(v*25,.35) for v in MATRIX_WEIGHTS.values()])]
    for actual,vector in zip(observed[-2:],expected):
        assert list(actual)==list(MATRIX_WEIGHTS)
        assert list(actual.values())==pytest.approx(vector,abs=1e-14)
