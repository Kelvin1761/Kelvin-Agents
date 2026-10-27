import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('nudge_diagnostic',Path(__file__).with_name('tennis-stored-nudge-ablation-20261027.py'))
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


def model():
    parts=[{'name':name,'probability':.7,'weight':.2,'active':True} for name in h.NAMES]
    parts.extend({'name':name,'probability':.8,'weight':.5,'active':True} for name in ('overall_elo_edge','surface_elo_edge'))
    return {'elo_base_logit':1.,'total_nudge_logit':.36,'components':parts}


def test_all_off_is_recorded_backbone_and_individual_ablation_is_real():
    ps=h.variants(model())
    assert ps['all_off']==h.probability(1.)
    assert ps['baseline']==h.probability(1.36)
    assert ps[h.NAMES[0]]==pytest.approx(h.probability(1.32),abs=1e-15)


def test_reconstruction_mismatch_and_empty_backbone_cannot_enter_corpus():
    m=model();m['total_nudge_logit']=.9
    with pytest.raises(ValueError,match='mismatch'):h.variants(m)
    m=model()
    for p in m['components']:
        if p['name'].endswith('elo_edge'):p['active']=False
    with pytest.raises(ValueError,match='no active Elo'):h.variants(m)


def test_unlogged_activity_is_not_guessed():
    m=model();del m['components'][0]['active']
    with pytest.raises(ValueError,match='activity not recorded'):h.variants(m)


def test_paired_bootstrap_tie_has_zero_interval_and_no_significance():
    stats=h.bootstrap_columns([[0.],[0.],[0.]])[0]
    assert stats['mean']==0 and stats['ci95']==[0.,0.]
    assert stats['bootstrap_two_sided_p']==1.
    assert h.holm([.01,.04,.03])==[.03,.06,.06]


def test_recorded_side_and_segment_risk_are_applied_to_every_arm():
    pricing={'model':model(),'selection_side':'player_b','segment_risk_discount':.12,'no_vig_market_probability':.4}
    ps=h.priced_variants(pricing)
    assert ps['baseline']==pytest.approx(.4+((1-h.probability(1.36))-.4)*.88,abs=1e-15)
    assert ps['all_off']==pytest.approx(.4+((1-h.probability(1.))-.4)*.88,abs=1e-15)


def test_missing_recorded_risk_is_not_fitted_or_defaulted():
    pricing={'model':model(),'selection_side':'player_a','no_vig_market_probability':.6}
    with pytest.raises(KeyError):h.priced_variants(pricing)
