"""Only documented validator warnings are successful; errors stay blocking."""
import sys
from pathlib import Path
import pytest

NBA=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(NBA))
import nba_orchestrator as o


@pytest.mark.parametrize('code,allowed,expected',[(0,(0,),True),(2,(0,),False),(2,(0,2),True),(1,(0,2),False),(75,(0,2),False)])
def test_script_status_contract(tmp_path,code,allowed,expected):
    script=tmp_path/'command.py';script.write_text(f'print("diagnostic")\nraise SystemExit({code})\n')
    failures=[]
    assert o.run_script(str(script),[],success_codes=allowed,failure_codes=failures) is expected
    assert failures==([] if expected else [code])


def test_compile_validator_explicitly_accepts_warning_status(tmp_path,monkeypatch):
    (tmp_path/'Game_BOS_LAL_Full_Analysis.md').write_text('complete report')
    calls=[]
    monkeypatch.setattr(o,'run_script',lambda script,args,**kwargs:calls.append((script,kwargs)) or True)
    assert o.validate_reports_for_release(str(tmp_path))
    assert calls==[(o.VALIDATE_OUTPUT,{'label':'Compile Release Validator','success_codes':(0,2)})]


def test_selected_release_ignores_unrelated_started_or_unfinished_report(tmp_path,monkeypatch):
    selected=tmp_path/'Game_BKN_CLE_Full_Analysis.md';selected.write_text('complete report')
    old=tmp_path/'Game_BOS_LAL_Full_Analysis.md';old.write_text('[FILL] already started')
    calls=[]
    monkeypatch.setattr(o,'run_script',lambda script,args,**kwargs:calls.append(args) or True)
    assert o.validate_reports_for_release(str(tmp_path),['BKN_CLE'])
    assert calls==[[str(selected)]]
    assert o._count_fill_residuals(str(tmp_path),['BKN_CLE'])==0
    assert o._count_fill_residuals(str(tmp_path))==1
    assert old.read_text()=='[FILL] already started'
    assert not o.validate_reports_for_release(str(tmp_path),['MIA_CHA'])


def test_master_compile_respects_explicit_game_scope(tmp_path):
    import subprocess
    (tmp_path/'Game_BKN_CLE_Full_Analysis.md').write_text('# BKN @ CLE\n')
    (tmp_path/'Game_BOS_LAL_Full_Analysis.md').write_text('# stale game\nUNRELATED_STALE_REPORT')
    result=subprocess.run([sys.executable,o.GENERATE_SGM,'--dir',str(tmp_path),'--games','BKN_CLE'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert 'UNRELATED_STALE_REPORT' not in (tmp_path/'NBA_All_SGM_Report.txt').read_text()
    assert 'Game_BOS_LAL_Full_Analysis.md' not in result.stdout
    assert '已報價 SGM: 0 個' in result.stdout


@pytest.mark.parametrize('compile_code',[0,1])
def test_scheduler_recompiles_successful_refresh_union_without_started_games(tmp_path,monkeypatch,compile_code):
    import subprocess
    sys.path.insert(0,str(NBA/'nba_daily_auto'))
    import nba_daily_schedule as schedule
    calls=[]
    def run(command):
        calls.append(command)
        return subprocess.CompletedProcess(command,compile_code if '--compile-only' in command else 0,'','')
    monkeypatch.setattr(schedule,'_run',run)
    class Log:
        def step(self,*args,**kwargs):pass
    if compile_code:
        with pytest.raises(schedule.TemporaryFailure,match='compile_refreshed_games_exit_1'):
            schedule._run_orchestrator_refresh('2026-10-25',tmp_path,refreshable_tags={'BKN_CLE','GSW_PHX'},schedule_tags={'BKN_CLE','GSW_PHX','BOS_LAL'},log=Log())
    else:
        schedule._run_orchestrator_refresh('2026-10-25',tmp_path,refreshable_tags={'BKN_CLE','GSW_PHX'},schedule_tags={'BKN_CLE','GSW_PHX','BOS_LAL'},log=Log())
    assert len(calls)==3
    assert calls[-1][-5:]==['--compile-only','--games','BKN_CLE','GSW_PHX','--skip-cloudflare-deploy']
    assert all('BOS_LAL' not in command for command in calls)
