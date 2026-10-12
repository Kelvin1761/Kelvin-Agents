import hashlib
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from au_unused_field_intake import inventory, fit_speed_standards
from au_unused_field_power import _speed_standards, _speed_figure
CUTOFF='2026-08-15T12:00:00+10:00'

def asset(path, lines, available='2026-08-14T09:00:00+10:00'):
    path.write_text('\n'.join(lines))
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'available_at':available,'audit':'PASS'}

def lines(sec=60,track='Track'):
    return [f'{track} R1 2026-08-{day:02d} 1200m cond:Good WinningTime:{sec}' for day in range(1,11)]

def test_prior_unique_events_build_reference(tmp_path):
    state=fit_speed_standards([asset(tmp_path/'form.md',lines())],CUTOFF)
    assert state['standard']=={('track',1200):60}
    assert state['unique_events']==10

def test_repeated_event_not_ten_independent_samples(tmp_path):
    state=fit_speed_standards([asset(tmp_path/'form.md',[lines()[0]]*20)],CUTOFF)
    assert state['standard']=={} and state['unique_events']==1

def test_same_day_future_runs_and_future_capture_not_consumed(tmp_path):
    a=asset(tmp_path/'past.md',lines()+['Track R1 2026-08-15 1200m cond:Good WinningTime:99'])
    b={'path':str(tmp_path/'must-not-open.md'),'sha256':'not-read','audit':'PASS','available_at':'2026-08-15T13:00:00+10:00'}
    state=fit_speed_standards([a,b],CUTOFF)
    assert state['standard']=={('track',1200):60} and state['unique_events']==10
    assert state['flags'][0]['reason']=='source_not_before_cutoff'

def test_changed_hash_rejected(tmp_path):
    a=asset(tmp_path/'form.md',lines());Path(a['path']).write_text('changed')
    with pytest.raises(ValueError,match='hash changed'):fit_speed_standards([a],CUTOFF)

def test_timezone_required(tmp_path):
    a=asset(tmp_path/'form.md',lines())
    with pytest.raises(ValueError,match='timezone'):fit_speed_standards([a],'2026-08-15T12:00:00')

def test_roots_and_cutoffs_have_no_shared_global_cache(tmp_path):
    a=asset(tmp_path/'a.md',lines(60));b=asset(tmp_path/'b.md',lines(80))
    assert _speed_standards(CUTOFF,[a])[0][('track',1200)]==60
    assert _speed_standards(CUTOFF,[b])[0][('track',1200)]==80
    assert _speed_standards('2026-08-10T12:00:00+10:00',[a])[0]=={}
    assert _speed_standards()==({}, {})

def test_conflicting_event_not_arbitrarily_selected(tmp_path):
    a=asset(tmp_path/'a.md',lines()+[lines()[0].replace('Time:60','Time:80')])
    state=fit_speed_standards([a],CUTOFF)
    assert state['standard']=={} and state['flags'][0]['reason']=='conflicting_event_time_or_going'

def test_inventory_archive_per_race_scores_without_depth_sidecar(tmp_path):
    m=tmp_path/'Archive/2026-08-05 Track Race 1-2';m.mkdir(parents=True)
    (m/'Race_1_Auto_Scoring.csv').write_text('header')
    (m/'Race_1_Logic.json').write_text('{}')
    (m/'Race 1 Formguide.md').write_text('[1] Alpha (2)\nTrack R1 2026-08-01 1200m cond:Good\n')
    data=inventory(tmp_path)
    assert data['counts']=={'meetings':1,'archived':1,'with_formguides':1,'with_any_scoring':1}
    assert data['meetings'][0]['observed_mean_form_depth']==1

def test_duplicate_meeting_fails_instead_of_selecting_backup(tmp_path):
    (tmp_path/'2026-08-05 Track').mkdir();(tmp_path/'Archive/2026-08-05 Track').mkdir(parents=True)
    with pytest.raises(ValueError,match='duplicate meeting'):inventory(tmp_path)

def test_speed_requires_matching_cutoff_and_prior_run(tmp_path):
    state=fit_speed_standards([asset(tmp_path/'a.md',lines())],CUTOFF)
    run={'track':'Track','dist':1200,'wt_sec':60,'margin':0,'cond':'Good','date':'2026-08-01'}
    assert _speed_figure(run,state,CUTOFF)==0
    assert _speed_figure(dict(run,date='2026-08-15'),state,CUTOFF) is None
    with pytest.raises(ValueError,match='cutoff'): _speed_figure(run,state,'2026-08-16T12:00:00+10:00')
