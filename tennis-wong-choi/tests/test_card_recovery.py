from __future__ import annotations

import json


def test_successful_card_ignores_dashboard_failure(tmp_path):
    from scripts import tennis_card_recovery as recovery

    log = tmp_path / "schedule.log"
    log.write_text(
        "[2026-08-13T09:00:01+10:00] Starting SAME-DAY refresh for 2026-08-13 "
        "run_source=launchd mode=card\n"
        '[2026-08-13T09:09:00+10:00] HEALTH_JSON {"date":"2026-08-13",'
        '"severity":"ok","priced":65,"deploy":"failed"}\n',
        encoding="utf-8",
    )
    assert recovery.successful_card_for_day(log, "2026-08-13") is not None


def test_missing_health_is_not_invented_as_success(tmp_path):
    from scripts import tennis_card_recovery as recovery

    log = tmp_path / "schedule.log"
    log.write_text(
        "[2026-08-13T09:00:01+10:00] Starting SAME-DAY refresh for 2026-08-13 "
        "run_source=launchd mode=card\n",
        encoding="utf-8",
    )
    assert recovery.successful_card_for_day(log, "2026-08-13") is None


def test_state_resets_on_a_new_day(tmp_path):
    from scripts import tennis_card_recovery as recovery

    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"day": "2026-08-12", "attempts": 2}))
    assert recovery.load_state(state_path, "2026-08-13") == {
        "day": "2026-08-13",
        "analysis_attempts": 0,
        "dashboard_attempts": 0,
        "low_disk_alerted": False,
    }


def test_low_disk_defers_without_consuming_attempt(tmp_path, monkeypatch):
    from scripts import tennis_card_recovery as recovery

    log = tmp_path / "schedule.log"
    state = tmp_path / "state.json"
    monkeypatch.setattr(recovery, "LOCK_PATH", tmp_path / "lock")
    monkeypatch.setattr(recovery, "runner_active", lambda _: False)
    monkeypatch.setattr(
        recovery,
        "disk_headroom",
        lambda: {"ok": False, "detail": "3GB free, 5GB required"},
    )
    sent = []
    monkeypatch.setattr(recovery, "notify", lambda message: sent.append(message))

    assert recovery.main([
        "--today", "2026-08-13", "--log", str(log), "--state", str(state)
    ]) == 75
    payload = json.loads(state.read_text())
    assert payload["analysis_attempts"] == 0
    assert payload["low_disk_alerted"] is True
    assert len(sent) == 1


def test_completed_card_with_stale_dashboard_recovers_publish_only(
    tmp_path, monkeypatch
):
    from scripts import tennis_card_recovery as recovery

    log = tmp_path / "schedule.log"
    state = tmp_path / "state.json"
    log.write_text(
        "[2026-08-13T09:00:01+10:00] Starting SAME-DAY refresh for 2026-08-13 "
        "run_source=launchd mode=card\n"
        '[2026-08-13T09:25:00+10:00] HEALTH_JSON {"date":"2026-08-13",'
        '"severity":"ok","priced":65,"deploy":"failed"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(recovery, "runner_active", lambda _: False)
    monkeypatch.setattr(
        recovery, "live_tennis_status",
        lambda day: {"published": False, "run_id": "tennis:unavailable", "status": "unavailable"},
    )
    deployed = []
    monkeypatch.setattr(
        recovery, "recover_dashboard",
        lambda day: (deployed.append(day) or True, "production verified"),
    )
    sent = []
    monkeypatch.setattr(recovery, "notify", lambda message: sent.append(message))
    monkeypatch.setattr(
        recovery, "RUNNER",
        type("MustNotRun", (), {"__str__": lambda self: (_ for _ in ()).throw(
            AssertionError("analysis runner must not execute"))})(),
    )

    assert recovery.main([
        "--today", "2026-08-13", "--log", str(log), "--state", str(state)
    ]) == 0
    assert deployed == ["2026-08-13"]
    assert json.loads(state.read_text())["dashboard_attempts"] == 1
    assert "Dashboard 自動復原完成" in sent[0]


def test_completed_card_already_live_does_nothing(tmp_path, monkeypatch, capsys):
    from scripts import tennis_card_recovery as recovery

    log = tmp_path / "schedule.log"
    log.write_text(
        "[2026-08-13T09:00:01+10:00] Starting SAME-DAY refresh for 2026-08-13 "
        "run_source=launchd mode=card\n"
        '[2026-08-13T09:25:00+10:00] HEALTH_JSON {"date":"2026-08-13",'
        '"severity":"ok","priced":65,"deploy":"deployed"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        recovery, "live_tennis_status",
        lambda day: {"published": True, "run_id": f"tennis:{day}", "status": "valid"},
    )
    monkeypatch.setattr(
        recovery, "recover_dashboard",
        lambda day: (_ for _ in ()).throw(AssertionError("must not redeploy")),
    )

    assert recovery.main([
        "--today", "2026-08-13", "--log", str(log),
        "--state", str(tmp_path / "state.json"), "--control-json"
    ]) == 0
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["status"] == "dormant"
    assert payload["reason"] == "card_and_dashboard_current"


CONTROL_DUPLICATE = json.dumps({
    "artifacts": ["/x/runs/tennis/2026-09-09/card/09%3A00/attempt-1.json"],
    "detail": {"run_id": "wc:tennis:run:2026-09-09:card:09%3A00:attempt-1"},
    "domain": "tennis", "mode": "card", "operation": "predict",
    "scheduled_slot": "09:00", "schema_version": "wong-choi-control-result/v1",
    "severity": "critical", "state": "failed", "status": "duplicate_skipped",
    "target_date": "2026-09-09",
}, sort_keys=True)


def test_control_plane_duplicate_is_recognised():
    from scripts import tennis_card_recovery as recovery

    assert recovery._control_plane_duplicate(
        "RECOVERY STARTED\n" + CONTROL_DUPLICATE + "\ntrailing\n") == "duplicate_skipped"
    # 真係行過嘅 run 唔可以當成冇行過。
    ran = CONTROL_DUPLICATE.replace('"duplicate_skipped"', '"complete"')
    assert recovery._control_plane_duplicate(ran) is None
    assert recovery._control_plane_duplicate("") is None
    assert recovery._control_plane_duplicate("{not json}") is None


def test_a_blocked_recovery_does_not_consume_an_attempt(tmp_path, monkeypatch):
    """2026-09-09：兩個復原時段 `duplicate_skipped`，一步都冇行過，attempt 燒晒。

    冇行過就唔可以計數 —— 唔係嘅話兩個時段會喺完全冇試過嘅情況下耗盡，
    然後報一個「未知錯誤，下一個復原時段會再試」，而其實冇下一次。
    """
    from scripts import tennis_card_recovery as recovery
    import subprocess

    log = tmp_path / "schedule.log"
    state = tmp_path / "state.json"
    monkeypatch.setattr(recovery, "LOCK_PATH", tmp_path / "lock")
    monkeypatch.setattr(recovery, "runner_active", lambda _: False)
    monkeypatch.setattr(recovery, "disk_headroom", lambda: {"ok": True, "detail": ""})
    sent = []
    monkeypatch.setattr(recovery, "notify", lambda message: sent.append(message))

    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = list(cmd)
        return subprocess.CompletedProcess(cmd, 1, CONTROL_DUPLICATE, "")

    monkeypatch.setattr(recovery.subprocess, "run", fake_run)

    assert recovery.main([
        "--today", "2026-09-09", "--log", str(log), "--state", str(state)
    ]) == 75
    # 復原一定要傳 `--force`，唔係嘅話 control plane 永遠當佢係重複。
    assert "--force" in seen["cmd"]
    assert json.loads(state.read_text())["analysis_attempts"] == 0
    assert sent and "control plane" in sent[0]
