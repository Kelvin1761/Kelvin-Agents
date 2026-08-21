from __future__ import annotations

import subprocess

from scripts import tennis_daily_schedule as scheduler


def test_ensure_live_network_accepts_ready(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "run_cli_json",
        lambda *args: {"diagnosis": "network_ready"},
    )

    scheduler.ensure_live_network()


def test_ensure_live_network_marks_sandbox_dns_as_temporary(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "run_cli_json",
        lambda *args: {"diagnosis": "system_dns_unavailable"},
    )

    try:
        scheduler.ensure_live_network()
    except scheduler.TemporaryDataUnavailable as exc:
        assert "host network access" in str(exc)
    else:
        raise AssertionError("network failure must stop the scheduled workflow")


def test_analysis_retry_reasons_reject_silent_empty_provider_responses():
    reasons = scheduler.analysis_retry_reasons(
        {
            "matches_analysed": 0,
            "valid_feature_snapshots": 0,
            "odds_coverage": {"fixtures": 0, "priced_matches": 0},
            "source_errors": [],
        }
    )
    assert "without a confirmed empty slate" in reasons[0]


def test_analysis_retry_reasons_allow_a_confirmed_empty_slate():
    assert scheduler.analysis_retry_reasons(
        {
            "matches_analysed": 0,
            "valid_feature_snapshots": 0,
            "odds_coverage": {"fixtures": 0, "priced_matches": 0},
            "confirmed_empty_slate": True,
            "source_errors": [],
        }
    ) == []


def test_analysis_retry_reasons_reject_failed_odds_and_enrichment():
    reasons = scheduler.analysis_retry_reasons(
        {
            "matches_analysed": 0,
            "valid_feature_snapshots": 0,
            "source_errors": [
                {"source": "odds", "error": "dns failed"},
                {"source": "event_markets", "error": "only match winner"},
            ],
        }
    )

    assert "zero matches after source failures" in reasons
    assert "odds: dns failed" in reasons
    assert "event_markets: only match winner" in reasons


def test_main_returns_temporary_failure_code_before_workflow(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduler, "LOG_DIR", tmp_path)
    monkeypatch.setattr(scheduler, "ensure_live_network", lambda: (_ for _ in ()).throw(
        scheduler.TemporaryDataUnavailable("network unavailable")
    ))
    monkeypatch.setattr(
        scheduler,
        "run_cli",
        lambda *args: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, list(args))
        ),
    )

    assert scheduler.main(["--today", "2026-07-25"]) == 75


# --------------------------------------------------------------------------- #
# Thin odds coverage must not pass as a normal quiet day (2026-07-29)
# --------------------------------------------------------------------------- #
def _payload(fixtures, priced, matches=None, valid=None):
    matches = priced if matches is None else matches
    valid = matches if valid is None else valid
    return {
        "matches_analysed": matches,
        "valid_feature_snapshots": valid,
        "odds_coverage": {"fixtures": fixtures, "priced_matches": priced},
        "source_errors": [],
    }


def test_unopened_book_is_flagged_for_retry():
    """The 20:00 job analyses TOMORROW, when Sportsbet has barely opened the book.
    On 2026-07-29 that produced a published card from 2 priced matches out of 102
    fixtures, and every gate passed because they only checked for zero matches."""
    reasons = scheduler.analysis_retry_reasons(_payload(fixtures=102, priced=2))
    assert reasons, "2/102 priced must not be treated as a valid betting card"
    assert "not open yet" in reasons[0]


def test_healthy_same_day_coverage_passes():
    assert scheduler.analysis_retry_reasons(_payload(fixtures=92, priced=60, valid=40)) == []


def test_genuinely_small_card_is_not_flagged():
    """A real quiet day (few fixtures, nearly all priced) must stay a pass --
    the gate is about coverage, not volume."""
    assert scheduler.analysis_retry_reasons(_payload(fixtures=9, priced=8)) == []


def test_ratio_gate_ignores_tiny_fixture_lists():
    """Below the fixture floor the ratio is noise, so it must not fire."""
    assert scheduler.analysis_retry_reasons(_payload(fixtures=4, priced=1)) == []


def test_scheduled_analysis_leaves_tracker_sync_and_deploy_to_run_daily(monkeypatch):
    calls = []
    logs = []

    def fake_run_cli_json(*args):
        calls.append(args)
        return {
            "matches_analysed": 40,
            "valid_feature_snapshots": 40,
            "odds_coverage": {"fixtures": 60, "priced_matches": 40},
            "source_errors": [],
            "analysis_dir": "/tmp/analysis",
            "tracker_sync": {"clv": {"synced": 3}, "combo": {"synced": 2}},
            "cloudflare_deploy": {"attempted": True, "status": "deployed"},
        }

    monkeypatch.setattr(scheduler, "run_cli_json", fake_run_cli_json)
    monkeypatch.setattr(scheduler, "log", logs.append)

    scheduler.analyse_next_day("2026-07-29")

    # The point of this test is that the wrapper does not re-run what run-daily
    # already owns -- syncing trackers or deploying a second time. Housekeeping
    # commands that own nothing of the day's output are allowed alongside it.
    assert calls[0] == ("run-daily", "--date", "2026-07-29")
    commands = {call[0] for call in calls}
    assert commands.isdisjoint(
        {"sync-clv-tracker", "sync-combo-tracker", "publish-dashboard"}
    )
    assert any("dashboard" in line and "deployed" in line for line in logs)


def test_scheduled_analysis_prunes_superseded_payloads_every_run(monkeypatch):
    """Unbounded growth is the bug, so retention cannot be a manual chore.

    The database reached 2.6GB with no retention of any kind, and at that size
    `disk_headroom` -- two database-widths -- began refusing to run recovery on
    a volume with 3.7GB free. The dashboard then sat a day stale with nothing
    in the logs looking wrong.
    """
    calls = []

    def fake_run_cli_json(*args):
        calls.append(args)
        if args[0] == "prune-raw-responses":
            return {"rows": 12, "bytes_freed": 5 * 1024 ** 2}
        return {
            "matches_analysed": 40,
            "valid_feature_snapshots": 40,
            "odds_coverage": {"fixtures": 60, "priced_matches": 40},
            "source_errors": [],
            "analysis_dir": "/tmp/analysis",
            "tracker_sync": {},
            "cloudflare_deploy": {"attempted": True, "status": "deployed"},
        }

    logs = []
    monkeypatch.setattr(scheduler, "run_cli_json", fake_run_cli_json)
    monkeypatch.setattr(scheduler, "log", logs.append)

    scheduler.analyse_next_day("2026-07-29")

    assert ("prune-raw-responses", "--keep-days", "7") in calls
    assert any("Pruned 12 superseded API payloads" in line for line in logs)


def test_a_failing_prune_never_costs_the_day(monkeypatch):
    calls = []

    def fake_run_cli_json(*args):
        calls.append(args)
        if args[0] == "prune-raw-responses":
            raise RuntimeError("database is locked")
        return {
            "matches_analysed": 40,
            "valid_feature_snapshots": 40,
            "odds_coverage": {"fixtures": 60, "priced_matches": 40},
            "source_errors": [],
            "analysis_dir": "/tmp/analysis",
            "tracker_sync": {},
            "cloudflare_deploy": {"attempted": True, "status": "deployed"},
        }

    logs = []
    monkeypatch.setattr(scheduler, "run_cli_json", fake_run_cli_json)
    monkeypatch.setattr(scheduler, "log", logs.append)

    scheduler.analyse_next_day("2026-07-29")

    assert any("Retention step skipped: database is locked" in line for line in logs)


def test_run_cli_logs_captured_output_before_raising(monkeypatch):
    logs = []

    class FailedCommand:
        stdout = "dashboard build traceback"
        returncode = 1

        def check_returncode(self):
            raise subprocess.CalledProcessError(self.returncode, ["run-daily"], output=self.stdout)

    monkeypatch.setattr(scheduler.subprocess, "run", lambda *args, **kwargs: FailedCommand())
    monkeypatch.setattr(scheduler, "log", logs.append)

    try:
        scheduler.run_cli("run-daily", "--date", "2026-08-02")
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("failed child command must still propagate its exit status")

    assert logs[-1] == "dashboard build traceback"


# --------------------------------------------------------------------------- #
# The next-day / same-day distinction (2026-08-11)
# --------------------------------------------------------------------------- #
def _empty_board(fixtures=21, priced=0):
    return {
        "matches_analysed": 0,
        "valid_feature_snapshots": 0,
        "source_errors": [],
        "odds_coverage": {"fixtures": fixtures, "priced_matches": priced},
    }


def test_an_empty_board_means_opposite_things_on_the_two_horizons():
    """The log line that hid three dark days.

    Sportsbet does not open tomorrow's book in the evening -- its own listing
    returns HTTP 200 and two bytes at 18:07, and 55 events for the same date at
    09:08 the next morning. So the 18:00 warm pass finding nothing is the world
    working, and the 09:00 pass finding nothing is the pipeline broken. Until
    2026-08-11 both produced `TEMPORARY DATA FAILURE` and exit 75, and the
    pipeline ran from 2026-08-09 to 2026-08-11 with zero odds captured while
    every evening's log looked exactly like every other evening's.
    """
    from tennis_wc.pipeline_readiness import (
        SEVERITY_ERROR, SEVERITY_EXPECTED_EMPTY, analysis_readiness,
    )

    warm = analysis_readiness(_empty_board(), horizon="next_day")
    assert warm["severity"] == SEVERITY_EXPECTED_EMPTY
    assert warm["reasons"] == [], "a closed book is not something to act on"
    assert warm["observed"], "but it is still recorded"

    card = analysis_readiness(_empty_board(), horizon="same_day")
    assert card["severity"] == SEVERITY_ERROR
    assert card["reasons"], "an empty board on the day has to be actionable"


def test_a_partial_book_on_the_day_is_a_retry_not_an_error():
    from tennis_wc.pipeline_readiness import SEVERITY_RETRY, analysis_readiness

    payload = _empty_board(fixtures=100, priced=12)
    # A partial book that we DID model: the shortfall is the book's, not ours.
    payload["matches_analysed"] = 12
    payload["valid_feature_snapshots"] = 12
    readiness = analysis_readiness(payload, horizon="same_day")
    assert readiness["severity"] == SEVERITY_RETRY


def test_our_own_failures_are_never_excused_by_the_horizon():
    """A closed book excuses a missing board. It does not excuse a broken us."""
    from tennis_wc.pipeline_readiness import SEVERITY_ERROR, analysis_readiness

    payload = _empty_board()
    payload["source_errors"] = [{"source": "odds", "error": "403 from provider"}]
    readiness = analysis_readiness(payload, horizon="next_day")
    assert readiness["severity"] == SEVERITY_ERROR
    assert any("odds" in reason for reason in readiness["reasons"])


def test_horizon_is_derived_in_one_place():
    from tennis_wc.pipeline_readiness import horizon_for

    assert horizon_for("2026-08-12", "2026-08-11") == "next_day"
    assert horizon_for("2026-08-11", "2026-08-11") == "same_day"
    assert horizon_for("2026-08-10", "2026-08-11") == "past"


def test_notify_reads_the_shared_credentials_file_and_never_raises(
    tmp_path, monkeypatch
):
    """A notification that fails must not fail the run that needed it."""
    import scripts.tennis_daily_schedule as scheduler_module

    # `log` appends to data/logs/tennis_daily_schedule.log, which the live
    # scheduler reads. A test must not write into the record it is checking.
    monkeypatch.setattr(scheduler_module, "log", lambda *_a, **_k: None)

    env = tmp_path / "notify.env"
    env.write_text(
        "# comment\n"
        "export WC_NOTIFY_TELEGRAM_TOKEN=123:ABC\n"
        "export WC_NOTIFY_TELEGRAM_CHAT=456\n"
    )
    assert scheduler_module.notify_credentials(env) == ("123:ABC", "456")

    missing = tmp_path / "absent.env"
    assert scheduler_module.notify_credentials(missing) is None
    assert scheduler_module.notify("anything", path=missing) is False


def test_betting_content_targets_primary_and_extra_once(tmp_path):
    """Health is private; the formal betting card goes to Kelvin + Heison."""
    import scripts.tennis_daily_schedule as scheduler_module

    env = tmp_path / "notify.env"
    env.write_text(
        "WC_NOTIFY_TELEGRAM_TOKEN=123:ABC\n"
        "WC_NOTIFY_TELEGRAM_CHAT=kelvin\n"
        "WC_NOTIFY_TELEGRAM_EXTRA=heison, kelvin; heison\n"
    )
    assert scheduler_module.notify_targets(env) == ["kelvin"]
    assert scheduler_module.notify_targets(env, audience="content") == [
        "kelvin", "heison"
    ]


def test_content_notification_attempts_every_recipient(tmp_path, monkeypatch):
    import urllib.parse
    import urllib.request

    import scripts.tennis_daily_schedule as scheduler_module

    env = tmp_path / "notify.env"
    env.write_text(
        "WC_NOTIFY_TELEGRAM_TOKEN=123:ABC\n"
        "WC_NOTIFY_TELEGRAM_CHAT=kelvin\n"
        "WC_NOTIFY_TELEGRAM_EXTRA=heison\n"
    )
    recipients: list[str] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, timeout):
        assert timeout == 15
        body = urllib.parse.parse_qs(request.data.decode())
        recipients.append(body["chat_id"][0])
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(scheduler_module, "log", lambda *_a, **_k: None)
    assert scheduler_module.notify("what to bet", path=env, audience="content")
    assert recipients == ["kelvin", "heison"]


def test_daily_bet_message_contains_only_formal_recommendations(tmp_path):
    import scripts.tennis_daily_schedule as scheduler_module

    report = tmp_path / "Tennis_Daily_Report.txt"
    report.write_text(
        "🎾 Tennis Wong Choi 每日投注報告\n"
        "日期：2026-08-14\n\n"
        "## 🎯 今日落注建議（先睇呢度）\n\n"
        "今日結論：✅ 有 1 組已通過驗證嘅 prop 選擇。\n\n"
        "### 注 1｜✅ VALIDATED_SINGLE\n"
        "- 選擇：Player A Win ≥1 Set YES @ 1.80（A vs B）\n"
        "- 狀態：VALIDATED_SINGLE\n"
        "- 賠率：1.80｜建議注碼：0.5u\n"
        "- 校準命中概率：60.0%\n"
        "- 公式可信度：中（70/100）\n"
        "- 信心理據：too long for Telegram\n\n"
        "❌ 跳過：Match-winner reference only\n\n"
        "## 📎 觀察名單\n\n"
        "- Player B @ 2.50\n"
    )
    message = scheduler_module.daily_bet_message("2026-08-14", report)
    assert "Player A Win ≥1 Set" in message
    assert "0.5u" in message and "60.0%" in message
    assert "Player B" not in message
    assert "too long" not in message
    assert "Match-winner reference only" not in message


def test_daily_bet_message_sends_an_explicit_no_bet_conclusion(tmp_path):
    import scripts.tennis_daily_schedule as scheduler_module

    report = tmp_path / "Tennis_Daily_Report.txt"
    report.write_text(
        "## 🎯 今日落注建議（先睇呢度）\n\n"
        "今日結論：❌ 今日無清晰好注，建議唔落。\n"
        "（研究訊號只留喺觀察板。）\n\n"
        "## 📎 觀察名單\n- Player C\n"
    )
    message = scheduler_module.daily_bet_message("2026-08-15", report)
    assert "今日無清晰好注" in message
    assert "今日無正式推薦" in message
    assert "Player C" not in message


def test_the_health_line_is_emitted_on_a_no_bet_day(monkeypatch):
    """A quiet day and a dead pipeline must not look the same.

    An empty card is a legitimate output, which is why it hid a broken pipeline
    for two months once and three dark days again in August: nothing errored,
    nothing printed, and there was no number whose absence you could notice.
    """
    from scripts import tennis_daily_schedule as scheduler_module

    monkeypatch.setattr(scheduler_module, "_prop_counts",
                        lambda _d: {"props": 0, "value": 0, "pending_older": 0})
    line = scheduler_module.daily_health_line("2026-08-11", {
        "odds_coverage": {"fixtures": 57, "priced_matches": 53},
        "matches_analysed": 47,
        "readiness": {"severity": "ok", "horizon": "same_day"},
        "tracker_sync": {"clv": {"synced": 31, "props_synced": 0,
                                 "props_without_feed_identity": 0,
                                 "clv_updated": 20}},
        "cloudflare_deploy": {"attempted": True, "status": "failed"},
    })
    assert "2026-08-11" in line and "ok" in line
    assert "value 0" in line, "a zero has to be printed, not omitted"
    assert "57" in line and "53" in line
    assert "Dashboard failed" in line


def test_the_health_push_is_opt_in(monkeypatch):
    """Building the alarm is mine; deciding the phone buzzes is Kelvin's."""
    from scripts import tennis_daily_schedule as scheduler_module

    monkeypatch.delenv("TENNIS_NOTIFY_HEALTH", raising=False)
    sent: list = []
    monkeypatch.setattr(scheduler_module, "notify", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(scheduler_module, "log", lambda *a, **k: None)
    monkeypatch.setattr(scheduler_module, "_prop_counts",
                        lambda _d: {"props": 1, "value": 1, "pending_older": 0})
    monkeypatch.setattr(scheduler_module, "run_cli_json", lambda *a, **k: {
        "odds_coverage": {"fixtures": 10, "priced_matches": 9},
        "matches_analysed": 9, "valid_feature_snapshots": 9, "source_errors": [],
    })
    scheduler_module.analyse_next_day("2026-08-11", today="2026-08-11")
    assert sent == [], "the health push must stay silent until it is switched on"


def test_daily_performance_message_separates_paper_from_live_and_lists_families():
    snapshot = {
        "paper": {
            "daily": {"settled": 4, "wins": 3, "pnl": 1.4, "roi": 0.35},
            "recent_14": {"settled": 43, "wins": 21, "pnl": -4.2, "roi": -0.0977},
            "overall": {"settled": 57, "wins": 29, "pnl": -4.765, "roi": -0.0836},
            "families": {
                "player_win_a_set": {
                    "settled": 57, "pnl": -4.765, "roi": -0.0836,
                    "recent_roi": -0.2144,
                },
                "player_aces": {
                    "settled": 26, "pnl": -2.824, "roi": -0.1086,
                    "recent_roi": -0.1086,
                },
            },
        },
        "live": {"settled": 0, "wins": 0, "pnl": 0.0, "roi": None},
        "scorecard": {
            "model": {"brier": 0.2127}, "market": {"brier": 0.1962},
        },
        "gate": {"enabled_families": []},
        "pending_value_older": 2,
    }

    message = scheduler.daily_performance_message("2026-08-20", snapshot)

    assert "紙上盤" in message and "實盤 0 注" in message
    assert "當日 4 注" in message and "+1.400u" in message
    assert "近14日 43 注" in message and "-4.200u" in message
    assert "贏一盤" in message and "球員 Ace" in message
    assert "Model 0.2127" in message and "Market 0.1962" in message
    assert "RESEARCH_ONLY" in message and "未結算 2" in message


def test_review_sends_daily_performance_when_enabled(monkeypatch):
    sent = []
    payload = {"review_report_path": "/tmp/review.md"}
    monkeypatch.setenv("TENNIS_NOTIFY_PERFORMANCE", "1")
    monkeypatch.setattr(scheduler, "top_up_lowtier_corpus", lambda *_a: None)
    monkeypatch.setattr(scheduler, "run_cli_json", lambda *_a: payload)
    monkeypatch.setattr(scheduler, "notify_daily_performance",
                        lambda day: sent.append(day) or True)
    monkeypatch.setattr(scheduler, "log", lambda *_a: None)

    assert scheduler.review_previous_day("2026-08-20") == payload
    assert sent == ["2026-08-20"]


def test_completed_same_day_card_sends_formal_bets_when_enabled(monkeypatch):
    """The content push belongs after the readiness gate, on same-day only."""
    from scripts import tennis_daily_schedule as scheduler_module

    payload = {
        "odds_coverage": {"fixtures": 60, "priced_matches": 40},
        "matches_analysed": 40,
        "valid_feature_snapshots": 40,
        "source_errors": [],
        "report_path": "/tmp/Tennis_Daily_Report.txt",
    }
    sent: list[tuple[str, dict]] = []
    monkeypatch.setenv("TENNIS_NOTIFY_BETS", "1")
    monkeypatch.delenv("TENNIS_NOTIFY_HEALTH", raising=False)
    monkeypatch.setattr(scheduler_module, "run_cli_json", lambda *_a, **_k: payload)
    monkeypatch.setattr(scheduler_module, "notify_daily_bets",
                        lambda day, result: sent.append((day, result)) or True)
    monkeypatch.setattr(scheduler_module, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(scheduler_module, "_prop_counts",
                        lambda _d: {"props": 1, "value": 1, "pending_older": 0})

    scheduler_module.analyse_next_day("2026-08-14", today="2026-08-14")

    assert sent == [("2026-08-14", payload)]


# --------------------------------------------------------------------------- #
# Phase 0.2's exit test, checkable (2026-08-11)
# --------------------------------------------------------------------------- #
def _log_lines(entries):
    """entries: (stamp, source, mode, priced|None)"""
    out = []
    for stamp, source, mode, priced in entries:
        out.append(f"[{stamp}] Starting SAME-DAY refresh for {stamp[:10]} "
                   f"(no review, no archive). run_source={source} mode={mode}")
        if priced is not None:
            out.append(
                f'[{stamp}] HEALTH_JSON {{"date": "{stamp[:10]}", '
                f'"horizon": "same_day", "severity": "ok", "fixtures": 57, '
                f'"priced": {priced}, "analysed": 47}}'
            )
    return "\n".join(out) + "\n"


def test_the_exit_test_does_not_accept_a_run_someone_typed(tmp_path):
    """A manual morning pass looked identical to a scheduled one in the log.

    That is precisely how three days went dark: the only scheduled job was the
    18:00 one, which asks for a book that is not open, and the pass that works
    had always been run by hand. When the hand stopped, nothing changed in the
    log. "Verified from the log rather than assumed" needs the log to record
    who started the run.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "verify_scheduled_runs",
        "/Users/imac/Antigravity-repo/tennis-wong-choi/scripts/verify_scheduled_runs.py",
    )
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)

    manual = tmp_path / "manual.log"
    manual.write_text(_log_lines([
        ("2026-08-11T09:00:04+10:00", "manual", "card", 53),
        ("2026-08-12T09:00:04+10:00", "manual", "card", 51),
    ]))
    runs = verifier.read_runs(manual)
    assert all(run["source"] == "manual" for run in runs)
    assert not [r for r in runs if r["source"] == "launchd"], (
        "two hand-typed days must not satisfy a test about the scheduler"
    )

    scheduled = tmp_path / "scheduled.log"
    scheduled.write_text(_log_lines([
        ("2026-08-11T09:00:04+10:00", "launchd", "card", 53),
        ("2026-08-12T09:00:04+10:00", "launchd", "card", 51),
    ]))
    runs = verifier.read_runs(scheduled)
    cards = [r for r in runs if r["mode"] == "card" and r["source"] == "launchd"]
    assert len(cards) == 2
    assert all((run["health"] or {}).get("priced") for run in cards)
    assert verifier._longest_consecutive(["2026-08-11", "2026-08-12"]) == 2
    assert verifier._longest_consecutive(["2026-08-11", "2026-08-13"]) == 1


def test_a_scheduled_run_that_priced_nothing_does_not_count(tmp_path):
    """An empty card is a legitimate output and not evidence the job works."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "verify_scheduled_runs",
        "/Users/imac/Antigravity-repo/tennis-wong-choi/scripts/verify_scheduled_runs.py",
    )
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)

    log = tmp_path / "empty.log"
    log.write_text(_log_lines([
        ("2026-08-11T09:00:04+10:00", "launchd", "card", 0),
        ("2026-08-12T09:00:04+10:00", "launchd", "card", 0),
    ]))
    runs = verifier.read_runs(log)
    assert all((run["health"] or {}).get("priced") == 0 for run in runs)


def test_a_missing_health_record_is_unknown_not_zero(tmp_path, monkeypatch, capsys):
    """A child can build the card then die before the scheduler writes health.

    That happened on 2026-08-13 when the post-success dashboard deploy failed.
    The provider's priced count was not zero; the verifier simply did not have
    one. Unknown and observed-zero must never be printed as the same number.
    """
    from scripts import verify_scheduled_runs as verifier

    log = tmp_path / "missing-health.log"
    log.write_text(_log_lines([
        ("2026-08-13T09:00:04+10:00", "launchd", "card", None),
    ]))
    monkeypatch.setattr(
        "sys.argv", ["verify_scheduled_runs.py", "--log", str(log)]
    )

    assert verifier.main() == 1
    output = capsys.readouterr().out
    assert "missing HEALTH_JSON: 1" in output
    assert "UNKNOWN, not zero" in output
    assert "2026-08-13    None" in output


def test_a_kickstarted_run_does_not_satisfy_the_scheduled_exit_test():
    """`run_source=launchd` says launchd started it, not that the schedule did.

    `launchctl kickstart` produces a genuine launchd run at any hour. Without the
    clock, a wiring test typed by hand would satisfy the exit test it was meant
    to prepare for -- the one clause that exists to stop exactly that kind of
    self-deception.
    """
    from scripts.verify_scheduled_runs import _near_scheduled_time

    assert _near_scheduled_time("2026-08-12T09:00:04+10:00", 9, 45) is True
    assert _near_scheduled_time("2026-08-12T09:41:00+10:00", 9, 45) is True
    assert _near_scheduled_time("2026-08-11T19:52:13+10:00", 9, 45) is False
    assert _near_scheduled_time("2026-08-12T23:58:00+10:00", 9, 45) is False
    assert _near_scheduled_time("not a timestamp", 9, 45) is False


def test_captured_output_elision_states_its_own_line_count():
    """A silent truncation reads as "that was all there was"."""
    import scripts.tennis_daily_schedule as sched

    summarised = sched.summarise_captured_output(
        "\n".join(f"line {n}" for n in range(500)))
    lines = summarised.splitlines()
    assert lines[0] == "line 0"
    assert lines[-1] == "line 499"
    elision = [line for line in lines if "elided" in line]
    assert len(elision) == 1
    expected = 500 - sched.CAPTURED_HEAD_LINES - sched.CAPTURED_TAIL_LINES
    assert str(expected) in elision[0]


def test_short_output_is_left_exactly_as_it_was():
    import scripts.tennis_daily_schedule as sched

    output = "\n".join(f"line {n}" for n in range(5))
    assert sched.summarise_captured_output(output) == output


def test_log_rotates_at_the_cap_and_keeps_generations(tmp_path, monkeypatch):
    import scripts.tennis_daily_schedule as sched

    monkeypatch.setattr(sched, "MAX_LOG_BYTES", 100)
    path = tmp_path / "s.log"
    path.write_text("x" * 150)
    assert sched.rotate_log_if_needed(path) is True
    assert (tmp_path / "s.log.1").read_text() == "x" * 150
    assert not path.exists()

    path.write_text("y" * 150)
    assert sched.rotate_log_if_needed(path) is True
    assert (tmp_path / "s.log.1").read_text() == "y" * 150
    assert (tmp_path / "s.log.2").read_text() == "x" * 150


def test_log_below_the_cap_is_left_alone(tmp_path, monkeypatch):
    import scripts.tennis_daily_schedule as sched

    monkeypatch.setattr(sched, "MAX_LOG_BYTES", 1_000_000)
    path = tmp_path / "s.log"
    path.write_text("small")
    assert sched.rotate_log_if_needed(path) is False
    assert path.read_text() == "small"


def test_the_exit_test_still_sees_a_morning_that_has_rotated_away(tmp_path):
    """Rotation must not be able to erase one of the two mornings."""
    from scripts.verify_scheduled_runs import read_runs

    live = tmp_path / "tennis_daily_schedule.log"
    rotated = tmp_path / "tennis_daily_schedule.log.1"
    rotated.write_text(
        "[2026-08-12T09:00:04+10:00] Starting SAME-DAY refresh "
        "run_source=launchd mode=card\n"
        '[2026-08-12T09:06:00+10:00] HEALTH_JSON {"priced": 40}\n'
    )
    live.write_text(
        "[2026-08-13T09:00:07+10:00] Starting SAME-DAY refresh "
        "run_source=launchd mode=card\n"
        '[2026-08-13T09:05:00+10:00] HEALTH_JSON {"priced": 38}\n'
    )
    runs = read_runs(live)
    assert [run["started_at"][:10] for run in runs] == ["2026-08-12", "2026-08-13"]
    assert [run["health"]["priced"] for run in runs] == [40, 38]


def test_launchd_capture_is_trimmed_from_the_front_keeping_the_tail(tmp_path, monkeypatch):
    """launchd never rotates its own capture and rotation needs root.

    The tail is kept because that is where a fresh failure is, and the file is
    trimmed in place rather than renamed because launchd holds the descriptor
    open for the current run.
    """
    import scripts.tennis_daily_schedule as sched

    monkeypatch.setattr(sched, "MAX_LOG_BYTES", 1000)
    path = tmp_path / "launchd.card.stdout.log"
    path.write_bytes(b"OLD" * 400 + b"NEWEST-LINE\n")
    assert sched.trim_launchd_capture(path) is True
    text = path.read_text()
    assert "NEWEST-LINE" in text
    assert "trimmed by the scheduler" in text
    assert path.stat().st_size < 1000


def test_launchd_capture_below_the_cap_is_untouched(tmp_path, monkeypatch):
    import scripts.tennis_daily_schedule as sched

    monkeypatch.setattr(sched, "MAX_LOG_BYTES", 1_000_000)
    path = tmp_path / "launchd.card.stdout.log"
    path.write_text("short\n")
    assert sched.trim_launchd_capture(path) is False
    assert path.read_text() == "short\n"


def test_a_missing_launchd_capture_is_not_an_error(tmp_path):
    import scripts.tennis_daily_schedule as sched

    assert sched.trim_launchd_capture(tmp_path / "never-written.log") is False


def test_headroom_is_measured_against_the_database_size(tmp_path):
    import scripts.tennis_daily_schedule as sched

    db = tmp_path / "tennis_wc.db"
    db.write_bytes(b"x" * 1024)
    result = sched.disk_headroom(db)
    # 2x of 1KB is under the floor, so the floor governs.
    assert result["required_bytes"] == 2 * 1024 ** 3
    assert "required for a" in result["detail"]


def test_headroom_failure_is_reported_not_swallowed(tmp_path, monkeypatch):
    """A run that cannot write looks exactly like a run that found nothing."""
    import shutil

    import scripts.tennis_daily_schedule as sched

    db = tmp_path / "tennis_wc.db"
    db.write_bytes(b"x" * 4096)
    monkeypatch.setattr(
        shutil, "disk_usage",
        lambda _path: type("U", (), {"free": 1024, "total": 0, "used": 0})())
    result = sched.disk_headroom(db)
    assert result["ok"] is False
    assert result["free_bytes"] == 1024


def _run_card_mode(monkeypatch, tmp_path, raiser):
    """Drive main() in card mode with a chosen failure, capturing notifications."""
    import scripts.tennis_daily_schedule as sched

    sent: list[str] = []
    monkeypatch.setattr(sched, "LOG_DIR", tmp_path)
    monkeypatch.setattr(sched, "notify", lambda text, **_kw: sent.append(text) or True)
    monkeypatch.setattr(sched, "disk_headroom",
                        lambda *_a, **_k: {"ok": True, "detail": "test"})
    monkeypatch.setattr(sched, "ensure_live_network", lambda: None)
    monkeypatch.setattr(sched, "run_cli", lambda *_a, **_k: "")
    monkeypatch.setattr(sched, "analyse_next_day", raiser)
    code = sched.main(["--source", "launchd", "--refresh-today"])
    return code, sent, (tmp_path / "tennis_daily_schedule.log").read_text()


def test_an_empty_board_on_the_morning_pass_notifies_and_exits_70(monkeypatch, tmp_path):
    """0.3's clause: a broken run produces a notification within one cycle.

    An empty listing for D-1 is normal and an empty listing for D never is, and
    the two used to produce the same log line -- the whole reason three dark days
    passed unnoticed.
    """
    import scripts.tennis_daily_schedule as sched

    def raiser(*_a, **_k):
        raise sched.AnalysisBoardMissing("0 events for today from sportsbet")

    code, sent, log_text = _run_card_mode(monkeypatch, tmp_path, raiser)
    assert code == 70
    assert len(sent) == 1
    assert "出唔到咭" in sent[0]
    assert "0 events for today" in sent[0]
    assert "BOARD MISSING" in log_text


def test_a_temporary_failure_exits_75_and_stays_quiet(monkeypatch, tmp_path):
    """Retryable is not dark. An alarm that fires on both gets muted."""
    import scripts.tennis_daily_schedule as sched

    def raiser(*_a, **_k):
        raise sched.TemporaryDataUnavailable("listing fetch timed out")

    code, sent, log_text = _run_card_mode(monkeypatch, tmp_path, raiser)
    assert code == 75
    assert sent == []
    assert "TEMPORARY DATA FAILURE" in log_text


def test_the_health_line_is_legible_on_the_real_payload_shape(monkeypatch):
    """`? (?)` means the readiness block is missing, and must not read as normal.

    cli.py sets payload["readiness"] with severity and horizon. A health line
    showing "?" therefore means the pipeline stopped populating it, not that the
    day was quiet -- so the two must be distinguishable at a glance.
    """
    import scripts.tennis_daily_schedule as sched

    monkeypatch.setattr(sched, "_prop_counts", lambda _date: {
        "props": 47, "value": 0, "pending_older": 0})
    payload = {
        "odds_coverage": {"fixtures": 25, "priced_matches": 25},
        "matches_analysed": 25,
        "readiness": {"status": "ready", "severity": "OK", "horizon": "same_day"},
    }
    line = sched.daily_health_line("2026-08-12", payload)
    assert "OK (same_day)" in line
    assert "?" not in line.splitlines()[0]

    without = sched.daily_health_line("2026-08-12",
                                      {k: v for k, v in payload.items()
                                       if k != "readiness"})
    assert "? (?)" in without.splitlines()[0]


def test_dashboard_auto_settlement_runs_after_native_review(monkeypatch, tmp_path):
    import scripts.tennis_daily_schedule as sched

    settlement = tmp_path / "settle_dashboard_bets.py"
    settlement.write_text("# test", encoding="utf-8")
    calls = []

    class Result:
        returncode = 0
        stdout = '{"applied": 2}'

    monkeypatch.setattr(sched, "DASHBOARD_SETTLEMENT", settlement)
    monkeypatch.setattr(sched, "PYTHON", tmp_path / "python")
    monkeypatch.setattr(
        sched.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)) or Result(),
    )
    monkeypatch.setattr(sched, "log", lambda *_args, **_kwargs: None)

    assert sched.sync_dashboard_settlements("2026-08-12") is True
    assert calls[0][0][-3:] == ["--date", "2026-08-12", "--apply"]
    assert calls[0][1]["timeout"] == 90


def test_dashboard_auto_settlement_is_best_effort(monkeypatch, tmp_path):
    import scripts.tennis_daily_schedule as sched

    settlement = tmp_path / "settle_dashboard_bets.py"
    settlement.write_text("# test", encoding="utf-8")
    messages = []
    monkeypatch.setattr(sched, "DASHBOARD_SETTLEMENT", settlement)
    monkeypatch.setattr(
        sched.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("offline")),
    )
    monkeypatch.setattr(sched, "log", messages.append)

    assert sched.sync_dashboard_settlements("2026-08-12") is False
    assert any("auto-settlement failed" in message for message in messages)


# --------------------------------------------------------------------------- #
# The evening card (2026-08-16)
#
# `match_date` is the Sydney calendar date and the formal card went out at
# 09:24 Sydney, so matches in the small hours were over before anyone was told:
# 35.9% of the matches on a pushed card had already started. The evening pass
# already analyses and prices that cohort -- it was simply barred from sending.
# --------------------------------------------------------------------------- #


def _next_day_payload():
    return {
        "odds_coverage": {"fixtures": 21, "priced_matches": 12},
        "matches_analysed": 12,
        "valid_feature_snapshots": 12,
        "source_errors": [],
        "report_path": "/tmp/Tennis_Daily_Report.txt",
    }


def _run_next_day(monkeypatch, sent):
    from scripts import tennis_daily_schedule as scheduler_module

    payload = _next_day_payload()
    monkeypatch.delenv("TENNIS_NOTIFY_HEALTH", raising=False)
    monkeypatch.setattr(scheduler_module, "run_cli_json", lambda *_a, **_k: payload)
    monkeypatch.setattr(
        scheduler_module, "notify_daily_bets",
        lambda day, result, **kw: sent.append((day, kw.get("early", False))) or True,
    )
    monkeypatch.setattr(scheduler_module, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(scheduler_module, "_prop_counts",
                        lambda _d: {"props": 1, "value": 1, "pending_older": 0})
    scheduler_module.analyse_next_day("2026-08-17", today="2026-08-16")
    return payload


def test_evening_pass_sends_an_early_card_when_enabled(monkeypatch):
    sent: list[tuple[str, bool]] = []
    monkeypatch.setenv("TENNIS_NOTIFY_EARLY_BETS", "1")
    monkeypatch.delenv("TENNIS_NOTIFY_BETS", raising=False)
    _run_next_day(monkeypatch, sent)
    assert sent == [("2026-08-17", True)]


def test_evening_pass_stays_silent_by_default(monkeypatch):
    sent: list[tuple[str, bool]] = []
    monkeypatch.delenv("TENNIS_NOTIFY_EARLY_BETS", raising=False)
    monkeypatch.delenv("TENNIS_NOTIFY_BETS", raising=False)
    _run_next_day(monkeypatch, sent)
    assert sent == []


def test_the_morning_switch_does_not_turn_on_the_evening_card(monkeypatch):
    """Two independent switches. Turning the evening card off must never be a
    reason the day's real card stops going out, or the reverse."""
    sent: list[tuple[str, bool]] = []
    monkeypatch.setenv("TENNIS_NOTIFY_BETS", "1")
    monkeypatch.delenv("TENNIS_NOTIFY_EARLY_BETS", raising=False)
    _run_next_day(monkeypatch, sent)
    assert sent == []


def test_the_early_card_says_the_board_is_half_open(tmp_path):
    """It is sent precisely because it is incomplete; hiding that would make it
    indistinguishable from the finished card."""
    import scripts.tennis_daily_schedule as scheduler_module

    report = tmp_path / "Tennis_Daily_Report.txt"
    report.write_text(
        "## 🎯 今日落注建議（先睇呢度）\n\n"
        "今日結論：✅ 有 1 組已通過驗證嘅 prop 選擇。\n\n"
        "### 注 1｜✅ VALIDATED_SINGLE\n"
        "- 選擇：Player A Win ≥1 Set YES @ 1.80（A vs B）\n"
        "- 開賽：08-17 01:00 悉尼時間（仲有 5 小時 12 分）\n"
        "- 賠率：1.80｜建議注碼：0.5u\n\n"
        "## 📎 觀察名單\n- Player C\n",
        encoding="utf-8",
    )
    early = scheduler_module.daily_bet_message("2026-08-17", report, early=True)
    assert "早報" in early
    assert "盤口未開齊" in early
    assert "01:00 悉尼時間" in early

    normal = scheduler_module.daily_bet_message("2026-08-17", report)
    assert "早報" not in normal
    assert "盤口未開齊" not in normal


def test_the_card_carries_the_start_time_so_the_window_is_visible(tmp_path):
    """The card's job is to be actionable. Before 2026-08-16 it printed no start
    time at all, so "can I still place this?" was unanswerable from the push."""
    import scripts.tennis_daily_schedule as scheduler_module

    report = tmp_path / "Tennis_Daily_Report.txt"
    report.write_text(
        "## 🎯 今日落注建議（先睇呢度）\n\n"
        "今日結論：✅ 有 1 組已通過驗證嘅 prop 選擇。\n\n"
        "### 注 1｜✅ VALIDATED_SINGLE\n"
        "- 選擇：Player A Win ≥1 Set YES @ 1.80（A vs B）\n"
        "- 開賽：08-17 01:00 悉尼時間（⚠️ 仲有 42 分）\n"
        "- 賠率：1.80｜建議注碼：0.5u\n\n"
        "## 📎 觀察名單\n- Player C\n",
        encoding="utf-8",
    )
    message = scheduler_module.daily_bet_message("2026-08-17", report)
    assert "開賽：08-17 01:00 悉尼時間" in message
    assert "仲有 42 分" in message
