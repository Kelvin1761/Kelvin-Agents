"""The scheduled runs: outcomes the control plane reads, and what reaches Telegram."""
from __future__ import annotations

import json
from datetime import date

import pytest

from scripts import tennis_daily_schedule as scheduler


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(scheduler, "disk_headroom", lambda: {"ok": True, "detail": "ok"})
    sent = []
    monkeypatch.setattr(scheduler, "notify", lambda text, audience="primary": sent.append((audience, text)))
    from tennis_wc import run
    monkeypatch.setattr(run, "publish_day", lambda d, payload: {"cloudflare_deploy": {"status": "stub"}})
    return sent


def _payload(severity="ok", priced=10):
    return {"matches_analysed": 10, "valid_feature_snapshots": 10, "props_priced": 50,
            "report_path": "r.txt", "source_errors": [], "source_warnings": [],
            "odds_coverage": {"fixtures": 12, "priced_matches": priced},
            "readiness": {"horizon": "same_day", "severity": severity, "observed": ["x"],
                          "reasons": [] if severity == "ok" else ["x"]},
            "cloudflare_deploy": {"status": "deployed"}}


def _stub_analysis(monkeypatch, payload):
    from tennis_wc import run

    monkeypatch.setattr(scheduler, "preflight", lambda: None)
    monkeypatch.setattr(run, "price_day", lambda d, today: payload)


def test_card_success_prints_control_json_and_tops_up(monkeypatch, capsys):
    _stub_analysis(monkeypatch, _payload())
    published = []
    monkeypatch.setattr(scheduler, "publish", lambda d, label, main: published.append((d, label, main)) or [])
    code = scheduler.main(["--refresh-today", "--today", "2026-11-07", "--control-json"])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 0 and out == {"status": "succeeded", "mode": "card", "target_date": "2026-11-07", "exit_code": 0}
    assert published == [("2026-11-07", "09:00", False)]


def test_card_tops_up_even_when_the_board_is_broken(monkeypatch, capsys, isolated):
    _stub_analysis(monkeypatch, _payload(severity="error", priced=0))
    published = []
    monkeypatch.setattr(scheduler, "publish", lambda d, label, main: published.append(label) or [])
    code = scheduler.main(["--refresh-today", "--today", "2026-11-07", "--control-json"])
    assert code == 70 and published == ["09:00"]
    assert isolated and "出唔到咭" in isolated[0][1]


def test_retry_severity_is_a_partial_75(monkeypatch, capsys):
    _stub_analysis(monkeypatch, _payload(severity="retry", priced=3))
    monkeypatch.setattr(scheduler, "publish", lambda *a, **k: [])
    assert scheduler.main(["--refresh-today", "--today", "2026-11-07"]) == 75


def test_health_json_line_keeps_the_recovery_contract(monkeypatch):
    _stub_analysis(monkeypatch, _payload())
    monkeypatch.setattr(scheduler, "publish", lambda *a, **k: [])
    scheduler.main(["--refresh-today", "--today", "2026-11-07", "--source", "launchd"])
    from scripts.verify_scheduled_runs import read_runs

    runs = read_runs(scheduler.LOG_DIR / "tennis_daily_schedule.log")
    assert runs[-1]["mode"] == "card" and runs[-1]["source"] == "launchd"
    assert runs[-1]["health"]["priced"] == 10 and runs[-1]["health"]["severity"] == "ok"


def test_a_locked_scheduler_is_blocked_not_failed(monkeypatch, capsys):
    import fcntl

    scheduler.LOG_DIR.mkdir(parents=True)
    with (scheduler.LOG_DIR / scheduler.LOCK_NAME).open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        code = scheduler.main(["--today", "2026-11-07", "--control-json"])
    assert code == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["status"] == "blocked"


def test_low_disk_refuses_to_start(monkeypatch):
    monkeypatch.setattr(scheduler, "disk_headroom", lambda: {"ok": False, "detail": "1GB"})
    assert scheduler.main(["--today", "2026-11-07"]) == 75


def test_night_prices_tomorrow_and_sends_the_main_card(monkeypatch):
    seen = {}
    monkeypatch.setattr(scheduler, "preflight", lambda: None)
    monkeypatch.setattr(scheduler, "analyse", lambda d, today: seen.setdefault("analysed", (d, today)))
    monkeypatch.setattr(scheduler, "publish", lambda d, label, main: seen.setdefault("published", (d, label, main)) or [])
    assert scheduler.main(["--night", "21:00", "--today", "2026-11-06"]) == 0
    assert seen == {"analysed": ("2026-11-07", "2026-11-06"), "published": ("2026-11-07", "21:00", True)}


def test_night_failure_still_records_picks_and_alerts_primary(monkeypatch, isolated):
    def broken(d, today):
        raise RuntimeError("sportsbet down")

    calls = []
    monkeypatch.setattr(scheduler, "preflight", lambda: None)
    monkeypatch.setattr(scheduler, "analyse", broken)
    monkeypatch.setattr(scheduler, "publish", lambda d, label, main: calls.append(main) or [])
    assert scheduler.main(["--night", "21:00", "--today", "2026-11-06"]) == 1
    assert calls == [False], "no main card on a failed pass, but picks still recorded"
    assert isolated[0][0] == "primary" and "抓盤失敗" in isolated[0][1]


def test_night_23_is_a_top_up_without_alert(monkeypatch, isolated):
    calls = []
    monkeypatch.setattr(scheduler, "preflight", lambda: None)
    monkeypatch.setattr(scheduler, "analyse", lambda d, today: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(scheduler, "publish", lambda d, label, main: calls.append((label, main)) or [])
    scheduler.main(["--night", "23:00", "--today", "2026-11-06"])
    assert calls == [("23:00", False)] and isolated == []


def test_daily_reviews_yesterday_then_warms_tomorrow(monkeypatch):
    from tennis_wc import run
    from tennis_wc.publish import telegram

    order = []
    monkeypatch.setattr(scheduler, "preflight", lambda: None)
    monkeypatch.setattr(scheduler, "_lowtier_corpus", lambda d: order.append(("corpus", d)))
    monkeypatch.setattr(run, "review_day", lambda d: order.append(("review", d)) or
                        {"settlement": {"graded": 1, "voided": 0}, "pending_for_date": 0, "results": {}})
    monkeypatch.setattr(telegram, "forward_milestone", lambda log_dir: None)
    monkeypatch.setattr(scheduler, "_dashboard_settlements", lambda d: None)
    monkeypatch.setattr(scheduler, "_archive", lambda d: order.append(("archive", d)))
    monkeypatch.setattr(scheduler, "analyse", lambda d, today: order.append(("analyse", d)))
    assert scheduler.main(["--today", "2026-11-05"]) == 0  # a Thursday: no weekly
    assert order == [("corpus", "2026-11-04"), ("review", "2026-11-04"),
                     ("archive", "2026-11-04"), ("analyse", "2026-11-06")]


def test_the_dashboard_is_deployed_after_the_picks_are_recorded(monkeypatch):
    from tennis_wc import run

    order = []
    monkeypatch.setattr(scheduler, "preflight", lambda: None)
    monkeypatch.setattr(scheduler, "analyse", lambda d, today: order.append("analyse") or {"readiness": {}})
    monkeypatch.setattr(scheduler, "publish", lambda d, label, main: order.append("picks") or [])
    monkeypatch.setattr(run, "publish_day", lambda d, payload: order.append("deploy") or {})
    scheduler.main(["--night", "21:00", "--today", "2026-11-06"])
    scheduler.main(["--refresh-today", "--today", "2026-11-07"])
    assert order == ["analyse", "picks", "deploy", "analyse", "picks", "deploy"]


def test_a_failed_analysis_records_picks_but_does_not_deploy(monkeypatch):
    from tennis_wc import run

    order = []
    monkeypatch.setattr(scheduler, "preflight", lambda: None)
    monkeypatch.setattr(scheduler, "analyse", lambda d, today: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(scheduler, "publish", lambda d, label, main: order.append("picks") or [])
    monkeypatch.setattr(run, "publish_day", lambda d, payload: order.append("deploy") or {})
    scheduler.main(["--night", "23:00", "--today", "2026-11-06"])
    assert order == ["picks"]
