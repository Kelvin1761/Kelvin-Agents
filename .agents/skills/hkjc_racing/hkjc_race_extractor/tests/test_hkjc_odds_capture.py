"""HKJC 賽前賠率快照：解析、追加、失敗形狀。全部離線，冇一個測試打 HKJC。

fixture `hkjc_pmpools_win_pla_20261014_HV.json` 係 2026-10-14 跑馬地真實回應
（只留 R1/R2 各三匹），所以欄位形狀係真嘅，唔係估出嚟嘅 —— AU 試過用假設
markup 寫 fixture，測試一路綠而 parser 喺真頁面回 0 匹。
"""
from __future__ import annotations

import copy
import gzip
import importlib.util
import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "hkjc_odds_capture.py"
_SPEC = importlib.util.spec_from_file_location("hkjc_odds_capture_test", SCRIPT)
oc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(oc)

FIXTURE = HERE / "fixtures" / "hkjc_pmpools_win_pla_20261014_HV.json"
AT = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _getter(payload: dict, *, gz: bool = False):
    calls: list[str] = []

    def get(url: str) -> bytes:
        calls.append(url)
        raw = json.dumps(payload).encode()
        return gzip.compress(raw) if gz else raw

    get.calls = calls  # type: ignore[attr-defined]
    return get


def _capture(tmp_path: Path, payload: dict, label: str = "prerace", **kw):
    return oc.capture_meeting(tmp_path, race_date="2026-10-14", venue="HappyValley",
                              venue_code="HV", label=label, getter=_getter(payload),
                              captured_at=kw.get("at", AT))


# ── query 一定要同官方網頁一模一樣（白名單） ─────────────────────────────────

def test_stripped_query_matches_the_whitelisted_form():
    """改一個欄位／次序，server 就回 WHITELIST_ERROR。呢條釘住 token 序列。"""
    got = oc.strip_ignored(oc.PM_POOL_QUERY)
    assert got.startswith(
        "query sp4e_racing_pmPool($date:String$venueCode:String"
        "$oddsTypes:[OddsType]$raceNo:Int){raceMeetings(date:$date venueCode:$venueCode)"
        "{pmPools(oddsTypes:$oddsTypes raceNo:$raceNo){id status sellStatus oddsType "
        "lastUpdateTime oddsLastUpdateTime guarantee minTicketCost name_en name_ch "
        "leg{number races}cWinSelections{composite name_ch name_en starters}"
        "oddsNodes{combString oddsValue hotFavourite oddsDropValue "
        "bankerOdds{combString oddsValue}}}}}")
    assert got.endswith("}}}}}")
    assert "  " not in got and "," not in got


def test_one_get_covers_the_whole_meeting_win_and_place():
    url = oc.build_url("2026-10-14", "hv")
    assert url.startswith("https://info.cld.hkjc.com/graphql/base-get/?")
    variables = json.loads(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["variables"][0])
    assert variables == {"date": "2026-10-14", "venueCode": "HV", "raceNo": 0,
                         "oddsTypes": ["WIN", "PLA"]}


# ── 解析 ────────────────────────────────────────────────────────────────────

def test_win_and_place_join_per_runner_from_the_real_response():
    races = oc.parse_pools(_payload())
    assert sorted(races) == ["1", "2"]
    assert races["1"]["runners"]["1"] == {"win": 4.9, "place": 2.4}
    assert races["1"]["runners"]["2"] == {"win": 23.0, "place": 6.3}
    assert races["2"]["runners"]["3"] == {"win": 3.2, "place": 1.5}
    assert races["1"]["pre_race"] is True
    assert races["1"]["win_updated"].startswith("2026-10-14T09:")


def test_horse_numbers_drop_the_leading_zero_to_match_logic():
    races = oc.parse_pools(_payload())
    assert "01" not in races["1"]["runners"] and "1" in races["1"]["runners"]


def test_a_non_numeric_price_is_a_scratching_not_a_price():
    payload = _payload()
    for pool in payload["data"]["raceMeetings"][0]["pmPools"]:
        if pool["leg"]["races"] == [1]:
            pool["oddsNodes"][1]["oddsValue"] = "SCR"
    races = oc.parse_pools(payload)
    assert races["1"]["scratched"] == ["2"]
    assert "2" not in races["1"]["runners"], "退出馬唔可以留一邊嘅價"


def test_a_closed_pool_is_flagged_as_not_pre_race():
    """停售後嘅價係開跑後嘅 —— 回測靠 `pre_race` 過濾，所以一定要標。"""
    payload = _payload()
    for pool in payload["data"]["raceMeetings"][0]["pmPools"]:
        if pool["leg"]["races"] == [2] and pool["oddsType"] == "WIN":
            pool["sellStatus"] = "STOP_SELL"
    races = oc.parse_pools(payload)
    assert races["1"]["pre_race"] is True
    assert races["2"]["pre_race"] is False


# ── 寫檔：追加、唔覆蓋 ────────────────────────────────────────────────────────

def test_snapshots_append_with_timestamp_and_label(tmp_path):
    first = _capture(tmp_path, _payload(), label="prerace")
    second = _capture(tmp_path, _payload(), label="lineup",
                      at=datetime(2026, 10, 14, 2, 0, tzinfo=timezone.utc))
    assert first["status"] == second["status"] == "ok"
    assert first["races"] == 2 and first["runners"] == 6
    doc = json.loads((tmp_path / oc.ODDS_HISTORY).read_text(encoding="utf-8"))
    assert [s["label"] for s in doc["snapshots"]] == ["prerace", "lineup"]
    assert doc["snapshots"][0]["captured_at"] == "2026-10-14T01:00:00+00:00"
    assert doc["scoring_input"] is False
    assert doc["venue_code"] == "HV"


def test_only_one_file_is_written_and_it_is_not_a_scoring_input(tmp_path):
    _capture(tmp_path, _payload())
    written = {p.name for p in tmp_path.iterdir()}
    assert written == {oc.ODDS_HISTORY}
    assert not oc.ODDS_HISTORY.endswith("Facts.md")
    assert "Logic" not in oc.ODDS_HISTORY


def test_a_corrupt_history_is_kept_aside_not_overwritten(tmp_path):
    (tmp_path / oc.ODDS_HISTORY).write_text("{not json", encoding="utf-8")
    _capture(tmp_path, _payload())
    backups = list(tmp_path.glob(oc.ODDS_HISTORY + ".corrupt-*"))
    assert len(backups) == 1 and backups[0].read_text() == "{not json"
    doc = json.loads((tmp_path / oc.ODDS_HISTORY).read_text(encoding="utf-8"))
    assert len(doc["snapshots"]) == 1


def test_pools_not_open_yet_write_nothing(tmp_path):
    empty = {"data": {"raceMeetings": [{"pmPools": []}]}}
    assert _capture(tmp_path, empty)["status"] == "not_open"
    assert not (tmp_path / oc.ODDS_HISTORY).exists()
    assert _capture(tmp_path, {"data": {"raceMeetings": []}})["status"] == "not_open"


def test_an_all_closed_meeting_writes_nothing(tmp_path):
    payload = _payload()
    for pool in payload["data"]["raceMeetings"][0]["pmPools"]:
        pool["sellStatus"] = "STOP_SELL"
    assert _capture(tmp_path, payload)["status"] == "closed"
    assert not (tmp_path / oc.ODDS_HISTORY).exists()


# ── 失敗一定要係例外，唔可以扮「冇賠率」 ─────────────────────────────────────

def test_whitelist_error_raises_instead_of_looking_empty(tmp_path):
    """官方改咗 query 之後會變呢個形狀：data 係 null，好似「未開盤」—— 唔准咁讀。"""
    payload = {"errors": [{"message": "Internal server error - WHITELIST_ERROR"}],
               "data": {"raceMeetings": None}}
    with pytest.raises(oc.OddsCaptureError, match="WHITELIST_ERROR"):
        _capture(tmp_path, payload)
    assert not (tmp_path / oc.ODDS_HISTORY).exists()


def test_http_failure_raises(tmp_path):
    def boom(url):
        raise TimeoutError("timed out")
    with pytest.raises(oc.OddsCaptureError, match="TimeoutError"):
        oc.fetch_pools("2026-10-14", "HV", getter=boom)


def test_non_json_raises():
    with pytest.raises(oc.OddsCaptureError, match="JSON"):
        oc.fetch_pools("2026-10-14", "HV", getter=lambda url: b"<html>blocked</html>")


def test_gzip_body_is_decoded():
    """HKJC 回 gzip，就算冇 Accept-Encoding 都會。"""
    got = oc.fetch_pools("2026-10-14", "HV", getter=_getter(_payload(), gz=True))
    assert got["data"]["raceMeetings"][0]["pmPools"]


def test_parse_does_not_mutate_the_payload():
    payload = _payload()
    before = copy.deepcopy(payload)
    oc.parse_pools(payload)
    assert payload == before
