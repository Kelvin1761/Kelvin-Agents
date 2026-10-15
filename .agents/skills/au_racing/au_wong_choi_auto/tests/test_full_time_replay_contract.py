"""Replay an explicit overlay; absent evidence preserves every old score."""
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from au_eval import default_scorer,configured_scorer,load_races
from au_racing_engine.scoring import FEATURE_KEYS


def row():
    return {'features':{k:60.0 for k in FEATURE_KEYS},'wet':0.0,'proven_class':0.0}


@pytest.mark.parametrize('value',[-1.25,0,.75])
def test_default_and_configured_replay_keep_explicit_overlay(value):
    base=row();candidate={**base,'full_time':value}
    for scorer in (default_scorer,configured_scorer()):
        assert abs(scorer(candidate)-scorer(base)-value)<1e-10


def test_rich_snapshot_loads_runtime_overlay_and_missing_remains_zero(tmp_path):
    p=tmp_path/'dataset.json'
    p.write_text(json.dumps({'races':[{'date':'2026-10-16','rows':[
        {**row(),'pos':1,'full_time_speed_feature':.75},{**row(),'pos':4}]}]}))
    rows=load_races(p)[0]['rows']
    assert rows[0]['full_time']==.75
    assert rows[1]['full_time']==0
    assert abs(default_scorer(rows[0])-default_scorer(rows[1])-.75)<1e-10
