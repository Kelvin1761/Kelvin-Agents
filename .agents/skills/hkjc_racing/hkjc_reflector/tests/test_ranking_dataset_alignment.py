from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_hkjc_ranking_dataset import (
    _choose_distance,
    _choose_race_class,
    _normalize_course,
    _normalize_track,
    _place_cutoff,
    _race_class_label,
    _race_class_number,
)


class RankingDatasetAlignmentTests(unittest.TestCase):
    def test_chinese_class_labels_are_normalized(self) -> None:
        self.assertEqual(_race_class_number("第四班"), 4)
        self.assertEqual(_race_class_label("第四班"), "Class 4")
        self.assertEqual(_race_class_label("國際一級賽"), "Group 1")

    def test_placeholder_class_falls_back_to_racecard(self) -> None:
        self.assertEqual(
            _choose_race_class("[FILL]", "第四班"),
            "第四班",
        )

    def test_awt_venue_repairs_missing_surface(self) -> None:
        self.assertEqual(_normalize_track("", "沙田AWT"), "AWT")
        self.assertEqual(_normalize_track("草地", "沙田"), "Turf")

    def test_course_rejects_distance_field_misalignment(self) -> None:
        self.assertEqual(_normalize_course("C+3 賽道"), "C+3")
        self.assertEqual(_normalize_course("1200米"), "Unknown")
        self.assertEqual(_normalize_course("#### 第二部分"), "Unknown")

    def test_distance_falls_back_past_placeholder(self) -> None:
        self.assertEqual(_choose_distance("[FILL]", "1200米"), "1200")
        self.assertEqual(_choose_distance("#### 第二部分", "1650"), "1650")

    def test_hkjc_place_cutoff_uses_actual_field_size(self) -> None:
        self.assertEqual(_place_cutoff(14), 3)
        self.assertEqual(_place_cutoff(7), 3)
        self.assertEqual(_place_cutoff(6), 2)
        self.assertEqual(_place_cutoff(4), 2)
        self.assertEqual(_place_cutoff(3), 0)


if __name__ == "__main__":
    unittest.main()
