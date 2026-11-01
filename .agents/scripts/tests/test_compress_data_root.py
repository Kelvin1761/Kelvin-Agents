"""compress_data_root: old files shrink in place, everything else is left alone."""
from __future__ import annotations

import os
import platform
import shutil
import sys
import time
import unittest
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compress_data_root as cdr  # noqa: E402

PAYLOAD = ('{"horse": "Example", "score": 61.5, "notes": "steady"}\n' * 2000).encode()
OLD = time.time() - 10 * 86400


@unittest.skipUnless(platform.system() == "Darwin" and shutil.which("ditto"), "APFS ditto only")
class CompressDataRootTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "data"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _file(self, rel: str, *, old: bool = True, payload: bytes = PAYLOAD) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        if old:
            os.utime(path, (OLD, OLD))
        return path

    def test_old_file_is_compressed_with_same_bytes_and_mtime(self) -> None:
        path = self._file("AU/2026-10-01 X/_prediction_snapshots/s1/Race_1_Logic.json")
        mtime = path.stat().st_mtime_ns
        summary = cdr.run(self.root, min_age_days=3, time_budget=60, dry_run=False)
        self.assertEqual(summary["compressed"], 1)
        self.assertTrue(path.lstat().st_flags & cdr.UF_COMPRESSED)
        self.assertEqual(path.read_bytes(), PAYLOAD)
        self.assertEqual(path.stat().st_mtime_ns, mtime)
        self.assertFalse((self.root / cdr.STAGING_NAME).exists())

    def test_fresh_db_log_and_hardlinked_files_are_untouched(self) -> None:
        fresh = self._file("AU/fresh.json", old=False)
        db = self._file("tennis.db")
        log = self._file("Field_Health.jsonl")
        wal = self._file("tennis.db-wal")
        linked = self._file("a/linked.json")
        os.link(linked, self.root / "a" / "linked-twin.json")
        summary = cdr.run(self.root, min_age_days=3, time_budget=60, dry_run=False)
        self.assertEqual(summary["compressed"], 0)
        for path in (fresh, db, log, wal, linked):
            self.assertFalse(path.lstat().st_flags & cdr.UF_COMPRESSED, path.name)

    def test_dry_run_counts_without_writing(self) -> None:
        path = self._file("HK/Race_1_Logic.json")
        summary = cdr.run(self.root, min_age_days=3, time_budget=60, dry_run=True)
        self.assertEqual(summary["compressed"], 1)
        self.assertFalse(path.lstat().st_flags & cdr.UF_COMPRESSED)

    def test_file_rewritten_during_copy_is_not_replaced(self) -> None:
        path = self._file("HK/Race_2_Logic.json")
        before = path.lstat()
        path.write_bytes(PAYLOAD + b"late write\n")
        staging = self.root / cdr.STAGING_NAME
        staging.mkdir()
        outcome, _ = cdr.compress_file(path, before, staging)
        self.assertNotEqual(outcome, "compressed")
        self.assertEqual(path.read_bytes(), PAYLOAD + b"late write\n")


if __name__ == "__main__":
    unittest.main()
