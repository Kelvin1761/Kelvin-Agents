"""賽果抽取：中途一場取消唔可以令之後嘅場次全部冇抓（2026-11-14 沙田 R6 取消，R7–R11 漏抓）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fast_extract_results as fer  # noqa: E402


def fake_fetch(cancelled, last):
    def fetch(date, race, venue):
        if race > last:
            return None
        return {"race_no": race, "results": [] if race in cancelled else [{"pos": "1"}]}
    return fetch


def test_cancelled_race_is_skipped_not_the_end():
    races = fer.extract_meeting("2026-11-14", "ShaTin", fetch=fake_fetch({6}, 11), pause=0)
    assert sorted(map(int, races)) == [1, 2, 3, 4, 5, 7, 8, 9, 10, 11]


def test_stops_when_race_does_not_exist():
    calls = []

    def fetch(date, race, venue):
        calls.append(race)
        return fake_fetch(set(), 9)(date, race, venue)

    races = fer.extract_meeting("2026-11-18", "HappyValley", fetch=fetch, pause=0)
    assert len(races) == 9 and calls == list(range(1, 11))
