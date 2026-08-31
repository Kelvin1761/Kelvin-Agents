from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT_DIR = ROOT / ".agents" / "skills" / "race_compliance_qa" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from race_compliance_scan import (
    check_placeholders,
    check_top4_drift,
    is_frozen_path,
    iter_live_files,
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


ANALYSIS_TEMPLATE = """
**第1選**
- **馬號及馬名:** [{a}] Alpha
**第2選**
- **馬號及馬名:** [{b}] Beta
**第3選**
- **馬號及馬名:** [{c}] Gamma
**第4選**
- **馬號及馬名:** [{d}] Delta
"""


def _logic(top4: list[str]) -> str:
    import json

    return json.dumps(
        {
            "horses": {n: {} for n in top4},
            "python_auto_verdict": {
                "ranking": [{"horse_number": n} for n in top4],
                "top4": [{"horse_number": n} for n in top4],
            },
        }
    )


class FrozenSubtreeTests(unittest.TestCase):
    """`_prediction_snapshots/` is frozen on purpose and must not be walked.

    2026-08-30: all six AU meetings exited rc=1 from the morning refresh because
    TOP4-001 compared a frozen snapshot's Analysis against the current Logic.
    The scheduler still recorded `status: ok` / `errors: []`, so a real failure
    would have looked identical.
    """

    def test_snapshot_analysis_does_not_trigger_drift(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # live pair agrees
            (root / "Race_2_Auto_Analysis.md").write_text(
                ANALYSIS_TEMPLATE.format(a="8", b="4", c="10", d="9"), encoding="utf-8"
            )
            (root / "Race_2_Logic.json").write_text(
                _logic(["8", "4", "10", "9"]), encoding="utf-8"
            )
            # frozen pre-refresh snapshot disagrees, exactly as it should
            snap = root / "_prediction_snapshots" / "20260829T155931+0000-abc"
            snap.mkdir(parents=True)
            (snap / "Race_2_Auto_Analysis.md").write_text(
                ANALYSIS_TEMPLATE.format(a="8", b="4", c="10", d="6"), encoding="utf-8"
            )

            self.assertEqual(check_top4_drift(root), [])

    def test_real_live_drift_is_still_critical(self) -> None:
        """Pruning snapshots must not turn the gate into a no-op."""
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Race_2_Auto_Analysis.md").write_text(
                ANALYSIS_TEMPLATE.format(a="8", b="4", c="10", d="9"), encoding="utf-8"
            )
            (root / "Race_2_Logic.json").write_text(
                _logic(["8", "4", "10", "6"]), encoding="utf-8"
            )

            issues = check_top4_drift(root)
            self.assertEqual([i.code for i in issues], ["TOP4-001"])
            self.assertEqual(issues[0].severity, "CRITICAL")
            # the LIVE file is named, not some snapshot copy
            self.assertTrue(issues[0].path.endswith("Race_2_Auto_Analysis.md"))
            self.assertNotIn("_prediction_snapshots", issues[0].path)

    def test_snapshot_cannot_mask_a_live_drift(self) -> None:
        """A snapshot that happens to match Logic must not overwrite the live entry.

        `analyses` is keyed by race number, so before the fix the last file the
        walk yielded won — which could be a stale snapshot that agreed with the
        current Logic, hiding a genuine live mismatch.
        """
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Race_2_Auto_Analysis.md").write_text(
                ANALYSIS_TEMPLATE.format(a="8", b="4", c="10", d="9"), encoding="utf-8"
            )
            (root / "Race_2_Logic.json").write_text(
                _logic(["8", "4", "10", "6"]), encoding="utf-8"
            )
            snap = root / "_prediction_snapshots" / "20260830T000616+0000-def"
            snap.mkdir(parents=True)
            # snapshot agrees with Logic — the masking shape
            (snap / "Race_2_Auto_Analysis.md").write_text(
                ANALYSIS_TEMPLATE.format(a="8", b="4", c="10", d="6"), encoding="utf-8"
            )

            self.assertEqual([i.code for i in check_top4_drift(root)], ["TOP4-001"])

    def test_frozen_dirnames_and_dot_dirs_are_pruned(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for sub in ("_prediction_snapshots", "_pre_v52_backup", "quarantine",
                        ".hkjc_cache", ".runtime", ".backup_before_trackwork_fix"):
                (root / sub).mkdir()
                (root / sub / "Race_1_Auto_Analysis.md").write_text("x", encoding="utf-8")
            (root / "Race_1_Auto_Analysis.md").write_text("x", encoding="utf-8")

            live = iter_live_files(root, "*.md")
            self.assertEqual([p.name for p in live], ["Race_1_Auto_Analysis.md"])
            self.assertEqual(live[0].parent, root)

    def test_live_files_are_shallowest_first(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nested").mkdir()
            (root / "nested" / "Race_1_Logic.json").write_text("{}", encoding="utf-8")
            (root / "Race_1_Logic.json").write_text("{}", encoding="utf-8")

            self.assertEqual(
                [p.parent for p in iter_live_files(root, "*.json")],
                [root, root / "nested"],
            )

    def test_is_frozen_path_ignores_the_filename_itself(self) -> None:
        root = Path("/meeting")
        self.assertFalse(is_frozen_path(root / ".hidden_report.md", root))
        self.assertTrue(is_frozen_path(root / "_prediction_snapshots" / "s" / "a.md", root))


if __name__ == "__main__":
    unittest.main()
