"""offload_prediction_snapshots: move, resolve, refuse silently-empty reads, and keep readers wired."""
from __future__ import annotations

import ast
import json
import shutil
import sys
import tempfile
import unittest
import warnings
from datetime import date
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(REPO))
import offload_prediction_snapshots as ops  # noqa: E402
import wongchoi_paths  # noqa: E402
from wongchoi_paths import SnapshotArchiveOffline, prediction_snapshot_dir  # noqa: E402

SNAP = "20261001T101500.000000+1000-abc123"


@unittest.skipUnless(shutil.which("ditto"), "macOS ditto only")
class OffloadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.au = base / "AU_Racing"
        self.archive = base / "archive"
        self.archive.mkdir()
        self.meeting = self.au / "Archive" / "2026-09-01 Randwick Race 1-8"
        snap = self.meeting / "_prediction_snapshots" / SNAP
        snap.mkdir(parents=True)
        (snap / "manifest.json").write_text('{"created_at": "2026-09-01T10:15:00+10:00"}')
        (snap / "Race_1_Auto_Scoring.csv").write_text("horse,score\nA,61\n")
        (self.meeting / "Meeting_Auto_Scoring.csv").write_text("x\n")
        self.before = ops.tree_digest(self.meeting / "_prediction_snapshots")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _offload(self) -> dict:
        return ops.offload(self.meeting, self.archive)

    def test_offload_moves_verified_copy_and_resolver_follows_marker(self) -> None:
        payload = self._offload()
        self.assertFalse((self.meeting / "_prediction_snapshots").exists())
        self.assertTrue((self.meeting / "Meeting_Auto_Scoring.csv").exists())
        self.assertEqual(payload["tree_sha256"], self.before["tree_sha256"])
        resolved = prediction_snapshot_dir(self.meeting, archive_root=self.archive)
        self.assertEqual(resolved, self.archive / "au" / self.meeting.name / "_prediction_snapshots")
        self.assertEqual(ops.tree_digest(resolved), self.before)
        # Engine replay reads the meeting name off the snapshot path's grandparent.
        self.assertEqual((resolved / SNAP / "x").parent.parent.parent.name, self.meeting.name)
        self.assertEqual(ops.verify(self.au, self.archive, deep=True), [])

    def test_unplugged_disk_raises_instead_of_reading_empty(self) -> None:
        self._offload()
        with self.assertRaises(SnapshotArchiveOffline):
            prediction_snapshot_dir(self.meeting, archive_root=Path(self.tmp.name) / "unmounted")
        shutil.rmtree(self.archive / "au")
        self.assertEqual(len(ops.verify(self.au, self.archive, deep=False)), 1)

    def test_meeting_without_snapshots_keeps_local_path(self) -> None:
        other = self.au / "Archive" / "2026-09-02 Nowhere"
        other.mkdir()
        self.assertEqual(prediction_snapshot_dir(other, archive_root=self.archive),
                         other / "_prediction_snapshots")

    def test_local_folder_wins_while_both_exist(self) -> None:
        self._offload()
        ops.restore(self.meeting, self.archive)
        self.assertFalse(wongchoi_paths.snapshot_offload_marker(self.meeting).exists())
        self.assertEqual(ops.tree_digest(self.meeting / "_prediction_snapshots"), self.before)
        self.assertEqual(prediction_snapshot_dir(self.meeting, archive_root=self.archive),
                         self.meeting / "_prediction_snapshots")

    def test_stale_partial_copy_is_replaced(self) -> None:
        dest = self.archive / "au" / self.meeting.name / "_prediction_snapshots" / SNAP
        dest.mkdir(parents=True)
        (dest / "manifest.json").write_text("truncated")
        self._offload()
        self.assertEqual(ops.verify(self.au, self.archive, deep=True), [])

    def test_only_old_archive_meetings_are_candidates(self) -> None:
        live = self.au / "2026-08-01 Live Race 1-8" / "_prediction_snapshots" / SNAP
        live.mkdir(parents=True)
        recent = self.au / "Archive" / "2026-10-25 Recent" / "_prediction_snapshots" / SNAP
        recent.mkdir(parents=True)
        got = ops.candidates(self.au, 30, date(2026, 11, 2))
        self.assertEqual(got, [self.meeting])

    def test_archive_on_internal_disk_is_refused(self) -> None:
        self.assertIsNotNone(ops.archive_ready(Path("/Volumes/__not_mounted__/x")))

    def test_new_snapshot_into_offloaded_meeting_is_refused(self) -> None:
        sys.path.insert(0, str(REPO / ".agents/skills"))
        from shared_wong_choi.immutable_snapshot import create_immutable_snapshot

        self._offload()
        with self.assertRaisesRegex(RuntimeError, "offloaded"):
            create_immutable_snapshot(self.meeting, domain="au", event_id=self.meeting.name,
                                      patterns=["Meeting_Auto_Scoring.csv"])
        self.assertFalse((self.meeting / "_prediction_snapshots").exists())

    def test_window_review_reads_offloaded_meeting(self) -> None:
        sys.path.insert(0, str(REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
        import au_window_review as wr

        self._offload()
        with mock.patch.object(wongchoi_paths, "SNAPSHOT_ARCHIVE_ROOT", self.archive):
            self.assertEqual(len(wr.stamped_snapshots(self.meeting)), 1)
        with mock.patch.object(wongchoi_paths, "SNAPSHOT_ARCHIVE_ROOT", Path(self.tmp.name) / "gone"):
            with self.assertRaises(SnapshotArchiveOffline):
                wr.stamped_snapshots(self.meeting)


@unittest.skipUnless(shutil.which("ditto"), "macOS ditto only")
class HkjcOffloadTest(unittest.TestCase):
    """HKJC meetings never move to Archive/, so their evidence paths point straight at the snapshots."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()  # research paths refuse /var -> /private/var
        self.hk = base / "HK_Racing"
        self.archive = base / "archive"
        self.archive.mkdir()
        self.meeting = self.hk / "2026-09-06_ShaTin"
        self.snap = self.meeting / "Prediction_Snapshots" / "20260905T214945+1000"
        self.snap.mkdir(parents=True)
        logic = self.snap / "Race_1_Logic.json"
        logic.write_text('{"race": 1}')
        digest = __import__("hashlib").sha256(logic.read_bytes()).hexdigest()
        (self.snap / "manifest.json").write_text(json.dumps({
            "immutable_prediction_snapshot": True,
            "files": [{"name": logic.name, "sha256": digest}]}))
        rb = self.meeting / "Prediction_Snapshots" / "Reverse_Bias"
        rb.mkdir()
        (rb / "reverse_bias_after_R2_abc.json").write_text("{}")
        self.patch = mock.patch.object(wongchoi_paths, "SNAPSHOT_ARCHIVE_ROOT", self.archive)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.tmp.cleanup()

    def test_candidates_are_old_dated_meetings_with_snapshots(self) -> None:
        (self.hk / "2026-10-28_ShaTin" / "Prediction_Snapshots").mkdir(parents=True)
        (self.hk / "2026-04-01_ShaTin_AWT_覆盤報告.md").write_text("x")
        (self.hk / "2026-05-03_ShaTin").mkdir()
        self.assertEqual(ops.candidates(self.hk, 14, date(2026, 11, 2), ops.HKJC), [self.meeting])

    def test_offload_and_readers_follow_marker(self) -> None:
        ops.offload(self.meeting, self.archive, ops.HKJC)
        self.assertFalse((self.meeting / "Prediction_Snapshots").exists())
        dest = self.archive / "hkjc" / self.meeting.name / "Prediction_Snapshots"
        self.assertEqual(prediction_snapshot_dir(self.meeting, "Prediction_Snapshots"), dest)
        self.assertEqual(ops.verify(self.hk, self.archive, True, ops.HKJC), [])

        sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
        import hkjc_shadow_monitor
        folder, manifest = hkjc_shadow_monitor._latest_snapshot(self.meeting)
        self.assertEqual(folder, dest / self.snap.name)
        self.assertTrue(manifest["immutable_prediction_snapshot"])

    def test_research_evidence_paths_follow_marker(self) -> None:
        sys.path.insert(0, str(REPO / ".agents/skills"))
        from shared_wong_choi.research_prediction_artifacts import _offloaded_candidate

        original = self.snap / "Race_1_Logic.json"
        self.assertIsNone(_offloaded_candidate(original))  # still local: direct read wins
        ops.offload(self.meeting, self.archive, ops.HKJC)
        got = _offloaded_candidate(original)
        self.assertEqual(got, self.archive / "hkjc" / self.meeting.name / "Prediction_Snapshots"
                         / self.snap.name / "Race_1_Logic.json")
        self.assertTrue(got.is_file())
        self.patch.stop()
        with mock.patch.object(wongchoi_paths, "SNAPSHOT_ARCHIVE_ROOT", Path(self.tmp.name) / "gone"):
            self.assertIsNone(_offloaded_candidate(original))  # unavailable, not a crash
        self.patch.start()

    def test_writers_refuse_offloaded_meeting(self) -> None:
        ops.offload(self.meeting, self.archive, ops.HKJC)
        sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_daily_auto"))
        import hkjc_daily_schedule
        with self.assertRaisesRegex(RuntimeError, "offloaded"):
            hkjc_daily_schedule.create_prediction_snapshot(self.meeting)
        self.assertFalse((self.meeting / "Prediction_Snapshots").exists())

    def test_cli_restore_and_verify_cover_both_platforms(self) -> None:
        ops.offload(self.meeting, self.archive, ops.HKJC)
        au = Path(self.tmp.name) / "AU_Racing"
        common = ["--au-root", str(au), "--hk-root", str(self.hk), "--archive-root", str(self.archive)]
        with mock.patch("sys.stdout"):
            self.assertEqual(ops.main(["--verify", *common]), 0)
            self.assertEqual(ops.main(["--restore", self.meeting.name, *common]), 0)
        self.assertTrue((self.snap / "Race_1_Logic.json").is_file())
        self.assertFalse(wongchoi_paths.snapshot_offload_marker(self.meeting, "Prediction_Snapshots").exists())


# Every place production code names a snapshot folder. A new reader must call
# `wongchoi_paths.prediction_snapshot_dir` — joining the name itself would see
# an empty folder once a meeting is offloaded and silently skip it.
ALLOWED = {
    "wongchoi_paths.py": "the resolver",
    ".agents/scripts/offload_prediction_snapshots.py": "the mover",
    ".agents/skills/shared_wong_choi/immutable_snapshot.py": "writer; new snapshots are always local",
    ".agents/skills/shared_racing/race_reflector/scripts/unified_reflector_core.py": "names passed to the resolver",
    ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/engine_core.py": "compares a folder name; same in either location",
    ".agents/skills/shared_wong_choi/research_prediction_artifacts.py": "names passed to the resolver",
    ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_shadow_monitor.py": "name passed to the resolver",
    ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_reverse_bias_shadow.py": "resolver for reads; writes refuse an offloaded meeting",
    ".agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_daily_schedule.py": "writer for today's meeting; refuses an offloaded one",
    # Not offloaded: the mover only walks AU Archive/ and HKJC meetings. Wire these first if that changes.
    ".agents/skills/nba/nba_daily_auto/nba_daily_schedule.py": "NBA",
    ".agents/skills/nba/nba_daily_auto/nba_no_prediction.py": "NBA",
    ".agents/scripts/nba_ml/nba_ml_pit.py": "NBA",
    "Horse_Racing_Dashboard/backend/services/nba_published_analysis.py": "NBA",
}
SKIP_PARTS = {"tests", "scratch", "docs", "archive", ".git", "node_modules", ".venv", "__pycache__"}


class ReaderWiringTest(unittest.TestCase):
    def test_no_unregistered_snapshot_folder_access(self) -> None:
        names = {"_prediction_snapshots", "Prediction_Snapshots"}
        found = set()
        for path in REPO.rglob("*.py"):
            rel = path.relative_to(REPO)
            if SKIP_PARTS & set(rel.parts) or rel.name.startswith("test_"):
                continue
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and node.value.split("/")[0] in names:
                    found.add(rel.as_posix())
        self.assertEqual(sorted(found - set(ALLOWED)), [],
                         "route new snapshot readers through wongchoi_paths.prediction_snapshot_dir")


if __name__ == "__main__":
    unittest.main()
