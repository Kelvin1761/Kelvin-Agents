"""Registry changes must invalidate explanations/contracts without changing HK."""
import importlib.util
from pathlib import Path
import sys

SHARED=Path(__file__).parents[3]/'shared_racing/scripts'

def load(name):
    spec=importlib.util.spec_from_file_location('audit_registry_'+name,SHARED/(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module


def test_explanation_fingerprint_includes_optional_registry(tmp_path):
    module=load('explain_model')
    tmp_path=tmp_path/'au_racing_engine'
    tmp_path.mkdir()
    (tmp_path/'scoring.py').write_text('original')
    initial=dict(module.fingerprint(tmp_path)[0])
    assert 'dimensions.py' not in initial
    (tmp_path/'dimensions.py').write_text('registry-v1')
    registered=dict(module.fingerprint(tmp_path)[0])
    assert 'dimensions.py' in registered
    (tmp_path/'dimensions.py').write_text('registry-v2')
    updated=dict(module.fingerprint(tmp_path)[0])
    assert registered['dimensions.py']!=updated['dimensions.py']
    assert initial['scoring.py']==updated['scoring.py']
    hk=tmp_path.parent/'hkjc_racing_engine';hk.mkdir();(hk/'dimensions.py').write_text('existing HK registry')
    assert 'dimensions.py' not in dict(module.fingerprint(hk)[0])


def test_contract_fingerprint_binds_registry_and_platforms_remain_separate(tmp_path,monkeypatch):
    module=load('data_contract')
    au=tmp_path/'au';hk=tmp_path/'hk';au.mkdir();hk.mkdir()
    (au/'scoring.py').write_text('au');(hk/'scoring.py').write_text('hk')
    monkeypatch.setitem(module.PLATFORMS,'au',dict(module.PLATFORMS['au'],engine=au))
    monkeypatch.setitem(module.PLATFORMS,'hkjc',dict(module.PLATFORMS['hkjc'],engine=hk))
    au_before=module.engine_fingerprint('au');hk_before=module.engine_fingerprint('hkjc')
    (au/'dimensions.py').write_text('registry')
    (hk/'dimensions.py').write_text('existing HK registry')
    assert module.engine_fingerprint('au')!=au_before
    assert module.engine_fingerprint('hkjc')==hk_before
