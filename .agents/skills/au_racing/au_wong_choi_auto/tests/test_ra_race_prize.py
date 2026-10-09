#!/usr/bin/env python3
"""今場總獎金由 RA Acceptances 頁攞，寫入 Racecard 標題，`build_au_logic` 照舊讀 `$…`。

2026-08 轉 Sportsbet 之後 `race_analysis.prize` 1,242 場得 1 場有值：Sportsbet 嘅賽事頁
同 API 都冇今場總獎金。冇咗佢，「上一仗 → 今場」升降班冇得計。
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL))

import ra_fields  # noqa: E402

PAGE = """
<table class="race-title"><tr><th><span>Race 1 - 12:00PM Bendigo Mazda 3YO Fillies Maiden Plate (1100 METRES)</span>
<span>Times displayed in local time of Race Meeting</span></th></tr>
<tr class="race-info"><td><b>Of $55,000.1st $30,250, 2nd $9,900</b> Maiden, Set Weights</td></tr></table>
<table><tr><th>No</th><th>Horse</th><th>Trainer</th><th>Jockey</th><th>Barrier</th><th>Weight</th>
<th>Probable Weight</th><th>Penalty</th><th>Hcp Rating</th><th>Last 10</th></tr>
<tr><td>1</td><td>ALPHA (NZ)</td><td>T</td><td>J</td><td>1</td><td>58</td><td>58</td><td>0</td><td>0</td><td>x</td></tr>
<tr><td>2</td><td>BRAVO</td><td>T</td><td>J</td><td>2</td><td>58</td><td>58</td><td>0</td><td>0</td><td>x</td></tr>
<tr><td>3</td><td>CHARLIE</td><td>T</td><td>J</td><td>3</td><td>58</td><td>58</td><td>0</td><td>0</td><td>x</td></tr>
</table>
<table class="race-title"><tr><th><span>Race 2 - 12:30PM Sportsbet Memsie Stakes (1400 METRES)</span></th></tr>
<tr class="race-info"><td><b>Of $750,000.1st $450,000</b> Group 1, Weight For Age</td></tr></table>
<table><tr><th>No</th><th>Horse</th><th>Trainer</th><th>Jockey</th><th>Barrier</th><th>Weight</th>
<th>Probable Weight</th><th>Penalty</th><th>Hcp Rating</th><th>Last 10</th></tr>
<tr><td>1</td><td>DELTA</td><td>T</td><td>J</td><td>1</td><td>59</td><td>59</td><td>0</td><td>116</td><td>x</td></tr>
<tr><td>2</td><td>ECHO</td><td>T</td><td>J</td><td>2</td><td>57</td><td>57</td><td>0</td><td>111</td><td>x</td></tr>
</table>
"""


class _Page(ra_fields.Fetcher):
    def __init__(self):  # noqa: D401 - no network, no cache
        pass

    def get(self, url, force=False, max_age=None):
        return PAGE


def _norm(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def test_acceptances_reads_total_prize_and_grade():
    races = ra_fields.acceptances("KEY", _Page())
    assert races[1]["prize"] == 55_000
    assert races[1]["grade"] == ""
    assert races[2]["prize"] == 750_000
    assert races[2]["grade"] == "Group 1"
    assert [r["horse"] for r in races[1]["runners"]] == ["ALPHA", "BRAVO", "CHARLIE"]


def test_prize_goes_to_the_race_whose_horses_match_not_the_race_number():
    races = ra_fields.acceptances("KEY", _Page())
    # Racecard 場次號同 RA 唔一致都要對得啱：呢張係 Memsie 嗰班馬
    lines = ["RACE 7 — 1400m | Sportsbet Memsie Stakes", "Track: Good 4",
             "1. Delta (3)", "Trainer: T", "2. Echo (1)", "Trainer: T"]
    assert ra_fields.stamp_race_prize(lines, races, _norm) is True
    assert lines[0] == "RACE 7 — 1400m | Sportsbet Memsie Stakes | $750,000"
    # 再跑一次唔會重複加
    assert ra_fields.stamp_race_prize(lines, races, _norm) is None


def test_no_stamp_when_horses_do_not_match():
    races = ra_fields.acceptances("KEY", _Page())
    lines = ["RACE 1 — 1100m | Something Else", "1. Zulu (1)", "2. Yankee (2)", "3. Xray (3)"]
    assert ra_fields.stamp_race_prize(lines, races, _norm) is None
    lines = ["RACE 1 — 1100m | Mixed", "1. Alpha (1)", "2. Yankee (2)", "3. Xray (3)", "4. Whisky (4)"]
    assert ra_fields.stamp_race_prize(lines, races, _norm) is False
    assert "$" not in lines[0]


def test_builder_still_reads_class_and_prize_from_stamped_header(tmp_path):
    sys.path.insert(0, str(SKILL / "au_wong_choi_auto" / "scripts"))
    import build_au_logic

    (tmp_path / "09-19 Race 9 Racecard.md").write_text(
        "RACE 9 — 1400m | Sportsbet Sir Rupert Clarke Stakes | $1,000,000\nTrack: Good 4\n",
        encoding="utf-8")
    facts = tmp_path / "09-19 Race 9 Facts.md"
    facts.write_text("# Race 9\n今仗距離: 1400m\n", encoding="utf-8")
    race_class, distance, prize = build_au_logic._extract_race_meta(facts, facts.read_text())
    assert race_class == "Sportsbet Sir Rupert Clarke Stakes"
    assert distance == "1400m"
    assert prize == 1_000_000
