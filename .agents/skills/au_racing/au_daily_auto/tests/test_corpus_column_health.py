"""語料 CSV 欄位級健康守衛。

呢一族缺陷中過兩次（`Time` 2026-08-26、`Barrier` 2026-08-31），兩次都係
「檔案仍在、行數仲加、零錯誤」。所以呢批測試最重要嗰兩個係：
守衛**真係會嗌**，而且**健康時唔會嗌**。
"""
import csv
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import au_healthcheck as H  # noqa: E402

COLUMNS = ["Date", "Track", "Race", "Distance", "Condition", "Pos", "Horse",
           "Barrier", "Weight", "Jockey", "Trainer", "Margin", "SP", "Time"]


def write_csv(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in COLUMNS})


def make_rows(n, *, days_back=5, **overrides):
    day = (date(2026, 8, 31) - timedelta(days=days_back)).isoformat()
    base = {"Date": day, "Track": "Randwick", "Race": "1", "Distance": "1200",
            "Condition": "Good 4", "Pos": "1", "Horse": "H", "Barrier": "3",
            "Weight": "57", "Jockey": "J", "Trainer": "T", "Margin": "—", "SP": "$3.50"}
    return [{**base, **overrides, "Horse": f"H{i}"} for i in range(n)]


class CorpusColumnHealthTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "results.csv"
        self.addCleanup(self.dir.cleanup)

    def test_healthy_csv_is_silent(self):
        write_csv(self.path, make_rows(200))
        self.assertEqual(H.corpus_column_advisories(self.path), [])

    def test_dead_column_fires(self):
        """呢個就係 2026-08 `Barrier` 欄嘅實際形狀 —— 全部空白。"""
        write_csv(self.path, make_rows(200, Barrier=""))
        out = H.corpus_column_advisories(self.path)
        self.assertTrue(any("Barrier" in x for x in out), out)
        self.assertTrue(any("0%" in x for x in out), out)

    def test_partial_decay_fires_below_floor(self):
        rows = make_rows(100) + make_rows(100, Barrier="")
        write_csv(self.path, rows)
        self.assertTrue(any("Barrier" in x for x in H.corpus_column_advisories(self.path)))

    def test_small_gap_above_floor_stays_silent(self):
        """輕微缺失唔應該嗌 —— 唔然人會學會忽略呢個守衛。"""
        rows = make_rows(196) + make_rows(4, Barrier="")
        write_csv(self.path, rows)
        self.assertEqual(H.corpus_column_advisories(self.path), [])

    def test_old_rows_cannot_dilute_a_fresh_death(self):
        """關鍵：只睇最近窗。舊嘅健康行唔可以稀釋一條剛死嘅欄。"""
        rows = make_rows(2000, days_back=400) + make_rows(50, Barrier="")
        write_csv(self.path, rows)
        self.assertTrue(any("Barrier" in x for x in H.corpus_column_advisories(self.path)))

    def test_missing_column_is_reported(self):
        """有行但成條欄唔見 —— 唔同「全部空白」，要分開報。"""
        fields = [c for c in COLUMNS if c != "Barrier"]
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in make_rows(50):
                writer.writerow({k: row.get(k, "") for k in fields})
        out = H.corpus_column_advisories(self.path)
        self.assertTrue(any("Barrier" in x and "冇" in x for x in out), out)

    def test_absent_and_empty_files_do_not_raise(self):
        self.assertTrue(H.corpus_column_advisories(self.path.with_name("nope.csv")))
        write_csv(self.path, [])
        self.assertTrue(H.corpus_column_advisories(self.path))


if __name__ == "__main__":
    unittest.main()
