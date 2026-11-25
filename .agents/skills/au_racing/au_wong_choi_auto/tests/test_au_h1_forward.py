"""EXP-20261125-11 H1 forward：參數凍結、盲測、只計 forward、只用賽前快照、接駁齊。"""
from __future__ import annotations

import ast
import json
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[1] / "scripts"
DAILY = HERE.parents[2] / "au_daily_auto"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(DAILY))

import au_h1_forward as F  # noqa: E402


# ---------------------------------------------------------------- 合成數據

def _race(day: str, k: int, rng, n: int = 8) -> dict:
    pos = rng.permutation(n) + 1
    rows = [{"n": i + 1, "name": f"H{k}-{i}", "ability": float(rng.normal(60, 3)),
             "trial_score": float(rng.choice([60.0, 70.0, 85.0])), "preparation_score": float(rng.normal(60, 4)),
             "pos": int(pos[i]), "sp": float(rng.uniform(2, 30))} for i in range(n)]
    return {"date": day, "meeting": f"{day} Track", "race": k, "rows": rows, "source": F.SOURCE_TAG}


def _races(start: str, days: int, per_day: int, seed: int = 0) -> list[dict]:
    rng = np.random.default_rng(seed)
    d0 = date.fromisoformat(start)
    return [_race((d0 + timedelta(days=i)).isoformat(), k, rng) for i in range(days) for k in range(1, per_day + 1)]


# ---------------------------------------------------------------- 1. 凍結參數

def test_frozen_file_matches_registered_sha_and_weights():
    w = F.load_frozen()
    frozen = json.loads(F.FROZEN_PATH.read_text(encoding="utf-8"))
    assert w == {k: float(v) for k, v in frozen["weights"].items()}
    assert frozen["fit"]["until"] == "2026-11-25" and frozen["fit"]["since"] == "2026-08-05"
    assert abs(w["trial_score"] - frozen["fit"]["beta_trial"] / frozen["fit"]["alpha"]) < 1e-12
    assert abs(w["preparation_score"] - frozen["fit"]["beta_prep"] / frozen["fit"]["alpha"]) < 1e-12


def test_modified_frozen_file_is_refused(tmp_path):
    copy = tmp_path / "frozen.json"
    shutil.copy(F.FROZEN_PATH, copy)
    data = json.loads(copy.read_text(encoding="utf-8"))
    data["weights"]["trial_score"] += 0.1
    copy.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(F.FrozenParamsChanged):
        F.load_frozen(copy)


def test_forward_script_never_refits():
    tree = ast.parse((SCRIPTS / "au_h1_forward.py").read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | \
        {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "_fit" not in names and "fit_frozen" not in names
    assert F.START_DATE > json.loads(F.FROZEN_PATH.read_text(encoding="utf-8"))["fit"]["until"]


def test_candidate_is_ability_plus_frozen_z_shift():
    race = {"date": "2026-12-01", "meeting": "m", "race": 1, "rows": [
        {"ability": 60.0, "trial_score": 60.0, "preparation_score": 50.0},
        {"ability": 62.0, "trial_score": 80.0, "preparation_score": 70.0}]}
    w = {"trial_score": 0.5, "preparation_score": 2.0}
    got = F.candidate([race], w)[0]["rows"]
    assert got[0]["ability"] == pytest.approx(60.0 - 0.5 - 2.0) and got[1]["ability"] == pytest.approx(62.0 + 0.5 + 2.0)
    assert race["rows"][0]["ability"] == 60.0     # 原本嗰份唔郁
    flat = {**race, "rows": [dict(x, trial_score=60.0, preparation_score=60.0) for x in race["rows"]]}
    assert [x["ability"] for x in F.candidate([flat], w)[0]["rows"]] == [60.0, 62.0]   # SD 0 → z 0


# ---------------------------------------------------------------- 2. 盲測

def test_status_is_blind_to_outcomes():
    w = F.load_frozen()
    races = _races(F.START_DATE, 12, 10)
    a = F.status(races, {}, w)
    shuffled = []
    rng = np.random.default_rng(9)
    for r in races:
        pos = rng.permutation([x["pos"] for x in r["rows"]])
        shuffled.append(dict(r, rows=[dict(x, pos=int(p)) for x, p in zip(r["rows"], pos)]))
    b = F.status(shuffled, {}, w)
    strip = lambda s: {k: v for k, v in s.items() if k != "generated_at"}  # noqa: E731
    assert strip(a) == strip(b)                         # 名次點變都唔影響 status
    assert a["outcomes_visible"] is False and a["state"] == "collecting" and "evaluation" not in a
    text = json.dumps(a)
    for word in ("dlogloss", "gold", "good", "auc", "verdict", "gap_change", "hit"):
        assert word not in text


def test_ready_needs_both_days_and_races():
    w = F.load_frozen()
    many_races_few_days = _races(F.START_DATE, F.TARGET_DAYS - 1, 40)
    assert len(many_races_few_days) >= F.TARGET_RACES
    assert not F.status(many_races_few_days, {}, w)["ready"]
    many_days_few_races = _races(F.START_DATE, F.TARGET_DAYS + 5, 20)
    assert len(many_days_few_races) < F.TARGET_RACES
    assert not F.status(many_days_few_races, {}, w)["ready"]
    enough = _races(F.START_DATE, F.TARGET_DAYS, 40)
    st = F.status(enough, {}, w)
    assert st["ready"] and st["cutoff_date"] == enough[-1]["date"] and st["outcomes_visible"] is False


def test_pre_start_races_are_not_counted():
    w = F.load_frozen()
    pre = _races("2026-10-01", 50, 40)
    st = F.status(pre, {}, w)
    assert st["races_collected"] == 0 and not st["ready"]


# ---------------------------------------------------------------- 3. 判決只計 forward

def test_evaluate_scores_only_forward_days_up_to_cutoff(monkeypatch):
    import au_logloss_ruler as L
    import market_ruler as M

    pre = _races("2026-10-15", 30, 10, seed=1)
    fwd = _races(F.START_DATE, F.TARGET_DAYS + 5, 40, seed=2)
    seen = {}

    def fake_rank(base, cand, *, nnull, version):
        seen["rank_version"] = version
        seen["scored_days"] = sorted(L.calibrations(base, "v2"))
        seen["max_date"] = max(r["date"] for r in base)
        seen["same_order"] = [(r["meeting"], r["race"]) for r in base] == [(r["meeting"], r["race"]) for r in cand]
        return {"verdict": "PASS"}

    def fake_market(base, cand, *, price_key, since, score_window):
        seen["market"] = (price_key, since, score_window)
        return {"paired": {"gap_change": {"dll_per_race": -0.001}, "verdict": "FAIL"}, "arms": {"candidate": {}}}

    monkeypatch.setattr(L, "evaluate", fake_rank)
    monkeypatch.setattr(M, "evaluate", fake_market)
    ev = F.evaluate(pre + fwd, F.load_frozen())
    cutoff = fwd[F.TARGET_DAYS * 40 - 1]["date"]
    assert ev["cutoff_date"] == cutoff and seen["max_date"] == cutoff
    assert (ev["forward_races"], ev["forward_days"]) == (F.TARGET_DAYS * 40, F.TARGET_DAYS)
    assert seen["scored_days"] and min(seen["scored_days"]) >= F.START_DATE
    assert seen["rank_version"] == "v2" and seen["same_order"]
    assert seen["market"] == ("sp", F.CALIBRATION_SINCE, (F.START_DATE, cutoff))
    assert ev["verdict"] == "PASS"
    assert L.calibrations.__name__ == "calibrations"     # monkeypatch 還原咗


def test_verdict_needs_gap_change_not_positive(monkeypatch):
    import au_logloss_ruler as L
    import market_ruler as M

    races = _races(F.START_DATE, F.TARGET_DAYS, 40)
    monkeypatch.setattr(L, "evaluate", lambda *a, **k: {"verdict": "PASS"})
    monkeypatch.setattr(M, "evaluate", lambda *a, **k: {"paired": {"gap_change": {"dll_per_race": 0.0004}}, "arms": {}})
    assert F.evaluate(races, F.load_frozen())["verdict"] == "FAIL"
    monkeypatch.setattr(L, "evaluate", lambda *a, **k: {"verdict": "REJECT"})
    monkeypatch.setattr(M, "evaluate", lambda *a, **k: {"paired": {"gap_change": {"dll_per_race": -0.01}}, "arms": {}})
    assert F.evaluate(races, F.load_frozen())["verdict"] == "FAIL"


def test_evaluate_refuses_before_target():
    with pytest.raises(ValueError):
        F.evaluate(_races(F.START_DATE, 5, 10), F.load_frozen())


# ---------------------------------------------------------------- 4. 防洩漏：只用賽前快照

class FakeCore:
    def __init__(self, snapshot, created, cutoff):
        self.snap = (snapshot, created, cutoff)

    def find_existing_results_file(self, platform, meeting_dir):
        return meeting_dir / "Race_Results_x.json"

    def select_prerace_snapshot(self, meeting_dir, platform):
        return self.snap

    def load_structured_results(self, platform, path):
        return {1: {"results": [{"horse_no": i, "placing": i, "odds": str(2.0 + i)} for i in (1, 2, 3, 4)],
                    "scratched_horse_numbers": []}}

    def load_prediction_rows(self, analysis_dir, platform):
        assert Path(analysis_dir).name.startswith("2026"), "預測一定要由快照目錄讀"
        return {1: [{"horse_no": i, "horse_name": f"H{i}", "ability_score": 60.0 + i,
                     "factor_scores": {"trial_score": 60.0, "preparation_score": 55.0 + i}} for i in (1, 2, 3, 4)]}


def _meeting(tmp_path):
    m = tmp_path / "2026-12-01 Randwick Race 1-8"
    m.mkdir()
    return m


def test_uses_prerace_snapshot_rows(tmp_path):
    m = _meeting(tmp_path)
    cut = datetime(2026, 12, 1, 0, 30, tzinfo=timezone.utc)
    races, info = F.collect_meeting(m, FakeCore(tmp_path / "20261201T090000+1100-x", cut - timedelta(hours=2), cut))
    assert info["source"] == "snapshot" and len(races) == 1
    r = races[0]
    assert r["source"] == F.SOURCE_TAG and r["snapshot"].startswith("20261201")
    assert [x["ability"] for x in r["rows"]] == [61.0, 62.0, 63.0, 64.0] and r["rows"][0]["sp"] == 3.0


def test_no_prerace_snapshot_means_no_rows(tmp_path):
    m = _meeting(tmp_path)
    races, info = F.collect_meeting(m, FakeCore(None, None, None))
    assert races == [] and info["source"] == "no_snapshot"      # 唔退返去 meeting 目錄


def test_snapshot_at_or_after_cutoff_is_rejected(tmp_path):
    m = _meeting(tmp_path)
    cut = datetime(2026, 12, 1, 0, 30, tzinfo=timezone.utc)
    races, info = F.collect_meeting(m, FakeCore(tmp_path / "20261201T120000+1100-x", cut, cut))
    assert races == [] and info["source"] == "no_snapshot"


def test_evaluate_rejects_non_snapshot_rows():
    races = _races(F.START_DATE, F.TARGET_DAYS, 40)
    races[0] = dict(races[0], source="meeting_dir")
    with pytest.raises(ValueError):
        F.evaluate(races, F.load_frozen())


# ---------------------------------------------------------------- 5. 接駁

def test_registered_in_forward_tracker():
    import au_forward_tracker as T
    hit = [t for t in T.FORWARD_TESTS if t.experiment == F.EXPERIMENT_ID]
    assert len(hit) == 1 and hit[0].kind == "status_file" and hit[0].status_file == "au-h1-forward-status.json"


def test_tracker_follows_status_ready_flag(tmp_path):
    import au_forward_tracker as T
    test = T.ForwardTest("h1", "H1", F.EXPERIMENT_ID, "status_file", 1000, "場", "判", status_file="s.json")
    (tmp_path / "s.json").write_text(json.dumps({"races_collected": 1500, "target_races": 1000, "ready": False}))
    assert not T.progress(test, work_dir=tmp_path)["ready"]          # 場數夠但賽日未夠
    (tmp_path / "s.json").write_text(json.dumps({"races_collected": 1500, "target_races": 1000, "ready": True}))
    assert T.progress(test, work_dir=tmp_path)["ready"]


def test_scheduler_step_wired_without_runlog_warn():
    src = (DAILY / "au_daily_schedule.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "step_h1_forward")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert not [c for c in calls if c.func.attr == "warn"]
    assert "step_h1_forward(runlog)" in src and 'H1_FORWARD = AU_SKILL / "au_wong_choi_auto" / "scripts" / "au_h1_forward.py"' in src
    body = ast.get_source_segment(src, fn)
    assert '"status", "evaluate"' in body and "au-h1-forward-status.json" in body
