"""Synthetic ledger only: every write goes to a pytest tmp_path."""
from __future__ import annotations

import sys
from pathlib import Path

AUTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO))
import nba_market_ledger as ledger  # noqa: E402
import nba_reliability as rel  # noqa: E402

DAY = "2026-10-22"


def _legs(root, count, p, hits, market="pts"):
    rows = []
    for i in range(count):
        key = {"game_tag": "AAA_BBB", "player": f"P{market}{p}{i}", "market": market, "line": 10.0, "side": "over"}
        rows.append({"row_type": "model_obs", "target_date": DAY, "snapshot_id": "s1", "snapshot_role": "production",
                     "snapshot_created_at": "2026-10-22T10:00:00+11:00", "season_phase": "EARLY_REGULAR",
                     "post_tip": False, "late_write": False, "tip_unknown": False,
                     "p_final": p, "picked": False, **key})
        rows.append({"row_type": "settlement", "target_date": DAY, "outcome": "hit" if i < hits else "miss",
                     "y": 1 if i < hits else 0, **key})
    ledger.append_rows(root, DAY, rows)


def test_insufficient_sample_is_not_ok(tmp_path):
    _legs(tmp_path, 40, 0.6, 24)
    report = rel.build(DAY, tmp_path, epoch="2026-10-01")
    assert report["status"] == "insufficient_n"
    assert "樣本未夠" in "\n".join(rel.message_lines(report))


def test_calibrated_window_is_ok(tmp_path):
    _legs(tmp_path, 100, 0.6, 60)
    report = rel.build(DAY, tmp_path, epoch="2026-10-01")
    assert report["status"] == "ok" and abs(report["overall"]["gap"]) < 0.01


def test_overconfident_high_band_raises_alert(tmp_path):
    _legs(tmp_path, 60, 0.9, 36)      # says 90%, 60% happens
    _legs(tmp_path, 60, 0.4, 24)      # calibrated low band: overall gap is small, high band is not
    report = rel.build(DAY, tmp_path, epoch="2026-10-01")
    assert report["high_band"]["n"] == 60 and report["high_band"]["gap"] > 0.25
    assert report["status"] == "alert"
    assert "校準警報" in "\n".join(rel.message_lines(report))


def test_stat_labels_and_write(tmp_path):
    _legs(tmp_path, 100, 0.5, 50, market="fg3m")
    report = rel.build(DAY, tmp_path, epoch="2026-10-01")
    assert "3PM" in report["by_stat"]
    path = rel.write(report, tmp_path)
    assert path.name == "reliability_latest.json" and (tmp_path / "reports" / f"reliability_{DAY}.json").exists()


def test_rows_before_epoch_do_not_drive_the_alert(tmp_path):
    _legs(tmp_path, 120, 0.9, 60)   # legacy-engine style overconfidence on DAY
    report = rel.build(DAY, tmp_path, epoch="2026-10-23")   # epoch is after DAY
    assert report["status"] == "insufficient_n" and report["overall"]["n"] == 0
    assert report["all_engines_context"]["overall"]["n"] == 120
