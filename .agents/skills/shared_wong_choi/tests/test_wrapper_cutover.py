from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_four_daily_wrappers_dispatch_prediction_lifecycle_through_control_plane() -> None:
    wrappers = {
        ".agents/skills/au_racing/au_daily_auto/run_au_daily_schedule.sh": "--domain au --mode",
        ".agents/skills/hkjc_racing/hkjc_daily_auto/run_hkjc_daily_schedule.sh": "--domain hkjc --mode",
        "tennis-wong-choi/scripts/run_tennis_daily_schedule.sh": "--domain tennis --mode",
        ".agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh": "--domain nba --mode",
    }
    for path, dispatch in wrappers.items():
        text = _read(path)
        assert "shared_wong_choi/control_plane.py" in text
        assert dispatch in text


def test_hkjc_weekly_review_stays_outside_prediction_dispatch_contract() -> None:
    text = _read(
        ".agents/skills/hkjc_racing/hkjc_daily_auto/run_hkjc_daily_schedule.sh"
    )
    assert 'if [ "$MODE" = "weekly" ]' in text
    assert 'hkjc_daily_schedule.py" --mode "$MODE"' in text


def test_tennis_external_launcher_remains_backward_compatible() -> None:
    text = _read("tennis-wong-choi/scripts/run_tennis_daily_schedule.sh")
    assert 'MODE="daily"' in text
    assert '--refresh-today "*' in text
    assert 'MODE="card"' in text
