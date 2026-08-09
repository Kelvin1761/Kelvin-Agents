from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = (
    ROOT
    / ".agents"
    / "skills"
    / "au_racing"
    / "au_wong_choi_auto"
    / "scripts"
)
ENGINE = SCRIPTS / "racing_engine"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ENGINE))

from au_auto_orchestrator import (
    _validate_input_shape,
    _validate_race_identity,
    _write_json_atomic,
    process_meeting_dir,
)
from build_au_logic import _extract_race_meta
from source_alignment import (
    normalize_horse_name,
    race_source_candidates,
    validate_facts_horse_alignment,
    venue_from_meeting_name,
)


FACTS = "\n".join(
    [
        "### 馬匹 #1 Alpha (NZ) (檔位 3) | 騎師: A Rider | 練馬師: A Trainer | 負重: 58kg",
        "data",
        "### 馬匹 #2 Bravo (檔位 7) | 騎師: B Rider | 練馬師: B Trainer | 負重: 未知",
        "data",
    ]
)


class SourceAlignmentTests(unittest.TestCase):
    def test_parser_accepts_unknown_weight_and_normalizes_country_suffix(self) -> None:
        matches = validate_facts_horse_alignment(FACTS)
        self.assertEqual([match.group(1) for match in matches], ["1", "2"])
        self.assertEqual(normalize_horse_name("Alpha (NZ)"), "alpha")

    def test_malformed_header_fails_loudly(self) -> None:
        malformed = FACTS.replace("(檔位 7)", "(檔位 ?)")
        with self.assertRaisesRegex(ValueError, "2 horse blocks but only 1 parsed"):
            validate_facts_horse_alignment(malformed)

    def test_empty_facts_fails_loudly(self) -> None:
        with self.assertRaisesRegex(ValueError, "no horse blocks found"):
            validate_facts_horse_alignment("")

    def test_facts_and_logic_runner_sets_must_match(self) -> None:
        with self.assertRaisesRegex(ValueError, "Logic runners absent from Facts"):
            validate_facts_horse_alignment(
                FACTS,
                logic_horse_keys={"1", "2", "9"},
            )

    def test_spaced_and_underscore_race_sources_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            spaced = folder / "07-15 Race 2 Racecard.md"
            underscore = folder / "07-15 Race_2_Racecard.md"
            spaced.write_text("x", encoding="utf-8")
            underscore.write_text("x", encoding="utf-8")
            self.assertEqual(
                race_source_candidates(folder, 2, "Racecard"),
                sorted([spaced, underscore]),
            )

    def test_venue_parser_handles_multiword_and_underscore_names(self) -> None:
        self.assertEqual(
            venue_from_meeting_name("2026-07-15 Warwick Farm Race 1-7"),
            "Warwick Farm",
        )
        self.assertEqual(
            venue_from_meeting_name("2026-07-25_Eagle_Farm_Race_1_9"),
            "Eagle Farm",
        )

    def test_empty_racecard_has_a_clear_source_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            facts = folder / "07-15 Race 5 Facts.md"
            facts.write_text("今仗距離: 1400m", encoding="utf-8")
            (folder / "07-15 Race 5 Racecard.md").write_text(
                "",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Racecard is empty"):
                _extract_race_meta(facts, facts.read_text(encoding="utf-8"))


class AutoPipelineGuardTests(unittest.TestCase):
    def test_race_filename_and_metadata_must_match(self) -> None:
        with self.assertRaisesRegex(ValueError, "Race identity mismatch"):
            _validate_race_identity(Path("Race_4_Logic.json"), 5)

    def test_empty_horse_object_is_rejected_before_scoring(self) -> None:
        with self.assertRaisesRegex(ValueError, "horses must be a non-empty"):
            _validate_input_shape(
                Path("Race_1_Logic.json"),
                {"race_analysis": {"race_number": 1}, "horses": {}},
            )

    def test_atomic_json_write_never_leaves_partial_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Race_1_Logic.json"
            _write_json_atomic(path, {"race_analysis": {"race_number": 1}})
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["race_analysis"][
                    "race_number"
                ],
                1,
            )
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_atomic_json_serialization_failure_preserves_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Race_1_Logic.json"
            path.write_text("KEEP_EXISTING\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Failed to serialize"):
                _write_json_atomic(path, {"not_json": object()})
            self.assertEqual(path.read_text(encoding="utf-8"), "KEEP_EXISTING\n")
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_corrupt_race_aborts_meeting_instead_of_writing_partial_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "Race_1_Logic.json").write_text("", encoding="utf-8")
            summary = folder / "Meeting_Auto_Scoring.csv"
            summary.write_text("KEEP_EXISTING\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Failed to read/parse"):
                process_meeting_dir(folder)
            self.assertEqual(
                summary.read_text(encoding="utf-8"),
                "KEEP_EXISTING\n",
            )

    def test_late_corrupt_race_is_rejected_before_earlier_outputs_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "Race_1_Logic.json").write_text(
                json.dumps(
                    {
                        "race_analysis": {"race_number": 1},
                        "horses": {"1": {"horse_name": "Valid Runner"}},
                    }
                ),
                encoding="utf-8",
            )
            (folder / "Race_2_Logic.json").write_text("", encoding="utf-8")
            existing = folder / "Race_1_Auto_Analysis.md"
            existing.write_text("KEEP_EXISTING\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Race_2_Logic"):
                process_meeting_dir(folder)
            self.assertEqual(
                existing.read_text(encoding="utf-8"),
                "KEEP_EXISTING\n",
            )


if __name__ == "__main__":
    unittest.main()
