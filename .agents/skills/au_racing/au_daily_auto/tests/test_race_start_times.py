#!/usr/bin/env python3
"""每場開跑時間 —— dashboard「即將開跑」時間線嘅數據源。

由排程本身已經會抓嘅 Sportsbet AllRacing payload 抽出，唔加任何請求；寫落每個
場次 folder 嘅 Race_Start_Times.json。取消咗嘅場要明確列出（2026-10-31
Traralgon R4-R6），唔可以喺時間線靜靜消失。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import au_daily_schedule as S  # noqa: E402


def meeting(name, events, region="Australia"):
    return {"name": name, "regionName": region, "isInternational": False,
            "className": "Horses - Aus/NZ", "events": events}


def event(number, start, status="O"):
    return {"raceNumber": number, "startTime": start, "statusCode": status}


def allracing(*meetings, greyhounds=()):
    """The real AllRacing shape that _au_horse_meetings walks."""
    return {"dates": [{"sections": [
        {"raceType": "horse", "meetings": list(meetings)},
        {"raceType": "greyhound", "meetings": list(greyhounds)},
    ]}]}


class Log:
    def __init__(self):
        self.warnings = []
        self.data = {}

    def warn(self, message):
        self.warnings.append(message)


class RaceStartTimesTests(unittest.TestCase):
    def setUp(self):
        self.payload = allracing(
            meeting("Randwick", [event(1, 1793409000), event(2, 1793411100)]),
            meeting("Traralgon", [event(1, 1793412960), event(4, 0, "B"), event(5, 0, "B")]),
            meeting("Yeppoon", [event(1, 0, "B")]),
            meeting("Ellerslie", [event(1, 1793400000)], region="New Zealand"),
            greyhounds=[meeting("Sandown Park", [event(1, 1793400000)])],
        )

    def test_every_race_start_and_every_abandoned_race_is_kept(self):
        starts = S.au_race_start_times(self.payload)
        self.assertEqual(starts["Randwick"], {"races": {"1": 1793409000, "2": 1793411100},
                                              "abandoned": [], "events": {}})
        self.assertEqual(starts["Traralgon"]["races"], {"1": 1793412960})
        self.assertEqual(starts["Traralgon"]["abandoned"], [4, 5])
        self.assertEqual(starts["Yeppoon"], {"races": {}, "abandoned": [1], "events": {}})
        # NZ and greyhound meetings never reach the AU timeline.
        self.assertEqual(set(starts), {"Randwick", "Traralgon", "Yeppoon"})

    def test_written_beside_the_analysis_and_matched_by_venue_key(self):
        starts = S.au_race_start_times(self.payload)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "2026-10-31 Traralgon Race 1-7"
            folder.mkdir()
            self.assertTrue(S.record_race_start_times(Log(), folder, "traralgon", starts))
            body = json.loads((folder / S.RACE_START_TIMES_FILE).read_text())
        self.assertEqual(body["source"], "sportsbet-allracing")
        self.assertEqual(body["races"], {"1": 1793412960})
        self.assertEqual(body["abandoned"], [4, 5])

    def test_unchanged_timetable_is_not_rewritten(self):
        # A rewrite bumps the folder mtime, which find_meeting_dir sorts by.
        starts = S.au_race_start_times(self.payload)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            S.record_race_start_times(Log(), folder, "Randwick", starts)
            path = folder / S.RACE_START_TIMES_FILE
            before = path.stat().st_mtime_ns
            S.record_race_start_times(Log(), folder, "Randwick", starts)
            self.assertEqual(path.stat().st_mtime_ns, before)
            starts["Randwick"]["races"]["2"] += 300          # race re-timed
            S.record_race_start_times(Log(), folder, "Randwick", starts)
            self.assertEqual(json.loads(path.read_text())["races"]["2"], 1793411400)

    def test_missing_folder_or_meeting_never_fails_the_run(self):
        starts = S.au_race_start_times(self.payload)
        log = Log()
        self.assertFalse(S.record_race_start_times(log, None, "Randwick", starts))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(S.record_race_start_times(log, Path(tmp), "Flemington", starts))
            self.assertFalse(S.record_race_start_times(log, Path(tmp) / "gone", "Randwick", starts))
        self.assertEqual(len(log.warnings), 1)          # the unwritable folder is reported

    def test_new_or_retimed_timetable_marks_the_meeting_for_republish(self):
        # 2026-11-01: meetings with no analysis change were never re-merged, so
        # their times never reached the board.
        starts = S.au_race_start_times(self.payload)
        with tempfile.TemporaryDirectory() as tmp:
            log = Log()
            S.record_race_start_times(log, Path(tmp), "Randwick", starts)
            self.assertEqual(log.data["timetables_changed"], [tmp])
            again = Log()
            S.record_race_start_times(again, Path(tmp), "Randwick", starts)
            self.assertNotIn("timetables_changed", again.data)      # unchanged: no republish
            starts["Randwick"]["races"]["1"] += 120
            S.record_race_start_times(again, Path(tmp), "Randwick", starts)
            self.assertEqual(again.data["timetables_changed"], [tmp])


    def test_morning_writes_every_live_meeting_before_and_without_analysis(self):
        # 2026-11-01: times only came from the analysis step, behind the
        # sportsbetform index page, and never on the --skip-analysis midday run.
        payload = allracing(
            meeting("Gold Coast", [event(1, 1793409000)]),
            meeting("Gold Coast Poly", [event(1, 1793412000)]),
            meeting("Randwick", [event(1, 1793409600)]),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("2026-11-01 Gold Coast Poly Race 1-8", "2026-11-01 Randwick Race 1-9",
                         "2026-11-01 Bendigo Race 1-7", "2026-10-31 Randwick Race 1-9"):
                (root / name).mkdir()
            log = Log()
            log.step = lambda *a, **k: setattr(log, "last_step", (a, k))
            original_root, original_api = S.AU_RACING, S.api_day_meetings
            S.AU_RACING = root
            S.api_day_meetings = lambda _log, _day, race_starts=None, **_: \
                race_starts.update(S.au_race_start_times(payload)) or []
            try:
                changed = S.step_race_start_times(log, S.date(2026, 11, 1))
            finally:
                S.AU_RACING, S.api_day_meetings = original_root, original_api
            poly = json.loads((root / "2026-11-01 Gold Coast Poly Race 1-8"
                               / S.RACE_START_TIMES_FILE).read_text())
            self.assertEqual(poly["races"], {"1": 1793412000})        # not Gold Coast turf
            self.assertTrue((root / "2026-11-01 Randwick Race 1-9" / S.RACE_START_TIMES_FILE).exists())
            self.assertFalse((root / "2026-10-31 Randwick Race 1-9" / S.RACE_START_TIMES_FILE).exists())
            self.assertEqual(len(changed), 2)                          # both go back on the board
            self.assertEqual(log.last_step[1]["missing"], ["2026-11-01 Bendigo Race 1-7"])
            self.assertEqual(len(log.warnings), 1)                     # the unmatched one is reported


class WatchLiveEventTests(unittest.TestCase):
    """睇直播掣：Sportsbet race page 只靠 event id 開，Sky 頻道由 AllRacing 逐場列。"""

    def _event(self, number, event_id, channel=None, provider="sky"):
        out = {"raceNumber": number, "startTime": 1793672940, "statusCode": "O",
               "id": event_id}
        if channel is not None:
            out["streaming"] = {"liveStream": {"provider": provider, "channel": channel}}
        return out

    def test_event_id_and_sky_channel_are_kept(self):
        payload = allracing(meeting("Sunshine Coast", [
            self._event(1, 11113186, "1"), self._event(2, 11113187, "2"),
            self._event(3, 11113188), self._event(4, 11113189, "1", provider="other")]))
        events = S.au_race_start_times(payload)["Sunshine Coast"]["events"]
        self.assertEqual(events["1"], {"id": 11113186, "sky": "1"})
        self.assertEqual(events["2"], {"id": 11113187, "sky": "2"})
        self.assertEqual(events["3"], {"id": 11113188, "sky": None})   # no stream listed
        self.assertEqual(events["4"]["sky"], None)                     # not a Sky stream

    def test_new_events_rewrite_an_otherwise_unchanged_timetable(self):
        """Folders written before this change must gain events on the next run."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / S.RACE_START_TIMES_FILE
            path.write_text(json.dumps({"races": {"1": 1793672940}, "abandoned": []}))
            found = {"races": {"1": 1793672940}, "abandoned": [],
                     "events": {"1": {"id": 11113186, "sky": "1"}}}
            from sportsbet_race_times import write_race_start_times
            self.assertTrue(write_race_start_times(Path(tmp), "Sunshine Coast", found))
            self.assertEqual(json.loads(path.read_text())["events"]["1"]["id"], 11113186)


if __name__ == "__main__":
    unittest.main()
