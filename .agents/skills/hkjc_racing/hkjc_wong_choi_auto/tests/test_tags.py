"""HKJC 標籤（tags.py）：每個 chip 係具體事實；未入分嘅要標明；賽日當日或之後嘅往績唔准用。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import summary, tags  # noqa: E402

RACE_DATE = "2026-11-11"


def _entry(date, venue_track, distance, jockey, placing, racecourse=None):
    d, m, y = date.split("/")
    return {"date": date, "race_date_full": f"{y}/{m}/{d}", "venue_track": venue_track,
            "racecourse": racecourse or ("HV" if venue_track.startswith("跑馬地") else "ST"),
            "distance": distance, "jockey": jockey, "placing": placing}


def _horse(name, jockey, *, hid, barrier=5, hk_starts=3, l400="", adjustments=(), rows=(), last6="3-4-5"):
    return {
        "horse_name": name, "jockey": jockey, "barrier": barrier, "hkjc_horse_id": hid,
        "last_6_finishes": last6,
        "_data": {"hk_starts": hk_starts, "l400_trend": l400},
        "python_auto": {
            "rank": 1,
            "trainer_signal_detail": {"adjustments": [
                {"factor": f, "delta": d, "evidence": f"{f} 證據"} for f, d in adjustments]},
            "grade_transparency": {"rows": [{"key": k, "label": k, "impact": i} for k, i in rows]},
        },
    }


def _meeting(tmp_path, horses, profiles, *, venue="跑馬地", track="Turf", distance="1650m", racecard=""):
    md = tmp_path / "2026-11-11_HappyValley"
    (md / ".hkjc_cache").mkdir(parents=True)
    (md / ".hkjc_cache" / "profile_cache.json").write_text(json.dumps(
        {hid: {"_ts": 0, "data": {"entries": entries}} for hid, entries in profiles.items()}, ensure_ascii=False),
        encoding="utf-8")
    if racecard:
        (md / "11-11 Race 5 排位表.md").write_text(racecard, encoding="utf-8")
    logic = {"race_analysis": {"race_number": 5, "race_date": RACE_DATE, "venue": venue, "track": track,
                               "distance": distance}, "horses": horses}
    return logic, md


def _labels(out, no, tone):
    return [t["label"] for t in out[no][tone]]


def test_purton_left_and_chose_are_unscored_facts(tmp_path):
    horses = {"1": _horse("被棄", "田泰安", hid="H1"), "2": _horse("被揀", "潘頓", hid="H2")}
    profiles = {"H1": [_entry("01/11/2026", "跑馬地草地\"C\"", 1650, "潘頓", 2)],
                "H2": [_entry("01/11/2026", "跑馬地草地\"C\"", 1650, "巴度", 4)]}
    out = tags.race_tags(*_meeting(tmp_path, horses, profiles))
    assert _labels(out, "1", "bad") == ["潘頓棄騎（揀咗 2 號）"]
    assert out["1"]["bad"][0]["scored"] is False
    assert _labels(out, "2", "note") == ["潘頓揀咗呢匹（棄 1 號）"]


def test_purton_not_in_this_race_is_not_a_tag(tmp_path):
    horses = {"1": _horse("甲", "田泰安", hid="H1"), "2": _horse("乙", "巴度", hid="H2")}
    profiles = {"H1": [_entry("01/11/2026", "跑馬地草地\"C\"", 1650, "潘頓", 2)], "H2": []}
    out = tags.race_tags(*_meeting(tmp_path, horses, profiles))
    assert not any("潘頓" in t["label"] for tone in out["1"].values() for t in tone)


def test_runs_on_or_after_race_day_are_ignored(tmp_path):
    # 賽後重跑：profile 已經有今仗（潘頓騎，1650米）—— 唔可以當「上仗」
    horses = {"1": _horse("甲", "田泰安", hid="H1", hk_starts=1), "2": _horse("乙", "潘頓", hid="H2", hk_starts=0)}
    profiles = {"H1": [_entry("11/11/2026", "跑馬地草地\"C\"", 1650, "潘頓", 1),
                       _entry("01/11/2026", "沙田草地\"A\"", 1200, "巴度", 5)], "H2": []}
    out = tags.race_tags(*_meeting(tmp_path, horses, profiles))
    assert "潘頓棄騎（揀咗 2 號）" not in _labels(out, "1", "bad")
    notes = _labels(out, "1", "note")
    assert "初跑1650米" in notes and "初跑跑馬地" in notes and "大幅升程（1200→1650米）" in notes


def test_first_time_tags_need_complete_history(tmp_path):
    # hk_starts 5 但 profile 只得 1 仗 → 歷史唔齊，唔可以話「初跑」
    horses = {"1": _horse("甲", "巴度", hid="H1", hk_starts=5)}
    profiles = {"H1": [_entry("01/11/2026", "沙田草地\"A\"", 1200, "巴度", 5)]}
    out = tags.race_tags(*_meeting(tmp_path, horses, profiles))
    assert not [t for t in out["1"]["note"] if t["key"].startswith("first_")]


def test_debut_horse_gets_no_first_time_tags(tmp_path):
    horses = {"1": _horse("初出", "巴度", hid="H1", hk_starts=0)}
    out = tags.race_tags(*_meeting(tmp_path, horses, {"H1": []}, venue="沙田AWT", track="AWT"))
    assert out["1"]["note"] == []


def test_first_awt_and_specialist(tmp_path):
    horses = {"1": _horse("甲", "巴度", hid="H1", hk_starts=4, rows=[("distance_fit", 0.43)])}
    runs = [_entry(f"0{d}/10/2026", "沙田草地\"A\"", 1200, "巴度", p) for d, p in ((1, 1), (2, 2), (3, 6), (4, 3))]
    out = tags.race_tags(*_meeting(tmp_path, horses, {"H1": runs}, venue="沙田AWT", track="AWT", distance="1200m"))
    good = out["1"]["good"]
    assert good[0]["label"] == "首本路程（1200米 4戰1勝3上名）" and good[0]["scored"] is True
    assert "初跑泥地" in _labels(out, "1", "note")


def test_trainer_signal_tags_follow_engine_adjustments_and_skip_small_ones(tmp_path):
    horses = {"1": _horse("甲", "巴度", hid="H1", adjustments=[
        ("人馬歷史", 4.0), ("騎練組合", 4.0), ("騎練組合", 2.0), ("騎師同程", 1.5), ("練馬師同程", -1.5), ("換騎", -1.5)],
        rows=[("trainer_signal", 2.0)])}
    profiles = {"H1": [_entry("01/11/2026", "跑馬地草地\"C\"", 1650, "田泰安", 4)]}
    out = tags.race_tags(*_meeting(tmp_path, horses, profiles))
    assert _labels(out, "1", "good") == ["人馬合拍", "騎練黃金組合"]          # +2 組合、+1.5 同程太細
    assert _labels(out, "1", "bad") == ["換騎（田泰安→巴度）"]
    assert all(t["scored"] for t in out["1"]["good"] + out["1"]["bad"])
    # 騎練訊號維度已由具體加減項講晒，唔再出「騎師實績強（巴度）」
    assert not any(t["key"] == "dim:trainer_signal" for t in out["1"]["good"])


def test_dimension_drivers_become_concrete_phrases(tmp_path):
    horse = _horse("甲", "巴度", hid="H1", barrier=3, last6="1-2-9-4-5-6",
                   rows=[("race_shape", 2.8), ("stability", -0.6), ("trackwork", -0.04)])
    out = tags.race_tags(*_meeting(tmp_path, {"1": horse}, {"H1": []}))
    assert _labels(out, "1", "good") == ["檔位走位有利（3檔）"]
    assert _labels(out, "1", "bad") == ["近績差（近3仗 1-2-9）"]
    assert out["1"]["good"][0]["impact"] == 2.8


def test_fastest_finisher_needs_a_clear_leader(tmp_path):
    trend = lambda *v: "（最舊 → 最新）" + "→".join(f"{x:.2f}" for x in v) + " → 趨勢: 波動"
    horses = {str(i): _horse(f"馬{i}", "巴度", hid=f"H{i}", l400=trend(24.0, 23.5, 23.0 + i / 10)) for i in range(1, 6)}
    out = tags.race_tags(*_meeting(tmp_path, horses, {f"H{i}": [] for i in range(1, 6)}))
    assert [t["label"] for t in out["1"]["good"] if t["key"] == "fastest_l400"] == ["近3仗末段全場最快（23.53s）"]
    assert not any(t["key"] == "fastest_l400" for no in "2345" for t in out[no]["good"])


def test_trainer_ace_from_racecard(tmp_path):
    card = "馬號: 1\n馬名: 甲\n優先參賽次序: + 1\n\n馬號: 2\n馬名: 乙\n優先參賽次序: * 1\n"
    horses = {"1": _horse("甲", "巴度", hid="H1"), "2": _horse("乙", "田泰安", hid="H2")}
    out = tags.race_tags(*_meeting(tmp_path, horses, {"H1": [], "H2": []}, racecard=card))
    assert "練馬師王牌" in _labels(out, "1", "note") and "練馬師王牌" not in _labels(out, "2", "note")


def test_missing_files_and_bad_input_never_raise(tmp_path):
    logic = {"race_analysis": {}, "horses": {"1": _horse("甲", "巴度", hid="H1", rows=[("race_shape", 1.0)])}}
    out = tags.race_tags(logic, tmp_path / "nope")
    assert _labels(out, "1", "good") == ["檔位走位有利（5檔）"]
    assert tags.race_tags({"horses": {"1": {"python_auto": None}}}) == {}
    assert "_error" in tags.race_tags({"horses": ["唔係 dict"]})


def test_summary_attach_carries_tags_and_does_not_touch_scores(tmp_path):
    horses = {"1": _horse("甲", "巴度", hid="H1", rows=[("race_shape", 2.0)])}
    horses["1"]["python_auto"].update({"ability_score": 70.0, "ability_score_raw": 65.0, "grade": "B"})
    logic, md = _meeting(tmp_path, horses, {"H1": []})
    before = json.dumps({k: v for k, v in horses["1"]["python_auto"].items()}, sort_keys=True)
    summary.attach(logic, md)
    auto = horses["1"]["python_auto"]
    assert _labels({"1": auto["summary"]["tags"]}, "1", "good") == ["檔位走位有利（5檔）"]
    auto.pop("summary")
    assert json.dumps(auto, sort_keys=True) == before
