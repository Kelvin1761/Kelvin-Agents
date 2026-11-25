"""Dashboard 校準機率（shadow）：同 model_probability 同一條公式、條件唔符合唔顯示、唔郁排名。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services import model_prob_display as D  # noqa: E402
from services.calibration_board_export import export_calibration_board  # noqa: E402


def _setup(tmp_path, **override):
    M = D._mp()
    params = {"status": "ok", "model_id": M.model_id("au"), "a": -0.005, "alpha": 0.08, "gamma": 1.14,
              "beta_win": 0.08, "fit_until": "2026-11-25", "n_days": 20, "n_races": 886}
    params.update(override)
    (tmp_path / "AU_Prob_Calibration.json").write_text(json.dumps(params), encoding="utf-8")
    csv = tmp_path / "Race_1_Auto_Scoring.csv"
    csv.write_text("race_number,horse_number,horse_name,ability_score,rank\n"
                   "1,1,A,62.0,1\n1,2,B,58.5,3\n1,3,C,60.0,2\n1,4,D,50.0,4\n", encoding="utf-8")
    D.load_params.cache_clear()
    return M, params, csv


def test_same_formula_as_model_probability(tmp_path):
    M, params, csv = _setup(tmp_path)
    got = D.race_probabilities(csv, "au", str(tmp_path))
    raws = [62.0, 58.5, 60.0, 50.0]
    t3, w = M.top3_probs(raws, params, "au"), M.win_probs(raws, params["beta_win"])
    for i, n in enumerate((1, 2, 3, 4)):
        assert got[n]["top3"] == pytest.approx(float(t3[i]), abs=1e-4)
        assert got[n]["win"] == pytest.approx(float(w[i]), abs=1e-4)
    assert sum(v["win"] for v in got.values()) == pytest.approx(1.0, abs=1e-3)
    assert got[1]["field_n"] == 4 and got[1]["fit_until"] == "2026-11-25"


@pytest.mark.parametrize("override", [{"status": "insufficient"}, {"model_id": "au_golden:old"}, {"alpha": None}])
def test_not_shown_unless_current_and_ok(tmp_path, override):
    _, _, csv = _setup(tmp_path, **override)
    assert D.race_probabilities(csv, "au", str(tmp_path)) == {}


def test_missing_files_mean_no_probability(tmp_path):
    D.load_params.cache_clear()
    assert D.race_probabilities(tmp_path / "nope.csv", "au", str(tmp_path)) == {}


def test_attach_is_display_only(tmp_path):
    _, _, csv = _setup(tmp_path)

    class H:
        def __init__(self, n, score):
            self.horse_number, self.ability_score, self.final_grade, self.model_probability = n, score, "A", None
    horses = [H(1, 70.0), H(2, 65.0), H(9, 50.0)]       # 9 號唔喺 CSV → 唔掛
    before = [(h.horse_number, h.ability_score, h.final_grade) for h in horses]
    assert D.attach(horses, csv, "au", str(tmp_path)) == 2
    assert [(h.horse_number, h.ability_score, h.final_grade) for h in horses] == before
    assert horses[2].model_probability is None and horses[0].model_probability["top3"] > 0


def test_calibration_board_export(tmp_path):
    raw = {"experiment": "EXP-20261125-07", "built_at": "x", "low_n": 50, "domains": {
        "au": {"first_day": "2026-08-25", "last_day": "2026-11-25",
               "top3": {"n": 10, "mean_p": 0.3, "hit_rate": 0.31, "ci": [0.2, 0.4], "logloss": 0.55,
                        "market": {"logloss_market": 0.5, "logloss_model": 0.55, "method": "m"},
                        "buckets": [{"bucket": "0.2-0.3", "n": 10, "mean_p": 0.25, "hit_rate": 0.3, "ci": [0.1, 0.5],
                                     "low_n": True}, {"bucket": "0.9-1.0", "n": 0}]},
               "win": {}},
        "nba": {"since": "2026-10-23", "until": "2026-11-16", "overall": {"n": 5, "mean_p": 0.3, "hit_rate": 0.3},
                "market_raw_close": {"gap": 0.04}, "buckets": []}}}
    p = tmp_path / "calibration_board.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    out = export_calibration_board(p)
    secs = {s["key"]: s for s in out["sections"]}
    assert secs["au_top3"]["available"] and secs["au_top3"]["market_logloss"] == 0.5
    assert [b["bucket"] for b in secs["au_top3"]["buckets"]] == ["0.2-0.3"]        # n=0 唔畫
    assert not secs["au_win"]["available"] and not secs["hkjc_top3"]["available"]  # 冇數唔扮有
    assert secs["nba"]["available"] and secs["nba"]["market_gap"] == 0.04
    with pytest.raises(Exception):
        export_calibration_board(tmp_path / "missing.json")
