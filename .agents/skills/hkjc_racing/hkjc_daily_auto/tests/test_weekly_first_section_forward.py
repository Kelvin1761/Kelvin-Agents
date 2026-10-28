"""每週 review 嘅「前速 forward」行（EXP-20261016-53）。

同其他尾段唔同：失敗一定要印出嚟（退回條件冇人睇 = 冇條件），REVERT 唔可以自動退，
最終判定只判一次。harness 同判定器全部 mock，唔會真係重跑。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hkjc_daily_schedule as schedule  # noqa: E402

ROW = {"meeting": "2026-10-18_ShaTin", "race": 1, "picks": [1, 2], "meeting_dead_fields": []}


def _fake_run(judge_output: str, *, live_rows=(ROW,), cf_rows=(ROW,), fail_step=None):
    calls = []

    def run_cmd(cmd, *, timeout=7200, env_overlay=None):
        calls.append((cmd, env_overlay))
        step = len(calls)
        if step == fail_step:
            return 1, "Traceback: boom"
        if "run" in cmd:
            rows = cf_rows if "--arm" in cmd else live_rows
            Path(cmd[cmd.index("--out") + 1]).write_text(
                "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            return 0, "wrote rows"
        return 0, judge_output

    return run_cmd, calls


def test_wait_line_and_pre_registered_invocation(tmp_path, monkeypatch):
    fake, calls = _fake_run("races=20  頭2換馬淨上名=+1  Good Δ=+0.50pp  Gold Δ=-5.00pp\n判定: WAIT（未夠 60 場）")
    monkeypatch.setattr(schedule, "run_cmd", fake)
    state: dict = {}
    text = schedule.first_section_forward_section(state, out_dir=tmp_path)
    assert "前速 forward" in text and "20 場" in text and "+1" in text
    assert "Gold Δ -5.00pp" in text and "WAIT" in text
    assert "first_section_forward_final" not in state
    live_cmd, cf_cmd, judge_cmd = (c for c, _ in calls)
    for cmd in (live_cmd, cf_cmd):
        assert cmd[cmd.index("--since") + 1] == "2026-10-17"
    assert "--arm" not in live_cmd
    assert cf_cmd[cf_cmd.index("--arm") + 1].endswith("hkjc_arm_with_first_section.py")
    assert judge_cmd[1].endswith("hkjc_first_section_forward.py")
    # 2026-10-27 退回後：判定器第一個檔 = 有前速（arm），第二個 = live（冇前速）
    assert judge_cmd[2] == cf_cmd[cf_cmd.index("--out") + 1]
    assert judge_cmd[3] == live_cmd[live_cmd.index("--out") + 1]
    assert all(env == {"PYTHONDONTWRITEBYTECODE": "1"} for _, env in calls)


def test_revert_is_reported_not_applied_and_frozen(tmp_path, monkeypatch):
    fake, _ = _fake_run("races=72  頭2換馬淨上名=-4  Good Δ=-1.00pp  Gold Δ=-2.00pp\n"
                        "判定: REVERT（中期止蝕：淨上名 ≤ −3）")
    monkeypatch.setattr(schedule, "run_cmd", fake)
    state: dict = {}
    text = schedule.first_section_forward_section(state, out_dir=tmp_path)
    assert "🛑" in text and "EXP-20261016-53" in text and "唔好重新上線" in text
    assert state["first_section_forward_final"]["line"] in text

    def must_not_run(*_a, **_k):
        raise AssertionError("frozen verdict must not rerun")

    monkeypatch.setattr(schedule, "run_cmd", must_not_run)
    again = schedule.first_section_forward_section(state, out_dir=tmp_path)
    assert "REVERT" in again and "已定案" in again


def test_final_verdict_at_150_is_judged_once(tmp_path, monkeypatch):
    fake, _ = _fake_run("races=158  頭2換馬淨上名=+6  Good Δ=+0.80pp  Gold Δ=-0.20pp\n"
                        "判定: KEEP（forward 同方向；仍然唔係已證實改善）")
    monkeypatch.setattr(schedule, "run_cmd", fake)
    state: dict = {}
    text = schedule.first_section_forward_section(state, out_dir=tmp_path)
    assert "KEEP" in text and "🛑" not in text and "可以考慮重新上線" in text
    assert "first_section_forward_final" in state


def test_midterm_continue_is_not_frozen(tmp_path, monkeypatch):
    fake, _ = _fake_run("races=80  頭2換馬淨上名=+2  Good Δ=+0.10pp  Gold Δ=+0.00pp\n"
                        "判定: CONTINUE（中期檢查通過，等夠 150 場）")
    monkeypatch.setattr(schedule, "run_cmd", fake)
    state: dict = {}
    assert "CONTINUE" in schedule.first_section_forward_section(state, out_dir=tmp_path)
    assert "first_section_forward_final" not in state


def test_harness_failure_is_visible(tmp_path, monkeypatch):
    fake, calls = _fake_run("unused", fail_step=2)
    monkeypatch.setattr(schedule, "run_cmd", fake)
    text = schedule.first_section_forward_section({}, out_dir=tmp_path)
    assert "⚠️" in text and "檢查失敗" in text and "前速 arm harness exit=1" in text
    assert len(calls) == 2  # judge never runs on a half-written pair


def test_unparseable_judge_output_is_visible(tmp_path, monkeypatch):
    fake, _ = _fake_run("something else entirely")
    monkeypatch.setattr(schedule, "run_cmd", fake)
    text = schedule.first_section_forward_section({}, out_dir=tmp_path)
    assert "⚠️" in text and "格式" in text


def test_dropped_rows_are_flagged(tmp_path, monkeypatch):
    bad = {"meeting": "2026-10-18_ShaTin", "race": 2, "error": "KeyError"}
    dead = {**ROW, "race": 3, "meeting_dead_fields": ["speed_score"]}
    fake, _ = _fake_run("races=1  頭2換馬淨上名=+0  Good Δ=+0.00pp  Gold Δ=+0.00pp\n判定: WAIT（未夠 60 場）",
                        live_rows=(ROW, bad, dead), cf_rows=(ROW, dead))
    monkeypatch.setattr(schedule, "run_cmd", fake)
    text = schedule.first_section_forward_section({}, out_dir=tmp_path)
    assert "score 失敗已剔除：live 1 場、前速 arm 0 場" in text
    assert "speed_score 死欄位已剔除：live 1 場、前速 arm 1 場" in text


def test_weekly_message_carries_the_line(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(schedule, "run_cmd", lambda *a, **k: (0, '{"x": 1}'))
    monkeypatch.setattr(schedule, "_review_summary", lambda _r: "ref")
    monkeypatch.setattr(schedule, "forward_meeting_count", lambda: 3)
    monkeypatch.setattr(schedule, "process_candidate_gate", lambda _p: ("none", None))
    monkeypatch.setattr(schedule, "learning_lines", lambda: [])
    monkeypatch.setattr(schedule, "field_health_section", lambda: "")
    monkeypatch.setattr(schedule, "results_db_reconcile_section", lambda: "")
    monkeypatch.setattr(schedule, "first_section_forward_section", lambda state: "\n\n🏇 前速 forward：stub")
    monkeypatch.setattr(schedule, "official_injury_forward_section", lambda state: "")
    monkeypatch.setattr(schedule, "forward_tracker_section", lambda state, path: "")
    monkeypatch.setattr(schedule, "notify", lambda message, **_k: sent.append(message) or True)
    code = schedule.run_weekly({}, tmp_path / "state.json", tmp_path / "gate.json")
    assert code == schedule.EXIT_OK
    assert sent and sent[0].endswith("🏇 前速 forward：stub")
