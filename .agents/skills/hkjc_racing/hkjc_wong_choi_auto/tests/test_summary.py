"""白話重點（summary.py）：原因按對總分嘅影響排，唔係按原始 0–100 分。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import summary  # noqa: E402


def _auto(rows, **extra):
    return {
        "rank": 1, "ability_score": 76.7, "grade": "A-",
        "grade_transparency": {"rows": [
            {"key": k, "label": label, "impact": impact} for k, label, impact in rows]},
        "matrix_reasoning": {k: {"text": f"{label}嘅原因 → 72分，加分位。"} for k, label, _ in rows},
        **extra,
    }


def test_reasons_are_ranked_by_impact_not_raw_score():
    auto = _auto([("form_line", "賽績線", 0.6), ("sectional", "段速表現", 2.4),
                  ("race_shape", "檔位與走位", -1.1), ("trackwork", "晨操狀態", -0.04)])
    out = summary.horse_summary({}, auto, 14)
    assert [p["label"] for p in out["plus"]] == ["段速表現", "賽績線"]
    assert [m["label"] for m in out["minus"]] == ["檔位與走位"]          # −0.04 細過門檻
    assert out["plus"][0]["why"] == "段速表現嘅原因"                       # 「→ 72分」唔再重複
    assert out["headline"] == "第1／14｜76.7 A-｜靠段速表現、賽績線；檔位與走位拖低"


def test_watch_lists_layoff_and_injury_but_not_age_check():
    horse = {"_data": {"official_injury_records": [
        {"incident_date": "2026-08-11", "detail": "於季終時年屆八歲或以上"},
        {"incident_date": "2026-08-04", "detail": "左邊骨盆受傷"},
    ]}}
    out = summary.horse_summary(horse, _auto([], days_since_last=210.0), 14)
    assert out["watch"][0] == "休賽 210 日後復出"
    assert "左邊骨盆受傷" in out["watch"][1] and "年屆" not in "".join(out["watch"])


def test_neutral_horse_says_so():
    out = summary.horse_summary({}, _auto([("sectional", "段速表現", 0.2)]), 9)
    assert out["plus"] == [] and out["minus"] == []
    assert out["headline"].endswith("冇明顯強項或弱項")


def test_race_summary_uses_measured_gap_buckets():
    ranking = [{"horse_number": n, "horse_name": f"馬{n}", "ability_score": s}
               for n, s in ((11, 80.0), (5, 76.5), (2, 75.0), (3, 74.5), (9, 68.0))]
    clear = summary.race_summary(ranking)
    assert clear["tightness"] == "clear" and "58%" in clear["lines"][0]
    assert any("斷層" in line for line in clear["lines"])
    ranking[1]["ability_score"] = 79.0
    assert summary.race_summary(ranking)["tightness"] == "close"


def test_battlefield_and_detail_lines():
    """Kelvin 2026-11-17：戰場全景歷史形勢＋今場分佈；全場重點加首選理由、歷史跑法／檔位、入分特別因素。"""
    table = {"since": "2019-09-01", "cells": {"谷草|1200": {"races": 1066, "base": {"n": 100, "place": 0.25, "win": 0.08},
             "style": {"放頭": {"n": 10, "place": 0.36, "win": 0.1}, "守中": {"n": 10, "place": 0.31, "win": 0.1},
                       "後上": {"n": 10, "place": 0.16, "win": 0.05}},
             "draw": {"內檔": {"n": 10, "place": 0.34, "win": 0.1}, "中檔": {"n": 10, "place": 0.24, "win": 0.1},
                      "外檔": {"n": 10, "place": 0.17, "win": 0.05}}}}}

    names = {"2": "甲", "11": "乙", "6": "丙"}

    def h(style, barrier, tags=None):
        return {"horse_name": names[barrier], "barrier": barrier, "python_auto": {"run_style": {"label": style} if style else None,
                                                     "summary": {"tags": tags or {}}}}
    logic = {"race_analysis": {"venue": "跑馬地", "track": "Turf", "distance": "1200m"},
             "horses": {"1": h("放頭", "2", {"good": [{"key": "draw", "label": "內檔優勢（2檔）", "scored": True}]}),
                        "2": h("後上", "11", {"bad": [{"key": "surface_move", "label": "跑馬地轉沙田草地", "scored": True}]}),
                        "3": h(None, "6")}}
    bf = summary.battlefield(logic, table)
    assert bf["surface"] == "跑馬地" and bf["today_styles"]["放頭"] == ["1"] and bf["today_styles"]["未明"] == ["3"]
    assert bf["today_draws"] == {"內檔": ["1"], "中檔": ["3"], "外檔": ["2"]}
    summary._BATTLEFIELD = table
    try:
        out = summary.race_summary([{"horse_number": "1", "horse_name": "甲", "ability_score": 80},
                                    {"horse_number": "2", "horse_name": "乙", "ability_score": 70}], logic)
    finally:
        summary._BATTLEFIELD = None
    text = "\n".join(out["lines"])
    assert "首選 1 甲 主要靠：內檔優勢（2檔）" in text
    assert "跑馬地 1200米歷史（1066 場）放頭最著數：上名率 36%（平均 25%）；今場慣性放頭：1 甲" in text
    assert "檔位：內檔上名率 34%，外檔只有 17%；今場內檔：1 甲（2 檔）" in text
    kinds = [it["kind"] for it in out["items"]]
    assert kinds[:2] == ["top", "reasons"] and "style" in kinds and "draw" in kinds
    # 半場或以下先列：3 匹入面 1 匹跑馬地轉沙田草地 → 列；名同號都有
    fac = [it for it in out["items"] if it["kind"] == "factor"]
    assert fac and fac[0]["horses"] == [{"no": "2", "name": "乙"}] and fac[0]["tone"] == "bad"
    assert out["battlefield"]["history"]["races"] == 1066


def test_scenario_constants():
    """情境幅度（EXP-20261117-08；EXP-20261119-10 改實測）：上名率 1pp ≈ 0.87 顯示分；跑法 ±2pp、檔位 ±3pp；即場 ×0.2、上限 2pp。"""
    sc = summary.scenario_constants()
    assert 0.8 < sc["pp_to_display"] < 0.95
    assert sc["style"]["放頭"] == {"放頭": 2, "守中": 0, "後上": -2}
    assert sc["draw"]["利內欄"] == {"內檔": 3, "中檔": 0, "外檔": -3}
    assert sc["full_pp"] == {"style": 2, "draw": 3}
    # 每個情境：被利一類 = 滿幅、冇一格超過滿幅
    assert all(max(abs(v) for v in d.values()) == sc["full_pp"]["style"] for d in sc["style"].values())
    assert all(max(abs(v) for v in d.values()) == sc["full_pp"]["draw"] for d in sc["draw"].values())
    assert set(sc["draw"]) == {"利內欄", "利中內", "利中欄", "利中外", "利外欄"}
    assert sc["inrace"] == {"shrink": 0.2, "cap_pp": 2, "min_starts": 8}


def test_brief_cuts_at_clause_and_drops_codes():
    text = "L400 23.29→23.77s；段速優勢：輸頭馬少（< 0.3 秒）(+6.5)、原始分段後段快過前段（受路程影響）(+3.0)、末段速度波動(-1.0) → 73分，加分位。"
    out = summary._brief(text)
    assert "(+6.5)" not in out and "→ 73分" not in out
    assert out.startswith("L400 23.29→23.77s；段速優勢：輸頭馬少")
    assert len(out) <= summary.BRIEF_LIMIT + 1
    assert summary._brief("晨操退出排名（EXP-20261029-02），只作顯示參考") == "晨操退出排名，只作顯示參考"


def test_dim_briefs_cover_every_dimension_and_trackwork_uses_its_read():
    auto = {
        "grade_transparency": {"rows": [{"key": "race_shape", "label": "檔位與走位"}]},
        "matrix_reasoning": {
            "race_shape": {"label": "檔位與走位情境（不含步速）", "text": "排5檔：檔位中性，睇出閘搶位 → 62分，中性。"},
            "trackwork": {"label": "晨操狀態", "text": "晨操退出排名（EXP-20261029-02），只作顯示參考"},
        },
        "trackwork_read": {"lines": ["近21日快操3課、試閘0課、踱步13課 → 工作量正常"], "verdict": "操練放緩，以正式賽績為準"},
    }
    dims = {d["key"]: d for d in summary.dim_briefs(auto)}
    assert dims["race_shape"] == {"key": "race_shape", "label": "檔位與走位", "text": "排5檔：檔位中性，睇出閘搶位"}
    assert dims["trackwork"]["text"] == "近21日快操3課、試閘0課；操練放緩，以正式賽績為準"


def test_verdict_top_pick_and_chaser():
    sm = {"plus": [{"label": "騎練訊號"}], "minus": [], "watch": [],
          "tags": {"good": [{"label": "近績好", "scored": True, "impact": 3.3}],
                   "bad": [{"label": "大幅增程", "scored": True, "impact": -0.1}]}}
    top = summary.verdict(sm, {"rank": 1, "ability_score": 87.6}, [87.6, 69.2, 60.0])
    assert top["text"] == "模型首選，拋離第二名 18.4 分。主要靠騎練訊號；要留意大幅增程。"
    assert top["good"] == ["近績好"] and top["bad"] == ["大幅增程"]
    assert "58%" in top["ref"]
    second = summary.verdict(sm, {"rank": 2, "ability_score": 69.2}, [87.6, 69.2, 60.0])
    assert second["text"].startswith("排第 2／3，落後首選 18.4 分")
    assert "44%" in second["ref"]
    enriched = summary.enrich(dict(sm), {"rank": 1, "ability_score": 87.6}, [87.6, 69.2])
    assert "dims" in enriched and "verdict" in enriched
