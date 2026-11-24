"""offsite_backup：本地後端完整走一次 —— 加密、重用、只重傳變咗嘅組、還原演練、竄改會捉到、保留代數。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import offsite_backup as ob  # noqa: E402


class OffsiteBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.src = t / "src"
        (self.src / "A").mkdir(parents=True)
        (self.src / "B" / "2026-10-01 X").mkdir(parents=True)
        (self.src / "A" / "one.json").write_text('{"a": 1}')
        (self.src / "B" / "2026-10-01 X" / "f.csv").write_text("x,y\n1,2\n" * 100)
        (self.src / "top.txt").write_text("hello")
        (self.src / "A" / ".DS_Store").write_text("junk")
        self.remote = t / "remote"
        key = t / "k.key"
        key.write_text("secret-key\n")
        self.cfg = {"backend": f"local:{self.remote}", "key_file": str(key)}
        self.sources = [("data", self.src)]
        self._state, self._scratch = ob.STATE, ob.SCRATCH
        ob.STATE = t / "state.json"
        os.environ["TMPDIR"] = str(t)
        self._workroot = ob._workroot
        ob._workroot = lambda: t

    def tearDown(self) -> None:
        ob.STATE = self._state
        ob._workroot = self._workroot
        self.tmp.cleanup()

    def run_backup(self):
        return ob.cmd_run(cfg=self.cfg, sources=self.sources)

    def test_roundtrip_reuse_and_drill(self) -> None:
        s1 = self.run_backup()
        self.assertEqual((s1["groups"], s1["uploaded_groups"]), (3, 3))
        blobs = [p for p in self.remote.rglob("*") if p.is_file()]
        self.assertTrue(all(b"hello" not in p.read_bytes() for p in blobs))          # 已加密
        s2 = self.run_backup()
        self.assertEqual((s2["uploaded_groups"], s2["reused_groups"]), (0, 3))
        (self.src / "A" / "one.json").write_text('{"a": 2, "b": 3}')
        s3 = self.run_backup()
        self.assertEqual((s3["uploaded_groups"], s3["reused_groups"]), (1, 2))
        rep = ob.cmd_drill(3, cfg=self.cfg, seed=0, sources=self.sources)
        self.assertTrue(rep["ok"], rep)
        self.assertTrue(any(g["content_checked"] for g in rep["groups"]))
        names = {g["name"] for g in ob.read_state()["last_manifest_groups"]}
        self.assertNotIn("data/A/.DS_Store", names)

    def test_tampered_object_fails_drill(self) -> None:
        self.run_backup()
        obj = next(p for p in (self.remote / "objects").rglob("*") if p.is_file())
        obj.write_bytes(obj.read_bytes()[:-1] + b"\x00")
        with self.assertRaises(ob.BackupError):
            ob.cmd_drill(3, cfg=self.cfg, seed=0, sources=self.sources)

    def test_wrong_key_cannot_read_manifest(self) -> None:
        self.run_backup()
        bad = Path(self.tmp.name) / "bad.key"
        bad.write_text("nope\n")
        with self.assertRaises(ob.BackupError):
            ob.cmd_drill(1, cfg=self.cfg | {"key_file": str(bad)}, sources=self.sources)

    def test_retention_deletes_unreferenced(self) -> None:
        old = ob.KEEP_GENERATIONS
        ob.KEEP_GENERATIONS = 2
        try:
            for i in range(4):
                (self.src / "top.txt").write_text(f"v{i}")
                self.run_backup()
            st = ob.read_state()
            self.assertEqual(len(st["generations"]), 2)
            self.assertEqual(len(list((self.remote / "manifests").glob("*.enc"))), 2)
            top_objs = list((self.remote / "objects" / "data" / "top.txt").glob("*"))
            self.assertEqual(len(top_objs), 2)          # 兩代各一份；更舊嘅已刪
        finally:
            ob.KEEP_GENERATIONS = old

    def test_big_dir_split_by_prefix(self) -> None:
        old = ob.GROUP_SPLIT_BYTES
        ob.GROUP_SPLIT_BYTES = 10
        try:
            names = {g["name"] for g in ob.plan_groups(self.sources)}
            self.assertIn("data/B/2026-10", names)
        finally:
            ob.GROUP_SPLIT_BYTES = old

    def test_status_freshness(self) -> None:
        self.assertFalse(ob.status()["fresh"])
        self.run_backup()
        self.assertTrue(ob.status()["fresh"])


if __name__ == "__main__":
    unittest.main()


class OffsiteSafetyTests(OffsiteBackupTests):
    """Sol 覆核：缺來源唔可以令舊副本被刪；新機用遠端 LATEST 還原；零組演練唔算過。"""

    def test_missing_source_is_carried_not_dropped(self):
        extra = Path(self.tmp.name) / "disk"
        (extra / "log").mkdir(parents=True)
        (extra / "log" / "a.jsonl").write_text("{}\n")
        self.sources = [("data", self.src), ("disk", extra)]
        old = ob.KEEP_GENERATIONS
        ob.KEEP_GENERATIONS = 2
        try:
            self.run_backup()
            import shutil
            shutil.move(str(extra), str(extra) + ".unplugged")          # 外置碟冇插
            for _ in range(3):
                s = self.run_backup()
            self.assertEqual(s["carried_groups"], 1)
            self.assertEqual(s["absent_sources"], ["disk"])
            disk_objs = list((self.remote / "objects" / "disk").rglob("*"))
            self.assertTrue([p for p in disk_objs if p.is_file()])        # 舊副本仲喺度
        finally:
            ob.KEEP_GENERATIONS = old

    def test_restore_on_fresh_machine_uses_remote_latest(self):
        self.run_backup()
        ob.STATE.unlink()                                                  # 本機 state 冇咗
        dest = Path(self.tmp.name) / "restored"
        res = ob.cmd_restore(dest, cfg=self.cfg)
        self.assertEqual(res["groups"], 3)
        self.assertEqual((dest / "data" / "A" / "one.json").read_text(), '{"a": 1}')
        with self.assertRaises(ob.BackupError):                            # 唔覆蓋非空資料夾
            ob.cmd_restore(dest, cfg=self.cfg)

    def test_key_file_created_private(self):
        key = Path(self.tmp.name) / "new.key"
        old = ob.CONFIG
        ob.CONFIG = Path(self.tmp.name) / "cfg.json"
        try:
            ob.cmd_init(f"local:{self.remote}", key)
        finally:
            ob.CONFIG = old
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)
