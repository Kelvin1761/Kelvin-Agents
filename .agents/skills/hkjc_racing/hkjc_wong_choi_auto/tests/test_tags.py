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
    assert "初跑1650米" in notes and "初跑跑馬地" not in notes      # 初次跑馬地改由 _surface_move_tags 出


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
    # 「初次泥地」而家由轉場組件（引擎 surface_move）出，唔再由馬匹頁 runs 計（EXP-20261117-06）
    assert "初跑泥地" not in _labels(out, "1", "note")


def test_specialist_needs_place_rate_above_two_thirds(tmp_path):
    # EXP-20261118-05：2/2 係首本；3/5（60%）同 1 勝 1/4 唔係（舊門檻會出）
    def run(placings):
        horses = {"1": _horse("甲", "巴度", hid="H1", hk_starts=len(placings), rows=[("distance_fit", 0.43)])}
        runs = [_entry(f"0{i + 1}/10/2026", "沙田草地\"A\"", 1200, "巴度", p) for i, p in enumerate(placings)]
        d = tmp_path / str(len(placings)) / "".join(map(str, placings))
        d.mkdir(parents=True)
        out = tags.race_tags(*_meeting(d, horses, {"H1": runs}, distance="1200m"))
        return [t for t in out["1"]["good"] if t["key"] == "specialist"]
    two = run([2, 3])
    assert two and "上名率 > 2/3" in two[0]["why"]
    assert not run([1, 2, 3, 6, 7])
    assert not run([1, 6, 7, 8])


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
    assert _labels(out, "1", "good") == ["內檔優勢（3檔）"]
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
    assert _labels(out, "1", "good") == ["中檔優勢（5檔）"]
    assert tags.race_tags({"horses": {"1": {"python_auto": None}}}) == {}
    assert "_error" in tags.race_tags({"horses": ["唔係 dict"]})


def test_summary_attach_carries_tags_and_does_not_touch_scores(tmp_path):
    horses = {"1": _horse("甲", "巴度", hid="H1", rows=[("race_shape", 2.0)])}
    horses["1"]["python_auto"].update({"ability_score": 70.0, "ability_score_raw": 65.0, "grade": "B"})
    logic, md = _meeting(tmp_path, horses, {"H1": []})
    before = json.dumps({k: v for k, v in horses["1"]["python_auto"].items()}, sort_keys=True)
    summary.attach(logic, md)
    auto = horses["1"]["python_auto"]
    assert _labels({"1": auto["summary"]["tags"]}, "1", "good") == ["中檔優勢（5檔）"]
    auto.pop("summary")
    assert json.dumps(auto, sort_keys=True) == before


def test_awt_vs_turf_and_straight_tags_are_unscored(tmp_path):
    horses = {"1": _horse("甲", "巴度", hid="H1", hk_starts=5)}
    runs = ([_entry(f"0{d}/10/2026", "沙田全天候跑道", 1200, "巴度", p) for d, p in ((1, 1), (2, 3))]
            + [_entry(f"0{d}/09/2026", "沙田草地\"A\"", 1200, "巴度", 8) for d in (1, 2, 3)])
    out = tags.race_tags(*_meeting(tmp_path / "a", horses, {"H1": runs}, venue="沙田AWT", track="AWT", distance="1200m"))
    t = [x for x in out["1"]["good"] if x["key"] == "awt_better"]
    assert t and t[0]["scored"] is False

    runs = [_entry("01/10/2026", "沙田草地\"A\"", 1000, "巴度", 2), _entry("01/09/2026", "沙田草地\"A\"", 1200, "巴度", 5)]
    horses = {"1": _horse("甲", "巴度", hid="H1", hk_starts=2)}
    out = tags.race_tags(*_meeting(tmp_path / "b", horses, {"H1": runs}, venue="沙田", distance="1000m"))
    assert "直路有上名往績（1戰1上名）" in _labels(out, "1", "good")


def test_formline_chip_does_not_say_strong(tmp_path):
    out = tags.race_tags(*_meeting(tmp_path, {"1": _horse("甲", "巴度", hid="H1", rows=[("form_line", 1.2)])}, {"H1": []}))
    assert _labels(out, "1", "good") == ["賽績線佔優"]


def test_wide_two_back_tag_is_unscored():
    """EXP-20261116-18：上上仗走外疊只顯示。"""
    out = tags._incident_tag({"incident_history_flags": "", "incident_wide_two_back": True})
    assert [t["label"] for t in out] == ["上上仗走外疊冇遮擋"]
    assert out[0]["scored"] is False and out[0]["tone"] == "good"
    assert tags._incident_tag({"incident_history_flags": ""}) == []


def test_gear_chips_and_trainer_pattern_wins():
    """Kelvin 2026-11-17：除去配備有訊號（未入分）要突出；首次配備只留意；練馬師專屬 pattern 有就唔重複。"""
    out = tags._gear_tags(["B-", "TT1", "H2"], set())
    assert [(t["label"], t["tone"], t["scored"]) for t in out] == [("除去眼罩", "good", False), ("首次戴繫舌帶", "note", False)]
    assert tags._gear_tags(["B-"], {"gear_removed"}) == []
    assert tags._gear_tags([], set()) == []


def test_jockey_change_always_names_both_riders():
    auto = {"trainer_signal_detail": {"adjustments": [{"factor": "換騎", "delta": -1.0, "evidence": "沿用原騎較好"}]}}
    horse = {"jockey": "何澤堯", "_data": {"prev_jockey": "楊明綸", "jockey_change_note": "今仗轉用騎師何澤堯（與此駒首次合作）"}}
    t = tags._jockey_change_tag(horse, auto, runs=[])
    assert t[0]["label"] == "換騎（楊明綸→何澤堯）" and "首次策騎此駒" in t[0]["why"]
    t = tags._jockey_change_tag({"jockey": "班德禮", "_data": {}}, auto, runs=[])
    assert t[0]["label"] == "換騎（今仗 班德禮）"


def test_weak_combo_reads_as_not_in_sync():
    auto = {"trainer_signal_detail": {"adjustments": [{"factor": "騎練組合", "delta": -3.0, "evidence": "x"}]}}
    assert [t["label"] for t in tags._trainer_tags(auto)] == ["騎練唔合拍"]


def test_distance_move_and_quick_backup_and_rating_near_win():
    """Kelvin 2026-11-17：增程有訊號 → 扣分位；減程留意；匆匆再出留意；評分跌返／接近贏馬分留意（EXP-20261117-02）。"""
    meta = {"distance": 1650, "date": "2026-11-18"}
    horse = {"_data": {"hk_starts": 3}}
    runs = [{"distance": 1200, "placing": 5, "venue": "HV", "awt": False, "jockey": "x"}]
    # 增減程 chip 用引擎組件（distance_move）嘅判斷：≥400 米先出；增程入分
    auto = {"distance_move": {"prev": 1200, "today": 1650, "up": True}, "distance_move_delta": -0.85}
    t = tags._distance_move_tags(auto)
    up = [x for x in t if x["key"] == "distance_up"]
    assert up and up[0]["label"] == "大幅增程（1200→1650米）" and up[0]["tone"] == "bad" and up[0]["scored"]
    assert up[0]["impact"] == -0.85
    auto = {"distance_move": {"prev": 1650, "today": 1200, "up": False}}
    t = tags._distance_move_tags(auto)
    assert [x["label"] for x in t if x["key"] == "distance_down"] == ["大幅減程（1650→1200米）"]
    auto = {"distance_move": {"prev": 1400, "today": 1200, "up": False}}     # 200 米唔係大幅
    t = tags._distance_move_tags(auto)
    assert not [x for x in t if x["key"] in ("distance_up", "distance_down")]
    assert tags._backup_tag({"days_since_last": 7})[0]["label"] == "相隔 7 日再出"
    assert tags._backup_tag({"days_since_last": 14}) == []
    from hkjc_racing_engine.form_patterns import flags
    h = {"last_6_finishes": "4-1", "_data": {"current_rating": "57", "rating_trend": "57→55",
                                              "recent_6_detail": "第1仗(01/11/2026 第四班)"}}
    f = flags(h, "第四班", "2026-11-18", win_table={})
    assert f["rating_near_win"] and not f["classdrop_rating_back"] and f["win_rating"] == 55
    out = tags._form_pattern_tags(h, {"race_class": "第四班", "date": "2026-11-18"})
    assert [x["label"] for x in out] == ["評分接近贏馬分（57，上次贏馬 55）"]


def test_next_entry_tag():
    """Kelvin 2026-11-17：賽前已報 7 日內另一場 → 留意標籤（EXP-20261117-04）。"""
    h = {"_data": {"next_entry": {"date": "2026-11-22", "venue": "沙田", "race": 9, "class": "4", "distance": 1400, "days": 4}}}
    t = tags._next_entry_tag(h)
    assert t[0]["label"] == "已報 11/22 沙田（4 日後）" and t[0]["tone"] == "note" and not t[0]["scored"]
    assert "第 9 場" in t[0]["why"] and "4班" in t[0]["why"]
    assert tags._next_entry_tag({"_data": {}}) == []


def test_scored_distance_move_always_has_a_chip_even_without_profile_runs():
    """2026-11-18：14 匹大幅增程扣咗分但只有 4 匹有 chip（馬匹頁往績冇載入 → _distance_venue_tags 提早 return）。"""
    auto = {"distance_move": {"prev": 1200, "today": 1650, "up": True}, "distance_move_delta": -0.8}
    out = tags.horse_tags("1", {"_data": {}}, auto, runs=[], meta={"distance": 1650, "date": "2026-11-18"})
    assert "大幅增程（1200→1650米）" in [t["label"] for t in out["bad"]]


def _hh(*rows):
    return {"hk_history": [dict(zip(("surface", "class", "distance", "placing", "jockey"), r)) for r in rows]}


def test_surface_tags_scored_and_info():
    auto = {"surface_move": {"today": "田草", "hv_to_st": True, "first_st": True}, "surface_move_delta": -3.9}
    t = tags._surface_move_tags({"_data": _hh(("谷草", "4", 1200, 5, "A"))}, auto)
    assert t[0]["label"] == "跑馬地轉沙田草地、初次沙田草地" and t[0]["scored"] and t[0]["tone"] == "bad"
    auto = {"surface_move": {"today": "泥地"}, "surface_move_delta": 0.0}
    t = tags._surface_move_tags({"_data": _hh(("谷草", "4", 1200, 5, "A"))}, auto)
    assert [(x["label"], x["tone"], x["scored"]) for x in t] == [("跑馬地轉泥地", "bad", False)]


def test_class_move_tags():
    h = {"weight": "116", "_data": _hh(("谷草", "3", 1200, 6, "A"), ("谷草", "4", 1200, 2, "A"))}
    # 第三班 → 第四班：曾經跑過第四班 → 唔係「初落」
    assert tags._class_move_tags(h, {"race_class": "第四班", "distance": 1200}) == []
    h = {"weight": "116", "_data": _hh(("谷草", "3", 1200, 6, "A"), ("田草", "3", 1200, 2, "A"))}
    t = tags._class_move_tags(h, {"race_class": "第四班（條件限制）", "distance": 1200})
    assert t[0]["label"] == "初落第4班＋1200米上過名（1次）" and t[0]["tone"] == "good" and not t[0]["scored"]
    h = {"weight": "116", "_data": _hh(("谷草", "4", 1200, 5, "A"))}
    t = tags._class_move_tags(h, {"race_class": "第三班", "distance": 1200})
    assert [x["label"] for x in t] == ["升班輕磅（116磅、上仗未贏）"]
    h = {"weight": "116", "_data": _hh(("谷草", "4", 1200, 1, "A"))}            # 上仗贏即升班唔計
    assert tags._class_move_tags(h, {"race_class": "第三班", "distance": 1200}) == []


def test_race_people_tags_jockey_switch_and_stable():
    hist3 = _hh(("谷草", "4", 1200, 5, "甲"), ("谷草", "4", 1200, 4, "甲"), ("谷草", "4", 1200, 6, "甲"))
    horses = {"1": {"jockey": "乙", "trainer": "T1", "_data": hist3}, "2": {"jockey": "甲", "trainer": "T1", "_data": {}},
              "3": {"jockey": "丙", "trainer": "T2", "_data": {}}}
    out = tags._race_people_tags(horses, {"date": "2026-11-18"})
    assert "常騎騎師甲今場騎 2 號" in [t["label"] for t in out["1"]]
    assert "甲棄 1 號揀呢匹" in [t["label"] for t in out["2"]]
    choices = sorted(t["label"] for no in ("1", "2") for t in out[no] if t["key"] == "stable_choice")
    assert choices == ["同馬房 2 匹：次選", "同馬房 2 匹：正選"]
    assert not [t for t in out.get("3", []) if t["key"] == "stable_choice"]


def test_age_weight_tag():
    assert tags._age_weight_tag({"weight": "133", "_data": {"age": 3}})[0]["label"] == "3 歲負 133 磅"
    assert tags._age_weight_tag({"weight": "133", "_data": {"age": 4}}) == []


def test_trainer_awt_switch_pattern():
    """EXP-20261117-09：容天鵬泥地／草地轉場（練馬師 pattern 表，未入分）。"""
    from hkjc_racing_engine.trainer_patterns import patterns, matches
    h = {"trainer": "容天鵬", "_data": {"hk_history": [{"surface": "泥地"}]}}
    assert "awt_switch" in patterns(h, "第四班", 1200, [], "谷草")
    assert "awt_switch" not in patterns(h, "第四班", 1200, [], "泥地")
    assert "awt_switch" not in patterns(h, "第四班", 1200, [])                 # 冇今仗場地 = 唔判
    assert [c["pattern"] for c in matches(h, "第四班", 1200, [], "田草")] == ["awt_switch"]
    assert matches(dict(h, trainer="蔡約翰"), "第四班", 1200, [], "田草") == []
