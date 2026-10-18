"""EXP-20261018-01：舊存檔 Logic 冇 venue → 由場次資料夾名補。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hkjc_auto_orchestrator import _meeting_venue_for_logic  # noqa: E402


class MeetingVenueTests(unittest.TestCase):
    def test_folder_names(self):
        self.assertEqual(_meeting_venue_for_logic("/x/2026-05-03_ShaTin/Race_1_Logic.json"), "沙田")
        self.assertEqual(_meeting_venue_for_logic("/x/2026-04-15_HappyValley/Race_9_Logic.json"), "跑馬地")

    def test_unknown_folder_returns_none(self):
        self.assertIsNone(_meeting_venue_for_logic("/tmp/scratch/Race_1_Logic.json"))


if __name__ == "__main__":
    unittest.main()
