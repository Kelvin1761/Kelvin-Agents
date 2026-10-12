from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from au_serve_training_projection import replay_projection
from au_prediction_intake import PredictionValidationError
from au_racing_engine.scoring import MATRIX_WEIGHTS,compose_matrix_score
from au_racing_engine.renderer import ensure_verdict


def projection():
    rows={}
    for i in range(1,5):
        matrix={k:60.0 for k in MATRIX_WEIGHTS};matrix['stability']=70-i
        rows[str(i)]={'horse_name':f'H{i}','matrix_scores':matrix,'feature_scores':{},
                      'wet_raw':0.1234,'class_raw':0.123456789}
    return {'schema':'au-serving-training-projection/v1','rows':rows,'runner_ids':list(rows)}


def test_raw_overlay_and_production_safety_are_preserved():
    p=projection();before=deepcopy(p);w=dict(MATRIX_WEIGHTS)
    result=replay_projection(p,w)
    expected=round(round(compose_matrix_score(p['rows']['1']['matrix_scores'],weights=w),4)+0.1234+0.123456789,4)
    assert result['ability']['1']==expected
    assert p==before and result['ranking']==['1','2','3','4']


def test_thin_evidence_swap_is_not_replaced_by_sorting_scores():
    from au_racing_engine.renderer import THIN_EVIDENCE_SCORED_LEAVES
    p=projection();p['rows']['1']['feature_scores']={k:60 for k in THIN_EVIDENCE_SCORED_LEAVES}
    result=replay_projection(p,dict(MATRIX_WEIGHTS))
    assert result['ability']['1']>result['ability']['2']
    assert result['ranking'][:2]==['2','1']


def test_weight_state_uses_exact_six_dimensions():
    with pytest.raises(PredictionValidationError,match='dimension_keys'):
        replay_projection(projection(),{'unknown':1})


def test_nonfinite_projection_fails():
    p=projection();p['rows']['1']['class_raw']=float('nan')
    with pytest.raises(PredictionValidationError,match='nonfinite_overlay'):
        replay_projection(p,dict(MATRIX_WEIGHTS))


def test_tie_break_matches_production():
    p=projection()
    for row in p['rows'].values():row['matrix_scores']={k:60 for k in MATRIX_WEIGHTS}
    p['runner_ids']=['4','2','3','1']
    assert replay_projection(p,dict(MATRIX_WEIGHTS))['ranking']==['1','2','3','4']



def test_json_weight_order_does_not_change_production_rounding():
    values=[100,20,90,30,80,40]
    weights_values=[0.1985817161998799,0.3393982436352133,0.09333068640237596,
                   0.1281336376124551,0.7556821553949953,0.4156721737092097]
    matrix=dict(zip(MATRIX_WEIGHTS,values));weights=dict(zip(MATRIX_WEIGHTS,weights_values))
    rows={str(i):{'horse_name':f'H{i}','matrix_scores':deepcopy(matrix),
                 'feature_scores':{},'wet_raw':0.0,'class_raw':0.0} for i in range(1,5)}
    p={'schema':'au-serving-training-projection/v1','runner_ids':list(rows),'rows':rows}
    expected=round(compose_matrix_score(matrix,weights=weights),4)
    assert expected==60.1235
    assert replay_projection(p,dict(reversed(list(weights.items()))))['ability']['1']==expected
