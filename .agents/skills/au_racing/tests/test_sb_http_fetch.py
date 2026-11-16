"""sb_http_fetch：唔開瀏覽器攞 sportsbetform。唔連網，用假 session。

鎖住：被拒絕即停唔重試；被拒絕先轉 Chrome（網絡斷唔轉）；賽事頁寫 API 賠率 sidecar；
對唔上唯一一場就唔貼賠率；讀賠率 HTML 優先、sidecar 後備；`WC_SB_FETCH=browser` 行舊路。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import claw_sportsbet_form as C  # noqa: E402
import sb_browser_fetch  # noqa: E402
import sb_http_fetch as H  # noqa: E402

RACE = f"{C.BASE}/456227/3475113/"
PAGE = "<html><title>Scone Race 1</title>" + "x" * 6000 + "</html>"


class Resp:
    def __init__(self, status=200, text="", data=None):
        self.status_code, self.text, self._data = status, text, data

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, pages=None, api=None, raise_for=None):
        self.pages, self.api, self.raise_for, self.calls = pages or {}, api or {}, raise_for or {}, []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url in self.raise_for:
            raise self.raise_for[url]
        if url.startswith(H.API):
            return Resp(200, data=self.api.get(url[len(H.API):], {}))
        status, text = self.pages.get(url, (404, ""))
        return Resp(status, text)


ALLRACING = {"meetings": [{"name": "Scone", "events": [{"id": 111, "raceNumber": 1}, {"id": 112, "raceNumber": 2}]},
                          {"name": "Kyneton", "events": [{"id": 211, "raceNumber": 1}]}]}
RACECARD = {"racecardEvent": {"markets": [{"selections": [
    {"runnerNumber": 1, "isOut": True, "prices": [{"priceCode": "L", "winPrice": 3.0}]},
    {"runnerNumber": 2, "statusCode": "A", "prices": [{"priceCode": "L", "winPrice": 1.45, "placePrice": 1.13}]},
    {"runnerNumber": 3, "statusCode": "A", "prices": [{"priceCode": "NTL"}, {"priceCode": "L", "winPrice": 9.0}]},
]}]}}
API_OK = {"AllRacing/2026-11-17": ALLRACING, "Events/111/RacecardWithContext": RACECARD}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._cache = sb_browser_fetch.CACHE_DIR
        sb_browser_fetch.CACHE_DIR = Path(self.tmp.name) / "cache"
        self.mapping = Path(self.tmp.name) / "ids.json"
        self.mapping.write_text(json.dumps({"2026-11-17 Scone Race 1-8": {
            "date": "2026-11-17", "meetingId": "456227", "races": ["3475113"]}}))
        self.logs = []

    def tearDown(self):
        sb_browser_fetch.CACHE_DIR = self._cache
        self.tmp.cleanup()

    def fetcher(self, session):
        f = H.HttpFetcher(delay=0, session=session, mapping_path=self.mapping, log=self.logs.append)
        f.delay = 0          # 測試唔等 12 秒下限
        return f


class HttpFetcherTests(Base):
    def test_race_page_cached_and_odds_sidecar_written(self):
        s = FakeSession({RACE: (200, PAGE)}, API_OK)
        f = self.fetcher(s)
        self.assertEqual(f.get(RACE), PAGE)
        self.assertEqual(sb_browser_fetch.cache_path(RACE).read_text(), PAGE)
        doc = json.loads(H.odds_sidecar_path(RACE).read_text())
        self.assertEqual(doc["event_id"], "111")
        # 退出馬（isOut）唔寫；只收 L 價
        self.assertEqual(doc["odds"], {"2": {"Sportsbet-FixedWin": 1.45, "Sportsbet-FixedPlace": 1.13},
                                       "3": {"Sportsbet-FixedWin": 9.0}})
        self.assertEqual(C.cached_page_odds(sb_browser_fetch.cache_path(RACE)),
                         {2: {"Sportsbet-FixedWin": 1.45, "Sportsbet-FixedPlace": 1.13},
                          3: {"Sportsbet-FixedWin": 9.0}})
        n = len(s.calls)
        self.assertEqual(f.get(RACE), PAGE)                   # cache 有就唔出網
        self.assertEqual(len(s.calls), n)

    def test_refusal_stops_without_retry(self):
        other = f"{C.BASE}/456227/3475114/"
        s = FakeSession({RACE: (403, "denied")})
        f = self.fetcher(s)
        self.assertIsNone(f.get(RACE))
        self.assertIn("HTTP 403", f.stop_reason)
        self.assertIsNone(f.get(other))                       # 拒絕之後一個請求都唔再出
        self.assertEqual(s.calls, [RACE])

    def test_short_body_is_a_block_page(self):
        f = self.fetcher(FakeSession({RACE: (200, "tiny")}))
        self.assertIsNone(f.get(RACE))
        self.assertIn("攔截頁", f.stop_reason)
        self.assertFalse(sb_browser_fetch.cache_path(RACE).exists())

    def test_timeouts_trip_only_after_three_in_a_row(self):
        urls = [f"{C.BASE}/1{i}0000/2000000/" for i in range(3)]
        f = self.fetcher(FakeSession(raise_for={u: TimeoutError("timed out") for u in urls}))
        self.assertIsNone(f.get(urls[0]))
        self.assertIsNone(f.stop_reason)                      # 單版 timeout 唔跳掣
        f.get(urls[1])
        self.assertIsNone(f.stop_reason)
        f.get(urls[2])
        self.assertIn("timeout", f.stop_reason)

    def test_ambiguous_or_missing_race_gets_no_odds(self):
        api = {"AllRacing/2026-11-17": {"a": {"name": "Scone", "events": [{"id": 1, "raceNumber": 1}]},
                                        "b": {"name": "Scone", "events": [{"id": 2, "raceNumber": 1}]}}}
        f = self.fetcher(FakeSession({RACE: (200, PAGE)}, api))
        self.assertEqual(f.get(RACE), PAGE)                   # 頁照攞
        self.assertFalse(H.odds_sidecar_path(RACE).exists())  # 兩個候選 → 唔貼
        self.assertEqual(len(f.odds_missed), 1)

    def test_html_odds_win_over_sidecar(self):
        cache = sb_browser_fetch.cache_path(RACE)
        cache.parent.mkdir(parents=True)
        cache.write_text('<td data-number="04"><span data-key="9-Sportsbet-FixedWin" class="ppodds" '
                         'data-odds="5.5"></span></td>')
        H.odds_sidecar_path(RACE).write_text(json.dumps({"odds": {"4": {"Sportsbet-FixedWin": 9.9}}}))
        self.assertEqual(C.cached_page_odds(cache), {4: {"Sportsbet-FixedWin": 5.5}})


class FakeBrowser:
    def __init__(self):
        self.calls, self.requests_made, self.stop_reason = [], 0, None
        self.network_reason = self.launch_reason = self.last_page_error = None
        self.closed = False

    def get(self, url, force=False):
        self.calls.append(url)
        return "browser:" + url

    def close(self):
        self.closed = True


class HybridTests(Base):
    def test_falls_back_to_chrome_on_refusal_and_stays_there(self):
        other = f"{C.BASE}/456227/3475114/"
        s = FakeSession({RACE: (403, "no")})
        made = []
        hy = H.HybridFetcher(http=self.fetcher(s), browser_factory=lambda: made.append(FakeBrowser()) or made[0],
                             log=self.logs.append)
        self.assertEqual(hy.get(RACE), "browser:" + RACE)
        self.assertEqual(hy.get(other), "browser:" + other)
        self.assertEqual(s.calls, [RACE])                    # HTTP 被拒之後唔再試 HTTP
        self.assertIn("HTTP 403", hy.fallback_reason)
        self.assertIsNone(hy.stop_reason)                    # 而家睇嘅係 Chrome 嘅狀態
        hy.close()
        self.assertTrue(made[0].closed)

    def test_network_failure_does_not_open_chrome(self):
        s = FakeSession(raise_for={RACE: ConnectionError("dns")})
        http = self.fetcher(s)
        http._NETWORK_RETRIES = 0
        hy = H.HybridFetcher(http=http, browser_factory=lambda: self.fail("唔應該開 Chrome"),
                             log=self.logs.append)
        self.assertIsNone(hy.get(RACE))
        self.assertIsNotNone(hy.network_reason)
        self.assertIsNone(hy.stop_reason)

    def test_success_never_opens_chrome(self):
        hy = H.HybridFetcher(http=self.fetcher(FakeSession({RACE: (200, PAGE)}, API_OK)),
                             browser_factory=lambda: self.fail("唔應該開 Chrome"), log=self.logs.append)
        self.assertEqual(hy.get(RACE), PAGE)
        self.assertEqual(hy.requests_made, 1)

    def test_env_selects_old_browser_path(self):
        old = os.environ.get("WC_SB_FETCH")
        try:
            os.environ["WC_SB_FETCH"] = "browser"
            self.assertEqual(type(H.make_fetcher(delay=25, log=self.logs.append)).__name__, "BrowserFetcher")
            os.environ["WC_SB_FETCH"] = ""
            self.assertIsInstance(H.make_fetcher(delay=25, log=self.logs.append,
                                                 origin_candidates=["x"]), H.HybridFetcher)
        finally:
            if old is None:
                os.environ.pop("WC_SB_FETCH", None)
            else:
                os.environ["WC_SB_FETCH"] = old


if __name__ == "__main__":
    unittest.main()
