"""每週摘要：讀兩份 ledger，出短文字；擠迫規則唔可以混入「輸入問題」排行。"""
from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))

import field_health_digest as digest  # noqa: E402

TODAY = dt.date(2026, 10, 13)  # W42 → 目標週 W41


def _write(path: Path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def _field_rows(margin_dead: bool):
    rows = []
    for w in ("2026-W37", "2026-W38", "2026-W39", "2026-W40", "2026-W41"):
        rows.append({"week": w, "source": "results_csv", "field": "Margin", "n": 2000,
                     "fill_rate": 0.0 if (margin_dead and w == "2026-W41") else 0.5})
    return rows


def _miss_rows():
    return [
        {"kind": "summary", "week": "2026-W41", "meeting": "a", "scored_races": 10},
        {"kind": "race", "week": "2026-W41", "meeting": "a", "race": 1, "bucket": "input_anomaly",
         "rules": ["pace_figure_alert", "tied"]},
        {"kind": "race", "week": "2026-W41", "meeting": "a", "race": 2, "bucket": "model_wrong", "rules": []},
        {"kind": "race", "week": "2026-W40", "meeting": "b", "race": 1, "bucket": "crowded", "rules": ["tight"]},
    ]


class DigestTests(unittest.TestCase):
    def test_reports_dead_column_and_miss_split(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(root / "AU_Field_Health.jsonl", _field_rows(margin_dead=True))
            _write(root / "AU_Miss_Autopsy.jsonl", _miss_rows())
            text = digest.build("au", root, today=TODAY)
            self.assertIn("2026-W41", text)
            self.assertIn("Margin", text)
            self.assertIn("10 場入面 2 場", text)
            self.assertIn("前 1 週", text)
            self.assertIn("PF 覆蓋警報 ×1", text)
            self.assertNotIn("頭兩名分差", text, "擠迫規則唔算輸入問題")

    def test_quiet_week(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _write(root / "AU_Field_Health.jsonl", _field_rows(margin_dead=False))
            text = digest.build("au", root, today=TODAY)
            self.assertIn("✅ 冇欄位變差", text)

    def test_no_ledgers_yet(self):
        with tempfile.TemporaryDirectory() as t:
            text = digest.build("hkjc", Path(t), today=TODAY)
            self.assertIn("未有紀錄", text)


if __name__ == "__main__":
    unittest.main()
