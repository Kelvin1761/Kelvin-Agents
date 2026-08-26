from __future__ import annotations

import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo


AUTO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO_DIR))
import nba_daily_schedule as schedule  # noqa: E402


SYDNEY = ZoneInfo("Australia/Sydney")


class _Log:
    def __init__(self) -> None:
        self.steps = []

    def step(self, name, status, **detail):
        self.steps.append((name, status, detail))


def _complete_analysis(folder: Path, target_date: str, tag: str = "BOS_LAL") -> None:
    (folder / f"Sportsbet_Odds_{tag}.json").write_text(
        json.dumps({"target_analysis_date": target_date, "matchup": "BOS @ LAL"}),
        encoding="utf-8",
    )
    (folder / f"nba_game_data_{tag}.json").write_text("{}\n", encoding="utf-8")
    (folder / f"Game_{tag}_Full_Analysis.md").write_text("A" * 2500, encoding="utf-8")
    (folder / "NBA_All_SGM_Report.txt").write_text("SGM\n", encoding="utf-8")
    (folder / "NBA_Banker_Report.txt").write_text("BANKER\n", encoding="utf-8")
    (folder / "_nba_session_state.md").write_text("PIPELINE_COMPLETE\n", encoding="utf-8")


class NbaDailyScheduleTests(unittest.TestCase):
    def test_evening_targets_tomorrow_and_morning_targets_today(self) -> None:
        evening = datetime(2026, 10, 20, 21, 0, tzinfo=SYDNEY)
        morning = datetime(2026, 10, 21, 6, 30, tzinfo=SYDNEY)
        self.assertEqual(schedule.pregame_target(evening).isoformat(), "2026-10-21")
        self.assertEqual(schedule.pregame_target(morning).isoformat(), "2026-10-21")

    def test_verified_sportsbet_tags_exclude_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _complete_analysis(folder, "2026-10-21", "BOS_LAL")
            (folder / "Sportsbet_Odds_NYK_MIA.json").write_text(
                json.dumps({"target_analysis_date": "2026-10-20"}), encoding="utf-8"
            )
            self.assertEqual(schedule.sportsbet_tags(folder, "2026-10-21"), ["BOS_LAL"])

    def test_analysis_gate_rejects_fill_and_missing_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _complete_analysis(folder, "2026-10-21")
            report = folder / "Game_BOS_LAL_Full_Analysis.md"
            report.write_text("[FILL]" + "A" * 2500, encoding="utf-8")
            (folder / "NBA_Banker_Report.txt").unlink()
            problems = schedule.validate_analysis(folder, "2026-10-21", ["BOS_LAL"])
            self.assertIn("fill_residual:Game_BOS_LAL_Full_Analysis.md", problems)
            self.assertIn("missing_or_empty:NBA_Banker_Report.txt", problems)

    def test_snapshot_copies_artifacts_with_hash_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _complete_analysis(folder, "2026-10-21")
            snapshot = schedule.create_prediction_snapshot(folder, "2026-10-21", ["BOS_LAL"])
            manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["game_tags"], ["BOS_LAL"])
            self.assertEqual(manifest["target_date"], "2026-10-21")
            self.assertEqual(manifest["season_context"]["season_phase"], "EARLY_REGULAR")
            self.assertEqual(manifest["snapshot_role"], "production")
            self.assertTrue(manifest["append_only"])
            self.assertEqual(len(manifest["files"]["Game_BOS_LAL_Full_Analysis.md"]["sha256"]), 64)
            self.assertEqual(
                (snapshot / "Game_BOS_LAL_Full_Analysis.md").read_text(encoding="utf-8"),
                "A" * 2500,
            )

    def test_offseason_pregame_is_dormant_without_orchestrator(self) -> None:
        log = _Log()
        with mock.patch.object(schedule, "load_espn_schedule", return_value=(set(), True)), mock.patch.object(
            schedule, "_run"
        ) as run:
            status = schedule.run_pregame("2026-08-25", log)
        self.assertEqual(status, "dormant")
        run.assert_not_called()

    def test_schedule_outage_is_not_false_dormant(self) -> None:
        log = _Log()
        with mock.patch.object(schedule, "load_espn_schedule", return_value=(set(), False)):
            with self.assertRaises(schedule.TemporaryFailure):
                schedule.run_pregame("2026-08-25", log)

    def test_offseason_with_unexpected_official_games_fails_closed(self) -> None:
        with mock.patch.object(
            schedule, "load_espn_schedule", return_value=({"BOS_LAL"}, True)
        ):
            with self.assertRaisesRegex(
                schedule.TemporaryFailure,
                "official_games_found_during_configured_off_season",
            ):
                schedule.run_pregame("2026-08-26", _Log())

    def test_preseason_runs_shadow_without_deploy_or_betting_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _complete_analysis(folder, "2026-10-10")
            snapshot = folder / "_prediction_snapshots" / "snapshot-1"
            snapshot.mkdir(parents=True)
            with mock.patch.object(
                schedule, "load_espn_schedule", return_value=({"BOS_LAL"}, True)
            ), mock.patch.object(
                schedule, "live_dir", return_value=folder
            ), mock.patch.object(
                schedule, "latest_snapshot", return_value=snapshot
            ), mock.patch.object(
                schedule, "_deploy"
            ) as deploy, mock.patch.object(
                schedule,
                "notify_once",
                return_value={"ok": True, "status": "sent"},
            ), mock.patch.object(
                schedule, "export_nba_snapshot"
            ) as export:
                status = schedule.run_pregame("2026-10-10", _Log())
            self.assertEqual(status, "shadow_complete")
            deploy.assert_not_called()
            export.assert_not_called()

    def test_warmup_snapshot_never_deploys_or_sends_content_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _complete_analysis(folder, "2026-10-21")
            snapshot = folder / "_prediction_snapshots" / "warmup"
            snapshot.mkdir(parents=True)
            with mock.patch.object(
                schedule, "load_espn_schedule", return_value=({"BOS_LAL"}, True)
            ), mock.patch.object(
                schedule, "live_dir", return_value=folder
            ), mock.patch.object(
                schedule, "latest_snapshot", return_value=snapshot
            ), mock.patch.object(
                schedule, "_deploy"
            ) as deploy, mock.patch.object(
                schedule, "export_nba_snapshot"
            ) as export, mock.patch.object(
                schedule,
                "notify_once",
                return_value={"ok": True, "status": "sent"},
            ):
                status = schedule.run_pregame(
                    "2026-10-21",
                    _Log(),
                    freshness_role=schedule.FreshnessRole.WARMUP,
                )
            self.assertEqual(status, "warmup_complete")
            deploy.assert_not_called()
            export.assert_not_called()

    def test_production_refresh_does_not_reuse_warmup_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _complete_analysis(folder, "2026-10-21")
            warmup = folder / "_prediction_snapshots" / "warmup"
            warmup.mkdir(parents=True)
            production = folder / "_prediction_snapshots" / "production"
            now = datetime(2026, 10, 21, 0, 30, tzinfo=SYDNEY)

            def latest(_folder, *, role=None):
                return warmup if role is schedule.FreshnessRole.WARMUP else None

            with mock.patch.object(
                schedule, "live_dir", return_value=folder
            ), mock.patch.object(
                schedule, "latest_snapshot", side_effect=latest
            ), mock.patch.object(
                schedule, "refresh_sportsbet_odds"
            ) as refresh, mock.patch.object(
                schedule, "_run_orchestrator_refresh"
            ) as orchestrate, mock.patch.object(
                schedule, "create_prediction_snapshot", return_value=production
            ) as create, mock.patch.object(
                schedule, "_deploy", return_value="ok"
            ), mock.patch.object(
                schedule,
                "notify_once",
                return_value={"ok": True, "status": "sent"},
            ), mock.patch.object(
                schedule, "export_nba_snapshot", return_value={}
            ), mock.patch.object(
                schedule, "nba_betting_message", return_value="card"
            ):
                status = schedule.run_pregame(
                    "2026-10-21",
                    _Log(),
                    freshness_role=schedule.FreshnessRole.PRODUCTION,
                    at=now,
                    schedule_events=({"BOS_LAL": now + timedelta(hours=8)}, True),
                )
            self.assertEqual(status, "complete")
            refresh.assert_called_once()
            orchestrate.assert_called_once()
            self.assertIs(
                create.call_args.kwargs["role"], schedule.FreshnessRole.PRODUCTION
            )

    def test_final_refresh_updates_only_unstarted_games(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _complete_analysis(folder, "2026-10-21", "BOS_LAL")
            _complete_analysis(folder, "2026-10-21", "NYK_MIA")
            production = folder / "_prediction_snapshots" / "production"
            production.mkdir(parents=True)
            (production / "manifest.json").write_text(
                '{"snapshot_role":"production"}\n', encoding="utf-8"
            )
            final = folder / "_prediction_snapshots" / "final"
            now = datetime(2026, 10, 21, 6, 30, tzinfo=SYDNEY)
            started_before = schedule._artifact_hashes(folder, {"BOS_LAL"})

            def latest(_folder, *, role=None):
                return production if role is schedule.FreshnessRole.PRODUCTION else None

            def rerun(_date, _folder, *, refreshable_tags, schedule_tags, log):
                self.assertEqual(refreshable_tags, {"NYK_MIA"})
                self.assertEqual(schedule_tags, {"BOS_LAL", "NYK_MIA"})
                (folder / "nba_game_data_NYK_MIA.json").write_text(
                    '{"refreshed":true}\n', encoding="utf-8"
                )

            with mock.patch.object(
                schedule, "live_dir", return_value=folder
            ), mock.patch.object(
                schedule, "latest_snapshot", side_effect=latest
            ), mock.patch.object(
                schedule, "refresh_sportsbet_odds"
            ), mock.patch.object(
                schedule, "_run_orchestrator_refresh", side_effect=rerun
            ), mock.patch.object(
                schedule, "create_prediction_snapshot", return_value=final
            ) as create, mock.patch.object(
                schedule, "_deploy", return_value="ok"
            ), mock.patch.object(
                schedule,
                "notify_once",
                return_value={"ok": True, "status": "sent"},
            ), mock.patch.object(
                schedule, "export_nba_snapshot", return_value={}
            ), mock.patch.object(
                schedule, "nba_betting_message", return_value="card"
            ):
                status = schedule.run_pregame(
                    "2026-10-21",
                    _Log(),
                    freshness_role=schedule.FreshnessRole.FINAL_REFRESH,
                    at=now,
                    schedule_events=(
                        {
                            "BOS_LAL": now - timedelta(minutes=1),
                            "NYK_MIA": now + timedelta(hours=2),
                        },
                        True,
                    ),
                )
            self.assertEqual(status, "complete")
            self.assertEqual(
                schedule._artifact_hashes(folder, {"BOS_LAL"}), started_before
            )
            self.assertEqual(create.call_args.kwargs["refreshable_tags"], ["NYK_MIA"])

    def test_final_refresh_without_material_change_keeps_production_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _complete_analysis(folder, "2026-10-21")
            production = folder / "_prediction_snapshots" / "production"
            production.mkdir(parents=True)
            (production / "manifest.json").write_text(
                '{"snapshot_role":"production"}\n', encoding="utf-8"
            )
            now = datetime(2026, 10, 21, 6, 30, tzinfo=SYDNEY)

            def latest(_folder, *, role=None):
                return production if role in {schedule.FreshnessRole.PRODUCTION, None} else None

            with mock.patch.object(
                schedule, "live_dir", return_value=folder
            ), mock.patch.object(
                schedule, "latest_snapshot", side_effect=latest
            ), mock.patch.object(
                schedule, "refresh_sportsbet_odds"
            ), mock.patch.object(
                schedule, "_run_orchestrator_refresh"
            ), mock.patch.object(
                schedule, "create_prediction_snapshot"
            ) as create, mock.patch.object(
                schedule, "_deploy"
            ) as deploy, mock.patch.object(
                schedule, "notify_once"
            ) as notify:
                status = schedule.run_pregame(
                    "2026-10-21",
                    _Log(),
                    freshness_role=schedule.FreshnessRole.FINAL_REFRESH,
                    at=now,
                    schedule_events=({"BOS_LAL": now + timedelta(hours=2)}, True),
                )
            self.assertEqual(status, "complete")
            create.assert_not_called()
            deploy.assert_not_called()
            notify.assert_not_called()

    def test_odds_refresh_restores_started_game_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            started = folder / "Sportsbet_Odds_BOS_LAL.json"
            unstarted = folder / "Sportsbet_Odds_NYK_MIA.json"
            started.write_text("old-started", encoding="utf-8")
            unstarted.write_text("old-unstarted", encoding="utf-8")

            def crawl(command, timeout=3600):
                started.write_text("new-started", encoding="utf-8")
                unstarted.write_text("new-unstarted", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

            with mock.patch.object(schedule, "_run", side_effect=crawl):
                schedule.refresh_sportsbet_odds(
                    folder,
                    "2026-10-21",
                    protected_tags={"BOS_LAL"},
                    log=_Log(),
                )
            self.assertEqual(started.read_text(encoding="utf-8"), "old-started")
            self.assertEqual(unstarted.read_text(encoding="utf-8"), "new-unstarted")

    def test_schedule_coverage_gate_rejects_missing_and_unexpected_games(self) -> None:
        problems = schedule.schedule_coverage_problems(
            {"BOS_LAL", "NYK_MIA"}, ["BOS_LAL", "CHI_WAS"]
        )
        self.assertEqual(
            problems,
            ["missing_official_game:NYK_MIA", "unexpected_game:CHI_WAS"],
        )

    def test_last_json_line_ignores_reflector_chatter(self) -> None:
        payload = schedule._last_json_line('progress\n{"status":"archived","analysis_date":"2026-10-21"}\n')
        self.assertEqual(payload["status"], "archived")

    def test_postgame_keeps_live_folder_when_results_are_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            result = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='{"status":"archive_skipped","message":"results not ready"}\n',
                stderr="",
            )
            with mock.patch.object(schedule, "live_dir", return_value=folder), mock.patch.object(
                schedule, "latest_snapshot", return_value=folder / "snapshot"
            ), mock.patch.object(schedule, "_run", return_value=result):
                with self.assertRaises(schedule.TemporaryFailure):
                    schedule.run_postgame("2026-10-21", _Log())
            self.assertTrue(folder.is_dir())

    def test_postgame_deploys_only_after_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            result = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='{"status":"archived","archive_path":"/archive/day"}\n',
                stderr="",
            )
            with mock.patch.object(schedule, "live_dir", return_value=folder), mock.patch.object(
                schedule, "latest_snapshot", return_value=folder / "snapshot"
            ), mock.patch.object(schedule, "_run", return_value=result), mock.patch.object(
                schedule, "_deploy", return_value="ok"
            ) as deploy, mock.patch.object(schedule, "notify_once"):
                status = schedule.run_postgame("2026-10-21", _Log())
            self.assertEqual(status, "archived")
            deploy.assert_called_once()

    def test_betting_message_uses_only_validated_export_values(self) -> None:
        snapshot = {
            "validation_status": "valid",
            "warnings": [],
            "recommendations": [
                {
                    "category": "banker",
                    "bet_type": "single",
                    "decision": "BET",
                    "validation_status": "valid",
                    "event_name": "BOS @ LAL",
                    "selection": "Player A 20+ PTS",
                    "odds": 1.72,
                    "metrics": {
                        "model_probability": 0.74,
                        "edge": 0.08,
                        "expected_value": 0.051,
                    },
                },
                {
                    "category": "sgm",
                    "bet_type": "combo",
                    "decision": "BET",
                    "validation_status": "valid",
                    "event_name": "BOS @ LAL",
                    "selection": "組合 1",
                    "odds": 2.12,
                    "risk": "Low",
                    "metrics": {"model_probability": 0.61, "average_edge": 0.05},
                    "legs": [
                        {
                            "selection": "Player A 20+ PTS",
                            "odds": 1.72,
                            "metrics": {
                                "model_probability": 0.74,
                                "expected_value": 0.051,
                            },
                        }
                    ],
                },
            ],
        }
        message = schedule.nba_betting_message("2026-10-21", snapshot)
        self.assertIn("Banker｜BOS @ LAL", message)
        self.assertIn("Player A 20+ PTS @1.72", message)
        self.assertIn("模型命中率 74.0%", message)
        self.assertIn("SGM｜BOS @ LAL｜@2.12", message)
        self.assertIn("模型唔保證盈利", message)

    def test_betting_message_emits_explicit_no_bet(self) -> None:
        message = schedule.nba_betting_message(
            "2026-10-21",
            {
                "validation_status": "blocked",
                "warnings": ["no_validated_nba_combos"],
                "recommendations": [],
            },
        )
        self.assertIn("今日 NO BET", message)

    def test_betting_message_blocks_partial_analysis(self) -> None:
        with self.assertRaisesRegex(ValueError, "telegram_betting_card_blocked:partial"):
            schedule.nba_betting_message(
                "2026-10-21",
                {
                    "validation_status": "partial",
                    "warnings": ["missing_matching_sportsbet_json"],
                    "recommendations": [
                        {
                            "decision": "BET",
                            "validation_status": "valid",
                            "category": "banker",
                        }
                    ],
                },
            )

    def test_notify_once_deduplicates_successful_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "telegram.json"
            with mock.patch.object(schedule, "NOTIFICATION_STATE", state_path), mock.patch.object(
                schedule,
                "send_message",
                return_value={"ok": True, "status": "sent"},
            ) as send:
                first = schedule.notify_once("same-key", "hello", audience="content")
                second = schedule.notify_once("same-key", "hello", audience="content")
            self.assertEqual(first["status"], "sent")
            self.assertEqual(second["status"], "duplicate_skipped")
            send.assert_called_once_with("hello", audience="content")

    def test_postgame_message_excludes_unresolved_legs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp)
            (archive / "Reflector_Training_Snapshot_2026-10-21.csv").write_text(
                "cleared,status\n1,verified\n0,verified\n,unresolved\n",
                encoding="utf-8",
            )
            (archive / "Dashboard_Settlement_Proposal_2026-10-21.json").write_text(
                json.dumps({"summary": {"nba": 2}}),
                encoding="utf-8",
            )
            (archive / "Reflector_Run_Summary_2026-10-21.json").write_text(
                json.dumps(
                    {
                        "ml_summary": {
                            "status": "ok",
                            "baseline": {"brier": 0.24},
                            "ml_model": {"brier": 0.21},
                        }
                    }
                ),
                encoding="utf-8",
            )
            message = schedule.postgame_message("2026-10-21", archive)
        self.assertIn("已核實 legs：2/3｜命中 1｜失手 1｜作廢 0", message)
        self.assertIn("命中率：50.0%", message)
        self.assertIn("未落實 legs：1", message)
        self.assertIn("baseline 0.24｜ML 0.21", message)


if __name__ == "__main__":
    unittest.main()
# Role-specific launchd jobs preserve the intended slot even after sleep/wake
# catch-up.  A shared pregame label cannot tell which original trigger woke it.
def test_launchd_pregame_jobs_pin_each_freshness_role() -> None:
    launchd = Path(schedule.__file__).resolve().parent / "launchd"
    expected = {
        "warmup": (21, 0, "warmup"),
        "production": (0, 30, "production"),
        "final-refresh": (6, 30, "final_refresh"),
    }
    for name, (hour, minute, role) in expected.items():
        payload = plistlib.loads(
            (launchd / f"com.antigravity.nba-wong-choi.{name}.plist.template").read_bytes()
        )
        assert payload["StartCalendarInterval"] == {"Hour": hour, "Minute": minute}
        assert payload["ProgramArguments"][-2:] == ["--freshness-role", role]

    assert not (launchd / "com.antigravity.nba-wong-choi.pregame.plist.template").exists()


def test_launchd_runner_dispatches_through_manifest_control_plane() -> None:
    runner = (Path(schedule.__file__).resolve().parent / "run_nba_daily_schedule.sh").read_text()
    assert "shared_wong_choi/control_plane.py" in runner
    assert "--domain nba --mode" in runner
