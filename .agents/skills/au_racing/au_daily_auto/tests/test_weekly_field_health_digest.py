"""healthcheck 一日跑三次，但欄位健康週報一個 ISO 週只可以發一次。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import au_healthcheck as H  # noqa: E402


class WeeklyDigestTests(unittest.TestCase):
    def test_sends_once_per_iso_week(self):
        sent = []
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            first = H.weekly_field_health_digest(date(2026, 10, 13), root=root, send=sent.append)
            again = H.weekly_field_health_digest(date(2026, 10, 15), root=root, send=sent.append)
            next_week = H.weekly_field_health_digest(date(2026, 10, 20), root=root, send=sent.append)
            self.assertIsNotNone(first)
            self.assertIsNone(again)
            self.assertIsNotNone(next_week)
            self.assertEqual(len(sent), 2)
            self.assertEqual((root / H.DIGEST_MARKER).read_text(encoding="utf-8").strip(), "2026-W43")
            self.assertTrue((root / "AU_Field_Health.jsonl").exists())

    def test_failed_send_does_not_mark_week_as_sent(self):
        def boom(_text):
            raise RuntimeError("telegram down")

        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            with self.assertRaises(RuntimeError):
                H.weekly_field_health_digest(date(2026, 10, 13), root=root, send=boom)
            self.assertFalse((root / H.DIGEST_MARKER).exists())


if __name__ == "__main__":
    unittest.main()
