from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / 'Horse_Racing_Dashboard'))
from au_racing_engine.dimensions import registry_snapshot  # noqa: E402
from backend.models.race import RaceAnalysis  # noqa: E402
from backend.services.au_dimension_registry import read_registry_metadata  # noqa: E402


def block(value):
    return '<!-- wc-au-dimensions:v1:' + base64.b64encode(json.dumps(value).encode()).decode() + ' -->'


def test_snapshot_is_detached_and_exactly_roundtrips():
    original = registry_snapshot()
    snap = copy.deepcopy(original)
    text = 'before\n' + block(snap) + '\nafter'
    decoded, cleaned = read_registry_metadata(text)
    assert decoded == json.loads(json.dumps(original))
    assert cleaned == 'before\n\nafter'
    snap['dimensions'][0]['label'] = 'different'
    assert registry_snapshot()['dimensions'][0]['label'] == original['dimensions'][0]['label']
    race = RaceAnalysis(race_number=1, dimension_registry=decoded)
    assert json.loads(race.model_dump_json())['dimension_registry'] == decoded


def test_legacy_report_remains_unknown_and_unchanged():
    text = '## Race 1 legacy report'
    assert read_registry_metadata(text) == (None, text)
    assert RaceAnalysis(race_number=1).dimension_registry is None


@pytest.mark.parametrize('kind', ['tamper', 'duplicate', 'schema', 'malformed', 'oversized'])
def test_invalid_metadata_is_observable(kind):
    value = registry_snapshot()
    if kind == 'tamper':
        value['dimensions'][0]['label'] = 'tampered'
    elif kind == 'schema':
        value['schema'] = 'au/unsupported'
    text = block(value)
    if kind == 'duplicate':
        text += '\n' + text
    elif kind == 'malformed':
        text = '<!-- wc-au-dimensions:v2:abc -->'
    elif kind == 'oversized':
        text = '<!-- wc-au-dimensions:v1:' + 'A' * 65537 + ' -->'
    with pytest.raises(ValueError):
        read_registry_metadata(text)


def test_one_registry_entry_reaches_engine_report_dashboard_and_eval(tmp_path):
    # An isolated fresh interpreter sees one added report-only dimension.
    # No consumer monkeypatch and no mutation of the real registry or profiles.
    package = tmp_path / 'au_racing_engine'
    shutil.copytree(SCRIPTS / 'au_racing_engine', package, ignore=shutil.ignore_patterns('__pycache__'))
    path = package / 'dimensions.py'
    source = path.read_text()
    source = source.replace('FEATURE_KEYS = tuple',
        "DIMENSION_SPECS = (*DIMENSION_SPECS, DimensionSpec('plugin_probe', '測試新增維度', (('form_score', 1.0),)))\n\nFEATURE_KEYS = tuple", 1)
    path.write_text(source)
    code = '''
import json,sys
sys.path.insert(0,sys.argv[1]);sys.path.insert(1,sys.argv[2]);sys.path.insert(2,sys.argv[3]);sys.path.insert(3,str(__import__('pathlib').Path(sys.argv[3])/'backend'))
from au_racing_engine import dimensions as d, matrix_mapper as m, renderer as r
from au_racing_engine.engine_core import RacingEngine
from au_racing_engine.scoring import compose_matrix_score
from services.parser_au import parse_au_analysis
import au_eval
fs=dict.fromkeys(d.FEATURE_KEYS,60.0);fs['form_score']=80
ms=m.map_features_to_matrix_scores(fs)
assert ms['plugin_probe']==80 and 'plugin_probe' not in d.MATRIX_WEIGHTS
assert compose_matrix_score(ms)==compose_matrix_score({k:v for k,v in ms.items() if k!='plugin_probe'})
row={'features':fs,'wet':0.,'proven_class':0.}
base=au_eval.default_scorer(row)
assert au_eval.default_scorer({**row,'features':{k:v for k,v in fs.items()}})==base
probe=au_eval.configured_scorer(weights={**d.MATRIX_WEIGHTS,'plugin_probe':0.2})(row)
assert abs(probe-base)>0.01
engine=RacingEngine({'horse_name':'Plugin Probe'},{'race_number':1,'distance':1200,'going':'Good 4'})
auto=engine.analyze_horse()
assert 'plugin_probe' in auto['matrix_scores'] and 'plugin_probe' in auto['matrix_reasoning']
logic={'race_analysis':{'race_number':1,'distance':1200},'horses':{'1':{'horse_name':'Plugin Probe','python_auto':auto}}}
path=__import__('pathlib').Path(sys.argv[4])/'Race_1_Auto_Analysis.md'
path.write_text(r.render_race_markdown(logic))
assert '測試新增維度' in path.read_text()
parsed=parse_au_analysis(str(path))
assert parsed and any(x['key']=='plugin_probe' for x in parsed.dimension_registry['dimensions'])
assert any(x.name=='測試新增維度' for x in parsed.horses[0].dimension_details)
assert json.loads(parsed.model_dump_json())['dimension_registry']['registry_sha256']==d.registry_snapshot()['registry_sha256']
print('PASS: registry-only dimension -> actual engine/report/dashboard snapshot/eval; dormant score unchanged')
'''
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', WC_SB_CACHE_ONLY='1',
               WC_PF_BACKFILL='0', WC_DISABLE_POST_SUCCESS_DEPLOY='1')
    child = subprocess.run([sys.executable, '-B', '-c', code, str(tmp_path), str(SCRIPTS),
                            str(ROOT / 'Horse_Racing_Dashboard'), str(tmp_path)],
                           cwd=ROOT, env=env, capture_output=True, text=True)
    assert child.returncode == 0, child.stdout + child.stderr
