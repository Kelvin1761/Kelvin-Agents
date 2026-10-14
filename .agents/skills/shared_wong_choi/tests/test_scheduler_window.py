from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import plistlib
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi import control_plane as CP
from shared_wong_choi.contracts import Domain, Operation, OperationResult, RunIdentity, RunRequest, RunState
from shared_wong_choi.control import RetryPolicy
from shared_wong_choi.scheduler_window import DeferredQueue, SYDNEY, next_allowed, quiet_until
from shared_wong_choi.schedule_policy import NBA_ROLE_SLOTS, jobs_for

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("hour,minute,blocked", [(21,59,False),(22,0,True),(23,59,True),(0,59,True),(1,0,False)])
def test_gaming_window_boundaries(hour, minute, blocked):
    now = datetime(2027, 2, 2, hour, minute, tzinfo=SYDNEY)
    assert bool(quiet_until(now)) is blocked
    if blocked:
        assert quiet_until(now).hour == 1
        assert quiet_until(now) > now


@pytest.mark.parametrize("day,utc_hour", [(datetime(2026,7,2,tzinfo=timezone.utc),12),(datetime(2026,10,12,tzinfo=timezone.utc),11)])
def test_quiet_window_tracks_dst(day, utc_hour):
    assert quiet_until(day.replace(hour=utc_hour)) is not None


def test_deferred_au_keeps_original_review_day_after_midnight(tmp_path):
    request = RunRequest(RunIdentity(Domain.AU, "evening", date(2027,2,2), "17:00"), Operation.PREDICT,
                         metadata={"scheduler_args": ["--rounds", "2"]})
    now = datetime(2027,2,2,23,tzinfo=SYDNEY)
    queue = DeferredQueue(tmp_path, Domain.AU)
    path = queue.put(request, quiet_until(now), reason="quiet")
    assert list(queue.ready(now)) == []
    [(saved, resumed)] = list(queue.ready(datetime(2027,2,3,1,40,tzinfo=SYDNEY)))
    assert saved == path
    assert resumed.identity == request.identity
    assert resumed.metadata["scheduler_args"] == ["--rounds", "2"]


def test_half_hour_hkjc_recovery_collapses_to_one_pending_request(tmp_path):
    queue = DeferredQueue(tmp_path, Domain.HKJC)
    now = datetime(2027,2,2,22,tzinfo=SYDNEY)
    for slot in ("22:00", "22:30", "23:00"):
        request = RunRequest(RunIdentity(Domain.HKJC,"recovery",date(2027,2,2),slot),Operation.RECOVER)
        queue.put(request,next_allowed(now,Domain.HKJC,"recovery"),reason="quiet")
    assert len(list(queue.root.glob("*.json"))) == 1


def test_quiet_dispatch_does_not_construct_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(CP,"create_adapter",lambda *a: pytest.fail("pipeline started during gaming"))
    request = RunRequest(RunIdentity(Domain.NBA,"pregame",date(2027,2,3),"20:30"),Operation.PREDICT)
    result = CP.dispatch(request,ROOT,tmp_path,RetryPolicy(),datetime(2027,2,2,22,tzinfo=SYDNEY))
    assert result.state is RunState.BLOCKED
    assert result.status == "deferred_quiet_hours"
    assert len(list((tmp_path/"deferred/nba").glob("*.json"))) == 1


def test_source_waiting_uses_cooldown_and_original_date(tmp_path, monkeypatch):
    calls = []
    class Adapter:
        def execute(self, request):
            calls.append(request.identity)
            return OperationResult(RunState.PARTIAL,"waiting",detail={"exit_code":75})
    monkeypatch.setattr(CP,"create_adapter",lambda *a:Adapter())
    now = datetime(2027,2,2,20,30,tzinfo=SYDNEY)
    request = RunRequest(RunIdentity(Domain.NBA,"pregame",date(2027,2,3),"20:30"),Operation.PREDICT,
                         metadata={"max_attempts":3,"freshness_role":"production"})
    result = CP.dispatch(request,ROOT,tmp_path,RetryPolicy(),now)
    assert len(calls) == 1
    assert result.detail["next_retry_at"] == (now+timedelta(minutes=30)).isoformat()
    queue = DeferredQueue(tmp_path,Domain.NBA)
    assert not list(queue.ready(now))
    [(path,resumed)] = list(queue.ready(now+timedelta(minutes=30)))
    assert resumed.identity.target_date == request.identity.target_date
    assert resumed.identity.attempt == 2
    # The third failure is terminal for the queue, rather than an infinite loop.
    CP.drain_deferred(Domain.NBA,ROOT,tmp_path,now+timedelta(minutes=30))
    CP.drain_deferred(Domain.NBA,ROOT,tmp_path,now+timedelta(minutes=60))
    assert [i.attempt for i in calls] == [1,2,3]
    assert not path.exists()


def test_duplicate_enqueue_does_not_reset_retry_or_cooldown(tmp_path):
    from dataclasses import replace
    now = datetime(2027,2,2,20,tzinfo=SYDNEY)
    request = RunRequest(RunIdentity(Domain.AU,"evening",date(2027,2,2),"17:00",2),Operation.PREDICT)
    queue = DeferredQueue(tmp_path,Domain.AU)
    path = queue.put(request,now+timedelta(hours=1),reason="retry")
    before = path.read_bytes()
    queue.put(replace(request,identity=replace(request.identity,attempt=1)),now,reason="duplicate")
    assert path.read_bytes() == before


def test_nba_both_evening_roles_target_tomorrow():
    now = datetime(2027,2,2,20,30,tzinfo=SYDNEY)
    for slot in ("19:30","20:30"):
        assert CP.infer_target_date(Domain.NBA,"pregame",slot,now=now) == date(2027,2,3)


def test_evening_jobs_waking_after_midnight_keep_scheduled_event_day():
    now=datetime(2027,2,3,0,30,tzinfo=SYDNEY)
    assert CP.infer_target_date(Domain.AU,"evening","17:00",now=now) == date(2027,2,2)
    assert CP.infer_target_date(Domain.NBA,"pregame","20:30",now=now) == date(2027,2,3)
    assert CP.infer_target_date(Domain.TENNIS,"daily","18:00",now=now) == date(2027,2,2)
    assert CP.infer_target_date(Domain.AU,"evening","17:00",now=now,explicit=date(2027,2,1)) == date(2027,2,1)


def test_repeated_invocation_during_cooldown_does_not_start_adapter(tmp_path,monkeypatch):
    req=RunRequest(RunIdentity(Domain.NBA,"pregame",date(2027,2,3),"20:30",2),Operation.PREDICT)
    now=datetime(2027,2,2,20,40,tzinfo=SYDNEY)
    DeferredQueue(tmp_path,Domain.NBA).put(req,now+timedelta(minutes=30),reason="waiting")
    monkeypatch.setattr(CP,"create_adapter",lambda *a:pytest.fail("cooldown bypassed"))
    result=CP.dispatch(req,ROOT,tmp_path,RetryPolicy(),now)
    assert result.status == "deferred_cooldown"


def test_checkpoint_only_affects_managed_scheduler_and_uses_margin(monkeypatch):
    from shared_wong_choi import scheduler_window as window
    class Clock:
        @staticmethod
        def now(zone):
            return datetime(2027,2,2,21,45,tzinfo=zone)
    monkeypatch.setattr(window,"datetime",Clock)
    monkeypatch.delenv("WC_SCHEDULER_MANAGED",raising=False)
    window.checkpoint()
    # Test quiet_until separately: replacing datetime also replaces combine.
    monkeypatch.setattr(window,"quiet_until",lambda *args,**kwargs: True)
    monkeypatch.setenv("WC_SCHEDULER_MANAGED","1")
    with pytest.raises(window.SchedulerDeferred):
        window.checkpoint()


@pytest.mark.parametrize("domain,relative,modes", [
    (Domain.AU,"au_racing/au_daily_auto",{"evening":"evening","morning":"morning"}),
    (Domain.HKJC,"hkjc_racing/hkjc_daily_auto",{"watch":"watch","prerace":"prerace","postrace":"postrace"}),
    (Domain.NBA,"nba/nba_daily_auto",{"production":"pregame","warmup":"pregame","final-refresh":"pregame","postgame":"postgame"}),
])
def test_launchd_and_schedule_policy_agree(domain,relative,modes):
    folder = ROOT/".agents/skills"/relative/"launchd"
    for suffix,mode in modes.items():
        data = plistlib.loads((folder/f"com.antigravity.{domain.value}-wong-choi.{suffix}.plist.template").read_bytes())
        calendars = data["StartCalendarInterval"]
        if isinstance(calendars,dict): calendars=[calendars]
        actual = {(d["Hour"],d["Minute"]) for d in calendars}
        expected = {(t.hour,t.minute) for job in jobs_for(domain) if job.mode==mode for t in job.times}
        assert actual <= expected
        if domain is Domain.NBA and mode=="pregame":
            role = data["ProgramArguments"][-1]
            assert actual == {tuple(map(int,NBA_ROLE_SLOTS[role].split(":")))}


def test_permanent_failure_is_not_requeued(tmp_path,monkeypatch):
    class Adapter:
        def execute(self,request):
            return OperationResult(RunState.FAILED,"permanent_error",detail={"exit_code":1})
    monkeypatch.setattr(CP,"create_adapter",lambda *a:Adapter())
    now=datetime(2027,2,2,2,tzinfo=SYDNEY)
    queue=DeferredQueue(tmp_path,Domain.AU)
    req=RunRequest(RunIdentity(Domain.AU,"evening",date(2027,2,1),"17:00"),Operation.PREDICT)
    path=queue.put(req,now,reason="quiet")
    CP.drain_deferred(Domain.AU,ROOT,tmp_path,now)
    assert not path.exists()


def test_checkpoint_does_not_spend_source_waiting_budget(tmp_path, monkeypatch):
    calls = []
    outcomes = ["gaming_window_checkpoint", "waiting", "gaming_window_checkpoint", "waiting", "waiting"]
    class Adapter:
        def execute(self, request):
            calls.append(request)
            return OperationResult(RunState.PARTIAL, "partial", detail={
                "exit_code": 75, "source_payload": {"reason": outcomes[len(calls) - 1]},
            })
    monkeypatch.setattr(CP, "create_adapter", lambda *a: Adapter())
    now = datetime(2027, 2, 2, 18, tzinfo=SYDNEY)
    req = RunRequest(RunIdentity(Domain.AU, "evening", date(2027, 2, 2), "17:00"), Operation.PREDICT)
    CP.dispatch(req, ROOT, tmp_path, RetryPolicy(), now)
    for step in range(1, 5):
        CP.drain_deferred(Domain.AU, ROOT, tmp_path, now + timedelta(minutes=30 * step))
    assert [r.identity.attempt for r in calls] == [1, 2, 3, 4, 5]
    assert [r.metadata.get("temporary_failures", 0) for r in calls] == [0, 0, 1, 1, 2]
    assert not list(DeferredQueue(tmp_path, Domain.AU).root.glob("*.json"))


def test_normal_launch_after_cooldown_resumes_saved_attempt(tmp_path, monkeypatch):
    from dataclasses import replace
    calls = []
    class Adapter:
        def execute(self, request):
            calls.append(request)
            return OperationResult(RunState.SUCCEEDED, "complete")
    monkeypatch.setattr(CP, "create_adapter", lambda *a: Adapter())
    now = datetime(2027, 2, 3, 1, 30, tzinfo=SYDNEY)
    req = RunRequest(RunIdentity(Domain.AU, "evening", date(2027, 2, 2), "17:00"), Operation.PREDICT)
    saved = replace(req, identity=replace(req.identity, attempt=4), metadata={"temporary_failures": 1})
    DeferredQueue(tmp_path, Domain.AU).put(saved, now, reason="checkpoint")
    CP.dispatch(req, ROOT, tmp_path, RetryPolicy(), now)
    assert calls == [saved]
    from shared_wong_choi.au_adapter import AUAdapter
    command = AUAdapter(ROOT, tmp_path).command(calls[0])
    assert command[command.index("--today") + 1] == "2027-02-02"


def test_runtime_cutover_snapshots_evening_and_leaves_bot_loaded():
    script = (ROOT / ".agents/skills/central_wong_choi/install_production_runtime.sh").read_text()
    labels = script.split("LABELS=(", 1)[1].split(")", 1)[0]
    assert "com.antigravity.au-wong-choi.evening" in labels
    assert "com.antigravity.au-wong-choi.bot" not in labels
    section = script.split('AU_SCRIPT_DIR=', 1)[1].split('/bin/bash', 1)[0]
    assert "com.antigravity.au-wong-choi.evening" in section
    assert "com.antigravity.au-wong-choi.deferred" in section
    assert "com.antigravity.au-wong-choi.bot" not in section
