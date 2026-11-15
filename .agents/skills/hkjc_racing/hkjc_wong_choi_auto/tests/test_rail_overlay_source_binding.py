"""Full native rail and overlay reader integration; synthetic identity only."""
import csv
import io
import json
import os
import subprocess
import sys

import pytest
from test_sectional_source_binding import ROOT, case


def rail_csv(version):
    stream=io.StringIO(); writer=csv.writer(stream)
    writer.writerow(['Date','RaceNo','Venue','Track','Distance','Rail','FieldSize','Draw','Place'])
    for rail in ('C+3','A'):
        for index in range(120):
            place = int(index < 60 and ((rail == 'C+3') == (version == 'A')))
            writer.writerow([f'2026-10-{1+index%20:02d}',1+index%20,'沙田','Turf',1200,rail,12,9+index%3,place])
    return stream.getvalue()


def day_payload(version,day='2026-10-01'):
    return {str(i): {'racedate':day,'venue':'ShaTin','race_no':i,
                    'results':[{'pos':'1','jockey':'潘頓' if version=='A' else f'別人{i}'}]}
            for i in range(1,8)}


DRIVER=r'''
import contextlib,hashlib,io,json,os,sys
from pathlib import Path
repo,hk,logic_path,request,mode=sys.argv[1:]
sys.path[:0]=[repo,str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'),str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_race_extractor/scripts')]
import wongchoi_paths
wongchoi_paths.HK_RACING=Path(hk)
import hkjc_auto_orchestrator as auto
from hkjc_racing_engine import rail_draw_context as rail,overlays
# Profile networking remains explicitly outside these two reader bindings.
auto._get_profile_scraper=lambda:None
root=Path(hk)/'HKJC_Race_Results_Database'
rail_path=root/'comprehensive_stats/rail_draw_results.csv'
values=[]; cache=None
logic=json.loads(Path(logic_path).read_text())
for item in json.loads(Path(request).read_text()):
    rail_path.parent.mkdir(parents=True,exist_ok=True)
    rail_path.write_text(item['rail']); os.utime(rail_path,ns=(1700000000000000000,1700000000000000000))
    for name,payload in item['days'].items():
        target=root/name; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(payload,ensure_ascii=False)); os.utime(target,ns=(1700000000000000000,1700000000000000000))
    runner=auto.HKJCAutoOrchestrator(Path(logic_path))
    kwargs={}
    if mode=='bound':
        if not values:
            with contextlib.redirect_stdout(io.StringIO()): runner.score_logic_data(Path(logic_path),logic)
            cache=(rail._read_dataset.cache_info(),overlays._jockey_wins_by_day.cache_info())
        from hkjc_racing_engine.rail_draw_context import RailDrawSource
        from hkjc_racing_engine.overlay_sources import OverlaySource,observe_catalog_sha256
        kwargs={'rail_source':RailDrawSource(rail_path,hashlib.sha256(rail_path.read_bytes()).hexdigest()),
                'overlay_source':OverlaySource(root,observe_catalog_sha256(root))}
    with contextlib.redirect_stdout(io.StringIO()): result=runner.score_logic_data(Path(logic_path),logic,**kwargs)
    if mode=='bound':
        proof=result['python_auto_run_contract'].pop('bound_context_sources')
        assert proof['rail']['sha256']==kwargs['rail_source'].sha256
        assert proof['overlay']['catalog_sha256']==kwargs['overlay_source'].sha256
    values.append(result)
if cache: assert cache==(rail._read_dataset.cache_info(),overlays._jockey_wins_by_day.cache_info())
assert json.loads(Path(logic_path).read_text())==logic
print(json.dumps(values,ensure_ascii=False,allow_nan=False))
'''


def context_case(tmp_path):
    hk,path=case(tmp_path)
    logic=json.loads(path.read_text()); logic['race_analysis'].update(track='Turf',rail='C+3')
    path.write_text(json.dumps(logic))
    return hk,path


def sequence_item(rail_version,overlay_version):
    payload=day_payload(overlay_version)
    return {'rail':rail_csv(rail_version),'days':{
        'hkjc results 2026 27/2026-10-01/full_day_results.json':payload,
        'hkjc results 2026 27/2026-10-01/duplicate.json':payload,
        'hkjc results 2026 27/2026-11-08/future.json':day_payload('A','2026-11-08')}}


def run_context(tmp_path,hk,path,versions,mode='default'):
    request=tmp_path/'contexts.json'; request.write_text(json.dumps([sequence_item(*v) for v in versions]))
    result=subprocess.run([sys.executable,'-B','-c',DRIVER,str(ROOT),str(hk),str(path),str(request),mode],cwd=tmp_path,
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stdout+result.stderr
    return json.loads(result.stdout)


def test_actual_stat_keyed_rail_and_root_keyed_overlay_cache_stay_on_a(tmp_path):
    hk,path=context_case(tmp_path)
    a=run_context(tmp_path,hk,path,[('A','A')])[0]
    b=run_context(tmp_path,hk,path,[('B','B')])[0]
    assert a['horses']['2']['python_auto']['ability_score_raw'] != b['horses']['2']['python_auto']['ability_score_raw']
    assert a['horses']['1']['python_auto']['overlays']['top_jockey_today']['value']==1
    assert b['horses']['1']['python_auto']['overlays']['top_jockey_today']['value']==0
    assert run_context(tmp_path,hk,path,[('A','A'),('B','B')])==[a,a]


def test_explicit_rail_and_overlay_a_b_a_match_complete_native_outputs(tmp_path):
    hk,path=context_case(tmp_path)
    a=run_context(tmp_path,hk,path,[('A','A')])[0]
    b=run_context(tmp_path,hk,path,[('B','B')])[0]
    assert run_context(tmp_path,hk,path,[('A','A'),('B','B'),('A','A')],'bound')==[a,b,a]


@pytest.mark.parametrize('which',['rail','overlay'])
def test_each_resource_independently_changes_native_consumer(tmp_path,which):
    hk,path=context_case(tmp_path)
    version=('B','A') if which=='rail' else ('A','B')
    a=run_context(tmp_path,hk,path,[('A','A')])[0]
    b=run_context(tmp_path,hk,path,[version])[0]
    aa=a['horses']['2' if which=='rail' else '1']['python_auto']
    bb=b['horses']['2' if which=='rail' else '1']['python_auto']
    if which=='rail':
        assert aa['feature_scores']['draw_score'] != bb['feature_scores']['draw_score']
        assert aa['race_shape_detail']['rail_draw_context']['adjustment'] != bb['race_shape_detail']['rail_draw_context']['adjustment']
    else:
        assert aa['overlays']['top_jockey_today']['value']==1
        assert bb['overlays']['top_jockey_today']['value']==0
    assert run_context(tmp_path,hk,path,[('A','A'),version,('A','A')],'bound')==[a,b,a]


def write_sources(root):
    (root/'comprehensive_stats').mkdir(parents=True)
    rail=root/'comprehensive_stats/rail_draw_results.csv'; rail.write_text(rail_csv('A'))
    day=root/'hkjc results 2026 27/2026-10-01'; day.mkdir(parents=True)
    (day/'full_day_results.json').write_text(json.dumps(day_payload('A')))
    return rail,day


@pytest.mark.parametrize('fault',['hash','untyped','absent','malformed','columns','linked','unreadable','bytes'])
def test_rail_faults_reject_before_headers_or_enrichment(tmp_path,monkeypatch,fault):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import rail_draw_context as rail
    from hkjc_racing_engine import native_sources as source
    hk,path=context_case(tmp_path)
    root=hk/'HKJC_Race_Results_Database'; dataset,_=write_sources(root)
    import hashlib
    binding=rail.RailDrawSource(dataset,hashlib.sha256(dataset.read_bytes()).hexdigest())
    if fault=='hash': binding=rail.RailDrawSource(dataset,'0'*64)
    elif fault=='untyped': binding={'path':str(dataset),'sha256':binding.sha256}
    elif fault=='absent': binding=rail.RailDrawSource(dataset,None)
    elif fault=='malformed':
        dataset.write_text('"unterminated'); binding=rail.RailDrawSource(dataset,hashlib.sha256(dataset.read_bytes()).hexdigest())
    elif fault=='columns': dataset.write_text('Wrong\n1\n'); binding=rail.RailDrawSource(dataset,hashlib.sha256(dataset.read_bytes()).hexdigest())
    elif fault=='linked':
        other=root/'other.csv'; other.write_bytes(dataset.read_bytes()); dataset.unlink(); dataset.symlink_to(other)
    elif fault=='unreadable':
        def failed(*args,**kwargs): raise OSError('unreadable')
        monkeypatch.setattr(source,'capture_source_file',failed)
    elif fault=='bytes': monkeypatch.setattr(source,'MAX_SOURCE_BYTES',1)
    header=Mock(side_effect=AssertionError('header ran before resource validation'))
    enrich=Mock(side_effect=AssertionError('enrichment ran before resource validation'))
    monkeypatch.setattr(auto,'_align_runner_headers',header); monkeypatch.setattr(auto,'_enrich_profile_history',enrich)
    with pytest.raises((ValueError,OSError,UnicodeError)):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),rail_source=binding)
    header.assert_not_called(); enrich.assert_not_called()


@pytest.mark.parametrize('fault',['hash','untyped','absent','season','day','file','removed','malformed','linked','unreadable','bytes','entries'])
def test_overlay_faults_reject_before_headers_or_enrichment(tmp_path,monkeypatch,fault):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import overlay_sources as source
    hk,path=context_case(tmp_path)
    root=hk/'HKJC_Race_Results_Database'; _,day=write_sources(root)
    binding=source.OverlaySource(root,source.observe_catalog_sha256(root))
    if fault=='hash': binding=source.OverlaySource(root,'0'*64)
    elif fault=='untyped': binding={'root':str(root),'sha256':binding.sha256}
    elif fault=='absent': binding=source.OverlaySource(root,None)
    elif fault=='season': (root/'hkjc results noncanonical').mkdir()
    elif fault=='day': (day.parent/'not-a-date').mkdir()
    elif fault=='file': (day/'other.json').write_text('{}')
    elif fault=='removed': (day/'full_day_results.json').unlink()
    elif fault=='malformed': (day/'full_day_results.json').write_text('{"bad":')
    elif fault=='linked': (day/'other.json').symlink_to(day/'full_day_results.json')
    elif fault=='unreadable': monkeypatch.setattr(source,'is_materialized_file',lambda _:False)
    elif fault=='bytes': monkeypatch.setattr(source,'MAX_CATALOG_BYTES',1)
    elif fault=='entries': monkeypatch.setattr(source,'MAX_ENTRIES',1)
    header=Mock(side_effect=AssertionError('header ran before resource validation'))
    enrich=Mock(side_effect=AssertionError('enrichment ran before resource validation'))
    monkeypatch.setattr(auto,'_align_runner_headers',header); monkeypatch.setattr(auto,'_enrich_profile_history',enrich)
    with pytest.raises((ValueError,OSError,UnicodeError)):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),overlay_source=binding)
    header.assert_not_called(); enrich.assert_not_called()


def test_overlay_universe_duplicate_order_window_and_tie_rules_match_native(tmp_path):
    from datetime import date
    from hkjc_racing_engine import overlays,overlay_sources as source
    root=tmp_path/'database'
    day=root/'hkjc results weird alias/not-a-date'; day.mkdir(parents=True)
    # First lexical copy wins even when the duplicate contradicts it.
    first=day_payload('A'); last=day_payload('B')
    (day/'aaa.json').write_text(json.dumps(first)); (day/'zzz.json').write_text(json.dumps(last))
    (day/'.hidden.json').write_text(json.dumps(day_payload('B')))
    hidden=day.parent/'.hidden'; hidden.mkdir(); (hidden/'x.json').write_text(json.dumps(day_payload('B')))
    extra=day.parent/'other'; extra.mkdir()
    for name,payload in [('future',day_payload('B','2026-11-08')),('old',day_payload('B','2025-01-01'))]:
        (extra/(name+'.json')).write_text(json.dumps(payload))
    held,proof=source.prepare_bound_history(source.OverlaySource(root,source.observe_catalog_sha256(root)))
    assert held==overlays._jockey_wins_by_day(str(root))
    assert overlays.top_jockeys_as_of(date(2026,11,8),history=held)==(frozenset({'潘頓'}),{'潘頓':7})
    assert set(proof['catalog']['files'])=={'hkjc results weird alias/not-a-date/aaa.json','hkjc results weird alias/not-a-date/zzz.json','hkjc results weird alias/other/future.json','hkjc results weird alias/other/old.json'}
    # Seven equal counts retain native name order at the six-jockey cutoff.
    tied={date(2026,10,1):{str(i):1 for i in range(7)}}
    assert overlays.top_jockeys_as_of(date(2026,11,8),history=tied)[0]==frozenset(str(i) for i in range(6))


def test_explicit_absent_resources_never_use_warmed_default_readers(tmp_path,monkeypatch):
    from hkjc_racing_engine import rail_draw_context as rail,overlays,overlay_sources as source
    def forbidden(*args,**kwargs): raise AssertionError('default resource reader called')
    monkeypatch.setattr(rail,'_dataset',forbidden); monkeypatch.setattr(overlays,'_jockey_wins_by_day',forbidden)
    history,proof=rail.prepare_bound_history(rail.RailDrawSource(tmp_path/'absent.csv',None))
    assert history.empty and proof['sha256'] is None
    context={'race_date':'2026-11-08','venue':'沙田','distance':1200,'rail':'C+3','track':'Turf'}
    assert rail.rail_draw_context_adjustment(context,12,history=history)['reason']=='rail_history_unavailable'
    wins,proof=source.prepare_bound_history(source.OverlaySource(tmp_path/'absent-root',None))
    from datetime import date
    assert wins=={} and overlays.top_jockeys_as_of(date(2026,11,8),history=wins) is None
    assert proof['catalog']['root_entries'] is None


def test_overlay_root_appearance_cannot_be_adopted_as_absence(tmp_path,monkeypatch):
    from hkjc_racing_engine import overlay_sources as source
    root=tmp_path/'database'; original=source._capture
    def appeared(path): write_sources(root); return original(path)
    monkeypatch.setattr(source,'_capture',appeared)
    with pytest.raises(ValueError,match='absent.*appeared'):
        source.prepare_bound_history(source.OverlaySource(root,None))


def test_overlay_second_payload_budget_rejects_before_read(tmp_path,monkeypatch):
    from hkjc_racing_engine import overlay_sources as source
    root=tmp_path/'database'; _,day=write_sources(root)
    first=day/'aaa.json'; first.write_text('{}')
    original=source.capture_source_file; calls=[]
    def capture(path,*,maximum_bytes=None):
        calls.append((path,maximum_bytes)); return original(path,maximum_bytes=maximum_bytes)
    monkeypatch.setattr(source,'capture_source_file',capture); monkeypatch.setattr(source,'MAX_CATALOG_BYTES',3)
    with pytest.raises(ValueError,match='bounded regular'): source.observe_catalog_sha256(root)
    assert len(calls)==2 and calls[1][1]==1


@pytest.mark.parametrize('change',['rewrite','replace','added_file'])
def test_overlay_mutations_during_capture_reject(tmp_path,monkeypatch,change):
    from hkjc_racing_engine import overlay_sources as source
    root=tmp_path/'database'; _,day=write_sources(root)
    first=day/'aaa.json'; first.write_text('{}')
    original=source.capture_source_file
    def capture(path,*,maximum_bytes=None):
        held=original(path,maximum_bytes=maximum_bytes)
        if path.name=='full_day_results.json':
            if change=='rewrite': first.write_text('{"changed":{}}')
            elif change=='replace':
                info=first.stat(); staged=day/'staged'
                staged.write_bytes(first.read_bytes()); os.utime(staged,ns=(info.st_atime_ns,info.st_mtime_ns)); os.replace(staged,first)
            else: (day/'new.json').write_text('{}')
        return held
    monkeypatch.setattr(source,'capture_source_file',capture)
    with pytest.raises(ValueError,match='changed'):
        source.observe_catalog_sha256(root)


def test_held_rail_frame_is_not_mutated_across_adjustment_calls(tmp_path):
    import hashlib
    from hkjc_racing_engine import rail_draw_context as rail
    dataset=tmp_path/'rail.csv'; dataset.write_text(rail_csv('A'))
    frame,_=rail.prepare_bound_history(rail.RailDrawSource(dataset,hashlib.sha256(dataset.read_bytes()).hexdigest()))
    before=frame.copy(deep=True)
    context={'race_date':'2026-11-08','venue':'沙田','distance':1200,'rail':'C+3','track':'Turf'}
    assert rail.rail_draw_context_adjustment(context,12,history=frame)['adjustment']==4.0
    rail.rail_draw_context_adjustment({**context,'rail':'A'},12,history=frame)
    rail.rail_draw_context_adjustment({**context,'race_date':'2026-10-01'},12,history=frame)
    assert frame.equals(before)


def test_ambiguous_glob_root_is_rejected_instead_of_selecting_other_data(tmp_path):
    from hkjc_racing_engine import overlay_sources as source
    root=tmp_path/'db[12]'; write_sources(root)
    with pytest.raises(ValueError,match='ambiguous'): source.observe_catalog_sha256(root)



def test_secondary_upgrade_helper_uses_explicit_overlay_history(tmp_path,monkeypatch):
    from datetime import date
    from hkjc_racing_engine import overlays,scoring
    from hkjc_racing_engine.engine_core import RacingEngine
    def forbidden(*args,**kwargs): raise AssertionError('default overlay history called')
    monkeypatch.setattr(overlays,'_jockey_wins_by_day',forbidden)
    # Exercise the existing dormant branch in this test only; production switch
    # and overlay weights remain unchanged in source and on disk.
    monkeypatch.setattr(scoring,'JOCKEY_CHANGE_SKIP_TOP_UPGRADE',True)
    horse={'jockey':'潘頓','_data':{'jockey_combo_block':'| 1 | 01/10/2026 | 普通騎師 | 5 | 舊紀錄 |'}}
    context={'race_date':'2026-11-08'}
    top=RacingEngine(horse,context,overlay_history={date(2026,10,1):{'潘頓':7}})
    other=RacingEngine(horse,context,overlay_history={date(2026,10,1):{'別人':7}})
    assert top._is_top_jockey_upgrade_exempt() is True
    assert other._is_top_jockey_upgrade_exempt() is False
