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

W = F.load_frozen()


@pytest.fixture(autouse=True)
def _verdict_lock_in_tmp(tmp_path, monkeypatch):
    """判決鎖一律指去 tmp，測試唔准掂真正嘅 WongChoiControl。"""
    lock = tmp_path / "lock" / f"{F.EXPERIMENT_ID}.json"
    monkeypatch.setattr(F, "verdict_path", lambda: lock)
    return lock


# ---------------------------------------------------------------- 合成數據

def _race(day: str, k: int, rng, n: int = 8) -> dict:
    pos = rng.permutation(n) + 1
    rows = [{"n": i + 1, "name": f"H{k}-{i}", "ability": float(rng.normal(60, 3)),
             "trial_score": float(rng.choice([60.0, 70.0, 85.0])), "preparation_score": float(rng.normal(60, 4)),
             "pos": int(pos[i]), "sp": float(rng.uniform(2, 30))} for i in range(n)]
    F.score_field(rows, W)
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
    F.score_field(race["rows"], w)
    got = F.candidate([race])[0]["rows"]
    assert got[0]["ability"] == pytest.approx(60.0 - 0.5 - 2.0) and got[1]["ability"] == pytest.approx(62.0 + 0.5 + 2.0)
    assert race["rows"][0]["ability"] == 60.0     # 原本嗰份唔郁
    flat = {**race, "rows": [dict(x, trial_score=60.0, preparation_score=60.0) for x in race["rows"]]}
    F.score_field(flat["rows"], w)
    assert [x["ability"] for x in F.candidate([flat])[0]["rows"]] == [60.0, 62.0]   # SD 0 → z 0
    with pytest.raises(ValueError):                  # 冇賽前候選分唔准用
        F.candidate([{**race, "rows": [{"ability": 1.0}]}])


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

    def fake_gap(base, cand, lo, hi):
        seen["gap_window"] = (lo, hi)
        return {"dll_per_race": -0.001}
    monkeypatch.setattr(F, "windowed_gap_change", fake_gap)
    ev = F.evaluate(pre + fwd, F.load_frozen())
    assert seen["gap_window"] == (F.START_DATE, ev["cutoff_date"])
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
    monkeypatch.setattr(M, "evaluate", lambda *a, **k: {"paired": {}, "arms": {}})
    monkeypatch.setattr(L, "evaluate", lambda *a, **k: {"verdict": "PASS"})
    monkeypatch.setattr(F, "windowed_gap_change", lambda *a: {"dll_per_race": 0.0004})
    assert F.evaluate(races, F.load_frozen())["verdict"] == "FAIL"
    monkeypatch.setattr(F, "windowed_gap_change", lambda *a: {"dll_per_race": 0.0})
    assert F.evaluate(races, F.load_frozen())["verdict"] == "PASS"
    monkeypatch.setattr(L, "evaluate", lambda *a, **k: {"verdict": "REJECT"})
    monkeypatch.setattr(F, "windowed_gap_change", lambda *a: {"dll_per_race": -0.01})
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
    races, info = F.collect_meeting(m, FakeCore(tmp_path / "20261201T090000+1100-x", cut - timedelta(hours=2), cut), W)
    assert info["source"] == "snapshot" and len(races) == 1
    r = races[0]
    assert r["source"] == F.SOURCE_TAG and r["snapshot"].startswith("20261201")
    assert [x["ability"] for x in r["rows"]] == [61.0, 62.0, 63.0, 64.0] and r["rows"][0]["sp"] == 3.0


def test_no_prerace_snapshot_means_no_rows(tmp_path):
    m = _meeting(tmp_path)
    races, info = F.collect_meeting(m, FakeCore(None, None, None), W)
    assert races == [] and info["source"] == "no_snapshot"      # 唔退返去 meeting 目錄


def test_snapshot_at_or_after_cutoff_is_rejected(tmp_path):
    m = _meeting(tmp_path)
    cut = datetime(2026, 12, 1, 0, 30, tzinfo=timezone.utc)
    races, info = F.collect_meeting(m, FakeCore(tmp_path / "20261201T120000+1100-x", cut, cut), W)
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


def test_tracker_ready_flag_only_for_marked_tests(tmp_path):
    import au_forward_tracker as T
    plain = T.ForwardTest("p", "P", "EXP-P", "status_file", 1000, "場", "判", status_file="s.json")
    marked = T.ForwardTest("h1", "H1", F.EXPERIMENT_ID, "status_file", 1000, "場", "判", status_file="s.json",
                           ready_from_status=True)

    def w(d):
        (tmp_path / "s.json").write_text(json.dumps(d))
    w({"races_collected": 1500, "target_races": 1000, "ready": False})
    assert T.progress(plain, work_dir=tmp_path)["ready"]              # 其他測試照舊睇場數
    assert not T.progress(marked, work_dir=tmp_path)["ready"]         # 場數夠但賽日未夠
    w({"races_collected": 10, "target_races": 1000, "ready": True})
    assert not T.progress(plain, work_dir=tmp_path)["ready"]
    assert T.progress(marked, work_dir=tmp_path)["ready"]
    w({"races_collected": 1500, "target_races": 1000, "ready": "false"})   # 字串唔算
    got = T.progress(marked, work_dir=tmp_path)
    assert not got["ready"] and "boolean" in got["error"]
    h1 = [t for t in T.FORWARD_TESTS if t.experiment == F.EXPERIMENT_ID][0]
    import au_hypothesis_forward as HF      # 通用假設 arm 都要同時夠賽日同場數（2026-11-26）
    allowed = {h1.experiment} | set(HF.ARMS)
    assert h1.ready_from_status and not any(t.ready_from_status for t in T.FORWARD_TESTS if t.experiment not in allowed)


# ---------------------------------------------------------------- Sol 覆核 2026-11-25 追加

class FieldCore(FakeCore):
    """5 匹、試閘分唔同；賽果可以換（模擬一匹唔跑完）。"""

    def __init__(self, results):
        cut = datetime(2026, 12, 1, 0, 30, tzinfo=timezone.utc)
        super().__init__(Path("/x/20261201T090000+1100-x"), cut - timedelta(hours=2), cut)
        self.results = results

    def load_structured_results(self, platform, path):
        return {1: {"results": self.results, "scratched_horse_numbers": []}}

    def load_prediction_rows(self, analysis_dir, platform):
        return {1: [{"horse_no": i, "horse_name": f"H{i}", "ability_score": 60.0 + i,
                     "factor_scores": {"trial_score": [60.0, 85.0, 70.0, 60.0, 90.0][i - 1],
                                       "preparation_score": 50.0 + 3 * i}} for i in (1, 2, 3, 4, 5)]}


def test_result_only_change_does_not_move_other_candidates(tmp_path):
    m = _meeting(tmp_path)
    all_finish = [{"horse_no": i, "placing": i, "odds": "5"} for i in (1, 2, 3, 4, 5)]
    dnf5 = [dict(r, placing=0) if r["horse_no"] == 5 else r for r in all_finish]      # 5 號唔跑完
    (a,), _ = F.collect_meeting(m, FieldCore(all_finish), W)
    (b,), _ = F.collect_meeting(m, FieldCore(dnf5), W)
    ca = {x["n"]: x["cand_ability"] for x in a["rows"]}
    cb = {x["n"]: x["cand_ability"] for x in b["rows"]}
    assert 5 in ca and 5 not in cb
    assert all(cb[n] == ca[n] for n in cb)          # 其他馬嘅候選分一模一樣
    wrong = [dict(x) for x in b["rows"]]             # 對照：喺有名次嘅馬入面先計 z（舊 bug）就會唔同
    F.score_field(wrong, W)
    assert any(abs(x["cand_ability"] - cb[x["n"]]) > 1e-9 for x in wrong)


def test_verdict_locked_by_experiment_id(monkeypatch, _verdict_lock_in_tmp):
    races = _races(F.START_DATE, F.TARGET_DAYS, 40)
    monkeypatch.setattr(F, "evaluate", lambda rs, w, **k: {"verdict": "FAIL", "cutoff_date": "x"})
    F.judge_once(races, W)
    assert json.loads(_verdict_lock_in_tmp.read_text())["evaluation"]["verdict"] == "FAIL"
    with pytest.raises(F.AlreadyJudged):
        F.judge_once(races, W)
    with pytest.raises(F.AlreadyJudged):
        F.write_verdict_once({"verdict": "PASS"})
    assert json.loads(_verdict_lock_in_tmp.read_text())["evaluation"]["verdict"] == "FAIL"   # 冇被覆蓋
    assert [p.name for p in _verdict_lock_in_tmp.parent.iterdir()] == [_verdict_lock_in_tmp.name]   # 冇暫存檔


def test_cli_cannot_rejudge_with_a_different_output_path(monkeypatch, tmp_path):
    F.write_verdict_once({"verdict": "FAIL"})

    def boom(*a, **k):
        raise AssertionError("已判就唔准再 collect／evaluate")
    monkeypatch.setattr(F, "collect", boom)
    monkeypatch.setattr(F, "evaluate", boom)
    other = tmp_path / "another" / "status.json"
    assert F.main(["evaluate", "--output", str(other), "--data-root", str(tmp_path)]) == 0
    st = json.loads(other.read_text())
    assert st["evaluation"] == {"verdict": "FAIL"} and st["state"] == "evaluated" and st["ready"] is True


def test_real_rulers_pair_races_and_score_only_forward(monkeypatch):
    """真 au_logloss_ruler v2 同 market_ruler（細樣本）：配對、計分窗、校準只用之前賽日。"""
    import au_logloss_ruler as L

    monkeypatch.setattr(F, "TARGET_DAYS", 22)
    monkeypatch.setattr(F, "TARGET_RACES", 100)
    pre = _races("2026-10-20", 25, 6, seed=3)
    fwd = _races(F.START_DATE, 24, 6, seed=4)
    ev = F.evaluate(pre + fwd, W, nnull=5)
    cutoff = fwd[22 * 6 - 1]["date"]
    assert ev["cutoff_date"] == cutoff
    assert ev["scored_days"] == [F.START_DATE, cutoff, 22]
    rank = ev["ranking_ruler"]
    assert rank["days"] == 22 and rank["races"] == 22 * 6            # 只計 forward
    gap = ev["market_ruler"]["gap_change"]
    assert gap["days"] == 22 and gap["races"] == 22 * 6
    assert ev["market_ruler"]["common_races"] == len(pre) + 22 * 6   # 每場都配對到
    # 校準只用之前賽日：倒轉嗰日（同之後）嘅賽果，嗰日嘅校準唔變
    base = L.eligible(pre + fwd)
    d = F.START_DATE
    flipped = [dict(r, rows=[dict(x, pos=len(r["rows"]) + 1 - x["pos"]) for x in r["rows"]]) if r["date"] >= d else r
               for r in base]
    assert L.calibrations(base, "v2")[d] == L.calibrations(flipped, "v2")[d]


def test_scheduler_step_wired_without_runlog_warn():
    src = (DAILY / "au_daily_schedule.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "step_h1_forward")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert not [c for c in calls if c.func.attr == "warn"]
    assert "step_h1_forward(runlog)" in src and 'H1_FORWARD = AU_SKILL / "au_wong_choi_auto" / "scripts" / "au_h1_forward.py"' in src
    body = ast.get_source_segment(src, fn)
    assert '"status", "evaluate"' in body and "au-h1-forward-status.json" in body
