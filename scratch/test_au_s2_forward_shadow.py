"""Guards of the S2 forward shadow (EXP-20261016-03): freeze once, look once, frozen code only."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import au_s2_forward_shadow_20261016 as fw  # noqa: E402


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(fw, "FREEZE", tmp_path / "freeze.json")
    monkeypatch.setattr(fw, "RESULT", tmp_path / "forward_result.json")
    monkeypatch.setattr(fw, "EXP_DIR", tmp_path)
    pooled = tmp_path / "pooled.json"
    w = {"stability": 0.3, "pace_perf": 0.1, "jockey_trainer": 0.6, "class_weight": 0.4,
         "track": 0.1, "preparation": 0.3}
    pooled.write_text(json.dumps({"prod_f6a": {"weights": w, "meta": {}}, "arm_S2": {"weights": w, "meta": {}},
                                  "procedure_hash": "x"}))
    return tmp_path, pooled


def test_freeze_is_never_rewritten(sandbox):
    _tmp, pooled = sandbox
    fw.cmd_freeze(SimpleNamespace(pooled=str(pooled)))
    with pytest.raises(SystemExit, match="never rewritten"):
        fw.cmd_freeze(SimpleNamespace(pooled=str(pooled)))


def test_code_drift_blocks_evaluation(sandbox):
    tmp, pooled = sandbox
    fw.cmd_freeze(SimpleNamespace(pooled=str(pooled)))
    frozen = json.loads(fw.FREEZE.read_text())
    key = next(iter(frozen["code_sha256"]))
    frozen["code_sha256"][key] = "0" * 64
    fw.FREEZE.write_text(json.dumps(frozen))
    with pytest.raises(SystemExit, match="differs from the frozen design"):
        fw.cmd_evaluate(SimpleNamespace(dry_run_counts=False))


def test_second_look_is_refused(sandbox):
    _tmp, pooled = sandbox
    fw.cmd_freeze(SimpleNamespace(pooled=str(pooled)))
    fw.RESULT.write_text("{}")
    with pytest.raises(SystemExit, match="opened once"):
        fw.cmd_evaluate(SimpleNamespace(dry_run_counts=False))


def test_too_few_days_is_refused(sandbox, monkeypatch):
    _tmp, pooled = sandbox
    fw.cmd_freeze(SimpleNamespace(pooled=str(pooled)))
    race = {"date": "2026-10-20", "meeting": "m", "race": 1, "rows": []}
    monkeypatch.setattr(fw, "collect", lambda _root: ([race], [race], {}))
    monkeypatch.setattr(fw, "data_root", lambda: Path("."))
    with pytest.raises(SystemExit, match="need 41"):
        fw.cmd_evaluate(SimpleNamespace(dry_run_counts=False))
    assert not fw.RESULT.exists()


def test_a_a_forward_arms_are_not_eligible():
    rows = [{"n": i, "pos": i, "features": {}, "ability": float(10 - i)} for i in range(1, 9)]
    races = [{"date": f"2026-10-{17 + d % 10:02d}", "meeting": "m", "race": d, "rows": rows}
             for d in range(60)]
    verdict = fw.judge({"A0": races, "B0": races, "B1": races})
    assert verdict["ship_eligible"] is False
