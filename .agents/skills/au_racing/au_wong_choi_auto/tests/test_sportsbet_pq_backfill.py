from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_backfill_sportsbet_performance_quality import backfill_archive  # noqa: E402


class SportsbetPQBackfillTest(unittest.TestCase):
    def test_dry_run_is_non_mutating_and_apply_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            meeting = root / "2026-08-01 Randwick Race 1-1"
            meeting.mkdir()
            path = meeting / "Race_1_Logic.json"
            logic = {
                "race_analysis": {
                    "race_number": 1,
                    "meeting_intelligence": {"venue": "Randwick"},
                },
                "horses": {
                    str(number): {
                        "horse_name": name,
                        "_data": {"facts_section": f"[{number}] {name} (1)\n"},
                    }
                    for number, name in enumerate(
                        ("Horse One", "Horse Two", "Horse Three"), 1
                    )
                },
            }
            path.write_text(json.dumps(logic), encoding="utf-8")
            quality = {
                ("2026-08-01", "randwick", 1, f"horse{name}"): {
                    "raw": raw,
                    "run_count": 2,
                    "runs": [{"date": "2026-07-01"}],
                }
                for name, raw in (("one", -1.0), ("two", 0.0), ("three", 1.0))
            }

            dry = backfill_archive(root, quality, apply=False)
            self.assertEqual(dry["counts"]["runners_recovered"], 3)
            self.assertNotIn(
                "sportsbet_performance_quality_score",
                json.loads(path.read_text())["horses"]["1"]["_data"],
            )

            applied = backfill_archive(root, quality, apply=True)
            self.assertEqual(applied["counts"]["files_changed"], 1)
            updated = json.loads(path.read_text())
            scores = [
                updated["horses"][str(number)]["_data"][
                    "sportsbet_performance_quality_score"
                ]
                for number in range(1, 4)
            ]
            self.assertLess(scores[0], scores[1])
            self.assertLess(scores[1], scores[2])

            again = backfill_archive(root, quality, apply=True)
            self.assertEqual(again["counts"].get("files_changed", 0), 0)
            self.assertEqual(again["counts"]["already_current"], 3)

            rolled_back = backfill_archive(
                root, quality, apply=True, rollback=True
            )
            self.assertEqual(rolled_back["counts"]["runners_rolled_back"], 3)
            restored = json.loads(path.read_text())
            self.assertNotIn(
                "sportsbet_performance_quality_score",
                restored["horses"]["1"]["_data"],
            )


if __name__ == "__main__":
    unittest.main()
