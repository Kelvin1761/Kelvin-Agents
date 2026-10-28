"""Forward 測試追蹤表：夠數提一次、冇累積要報、預先登記 A/B 只判一次、永遠唔改模型。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hkjc_forward_tracker as tracker  # noqa: E402


def _meeting(root: Path, name: str, races: int, awt: set[int] = frozenset(), trackwork: bool = False) -> None:
    m = root / name
    m.mkdir()
    payload = {str(i): {"results": [{"pos": "1"}]} for i in range(1, races + 1)}
    (m / f"{name}_全日賽果.json").write_text(json.dumps(payload), encoding="utf-8")
    for i in range(1, races + 1):
        surface = "全天候跑道" if i in awt else "草地"
        (m / f"{name[5:10]} Race {i} 排位表.md").write_text(f"場地: {surface}\n", encoding="utf-8")
    if trackwork:
        (m / f"{name[:10]} Race 1 晨操.json").write_text("{}", encoding="utf-8")


def _ledger(path: Path, summary: dict, rows: list[dict]) -> Path:
    path.write_text(json.dumps({"summary": summary, "rows": rows}), encoding="utf-8")
    return path


def _test(key):
    return next(t for t in tracker.FORWARD_TESTS if t.key == key)


def test_shadow_profile_ready_collecting_and_stalled(tmp_path):
    ledger = tracker._ledger_summary(_ledger(tmp_path / "l.json", {
        "race_shape_legacy_unbounded": {"active_races": 81, "races": 90},
        "weight_refit_t02": {"active_races": 59, "races": 60},
        "trainer_recency_st_early90": {"active_races": 0, "races": 0},
        "race_shape_st_draw70": {"active_races": 0, "races": 30},
    }, [{"profile": "weight_refit_t02"}] * 25))
    get = lambda key: tracker.progress(_test(key), root=tmp_path, ledger=ledger, state={})
    assert get("race_shape_legacy_unbounded")["status"] == "ready"
    assert get("weight_refit_t02")["status"] == "collecting"
    assert get("trainer_recency_st_early90")["status"] == "stalled"  # 一場記錄都冇
    assert get("race_shape_st_draw70")["status"] == "stalled"        # 有記錄但 0 active
    # 人手判咗嘅 rollback 對照只顯示結論，唔再提醒
    assert get("race_shape_v2_legacy_hv")["status"] == "decided"
    assert get("pre_race_draw_context_v1_generic")["status"] == "decided"


def test_race_awt_and_trackwork_counts_respect_since(tmp_path):
    _meeting(tmp_path, "2026-10-07_HappyValley", 9, trackwork=True)
    _meeting(tmp_path, "2026-10-11_ShaTin", 10, trackwork=True)
    _meeting(tmp_path, "2026-10-28_ShaTin", 9, awt=set(range(1, 10)))
    assert tracker._race_count(tmp_path, "2026-10-11") == 19
    assert tracker._awt_race_count(tmp_path, "2026-10-28") == 9
    assert tracker._awt_race_count(tmp_path, "2026-10-29") == 0
    assert tracker._trackwork_meetings(tmp_path) == 2


def test_remind_sends_once_per_status(tmp_path):
    ledger_path = _ledger(tmp_path / "l.json", {"race_shape_st_draw70": {"active_races": 81}}, [])
    sent: list[str] = []
    state: dict = {}
    tracker.remind(state, root=tmp_path, ledger_path=ledger_path, notify=lambda m: sent.append(m) or True)
    assert len(sent) == 1 and "夠數" in sent[0] and "EXP-20260929-02" in sent[0]
    tracker.remind(state, root=tmp_path, ledger_path=ledger_path, notify=lambda m: sent.append(m) or True)
    assert len(sent) == 1


def test_failed_telegram_is_retried_next_time(tmp_path):
    ledger_path = _ledger(tmp_path / "l.json", {"race_shape_st_draw70": {"active_races": 81}}, [])
    state: dict = {}
    tracker.remind(state, root=tmp_path, ledger_path=ledger_path, notify=lambda m: False)
    assert "race_shape_st_draw70" not in state[tracker.STATE_KEY]["notified"]


def _fake_run(deltas):
    calls = []

    def run(cmd, *, timeout=0, env_overlay=None):
        calls.append(cmd)
        if "compare" in cmd:
            out = Path(cmd[cmd.index("--out") + 1])
            out.write_text(json.dumps({"races": 61, "verdict": {"detail": {
                "primary": {"gold": {"delta": deltas[0]}, "good_positional": {"delta": deltas[1]}},
                "ranking": {"ndcg_at5": {"delta": deltas[2]}}}}}), encoding="utf-8")
        return 0, "ok"
    return run, calls


def test_harness_ab_is_judged_once_and_frozen(tmp_path):
    for name in ("2026-10-11_ShaTin", "2026-10-14_HappyValley", "2026-10-19_ShaTin",
                 "2026-10-21_HappyValley", "2026-10-25_ShaTin", "2026-10-28_ShaTin"):
        _meeting(tmp_path, name, 11)
    run, calls = _fake_run((0.0, 0.01, 0.002))
    state: dict = {}
    lines = tracker.judge_ready(state, root=tmp_path, run_cmd=run, harness=Path("h.py"), python="py",
                                out_dir=tmp_path / "fc", stamp=lambda: "now")
    assert len(calls) == 3 and "--arm" in calls[1] and "fixed_rule" in calls[2]
    assert lines and "建議剷走" in lines[0]
    assert state[tracker.STATE_KEY]["judged"]["gear_removed"]["passed"] is True
    again = tracker.judge_ready(state, root=tmp_path, run_cmd=run, harness=Path("h.py"), python="py",
                                out_dir=tmp_path / "fc", stamp=lambda: "now")
    assert again == [] and len(calls) == 3
    item = tracker.progress(_test("gear_removed"), root=tmp_path, ledger={}, state=state)
    assert item["status"] == "decided"


def test_harness_ab_negative_delta_keeps_current_model(tmp_path):
    for i in range(6):
        _meeting(tmp_path, f"2026-10-{12 + i:02d}_ShaTin", 11)
    run, _ = _fake_run((0.01, -0.005, 0.002))
    state: dict = {}
    lines = tracker.judge_ready(state, root=tmp_path, run_cmd=run, harness=Path("h.py"), python="py",
                                out_dir=tmp_path / "fc", stamp=lambda: "now")
    assert "維持現狀" in lines[0]
    assert state[tracker.STATE_KEY]["judged"]["gear_removed"]["passed"] is False


def test_not_enough_races_runs_nothing(tmp_path):
    _meeting(tmp_path, "2026-10-11_ShaTin", 10)
    run, calls = _fake_run((0, 0, 0))
    assert tracker.judge_ready({}, root=tmp_path, run_cmd=run, harness=Path("h.py"), python="py",
                               out_dir=tmp_path / "fc", stamp=lambda: "now") == []
    assert calls == []


def test_section_lists_every_test_and_frozen_state_judges(tmp_path):
    state = {"first_section_forward_final": {"line": "🏇 前速 forward：150 場｜判定 REVERT"}}
    text = tracker.section(state, root=tmp_path, ledger_path=None)
    assert text.count("\n") >= len(tracker.FORWARD_TESTS)
    assert "✅ 頭段速度（已退回）" in text and "REVERT" in text
