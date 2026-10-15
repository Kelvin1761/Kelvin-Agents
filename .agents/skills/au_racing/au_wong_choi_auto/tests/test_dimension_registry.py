"""Metadata equivalence; full-corpus producer and remaining consumers audit separately."""
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).parents[1]/"scripts"))

from au_racing_engine import dimensions, matrix_mapper, renderer, scoring


def test_legacy_metadata_exactly_retained():
    expected = json.loads((Path(__file__).parent/'dimension_registry_legacy_expected.json').read_text())
    for key, value in expected.items():
        owner = scoring if hasattr(scoring,key) else (matrix_mapper if hasattr(matrix_mapper,key) else renderer)
        # JSON canonical comparison retains insertion order separately below.
        assert json.loads(json.dumps(getattr(owner,key))) == value
    assert list(scoring.MATRIX_WEIGHTS) == list(expected['MATRIX_WEIGHTS'])
    assert list(matrix_mapper.MATRIX_FORMULAS) == list(expected['MATRIX_FORMULAS'])


def test_class_score_contribution_evidence_and_report_roles_are_distinct():
    spec=next(s for s in dimensions.LEAF_SPECS if s.key=='class_score')
    assert spec.report_only and not spec.counts_as_evidence and spec.shown_in_report
    assert dimensions.contributes_to_score('class_score') == scoring.CLASS_SCORE_LIVE
    assert 'class_score' not in renderer.THIN_EVIDENCE_SCORED_LEAVES
    assert renderer._default_leaf_count({'feature_scores':{'class_score':60}})==0


def test_retired_draw_still_counts_for_legacy_ability_keys_without_direct_score():
    assert 'pace_map_score' in scoring.ABILITY_FEATURE_KEYS
    assert not dimensions.contributes_to_score('pace_map_score')
    assert 'pace_map_score' not in renderer.THIN_EVIDENCE_SCORED_LEAVES


def test_safety_count_and_composition_unchanged():
    assert renderer._default_leaf_count({'feature_scores':dict.fromkeys(scoring.FEATURE_KEYS,60)})==8  # EXP-20261016-01: trial_score no longer evidence
    fs={key:60+i*.75 for i,key in enumerate(scoring.FEATURE_KEYS)}
    matrices=matrix_mapper.map_features_to_matrix_scores(fs)
    independent=60+sum((matrices[key]-60)*weight for key,weight in scoring.MATRIX_WEIGHTS.items())
    assert scoring.compose_matrix_score(matrices)==independent


def test_class_live_off_uses_same_registry_formula_and_no_class_weight():
    import os
    env=dict(os.environ,WC_AU_CLASS_SCORE_LIVE='0',PYTHONDONTWRITEBYTECODE='1')
    package_parent=Path(dimensions.__file__).parents[1]
    code=f"import sys;sys.path.insert(0,{str(package_parent)!r});from au_racing_engine import dimensions as d;assert d.MATRIX_FORMULAS['class_weight']==(('rating_score',.70),);assert not d.contributes_to_score('class_score');assert 'class_score' in d.REPORT_ONLY_FEATURE_KEYS"
    result=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
