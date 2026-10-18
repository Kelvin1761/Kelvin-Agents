"""Guards of the post-bundle forward check (EXP-20261018-10): freeze once, look once, frozen code only."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import au_post_bundle_forward_20261018 as fw  # noqa: E402


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(fw, "EXP_DIR", tmp_path)
    monkeypatch.setattr(fw, "FREEZE", tmp_path / "freeze.json")
    monkeypatch.setattr(fw, "RESULT", tmp_path / "forward_result.json")
    freeze = {"a0_sha": "a", "a1_sha": "b", "valid_from": fw.VALID_FROM, "min_meeting_days": 41,
              "code_sha256": fw.code_hashes()}
    return tmp_path, freeze


def write(path, data):
    path.write_text(json.dumps(data))


def test_freeze_is_never_rewritten(sandbox):
    tmp, freeze = sandbox
    write(fw.FREEZE, freeze)
    with pytest.raises(SystemExit, match="never rewritten"):
        fw.cmd_freeze(SimpleNamespace(allow_non_main=True))


def test_code_drift_blocks_evaluation(sandbox):
    tmp, freeze = sandbox
    key = next(iter(freeze["code_sha256"]))
    freeze["code_sha256"][key] = "0" * 64
    write(fw.FREEZE, freeze)
    with pytest.raises(SystemExit, match="differs from the frozen design"):
        fw.cmd_evaluate(SimpleNamespace())


def test_second_look_is_refused(sandbox):
    tmp, freeze = sandbox
    write(fw.FREEZE, freeze)
    fw.RESULT.write_text("{}")
    with pytest.raises(SystemExit, match="opened once"):
        fw.cmd_evaluate(SimpleNamespace())


def test_too_few_days_is_refused(sandbox, monkeypatch):
    tmp, freeze = sandbox
    write(fw.FREEZE, freeze)
    rows = [{"n": i, "name": f"h{i}", "pos": i, "features": {}, "ability": 10.0 - i} for i in range(1, 9)]
    race = {"date": "2026-10-20", "meeting": "m", "race": 1, "rows": rows}
    monkeypatch.setattr(fw, "meetings_between", lambda *a, **k: [])
    monkeypatch.setattr(fw, "run_arms", lambda freeze, meetings: ([race], [race], {}))
    with pytest.raises(SystemExit, match="need 41"):
        fw.cmd_evaluate(SimpleNamespace())
    assert not fw.RESULT.exists()


def test_replay_check_refuses_forward_dates():
    with pytest.raises(SystemExit, match="before the forward window"):
        fw.cmd_replay_check(SimpleNamespace(date=fw.VALID_FROM))
