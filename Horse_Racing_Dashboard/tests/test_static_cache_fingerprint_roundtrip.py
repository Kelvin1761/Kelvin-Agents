import copy
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'Horse_Racing_Dashboard/generate_static.py'
spec=importlib.util.spec_from_file_location('fingerprint_collector',P)
G=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=G
spec.loader.exec_module(G)

class Clock(datetime):
    @classmethod
    def now(cls,tz=None):
        return cls(2026,10,12,12,0,0)

def test_fingerprint_survives_actual_json_cache_roundtrip(tmp_path):
    source=tmp_path/'Race_1_Auto_Analysis.md'
    source.write_text('Unchanged report\n')
    meeting=G._au_meeting_from_directory(tmp_path/'2026-08-05 Fixture Race 1-1')
    meeting.folder_paths={'Kelvin':str(tmp_path)}
    fingerprint=G._source_fingerprint(meeting)
    cache=tmp_path/'cache.json'
    G._write_cache(cache,{'fixture':{'fingerprint':fingerprint}})
    loaded=G._load_cache(cache)['entries']['fixture']['fingerprint']
    assert loaded==fingerprint==G._source_fingerprint(meeting)

def test_actual_collector_reuses_unchanged_and_refreshes_changed_inputs(tmp_path):
    folder=tmp_path/'2026-08-05 Fixture Race 1-1'
    folder.mkdir()
    source=folder/'Race_1_Auto_Analysis.md'
    source.write_text('MAIDEN')
    meeting=G._au_meeting_from_directory(folder)
    cache=tmp_path/'cache.json'
    calls=[]
    def collect(m):
        calls.append(source.read_text())
        metadata={'date':m.date,'venue':m.venue,'region':m.region.value,'analysts':['Kelvin']}
        key=f'{m.date}|{m.venue}'
        races={'meeting':metadata,'races_by_analyst':{'Kelvin':[{'race_number':1,'race_class':source.read_text(),'going':'Heavy 8','horses':[]}]}}
        return metadata,key,races,{}
    with patch.object(G,'discover_meetings',return_value=[meeting]), \
         patch.object(G,'_collect_meeting',side_effect=collect), \
         patch.object(G,'_attach_track_geometry',side_effect=lambda m:m), \
         patch.object(G,'get_summary_roi',return_value={}) as roi, \
         patch.object(G,'datetime',Clock):
        cold=G.collect_all_data(cache)
        warm=G.collect_all_data(cache)
        assert calls==['MAIDEN']
        assert cold==warm
        source.write_text('GROUP 2 CHANGED')
        changed=G.collect_all_data(cache)
        assert calls==['MAIDEN','GROUP 2 CHANGED']
        assert changed['races']['2026-08-05|Fixture']['races_by_analyst']['Kelvin'][0]['race_class']=='GROUP 2 CHANGED'
        assert roi.call_count==3
    assert copy.deepcopy(cold)==warm
