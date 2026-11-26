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
        data = obj.read_bytes()
        obj.write_bytes(data[:-1] + bytes([data[-1] ^ 0xFF]))   # 反轉最後一 byte：一定改到（原本寫 \x00 有 1/256 等於冇改，flaky）
        with self.assertRaises(ob.BackupError):
            ob.cmd_drill(3, cfg=self.cfg, seed=0, sources=self.sources)

    def test_wrong_key_cannot_read_manifest(self) -> None:
        self.run_backup()
        bad = Path(self.tmp.name) / "bad.key"
        bad.write_text("nope\n")
        with self.assertRaises(ob.BackupError):
            ob.cmd_drill(1, cfg=self.cfg | {"key_file": str(bad)}, sources=self.sources)

    def test_garbage_decrypt_is_backup_error(self) -> None:
        """錯鑰匙碰啱過到 padding（~1/256）：openssl rc=0 但出亂碼 → 一定係 BackupError（確定性重現 flaky）。"""
        import subprocess
        from unittest import mock
        for junk in (b"\xec\x01\x99garbage", b"[1, 2]", b"not json"):
            fake = subprocess.CompletedProcess([], 0, stdout=junk, stderr=b"")
            with mock.patch.object(ob.subprocess, "run", return_value=fake):
                with self.assertRaises(ob.BackupError):
                    ob._decrypt_json(Path("x"), "k")

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


class RcloneBackendTests(OffsiteBackupTests):
    """用假 rclone（喺本機資料夾模擬 copyto／deletefile）行一次完整備份同還原。"""

    def setUp(self):
        super().setUp()
        t = Path(self.tmp.name)
        fake_root = t / "gdrive"
        fake_root.mkdir()
        bindir = t / "bin"
        bindir.mkdir()
        script = bindir / "rclone"
        script.write_text(f"""#!/usr/bin/env python3
import shutil, sys, os
from pathlib import Path
root = Path({str(fake_root)!r})
args = [a for a in sys.argv[1:] if not a.startswith("--") and not a.isdigit()]
def real(x):
    return root / x.split(":", 2)[-1] if x.startswith("gdrive:") else Path(x)
if args[0] == "copyto":
    dst = real(args[2]); dst.parent.mkdir(parents=True, exist_ok=True)
    src = real(args[1])
    if not src.exists():
        print("object not found", file=sys.stderr); sys.exit(3)
    shutil.copyfile(src, dst)
elif args[0] == "deletefile":
    p = real(args[1])
    if not p.exists():
        print("object not found", file=sys.stderr); sys.exit(4)
    p.unlink()
""")
        script.chmod(0o755)
        self._path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bindir}:{self._path}"
        self.cfg = self.cfg | {"backend": "rclone:gdrive:WongChoiBackup"}
        self.remote = fake_root / "WongChoiBackup"
        self._sleep = ob.time.sleep
        ob.time.sleep = lambda s: None

    def tearDown(self):
        os.environ["PATH"] = self._path
        ob.time.sleep = self._sleep
        super().tearDown()


class SystemStateTests(unittest.TestCase):
    """系統狀態：抄（保留 mtime、唔包鑰匙）→ place 放返原位；新機用戶名唔同會換 home；預設唔覆蓋。"""

    def test_stage_and_place_with_home_remap(self):
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            old_home = t / "Users" / "imac"
            (old_home / "state").mkdir(parents=True)
            (old_home / ".wongchoi_notify.env").write_text("TOKEN=x")
            (old_home / "state" / "a.json").write_text("{}")
            (old_home / "state" / "merge-01.json").write_text("big")
            items = [("home", old_home, [".wongchoi_notify.env", ".wongchoi_offsite.key"]),
                     ("st", old_home / "state", ["*.json"])]
            (old_home / ".wongchoi_offsite.key").write_text("SECRET")
            saved_home = ob.HOME
            ob.HOME = old_home
            try:
                root = ob.stage_system(t / "work", items)
            finally:
                ob.HOME = saved_home
            self.assertTrue((root / "home" / ".wongchoi_offsite.key").exists())   # 呢個 test 嘅 items 叫佢包
            self.assertFalse((root / "st" / "merge-01.json").exists())            # 發佈暫存唔包
            self.assertNotIn(".wongchoi_offsite.key", [n for _, _, g in ob.SYSTEM_ITEMS for n in g])  # 正式清單冇鑰匙
            new_home = t / "Users" / "kelvin"
            new_home.mkdir(parents=True)
            ob.HOME = new_home
            try:
                res = ob.place_system(t / "work")
                again = ob.place_system(t / "work")
            finally:
                ob.HOME = saved_home
            self.assertEqual((new_home / ".wongchoi_notify.env").read_text(), "TOKEN=x")
            self.assertEqual((new_home / "state" / "a.json").read_text(), "{}")
            self.assertEqual(oct((new_home / ".wongchoi_notify.env").stat().st_mode & 0o777), "0o600")
            self.assertGreaterEqual(res["placed"], 3)
            self.assertEqual(again["placed"], 0)                                   # 預設唔覆蓋
