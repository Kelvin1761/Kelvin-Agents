"""Retired dimensions cannot silently re-enter the default fitted search."""
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import au_matrix_refit as refit
from au_racing_engine.dimensions import MATRIX_WEIGHTS


def fixture(tmp_path):
    rows=[{'n':i,'name':f'Horse{i}','pos':i,'features':{'pace_map_score':draw},'wet':0,'proven_class':0,'ability':60}
          for i,draw in [(1,30),(2,90)]]
    path=tmp_path/'data.json';path.write_text(json.dumps({'races':[{'date':'2026-08-05','meeting':'fixture','race':1,'field':2,'rows':rows}]}))
    return path


def test_default_search_has_exact_live_registry_dimensions(tmp_path):
    assert refit.DIMS==tuple(MATRIX_WEIGHTS)
    assert 'race_shape' not in refit.DIMS and 'form_line' not in refit.DIMS
    ds=refit.Dataset(fixture(tmp_path));mx=ds.dim_matrix()
    assert mx.shape==(2,6)
    np.testing.assert_array_equal(ds.ability(mx,MATRIX_WEIGHTS),[60,60])


def test_explicit_research_dimension_reaches_actual_cli_matrix_path(tmp_path,monkeypatch):
    path=fixture(tmp_path);captured={}
    monkeypatch.setattr(refit,'DIMS',tuple(MATRIX_WEIGHTS))
    monkeypatch.setattr(refit,'OBJ_KEYS',refit.OBJ_KEYS)
    def inspect_dataset(ds,args):
        mx=ds.dim_matrix();captured['dims']=refit.DIMS;captured['shape']=mx.shape
        captured['candidate']=ds.ability(mx,{'race_shape':1.0})
    monkeypatch.setattr(refit,'cmd_verify',inspect_dataset)
    monkeypatch.setattr(sys,'argv',['au_matrix_refit.py','verify','--data',str(path),'--with-dimension','race_shape'])
    refit.main()
    assert captured['dims']==tuple(MATRIX_WEIGHTS)+('race_shape',)
    assert captured['shape']==(2,7)
    np.testing.assert_array_equal(captured['candidate'],[30,90])
