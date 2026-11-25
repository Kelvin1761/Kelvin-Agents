"""通用假設 forward（au_hypothesis_forward）：凍結、term 定義、盲測、判決、接駁。"""
from __future__ import annotations

import ast
import json
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

import au_hypothesis_forward as F  # noqa: E402

H2, H3 = F.ARMS["EXP-20261126-01"], F.ARMS["EXP-20261126-02"]


@pytest.fixture(autouse=True)
def _locks_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "verdict_path", lambda arm: tmp_path / "lock" / f"{arm.id}.json")
    return tmp_path / "lock"


def _row(rng, i, k):
    return {"n": i + 1, "name": f"H{k}-{i}", "ability": float(rng.normal(60, 3)),
            "jockey_score": float(rng.normal(60, 5)), "trainer_score": float(rng.normal(60, 5)),
            "days_since_last": float(rng.choice([7, 21, 35, 120])), "sp": float(rng.uniform(2, 30))}


def _races(arm, start, days, per_day, seed=0, n=8):
    rng = np.random.default_rng(seed)
    w = F.load_frozen(arm)
    out = []
    for d in range(days):
        day = (date.fromisoformat(start) + timedelta(days=d)).isoformat()
        for k in range(1, per_day + 1):
            rows = [_row(rng, i, k) for i in range(n)]
            F.score_field(arm, rows, w)
            for x, p in zip(rows, rng.permutation(n) + 1):
                x["pos"] = int(p)
            out.append({"date": day, "meeting": f"{day} T", "race": k, "rows": rows, "source": F.SOURCE_TAG})
    return out


# 1. 凍結

@pytest.mark.parametrize("arm", list(F.ARMS.values()), ids=list(F.ARMS))
def test_every_arm_frozen_matches_sha_and_terms(arm):
    w = F.load_frozen(arm)
    frozen = json.loads(arm.frozen_path.read_text(encoding="utf-8"))
    assert set(w) == {t.key for t in arm.terms}
    assert frozen["experiment"] == arm.id and frozen["fit"]["until"] < arm.start
    for k in w:
        assert w[k] == pytest.approx(frozen["fit"]["beta"][k] / frozen["fit"]["alpha"])


def test_modified_frozen_is_refused(tmp_path, monkeypatch):
    bad = tmp_path / H2.frozen
    data = json.loads(H2.frozen_path.read_text(encoding="utf-8"))
    data["weights"]["jockey_score"] += 0.1
    bad.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(F, "PATCH_DIR", tmp_path)
    with pytest.raises(F.FrozenParamsChanged):
        F.load_frozen(H2)


def test_forward_engine_never_refits():
    tree = ast.parse((SCRIPTS / "au_hypothesis_forward.py").read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | \
        {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "_fit" not in names


def test_directions_match_hypotheses():
    w2, w3 = F.load_frozen(H2), F.load_frozen(H3)
    assert w2["jockey_score"] > 0 and w2["trainer_score"] > 0      # H2：騎練被低估
    assert w3["spell90"] < 0 and w3["backup14"] > 0                # H3：長休高估、快回低估


# 2. term 定義

def test_indicator_terms():
    spell, backup = H3.terms
    assert spell.indicator(90) == 1 and spell.indicator(89) == 0 and spell.indicator(None) == 0
    assert backup.indicator(14) == 1 and backup.indicator(1) == 1
    assert backup.indicator(0) == 0 and backup.indicator(15) == 0 and backup.indicator(None) == 0


def test_shift_is_computed_on_full_prerace_field():
    rows = [{"ability": 60.0, "days_since_last": d} for d in (7, 30, 120, None)]
    F.score_field(H3, rows, {"spell90": -2.0, "backup14": 1.0})
    assert [x["cand_ability"] for x in rows] == [61.0, 60.0, 58.0, 60.0]


# 3. 盲測、計數

def test_status_blind_and_needs_days_and_races():
    w = F.load_frozen(H2)
    few_days = _races(H2, H2.start, H2.target_days - 1, 40)
    assert len(few_days) >= H2.target_races and not F.status(H2, few_days, {}, w)["ready"]
    enough = _races(H2, H2.start, H2.target_days, 40)
    st = F.status(H2, enough, {}, w)
    assert st["ready"] and st["outcomes_visible"] is False
    shuffled = [dict(r, rows=[dict(x, pos=len(r["rows"]) + 1 - x["pos"]) for x in r["rows"]]) for r in enough]
    strip = lambda s: {k: v for k, v in s.items() if k != "generated_at"}  # noqa: E731
    assert strip(F.status(H2, shuffled, {}, w)) == strip(st)
    for word in ("dlogloss", "gold", "auc", "verdict", "gap_change"):
        assert word not in json.dumps(st)


def test_pre_start_not_counted():
    st = F.status(H3, _races(H3, "2026-10-01", 50, 40), {}, F.load_frozen(H3))
    assert st["races_collected"] == 0 and not st["ready"]


# 4. 判決

def test_evaluate_rule_and_window(monkeypatch):
    import au_logloss_ruler as L
    import market_ruler as M
    races = _races(H2, "2026-10-20", 20, 5, seed=1) + _races(H2, H2.start, H2.target_days, 40, seed=2)
    seen = {}
    monkeypatch.setattr(L, "evaluate", lambda b, c, **k: seen.setdefault("days", sorted(L.calibrations(b, "v2"))) and {"verdict": "PASS"})
    monkeypatch.setattr(M, "evaluate", lambda *a, **k: seen.setdefault("mw", k["score_window"]) and {"paired": {}, "arms": {}})
    monkeypatch.setattr(F.H1, "windowed_gap_change", lambda b, c, lo, hi: {"dll_per_race": 0.0})
    ev = F.evaluate(H2, races)
    assert ev["verdict"] == "PASS" and min(seen["days"]) >= H2.start and seen["mw"][0] == H2.start
    monkeypatch.setattr(F.H1, "windowed_gap_change", lambda *a: {"dll_per_race": 0.0003})
    assert F.evaluate(H2, races)["verdict"] == "FAIL"
    with pytest.raises(ValueError):
        F.evaluate(H2, _races(H2, H2.start, 3, 5))


def test_verdict_lock_per_arm(monkeypatch, _locks_in_tmp):
    monkeypatch.setattr(F, "evaluate", lambda arm, rs, **k: {"verdict": "FAIL"})
    F.judge_once(H2, [])
    with pytest.raises(F.AlreadyJudged):
        F.judge_once(H2, [])
    F.judge_once(H3, [])           # 另一個 arm 唔受影響
    assert sorted(p.name for p in _locks_in_tmp.iterdir()) == [f"{H2.id}.json", f"{H3.id}.json"]


def test_real_rulers_small_sample(monkeypatch):
    import dataclasses
    small = dataclasses.replace(H3, target_days=20, target_races=100)
    races = _races(H3, "2026-10-20", 25, 6, seed=3) + _races(H3, H3.start, 22, 6, seed=4)
    ev = F.evaluate(small, races, nnull=5)
    assert ev["scored_days"][0] == H3.start and ev["scored_days"][2] == 20
    assert ev["ranking_ruler"]["races"] == 20 * 6 and ev["market_ruler"]["gap_change"]["races"] == 20 * 6


# 5. 快照讀取

class FakeCore:
    def __init__(self, snap):
        cut = datetime(2026, 12, 1, 0, 30, tzinfo=timezone.utc)
        self.snap = (snap, cut - timedelta(hours=2), cut)

    def find_existing_results_file(self, platform, m):
        return m / "r.json"

    def select_prerace_snapshot(self, m, platform):
        return self.snap

    def load_structured_results(self, platform, p):
        return {1: {"results": [{"horse_no": i, "placing": i, "odds": "4"} for i in (1, 2, 3)],
                    "scratched_horse_numbers": []}}

    def load_prediction_rows(self, d, platform):
        return {1: [{"horse_no": i, "horse_name": f"H{i}", "ability_score": 60.0 + i,
                     "factor_scores": {"jockey_score": 50.0 + i, "trainer_score": 55.0}} for i in (1, 2, 3, 4)]}


def test_collect_reads_logic_days_and_full_field(tmp_path):
    m = tmp_path / "2026-12-01 Randwick Race 1-8"
    m.mkdir()
    snap = tmp_path / "snap"
    snap.mkdir()
    horses = {str(i): {"horse_number": str(i), "python_auto": {"preparation_cycle": {"days_since_last_run": d}}}
              for i, d in zip((1, 2, 3, 4), (7, 100, "", 30))}
    (snap / "Race_1_Logic.json").write_text(json.dumps({"horses": horses}), encoding="utf-8")
    (r,), info = F.collect_meeting(H3, m, FakeCore(snap), {"spell90": -2.0, "backup14": 1.0})
    assert info["source"] == "snapshot" and [x["n"] for x in r["rows"]] == [1, 2, 3]   # 4 號冇賽果 → 只喺 join 剔走
    assert [x["cand_ability"] for x in r["rows"]] == [62.0, 60.0, 63.0]
    (snap / "Race_1_Logic.json").unlink()
    races, info = F.collect_meeting(H3, m, FakeCore(snap), {"spell90": -2.0, "backup14": 1.0})
    assert races == [] and info["skipped_races"] == 1                                 # 冇 Logic = 成場唔要
    (r2,), _ = F.collect_meeting(H2, m, FakeCore(snap), F.load_frozen(H2))            # H2 唔使 Logic
    assert len(r2["rows"]) == 3


# 6. 接駁

def test_every_arm_in_tracker_and_scheduler():
    import au_forward_tracker as T
    for arm in F.ARMS.values():
        hit = [t for t in T.FORWARD_TESTS if t.experiment == arm.id]
        assert len(hit) == 1 and hit[0].status_file == F.status_file_name(arm) and hit[0].ready_from_status
        assert hit[0].minimum == arm.target_races
    src = (DAILY / "au_daily_schedule.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "step_hyp_forward")
    assert not [c for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                and c.func.attr == "warn"]
    assert "step_hyp_forward(runlog)" in src and '"nightly"' in ast.get_source_segment(src, fn)


def test_nightly_isolates_arm_failures(monkeypatch, tmp_path):
    calls = []

    def fake(arm, command, out, root, **kw):
        calls.append(arm.id)
        if arm.id == H2.id:
            raise RuntimeError("boom")
        return {"state": "collecting", "ready": False}
    monkeypatch.setattr(F, "run_arm", fake)
    assert F.main(["nightly", "--work-dir", str(tmp_path), "--data-root", str(tmp_path)]) == 1
    assert calls == [H2.id, H3.id]


# 7. Sol 覆核 2026-11-26 追加

def test_judging_needs_production_root(monkeypatch, tmp_path):
    st = {"ready": True, "state": "ready"}
    monkeypatch.setattr(F, "load_frozen", lambda arm: {})
    monkeypatch.setattr(F, "collect", lambda *a, **k: ([], {"offline": [], "meetings": {}, "skipped_races": 0}))
    monkeypatch.setattr(F, "status", lambda *a, **k: dict(st))
    monkeypatch.setattr(F, "judge_once", lambda *a, **k: pytest.fail("唔准封判決"))
    with pytest.raises(F.NonProductionJudge):
        F.run_arm(H2, "evaluate", tmp_path / "o.json", tmp_path / "other", production_root=tmp_path / "prod")
    with pytest.raises(F.NonProductionJudge):
        F.run_arm(H2, "evaluate", tmp_path / "o.json", tmp_path / "prod")      # 冇講生產語料 = 唔准
    monkeypatch.setattr(F, "judge_once", lambda *a, **k: {"verdict": "FAIL"})
    got = F.run_arm(H2, "evaluate", tmp_path / "o.json", tmp_path / "prod", production_root=tmp_path / "prod")
    assert got["state"] == "evaluated"


def test_output_cannot_target_lock_dir(_locks_in_tmp):
    with pytest.raises(ValueError):
        F.run_arm(H2, "status", _locks_in_tmp / "x.json", _locks_in_tmp)


class DupCore(FakeCore):
    def load_prediction_rows(self, d, platform):
        rows = super().load_prediction_rows(d, platform)
        rows[1][3] = dict(rows[1][2])          # 4 號變咗第二個 3 號；3 匹有賽果，筆數仍然夾
        return rows


def test_duplicate_horse_numbers_skip_race(tmp_path):
    m = tmp_path / "2026-12-01 Randwick Race 1-8"
    m.mkdir()
    races, info = F.collect_meeting(H2, m, DupCore(tmp_path), F.load_frozen(H2))
    assert races == [] and info["skipped_races"] == 1


class DnfCore(FakeCore):
    def __init__(self, snap, dnf):
        super().__init__(snap)
        self.dnf = dnf

    def load_structured_results(self, platform, p):
        res = [{"horse_no": i, "placing": (0 if i == self.dnf else i), "odds": "4"} for i in (1, 2, 3, 4)]
        return {1: {"results": res, "scratched_horse_numbers": []}}


def test_h2_z_uses_full_field_not_finishers(tmp_path):
    m = tmp_path / "2026-12-01 Randwick Race 1-8"
    m.mkdir()
    w = F.load_frozen(H2)
    (a,), _ = F.collect_meeting(H2, m, DnfCore(tmp_path, None), w)
    (b,), _ = F.collect_meeting(H2, m, DnfCore(tmp_path, 4), w)
    ca, cb = {x["n"]: x["cand_ability"] for x in a["rows"]}, {x["n"]: x["cand_ability"] for x in b["rows"]}
    assert 4 in ca and 4 not in cb and all(cb[n] == ca[n] for n in cb)
    wrong = [dict(x) for x in b["rows"]]
    F.score_field(H2, wrong, w)                  # 對照：喺完賽馬入面先計 z 會唔同
    assert any(abs(x["cand_ability"] - cb[x["n"]]) > 1e-9 for x in wrong)
