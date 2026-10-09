"""冇認出領放馬嘅場唔可以報「極慢」—— 嗰個係「冇證據」唔係「冇步速」。

2026-09-09→10-08：653/653 場「極慢」都係 leaders=0，佔全部 53% 場次。
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
INJECT = REPO_ROOT / ".agents" / "scripts" / "inject_fact_anchors.py"


def _inject():
    spec = importlib.util.spec_from_file_location("_ifa_pace_label_test", INJECT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ifa_pace_label_test"] = module
    spec.loader.exec_module(module)
    return module


class PaceLabelNeedsALeaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classify = staticmethod(_inject()._classify_pace_v2)

    def test_no_leader_is_unknown_not_extremely_slow(self):
        # 2026-09-26 Rosehill R3 原樣：leaders=0, pressers=0, on_pace=1
        self.assertEqual(self.classify(0, 1, 6, 1400, "Good 4", n_pressers=0), "未明")
        self.assertEqual(self.classify(0, 2, 12, 1000, "Soft 5", n_pressers=1), "未明")

    def test_leaders_present_still_graded(self):
        self.assertEqual(self.classify(3, 1, 14, 1100, "Good 4", n_pressers=2), "極快")
        self.assertEqual(self.classify(1, 0, 10, 2000, "Good 4", n_pressers=0), "慢")
        self.assertEqual(self.classify(1, 1, 10, 1200, "Good 4", n_pressers=1), "正常")

    def test_empty_field_unchanged(self):
        self.assertEqual(self.classify(0, 0, 0), "正常")


if __name__ == "__main__":
    unittest.main()
