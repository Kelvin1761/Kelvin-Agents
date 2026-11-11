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


def test_rail_ledger_needs_both_venues(tmp_path):
    test = _test("rail_bias")
    get = lambda: tracker.progress(test, root=tmp_path, ledger={}, state={})
    assert get()["status"] == "unknown"  # ledger 未有
    rows = [{"meeting": f"2026-{i:03d}_ShaTin", "venue": "沙田", "race": r} for i in range(60) for r in (1, 2)]
    rows += [{"meeting": f"2026-{i:03d}_HappyValley", "venue": "跑馬地", "race": 1} for i in range(59)]
    path = tmp_path / tracker.RAIL_LEDGER_NAME
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    item = get()
    assert (item["count"], item["status"]) == (59, "collecting")  # 逐場行唔係逐日；跑馬地差一日
    assert "沙田 60" in item["note"] and "跑馬地 59" in item["note"]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"meeting": "2026-999_HappyValley", "venue": "跑馬地", "race": 1}) + "\n")
    assert get()["status"] == "ready"


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
    # 10-11 起只得 l400_standardised 未判（gear_removed、weight_rating_gap 已 decided）
    assert len(calls) == 3 and "--arm" in calls[1] and "fixed_rule" in calls[2]
    assert lines and "L400" in lines[0] and "建議上線" in lines[0]
    assert state[tracker.STATE_KEY]["judged"]["l400_standardised"]["passed"] is True
    again = tracker.judge_ready(state, root=tmp_path, run_cmd=run, harness=Path("h.py"), python="py",
                                out_dir=tmp_path / "fc", stamp=lambda: "now")
    assert again == [] and len(calls) == 3
    item = tracker.progress(_test("l400_standardised"), root=tmp_path, ledger={}, state=state)
    assert item["status"] == "decided"


def test_harness_ab_negative_delta_keeps_current_model(tmp_path):
    for i in range(6):
        _meeting(tmp_path, f"2026-10-{12 + i:02d}_ShaTin", 11)
    run, _ = _fake_run((0.01, -0.005, 0.002))
    state: dict = {}
    lines = tracker.judge_ready(state, root=tmp_path, run_cmd=run, harness=Path("h.py"), python="py",
                                out_dir=tmp_path / "fc", stamp=lambda: "now")
    assert "維持現狀" in lines[0]
    assert state[tracker.STATE_KEY]["judged"]["l400_standardised"]["passed"] is False


def test_decided_harness_ab_is_never_auto_judged(tmp_path):
    """人手判完（weight_rating_gap 已上線、gear_removed 已剷）就唔准再自動判 —— 否則會對住已改嘅 live 發誤導通知。"""
    for i in range(6):
        _meeting(tmp_path, f"2026-11-{1 + i:02d}_ShaTin", 11)
    run, calls = _fake_run((0.01, 0.0, 0.001))
    state: dict = {}
    tracker.judge_ready(state, root=tmp_path, run_cmd=run, harness=Path("h.py"), python="py",
                        out_dir=tmp_path / "fc", stamp=lambda: "now")
    judged = state[tracker.STATE_KEY]["judged"]
    assert "weight_rating_gap" not in judged and "gear_removed" not in judged
    assert not any("hkjc_arm_weight_rating_gap.py" in " ".join(map(str, c)) for c in calls)


def test_post_live_revert_says_old_version_did_not_lose(tmp_path):
    """EXP-20261111-10：Δ = 舊版 − live，全部 ≥ 0 要講「舊版唔輸」，唔係「建議上線」或「建議剷走」。"""
    for i in range(6):
        _meeting(tmp_path, f"2026-11-{12 + i:02d}_ShaTin", 11)
    run, calls = _fake_run((0.0, 0.0, 0.0))
    state: dict = {}
    lines = tracker.judge_ready(state, root=tmp_path, run_cmd=run, harness=Path("h.py"), python="py",
                                out_dir=tmp_path / "fc", stamp=lambda: "now")
    post = [line for line in lines if "上線後" in line]
    assert post and "舊版唔輸" in post[0] and "剷走" not in post[0]
    assert any("hkjc_arm_revert_rating_gap.py" in " ".join(map(str, c)) for c in calls)


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


def test_live_nights_count_only_complete_race_nights(tmp_path):
    live = tmp_path / "HKJC_Race_Results_Database" / "_live"
    live.mkdir(parents=True)
    (live / "2026-11-01.state.json").write_text(json.dumps({"1": {"captured_at": "x"}}))          # before since
    (live / "2026-11-04.state.json").write_text(json.dumps({"1": {"captured_at": "x"}, "2": {"captured_at": "y"}}))
    (live / "2026-11-08.state.json").write_text(json.dumps({"1": {"captured_at": "x"}, "2": {"gave_up": "y"}}))
    (live / "2026-11-11.state.json").write_text(json.dumps({"1": {"captured_at": "x"}, "2": {"attempts": 3}}))  # still running
    assert tracker._live_nights(tmp_path, "2026-11-04") == (1, 1)
    item = tracker.progress(_test("live_track_bias"), root=tmp_path, ledger={}, state={})
    assert item["count"] == 1 and item["status"] == "collecting" and "1 晚唔完整" in item["note"]


def _speedpro(root: Path, folder: str, stamp: str, races: int) -> None:
    snap = root / "_speedpro_snapshots" / folder / stamp
    snap.mkdir(parents=True)
    for i in range(1, races + 1):
        (snap / f"sg_race_{i}.json").write_text("{}", encoding="utf-8")


def test_speedpro_counts_only_races_with_a_pre_race_snapshot(tmp_path):
    test = _test("speedpro_energy_diff")
    get = lambda: tracker.progress(test, root=tmp_path, ledger={}, state={})
    _meeting(tmp_path, "2026-11-08_ShaTin", 11)                    # 登記日之前：唔數
    _speedpro(tmp_path, "2026-11-08_ST", "20261107T050004Z", 11)
    _meeting(tmp_path, "2026-11-11_HappyValley", 9)                # 賽日朝早抓：賽前
    _speedpro(tmp_path, "2026-11-11_HV", "20261111T014500Z", 8)    # 第 9 場冇檔
    _meeting(tmp_path, "2026-11-15_ShaTin", 10)                    # 只有開跑後抓嘅：唔算
    _speedpro(tmp_path, "2026-11-15_ST", "20261115T060000Z", 10)
    assert tracker._speedpro_race_count(tmp_path, test.since) == (8, 11)
    item = get()
    assert (item["count"], item["status"]) == (8, "collecting")
    assert "11 場" in item["note"]
    assert tracker.speedpro_pre_race_snapshot(tmp_path, "2026-11-15_ShaTin") is None


def test_speedpro_collector_gone_quiet_is_reported(tmp_path):
    for day in ("2026-11-11_HappyValley", "2026-11-15_ShaTin", "2026-11-18_HappyValley"):
        _meeting(tmp_path, day, 9)
    item = tracker.progress(_test("speedpro_energy_diff"), root=tmp_path, ledger={}, state={})
    assert item["status"] == "stalled" and "收集器" in item["note"]


def _results(root: Path, name: str, races: dict) -> None:
    """races: {race_no: [(horse_no, brand, jockey, pos), ...]}"""
    m = root / name
    m.mkdir(exist_ok=True)
    payload = {str(rn): {"race_no": rn, "results": [
        {"pos": str(pos), "horse_no": str(no), "horse_name": f"馬{no}({brand})", "jockey": jockey, "win_odds": "5"}
        for no, brand, jockey, pos in rows]} for rn, rows in races.items()}
    (m / f"{name}_全日賽果.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_purton_rival_counts_only_when_purton_rides_another_horse_in_the_same_race(tmp_path):
    import hkjc_purton_rival as pr
    _results(tmp_path, "2026-11-08_ShaTin", {1: [(1, "A001", "潘頓", 1), (2, "B002", "潘頓", 4), (3, "C003", "潘頓", 2)]})
    _results(tmp_path, "2026-11-11_HappyValley", {
        1: [(1, "A001", "田泰安", 3), (2, "X009", "潘頓", 1)],   # A001：潘頓同場揀咗 X009 → case
        2: [(1, "B002", "巴度", 2)],                             # B002：潘頓唔喺呢場 → 唔係
        3: [(1, "C003", "潘頓", 5)],                             # C003：潘頓留低 → 唔係
    })
    _results(tmp_path, "2026-11-15_ShaTin", {1: [(1, "A001", "田泰安", "WV"), (2, "Y010", "潘頓", 2)]})  # 退出唔計
    cases = pr.rival_cases(tmp_path, "2026-11-11")
    assert [(c["date"], c["horse"]) for c in cases] == [("2026-11-11", "A001")]
    assert pr.rival_cases(tmp_path, "2026-11-12") == []
    item = tracker.progress(_test("purton_rival"), root=tmp_path, ledger={}, state={})
    assert (item["count"], item["status"]) == (1, "collecting")


def test_purton_rival_never_uses_same_day_history(tmp_path):
    import hkjc_purton_rival as pr
    # 同一日上一場潘頓騎過唔算「上仗」（同一匹馬一日唔會跑兩場；呢度防住計法本身）
    _results(tmp_path, "2026-11-11_HappyValley", {1: [(1, "A001", "潘頓", 1)], 2: [(1, "A001", "田泰安", 1), (2, "Z", "潘頓", 2)]})
    assert pr.rival_cases(tmp_path, "") == []
