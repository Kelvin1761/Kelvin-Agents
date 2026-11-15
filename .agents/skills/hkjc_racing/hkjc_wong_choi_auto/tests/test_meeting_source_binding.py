"""Native meeting/display resource binding, using synthetic files only."""
import hashlib
import json
import os
import subprocess
import sys

import pytest
from test_sectional_source_binding import ROOT,case


def facts(version):
    weight='126' if version=='A' else '140'
    delta='-0.20' if version=='A' else '-3.00'
    return f"### 馬號 1 — 測試甲 | 騎師: 潘頓 | 練馬師: 蔡約翰 | 負磅: {weight} | 檔位: 2\n全段速剖面\n| # | Δ1 |\n| 1 | {delta} |\n| 2 | {delta} |\n🔧\n### 馬號 2 — 測試乙 | 騎師: 普通騎師 | 練馬師: 普通練馬師 | 負磅: 133 | 檔位: 12\n"


def events(version):
    return {'events':[['2026-10-01','蔡約翰',int(version=='A')] for _ in range(10)] + [['2026-10-01','普通練馬師',int(version=='A')] for _ in range(10)] + [['2026-11-08','蔡約翰',1]]}


DRIVER=r'''
import contextlib,hashlib,io,json,os,sys
from pathlib import Path
repo,hk,logic_path,request,mode=sys.argv[1:]
sys.path[:0]=[repo,str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'),str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_race_extractor/scripts')]
import wongchoi_paths
wongchoi_paths.HK_RACING=Path(hk)
import hkjc_auto_orchestrator as auto
from hkjc_racing_engine import debut_trainer
# Other live resource readers are outside this meeting/debut slice.
auto._get_profile_scraper=lambda:None
logic_path=Path(logic_path); logic=json.loads(logic_path.read_text())
requests=json.loads(Path(request).read_text()); results=[]; initial_debut=None
debut_path=Path(hk)/'HKJC_Sections/debut_trainer.json'
for index,item in enumerate(requests):
    target=logic_path.parent/'Synthetic Race 1 Facts.md'; target.write_text(item['facts'])
    debut_path.write_text(json.dumps(item['events']))
    for relative,content in item.get('display',{}).items():
        file=logic_path.parent/relative; file.parent.mkdir(parents=True,exist_ok=True)
        if isinstance(content,dict): file.write_bytes(content['utf16'].encode('utf-16'))
        else: file.write_text(content)
    kwargs={}
    if mode.startswith('bound'):
        if not results:
            debut_trainer.load_events(); initial_debut=debut_trainer._EVENTS  # Populate real default A.
        from hkjc_racing_engine.meeting_sources import MeetingSource,observe_catalog_sha256
        from hkjc_racing_engine.native_sources import JsonSource
        kwargs['meeting_source']=MeetingSource(logic_path.parent,observe_catalog_sha256(logic_path,1))
        kwargs['debut_source']=JsonSource(debut_path,hashlib.sha256(debut_path.read_bytes()).hexdigest())
    original=auto._enrich_profile_history
    guarded={}
    if mode in {'interleave','bound_interleave','bound_locked'}:
        def interleave(*args,**kw):
            original(*args,**kw)
            target.write_text(requests[-1]['facts'])  # Owned fixture mutation after headers.
            if mode=='bound_locked':
                target.unlink()
                (logic_path.parent/'Competing Race 1 Facts.md').write_text('foreign fixture')
                def forbidden(*args,**kwargs): raise AssertionError('live meeting resolver used')
                for name in ('_facts_path_for_logic','_trackwork_path_for_logic','_formguide_path_for_logic','_racecard_path_for_logic'):
                    setattr(auto,name,forbidden)
                import hkjc_official_injury
                hkjc_official_injury.pdf_path_for_meeting=forbidden
                def guard(original):
                    def checked(self,*args,**kwargs):
                        if self==logic_path.parent or logic_path.parent in self.parents:
                            raise AssertionError('live meeting read/probe used: '+str(self))
                        return original(self,*args,**kwargs)
                    return checked
                for name in ('read_text','read_bytes','exists','glob'):
                    guarded[name]=getattr(Path,name); setattr(Path,name,guard(guarded[name]))
        auto._enrich_profile_history=interleave
    with contextlib.redirect_stdout(io.StringIO()):
        result=auto.HKJCAutoOrchestrator(logic_path).score_logic_data(logic_path,logic,**kwargs)
    auto._enrich_profile_history=original
    for name,method in guarded.items(): setattr(Path,name,method)
    if mode.startswith('bound'):
        proof=result['python_auto_run_contract'].pop('bound_meeting_sources')
        assert proof['meeting']['catalog_sha256']==kwargs['meeting_source'].sha256
        assert proof['debut']['sha256']==kwargs['debut_source'].sha256
    results.append(result)
    guarded={}
    if mode in {'interleave','bound_interleave','bound_locked'}: break
if initial_debut is not None: assert debut_trainer._EVENTS is initial_debut
assert json.loads(logic_path.read_text())==logic
print(json.dumps(results,ensure_ascii=False,allow_nan=False))
'''


def run_meeting(tmp_path,hk,path,versions,mode='default',display=False):
    request=tmp_path/'meeting-sequence.json'; request.write_text(json.dumps([{'facts':facts(v),'events':events(v),**({'display':display_files(v)} if display else {})} for v in versions]))
    result=subprocess.run([sys.executable,'-B','-c',DRIVER,str(ROOT),str(hk),str(path),str(request),mode],cwd=tmp_path,
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stdout+result.stderr
    return json.loads(result.stdout)


def test_actual_native_reopens_facts_after_headers_and_can_mix_versions(tmp_path):
    hk,path=case(tmp_path)
    a=run_meeting(tmp_path,hk,path,['A'])[0]
    b=run_meeting(tmp_path,hk,path,['B'])[0]
    assert a['horses']['1']['weight']=='126' and b['horses']['1']['weight']=='140'
    assert a['horses']['1']['_data']['first_section_min_delta']==-0.2
    assert b['horses']['1']['_data']['first_section_min_delta']==-3.0
    mixed=run_meeting(tmp_path,hk,path,['A','B'],'interleave')[0]
    assert mixed['horses']['1']['weight']=='126'
    assert mixed['horses']['1']['_data']['first_section_min_delta']==-3.0
    assert mixed != a and mixed != b


def test_bound_meeting_holds_native_inputs_across_calls_and_interleaving(tmp_path):
    hk,path=case(tmp_path)
    a=run_meeting(tmp_path,hk,path,['A'])[0]; b=run_meeting(tmp_path,hk,path,['B'])[0]
    assert run_meeting(tmp_path,hk,path,['A','B','A'],'bound')==[a,b,a]
    assert run_meeting(tmp_path,hk,path,['A','B'],'bound_interleave')[0]==a


def test_bound_meeting_rejects_logic_filename_race_identity_mismatch(tmp_path):
    from hkjc_racing_engine import meeting_sources as source
    root=tmp_path/'meeting'; root.mkdir()
    with pytest.raises(ValueError,match='race identity'):
        source.observe_catalog_sha256(root/'Race_2_Logic.json',1)


@pytest.mark.parametrize('alias',['same','hardlink'])
def test_same_profile_path_cannot_bind_two_different_snapshots(tmp_path,monkeypatch,alias):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import meeting_sources as source
    from hkjc_racing_engine.native_sources import JsonSource
    hk,path=case(tmp_path)
    cache=path.parent/'.hkjc_cache/profile_cache.json'; cache.parent.mkdir()
    logic=json.loads(path.read_text()); logic['horses']['1']['trackwork']={'horseid':'H1'}
    a=json.dumps({'H1':{'_ts':0,'data':{'horse_id':'H1','entries':[],'marker':'A'}}}).encode()
    b=a.replace(b'"A"',b'"B"')
    def write(raw): cache.write_bytes(raw); os.utime(cache,ns=(1700000000000000000,1700000000000000000))
    write(b); meeting=source.MeetingSource(path.parent,source.observe_catalog_sha256(path,1))
    write(a)
    profile_path=cache
    if alias=='hardlink':
        profile_path=tmp_path/'profile-alias.json'; os.link(cache,profile_path)
    profile=JsonSource(profile_path,hashlib.sha256(a).hexdigest())
    original=auto._prepare_profile_reader
    def interleave(*args,**kwargs):
        reader=original(*args,**kwargs); write(b); return reader
    monkeypatch.setattr(auto,'_prepare_profile_reader',interleave)
    header=Mock(side_effect=AssertionError('incoherent source passed to headers'))
    monkeypatch.setattr(auto,'_align_runner_headers',header)
    with pytest.raises(ValueError,match='profile.*binding'):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,logic,profile_source=profile,meeting_source=meeting)
    header.assert_not_called()



def display_files(version):
    priority='+' if version=='A' else ''
    card='班次: 第四班\n'
    for number,name in [('1','測試甲'),('2','測試乙')]:
        card+=f'\n馬號: {number}\n馬名: {name}\n優先參賽次序: {priority}\n\n'
    entry={'date':'01/10/2026','race_date_full':'01/10/2026','racecourse':'ST','venue_track':'沙田 草地',
           'distance':1200 if version=='A' else 1600,'placing':1 if version=='A' else 8,'jockey':'潘頓'}
    cache={'H1':{'_ts':0,'data':{'horse_id':'H1','entries':[dict(entry) for _ in range(3)]}}}
    injury='傷患記錄\n1 1 測試甲 A001 01/10/2026 左前球節手術 10/10/2026\n由香港賽馬會'
    if version=='B': injury=injury.replace('01/10/2026','09/11/2026')
    return {'Synthetic Race 1 排位表.md':card,'.hkjc_cache/profile_cache.json':json.dumps(cache),
            '01 全日出賽馬匹資料 (PDF).md':{'utf16':injury},'99 全日出賽馬匹資料 (PDF).md':'傷患記錄\n1 1 測試甲 A001 01/10/2026 流血 10/10/2026'}


def display_case(tmp_path):
    hk,path=case(tmp_path); logic=json.loads(path.read_text())
    logic['horses']['1']['hkjc_horse_id']='H1'; logic['horses']['1']['_data']['hk_starts']=3
    logic['horses']['2']['is_debut']=True
    path.write_text(json.dumps(logic)); return hk,path


def all_tags(value,number):
    tags=value['horses'][number]['python_auto']['summary']['tags']
    return {item['key']:item for group in tags.values() for item in group}


def test_native_display_profiles_priority_injury_debut_match_complete_fresh_outputs(tmp_path):
    hk,path=display_case(tmp_path)
    a=run_meeting(tmp_path,hk,path,['A'],display=True)[0]
    b=run_meeting(tmp_path,hk,path,['B'],display=True)[0]
    assert 'specialist' in all_tags(a,'1') and 'first_distance' in all_tags(b,'1')
    assert 'trainer_ace' in all_tags(a,'1') and 'trainer_ace' not in all_tags(b,'1')
    assert a['horses']['1']['_data']['official_injury_records'][0]['detail']=='左前球節手術'
    assert 'official_injury_records' not in b['horses']['1']['_data']
    assert all_tags(a,'2')['debut_trainer']['label'] != all_tags(b,'2')['debut_trainer']['label']
    assert run_meeting(tmp_path,hk,path,['A','B','A'],'bound',display=True)==[a,b,a]


def test_held_meeting_survives_deletion_new_candidates_and_forbids_live_reads(tmp_path):
    hk,path=display_case(tmp_path)
    a=run_meeting(tmp_path,hk,path,['A'],display=True)[0]
    assert run_meeting(tmp_path,hk,path,['A','B'],'bound_locked',display=True)[0]==a


@pytest.mark.parametrize('fault',['hash','root','race','untyped','facts_changed','cache_appeared','duplicate','linked','utf8','cache_json','cache_shape','unavailable','bytes','entries'])
def test_meeting_faults_reject_before_headers_enrichment_or_events(tmp_path,monkeypatch,fault):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import meeting_sources as source
    hk,path=case(tmp_path); f=path.parent/'Synthetic Race 1 Facts.md'; f.write_text(facts('A'))
    binding=source.MeetingSource(path.parent,source.observe_catalog_sha256(path,1))
    if fault=='hash': binding=source.MeetingSource(path.parent,'0'*64)
    elif fault=='root': binding=source.MeetingSource(tmp_path,binding.sha256)
    elif fault=='race':
        logic=json.loads(path.read_text()); logic['race_analysis']['race_number']=2; path.write_text(json.dumps(logic))
    elif fault=='untyped': binding={'root':str(path.parent),'sha256':binding.sha256}
    elif fault=='facts_changed': f.write_text(facts('B'))
    elif fault=='cache_appeared':
        (path.parent/'.hkjc_cache').mkdir(); (path.parent/'.hkjc_cache/profile_cache.json').write_text('{}')
    elif fault=='duplicate': (path.parent/'Other Race 1 Facts.md').write_text('other')
    elif fault=='linked': f.unlink(); f.symlink_to(path)
    elif fault=='utf8': f.write_bytes(b'\xff'); binding=source.MeetingSource(path.parent,source._capture(path,1)[2])
    elif fault in {'cache_json','cache_shape'}:
        (path.parent/'.hkjc_cache').mkdir(); (path.parent/'.hkjc_cache/profile_cache.json').write_text('{bad' if fault=='cache_json' else '{"H1":42}')
        binding=source.MeetingSource(path.parent,source._capture(path,1)[2])
    elif fault=='unavailable': monkeypatch.setattr(source,'is_materialized_file',lambda _:False)
    elif fault=='bytes': monkeypatch.setattr(source,'MAX_CATALOG_BYTES',1)
    elif fault=='entries': monkeypatch.setattr(source,'MAX_ENTRIES',1)
    header=Mock(side_effect=AssertionError('header before validation')); enrich=Mock(side_effect=AssertionError('enrichment before validation')); sink=Mock()
    monkeypatch.setattr(auto,'_align_runner_headers',header); monkeypatch.setattr(auto,'_enrich_profile_history',enrich)
    with pytest.raises((ValueError,OSError,UnicodeError)):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),meeting_source=binding,event_sink=sink)
    header.assert_not_called(); enrich.assert_not_called(); sink.assert_not_called()


@pytest.mark.parametrize('payload',[{}, {'events':None}, {'events':[['bad','蔡約翰',1]]}, {'events':[['2026-10-01','蔡約翰',True]]}, {'events':[['2026-10-01','蔡約翰',2]]}])
def test_bad_debut_events_reject_before_enrichment(tmp_path,monkeypatch,payload):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine.native_sources import JsonSource
    hk,path=case(tmp_path); source=tmp_path/'events.json'; source.write_text(json.dumps(payload))
    header=Mock(side_effect=AssertionError('header before validation')); monkeypatch.setattr(auto,'_align_runner_headers',header)
    with pytest.raises((ValueError,TypeError)):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),debut_source=JsonSource(source,hashlib.sha256(source.read_bytes()).hexdigest()))
    header.assert_not_called()


def test_absent_debut_is_explicit_empty_and_never_reads_hot(tmp_path,monkeypatch):
    from hkjc_racing_engine import debut_trainer as native
    from hkjc_racing_engine.native_sources import JsonSource
    def forbidden(*args,**kwargs): raise AssertionError('HOT debut events read')
    monkeypatch.setattr(native,'load_events',forbidden)
    events,proof=native.prepare_bound_events(JsonSource(tmp_path/'absent.json',None))
    assert events==[] and proof['sha256'] is None
    assert native.rate('蔡約翰','2026-11-08',events=events) is None


def test_strict_tag_errors_propagate_while_default_display_degrades(monkeypatch):
    from hkjc_racing_engine import tags
    def broken(*args,**kwargs): raise ValueError('tag failure')
    monkeypatch.setattr(tags,'_race_meta',broken)
    assert tags.race_tags({})=={'_error':'ValueError: tag failure'}
    with pytest.raises(ValueError,match='tag failure'): tags.race_tags({},debut_events=[])


@pytest.mark.parametrize('number',[0,'00'])
def test_zero_race_identity_rejects_before_inventory(tmp_path,monkeypatch,number):
    from hkjc_racing_engine import meeting_sources as source
    def forbidden(*args,**kwargs): raise AssertionError('inventory read for invalid race')
    monkeypatch.setattr(source,'_entries',forbidden)
    with pytest.raises(ValueError,match='race number'):
        source.observe_catalog_sha256(tmp_path/f'Race_{number}_Logic.json',number)


@pytest.mark.parametrize('change',['rewrite','replace','added_file'])
def test_meeting_mutation_during_capture_rejects_before_context(tmp_path,monkeypatch,change):
    from hkjc_racing_engine import meeting_sources as source
    hk,path=case(tmp_path); target=path.parent/'Synthetic Race 1 Facts.md'; target.write_text(facts('A'))
    original=source.capture_source_file
    def capture(file,*,maximum_bytes=None):
        held=original(file,maximum_bytes=maximum_bytes)
        if file.name.endswith('賽績.md'):
            if change=='rewrite': target.write_text(facts('B'))
            elif change=='replace':
                info=target.stat(); staged=target.parent/'staged'
                staged.write_bytes(target.read_bytes()); os.utime(staged,ns=(info.st_atime_ns,info.st_mtime_ns)); os.replace(staged,target)
            else: (target.parent/'Competing Race 1 Facts.md').write_text(facts('A'))
        return held
    monkeypatch.setattr(source,'capture_source_file',capture)
    with pytest.raises(ValueError,match='changed'): source.observe_catalog_sha256(path,1)


def test_meeting_remaining_budget_precedes_second_payload_read(tmp_path,monkeypatch):
    from hkjc_racing_engine import meeting_sources as source
    hk,path=case(tmp_path); target=path.parent/'Synthetic Race 1 Facts.md'; target.write_text(facts('A'))
    original=source.capture_source_file; calls=[]
    def capture(file,*,maximum_bytes=None):
        calls.append((file,maximum_bytes)); return original(file,maximum_bytes=maximum_bytes)
    monkeypatch.setattr(source,'capture_source_file',capture); monkeypatch.setattr(source,'MAX_CATALOG_BYTES',target.stat().st_size+1)
    with pytest.raises(ValueError,match='bounded regular'): source.observe_catalog_sha256(path,1)
    assert len(calls)==2 and calls[1][1]==1


def test_meeting_declared_absence_rejects_root_appearance(tmp_path,monkeypatch):
    from hkjc_racing_engine import meeting_sources as source
    root=tmp_path/'absent'; path=root/'Race_1_Logic.json'; original=source._capture
    def appeared(*args): root.mkdir(); return original(*args)
    monkeypatch.setattr(source,'_capture',appeared)
    with pytest.raises(ValueError,match='absent.*appeared'):
        source.prepare_bound_meeting(source.MeetingSource(root,None),path,1)


def test_native_priority_pattern_is_distinct_from_core_racecard(tmp_path):
    from hkjc_racing_engine import meeting_sources as source,tags
    hk,path=case(tmp_path)
    text=display_files('A')['Synthetic Race 1 排位表.md']
    (path.parent/'Race 1 排位表.md').write_text(text)  # No prefix space.
    context,_=source.prepare_bound_meeting(source.MeetingSource(path.parent,source.observe_catalog_sha256(path,1)),path,1)
    assert context.text('racecard')==text and context.text('priority') is None
    assert tags.load_priorities(path.parent,1)==tags.load_priorities(path.parent,1,meeting_context=context)=={}
