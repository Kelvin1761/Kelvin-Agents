"""AU 場次分級（都會／省級／鄉鎮）同每場開跑時間入 dashboard payload。

2026-10-31：一個星期六 16 個 AU 場次，首頁係 16 張一模一樣嘅卡，冇分級冇時間。
分級跟各州官方定義（backend/services/au_venue_tiers.json），名稱用引擎嘅
_track_geometry_key，所以 Rosehill Gardens／Randwick-Kensington 呢類別名唔使
另抄一份 alias 表。
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


DASHBOARD_DIR = Path(__file__).resolve().parents[1]
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

import generate_static  # noqa: E402


class VenueTierTests(unittest.TestCase):
    def test_official_tiers_by_racecourse(self):
        cases = {
            # Racing NSW: four ATC metro tracks, five PRANSW provincial clubs.
            "Randwick": ("NSW", "metro"), "Rosehill Gardens": ("NSW", "metro"),
            "Randwick-Kensington": ("NSW", "metro"), "Newcastle": ("NSW", "provincial"),
            "Illawarra Grange": ("NSW", "provincial"), "Dubbo": ("NSW", "country"),
            # Racing Victoria 2023: Ballarat / Pakenham are provincial on turf only.
            "Flemington": ("VIC", "metro"), "Caulfield Heath": ("VIC", "metro"),
            "Mornington": ("VIC", "provincial"), "Ballarat": ("VIC", "provincial"),
            "Ballarat Synthetic": ("VIC", "country"), "Moe": ("VIC", "country"),
            "Doomben": ("QLD", "metro"), "Gold Coast": ("QLD", "provincial"),
            "Rockhampton": ("QLD", "country"),
            "Morphettville": ("SA", "metro"), "Murray Bridge": ("SA", "provincial"),
            # Racing SA: Port Lincoln reclassified to country from 2026/27.
            "Port Lincoln": ("SA", "country"),
            "Ascot": ("WA", "metro"), "Hobart": ("TAS", "metro"),
            "Alice Springs": ("NT", "country"),
        }
        for venue, (state, tier) in cases.items():
            with self.subTest(venue=venue):
                self.assertEqual(generate_static.au_venue_profile(venue),
                                 {"state": state, "tier": tier})

    def test_unknown_venue_is_country_without_a_state(self):
        self.assertEqual(generate_static.au_venue_profile("Nowhere Park"),
                         {"state": "", "tier": "country"})

    def test_a_venue_is_never_both_metro_and_provincial(self):
        raw = json.loads(generate_static.AU_VENUE_TIERS_PATH.read_text(encoding="utf-8"))
        metro = {k for keys in raw["metropolitan"].values() for k in keys}
        provincial = {k for keys in raw["provincial"].values() for k in keys}
        self.assertEqual(metro & provincial, set())


class MeetingContextTests(unittest.TestCase):
    def _attach(self, timetable):
        meeting_data = {"date": "2026-10-31", "venue": "Traralgon", "region": "au"}
        races_data = {"races_by_analyst": {"Kelvin": [
            {"race_number": n, "start_time": 1, "abandoned": True} for n in (1, 4, 5)]}}
        with tempfile.TemporaryDirectory() as tmp:
            if timetable is not None:
                (Path(tmp) / generate_static.RACE_START_TIMES_FILE).write_text(json.dumps(timetable))
            meeting = SimpleNamespace(folder_paths={"Kelvin": tmp})
            generate_static._attach_meeting_context(meeting, meeting_data, races_data)
        return meeting_data, races_data["races_by_analyst"]["Kelvin"]

    def test_start_times_abandoned_races_and_tier_are_attached(self):
        meeting_data, races = self._attach({"races": {"1": 1793412960}, "abandoned": [4]})
        self.assertEqual((meeting_data["state"], meeting_data["tier"]), ("VIC", "country"))
        self.assertEqual(meeting_data["first_start"], 1793412960)
        self.assertEqual(races[0], {"race_number": 1, "start_time": 1793412960})
        self.assertEqual(races[1], {"race_number": 4, "abandoned": True})
        # No timetable entry and not abandoned: stale values from a base snapshot go.
        self.assertEqual(races[2], {"race_number": 5})

    def test_missing_timetable_clears_rather_than_guesses(self):
        meeting_data, races = self._attach(None)
        self.assertNotIn("first_start", meeting_data)
        self.assertTrue(all(set(r) == {"race_number"} for r in races))

    def test_hkjc_start_times_come_from_the_club_racecard(self):
        # HKJC's own racecard already carries 時間 (HK time): no Sportsbet, no extra
        # request. A Heison-only folder still counts; a stray timetable file is ignored.
        meeting_data = {"date": "2026-11-01", "venue": "HappyValley", "region": "hkjc"}
        races_data = {"races_by_analyst": {"Heison": [{"race_number": 1}, {"race_number": 2},
                                                      {"race_number": 3}]}}
        with tempfile.TemporaryDirectory() as tmp:
            for n, clock in ((1, "12:45"), (2, "13:15")):
                (Path(tmp) / f"11-01 Race {n} 排位表.md").write_text(
                    f"場次: 第{n}場\n日期: 2026-11-01\n地點: 跑馬地\n時間: {clock}\n", encoding="utf-8")
            (Path(tmp) / generate_static.RACE_START_TIMES_FILE).write_text(
                json.dumps({"races": {"1": 1, "2": 2, "3": 3}}))
            meeting = SimpleNamespace(region=generate_static.Region.HKJC, folder_paths={"Heison": tmp})
            generate_static._attach_meeting_context(meeting, meeting_data, races_data)
        races = races_data["races_by_analyst"]["Heison"]
        self.assertNotIn("tier", meeting_data)
        self.assertEqual(races[0]["start_time"], 1793508300)      # 12:45 HKT
        self.assertEqual(races[1]["start_time"], 1793510100)      # 13:15 HKT
        self.assertNotIn("start_time", races[2])                   # no racecard time

    def test_every_build_fills_tiers_for_previously_published_meetings(self):
        data = {"meetings": [{"date": "2026-10-31", "venue": "Randwick", "region": "au"},
                             {"date": "2026-11-01", "venue": "HappyValley", "region": "hkjc"}]}
        generate_static._ensure_au_venue_profiles(data)
        self.assertEqual(data["meetings"][0]["tier"], "metro")
        self.assertNotIn("tier", data["meetings"][1])


if __name__ == "__main__":
    unittest.main()
