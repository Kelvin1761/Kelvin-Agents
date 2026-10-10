from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

AUTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO))
import nba_daily_schedule as schedule
sys.path.insert(0, str(AUTO.parent))
sys.path.insert(0, str(AUTO.parent / "nba_data_extractor" / "scripts"))
import nba_orchestrator as orchestrator
import claw_sportsbet_odds as claw


def child_result(code=75, **changes):
    payload = {"status": "waiting_player_markets", "reason": "player_markets_not_open", "waiting_games": ["MEM_CHI"]}
    payload.update(changes)
    return subprocess.CompletedProcess([], code, "NBA_PIPELINE_RESULT: " + json.dumps(payload) + "\n", "")


class MarketWaitingTests(unittest.TestCase):
    def test_child_waiting_is_distinct_from_analysis_failure(self):
        log = mock.Mock()
        with mock.patch.object(schedule, "_run", return_value=child_result()):
            with self.assertRaises(schedule.PlayerMarketsWaiting) as raised:
                schedule._run_orchestrator_refresh("2026-10-10", Path("/unused"), refreshable_tags={"MEM_CHI"}, schedule_tags={"MEM_CHI"}, log=log)
        self.assertEqual(raised.exception.games, ["MEM_CHI"])
        self.assertEqual(log.step.call_args.args[:2], ("orchestrator", "waiting"))

    def test_exit_75_without_verified_waiting_reason_is_a_failure(self):
        result = subprocess.CompletedProcess([], 75, "player_markets_not_open in an unrelated diagnostic", "network unavailable")
        with mock.patch.object(schedule, "_run", return_value=result):
            with self.assertRaisesRegex(schedule.TemporaryFailure, "orchestrator_exit_75") as raised:
                schedule._run_orchestrator_refresh("2026-10-10", Path("/unused"), refreshable_tags={"MEM_CHI"}, schedule_tags={"MEM_CHI"}, log=mock.Mock())
        self.assertNotIsInstance(raised.exception, schedule.PlayerMarketsWaiting)

    def test_real_failure_and_malformed_result_cannot_become_waiting(self):
        for result in (child_result(code=1), child_result(waiting_games=[]), child_result(waiting_games=[None]), child_result(reason="network_failure"), subprocess.CompletedProcess([], 75, "NBA_PIPELINE_RESULT: []", ""), subprocess.CompletedProcess([], 75, "NBA_PIPELINE_RESULT: {", "")):
            with self.subTest(result=result):
                self.assertEqual(schedule.waiting_player_games(result), [])

    def test_incomplete_warmup_refreshes_source_on_each_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            cached = folder / "Sportsbet_Odds_MEM_CHI.json"
            cached.write_text('{"player_props":{}}')
            count = 0
            def refresh(*args, **kwargs):
                nonlocal count
                count += 1
                cached.write_text(json.dumps({"source_read": count}))
            def rerun(*args, **kwargs):
                self.assertEqual(json.loads(cached.read_text())["source_read"], count)
                raise schedule.PlayerMarketsWaiting(["MEM_CHI"])
            with mock.patch.object(schedule, "load_espn_schedule", return_value=({"MEM_CHI"}, True)), mock.patch.object(schedule, "live_dir", return_value=folder), mock.patch.object(schedule, "latest_snapshot", return_value=None), mock.patch.object(schedule, "refresh_sportsbet_odds", side_effect=refresh) as fetched, mock.patch.object(schedule, "_run_orchestrator_refresh", side_effect=rerun), mock.patch.object(schedule, "create_prediction_snapshot") as snapshot:
                for _ in range(2):
                    with self.assertRaises(schedule.PlayerMarketsWaiting):
                        schedule.run_pregame("2026-10-10", mock.Mock(), freshness_role=schedule.FreshnessRole.WARMUP)
            self.assertEqual(fetched.call_count, 2)
            snapshot.assert_not_called()

    def test_waiting_notification_and_manifest_are_partial_not_success_or_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            output = io.StringIO()
            with mock.patch.object(schedule, "STATE_DIR", folder / "state"), mock.patch.object(schedule, "LOG_DIR", folder / "logs"), mock.patch.object(schedule, "load_espn_events", return_value=({}, True)), mock.patch.object(schedule, "run_pregame", side_effect=schedule.PlayerMarketsWaiting(["MEM_CHI"])), mock.patch.object(schedule, "notify_once", return_value={"status": "sent"}) as notify, mock.patch.object(sys, "argv", ["scheduler", "--mode", "pregame", "--date", "2026-10-10"]), contextlib.redirect_stdout(output):
                code = schedule.main()
            self.assertEqual(code, 75)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["status"], "partial")
            self.assertEqual(payload["reason"], "player_markets_not_open")
            self.assertEqual(payload["waiting_games"], ["MEM_CHI"])
            log = json.loads(next((folder / "logs").glob("*.json")).read_text())
            self.assertEqual(log["status"], "partial")
            self.assertEqual(log["errors"], [])
            self.assertEqual(log["waiting_games"], ["MEM_CHI"])
            message = notify.call_args.args[1]
            self.assertIn("等待球員盤口", message)
            self.assertIn("尚未完成", message)
            self.assertNotIn("暫時失敗", message)
            self.assertEqual(notify.call_args.args[0], "waiting-player-markets:2026-10-10")

    def test_real_failure_still_records_error_and_failure_notification(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with mock.patch.object(schedule, "STATE_DIR", folder / "state"), mock.patch.object(schedule, "LOG_DIR", folder / "logs"), mock.patch.object(schedule, "load_espn_events", return_value=({}, True)), mock.patch.object(schedule, "run_pregame", side_effect=schedule.TemporaryFailure("orchestrator_exit_1:all")), mock.patch.object(schedule, "notify_once", return_value={"status": "sent"}) as notify, mock.patch.object(sys, "argv", ["scheduler", "--mode", "pregame", "--date", "2026-10-10"]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(schedule.main(), 75)
            log = json.loads(next((folder / "logs").glob("*.json")).read_text())
            self.assertEqual(log["errors"], ["orchestrator_exit_1:all"])
            self.assertIn("暫時失敗", notify.call_args.args[1])

    def test_orchestrator_emits_machine_readable_waiting_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "Sportsbet_Odds_MEM_CHI.json").write_text(json.dumps({"target_analysis_date": "2026-10-10", "event_local_date": "2026-10-10", "matchup": "MEM @ CHI", "game_lines": {"ml_away": "2.2"}, "player_props": {}}))
            output = io.StringIO()
            with mock.patch.object(sys, "argv", ["orchestrator", "--date", "2026-10-10", "--auto", "--skip-cloudflare-deploy"]), mock.patch.object(orchestrator, "get_target_dir", return_value=str(folder)), mock.patch.object(orchestrator, "load_espn_schedule", return_value=({"MEM_CHI"}, True)), mock.patch.object(orchestrator, "run_script") as run, contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
                orchestrator.main()
            self.assertEqual(raised.exception.code, 75)
            result = subprocess.CompletedProcess([], 75, output.getvalue(), "")
            self.assertEqual(schedule.waiting_player_games(result), ["MEM_CHI"])
            run.assert_not_called()
            self.assertFalse((folder / "_prediction_snapshots").exists())

    def test_missing_game_data_keeps_coverage_blocked_and_emits_waiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "Sportsbet_Odds_MEM_CHI.json").write_text(json.dumps({"target_analysis_date": "2026-10-11", "event_local_date": "2026-10-11", "matchup": "MEM @ CHI", "game_lines": {"ml_away": "2.2"}, "player_props": {}}))
            output = io.StringIO()
            with mock.patch.object(sys, "argv", ["orchestrator", "--date", "2026-10-11", "--auto"]), mock.patch.object(orchestrator, "get_target_dir", return_value=str(folder)), mock.patch.object(orchestrator, "load_espn_schedule", return_value=({"MEM_CHI", "DAL_HOU"}, True)), mock.patch.object(orchestrator, "process_single_game") as analyze, mock.patch.object(orchestrator, "run_script") as run, contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
                orchestrator.main()
            self.assertEqual(raised.exception.code, 75)
            result = subprocess.CompletedProcess([], 75, output.getvalue(), "")
            self.assertEqual(schedule.waiting_game_markets(result), ["DAL_HOU"])
            analyze.assert_not_called()
            run.assert_not_called()
            self.assertFalse((folder / "_prediction_snapshots").exists())
            with mock.patch.object(schedule, "_run", return_value=result), self.assertRaises(schedule.GameMarketsWaiting):
                schedule._run_orchestrator_refresh("2026-10-11", folder, refreshable_tags={"MEM_CHI", "DAL_HOU"}, schedule_tags={"MEM_CHI", "DAL_HOU"}, log=mock.Mock())

    def test_game_data_waiting_records_missing_tags_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            output = io.StringIO()
            with mock.patch.object(schedule, "STATE_DIR", folder / "state"), mock.patch.object(schedule, "LOG_DIR", folder / "logs"), mock.patch.object(schedule, "load_espn_events", return_value=({}, True)), mock.patch.object(schedule, "run_pregame", side_effect=schedule.GameMarketsWaiting(["DAL_HOU"])), mock.patch.object(schedule, "notify_once", return_value={"status": "sent"}) as notify, mock.patch.object(sys, "argv", ["scheduler", "--mode", "pregame", "--date", "2026-10-11"]), contextlib.redirect_stdout(output):
                code = schedule.main()
            self.assertEqual(code, 75)
            self.assertEqual(json.loads(output.getvalue())["reason"], "sportsbet_game_data_missing")
            log = json.loads(next((folder / "logs").glob("*.json")).read_text())
            self.assertEqual(log["status"], "partial")
            self.assertEqual(log["errors"], [])
            self.assertEqual(log["waiting_games"], ["DAL_HOU"])
            self.assertIn("等待賽事盤口資料", notify.call_args.args[1])
            self.assertIn("尚未完成", notify.call_args.args[1])
            self.assertNotIn("暫時失敗", notify.call_args.args[1])

    def test_unverified_game_waiting_payload_remains_a_real_failure(self):
        for result in (child_result(status="waiting_game_markets", reason="network_error"), child_result(code=1, status="waiting_game_markets", reason="sportsbet_game_data_missing"), child_result(status="waiting_game_markets", reason="sportsbet_game_data_missing", waiting_games=[])):
            self.assertEqual(schedule.waiting_game_markets(result), [])

    def test_actual_full_game_handicap_format_keeps_away_spread(self):
        extractor = claw.SportsbetNBAExtractor(target_date="2026-10-10")
        book = {"markets": {"1": {"name": "Handicap Betting", "outcomeIds": [1, 2]}}, "outcomes": {
            "1": {"name": "Memphis Grizzlies", "winPrice": {"num": 890, "den": 1000}, "handicap": {"value": "-3.5", "display": "+3.5"}},
            "2": {"name": "Chicago Bulls", "winPrice": {"num": 910, "den": 1000}, "handicap": {"value": "-3.5", "display": "-3.5"}}
        }}
        markets = extractor._parse_normalized_markets(book)
        cleaned = extractor._clean_markets(markets)
        data = extractor._format_as_sportsbet("Memphis Grizzlies At Chicago Bulls", "MEM", "CHI", cleaned)
        self.assertEqual(data["game_lines"]["spread_away"], "+3.5")
        self.assertTrue(all(not players for players in data["player_props"].values()))
        self.assertIsNone(extractor._classify_market("1st Quarter Handicap Betting"))
        self.assertIsNone(extractor._classify_market("Pick Your Own Handicap"))
