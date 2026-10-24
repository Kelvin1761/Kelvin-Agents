"""No network: real inputs/IPC plus deterministic deployment-boundary fakes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import au_daily_schedule as S
import au_progressive_publish as P


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_AU_SCHED_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(S, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(S, "LOG_DIR", tmp_path / "logs")


def meeting(tmp_path, name="Alpha", races=2):
    folder = tmp_path / f"2026-10-24 {name} Race 1-{races}"
    folder.mkdir(parents=True)
    for race in range(1, races + 1):
        for suffix, content in (("Logic.json", '{"horses":{}}'),
                                ("Auto_Analysis.md", "original analysis"),
                                ("Auto_Scoring.csv", "horse,score\nA,60\n")):
            (folder / f"Race_{race}_{suffix}").write_text(content)
    (folder / "odds_history.json").write_text('{}')
    return folder


def job(tmp_path, name, number):
    source = meeting(tmp_path / "source", name)
    frozen = tmp_path / "spool" / "inputs" / str(number) / source.name
    digest, size = P.freeze_meeting(source, frozen)
    return {"id": str(number), "meeting": source.name, "folder": str(frozen),
            "digest": digest, "bytes": size, "queued_at": time.time()}


def queue(root, jobs):
    P.atomic_json(root / "queue.json", {
        "review_day": "2026-10-23", "started_at": S.stamp(),
        "archived": [], "jobs": jobs})


def record_test_evidence(log, folders):
    log.step("prediction-evidence", "ok", meetings=[
        {"meeting": f.name, "snapshot": str(f)} for f in folders])
    return True


def result_ok(log):
    log.data["cloudflare_deployment"] = {"ok": True, "verified": {"ok": True}}
    log.data["dashboard_validation"] = {"ok": True}
    return True


def test_freeze_has_no_live_references_or_nested_corpus(tmp_path):
    source = meeting(tmp_path)
    history = source / "_prediction_snapshots"
    history.mkdir()
    (history / "huge.json").write_text("do not copy")
    target = tmp_path / "frozen" / source.name
    digest, size = P.freeze_meeting(source, target)
    (source / "Race_1_Auto_Analysis.md").write_text("changed by next analysis")
    assert (target / "Race_1_Auto_Analysis.md").read_text() == "original analysis"
    assert not (target / "_prediction_snapshots").exists()
    assert digest == P.meeting_digest(target)
    assert size == sum(p.stat().st_size for p in target.iterdir())


@pytest.mark.parametrize("suffix", ["Logic.json", "Auto_Analysis.md", "Auto_Scoring.csv"])
def test_incomplete_meeting_never_enters_queue(tmp_path, suffix):
    source = meeting(tmp_path)
    (source / f"Race_2_{suffix}").unlink()
    with pytest.raises(ValueError, match="incomplete"):
        P.freeze_meeting(source, tmp_path / "frozen")


def test_pending_analysis_never_enters_queue(tmp_path):
    source = meeting(tmp_path)
    (source / S.ANALYSIS_PENDING).touch()
    with pytest.raises(ValueError, match="pending"):
        P.freeze_meeting(source, tmp_path / "frozen")


def test_large_copy_fails_before_writing(tmp_path, monkeypatch):
    source = meeting(tmp_path)
    monkeypatch.setattr(P, "MAX_MEETING_BYTES", 1)
    with pytest.raises(ValueError, match="64 MiB"):
        P.freeze_meeting(source, tmp_path / "frozen")
    assert not (tmp_path / "frozen").exists()


def test_worker_coalesces_arrivals_and_keeps_prior_published_meetings(tmp_path, monkeypatch):
    root = tmp_path / "spool"
    jobs = [job(tmp_path, name, i) for i, name in enumerate(("Alpha", "Beta", "Gamma"), 1)]
    queue(root, jobs[:1])
    batches = []

    def publish(log, folders, archived, **kwargs):
        batches.append([p.name for p in folders])
        assert kwargs == {"recover_unpublished": False, "isolate_failures": True,
                          "retain_intermediates": False}
        if len(batches) == 1:
            queue(root, jobs)
            (root / "done").touch()
        return result_ok(log)

    monkeypatch.setattr(S, "step_dashboard", publish)
    assert P.run_worker(root, S, poll_seconds=0) == 0
    result = P.read_json(root / "result.json")
    assert batches == [[jobs[0]["meeting"]], [j["meeting"] for j in jobs]]
    assert len(result["published"]) == 3
    assert result["batch_count"] == result["deployment_count"] == 2
    assert result["complete"] and result["finished"]
    assert not (root / "build").exists()
    assert len(list((root / "batches").glob('*.json'))) == 2


def test_failed_upload_does_not_discard_new_or_previous_jobs(tmp_path, monkeypatch):
    root = tmp_path / "spool"
    jobs = [job(tmp_path, name, i) for i, name in enumerate(("Alpha", "Beta"), 1)]
    queue(root, jobs[:1])
    batches = []

    def publish(log, folders, archived, **kwargs):
        batches.append([p.name for p in folders])
        if len(batches) == 1:
            queue(root, jobs)
            (root / "done").touch()
            log.error("deploy", "transient upload failure")
            return False
        return result_ok(log)

    monkeypatch.setattr(S, "step_dashboard", publish)
    P.run_worker(root, S, poll_seconds=0)
    result = P.read_json(root / "result.json")
    assert batches[1] == [j["meeting"] for j in jobs]
    assert result["complete"] and not result["pending"]
    assert len(result["published"]) == 2


def test_bad_meeting_is_quarantined_while_healthy_meetings_publish(tmp_path, monkeypatch):
    root = tmp_path / "spool"
    jobs = [job(tmp_path, name, i) for i, name in enumerate(("Alpha", "Bad", "Gamma"), 1)]
    queue(root, jobs)
    (root / "done").touch()

    def publish(log, folders, archived, **kwargs):
        S.reject_publication(log, folders[1], "dead-field")
        return result_ok(log)

    monkeypatch.setattr(S, "step_dashboard", publish)
    P.run_worker(root, S, poll_seconds=0)
    result = P.read_json(root / "result.json")
    assert set(result["published"]) == {jobs[0]["meeting"], jobs[2]["meeting"]}
    assert result["rejected"] == {jobs[1]["meeting"]: "dead-field"}
    assert not result["complete"]


def test_changed_frozen_input_is_rejected_before_deploy(tmp_path, monkeypatch):
    root = tmp_path / "spool"
    j = job(tmp_path, "Alpha", 1)
    (Path(j["folder"]) / "Race_1_Logic.json").write_text("changed")
    queue(root, [j])
    (root / "done").touch()
    seen = []

    def publish(log, folders, archived, **kwargs):
        seen.extend(folders)
        return result_ok(log)

    monkeypatch.setattr(S, "step_dashboard", publish)
    P.run_worker(root, S, poll_seconds=0)
    result = P.read_json(root / "result.json")
    assert not seen and not result["published"]
    assert "digest changed" in result["rejected"][j["meeting"]]


def test_unresolved_upload_is_reported_as_pending_not_success(tmp_path, monkeypatch):
    root = tmp_path / "spool"
    j = job(tmp_path, "Alpha", 1)
    queue(root, [j])
    (root / "done").touch()
    monkeypatch.setattr(S, "step_dashboard", lambda *a, **k: False)
    P.run_worker(root, S, poll_seconds=0)
    result = P.read_json(root / "result.json")
    assert not result["complete"] and result["pending"] == [j["meeting"]]


def test_empty_queue_still_publishes_archive_pruning(tmp_path, monkeypatch):
    root = tmp_path / "spool"
    queue(root, [])
    data = P.read_json(root / "queue.json")
    data["archived"] = ["2026-10-23 Old Race 1-2"]
    P.atomic_json(root / "queue.json", data)
    (root / "done").touch()
    seen = []

    def publish(log, folders, archived, **kwargs):
        seen.extend(archived)
        return result_ok(log)

    monkeypatch.setattr(S, "step_dashboard", publish)
    P.run_worker(root, S, poll_seconds=0)
    assert seen == data["archived"]
    assert P.read_json(root / "result.json")["complete"]


def wait_for(path, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not path.exists():
        time.sleep(.02)
    assert path.exists()


def test_real_child_does_not_block_analysis_and_finish_drains_it(tmp_path, monkeypatch):
    stub = tmp_path / "worker.py"
    stub.write_text('''import json,sys,time
from pathlib import Path
root=Path(sys.argv[1])
(root/'entered').touch()
while not (root/'done').exists(): time.sleep(.02)
q=json.loads((root/'queue.json').read_text())
(root/'result.json').write_text(json.dumps({'complete':True,'finished':True,
    'published':{j['meeting']:j['id'] for j in q['jobs']},'batch_count':1}))
''')
    real_popen = subprocess.Popen

    def spawn(command, **kwargs):
        assert kwargs['start_new_session'] is True
        root = Path(command[command.index('--spool') + 1])
        return real_popen([sys.executable, str(stub), str(root)], **kwargs)

    monkeypatch.setattr(P.subprocess, "Popen", spawn)
    monkeypatch.setattr(S, "step_prediction_evidence", record_test_evidence)
    log = S.RunLog("evening", S.date(2026, 10, 23), tmp_path / "run.json", notify=False)
    original_work = S.WORK_DIR
    publisher = P.ProgressivePublisher(S, log, [])
    try:
        first, second = meeting(tmp_path, "Alpha"), meeting(tmp_path, "Beta")
        publisher.submit(first)
        wait_for(publisher.root / "entered")
        before = time.monotonic()
        publisher.submit(second)
        publisher.submit(second)  # Retry rounds cannot queue the same meeting twice.
        assert time.monotonic() - before < .5
        assert publisher.process.poll() is None
        assert S.WORK_DIR == original_work
        result = publisher.finish()
        assert len(result['published']) == 2 and result['complete']
        assert result['copy_seconds'] < .5
    finally:
        publisher.abort()


def test_summary_never_claims_everything_live_when_one_meeting_is_rejected():
    import au_run_summary
    text = au_run_summary.evening({
        'races_added':[{'meeting':'2026-10-24 Bad Race 1-2','races':[1,2]}],
        'cloudflare_deployment':{'ok':True,'verified':{'ok':True}},
        'publication_rejected':{'2026-10-24 Bad Race 1-2':'dead-field'},
        'progressive_publication':{'published':{'2026-10-24 Alpha Race 1-2':'1'}},
    })
    assert '部分上線' in text and 'Bad：未更新上線' in text
    assert '✅ 已上線並核實' not in text


def test_required_input_symlink_is_not_treated_as_a_frozen_file(tmp_path):
    source = meeting(tmp_path)
    logic = source / 'Race_1_Logic.json'
    logic.unlink()
    target = tmp_path / 'other.json'
    target.write_text('{}')
    logic.symlink_to(target)
    with pytest.raises(ValueError, match='incomplete'):
        P.freeze_meeting(source, tmp_path / 'frozen')


def test_abort_kills_worker_and_its_upload_descendants(tmp_path, monkeypatch):
    marker = tmp_path / 'late-upload'
    stub = tmp_path / 'worker.py'
    child = f"import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).touch()"
    stub.write_text("import subprocess,sys,time\nfrom pathlib import Path\n"
                    + f"subprocess.Popen([sys.executable,'-c',{child!r}])\n"
                    + "Path(sys.argv[1],'entered').touch()\ntime.sleep(60)\n")
    real_popen = subprocess.Popen

    def spawn(command, **kwargs):
        root = command[command.index('--spool') + 1]
        return real_popen([sys.executable, str(stub), root], **kwargs)

    monkeypatch.setattr(P.subprocess, 'Popen', spawn)
    monkeypatch.setattr(S, 'step_prediction_evidence', record_test_evidence)
    log = S.RunLog('evening', S.date(2026,10,23), tmp_path/'run.json', notify=False)
    publisher = P.ProgressivePublisher(S, log, [])
    try:
        publisher.submit(meeting(tmp_path))
        wait_for(publisher.root/'entered')
        publisher.abort()
        assert publisher.process.poll() is not None
        time.sleep(1.1)
        assert not marker.exists()
    finally:
        publisher.abort()


def test_drain_timeout_cannot_leave_an_upload_running(tmp_path, monkeypatch):
    stub = tmp_path/'worker.py'
    stub.write_text("import time; time.sleep(60)")
    real_popen = subprocess.Popen
    monkeypatch.setattr(P.subprocess, 'Popen',
                        lambda command, **kw: real_popen([sys.executable,str(stub)], **kw))
    monkeypatch.setattr(S, 'step_prediction_evidence', record_test_evidence)
    monkeypatch.setenv('WC_AU_PUBLICATION_DRAIN_SECONDS', '.05')
    log = S.RunLog('evening', S.date(2026,10,23), tmp_path/'run.json', notify=False)
    publisher = P.ProgressivePublisher(S, log, [])
    try:
        publisher.submit(meeting(tmp_path))
        with pytest.raises(TimeoutError, match='deadline'):
            publisher.finish()
        assert publisher.process.poll() is not None
    finally:
        publisher.abort()


def test_owner_death_stops_orphaned_publisher_and_descendants(tmp_path):
    marker = tmp_path/'late-upload'
    pidfile = tmp_path/'worker.pid'
    module_dir = str(Path(P.__file__).parent)
    upload = f"import time; from pathlib import Path; time.sleep(1.2); Path({str(marker)!r}).touch()"
    worker = (f"import sys,os,threading,subprocess,time; sys.path.insert(0,{module_dir!r}); "
              "from au_progressive_publish import guard_owner; "
              "threading.Thread(target=guard_owner,args=(int(sys.argv[1]),.02),daemon=True).start(); "
              f"subprocess.Popen([sys.executable,'-c',{upload!r}]); "
              "time.sleep(60)")
    owner = ("import subprocess,sys,os,time; from pathlib import Path; "
             f"p=subprocess.Popen([sys.executable,'-c',{worker!r},str(os.getpid())],start_new_session=True); "
             f"Path({str(pidfile)!r}).write_text(str(p.pid)); time.sleep(60)")
    process = subprocess.Popen([sys.executable,'-c',owner], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        wait_for(pidfile)
        time.sleep(.1)
        process.kill()  # Simulate a hard scheduler crash, bypassing finally.
        process.communicate(timeout=3)
        time.sleep(1.3)
        assert not marker.exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        if pidfile.exists():
            try:
                os.killpg(int(pidfile.read_text()), 9)
            except ProcessLookupError:
                pass


def test_done_barrier_cannot_skip_a_last_concurrent_queue_update(tmp_path, monkeypatch):
    root = tmp_path/'spool'
    jobs = [job(tmp_path,name,i) for i,name in enumerate(('Alpha','Beta'),1)]
    queue(root,jobs[:1])
    original_read = P.read_json
    reads = []

    def racing_read(path, default=None):
        data = original_read(path,default)
        if path.name == 'queue.json':
            reads.append(1)
            if len(reads) == 2:
                queue(root,jobs)
                (root/'done').touch()
                # The just-completed read still observes the previous version.
        return data

    monkeypatch.setattr(P,'read_json',racing_read)
    monkeypatch.setattr(S,'step_dashboard',lambda log,*a,**k: result_ok(log))
    P.run_worker(root,S,poll_seconds=0)
    result = original_read(root/'result.json')
    assert result['complete'] and len(result['published']) == 2


def test_freeze_can_use_immutable_evidence_instead_of_mutable_live_folder(tmp_path):
    source = meeting(tmp_path)
    evidence = tmp_path/'prediction-snapshot'
    shutil = __import__('shutil')
    shutil.copytree(source,evidence)
    (source/'Race_1_Auto_Analysis.md').write_text('mutated after evidence registration')
    target = tmp_path/'frozen'/source.name
    P.freeze_meeting(evidence,target,meeting_name=source.name)
    assert (target/'Race_1_Auto_Analysis.md').read_text() == 'original analysis'


def test_changed_evidence_manifest_hash_is_rejected(tmp_path):
    import hashlib
    source = meeting(tmp_path)
    file = source/'Race_1_Logic.json'
    (source/'manifest.json').write_text(json.dumps({'files':[
        {'name':file.name,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}]}))
    file.write_text('corrupted after prediction registration')
    with pytest.raises(ValueError,match='evidence hash changed'):
        P.freeze_meeting(source,tmp_path/'frozen')


def test_parent_rejects_a_finished_result_that_omits_a_queued_meeting(tmp_path, monkeypatch):
    stub = tmp_path/'worker.py'
    stub.write_text('pass')
    real_popen = subprocess.Popen
    monkeypatch.setattr(P.subprocess, 'Popen',
                        lambda command, **kw: real_popen([sys.executable,str(stub)], **kw))
    monkeypatch.setattr(S, 'step_prediction_evidence', record_test_evidence)
    log = S.RunLog('evening', S.date(2026,10,23), tmp_path/'run.json', notify=False)
    publisher = P.ProgressivePublisher(S, log, [])
    source = meeting(tmp_path)
    publisher.submit(source)
    # An apparently successful but incomplete child receipt cannot authorize all-live.
    P.atomic_json(publisher.root/'result.json',
                  {'finished':True,'complete':True,'published':{}})
    monkeypatch.setattr(publisher, '_start', lambda: None)
    result = publisher.finish()
    assert not result['complete'] and result['pending'] == [source.name]
