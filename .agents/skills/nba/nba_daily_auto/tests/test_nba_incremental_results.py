"""The existing postgame job polls Final results without prematurely archiving."""
from types import SimpleNamespace
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nba_daily_schedule as schedule


class Log:
    def __init__(self):self.rows=[]
    def step(self,*args,**kw):self.rows.append((args,kw))


def setup(monkeypatch,tmp_path,appended):
    monkeypatch.setattr(schedule,'live_dir',lambda day:tmp_path)
    monkeypatch.setattr(schedule,'latest_snapshot',lambda folder:tmp_path/'snapshot')
    monkeypatch.setattr(schedule.no_prediction,'covers_date',lambda folder:False)
    monkeypatch.setattr(schedule,'STATE_DIR',tmp_path/'state')
    monkeypatch.setattr(schedule,'results_due',lambda *a,**kw:['BOS_NYK'])
    (tmp_path/'Sportsbet_Odds_BOS_NYK.json').write_text('{"event_start_time":"2026-10-25T00:00:00+00:00"}')
    monkeypatch.setattr(schedule,'_run',lambda command,**kw:SimpleNamespace(returncode=0))
    brief=tmp_path/'Results_Brief_2026-10-24.json';brief.write_text('{}')
    monkeypatch.setattr(schedule.market_ledger,'ledger_root',lambda:tmp_path)
    monkeypatch.setattr(schedule.market_ledger,'settle',lambda *a,**kw:{'appended':appended,'candidates':2})
    deploy=[]
    monkeypatch.setattr(schedule,'_deploy',lambda *a:deploy.append(a) or 'ok')
    return deploy


def test_final_outcomes_update_dashboard_without_archiving(monkeypatch,tmp_path):
    deployed=setup(monkeypatch,tmp_path,2)
    assert schedule.run_results_refresh('2026-10-25',Log())=='updated'
    assert len(deployed)==1 and tmp_path.exists()


def test_repeated_or_unfinished_results_do_not_deploy(monkeypatch,tmp_path):
    deployed=setup(monkeypatch,tmp_path,0)
    assert schedule.run_results_refresh('2026-10-25',Log())=='unchanged'
    assert deployed==[]


def test_no_snapshot_is_dormant(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path,2)
    monkeypatch.setattr(schedule,'latest_snapshot',lambda folder:None)
    assert schedule.run_results_refresh('2026-10-25',Log())=='dormant'


def test_existing_job_has_bounded_results_slots():
    import plistlib
    root=Path(schedule.__file__).parent
    data=plistlib.loads((root/'launchd/com.antigravity.nba-wong-choi.postgame.plist.template').read_bytes())
    assert '--incremental-results' in data['ProgramArguments']
    assert data['StartInterval']==900
    assert len(data['StartCalendarInterval'])==2
    assert {'Hour':21,'Minute':30} in data['StartCalendarInterval']



def test_source_timing_waits_until_tip_plus_150_minutes_and_cools_down(tmp_path):
    from datetime import datetime,timedelta,timezone
    tip=datetime(2026,10,25,0,tzinfo=timezone.utc)
    (tmp_path/'Sportsbet_Odds_BOS_NYK.json').write_text('{"event_start_time":"2026-10-25T00:00:00+00:00"}')
    row={'row_type':'model_obs','target_date':'2026-10-25','game_tag':'BOS_NYK','snapshot_role':'production','player':'Player','market':'pts','line':20}
    assert schedule.results_due(tmp_path,'2026-10-25',tip+timedelta(minutes=149),rows=[row])==[]
    assert schedule.results_due(tmp_path,'2026-10-25',tip+timedelta(minutes=150),rows=[row])==['BOS_NYK']
    attempts={'BOS_NYK:'+tip.isoformat():(tip+timedelta(minutes=150)).isoformat()}
    assert schedule.results_due(tmp_path,'2026-10-25',tip+timedelta(minutes=164),rows=[row],attempts=attempts)==[]
    assert schedule.results_due(tmp_path,'2026-10-25',tip+timedelta(minutes=165),rows=[row],attempts=attempts)==['BOS_NYK']
    settled={**row,'row_type':'settlement','outcome':'hit'}
    assert schedule.results_due(tmp_path,'2026-10-25',tip+timedelta(minutes=165),rows=[row,settled])==[]
    assert schedule.results_due(tmp_path,'2026-10-25',tip+timedelta(hours=9),rows=[row])==[]


def test_missing_source_time_warmup_and_no_prediction_never_trigger_fetch(tmp_path):
    from datetime import datetime,timezone
    now=datetime(2026,10,25,3,tzinfo=timezone.utc)
    odds=tmp_path/'Sportsbet_Odds_BOS_NYK.json';odds.write_text('{}')
    row={'row_type':'model_obs','target_date':'2026-10-25','game_tag':'BOS_NYK','snapshot_role':'production','player':'Player','market':'pts','line':20}
    assert schedule.results_due(tmp_path,'2026-10-25',now,rows=[row])==[]
    odds.write_text('{"event_start_time":"2026-10-25T00:00:00+00:00"}')
    assert schedule.results_due(tmp_path,'2026-10-25',now,rows=[{**row,'snapshot_role':'warmup'}])==[]
    assert schedule.results_due(tmp_path,'2026-10-25',now,rows=[row,{'row_type':'no_prediction','target_date':'2026-10-25','game_tag':'BOS_NYK'}])==[]



def test_installer_rejects_fast_timer_and_missing_incremental_guard(tmp_path):
    import plistlib
    import pytest
    from verify_results_timer import verify
    path=tmp_path/'job.plist'
    template=Path(schedule.__file__).parent/'launchd/com.antigravity.nba-wong-choi.postgame.plist.template'
    data=plistlib.loads(template.read_bytes())
    path.write_bytes(plistlib.dumps(data));verify(path)
    data['StartInterval']=30;path.write_bytes(plistlib.dumps(data))
    with pytest.raises(ValueError,match='900'):verify(path)
    data['StartInterval']=900;data['ProgramArguments'].remove('--incremental-results')
    path.write_bytes(plistlib.dumps(data))
    with pytest.raises(ValueError,match='incremental'):verify(path)
