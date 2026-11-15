"""Whole native-source preparation coherence, synthetic data only."""
import json
import os
from pathlib import Path

import pytest

from test_sectional_source_binding import case
from test_same_course_source_binding import database_files


def write_database(root, version):
    for relative, text in database_files(version).items():
        if relative.endswith('.json'):
            payload=json.loads(text)
            for race in payload.values():
                race['racedate']=Path(relative).parent.name
                race['results'][0]['jockey']='潘頓' if version=='A' else '別人'
            text=json.dumps(payload,ensure_ascii=False)
        path=root/relative; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text); os.utime(path,ns=(1700000000000000000,1700000000000000000))


def test_overlapping_native_catalogs_cannot_prepare_different_daily_bytes(tmp_path,monkeypatch):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    import hkjc_same_course_times as same
    from hkjc_racing_engine import completed_sources as completed,overlay_sources as overlays
    hk,path=case(tmp_path); root=hk/'HKJC_Race_Results_Database'
    write_database(root,'B')
    overlay=overlays.OverlaySource(root,overlays.observe_catalog_sha256(root))
    write_database(root,'A')
    history=completed.CompletedRowsSource(root,completed.observe_catalog_sha256(root))
    original=same.prepare_bound_history; observed={}
    def interleave(source):
        result=original(source); assert result
        observed['same_course']=result
        write_database(root,'B')
        return result
    monkeypatch.setattr(same,'prepare_bound_history',interleave)
    header=Mock(side_effect=AssertionError('incoherent catalogs reached native headers'))
    monkeypatch.setattr(auto,'_align_runner_headers',header)
    with pytest.raises(ValueError,match='source.*coherence|source.*changed'):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),same_course_source=history,overlay_source=overlay)
    assert observed['same_course']
    header.assert_not_called()


WHOLE_DRIVER = r'''
import contextlib,hashlib,io,json,sys,os
from pathlib import Path
from datetime import date
repo,hk,logic_path,request,mode=sys.argv[1:]
sys.path[:0]=[repo,str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'),str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_race_extractor/scripts')]
import wongchoi_paths
wongchoi_paths.HK_RACING=Path(hk)
import requests
network=[]
def forbidden_network(*a,**kw): network.append(1); raise AssertionError('network called')
requests.sessions.Session.request=forbidden_network
logic_path=Path(logic_path); hk=Path(hk)
requests_data=json.loads(Path(request).read_text()); values=[]; cache=None
for item in requests_data:
    for relative,raw in item.items():
        file=hk/relative; file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(bytes.fromhex(raw)); os.utime(file,ns=(1700000000000000000,1700000000000000000))
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import live_priors as lp,pit_sections as ps,engine_core as core,rail_draw_context as rail,overlays,debut_trainer,market_history as market
    import hkjc_same_course_times as same
    lp.hk_today=lambda:date(2026,11,8)
    logic=json.loads(logic_path.read_text())
    runner=auto.HKJCAutoOrchestrator(logic_path,shadow_profile='trainer_recency_st_early90')
    kwargs={}
    if mode=='bound':
        if not values:
            with contextlib.redirect_stdout(io.StringIO()): runner.score_logic_data(logic_path,logic)
            import scrape_hkjc_horse_profile as legacy
            from copy import deepcopy
            cached_rail=rail._dataset(rail.DATASET)
            cached_overlay=overlays._jockey_wins_by_day(str(overlays.RESULTS_DB))
            rail_before=cached_rail.copy(deep=True); overlay_before=deepcopy(cached_overlay)
            def cache_data():
                return deepcopy((lp._JT_RATINGS.jockey,lp._JT_RATINGS.trainer,
                    lp._RECENCY_TRAINER_RATINGS.trainer,lp._RECENCY_TRAINER_RATINGS.as_of_date,
                    core._TRAINER_SIGNAL_PRIORS.combo,core._TRAINER_SIGNAL_PRIORS.jockey_distance,
                    core._TRAINER_SIGNAL_PRIORS.trainer_distance,core._TRAINER_SIGNAL_PRIORS.jockey_change,
                    lp._PRIOR_SOURCE_MANIFEST,ps._TABLE,same._HISTORY,debut_trainer._EVENTS,legacy._profile_cache,market._TABLE))
            data_before=cache_data()
            cache=(lp._JT_RATINGS,lp._RECENCY_TRAINER_RATINGS,core._TRAINER_SIGNAL_PRIORS,lp._PRIOR_SOURCE_MANIFEST,ps._TABLE,same._HISTORY,debut_trainer._EVENTS,legacy._profile_cache,market._TABLE,rail._read_dataset.cache_info(),overlays._jockey_wins_by_day.cache_info())
            def forbidden_reader(*a,**kw): raise AssertionError('strict full invocation used default resource getter')
            auto._get_profile_scraper=forbidden_reader
        from hkjc_racing_engine.native_sources import JsonSource
        from hkjc_racing_engine import completed_sources as cs,prior_sources as pri,overlay_sources as ovs,meeting_sources as ms
        def j(path): return JsonSource(path,hashlib.sha256(path.read_bytes()).hexdigest())
        db=hk/'HKJC_Race_Results_Database'; stats=db/'comprehensive_stats'
        kwargs={'sectional_source':j(hk/'HKJC_Sections/pit_sections.json'),
                'profile_source':j(logic_path.parent/'.hkjc_cache/profile_cache.json'),
                'same_course_source':cs.CompletedRowsSource(db,cs.observe_catalog_sha256(db)),
                'prior_source':pri.PriorSource(stats,pri.observe_catalog_sha256(stats)),
                'rail_source':rail.RailDrawSource(stats/'rail_draw_results.csv',hashlib.sha256((stats/'rail_draw_results.csv').read_bytes()).hexdigest()),
                'overlay_source':ovs.OverlaySource(db,ovs.observe_catalog_sha256(db)),
                'meeting_source':ms.MeetingSource(logic_path.parent,ms.observe_catalog_sha256(logic_path,1)),
                'debut_source':j(hk/'HKJC_Sections/debut_trainer.json'),
                'market_source':j(hk/'HKJC_Sections/market_history.json')}
    with contextlib.redirect_stdout(io.StringIO()): result=runner.score_logic_data(logic_path,logic,**kwargs)
    if mode=='bound':
        contract=result['python_auto_run_contract']
        observation=contract.pop('bound_source_observation')
        assert observation['source_names']==['sectional','profile','same_course','prior','rail','overlay','meeting','debut','market']
        assert len(observation['files'])>=15 and observation['absent_paths']
        assert observation['bytes_read']>=sum(info['size'] for info in observation['files'].values())
        assert contract.pop('bound_prior_source')['catalog_sha256']==kwargs['prior_source'].sha256
        contexts=contract.pop('bound_context_sources')
        assert contexts['overlay']['catalog_sha256']==kwargs['overlay_source'].sha256
        assert contexts['market']['sha256']==kwargs['market_source'].sha256
        assert contract.pop('bound_meeting_sources')['meeting']['catalog_sha256']==kwargs['meeting_source'].sha256
    else:
        assert 'bound_source_observation' not in result['python_auto_run_contract']
    values.append(result)
if cache:
    current=(lp._JT_RATINGS,lp._RECENCY_TRAINER_RATINGS,core._TRAINER_SIGNAL_PRIORS,lp._PRIOR_SOURCE_MANIFEST,ps._TABLE,same._HISTORY,debut_trainer._EVENTS,legacy._profile_cache,market._TABLE,rail._read_dataset.cache_info(),overlays._jockey_wins_by_day.cache_info())
    assert all(a is b for a,b in zip(cache[:9],current[:9])) and cache[9:]==current[9:]
    assert cache_data()==data_before
    assert cached_rail.equals(rail_before) and cached_overlay==overlay_before
assert not network
print(json.dumps(values,ensure_ascii=False,allow_nan=False))
'''


def whole_case(tmp_path):
    from test_meeting_source_binding import display_case
    hk,path=display_case(tmp_path)
    # Place this meeting under the synthetic native data root. The legacy
    # profile cache genuinely loads from cwd, which is this meeting directory.
    meeting=hk/path.parent.name; path.parent.rename(meeting); path=meeting/path.name
    logic=json.loads(path.read_text()); logic['race_analysis'].update(rail='C+3',track='Turf')
    for number,horse in logic['horses'].items():
        horse['horse_code']='A00'+number
        horse['trackwork']={'horseid':'HK_SYNTH_'+number}
        horse['hkjc_horse_id']='HK_SYNTH_'+number
    path.write_text(json.dumps(logic))
    return hk,path


def whole_files(path,version,stamp):
    from test_sectional_source_binding import TABLE_A,TABLE_B
    from test_profile_source_binding import cache
    from test_prior_source_binding import prior_files
    from test_rail_overlay_source_binding import rail_csv
    from test_meeting_source_binding import facts,events,display_files
    files={}
    for relative,text in database_files(version).items():
        if relative.endswith('.json'):
            payload=json.loads(text)
            for race in payload.values():
                race['racedate']=Path(relative).parent.name
                race['results'][0]['jockey']='潘頓' if version=='A' else '別人'
            text=json.dumps(payload)
        files['HKJC_Race_Results_Database/'+relative]=text.encode()
    for relative,text in prior_files(version).items(): files['HKJC_Race_Results_Database/comprehensive_stats/'+relative]=text.encode()
    files['HKJC_Race_Results_Database/comprehensive_stats/rail_draw_results.csv']=rail_csv(version).encode()
    files['HKJC_Sections/pit_sections.json']=json.dumps(TABLE_A if version=='A' else TABLE_B,sort_keys=True).encode()
    files['HKJC_Sections/debut_trainer.json']=json.dumps(events(version)).encode()
    files['HKJC_Sections/market_history.json']=json.dumps({'version':1,'horses':{
        'A001':[['2026-10-01',3.0 if version=='A' else 25.0],['2026-11-08',999.0]],
        'A002':[['2026-10-01',25.0 if version=='A' else 3.0]]}}).encode()
    prefix=path.parent.name+'/'
    for relative,content in display_files(version).items():
        if relative=='.hkjc_cache/profile_cache.json': continue
        files[prefix+relative]=content['utf16'].encode('utf-16') if isinstance(content,dict) else content.encode()
    files[prefix+'Synthetic Race 1 Facts.md']=facts(version).encode()
    files[prefix+'.hkjc_cache/profile_cache.json']=json.dumps(cache(70 if version=='A' else 40,timestamp=stamp),sort_keys=True).encode()
    return {name:raw.hex() for name,raw in files.items()}


def run_whole(tmp_path,hk,path,versions,*,mode='default',repo=None):
    import subprocess,sys,time
    from test_sectional_source_binding import ROOT
    request=tmp_path/'whole-source-sequence.json'; stamp=time.time()
    request.write_text(json.dumps([whole_files(path,version,stamp) for version in versions]))
    result=subprocess.run([sys.executable,'-B','-c',WHOLE_DRIVER,str(ROOT if repo is None else repo),str(hk),str(path),str(request),mode],
        cwd=path.parent,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    return json.loads(result.stdout)


def test_all_nine_native_sources_together_match_full_fresh_a_b_a(tmp_path):
    hk,path=whole_case(tmp_path)
    a=run_whole(tmp_path,hk,path,['A'])[0]; b=run_whole(tmp_path,hk,path,['B'])[0]
    assert a!=b
    assert a['horses']['1']['python_auto']['market_history_delta'] != 0
    assert run_whole(tmp_path,hk,path,['A','B','A'],mode='bound')==[a,b,a]


@pytest.mark.parametrize('change',['rewrite','same_bytes_replace','appearance','inventory'])
def test_finalization_rejects_changes_before_headers_enrichment_events(tmp_path,monkeypatch,change):
    from unittest.mock import Mock
    import hashlib
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import debut_trainer as debut,meeting_sources as meeting
    from hkjc_racing_engine.native_sources import JsonSource
    from test_sectional_source_binding import TABLE_A,TABLE_B
    hk,path=case(tmp_path); section=hk/'HKJC_Sections/section.json'; late=hk/'HKJC_Sections/debut.json'
    section.write_text(json.dumps(TABLE_A)); late.write_text('{"events":[]}')
    if change=='appearance': section.unlink()
    source=JsonSource(section,None if change=='appearance' else hashlib.sha256(section.read_bytes()).hexdigest())
    kwargs={'sectional_source':source,'debut_source':JsonSource(late,hashlib.sha256(late.read_bytes()).hexdigest())}
    if change=='inventory': kwargs['meeting_source']=meeting.MeetingSource(path.parent,meeting.observe_catalog_sha256(path,1))
    original=debut.prepare_bound_events
    def mutate(value):
        result=original(value)
        if change=='same_bytes_replace':
            info=section.stat(); staged=section.parent/'staged'
            staged.write_bytes(section.read_bytes()); os.utime(staged,ns=(info.st_atime_ns,info.st_mtime_ns)); os.replace(staged,section)
        elif change=='inventory': (path.parent/'Unobserved Race 1 Facts.md').write_text('new')
        else: section.write_text(json.dumps(TABLE_B))
        return result
    monkeypatch.setattr(debut,'prepare_bound_events',mutate)
    header=Mock(side_effect=AssertionError('headers after invalid finalization')); enrich=Mock(); sink=Mock()
    monkeypatch.setattr(auto,'_align_runner_headers',header); monkeypatch.setattr(auto,'_enrich_profile_history',enrich)
    with pytest.raises(ValueError,match='source.*coherence|source.*changed'):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),event_sink=sink,**kwargs)
    header.assert_not_called(); enrich.assert_not_called(); sink.assert_not_called()


def test_different_paths_to_one_inode_cannot_capture_conflicting_json(tmp_path,monkeypatch):
    from unittest.mock import Mock
    import hashlib
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine.native_sources import JsonSource
    from test_sectional_source_binding import TABLE_A
    hk,path=case(tmp_path); source=hk/'source.json'; alias=hk/'alias.json'
    a=json.dumps({**TABLE_A,'HK_SYNTH_1':{'_ts':0,'data':{'horse_id':'HK_SYNTH_1','entries':[]}}}).encode()
    b=a.replace(b'24.0',b'22.0')
    source.write_bytes(a); os.link(source,alias)
    original=auto._prepare_profile_reader
    def interleave(*args,**kwargs): alias.write_bytes(b); return original(*args,**kwargs)
    monkeypatch.setattr(auto,'_prepare_profile_reader',interleave)
    header=Mock(); monkeypatch.setattr(auto,'_align_runner_headers',header)
    with pytest.raises(ValueError,match='source coherence.*inode'):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),
            sectional_source=JsonSource(source,__import__('hashlib').sha256(a).hexdigest()),
            profile_source=JsonSource(alias,__import__('hashlib').sha256(b).hexdigest()))
    header.assert_not_called()


def test_aggregate_byte_limit_blocks_second_payload_before_read(tmp_path,monkeypatch):
    import hashlib
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import native_sources as source,native_source_capture as capture
    hk,path=case(tmp_path); a=hk/'a.json'; b=hk/'b.json'
    a.write_text('{"standards":{}}'); b.write_text('{"unused":"long enough to exceed remaining byte"}')
    monkeypatch.setattr(capture,'MAX_CAPTURE_BYTES',a.stat().st_size+1)
    reads=[]; original=source.os.fdopen
    class Spy:
        def __init__(self,handle): self.handle=handle
        def __enter__(self): self.handle.__enter__(); return self
        def __exit__(self,*args): return self.handle.__exit__(*args)
        def __getattr__(self,name): return getattr(self.handle,name)
        def read(self,size=-1): reads.append(size); return self.handle.read(size)
    monkeypatch.setattr(source.os,'fdopen',lambda *args,**kwargs:Spy(original(*args,**kwargs)))
    with pytest.raises(ValueError,match='bounded regular'):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),
            sectional_source=source.JsonSource(a,hashlib.sha256(a.read_bytes()).hexdigest()),
            profile_source=source.JsonSource(b,hashlib.sha256(b.read_bytes()).hexdigest()))
    assert reads==[a.stat().st_size]
    assert capture._ACTIVE.get() is None


@pytest.mark.parametrize('bound',['MAX_OBSERVATIONS','MAX_NAMESPACE_ENTRIES'])
def test_aggregate_observation_limits_block_native_preparation(tmp_path,monkeypatch,bound):
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import meeting_sources as meeting,native_source_capture as capture
    hk,path=case(tmp_path); source=meeting.MeetingSource(path.parent,meeting.observe_catalog_sha256(path,1))
    monkeypatch.setattr(capture,bound,1)
    with pytest.raises(ValueError,match='source coherence.*bound'):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),meeting_source=source)
    assert capture._ACTIVE.get() is None


def test_failed_or_nested_native_preparation_resets_capture_scope(tmp_path,monkeypatch):
    import hashlib
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import native_source_capture as capture
    from hkjc_racing_engine.native_sources import JsonSource
    from test_sectional_source_binding import TABLE_A
    hk,path=case(tmp_path); file=hk/'section.json'; file.write_text(json.dumps(TABLE_A)); source=JsonSource(file,hashlib.sha256(file.read_bytes()).hexdigest())
    original=auto._prepare_profile_reader
    def nested(*args,**kwargs):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),sectional_source=source)
    monkeypatch.setattr(auto,'_prepare_profile_reader',nested)
    with pytest.raises(ValueError,match='nested native source coherence'):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),sectional_source=source,profile_source=JsonSource(hk/'absent.json',None))
    assert capture._ACTIVE.get() is None
    monkeypatch.setattr(auto,'_prepare_profile_reader',original)
    # Prepare real source data again after failure; capture state cannot leak.
    with capture.source_capture(['sectional']) as observed:
        from hkjc_racing_engine.native_sources import read_bound_json
        assert read_bound_json(source)==TABLE_A
        receipt=observed.finish()
    assert set(receipt['files'])=={str(file)} and capture._ACTIVE.get() is None


def test_concurrent_actual_nine_source_invocations_keep_capture_state_separate(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    import hashlib
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import native_source_capture as capture,completed_sources as cs,prior_sources as pri,overlay_sources as ov,meeting_sources as ms,rail_draw_context as rail
    from hkjc_racing_engine.native_sources import JsonSource
    from test_sectional_source_binding import TABLE_A,TABLE_B
    inputs=[]
    for index,table in enumerate([TABLE_A,TABLE_B]):
        parent=tmp_path/str(index); parent.mkdir(); hk,path=case(parent)
        section=hk/'section.json'; section.write_text(json.dumps(table))
        kwargs={'sectional_source':JsonSource(section,hashlib.sha256(section.read_bytes()).hexdigest()),
                'profile_source':JsonSource(hk/'absent-profile.json',None),
                'same_course_source':cs.CompletedRowsSource(hk/'absent-db',None),
                'prior_source':pri.PriorSource(hk/'absent-stats',None),
                'rail_source':rail.RailDrawSource(hk/'absent-rail.csv',None),
                'overlay_source':ov.OverlaySource(hk/'absent-overlay',None),
                'meeting_source':ms.MeetingSource(path.parent,ms.observe_catalog_sha256(path,1)),
                'debut_source':JsonSource(hk/'absent-debut.json',None),
                'market_source':JsonSource(hk/'absent-market.json',None)}
        inputs.append((hk,path,kwargs))
    barrier=Barrier(2); original=capture._Capture.file
    def interleave(self,path,metadata,identity):
        if Path(path).name=='section.json': barrier.wait(timeout=10)
        return original(self,path,metadata,identity)
    monkeypatch.setattr(capture._Capture,'file',interleave)
    def score(item):
        hk,path,kwargs=item
        result=auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),**kwargs)
        assert capture._ACTIVE.get() is None
        receipt=result['python_auto_run_contract']['bound_source_observation']
        assert len(receipt['source_names'])==9
        assert all(str(path.parent.parent.parent) in name for name in receipt['files'])
        assert all(str(inputs[1 if item is inputs[0] else 0][0]) not in name for name in receipt['files'])
        return result
    with ThreadPoolExecutor(max_workers=2) as workers: results=list(workers.map(score,inputs))
    assert results[0]['horses']['1']['python_auto']['ability_score_raw'] != results[1]['horses']['1']['python_auto']['ability_score_raw']
    assert capture._ACTIVE.get() is None
