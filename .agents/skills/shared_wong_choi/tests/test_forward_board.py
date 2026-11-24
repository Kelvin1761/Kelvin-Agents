"""forward_board：寫／讀／過期／渲染，同四個 tracker 真係會寫總板（用假數據，寫去 temp）。"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fb = _load("wc_forward_board_test", SKILLS / "shared_wong_choi" / "forward_board.py")
NOW = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)


class ForwardBoardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["WC_FORWARD_BOARD_ROOT"] = str(self.root)

    def tearDown(self):
        os.environ.pop("WC_FORWARD_BOARD_ROOT", None)
        self.tmp.cleanup()

    def test_publish_board_render_and_stale(self):
        fb.publish("au", [fb.row("a", "A 測試", "EXP-1", count=5, minimum=10, unit="場"),
                          fb.row("b", "B 測試", "EXP-2", count=10, minimum=10, unit="場", status="ready",
                                 note="判佢")], now=NOW - timedelta(hours=2))
        fb.publish("nba", [fb.row("c", "C", "EXP-3", status="decided")], now=NOW - timedelta(hours=72))
        b = fb.board(now=NOW)
        self.assertFalse(b["au"]["stale"])
        self.assertTrue(b["nba"]["stale"])
        self.assertTrue(b["hkjc"]["missing"])
        lines = fb.render(b)
        self.assertIn("⏰ B 測試（EXP-2）：10/10 場 —— 判佢", lines[1])        # 夠數排先
        self.assertTrue(any("tracker 好耐冇更新" in l for l in lines))
        self.assertFalse(any("C（EXP-3）" in l for l in lines))                # decided 預設收埋
        self.assertEqual(fb.summary(b)["ready"], 1)

    def test_bad_status_and_domain_rejected(self):
        with self.assertRaises(ValueError):
            fb.row("a", "A", "E", status="weird")
        with self.assertRaises(ValueError):
            fb.publish("golf", [])

    def test_pytest_default_never_touches_real_control_root(self):
        os.environ.pop("WC_FORWARD_BOARD_ROOT")
        os.environ.setdefault("PYTEST_CURRENT_TEST", "x")
        self.assertNotIn("WongChoiData", str(fb.board_dir()))

    def test_au_tracker_publishes(self):
        sys.path.insert(0, str(SKILLS / "au_racing" / "au_daily_auto"))
        import au_forward_tracker as t
        work = self.root / "work"
        work.mkdir()
        test = t.ForwardTest("x", "X 測試", "EXP-9", "status_file", 100, "場", "做嘢", status_file="x.json")
        (work / "x.json").write_text(json.dumps({"races_collected": 120}))
        t.check(work_dir=work, push=lambda m: None, tests=(test,))
        row = json.loads((self.root / "au.json").read_text())["tests"][0]
        self.assertEqual((row["count"], row["minimum"], row["status"]), (120, 100, "ready"))

    def test_nba_tracker_publishes(self):
        sys.path.insert(0, str(SKILLS / "nba" / "nba_daily_auto"))
        import nba_forward_tracker as t
        test = t.ForwardTest("f", "精選", "EXP-F", "s.py", "F", "做嘢")

        class Mod:
            @staticmethod
            def status(ledger, analysis):
                return {"F": {"bets": 40, "ready": False, "checkpoint": {"bets": 250}}}

        t.check(ledger=self.root, analysis=self.root, reports=self.root, notify=lambda k, m: None,
                tests=(test,), loader=lambda s: Mod)
        row = json.loads((self.root / "nba.json").read_text())["tests"][0]
        self.assertEqual((row["count"], row["minimum"], row["unit"], row["status"]), (40, 250, "注", "collecting"))


if __name__ == "__main__":
    unittest.main()
