"""戰場全景頁頭：路程唔可以印 1200mm、要寫場地；AWT 要講明泥地往績未入分（純顯示）。"""
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_racing_engine import renderer  # noqa: E402

AWT = {"race_class": "第四班", "distance": "1200m", "venue": "沙田AWT", "track": "AWT", "course": "Unknown"}
TURF = {"race_class": "第四班", "distance": "1200m", "venue": "沙田", "track": "Turf", "course": "A"}


def _horse(name, stats):
    return {"horse_name": name, "season_stats": stats}


class PanoramaTrackHeaderTest(unittest.TestCase):
    def _header(self, race):
        return next(line for line in renderer._render_panorama(race, {}, {}) if "賽事格局" in line)

    def test_distance_has_single_unit_and_track_is_named(self):
        self.assertEqual(self._header(AWT), "| 賽事格局 | 第四班 / 1200m / 沙田全天候跑道 / HKJC |")
        self.assertEqual(self._header(TURF), '| 賽事格局 | 第四班 / 1200m / 沙田草地 "A" 賽道 / HKJC |')

    def test_all_weather_notice_lists_runners_without_same_course_record(self):
        verdict = {"ranking": [{"horse_number": 4, "horse_name": "甲"}, {"horse_number": 12, "horse_name": "乙"}]}
        horses = {
            "4": _horse("甲", "季內 (0-0-0-1) | 同程 (1-1-0-5) | 同場同程 (0-1-1-5)"),
            "12": _horse("乙", "季內 (0-0-0-2) | 同程 (1-7-3-14) | 同場同程 (0-0-0-0)"),
        }
        notice = "\n".join(renderer._all_weather_notice(AWT, verdict, horses))

        self.assertIn("今場場地路程未跑過: [12] 乙", notice)
        self.assertIn("[4] 甲 0-1-1-5", notice)
        self.assertEqual(renderer._all_weather_notice(TURF, verdict, horses), [])


if __name__ == "__main__":
    unittest.main()
