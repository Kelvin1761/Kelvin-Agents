"""每週 review 嘅「傷患記錄 forward」行（EXP-20261020-02 B1）。

規則喺判定器；呢度只驗：用預先登記嘅日期／arm／判定器、失敗一定印出嚟、
≥ 60 場判定只判一次、CONFIRM 都唔會自動轉。harness 同判定器全部 mock。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hkjc_daily_schedule as schedule  # noqa: E402

ROW = {"meeting": "2026-10-21_HappyValley", "race": 1, "picks": [1, 2], "meeting_dead_fields": []}


def _fake_run(judge_output: str, *, fail_step=None):
    calls = []

    def run_cmd(cmd, *, timeout=7200, env_overlay=None):
        calls.append((cmd, env_overlay))
        if len(calls) == fail_step:
            return 1, "Traceback: boom"
        if "run" in cmd:
            Path(cmd[cmd.index("--out") + 1]).write_text(json.dumps(ROW) + "\n", encoding="utf-8")
            return 0, "wrote rows"
        return 0, judge_output

    return run_cmd, calls


WAIT = "races=9  Gold Δ=+0.00pp  Good Δ=+0.00pp  NDCG Δ=+0.0001  排序改變=2場\n判定: WAIT（未夠 60 場）"


def test_wait_uses_pre_registered_invocation_and_is_not_frozen(tmp_path, monkeypatch):
    fake, calls = _fake_run(WAIT)
    monkeypatch.setattr(schedule, "run_cmd", fake)
    state: dict = {}
    text = schedule.official_injury_forward_section(state, out_dir=tmp_path)
    assert "傷患記錄 forward" in text and "9 場" in text and "WAIT" in text
    assert "official_injury_forward_final" not in state
    live_cmd, cand_cmd, judge_cmd = (c for c, _ in calls)
    for cmd in (live_cmd, cand_cmd):
        assert cmd[cmd.index("--since") + 1] == "2026-10-21"
    assert "--arm" not in live_cmd
    assert cand_cmd[cand_cmd.index("--arm") + 1].endswith("hkjc_arm_official_injury_issue.py")
    assert judge_cmd[1].endswith("hkjc_official_injury_forward.py")


def test_confirm_is_reported_not_applied_and_frozen(tmp_path, monkeypatch):
    fake, _ = _fake_run("races=63  Gold Δ=+0.50pp  Good Δ=+0.00pp  NDCG Δ=+0.0010  排序改變=8場\n"
                        "判定: CONFIRM（三項 ≥ 0；可以轉 issue，要你發佈；仍然唔係已證實改善）")
    monkeypatch.setattr(schedule, "run_cmd", fake)
    state: dict = {}
    text = schedule.official_injury_forward_section(state, out_dir=tmp_path)
    assert "✅" in text and "唔會自動轉" in text
    assert state["official_injury_forward_final"]["line"] in text

    def must_not_run(*_a, **_k):
        raise AssertionError("frozen verdict must not rerun")

    monkeypatch.setattr(schedule, "run_cmd", must_not_run)
    assert "已定案" in schedule.official_injury_forward_section(state, out_dir=tmp_path)


def test_stay_off_is_frozen(tmp_path, monkeypatch):
    fake, _ = _fake_run("races=61  Gold Δ=-0.50pp  Good Δ=+0.00pp  NDCG Δ=+0.0000  排序改變=7場\n"
                        "判定: STAY_OFF（有項 < 0；維持 off）")
    monkeypatch.setattr(schedule, "run_cmd", fake)
    state: dict = {}
    text = schedule.official_injury_forward_section(state, out_dir=tmp_path)
    assert "STAY_OFF" in text and "✅" not in text
    assert "official_injury_forward_final" in state


def test_failure_is_visible(tmp_path, monkeypatch):
    fake, calls = _fake_run("unused", fail_step=2)
    monkeypatch.setattr(schedule, "run_cmd", fake)
    text = schedule.official_injury_forward_section({}, out_dir=tmp_path)
    assert "⚠️" in text and "候選 harness exit=1" in text
    assert len(calls) == 2


def test_unparseable_output_is_visible(tmp_path, monkeypatch):
    fake, _ = _fake_run("nonsense")
    monkeypatch.setattr(schedule, "run_cmd", fake)
    assert "格式" in schedule.official_injury_forward_section({}, out_dir=tmp_path)
