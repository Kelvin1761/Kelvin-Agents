"""Synthetic ledger only: every write goes to a pytest tmp_path."""
from __future__ import annotations

import sys
import json
import pytest
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
        rows[-1]["probability_model_id"] = rel.current_model_id()
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


def _change_models(root, identity):
    path = ledger.ledger_path(root, DAY)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        if row["row_type"] == "model_obs":
            row["probability_model_id"] = identity
            row["engine"] = "calibrated(hybrid)"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_same_day_old_coefficients_never_trigger_current_model_alert(tmp_path):
    _legs(tmp_path, 120, 0.9, 60)
    _change_models(tmp_path, "calibrated:old:fixture")
    report = rel.build(DAY, tmp_path, epoch="2026-10-01")
    assert report["status"] == "insufficient_n"
    assert report["overall"]["n"] == 0
    assert report["excluded_model_legs"] == 120
    assert report["all_engines_context"]["overall"]["n"] == 120


def test_unversioned_calibrated_engine_is_not_assumed_current(tmp_path):
    _legs(tmp_path, 120, 0.9, 60)
    _change_models(tmp_path, None)
    report = rel.build(DAY, tmp_path, epoch="2026-10-01")
    assert report["overall"]["n"] == 0
    assert report["models_seen"] == {"calibrated:unversioned": 120}


def test_choose_latest_snapshot_before_filtering_model_identity(tmp_path):
    _legs(tmp_path, 100, 0.6, 60)
    rows = ledger.read_rows(tmp_path, DAY)
    changed = [{**r, "snapshot_id": "s2", "snapshot_created_at": "2026-10-22T11:00:00+11:00",
                "probability_model_id": "legacy:hybrid", "p_final": 0.9}
               for r in rows if r["row_type"] == "model_obs"]
    ledger.append_rows(tmp_path, DAY, changed)
    report = rel.build(DAY, tmp_path, epoch="2026-10-01")
    assert report["overall"]["n"] == 0  # must not resurrect s1 to manufacture a current-model sample
    assert report["excluded_model_legs"] == 100


def test_deliberately_disabled_current_layer_is_explicit(tmp_path, monkeypatch):
    _legs(tmp_path, 100, 0.6, 60)
    monkeypatch.setenv("NBA_WC_PROB_LAYER", "0")
    report = rel.build(DAY, tmp_path, epoch="2026-10-01")
    assert report["status"] == "disabled" and report["overall"]["n"] == 0
    assert "刻意關閉" in "\n".join(rel.message_lines(report))


def _picked_population(root, events=10, per_event=10):
    rows = []
    for picked, p, hits in [(True, .7, 4), (False, .3, 6)]:
        for event in range(events):
            for i in range(per_event):
                key = {'game_tag': f'A{event:02d}_B{event:02d}', 'player': f'{picked}-{i}', 'market': 'pts', 'line': 10., 'side': 'over'}
                rows.append({'row_type': 'model_obs', 'target_date': DAY, 'snapshot_id': 's1', 'snapshot_role': 'production',
                             'snapshot_created_at': '2026-10-22T10:00:00+11:00', 'post_tip': False, 'late_write': False,
                             'tip_unknown': False, 'p_final': p, 'picked': picked, 'probability_model_id': rel.current_model_id(), **key})
                rows.append({'row_type': 'settlement', 'target_date': DAY, 'outcome': 'hit' if i < hits else 'miss', 'y': int(i < hits), **key})
    ledger.append_rows(root, DAY, rows)


def test_picked_miscalibration_alerts_even_when_global_calibration_is_good(tmp_path):
    _picked_population(tmp_path)
    report = rel.build(DAY, tmp_path, epoch='2026-10-01')
    assert abs(report['overall']['gap']) < .001
    assert report['picked_status'] == 'alert' and report['status'] == 'alert'
    assert report['picked_event_clusters'] == 10 and report['picked']['n'] == 100
    assert report['picked_by_stat']['PTS']['gap'] == pytest.approx(.3)
    assert '選中腿校準警報' in '\n'.join(rel.message_lines(report))


def test_many_picked_legs_from_one_game_are_not_enough_events(tmp_path):
    _picked_population(tmp_path, events=1, per_event=100)
    report = rel.build(DAY, tmp_path, epoch='2026-10-01')
    assert report['picked']['n'] == 100
    assert report['picked_status'] == 'insufficient_n'
    assert report['picked_event_clusters'] == 1


def test_old_model_picked_rows_are_not_current_selection_evidence(tmp_path):
    _picked_population(tmp_path)
    _change_models(tmp_path, 'calibrated:old:fixture')
    report = rel.build(DAY, tmp_path, epoch='2026-10-01')
    assert report['picked']['n'] == 0 and report['picked_status'] == 'insufficient_n'
