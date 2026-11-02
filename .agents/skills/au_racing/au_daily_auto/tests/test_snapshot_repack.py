"""Busy-day recovery must retain analysis, ranks and tracking history."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import au_daily_schedule as schedule  # noqa: E402
from Horse_Racing_Dashboard.generate_static import load_snapshot  # noqa: E402


def test_legacy_snapshot_recovers_without_dropping_any_content(tmp_path, monkeypatch):
    payload = {
        "meetings": [{"date": "2026-11-02", "venue": "Today", "region": "AU"},
                     {"date": "2026-11-03", "venue": "Future", "region": "HKJC"}],
        "races": {"2026-11-02|Today": {"races_by_analyst": {"auto": [{
            "race_number": 1, "horses": [{"horse_number": 1, "rank": 1,
                "odds": 2.5, "raw_text": "完整分析" * 10000,
                "data_readout": "全部證據", "dimension_details": [{"score": 75}]}]}]}}},
        "sports_feed": {"sports": {"tennis": {"tracking": {
            "records": [{"event": str(i), "detail": "完整歷史" * 100} for i in range(100)]}}}},
    }
    before = copy.deepcopy(payload)
    source = tmp_path / "legacy.json"
    source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(schedule, "WORK_DIR", tmp_path)
    monkeypatch.setattr(schedule, "MAX_SNAPSHOT_MIB", 0.02)
    log = Mock()
    result = schedule.shrink_to_fit(log, source, schedule.date(2026, 11, 2))
    assert result != source
    assert result.stat().st_size < 0.02 * 1048576
    assert load_snapshot(result) == before
    assert json.loads(source.read_text(encoding="utf-8")) == before
    log.error.assert_not_called()
    log.step.assert_called_once()


def test_repacking_current_transport_is_idempotent(tmp_path, monkeypatch):
    source = tmp_path / "small.json"
    source.write_text('{"meetings":[],"races":{}}', encoding="utf-8")
    monkeypatch.setattr(schedule, "WORK_DIR", tmp_path)
    assert schedule.repack_snapshot(source) == source


def test_hard_upload_limit_stops_before_validation_or_deployment(tmp_path, monkeypatch):
    source = tmp_path / "oversize.json"
    with source.open("wb") as handle:
        handle.truncate(25 * 1048576)
    monkeypatch.setattr(schedule, "build_snapshot", lambda *a, **k: (source, [], []))
    monkeypatch.setattr(schedule, "check_data_contract", lambda *a: [])
    monkeypatch.setattr(schedule, "shrink_to_fit", lambda *a: source)
    validate, deploy = Mock(), Mock()
    monkeypatch.setattr(schedule, "validate_snapshot", validate)
    monkeypatch.setattr(schedule, "deploy_dashboard", deploy)
    assert schedule.step_dashboard(Mock(), [], []) is False
    validate.assert_not_called()
    deploy.assert_not_called()
