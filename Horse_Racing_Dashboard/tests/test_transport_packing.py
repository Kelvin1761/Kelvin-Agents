"""2026-10-31：16 個 AU 場次只上咗 9 個 dashboard。

snapshot JSON 去到 25.7–26.9 MiB，撞 Cloudflare 單檔 25 MiB 上限：tennis
tracking 14,350 條（12.2 MiB）以 plain JSON 放喺入面，而 raw_text 逐匹馬
gzip 唔可以共用字典（812 匹 5.78 MiB）。只增唔減嘅內容一定要打包；呢度鎖住
「打包 → 還原」完全無損、排程驗證用嘅欄位冇被打包、同埋 size 閘門講得出
真正最大嗰部份。
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parents[1]
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

import generate_static  # noqa: E402

KEY = "2026-10-31|Randwick"


def payload(records=3000):
    prose = "段速、步速同證據都支持。" * 40
    horses = [{"horse_number": n, "score": 70 + n, "odds": 3.5,
               "raw_text": f"### No.{n}\n{prose}",
               "data_readout": [{"label": "段速", "text": prose}],
               "dimension_details": [{"dimension": "form", "score": 61.5}]}
              for n in range(1, 13)]
    return {
        "meetings": [{"date": "2026-10-31", "venue": "Randwick", "region": "AU"}],
        "races": {KEY: {"races_by_analyst": {
            # An analyst name containing the key separator must still resolve.
            "Kelvin|AU": [{"race_number": r, "horses": copy.deepcopy(horses)}
                          for r in (1, 2)]}}},
        "consensus": {},
        "sports_feed": {"sports": {"tennis": {"validation_status": "valid", "tracking": {
            "status": "valid", "covered_dates": ["2026-10-30"],
            "records": [{"id": f"tennis:{i}", "day": "2026-07-01", "state": "lost",
                         "evidence_note": "PROP_3_LEG_TRIAL 3 legs " * 4}
                        for i in range(records)]}}}},
    }


def write_raw(tmp, data):
    path = Path(tmp) / "snapshot.json"
    path.write_text(json.dumps(data))
    return path


class TransportPackingTests(unittest.TestCase):
    def test_round_trip_is_lossless_and_leaves_input_untouched(self):
        data = payload()
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            for _ in range(3):      # the merge base is re-read and re-written all day
                generate_static._write_json(path, data)
                self.assertEqual(data, original)
                data = generate_static.load_snapshot(path)
                self.assertEqual(data, original)

    def test_scheduler_fields_stay_plain_and_bulk_is_packed(self):
        packed = generate_static.pack_for_transport(payload())
        entry = packed["races"][KEY]
        race = entry["races_by_analyst"]["Kelvin|AU"][1]
        horse = race["horses"][0]
        # validate_snapshot / dashboard_odds_issues read these with a bare json.loads.
        self.assertEqual(race["race_number"], 2)
        self.assertEqual((horse["horse_number"], horse["score"], horse["odds"]), (1, 71, 3.5))
        for field in generate_static.PACKED_HORSE_FIELDS:
            self.assertNotIn(field, horse)
        self.assertIn("horse_fields_gzip", entry)
        tracking = packed["sports_feed"]["sports"]["tennis"]["tracking"]
        self.assertNotIn("records", tracking)
        self.assertEqual(tracking["records_count"], 3000)
        self.assertEqual(tracking["covered_dates"], ["2026-10-30"])

    def test_packing_is_far_smaller_than_plain(self):
        data = payload()
        plain = len(json.dumps(data, ensure_ascii=False).encode())
        packed = len(json.dumps(generate_static.pack_for_transport(data),
                                ensure_ascii=False).encode())
        self.assertLess(packed, plain / 8)

    def test_legacy_per_horse_snapshot_is_still_readable(self):
        data = payload(records=2)
        expected = copy.deepcopy(data)
        legacy = copy.deepcopy(data)
        for horse in generate_static._snapshot_horses(legacy):
            horse["raw_text_gzip"] = generate_static.base64.b64encode(
                generate_static.gzip.compress(horse.pop("raw_text").encode())).decode()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(generate_static.load_snapshot(write_raw(tmp, legacy)), expected)

    def test_html_carries_the_packed_form(self):
        html = generate_static.generate_html(payload())
        self.assertIn('"horse_fields_gzip"', html)
        self.assertIn('"records_gzip"', html)
        self.assertIn("unpackDashboardData", html)
        self.assertNotIn("段速、步速同證據都支持。", html)

    def test_truncated_tracking_fails_closed(self):
        data = generate_static.pack_for_transport(payload(records=5))
        data["sports_feed"]["sports"]["tennis"]["tracking"]["records_count"] = 6
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                generate_static.load_snapshot(write_raw(tmp, data))

    def test_bundle_that_does_not_match_its_races_fails_closed(self):
        data = generate_static.pack_for_transport(payload(records=0))
        data["races"][KEY]["races_by_analyst"]["Kelvin|AU"].pop()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                generate_static.load_snapshot(write_raw(tmp, data))

    def test_size_gate_names_the_measured_largest_section(self):
        # The old message always blamed raw_text; on 2026-10-31 it was tennis.
        data = payload(records=3000)
        self.assertEqual(generate_static._size_breakdown(data)[0][0], "sports_feed/tennis")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.json"
            path.write_bytes(b"0" * generate_static.CLOUDFLARE_ASSET_LIMIT)
            with self.assertRaises(SystemExit) as raised:
                generate_static._check_upload_size(path, "Snapshot JSON", lambda: data)
        self.assertIn("sports_feed/tennis", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
