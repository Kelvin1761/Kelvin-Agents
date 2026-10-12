import importlib.util
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'Horse_Racing_Dashboard/generate_static.py'
spec=importlib.util.spec_from_file_location('class_cache_generator',P)
G=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=G
spec.loader.exec_module(G)

def test_unchanged_v6_cache_cannot_keep_race_number_as_class(tmp_path):
    cache=tmp_path/'cache.json'
    stale={'fixture':{'fingerprint':'unchanged','races':[{'race_class':'Race 1'}]}}
    cache.write_text(json.dumps({'version':6,'entries':stale}))
    original=cache.read_bytes()
    loaded=G._load_cache(cache)
    assert loaded['version']==G.CACHE_VERSION
    assert loaded['entries']=={}
    assert cache.read_bytes()==original
    fresh={'fixture':{'fingerprint':'unchanged','races':[{'race_class':'MAIDEN'}]}}
    G._write_cache(cache,fresh)
    assert G._load_cache(cache)['entries']==fresh
