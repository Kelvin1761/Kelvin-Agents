"""重抓 Racecard 唔可以洗走已經補咗嘅官方讓磅分。

Sportsbet 個 rating 欄 0% 有值，數字全部由 RA 補。2026-10-02 Cranbourne：晚更補咗
76 個，賽日早更重抓 Racecard 寫返 `Rating: -`，RA 州曆又查唔到 → 全場當未評分。
讓磅分喺接受報名嗰刻就定咗，所以重寫時沿用返舊 Racecard 嘅數。
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
os.environ.setdefault("WC_SB_CACHE_ONLY", "1")

from claw_sportsbet_form import existing_ratings, rating_for_card, _rating_key  # noqa: E402

CARD = """RACE 2 — 1400m | BM64 Handicap
Track: Good 4 | Weather: Unknown | Rail:
============================================================
1. Delta Dawn (1)
Trainer: T | Jockey: J | Weight: 59.0kg | Age: 4yoM | Rating: 72
Career: 9 : 2-1-1 | Win: 22% | Place: 44%
----------------------------------------
2. O'Echo (2)
Trainer: T | Jockey: J | Weight: 57.0kg | Age: 5yoG | Rating: -
Career: 3 : 0-0-0 | Win: 0% | Place: 0%
----------------------------------------
"""


def test_reads_only_numeric_ratings(tmp_path):
    card = tmp_path / "10-02 Race 2 Racecard.md"
    card.write_text(CARD, encoding="utf-8")
    kept = existing_ratings(card)
    assert kept == {_rating_key("Delta Dawn"): "72"}


def test_missing_card_is_empty(tmp_path):
    assert existing_ratings(tmp_path / "nope.md") == {}


def test_sportsbet_blank_falls_back_to_kept_rating():
    assert rating_for_card("-", "72") == "72"
    assert rating_for_card("", "72") == "72"


def test_sportsbet_number_wins_and_nothing_kept_keeps_original():
    assert rating_for_card("80", "72") == "80"
    assert rating_for_card("-", None) == "-"
