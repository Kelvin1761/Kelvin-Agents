"""Validate GPS decomposition, benchmark semantics and strict prior-date fits."""

from copy import deepcopy
import unittest

from au_contextual_gps_speed_20261015 import (
    aggregate,
    ContextStandard,
    date_features,
    source_rows,
    track_variants,
    zscores,
    parse_xml,
    class_key,
)


def events():
    rows = []
    for i in range(120):
        distance = (1000, 1200, 1400, 1600)[i % 4]
        track = "ipswich" if i % 2 else "doomben"
        day = f"2026-07-{1 + i // 12:02}"
        total = distance / 16 + (i % 3) * 0.2
        early = (distance - 800) / 15 + (i % 3) * 0.1
        key = (track, day, i % 12 + 1, distance)
        rows.append(
            {
                "date": day,
                "track": track,
                "going": "good",
                "class": "BM64",
                "distance": distance,
                "key": key,
                "total": total,
                "early": early,
                "rows": [
                    {"horse": f"horse{j}", "time": total + j * 0.2, "early": early + j * 0.1, "distance": distance}
                    for j in range(3)
                ],
            }
        )
    return rows


class ContextSpeedTests(unittest.TestCase):
    def test_sponsor_group_is_not_group_race(self):
        self.assertEqual(class_key("RaceClass:[ACME Group Handicap]"), "Open")
        self.assertEqual(class_key("RaceClass:[GROUP 3 Sprint]"), "Group")

    def test_xml_uses_horse_finish_not_race_header(self):
        sections = "".join(
            f'<SectionSummary CumulatedDistance="{200 + i * 200}"><SectionTime Time="00:00:12.000"/></SectionSummary>'
            for i in range(5)
        )
        horses = "".join(
            f'<HorseSummary Name="Horse {i}" HorseCode="{i}" IsFinishTimeOfficial="true"><FinishTime Time="00:01:00.000"/><Sections>{sections}</Sections></HorseSummary>'
            for i in range(3)
        )
        xml = f'<RaceSummary EventDate="2026-09-01T00:00:00"><CourseName>Ipswich</CourseName><RaceName>BENCHMARK 65 Handicap</RaceName><TrackCondition>Soft6</TrackCondition><RailPosition>+6m Entire</RailPosition><FinishTime Time="00:01:10.000"/><Horses>{horses}</Horses></RaceSummary>'
        event = parse_xml(xml.encode(), "official_R01.xml")
        self.assertEqual(event["rating"], "6")
        self.assertEqual(event["rail"], "6")
        self.assertEqual(event["rows"][0]["time"], 60.0)
        self.assertEqual(event["rows"][0]["early"], 12.0)

    def test_legacy_compact_header_date(self):
        header = "Date,RaceNumber,date;20250301 Eagle Farm QLD - Professional;Race;1:00;EAGL_1000m_TRACK\n"
        payload = ";".join(f"{200 + i * 200};17;0:12.00" for i in range(5))
        rows, _ = source_rows(header + "01/03/2025,1,Older Horse;2;" + payload, "official")
        self.assertEqual(rows[0]["date"], "2025-03-01")
        self.assertEqual(rows[0]["track"], "eaglefarm")
        self.assertEqual(rows[0]["early"], 12.0)

    def test_total_minus_l800_is_own_early_time(self):
        header = "Date,RaceNumber,date;2026-10-08 Ipswich QLD - Professional;Race;00:01:42.825;IPSW_1666m_TRACK\n"
        splits = [18.38, 11.77, 12.06, 12.25, 12.27, 11.87, 11.46, 11.75]
        payload = ";".join(f"{266 + i * 200};17;00:00:{value:.2f}" for i, value in enumerate(splits))
        rows, _ = source_rows(header + "08/10/2026,1,Swanfels;5;" + payload, "official")
        self.assertAlmostEqual(rows[0]["time"], 101.81)
        self.assertAlmostEqual(rows[0]["l800"], 47.35)
        self.assertAlmostEqual(rows[0]["early"], 54.46)
        self.assertAlmostEqual((rows[0]["distance"] - 800) / rows[0]["early"], 15.90157914)

    def test_no_early_signal_at_800m(self):
        header = "Date,RaceNumber,date;2026-10-08 Ipswich QLD - Professional;Race;00:00:46;IPSW_800m_TRACK\n"
        payload = ";".join(f"{200 + i * 200};18;00:00:12.00" for i in range(4))
        rows, _ = source_rows(header + "08/10/2026,1,Short Horse;3;" + payload, "official")
        self.assertEqual(rows, [])

    def test_future_source_cannot_change_prior_features(self):
        history = events()
        before, state = date_features(history, "2026-08-05")
        future = deepcopy(history[0])
        future.update(date="2026-08-05", total=3000, early=2500)
        after, after_state = date_features(history + [future], "2026-08-05")
        self.assertEqual(before, after)
        self.assertEqual(state, after_state)

    def test_common_class_time_does_not_reward_the_label_itself(self):
        history = events()
        model = ContextStandard(history, "total")
        first = history[0]
        second = {**first, "class": "Group"}
        self.assertEqual(model.predict(first, True), model.predict(second, True))

    def test_variant_excludes_own_race(self):
        history = events()
        total = ContextStandard(history, "total")
        early = ContextStandard(history, "early")
        before = track_variants(history, total, early)
        changed = deepcopy(history)
        changed[0]["total"] *= 2
        changed[0]["early"] *= 2
        after = track_variants(changed, total, early)
        self.assertEqual(before[history[0]["key"]], after[history[0]["key"]])

    def test_distance_transfer_reduces_reliability(self):
        key = ("ipswich", "2026-09-01", 1, 1000)
        source = {(key, "horse"): {"A": 3.0, "B": 4.0, "C": 1.0, "going": "good"}}
        same, n, confidence = aggregate([key], "horse", "2026-09-03", 1000, "good", source)
        _, _, far_confidence = aggregate([key], "horse", "2026-09-03", 2000, "good", source)
        self.assertEqual(n, 1)
        self.assertEqual(same["A"], 3.0)
        self.assertGreater(confidence["A"], far_confidence["A"])
        self.assertLess(confidence["A"], 0.25)

    def test_target_and_future_runs_do_not_aggregate(self):
        key = ("ipswich", "2026-10-01", 1, 1000)
        source = {(key, "horse"): {"A": 3.0, "B": 4.0, "C": 1.0, "going": "good"}}
        values, n, confidence = aggregate([key], "horse", "2026-10-01", 1000, "good", source)
        self.assertEqual(n, 0)
        self.assertTrue(all(value is None for value in values.values()))
        self.assertTrue(all(value == 0 for value in confidence.values()))

    def test_missing_values_are_neutral_in_race_normalisation(self):
        self.assertEqual(zscores([None, 1.0, 3.0]), [0.0, -1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
