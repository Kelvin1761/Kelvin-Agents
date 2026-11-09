"""EXP-20261109-04: the NBA forward tracker and the frozen evaluation script it drives."""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import nba_forward_tracker as tracker  # noqa: E402

REPO = HERE.parents[4]
SCRIPT = REPO / "docs/experiments/patches/nba_forward_mt/evaluate.py"


def _script():
    spec = importlib.util.spec_from_file_location("nba_forward_mt_eval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeScript:
    def __init__(self, ready):
        self.ready, self.evaluated = ready, []

    def status(self, ledger, analysis):
        return {"M": {"ready": self.ready, "days": 3, "flagged_legs": 10,
                      "checkpoint": {"days": 21, "flagged_legs": 800}},
                "T": {"ready": False, "events": 1, "event_legs": 2,
                      "checkpoint": {"events": 60, "event_legs": 200}}}

    def evaluate(self, ledger, analysis, reports, only=None):
        self.evaluated.append(only)
        return {only: {"pass": False, "n_flagged": 900, "n_legs": 2000,
                       "primary_delta_resid": -0.01, "ci95": [-0.03, 0.01]}}


def test_registry_covers_both_tests():
    assert {t.test for t in tracker.FORWARD_TESTS} == {"M", "T"}
    for t in tracker.FORWARD_TESTS:
        assert (REPO / t.script).is_file()


def test_not_ready_never_evaluates_or_notifies(tmp_path):
    fake, sent = FakeScript(False), []
    tracker.check(ledger=tmp_path, analysis=tmp_path, reports=tmp_path,
                  notify=lambda k, m: sent.append(k), loader=lambda s: fake)
    assert sent == [] and fake.evaluated == []


def test_ready_evaluates_once_and_notifies(tmp_path):
    fake, sent = FakeScript(True), []
    report = tracker.check(ledger=tmp_path, analysis=tmp_path, reports=tmp_path,
                           notify=lambda k, m: sent.append((k, m)), loader=lambda s: fake)
    assert fake.evaluated == ["M"]
    assert [k for k, _ in sent] == ["forward-ready:minutes_risk"]
    assert "未過" in sent[0][1] and "上唔上線係你決定" in sent[0][1]
    assert "21" in tracker.summary_line(report)


def test_loader_failure_is_reported_not_raised(tmp_path):
    def boom(_):
        raise OSError("missing")
    report = tracker.check(ledger=tmp_path, analysis=tmp_path, reports=tmp_path,
                           notify=lambda k, m: None, loader=boom)
    assert all("error" in v for v in report.values())


def test_script_ignores_rows_before_forward_start(tmp_path):
    ev = _script()
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    row = {"row_type": "settlement", "target_date": "2026-11-08", "game_tag": "A_B",
           "player": "X Y", "market": "pts", "line": 10, "outcome": "hit", "y": 1}
    (ledger / "2026-11-08.jsonl").write_text(json.dumps(row) + "\n")
    (ledger / "2026-11-10.jsonl").write_text(json.dumps(dict(row, target_date="2026-11-09")) + "\n")
    assert ev.outcomes(ev.load(ledger)) == {}


def test_script_refuses_to_evaluate_before_checkpoint(tmp_path):
    ev = _script()
    (tmp_path / "ledger").mkdir()
    out = ev.evaluate(tmp_path / "ledger", tmp_path, tmp_path / "reports")
    assert out["M"]["status"] == "not_ready" and out["T"]["status"] == "not_ready"
    assert not (tmp_path / "reports").exists()


def test_line_pick_prefers_price_nearest_190_after_news():
    ev = _script()
    from datetime import datetime, timezone
    t0 = datetime(2026, 11, 10, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 11, 10, 3, tzinfo=timezone.utc)
    obs = [(t0, 20.0, 1.90), (t1, 20.0, 1.60), (t1, 25.0, 2.10)]
    base = ("d", "g", "p", "pts")
    y = {base + (20.0,): 1, base + (25.0,): 0}
    leg = ev.pick_line(obs, y, base, after=t1)
    assert leg == {"line": 25.0, "price": 2.10, "y": 0}
    assert ev.pick_line(obs, y, base)["price"] == 2.10  # closing prices when no news time
