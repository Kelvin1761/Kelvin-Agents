from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
AU_RACING = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(AU_RACING))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, str(SCRIPTS.parents[2] / "shared_racing"))

from au_unhealthy_leaf_test import evaluate  # noqa: E402
from au_unused_field_power import runner_features  # noqa: E402
from sb_backfill_archive import scored_meeting_index  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402


def test_unhealthy_leaf_harness_accepts_current_runtime_rows() -> None:
    race = {
        "rows": [
            {
                "horse_name": f"Horse {index}",
                "features": {"form_score": 70.0 - index},
                "wet": 0.0,
                "pos": index,
            }
            for index in range(1, 5)
        ]
    }
    result = evaluate([race], MATRIX_WEIGHTS)
    assert result is not None
    assert result["gold"] == 100.0
    assert result["pass"] == 100.0


def test_scored_meeting_index_includes_archived_meetings(tmp_path: Path) -> None:
    direct = tmp_path / "2026-08-01 Track Race 1-1"
    archived = tmp_path / "Archive" / "2026-08-02 Track Race 1-1"
    direct.mkdir(parents=True)
    archived.mkdir(parents=True)
    (direct / "Meeting_Auto_Scoring.csv").write_text("race_number\n1\n")
    (archived / "Meeting_Auto_Scoring.csv").write_text("race_number\n1\n")

    indexed = scored_meeting_index(tmp_path)

    assert indexed[direct.name] == direct.resolve()
    assert indexed[archived.name] == archived.resolve()


def test_scored_meeting_index_refuses_duplicate_snapshots(tmp_path: Path) -> None:
    name = "2026-08-01 Track Race 1-1"
    for parent in (tmp_path, tmp_path / "Archive"):
        meeting = parent / name
        meeting.mkdir(parents=True)
        (meeting / "Meeting_Auto_Scoring.csv").write_text("race_number\n1\n")

    try:
        scored_meeting_index(tmp_path)
    except RuntimeError as exc:
        assert "duplicate scored meeting folder" in str(exc)
    else:
        raise AssertionError("duplicate meeting snapshots must not be selected silently")


def test_historical_feature_harness_blocks_mutable_overview_outcomes() -> None:
    block = "\n".join(
        [
            "[1] Example Star (3)",
            "Career: 10: 2-2-1  Last 10: 12345x  Prize: $100,000",
            "1st Up: 4: 2-1-0  2nd Up: 3: 1-1-0  3rd Up: 3: 0-1-1",
            "Days: 20  Ave $: $10,000  J/H: 1: 1-0-0",
            "WinRange: 1200m - 1400m",
            "Track R2 2026-07-01 1400m cond:Good $50000 J Doe (3) 58kg margin:1.0L starters:10",
            "1-Rival (58kg), 2-Example Star (58kg), 3-Other (57kg)",
        ]
    )

    features = runner_features(block, 1400, "Example Star", "J Doe")

    assert "ave_prize" not in features
    assert "up_place_rate" not in features
    assert "jh_pre_place_rate" not in features  # requires two pre-race run rows
