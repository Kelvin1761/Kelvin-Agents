"""官方騎練排名 vs 賽果庫對數（crawl_hkjc_jockey_trainer）。

舊版 crawler 爬 HTML table；新站係 client-side render，HTML 一行數據都冇，
永遠回 0 行而且由來冇 caller。而家改為 GraphQL + 只做數據質素檢查：
官方本季 [頭,二,三,四,五,出賽] 應該同我哋 full_day_results.json 逐人一樣，
對唔上就代表賽果庫漏咗賽日。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import crawl_hkjc_jockey_trainer as ranking  # noqa: E402


def _stat(counts, trk="ALL", ven="ALL"):
    keys = ("numFirst", "numSecond", "numThird", "numFourth", "numFifth", "numStarts")
    return {**dict(zip(keys, counts)), "stakeWon": "0", "trk": trk, "ven": ven}


def _person(name_ch, counts, extra_rows=()):
    return {"name_ch": name_ch, "name_en": name_ch, "ssnStat": [*extra_rows, _stat(counts)], "dhStat": []}


def _meeting(root: Path, day: str, races: dict) -> None:
    folder = root / "hkjc results 2026 27" / day
    folder.mkdir(parents=True)
    (folder / "full_day_results.json").write_text(json.dumps(races, ensure_ascii=False), encoding="utf-8")


def _race(*rows):
    return {"results": [{"pos": p, "jockey": j, "trainer": t} for p, j, t in rows]}


def _fake_post(last_date, jockeys, trainers):
    def post(operation, _query, _variables):
        if operation == "rw_LastMeeting":
            return {"data": {"lastMeeting": {"date": last_date, "season": "26/27"}}}
        if operation == "rw_GetJockeyRanking":
            return {"data": {"jockeyStat": jockeys}}
        if operation == "rw_GetTrainerRanking":
            return {"data": {"trainerStat": trainers}}
        raise AssertionError(operation)

    return post


def _db(tmp_path: Path) -> Path:
    _meeting(tmp_path, "2026-10-07", {
        "1": _race(("1", "潘頓", "方嘉柏"), ("2", "布文", "蔡約翰"), ("PU", "田泰安", "方嘉柏"), ("WV", "巴度", "蔡約翰")),
        "2": _race(("1 平頭馬", "布文", "蔡約翰"), ("1 平頭馬", "潘頓", "方嘉柏"), ("---", "田泰安", "方嘉柏")),
    })
    _meeting(tmp_path, "2026-10-11", {"1": _race(("1", "田泰安", "方嘉柏"), ("2", "潘頓", "蔡約翰"))})
    return tmp_path


OFFICIAL_J = [
    _person("潘頓", [2, 1, 0, 0, 0, 3], extra_rows=[_stat([9, 9, 9, 9, 9, 99], "TURF", "ST")]),
    _person("布文", [1, 1, 0, 0, 0, 2]),
    _person("田泰安", [1, 0, 0, 0, 0, 2]),
    _person("冇出賽", [0, 0, 0, 0, 0, 0]),
]
OFFICIAL_T = [_person("方嘉柏", [3, 0, 0, 0, 0, 4]), _person("蔡約翰", [1, 2, 0, 0, 0, 3])]


def test_counts_match_official_rules(tmp_path):
    """退出（WV、---）唔計出賽；PU 計出賽冇名次；平頭馬計頭馬；只用 ALL/ALL 行。"""
    report = ranking.build_report(_db(tmp_path), post=_fake_post("2026-10-11", OFFICIAL_J, OFFICIAL_T))
    assert report["status"] == "ok", report
    assert report["jockey"]["matched"] == report["jockey"]["compared"] == 3
    assert report["trainer"]["matched"] == 2
    assert "✅" in ranking.format_report(report)


def test_missing_meeting_warns(tmp_path):
    """官方已計 10-14，賽果庫冇 = 賽果庫停咗。"""
    db = _db(tmp_path)
    j = [*OFFICIAL_J[:2], _person("田泰安", [2, 0, 0, 0, 0, 3])]
    report = ranking.build_report(db, post=_fake_post("2026-10-14", j, OFFICIAL_T))
    assert report["status"] == "warn"
    assert any("2026-10-14" in p for p in report["problems"])
    assert any("頭馬總數差 +1" in p for p in report["problems"])
    text = ranking.format_report(report)
    assert "⚠️" in text and "田泰安" in text


def test_meetings_after_official_cutoff_are_ignored(tmp_path):
    """我哋已入咗官方未計嘅新賽日 —— 唔係差異。"""
    db = _db(tmp_path)
    _meeting(db, "2026-10-14", {"1": _race(("1", "潘頓", "方嘉柏"))})
    report = ranking.build_report(db, post=_fake_post("2026-10-11", OFFICIAL_J, OFFICIAL_T))
    assert report["status"] == "ok", report


def test_site_failure_is_unavailable_not_exception(tmp_path):
    def boom(*_a):
        raise OSError("network down")

    report = ranking.build_report(_db(tmp_path), post=boom)
    assert report["status"] == "unavailable"
    assert "今次攞唔到" in ranking.format_report(report)


def test_whitelist_error_is_unavailable(tmp_path):
    def rejected(*_a):
        return {"errors": [{"message": "Internal server error - WHITELIST_ERROR"}], "data": {"lastMeeting": None}}

    assert ranking.build_report(_db(tmp_path), post=rejected)["status"] == "unavailable"


def test_season_folder_name():
    assert ranking.results_dir_for_season(Path("/x"), "26/27") == Path("/x/hkjc results 2026 27")
