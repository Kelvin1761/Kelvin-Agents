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
