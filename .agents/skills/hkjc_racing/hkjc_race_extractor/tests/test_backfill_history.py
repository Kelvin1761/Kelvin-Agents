"""backfill_history 解析器：用真頁面 fixture（2019、2025 分段頁；2016 年入口退役馬資料頁）。"""
import gzip
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import backfill_history as b  # noqa: E402

FX = HERE / "fixtures" / "backfill"


def _read(name):
    return gzip.open(FX / name, "rt", encoding="utf-8").read()


def test_sectional_2019_three_sections_no_200m_splits():
    d = b.parse_sectional(_read("sectional_2019-11-03_R1.html.gz"))
    assert (d["distance"], d["class"], d["course"], d["going"], d["surface"]) == (1200, "第五班", "C+3", "好地至快地", "草地")
    assert len(d["horses"]) == 12
    w = d["horses"][0]
    assert (w["finish"], w["horse_id"], w["name"]) == ("1", "HK_2016_A277", "印印腳")
    assert [s["time"] for s in w["sections"]] == [24.49, 22.94, 22.37]
    assert [s["pos"] for s in w["sections"]] == [3, 5, 1]
    assert all(s["sub200"] == [] for s in w["sections"])
    # 每匹段數一樣（解析唔可以靜靜漏段）
    assert {len(h["sections"]) for h in d["horses"]} == {3}


def test_sectional_2025_200m_splits_not_duplicated():
    d = b.parse_sectional(_read("sectional_2025-11-09_R1.html.gz"))
    w = d["horses"][0]
    assert [s["time"] for s in w["sections"]] == [25.26, 23.2, 23.7, 24.28]
    assert w["sections"][2]["sub200"] == [11.76, 11.94]
    assert w["sections"][3]["sub200"] == [11.98, 12.3]
    assert abs(sum(w["sections"][3]["sub200"]) - w["sections"][3]["time"]) < 0.02


def test_horse_profile_runs_and_static_fields_only():
    d = b.parse_horse(_read("horse_HK_2016_A277.html.gz"))
    assert d["profile"]["父系"] == "Savabeel" and d["profile"]["出生地"] == "紐西蘭"
    assert "最後評分" not in d["profile"]          # 今日快照唔取（防洩漏）
    assert "最後評分" in d["snapshot"] and "總獎金*" in d["snapshot"]   # 快照分開保存
    assert len(d["runs"]) == 26
    r = d["runs"][0]
    assert (r["date"], r["rating"], r["gear"], r["body_wt"], r["season"]) == ("21/12/2019", "28", "SR/TT", "1195", "19/20")


def test_page_validity_rejects_unexpected_pages():
    assert b.looks_valid("sectional", _read("sectional_2019-11-03_R1.html.gz")) == "ok"
    assert b.looks_valid("sectional", "<html>Access Denied</html>") is None
    assert b.looks_valid("horse", "<html>captcha</html>") is None


def test_active_horse_two_digit_year_dates():
    # 現役馬頁面日期係 01/11/26（兩位數年份）；之前 regex 只收四位數，令現役馬 0 仗（2026-11-14 發現）
    d = b.parse_horse(_read("horse_active_HK_2024_K503.html.gz"))
    assert len(d["runs"]) >= 10
    r = d["runs"][0]
    assert (r["date"], r["pos"], r["rating"], r["season"]) == ("01/11/2026", "01", "40", "26/27")
