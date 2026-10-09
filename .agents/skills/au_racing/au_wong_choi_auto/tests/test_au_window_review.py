from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import au_window_review as w  # noqa: E402


class SnapshotTimeTest(unittest.TestCase):
    def test_utc_and_local_stamps_both_parse_with_their_offset(self):
        # 2026-09 中之後快照名改用悉尼本地時間；當晒 UTC 會錯揀前一晚嗰份。
        utc = w.snapshot_time("20260912T004237.767999+0000-a5e3a320c751")
        local = w.snapshot_time("20260926T103912.870573+1000-d25691af6575")
        self.assertEqual(utc.utcoffset(), timedelta(0))
        self.assertEqual(local.utcoffset(), timedelta(hours=10))
        self.assertEqual(local.astimezone(w.SYD).hour, 10)
        self.assertEqual(utc.astimezone(w.SYD).hour, 10)

    def test_pick_snapshot_prefers_latest_before_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            meeting = Path(tmp) / "2026-09-26 Rosehill Race 1-10"
            snaps = meeting / "_prediction_snapshots"
            for name in ("20260926T024241.093089+1000-aaaa",   # 前一晚
                         "20260926T103912.870573+1000-bbbb",   # 早更
                         "20260926T210000.000000+1000-cccc"):  # 賽後
                (snaps / name).mkdir(parents=True)
            snap, rule, local = w.pick_snapshot(meeting, "2026-09-26")
            self.assertEqual(snap.name, "20260926T103912.870573+1000-bbbb")
            self.assertEqual(rule, "pre_cutoff")
            self.assertEqual(local, "2026-09-26 10:39")

    def test_post_race_only_snapshot_is_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            meeting = Path(tmp) / "2026-10-03 Kalgoorlie Race 1-9"
            (meeting / "_prediction_snapshots" / "20261003T211100.000000+1000-dddd").mkdir(parents=True)
            snap, rule, _ = w.pick_snapshot(meeting, "2026-10-03")
            self.assertIsNone(snap)
            self.assertEqual(rule, "none")


class ResultsParseTest(unittest.TestCase):
    def test_reflector_results_keep_number_position_and_sp(self):
        text = "\n".join([
            "# Flemington Race Results — 2026-09-12",
            "## Race 1",
            "1st: #6 Jett Smash SP$4.40",
            "2nd: #1 Space Rider (2.75L) SP$6.00",
            "3rd: #12 Somethings Burnin' (1.21L) SP$4.60",
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Race_Results_Reflector.md"
            path.write_text(text, encoding="utf-8")
            res = w.parse_reflector_results(path)
        self.assertEqual(res[1][6], {"pos": 1, "name": "Jett Smash", "sp": 4.4})
        self.assertEqual(res[1][12]["name"], "Somethings Burnin'")
        self.assertEqual(res[1][1]["pos"], 2)


class BucketTest(unittest.TestCase):
    def test_class_bucket(self):
        self.assertEqual(w.class_bucket("Fitzsimmons Racing BM66 Handicap"), "BM64-76")
        self.assertEqual(w.class_bucket("QUAYCLEAN MAIDEN"), "Maiden")
        self.assertEqual(w.class_bucket("Sportsbet Sir Rupert Clarke Stakes"), "Stakes/Plate/Open")

    def test_venue_state_uses_longest_match(self):
        self.assertEqual(w.venue_state("Warwick Farm"), "NSW")
        self.assertEqual(w.venue_state("Warwick"), "QLD")
        self.assertEqual(w.venue_state("Murray Bridge"), "SA")
        self.assertEqual(w.venue_state("Randwick-Kensington"), "NSW")


class StartTimeTest(unittest.TestCase):
    def test_start_times_come_from_cached_race_page_nav(self):
        import hashlib, json
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "map.json").write_text(json.dumps({"2026-10-03 Eagle Farm Race 1-10": {
                "date": "2026-10-03", "meetingId": "451966", "races": ["3439800"]}}))
            url = "https://www.sportsbetform.com.au/451966/3439800/"
            nav = ('<a class="raceLink" href="/451966/3439800/">Race 1<abbr data-utime="1790991480"></abbr></a>'
                   '<a class="raceLink" href="/451966/3439801/">Race 2<abbr data-utime="1790993580"></abbr></a>')
            (tmp / (hashlib.sha1(url.encode()).hexdigest() + ".html")).write_text(nav)
            starts = w.load_start_times(tmp / "map.json", tmp)("2026-10-03 Eagle Farm Race 1-10")
            self.assertEqual(sorted(starts), [1, 2])
            self.assertLess(starts[1], starts[2])
            self.assertEqual(w.load_start_times(tmp / "map.json", tmp)("unknown"), {})

    def test_each_race_uses_latest_snapshot_before_its_own_start(self):
        # 10-03：早更 10:00 開、11:13 先完，快照 11:11 —— 固定 11:00 截止會錯揀前一晚嗰份。
        with tempfile.TemporaryDirectory() as tmp:
            meeting = Path(tmp) / "2026-10-03 Eagle Farm Race 1-10"
            for name in ("20261003T030043.162256+1000-aaaa", "20261003T111150.923574+1000-bbbb"):
                (meeting / "_prediction_snapshots" / name).mkdir(parents=True)
            stamped = w.stamped_snapshots(meeting)
            start = w.datetime(2026, 10, 3, 11, 58, tzinfo=w.SYD)
            snap, rule, _ = w.pick_for_race(stamped, start, meeting, "2026-10-03")
            self.assertTrue(snap.name.startswith("20261003T111150"))
            self.assertEqual(rule, "pre_start")
            early = w.datetime(2026, 10, 3, 2, 0, tzinfo=w.SYD)
            self.assertIsNone(w.pick_for_race(stamped, early, meeting, "2026-10-03")[0])


if __name__ == "__main__":
    unittest.main()
