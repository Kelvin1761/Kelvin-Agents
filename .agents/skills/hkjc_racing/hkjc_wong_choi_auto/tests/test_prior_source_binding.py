"""Native per-call prior isolation, synthetic inputs; never PIT authority."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from test_sectional_source_binding import ROOT, case


def prior_files(version):
    high, low = ((60, 5) if version == 'A' else (5, 60))
    high_place, low_place = ((80, 20) if version == 'A' else (20, 80))
    out = {}
    for group, names in [('jockey', ('潘頓', '普通騎師')), ('trainer', ('蔡約翰', '普通練馬師'))]:
        column = group.title()
        out[f'26_27/{group}_master_stats.csv'] = f'{column},Wins,Starts,Places\n{names[0]},{high},100,{high_place}\n{names[1]},{low},100,{low_place}\n'
    out['26_27/general_pre_race_priors/jockey_trainer_combo_priors.csv'] = f'Jockey,Trainer,Wins,Starts,Places\n潘頓,蔡約翰,{high},100,{high_place}\n普通騎師,普通練馬師,{low},100,{low_place}\n'
    for group, names in [('jockey', ('潘頓', '普通騎師')), ('trainer', ('蔡約翰', '普通練馬師'))]:
        out[f'26_27/{group}_distance_stats.csv'] = f'{group.title()},Distance,Wins,Starts,Places\n{names[0]},1200,{high},100,{high_place}\n{names[1]},1200,{low},100,{low_place}\n'
    out['26_27/general_pre_race_priors/jockey_change_priors.csv'] = f'JockeyChanged,Wins,Starts,Places\nTrue,{high},100,{high_place}\nFalse,{low},100,{low_place}\n'
    out['26_27/jockey_draw_performance.csv'] = 'Jockey,Draw,Wins,Starts,Places\n潘頓,2,1,10,3\n'
    out['experimental/trainer_recency_90d_stats.csv'] = f'Trainer,Wins,Starts,Places,AsOfDate,LatestResultDate,HalfLifeDays\n蔡約翰,{high},100,{high_place},2026-11-08,2026-11-07,30\n普通練馬師,{low},100,{low_place},2026-11-08,2026-11-07,30\n'
    return out


DRIVER = r'''
import contextlib, io, json, os, sys
from pathlib import Path
from datetime import date
repo, hk, logic_path, request, mode = sys.argv[1:]
sys.path[:0] = [repo, str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'), str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_race_extractor/scripts')]
import wongchoi_paths
wongchoi_paths.HK_RACING = Path(hk)
root = Path(hk)/'HKJC_Race_Results_Database/comprehensive_stats'
values = []
cache = None
for files in json.loads(Path(request).read_text()):
    for relative, content in files.items():
        target = root/relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content); os.utime(target, ns=(1700000000000000000,1700000000000000000))
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import live_priors as lp, engine_core as core
    lp.hk_today = lambda: date(2026,11,8)  # Synthetic clock only, no source gets PIT mode.
    auto._get_profile_scraper = lambda: None
    logic = json.loads(Path(logic_path).read_text())
    kwargs = {}
    if mode == 'bound':
        if not values:
            lp.get_jt_ratings('2026-11-08')
            lp.get_recency_trainer_rating('蔡約翰', as_of_date='2026-11-08')
            core._TRAINER_SIGNAL_PRIORS = lp.TrainerSignalPriors()
            lp.prior_source_manifest()
            cache = (lp._JT_RATINGS, lp._RECENCY_TRAINER_RATINGS, core._TRAINER_SIGNAL_PRIORS, lp._PRIOR_SOURCE_MANIFEST)
        from hkjc_racing_engine.prior_sources import PriorSource, observe_catalog_sha256
        kwargs['prior_source'] = PriorSource(root, observe_catalog_sha256(root))
    with contextlib.redirect_stdout(io.StringIO()):
        result = auto.HKJCAutoOrchestrator(Path(logic_path), shadow_profile="trainer_recency_st_early90").score_logic_data(Path(logic_path), logic, **kwargs)
    if mode == 'bound':
        proof = result['python_auto_run_contract'].pop('bound_prior_source')
        assert proof['catalog_sha256'] == kwargs['prior_source'].sha256
        assert proof['catalog']['files']['experimental/trainer_recency_90d_stats.csv']['sha256']
    else:
        assert 'bound_prior_source' not in result['python_auto_run_contract']
    values.append(result)
if cache:
    assert all(a is b for a,b in zip(cache,(lp._JT_RATINGS,lp._RECENCY_TRAINER_RATINGS,core._TRAINER_SIGNAL_PRIORS,lp._PRIOR_SOURCE_MANIFEST)))
assert json.loads(Path(logic_path).read_text()) == logic
print(json.dumps(values, ensure_ascii=False, allow_nan=False))
'''


def run_priors(tmp_path, hk, path, versions, mode='default'):
    request = tmp_path/'priors-sequence.json'
    request.write_text(json.dumps([prior_files(v) if isinstance(v,str) else v for v in versions]))
    result = subprocess.run([sys.executable,'-B','-c',DRIVER,str(ROOT),str(hk),str(path),str(request),mode], cwd=tmp_path,
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_actual_default_prior_cache_does_not_reobserve_b(tmp_path):
    hk, path = case(tmp_path)
    a = run_priors(tmp_path,hk,path,['A'])[0]
    b = run_priors(tmp_path,hk,path,['B'])[0]
    assert a != b
    assert a['horses']['1']['python_auto']['ability_score_raw'] != b['horses']['1']['python_auto']['ability_score_raw']
    assert run_priors(tmp_path,hk,path,['A','B']) == [a,a]


def test_bound_priors_a_b_a_match_complete_fresh_native_output(tmp_path):
    hk, path = case(tmp_path)
    a = run_priors(tmp_path,hk,path,['A'])[0]
    b = run_priors(tmp_path,hk,path,['B'])[0]
    assert a != b
    assert run_priors(tmp_path,hk,path,['A','B','A'],'bound') == [a,b,a]


def write_priors(root, version='A'):
    for relative, content in prior_files(version).items():
        path = root/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content)


@pytest.mark.parametrize('role', ['master','signal','recency'])
def test_each_native_prior_consumer_changes_and_matches_fresh_output(tmp_path, role):
    hk, path = case(tmp_path)
    a, changed = prior_files('A'), prior_files('A')
    for relative, content in prior_files('B').items():
        selected = ('master_stats' in relative if role == 'master' else
                    relative.startswith('experimental/') if role == 'recency' else
                    'master_stats' not in relative and not relative.startswith('experimental/'))
        if selected: changed[relative] = content
    reference_a = run_priors(tmp_path,hk,path,[a])[0]
    reference_b = run_priors(tmp_path,hk,path,[changed])[0]
    auto_a = reference_a['horses']['1']['python_auto']
    auto_b = reference_b['horses']['1']['python_auto']
    if role == 'recency':
        shadow_a = auto_a['shadow_profiles']['trainer_recency_st_early90']
        shadow_b = auto_b['shadow_profiles']['trainer_recency_st_early90']
        assert shadow_a['applied'] and shadow_b['applied']
        assert shadow_a['recency_source']['score'] != shadow_b['recency_source']['score']
        assert shadow_a['ability_score'] != shadow_b['ability_score']
    else:
        assert auto_a['feature_scores'] != auto_b['feature_scores']
    assert run_priors(tmp_path,hk,path,[a,changed,a],'bound') == [reference_a,reference_b,reference_a]


@pytest.mark.parametrize('fault', ['season_added','season_removed','source_changed','source_removed','source_appeared',
                                  'malformed','missing_columns','linked','unreadable','bad_hash','untyped','byte_bound'])
def test_prior_failures_reject_before_any_native_enrichment(tmp_path, monkeypatch, fault):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import prior_sources as sources
    hk, path = case(tmp_path)
    root = hk/'HKJC_Race_Results_Database/comprehensive_stats'; write_priors(root)
    binding = sources.PriorSource(root, sources.observe_catalog_sha256(root))
    target = root/'26_27/jockey_master_stats.csv'
    if fault == 'season_added': (root/'27_28').mkdir()
    elif fault == 'season_removed': (root/'26_27').rename(root/'old-season')
    elif fault == 'source_changed': target.write_text(target.read_text().replace('60','61'))
    elif fault == 'source_removed': target.unlink()
    elif fault == 'source_appeared': (root/'26_27/extra.csv').write_text('x\n1\n')
    elif fault == 'malformed': target.write_text('"unterminated')
    elif fault == 'missing_columns': target.write_text('Wrong\n1\n')
    elif fault == 'linked': target.unlink(); target.symlink_to(root/'26_27/trainer_master_stats.csv')
    elif fault == 'unreadable': monkeypatch.setattr(sources,'is_materialized_file',lambda path: False)
    elif fault == 'bad_hash': binding = sources.PriorSource(root,'0'*64)
    elif fault == 'untyped': binding = {'root':str(root),'sha256':binding.sha256}
    elif fault == 'byte_bound': monkeypatch.setattr(sources,'MAX_CATALOG_BYTES',1)
    enrich = Mock(side_effect=AssertionError('enrichment ran before resource validation'))
    monkeypatch.setattr(auto,'_enrich_profile_history',enrich)
    with pytest.raises((ValueError,OSError,UnicodeError)):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path,json.loads(path.read_text()),prior_source=binding)
    enrich.assert_not_called()


def test_bound_prior_temporal_modes_and_live_tripwire_are_preserved(tmp_path, monkeypatch):
    from datetime import date
    from hkjc_racing_engine import live_priors as lp, prior_sources as sources
    root = tmp_path/'stats'; write_priors(root)
    monkeypatch.setattr(lp,'hk_today',lambda: date(2026,11,9))
    context = sources.prepare_bound_priors(sources.PriorSource(root,sources.observe_catalog_sha256(root)))
    assert context.recency.as_of_date == '2026-11-08'
    for source in [context.ratings,context.signals,context.recency]:
        assert source.temporal_mode in {'latest_season_snapshot','latest_recency_snapshot'}
        assert not lp.temporal_source_is_safe(source,'2026-11-08')
        assert not lp.temporal_source_is_safe(source,None)
        assert lp.temporal_source_is_safe(source,'2026-11-09')
    assert lp.get_jt_ratings('2026-11-08',prior_context=context).lookup('jockey','潘頓') is None
    assert lp.get_recency_trainer_rating('蔡約翰',as_of_date='2026-11-08',prior_context=context) is None
    monkeypatch.setenv(lp.LIVE_CARD_ENV,'1')
    with pytest.raises(lp.LiveCardDateMismatch): lp.get_jt_ratings('2026-11-08',prior_context=context)


def test_explicit_lookup_errors_do_not_degrade_to_tier_fallback(monkeypatch):
    from hkjc_racing_engine import live_priors as lp
    from hkjc_racing_engine.features.jockey import continuous_rating
    def broken(*args,**kwargs): raise ValueError('broken held context')
    monkeypatch.setattr(lp,'get_jt_ratings',broken)
    assert continuous_rating('jockey','潘頓',as_of_date='2026-11-08') is None
    with pytest.raises(ValueError,match='broken held'): continuous_rating('jockey','潘頓',as_of_date='2026-11-08',prior_context=object())


def test_absent_root_and_fallback_are_explicit_and_do_not_read_defaults(tmp_path):
    from hkjc_racing_engine import prior_sources as sources
    root = tmp_path/'absent'
    context = sources.prepare_bound_priors(sources.PriorSource(root,None))
    assert context.ratings.jockey == context.signals.combo == context.recency.trainer == {}
    assert len(context.manifest()) == 14
    assert all(row['materialized'] is False for row in context.manifest())
    root.mkdir()
    with pytest.raises(ValueError,match='absent'): sources.prepare_bound_priors(sources.PriorSource(root,None))


def test_catalog_remaining_budget_is_checked_before_second_payload_read(tmp_path, monkeypatch):
    from hkjc_racing_engine import prior_sources as sources
    root = tmp_path/'stats'; write_priors(root)
    original = sources.capture_source_file
    calls=[]
    def capture(path, *, maximum_bytes=None):
        calls.append((path,maximum_bytes))
        return original(path,maximum_bytes=maximum_bytes)
    monkeypatch.setattr(sources,'capture_source_file',capture)
    monkeypatch.setattr(sources,'MAX_CATALOG_BYTES',len((root/'26_27/general_pre_race_priors/jockey_change_priors.csv').read_bytes())+1)
    with pytest.raises(ValueError,match='bounded regular|bound exhausted'): sources.observe_catalog_sha256(root)
    assert len(calls) == 2 and calls[1][1] == 1


def test_declared_absent_root_cannot_adopt_appearance_during_capture(tmp_path, monkeypatch):
    from hkjc_racing_engine import prior_sources as sources
    root = tmp_path/'absent'
    original = sources._capture
    def appeared(path):
        write_priors(root)
        return original(path)
    monkeypatch.setattr(sources,'_capture',appeared)
    with pytest.raises(ValueError,match='absent.*appeared'):
        sources.prepare_bound_priors(sources.PriorSource(root,None))


def test_strict_run_contract_identifies_raw_recency_and_season_binding(tmp_path):
    from hkjc_racing_engine import prior_sources as sources
    from hkjc_racing_engine.engine_core import scoring_run_contract
    root = tmp_path/'stats'; write_priors(root)
    digest = sources.observe_catalog_sha256(root)
    context = sources.prepare_bound_priors(sources.PriorSource(root,digest))
    evidence = scoring_run_contract(prior_context=context)['bound_prior_source']
    assert evidence['catalog_sha256'] == digest
    assert evidence['catalog']['current_tag']
    assert len(evidence['catalog']['files'][sources.RECENCY]['sha256']) == 64
    assert evidence['catalog']['files'][sources.RECENCY]['size'] > 0


@pytest.mark.parametrize('change',['rewrite','replace','absent_appears'])
def test_selected_file_change_during_capture_rejects_before_context(tmp_path,monkeypatch,change):
    from hkjc_racing_engine import prior_sources as sources
    root=tmp_path/'stats'; write_priors(root)
    target=root/'26_27/general_pre_race_priors/jockey_change_priors.csv'
    missing=root/'26_27/jockey_draw_performance.csv'
    if change == 'absent_appears': missing.unlink()
    original=sources.capture_source_file
    def capture(path,*,maximum_bytes=None):
        held=original(path,maximum_bytes=maximum_bytes)
        if path == root/sources.RECENCY:
            if change == 'rewrite': target.write_text(target.read_text().replace('60','61'))
            elif change == 'replace':
                info=target.stat(); replacement=target.parent/'replacement'
                replacement.write_bytes(target.read_bytes()); os.utime(replacement,ns=(info.st_atime_ns,info.st_mtime_ns)); os.replace(replacement,target)
            else: missing.write_text(prior_files('A')['26_27/jockey_draw_performance.csv'])
        return held
    monkeypatch.setattr(sources,'capture_source_file',capture)
    with pytest.raises(ValueError,match='changed|inventory'):
        sources.observe_catalog_sha256(root)


def test_held_csv_consumers_receive_fresh_frames_and_manifest_copies(tmp_path):
    from hkjc_racing_engine import prior_sources as sources
    root=tmp_path/'stats'; write_priors(root)
    captured=sources._capture(root)
    context=sources.PriorContext(captured)
    again=sources.PriorContext(captured)
    assert context.ratings.jockey == again.ratings.jockey
    assert context.signals.jockey_distance == again.signals.jockey_distance
    evidence=context.evidence(); evidence['catalog']['files'].clear()
    manifest=context.manifest(); manifest[0]['size']=-1
    assert context.evidence()['catalog']['files']
    assert context.manifest()[0]['size'] >= 0


def test_legacy_direct_jockey_change_helper_keeps_default_reader(tmp_path,monkeypatch):
    from hkjc_racing_engine import live_priors as lp
    path=tmp_path/'change.csv'
    path.write_text(prior_files('A')['26_27/general_pre_race_priors/jockey_change_priors.csv'])
    monkeypatch.setattr(lp,'GENERAL_PRIOR_FILES',{'jockey_change':[path]})
    obj=lp.TrainerSignalPriors.__new__(lp.TrainerSignalPriors)
    result=obj._load_jockey_change()
    assert result[True]['wins'] == 60 and result[False]['wins'] == 5
