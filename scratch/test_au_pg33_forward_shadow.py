"""Guards of the pg33 forward shadow (EXP-20261016-11): freeze once, look once, frozen code only."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import au_pg33_forward_shadow_20261016 as fw  # noqa: E402


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(fw, "FREEZE", tmp_path / "freeze.json")
    monkeypatch.setattr(fw, "RESULT", tmp_path / "forward_result.json")
    monkeypatch.setattr(fw, "EXP_DIR", tmp_path)
    return tmp_path


def test_freeze_is_never_rewritten(sandbox):
    fw.cmd_freeze(SimpleNamespace())
    with pytest.raises(SystemExit, match="never rewritten"):
        fw.cmd_freeze(SimpleNamespace())


def test_code_drift_blocks_evaluation(sandbox):
    fw.cmd_freeze(SimpleNamespace())
    frozen = json.loads(fw.FREEZE.read_text())
    key = next(iter(frozen["code_sha256"]))
    frozen["code_sha256"][key] = "0" * 64
    fw.FREEZE.write_text(json.dumps(frozen))
    with pytest.raises(SystemExit, match="differs from the frozen design"):
        fw.cmd_evaluate(SimpleNamespace(dry_run_counts=False))


def test_second_look_is_refused(sandbox):
    fw.cmd_freeze(SimpleNamespace())
    fw.RESULT.write_text("{}")
    with pytest.raises(SystemExit, match="opened once"):
        fw.cmd_evaluate(SimpleNamespace(dry_run_counts=False))


def test_too_few_days_is_refused(sandbox, monkeypatch):
    fw.cmd_freeze(SimpleNamespace())
    race = {"date": "2026-10-20", "meeting": "m", "race": 1, "rows": []}
    monkeypatch.setattr(fw, "collect", lambda _root: ([race], {}))
    monkeypatch.setattr(fw, "data_root", lambda: Path("."))
    with pytest.raises(SystemExit, match="need 41"):
        fw.cmd_evaluate(SimpleNamespace(dry_run_counts=False))
    assert not fw.RESULT.exists()


def test_replay_check_refuses_forward_dates():
    with pytest.raises(SystemExit, match="before the forward window"):
        fw.cmd_replay_check(SimpleNamespace(date=fw.VALID_FROM))


def run(finish, starters, prize):
    return {"finish_pos": finish, "starters": starters, "prize": prize}


def test_placing_gate_only_withholds_positive_class_credit():
    from au_racing_engine import engine_core as ec
    rich, poor = 10 ** (ec.FORM_QUALITY_MU_LOG_PRIZE + 1), 10 ** (ec.FORM_QUALITY_MU_LOG_PRIZE - 1)
    # 前列 → 同 eq2 一樣；後列高班 → 冇獎金加分；後列低班 → 照扣
    assert fw.pg33_raw([run(1, 10, rich)] * 2) == fw.pg33_raw([run(1, 10, rich)] * 2, gate=1.0)
    assert fw.pg33_raw([run(9, 10, rich)] * 2) < fw.pg33_raw([run(9, 10, rich)] * 2, gate=1.0)
    assert fw.pg33_raw([run(9, 10, poor)] * 2) == fw.pg33_raw([run(9, 10, poor)] * 2, gate=1.0)
    assert fw.pg33_raw([run(9, 10, rich)]) is None  # 最少兩場


def test_a_a_forward_arms_are_not_eligible():
    rows = [{"n": i, "pos": i, "sp": 5.0, "features": {}, "ability": float(10 - i)} for i in range(1, 9)]
    races = [{"date": f"2026-10-{17 + d % 10:02d}", "meeting": "m", "race": d, "rows": rows}
             for d in range(60)]
    assert fw.judge(races, races)["ship_eligible"] is False
