"""Sportsbet 抽取嘅時點正確性同場次身分。

兩個真實出現過嘅缺陷，兩個都係**靜靜**壞：

1. **賽後洩漏。** sportsbetform 嘅表格頁只有賽後先抓到，所以每匹馬嘅往績
   第一行就係我哋要預測嗰場，連名次、負距、頭馬名同 600m 段速都齊。
   實測 2026-08-01 Flemington：520 條往績有 89 條（17.1%）係當日或之後，
   而且係最近一行 —— 近績加權最重嗰行。留住佢，backtest 會靚到假。

2. **場次錯配。** raceId 唔跟場次遞增（3393737=R7、3393739=R9、
   3394294=R6、3394295=R8）。舊 `parse_race` 個 regex 要求開跑時間，
   賽後頁面冇，所以 `race_number` 永遠係 None，靜靜跌返落 enumerate 次序，
   將 R6–R9 洗牌。
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
AU_RACING = ROOT / ".agents" / "skills" / "au_racing"
sys.path.insert(0, str(AU_RACING))

from claw_sportsbet_form import parse_race, run_date, write_meeting  # noqa: E402

MEETING_DATE = "2026-08-01"

RUN_LINE = re.compile(
    r"^\S.*?\sR\d+\s(?P<date>\d{4}-\d{2}-\d{2})\s+\d+m\s+cond:", re.M)


def _run(date, pos="3", field="11"):
    return {
        "header": {"track": "Flemington", "going": "Good", "date": date,
                   "race": "5", "dist": "1410"},
        "pos": pos, "field": field, "margin": "0.42",
        "jockey": "E Pozman", "barrier": "10", "weight": "61.5",
        "prize": "130,000", "sp": "7.50", "l600": None,
        "opponents": [{"name": "Stage 'n' Screen", "wt": "58", "mgn": None}],
    }


class RunDateTest(unittest.TestCase):
    def test_normalises_sportsbet_ddmmyyyy(self):
        self.assertEqual(run_date(_run("15/07/2026")), "2026-07-15")

    def test_missing_date_is_empty_not_none(self):
        self.assertEqual(run_date({"header": {}}), "")

    def test_empty_date_sorts_before_the_meeting(self):
        # 冇日期就唔應該當成賽後洩漏而丟棄 —— "" < "2026-08-01"。
        self.assertLess(run_date({"header": {}}), MEETING_DATE)


class PointInTimeWriteTest(unittest.TestCase):
    """write_meeting 一定要丟走喺場次日期當日或之後嘅往績。"""

    def _write(self, runs):
        parsed = {
            "meta": {"venue": "Flemington", "race_number": 5, "distance": 1410,
                     "track_condition": "Good"},
            "overview": {1: {"name": "Silent Shares", "fixed_win": "7.50"}},
            "runs": [], "text": "",
        }
        blocks = [{"name": "Silent Shares", "barrier": "10", "stats": {},
                   "runs": runs}]
        tmp = tempfile.mkdtemp()
        stats = write_meeting([(5, parsed, blocks)], tmp, MEETING_DATE,
                              "Flemington", verbose=False)
        fg = next(Path(tmp).glob("*Race 5 Formguide.md")).read_text(encoding="utf-8")
        return stats, fg

    def test_drops_the_race_being_predicted(self):
        stats, fg = self._write([_run("01/08/2026"), _run("15/07/2026")])
        self.assertEqual(stats["dropped"], 1)
        self.assertEqual(stats["kept"], 1)
        self.assertNotIn("2026-08-01", fg)
        self.assertIn("2026-07-15", fg)

    def test_drops_anything_after_the_meeting_too(self):
        stats, _ = self._write([_run("08/08/2026"), _run("15/07/2026")])
        self.assertEqual(stats["dropped"], 1)

    def test_keeps_a_clean_history_untouched(self):
        stats, fg = self._write([_run("15/07/2026"), _run("04/07/2026")])
        self.assertEqual(stats["dropped"], 0)
        self.assertEqual(len(RUN_LINE.findall(fg)), 2)

    def test_no_written_run_is_dated_on_or_after_the_meeting(self):
        """呢個係真正嘅不變式 —— 上面三個係佢嘅例子。"""
        _, fg = self._write([_run(d) for d in
                             ("01/08/2026", "31/07/2026", "15/07/2026",
                              "02/08/2026", "04/07/2026")])
        for m in RUN_LINE.finditer(fg):
            self.assertLess(m.group("date"), MEETING_DATE,
                            f"賽後洩漏：{m.group('date')}")


class RaceIdentityTest(unittest.TestCase):
    """場次一定要由頁面攞，唔可以靠 raceId 次序推。"""

    HTML = ("<html><head><title>Flemington Race 7</title></head><body>"
            "<div>Flemington Race 7</div><div>Track: Good 4</div>"
            "<div>1200m </div></body></html>")

    def test_reads_race_number_from_a_post_race_page(self):
        meta = parse_race(self.HTML)["meta"]
        self.assertEqual(meta.get("race_number"), 7)
        self.assertEqual(meta.get("venue"), "Flemington")
        self.assertEqual(meta.get("track_condition"), "Good 4")

    def test_start_time_is_optional(self):
        # 賽後頁面冇開跑時間；佢缺席唔可以令 race_number 變 None。
        self.assertIsNone(parse_race(self.HTML)["meta"].get("start"))

    def test_still_reads_a_pre_race_page_with_a_start_time(self):
        html = self.HTML.replace("<div>Flemington Race 7</div>",
                                 "<div>Flemington Race 7 - 14:30</div>")
        meta = parse_race(html)["meta"]
        self.assertEqual(meta.get("race_number"), 7)
        self.assertEqual(meta.get("start"), "14:30")

    def test_temperature_is_not_mistaken_for_track_grade(self):
        html = ("<html><head><title>Alice Springs Race 1</title></head><body>"
                "<span>Track: Good</span><span>25°C</span><div>1100m </div>"
                "</body></html>")
        self.assertEqual(parse_race(html)["meta"]["track_condition"], "Good")


if __name__ == "__main__":
    unittest.main()


class RefusalIsNotRetriedTests(unittest.TestCase):
    """一個穩定嘅攔截頁唔可以當 rate limit 嚟重試。

    2026-08-04：試抽 `?view=Speedmap` 攞到三個 HTTP 403，**長度完全一樣（919）**。
    Rate limit 退避之後行為會變；長度逐次一樣就係同一版攔截頁。條 fetcher 當時
    分唔開，所以喺人哋明講唔畀嘅時候再敲多兩次門 —— 而「非 200 就停低、
    唔重試」正正係抽取紀律嘅第一條。
    """

    def _fetcher(self, responses):
        import claw_sportsbet_form as C

        class _R:
            def __init__(self, code, text):
                self.status_code, self.text = code, text

        class _S:
            def __init__(self):
                self.calls = 0

            def get(self, url, timeout=None):
                r = responses[min(self.calls, len(responses) - 1)]
                self.calls += 1
                return _R(*r)

        f = C.SportsbetFormFetcher(delay=0.0, verbose=False,
                                   cache_dir=Path(tempfile.mkdtemp()))
        f.session = _S()
        return f

    def test_identical_refusal_twice_stops_immediately(self):
        f = self._fetcher([(403, "x" * 919)])
        self.assertIsNone(f.get("https://example.test/blocked/"))
        self.assertEqual(f.session.calls, 2, "第二次見到同一個攔截頁就要停")

    def test_a_varying_failure_still_uses_its_retries(self):
        """長度變化 = 可能係 rate limit／半截回應，嗰個先值得退避重試。"""
        f = self._fetcher([(403, "x" * 900), (429, "y" * 40), (503, "z" * 12)])
        self.assertIsNone(f.get("https://example.test/flaky/"))
        self.assertEqual(f.session.calls, 3)

    def test_success_after_a_transient_failure_is_kept(self):
        f = self._fetcher([(429, "y" * 40), (200, "o" * 6000)])
        self.assertEqual(len(f.get("https://example.test/ok/") or ""), 6000)
