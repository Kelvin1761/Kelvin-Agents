"""Cross-process deadlines cannot use process-relative macOS Python 3.9 clocks."""

from __future__ import annotations

import importlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi import research_resources as resources
from shared_wong_choi.research_evaluation import EvaluationError


def test_deadline_clock_is_shared_across_fresh_interpreters():
    before = resources._deadline_now()
    child = float(
        subprocess.check_output(
            [
                sys.executable,
                "-c",
                "from shared_wong_choi.research_resources import _deadline_now; print(_deadline_now())",
            ],
            env={**os.environ, "PYTHONPATH": str(Path(resources.__file__).resolve().parent.parent)},
            text=True,
        )
    )
    assert before <= child <= resources._deadline_now()


def test_deadline_clock_does_not_fall_back_to_process_relative_time(monkeypatch):
    monkeypatch.setattr(resources.time, "clock_gettime", lambda _: (_ for _ in ()).throw(OSError("unavailable")))
    with pytest.raises(resources.ResourceInterrupted, match="deadline_clock_unavailable"):
        resources._deadline_now()


@pytest.mark.parametrize(
    "clock,deadline",
    [(None, 1), ("process-relative", 1), ("posix-clock-monotonic/v1", math.inf), ("posix-clock-monotonic/v1", True)],
)
@pytest.mark.parametrize(
    "module_name,schema",
    [
        ("research_resources", "wong-choi-research-postflight-request/v1"),
        ("research_supervision", "wong-choi-supervised-research-phase/v1"),
    ],
)
def test_workers_reject_unknown_or_invalid_deadline_before_source_io(tmp_path, module_name, schema, clock, deadline):
    module = importlib.import_module("shared_wong_choi." + module_name)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps({"schema_version": schema, "action": "tennis-source", "deadline_clock": clock, "deadline": deadline})
    )
    with pytest.raises((ValueError, EvaluationError)):
        module._worker_body(request)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["request.json"]


@pytest.mark.parametrize(
    "module_name,schema",
    [
        ("research_resources", "wong-choi-research-postflight-request/v1"),
        ("research_supervision", "wong-choi-supervised-research-phase/v1"),
    ],
)
def test_worker_expiry_ignores_reset_process_clock(tmp_path, monkeypatch, module_name, schema):
    module = importlib.import_module("shared_wong_choi." + module_name)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": schema,
                "action": "tennis-source",
                "deadline_clock": "posix-clock-monotonic/v1",
                "deadline": 1,
                "parent_pid": os.getppid(),
                "registry": str(tmp_path / "registry"),
                "state_root": str(tmp_path / "state"),
                "warm_root": str(tmp_path / "warm"),
                "production_locks": [str(tmp_path / "production.lock")],
                "reserve_bytes": 0,
            }
        )
    )
    monkeypatch.setattr(resources.time, "clock_gettime", lambda _: 2)
    monkeypatch.setattr(resources.time, "monotonic", lambda: 0)
    with pytest.raises(resources.ResourceInterrupted, match="timeout"):
        module._worker_body(request)
    assert not (tmp_path / "work").exists()
