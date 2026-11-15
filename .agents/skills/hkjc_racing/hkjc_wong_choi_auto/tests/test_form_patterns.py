"""賽績 pattern（EXP-20261115-15）：老馬贏後、降班＋評分跌返贏馬分 —— 由 Logic 欄位計。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine.form_patterns import flags  # noqa: E402


def horse(fin, starts, rating, trend, last_cls):
    return {"last_6_finishes": fin, "career_race_starts": starts,
            "_data": {"total_starts": starts, "current_rating": rating, "rating_trend": f"{trend} → 穩定",
                      "recent_6_detail": f"第1仗(19/10/2026 {last_cls}): 1名 1 | 第2仗(27/09/2026 第四班): 5名 3"}}


class FormPatternsTest(unittest.TestCase):
    def test_old_won_last(self):
        self.assertTrue(flags(horse("1-5-3", 40, 60, "58→55→54", "第四班"), "第四班")["old_won_last"])
        self.assertFalse(flags(horse("1-5-3", 20, 60, "58→55→54", "第四班"), "第四班")["old_won_last"])      # 唔夠老
        self.assertFalse(flags(horse("2-1-3", 40, 60, "58→55→54", "第四班"), "第四班")["old_won_last"])      # 上仗冇贏
        self.assertFalse(flags(horse("1-5-3", 40, 98, "96→95→94", "第二班"), "第二班")["old_won_last"])      # 高班豁免

    def test_classdrop_rating_back(self):
        # 上仗第三班 → 今仗第四班；評分 58 ≤ 近 6 仗最近贏馬（第 3 仗）評分 60
        h = horse("6-8-1-4", 20, 58, "62→61→60→59", "第三班")
        self.assertTrue(flags(h, "第四班")["classdrop_rating_back"])
        self.assertFalse(flags(h, "第三班")["classdrop_rating_back"])          # 冇降班
        h2 = horse("6-8-1-4", 20, 63, "62→61→60→59", "第三班")
        self.assertFalse(flags(h2, "第四班")["classdrop_rating_back"])         # 評分高過贏馬分
        self.assertFalse(flags(horse("6-8-4-4", 20, 58, "62→61→60→59", "第三班"), "第四班")["classdrop_rating_back"])  # 近 6 仗冇贏

    def test_missing_fields_are_false(self):
        f = flags({"last_6_finishes": ""}, None)
        self.assertFalse(f["old_won_last"] or f["classdrop_rating_back"])


if __name__ == "__main__":
    unittest.main()
