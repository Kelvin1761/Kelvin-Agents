"""老馬＋練馬師剩餘表現（實驗性上線 2026-11-22）：幅度凍結、冇前視、開關回退、入綜合分。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from au_racing_engine import people_overlays as P  # noqa: E402
from au_racing_engine.engine_core import RacingEngine  # noqa: E402

TABLE = {"jackbruce": [["2026-11-01", 5.0, 50], ["2026-11-21", 12.0, 70]],
         "davidpfieffer": [["2026-11-01", -1.0, 30]]}


def test_frozen_constants():
    assert (P.OLD_AGE, P.OLD_HORSE_PENALTY, P.TRAINER_BETA, P.TRAINER_K) == (8, -3.46, 40.0, 50.0)


def test_old_horse(monkeypatch):
    assert P.old_horse_feature(8) == -3.46 and P.old_horse_feature(7) == 0.0 and P.old_horse_feature(None) == 0.0
    monkeypatch.setenv("WC_AU_OLD_HORSE_LIVE", "0")
    assert P.old_horse_feature(9) == 0.0


def test_trainer_lookup_is_as_of():
    assert P.trainer_raw("Jack Bruce", "2026-11-21", TABLE) == 5.0 / 100     # 11-21 嗰筆唔用（同日）
    assert P.trainer_raw("Jack Bruce", "2026-11-22", TABLE) == 12.0 / 120
    assert P.trainer_raw("Jack Bruce", "2026-10-01", TABLE) == 0.0           # 未有紀錄
    assert P.trainer_raw("Nobody", "2026-11-22", TABLE) == 0.0


def test_trainer_feature_is_field_centred(monkeypatch):
    field = ["Jack Bruce", "David Pfieffer"]
    a = P.trainer_feature("Jack Bruce", field, "2026-11-22", TABLE)
    b = P.trainer_feature("David Pfieffer", field, "2026-11-22", TABLE)
    assert abs(a + b) < 1e-9 and a > 0
    monkeypatch.setenv("WC_AU_TRAINER_RESIDUAL_LIVE", "0")
    assert P.trainer_feature("Jack Bruce", field, "2026-11-22", TABLE) == 0.0


def test_engine_adds_both_overlays(tmp_path, monkeypatch):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"trainers": TABLE}))
    monkeypatch.setenv("WC_AU_TRAINER_RESIDUAL_TABLE", str(path))
    ctx = {"race_class": "BM70", "distance": "1200m", "field_summary": {"count": 2}, "date": "2026-11-22",
           "field_trainers": ["Jack Bruce", "David Pfieffer"],
           "meeting_intelligence": {"venue": "Kembla Grange", "going": "Good 4", "date": "2026-11-22"}}
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 3, "weight": 57.0, "age": 9,
             "jockey": "A Rider", "trainer": "Jack Bruce", "_data": {}}
    out = RacingEngine(horse, dict(ctx)).analyze_horse()
    assert out["old_horse_feature"] == -3.46
    assert out["trainer_residual_feature"] > 0
    base = out["pure_7d_score"] + out["wet_form_feature"] + out["proven_class_feature"] + \
        out["full_time_speed_feature"] + out["draw_feature"]
    assert abs(out["ability_score"] - round(base + out["old_horse_feature"] + out["trainer_residual_feature"], 4)) < 1e-3
    keys = {t["key"]: t for tone in ("good", "bad", "note") for t in out["tags"].get(tone, [])}
    assert keys["old_horse"]["scored"] is True and keys["trainer_residual"]["scored"] is True


PRIZE = {"jockey|kerrinmcevoy": [["2026-11-01", 7.0], ["2026-11-22", 9.0]], "jockey|rachelking": [["2026-11-01", 7.6]],
         "trainer|jackbruce": [["2026-11-01", 6.6]], "trainer|davidpfieffer": [["2026-11-01", 6.3]]}


def test_prize_constants_and_log_total():
    assert (P.PRIZE_BETA_JOCKEY, P.PRIZE_BETA_TRAINER) == (5.51, 4.43)
    t = {"Last 12 Months": {"$0 - $5,000": {"starts": 8}, "$5,001 - $10,000": {"starts": 2}}}
    assert abs(P.log_total_prize({"Last 12 Months": {}}) or 0) == 0 and P.log_total_prize({"Last 12 Months": {}}) is None
    import math
    assert abs(P.log_total_prize(t) - math.log10(8 * 2500 + 2 * 7500 + 1)) < 1e-9


def test_prize_as_of_and_field_centred(monkeypatch):
    assert P.prize_raw("jockey", "Kerrin McEvoy", "2026-11-22", PRIZE) == 7.0          # 同日快照唔用
    assert P.prize_raw("jockey", "Kerrin McEvoy (a2)", "2026-11-23", PRIZE) == 9.0     # 括號減磅唔影響配對
    fj, ft = ["Kerrin McEvoy", "Rachel King"], ["Jack Bruce", "David Pfieffer"]
    a = P.prize_feature("Kerrin McEvoy", "Jack Bruce", fj, ft, "2026-11-21", PRIZE)
    b = P.prize_feature("Rachel King", "David Pfieffer", fj, ft, "2026-11-21", PRIZE)
    assert abs(a + b) < 1e-9
    assert abs(a - round(5.51 * (7.0 - 7.3) + 4.43 * (6.6 - 6.45), 4)) < 1e-9
    assert P.prize_feature("Nobody", "Nobody", fj, ft, "2026-11-21", PRIZE) == 0.0
    monkeypatch.setenv("WC_AU_PEOPLE_PRIZE_LIVE", "0")
    assert P.prize_feature("Kerrin McEvoy", "Jack Bruce", fj, ft, "2026-11-21", PRIZE) == 0.0
