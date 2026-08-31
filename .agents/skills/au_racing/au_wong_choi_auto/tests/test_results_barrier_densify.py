"""語料 CSV 嘅實際出閘檔位：分母一定要係「呢場實際有賽果嗰批」。

第一版喺 Logic 名單上 densify，實測只對 75.9%（aggregator 寫嘅舊行係 97.8%）——
因為 42.5% 場次嘅 Logic 名單仍然含已退出嘅幽靈馬。呢批測試守住正確分母，
同守住「賽果被剪短就唔好猜」。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from au_results_ingest import _densify_by_race  # noqa: E402


def race(barriers, positions=None, date="2026-08-01", track="Randwick", no="1"):
    positions = positions or list(range(1, len(barriers) + 1))
    return [{"Date": date, "Track": track, "Race": no, "Horse": f"H{i}",
             "Barrier": str(b), "Pos": str(p)}
            for i, (b, p) in enumerate(zip(barriers, positions))]


def barriers(rows):
    return [r["Barrier"] for r in rows]


class TestDensifyByRace(unittest.TestCase):
    def test_clean_race_is_untouched(self):
        rows = race([3, 1, 4, 2, 5])
        changed, _ = _densify_by_race(rows)
        self.assertEqual(changed, 0)
        self.assertEqual(barriers(rows), ["3", "1", "4", "2", "5"])

    def test_scratched_race_is_renumbered(self):
        """原始抽籤 2/5/9/13，四匹出賽 → 1/2/3/4。"""
        rows = race([2, 5, 9, 13])
        changed, _ = _densify_by_race(rows)
        self.assertEqual(changed, 4)
        self.assertEqual(barriers(rows), ["1", "2", "3", "4"])

    def test_order_is_preserved(self):
        raw = [11, 2, 14, 7, 3]
        rows = race(raw)
        _densify_by_race(rows)
        got = [int(b) for b in barriers(rows)]
        self.assertEqual([i for i, _ in sorted(enumerate(raw), key=lambda t: t[1])],
                         [i for i, _ in sorted(enumerate(got), key=lambda t: t[1])])

    def test_truncated_result_is_skipped_not_guessed(self):
        """只有頭 4 名但實際跑 12 匹 —— 喺 4 行上 densify 會砌一個更錯嘅檔位。"""
        rows = race([2, 5, 9, 13], positions=[1, 2, 3, 12])
        changed, skipped = _densify_by_race(rows)
        self.assertEqual(changed, 0)
        self.assertEqual(skipped, 4)
        self.assertEqual(barriers(rows), ["2", "5", "9", "13"])

    def test_duplicate_barriers_are_skipped(self):
        rows = race([2, 2, 5])
        changed, skipped = _densify_by_race(rows)
        self.assertEqual((changed, skipped), (0, 3))

    def test_missing_barrier_skips_whole_race(self):
        rows = race([2, 5, 9])
        rows[1]["Barrier"] = ""
        changed, skipped = _densify_by_race(rows)
        self.assertEqual(changed, 0)
        self.assertEqual(skipped, 3)
        self.assertEqual(barriers(rows), ["2", "", "9"])

    def test_races_are_kept_separate(self):
        rows = race([2, 5, 9], no="1") + race([4, 8, 12], no="2")
        _densify_by_race(rows)
        self.assertEqual(barriers(rows), ["1", "2", "3", "1", "2", "3"])

    def test_same_race_number_different_track(self):
        rows = race([2, 5, 9], track="Randwick") + race([4, 8, 12], track="Flemington")
        _densify_by_race(rows)
        self.assertEqual(barriers(rows), ["1", "2", "3", "1", "2", "3"])


if __name__ == "__main__":
    unittest.main()
