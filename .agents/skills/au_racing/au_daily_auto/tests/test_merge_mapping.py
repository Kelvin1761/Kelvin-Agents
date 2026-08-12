#!/usr/bin/env python3
"""對應表要並集合併，唔可以還原。

2026-08-12：自動更新步驟為咗令 fast-forward 過得到，喺 merge 之前做
`git checkout -- sb_archive_meeting_ids.json`。個檔係「已追蹤 + 每次 run 寫入」
嘅組合，所以呢個還原**每次 run 開頭都抹走上一次 run 寫入嘅 meeting ID**。
補跑辛苦抽返嘅五個場次，10:00 一開就冇咗對應表，覆核全部報 refresh_deferred，
退出馬同場地變化一個都覆核唔到。

當時我寫嘅註解係「掉咗唔會錯，只係要再 derive 一次」—— 錯。覆盤路徑會重新推導，
覆核路徑唔會，佢直接放棄。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import merge_mapping as M  # noqa: E402


class MergeMappingTests(unittest.TestCase):
    def _files(self, tmp, local, incoming):
        a = Path(tmp) / "local.json"
        b = Path(tmp) / "git.json"
        a.write_text(json.dumps(local), encoding="utf-8")
        b.write_text(json.dumps(incoming), encoding="utf-8")
        return a, b

    def test_local_entries_survive_the_merge(self):
        # 就係呢個 case：補跑寫入五個場次，git 版本只有一個。
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self._files(tmp, {"new1": {"x": 1}, "new2": {"x": 2}},
                               {"old": {"x": 0}})
            M.merge(a, b)
            got = json.loads(a.read_text(encoding="utf-8"))
        self.assertEqual(sorted(got), ["new1", "new2", "old"])

    def test_committed_entries_are_not_lost_either(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self._files(tmp, {"new": {}}, {"a": {}, "b": {}, "c": {}})
            M.merge(a, b)
            got = json.loads(a.read_text(encoding="utf-8"))
        self.assertEqual(len(got), 4)

    def test_a_key_present_in_both_keeps_the_local_copy(self):
        # 同一個 key 兩邊都係由同一版索引頁推導，所以取邊個都一樣；
        # 取本機係因為佢可能剛剛補齊咗 races 清單。
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self._files(tmp, {"k": {"races": [1, 2, 3]}},
                               {"k": {"races": [1]}})
            M.merge(a, b)
            got = json.loads(a.read_text(encoding="utf-8"))
        self.assertEqual(got["k"]["races"], [1, 2, 3])

    def test_unreadable_side_does_not_destroy_the_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "local.json"
            b = Path(tmp) / "git.json"
            a.write_text(json.dumps({"keep": {}}), encoding="utf-8")
            b.write_text("{ not json", encoding="utf-8")
            M.merge(a, b)
            self.assertIn("keep", json.loads(a.read_text(encoding="utf-8")))

    def test_the_runner_no_longer_reverts_the_file(self):
        runner = (Path(M.__file__).parent / "run_au_daily_schedule.sh").read_text()
        self.assertIn("merge_mapping.py", runner)
        # checkout 仍然需要（令 ff 過得到），但一定要跟住合併返
        self.assertLess(runner.index("git checkout --quiet --"),
                        runner.index("merge_mapping.py"))


if __name__ == "__main__":
    unittest.main()
