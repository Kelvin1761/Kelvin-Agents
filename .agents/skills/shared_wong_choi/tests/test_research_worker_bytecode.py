"""Actual research subprocesses must run pinned source, not timestamp-valid pyc."""
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.research_runner import CommandInvocation,SubprocessResearchExecutor,_git_checkout_probe


def stale_checkout(tmp_path):
    checkout=tmp_path/'checkout'; checkout.mkdir()
    source=checkout/'scoring_fixture.py'; old=b'VALUE = 11\n'; new=b'VALUE = 22\n'
    assert len(old)==len(new)
    source.write_bytes(old); os.utime(source,(1700000000,1700000000))
    cache=tmp_path/'old-bytecode'; cache.mkdir()
    compiled=subprocess.run([sys.executable,'-X',f'pycache_prefix={cache}','-c',
        'import py_compile,sys;py_compile.compile(sys.argv[1],doraise=True)',str(source)],capture_output=True,text=True)
    assert compiled.returncode==0,compiled.stderr
    assert list(cache.rglob('scoring_fixture*.pyc'))
    source.write_bytes(new); os.utime(source,(1700000000,1700000000))
    for args in [('init','--quiet'),('add','scoring_fixture.py'),('commit','--quiet','-m','fixture source B')]:
        subprocess.run(['git','-C',str(checkout),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',*args],check=True,capture_output=True)
    commit=_git_checkout_probe(checkout)
    assert len(commit)==40 and source.read_bytes()==new
    return checkout,cache,commit


def test_real_research_executor_ignores_stale_bytecode_after_clean_sha_probe(tmp_path):
    checkout,old_cache,commit=stale_checkout(tmp_path)
    output=tmp_path/'output'; output.mkdir()
    invocation=CommandInvocation('baseline',0,(sys.executable,'-c','import scoring_fixture;print(scoring_fixture.VALUE)'),
        checkout,{'PYTHONDONTWRITEBYTECODE':'1','PYTHONPYCACHEPREFIX':str(old_cache)},output,output/'metrics.json')
    result=SubprocessResearchExecutor(poll_seconds=.01,terminate_grace=.1).run(invocation,timeout_seconds=10,production_active=lambda:False)
    assert result.returncode==0,result.stderr
    assert _git_checkout_probe(checkout)==commit
    assert result.stdout.strip()=='22'


def cache_files(root):
    import hashlib
    return {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob('*.pyc')}


def test_real_inherited_group_executor_uses_new_source_and_retains_old_cache(tmp_path):
    import json
    checkout,old_cache,commit=stale_checkout(tmp_path)
    before=cache_files(old_cache); output=tmp_path/'output'; output.mkdir()
    package=Path(__file__).resolve().parents[2]
    driver='''import json,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom shared_wong_choi.research_runner import CommandInvocation\nfrom shared_wong_choi.research_supervision import _InheritedGroupExecutor\ncheckout,cache,output=map(Path,sys.argv[2:])\ni=CommandInvocation('baseline',0,(sys.executable,'-c','import scoring_fixture;print(scoring_fixture.VALUE)'),checkout,{'PYTHONDONTWRITEBYTECODE':'1','PYTHONPYCACHEPREFIX':str(cache)},output,output/'metrics.json')\nr=_InheritedGroupExecutor(poll_seconds=.01,terminate_grace=.1).run(i,timeout_seconds=10,production_active=lambda:False)\nprint(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}))'''
    result=subprocess.run([sys.executable,'-B','-c',driver,str(package),str(checkout),str(old_cache),str(output)],
        start_new_session=True,capture_output=True,text=True,timeout=20,
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPYCACHEPREFIX':str(tmp_path/'outer-empty-cache')})
    assert result.returncode==0,result.stderr
    response=json.loads(result.stdout)
    assert response['returncode']==0 and response['stdout'].strip()=='22',response
    assert cache_files(old_cache)==before and _git_checkout_probe(checkout)==commit


def test_each_spawn_gets_new_private_prefix_over_inherited_and_invocation_values(tmp_path,monkeypatch):
    import json,stat
    monkeypatch.setenv('PYTHONPYCACHEPREFIX',str(tmp_path/'inherited-old'))
    monkeypatch.setenv('PYTHONDONTWRITEBYTECODE','0')
    output=tmp_path/'output'; output.mkdir()
    code='import json,sys;print(json.dumps([sys.pycache_prefix,sys.dont_write_bytecode]))'
    invocation=CommandInvocation('test',0,(sys.executable,'-c',code),tmp_path,
        {'PYTHONPYCACHEPREFIX':str(tmp_path/'requested-old'),'PYTHONDONTWRITEBYTECODE':'0','SECRET_FAKE_VALUE':'must-not-be-recorded'},output,output/'metrics.json')
    executor=SubprocessResearchExecutor(poll_seconds=.01,terminate_grace=.1)
    runs=[executor.run(invocation,timeout_seconds=10,production_active=lambda:False) for _ in range(2)]
    values=[json.loads(run.stdout) for run in runs]
    assert values[0][0]!=values[1][0]
    for prefix,disabled in values:
        assert disabled is True
        cache=Path(prefix); assert cache.parent.parent==output and not list(cache.iterdir())
        assert stat.S_IMODE(cache.stat().st_mode)==0o700
        policy=cache.parent/'policy.json'
        assert stat.S_IMODE(policy.stat().st_mode)==0o600
        data=json.loads(policy.read_text())
        assert data['pycache_prefix']==prefix and data['direct_python_options_checked'] is True
        assert 'SECRET_FAKE_VALUE' not in policy.read_text() and 'must-not-be-recorded' not in policy.read_text()
        assert len(data['argv_sha256'])==64


import pytest


@pytest.mark.parametrize('flags',[('-I',),('-E',),('-BEI',),('-X','pycache_prefix=/old'),('-Xpycache_prefix=/old',),('-BXpycache_prefix=',)])
def test_ignoring_or_overriding_interpreter_flags_block_before_spawn(tmp_path,monkeypatch,flags):
    from unittest.mock import Mock
    import shared_wong_choi.research_runner as runner
    popen=Mock(side_effect=AssertionError('unsafe interpreter was spawned'))
    monkeypatch.setattr(runner.subprocess,'Popen',popen)
    invocation=CommandInvocation('test',0,(sys.executable,*flags,'-c','pass'),tmp_path,{},tmp_path,tmp_path/'metrics.json')
    with pytest.raises(ValueError,match='Python options'):
        runner.SubprocessResearchExecutor()._spawn(invocation)
    popen.assert_not_called(); assert not list(tmp_path.glob('.python-bytecode-*'))


@pytest.mark.parametrize('argv',[
    ('-B','-c','print("-I")','-E'),('-m','module','-I'),('script.py','-E','-Xpycache_prefix=/old'),
    ('--','script.py','-I'),('-W','ignore','-X','utf8=1','-c','pass'),('-Bc','print("-E")'),
])
def test_script_arguments_and_unrelated_interpreter_options_are_not_rewritten(argv):
    from shared_wong_choi.research_runner import _direct_python_options
    assert _direct_python_options((sys.executable,*argv)) is True


def test_unsafe_output_path_or_allocation_failure_never_spawns(tmp_path,monkeypatch):
    from unittest.mock import Mock
    import shared_wong_choi.research_runner as runner
    target=tmp_path/'target'; target.mkdir(); alias=tmp_path/'alias'; alias.symlink_to(target,target_is_directory=True)
    invocation=CommandInvocation('test',0,(sys.executable,'-c','pass'),tmp_path,{},alias,alias/'metrics.json')
    popen=Mock(side_effect=AssertionError('unsafe output spawned')); monkeypatch.setattr(runner.subprocess,'Popen',popen)
    with pytest.raises(ValueError,match='ancestry'): runner.SubprocessResearchExecutor()._spawn(invocation)
    def failed(*args,**kwargs): raise OSError('synthetic allocation failure')
    monkeypatch.setattr(runner.tempfile,'mkdtemp',failed)
    from dataclasses import replace
    with pytest.raises(OSError,match='allocation'): runner.SubprocessResearchExecutor()._spawn(replace(invocation,output_dir=target))
    popen.assert_not_called()


def test_failed_spawn_retains_private_policy_evidence_without_touching_old_cache(tmp_path,monkeypatch):
    import json
    import shared_wong_choi.research_runner as runner
    checkout,cache,_=stale_checkout(tmp_path); before=cache_files(cache)
    output=tmp_path/'output'; output.mkdir()
    invocation=CommandInvocation('test',0,(sys.executable,'-c','pass'),checkout,{'PYTHONPYCACHEPREFIX':str(cache)},output,output/'metrics.json')
    def failed(*args,**kwargs): raise OSError('synthetic spawn failure')
    monkeypatch.setattr(runner.subprocess,'Popen',failed)
    with pytest.raises(OSError,match='spawn'): runner.SubprocessResearchExecutor()._spawn(invocation)
    policies=list(output.glob('.python-bytecode-*/policy.json'))
    assert len(policies)==1 and json.loads(policies[0].read_text())['dont_write_bytecode'] is True
    assert cache_files(cache)==before
