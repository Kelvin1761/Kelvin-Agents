import importlib.util
from pathlib import Path

scripts = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("batch_extract_guard", scripts / "batch_extract.py")
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


def test_trial_update_never_runs_under_pytest(monkeypatch):
    calls = []
    monkeypatch.setattr(batch.subprocess, "run", lambda *a, **k: calls.append(a))
    assert batch.update_barrier_trials() is False
    assert calls == []


def test_trial_update_runs_outside_tests(monkeypatch):
    calls = []
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("WC_SKIP_TRIAL_UPDATE", raising=False)
    monkeypatch.setattr(batch.subprocess, "run", lambda *a, **k: calls.append(a))
    assert batch.update_barrier_trials() is True
    assert len(calls) == 1 and "extract_barrier_trials.py" in calls[0][0][1]
