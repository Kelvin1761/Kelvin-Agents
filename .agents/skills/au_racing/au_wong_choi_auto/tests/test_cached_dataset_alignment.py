from __future__ import annotations

import csv
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

from au_cached_walkforward_ml import materialize_dataset


class CachedDatasetAlignmentTests(unittest.TestCase):
    def _write_sources(self, root: Path, ability: float = 70.0) -> tuple[Path, Path]:
        archive = root / "archive"
        meeting = archive / "2026-01-01 Randwick Race 1-10"
        meeting.mkdir(parents=True, exist_ok=True)
        scoring = meeting / "Meeting_Auto_Scoring.csv"
        with scoring.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "race_number",
                    "race_class",
                    "horse_number",
                    "horse_name",
                    "ability_score",
                    "rank_score",
                ],
            )
            writer.writeheader()
            for number, name in enumerate(("Alpha", "Bravo", "Charlie", "Delta"), 1):
                writer.writerow(
                    {
                        "race_number": 1,
                        "race_class": "BM72",
                        "horse_number": number,
                        "horse_name": name,
                        "ability_score": ability - number,
                        "rank_score": ability - number,
                    }
                )

        results = root / "results.csv"
        with results.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "Date",
                    "Track",
                    "Race",
                    "Horse",
                    "Pos",
                    "Barrier",
                    "SP",
                    "Condition",
                ],
            )
            writer.writeheader()
            for number, name in enumerate(("Alpha", "Bravo", "Charlie", "Delta"), 1):
                writer.writerow(
                    {
                        "Date": "2026-01-01",
                        "Track": "Randwick",
                        "Race": 1,
                        "Horse": name,
                        "Pos": number,
                        "Barrier": number + 1,
                        "SP": f"{2.0 + number:.1f}",
                        "Condition": "Good 4",
                    }
                )
        return archive, results

    def test_cache_is_bound_to_sources_and_preserves_outcome_only_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, results = self._write_sources(root)
            cache = root / "cache"
            rows = materialize_dataset(
                archive_root=archive,
                historical_results_csv=results,
                cache_dir=cache,
            )
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["race_class"], "BM72")
            self.assertEqual(rows[0]["result_sp_label"], 3.0)
            self.assertEqual(rows[0]["result_barrier_label"], 2)

            # Same cache directory, changed source: rebuild=False must still
            # invalidate the cache and reflect the new source score.
            archive, results = self._write_sources(root, ability=80.0)
            refreshed = materialize_dataset(
                archive_root=archive,
                historical_results_csv=results,
                cache_dir=cache,
            )
            self.assertEqual(refreshed[0]["ability_score"], 79.0)


if __name__ == "__main__":
    unittest.main()
