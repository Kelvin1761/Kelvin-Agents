from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT_DIR = ROOT / ".agents" / "skills" / "race_compliance_qa" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from race_compliance_scan import (
    check_placeholders,
    parse_analysis_top4,
    parse_logic_top4,
    parse_result_json,
)


class RaceComplianceScanTests(unittest.TestCase):
    def test_parse_result_json_supports_archive_results_mapping(self) -> None:
        parsed = parse_result_json(
            {
                "meeting": {"name": "Canterbury"},
                "events": {"7": {"event_number": 7}},
                "results": {
                    "7": [
                        {"competitor_number": 3, "horse_name": "Mountain Chatter", "finish_position": 1},
                        {"competitor_number": 13, "horse_name": "Dear Jewel", "finish_position": 2},
                    ]
                },
            }
        )

        self.assertEqual(parsed[7], [(1, 3, "Mountain Chatter"), (2, 13, "Dear Jewel")])

    def test_archive_mapping_excludes_scratched_runners(self) -> None:
        """Scratched runners carry finish_position -1 in the archive dialect.

        parse_int() digit-scrapes "-1" to 1, so an unguarded parse invents a
        phantom winner that outranks the real one. All 35 real AU
        Race_Results_*.json files contain such rows (1027 of 4401).
        """
        parsed = parse_result_json(
            {
                "results": {
                    "4": [
                        {
                            "competitor_number": 9,
                            "horse_name": "Scratched Horse",
                            "finish_position": -1,
                            "is_scratched": True,
                        },
                        {
                            "competitor_number": 2,
                            "horse_name": "Real Winner",
                            "finish_position": 1,
                            "is_scratched": False,
                        },
                    ]
                }
            }
        )

        self.assertEqual(parsed[4], [(1, 2, "Real Winner")])

    def test_archive_mapping_sorts_by_finish_position(self) -> None:
        parsed = parse_result_json(
            {
                "results": {
                    "2": [
                        {"competitor_number": 5, "horse_name": "Third", "finish_position": 3},
                        {"competitor_number": 1, "horse_name": "First", "finish_position": 1},
                        {"competitor_number": 8, "horse_name": "Second", "finish_position": 2},
                    ]
                }
            }
        )

        self.assertEqual(
            parsed[2],
            [(1, 1, "First"), (2, 8, "Second"), (3, 5, "Third")],
        )

    def test_legacy_dialects_still_parse(self) -> None:
        """The archive branch must not regress the older shapes."""
        # list of races, pos / horse_no
        self.assertEqual(
            parse_result_json(
                [
                    {
                        "results": [
                            {"pos": 2, "horse_no": 7, "horse_name": "B"},
                            {"pos": 1, "horse_no": 4, "horse_name": "A"},
                        ]
                    }
                ]
            ),
            {1: [(1, 4, "A"), (2, 7, "B")]},
        )
        # {"races": {...}} wrapper, position / num
        self.assertEqual(
            parse_result_json({"races": {"3": {"results": [{"position": 1, "num": 9, "name": "C"}]}}}),
            {3: [(1, 9, "C")]},
        )
        # explicit race_no inside the race payload, rank / horse_number
        self.assertEqual(
            parse_result_json(
                {"whatever": {"race_no": 5, "results": [{"rank": 1, "horse_number": 2, "name": "D"}]}}
            ),
            {5: [(1, 2, "D")]},
        )

    def test_empty_archive_results_falls_through_to_generic_walk(self) -> None:
        """An empty `results` mapping must not swallow a parseable sibling race."""
        parsed = parse_result_json(
            {
                "results": {},
                "7": {"results": [{"pos": 1, "horse_no": 3, "name": "E"}]},
            }
        )

        self.assertEqual(parsed, {7: [(1, 3, "E")]})

    def test_non_result_payloads_return_empty(self) -> None:
        for payload in ("nope", 42, None, [], {}, {"a": 1}):
            with self.subTest(payload=payload):
                self.assertEqual(parse_result_json(payload), {})

    def test_hkjc_url_keyed_result_cache_parses(self) -> None:
        payload = {
            "https://racing.hkjc.com/results?RaceNo=7": [
                {"placing": 1, "horse_no": 5, "horse_name": "Winner"},
                {"placing": 2, "horse_no": 11, "horse_name": "Second"},
            ]
        }
        self.assertEqual(
            parse_result_json(payload),
            {7: [(1, 5, "Winner"), (2, 11, "Second")]},
        )

    def test_current_python_auto_verdict_is_canonical_top4(self) -> None:
        data = {
            "race_analysis": {"verdict": {}},
            "python_auto_verdict": {
                "top4": [
                    {"horse_number": "3"},
                    {"horse_number": "1"},
                    {"horse_number": "7"},
                    {"horse_number": "2"},
                ]
            },
        }
        self.assertEqual(parse_logic_top4(data), ["3", "1", "7", "2"])

    def test_small_field_can_have_fewer_than_four_canonical_picks(self) -> None:
        from tempfile import TemporaryDirectory
        import json
        from race_compliance_scan import check_top4_drift

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Race_1_Logic.json").write_text(
                json.dumps(
                    {
                        "horses": {"1": {}, "2": {}},
                        "python_auto_verdict": {
                            "ranking": [
                                {"horse_number": "1"},
                                {"horse_number": "2"},
                            ],
                            "top4": [
                                {"horse_number": "1"},
                                {"horse_number": "2"},
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(check_top4_drift(root), [])

    def test_current_hkjc_numbered_top4_markdown_parses(self) -> None:
        text = """
**第1選**
- **馬號及馬名:** [1] Alpha
**第2選**
- **馬號及馬名:** [2] Beta
**第3選**
- **馬號及馬名:** [8] Gamma
**第4選**
- **馬號及馬名:** [9] Delta
"""
        self.assertEqual(parse_analysis_top4(text), ["1", "2", "8", "9"])

    def test_legacy_placeholders_do_not_fail_canonical_auto_layer(self) -> None:
        from tempfile import TemporaryDirectory
        import json

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "Race_1_Logic.json"
            path.write_text(
                json.dumps(
                    {
                        "python_auto_verdict": {"top4": [{"horse_number": "1"}]},
                        "horses": {
                            "1": {
                                "core_logic": "[FILL]",
                                "base_rating": "[AUTO]",
                                "python_auto": {"core_logic": "完整 deterministic 判讀"},
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.assertEqual(check_placeholders(path), [])


if __name__ == "__main__":
    unittest.main()
