"""AU 每日排程 runner 嘅純函數測試。

呢度只測**判斷**，唔測抽取／評分／發佈（嗰啲已經有自己嘅 suite）。judgement
出錯嘅代價唔對稱：
  - 場地狀況 parse 錯 → 用錯 going 評分，靜靜咁錯。
  - 馬場配錯 → 拉一個馬場嘅場地狀況入另一個馬場。
  - snapshot 場次數數錯 → 「10 場」同「空馬場」睇落一樣，驗證形同虛設。
  - 「有冇實質變動」判斷錯 → 每晚無謂重評分，或者退出馬冇人理。
"""
from __future__ import annotations

import contextlib
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import au_daily_schedule as S  # noqa: E402


class TestGoing(unittest.TestCase):
    def test_api_and_page_formats(self):
        self.assertEqual(S.normalise_going("Soft (5)"), "Soft 5")
        self.assertEqual(S.normalise_going("Good 4"), "Good 4")
        self.assertEqual(S.normalise_going("heavy10"), "Heavy 10")
        self.assertEqual(S.normalise_going("Synthetic"), "Synthetic")

    def test_rubbish_is_empty_not_guessed(self):
        # 認唔到就要回空，唔可以亂猜 —— 落一個錯 going 落去評分，比冇 going 差。
        self.assertEqual(S.normalise_going(""), "")
        self.assertEqual(S.normalise_going(None), "")
        self.assertEqual(S.normalise_going("Unknown"), "")
        self.assertEqual(S.normalise_going("W"), "")


class TestVenueMatch(unittest.TestCase):
    AU = ["Belmont", "Canterbury", "Cranbourne", "Doomben", "Hobart",
          "Murray Bridge"]

    def test_exact_and_abbreviated(self):
        self.assertEqual(S.match_venue("belmont", self.AU), "Belmont")
        # 索引頁用縮寫，API 出全名。
        self.assertEqual(S.match_venue("murray_bdge", self.AU), "Murray Bridge")

    def test_abbreviations_on_either_side_still_match(self):
        # 2026-08-06 實測：索引頁出 `mount_isa`，API 出 `Mt Isa` —— 三步配對全部
        # 唔中，一個真澳洲場次被當海外剔走，靜靜咁冇分析。
        self.assertEqual(S.match_venue("mount_isa", ["Mt Isa", "Gosford"]), "Mt Isa")
        self.assertEqual(S.match_venue("mt_isa", ["Mount Isa"]), "Mount Isa")
        self.assertEqual(S.match_venue("saint_arnaud", ["St Arnaud"]), "St Arnaud")

    def test_overseas_meetings_are_rejected(self):
        # 2026-08-05 索引頁 12 個場次，一半係英國／愛爾蘭／南非／加拿大。
        # 2026-08-06 索引頁嗰批：kempton / newmarket / sligo / vaal / yarmouth
        for slug in ("lingfield", "pontefract", "roscommon", "kenilworth",
                     "brighton", "assiniboia_downs", "kempton", "newmarket",
                     "sligo", "vaal", "yarmouth"):
            self.assertIsNone(S.match_venue(slug, self.AU), slug)

    def test_ambiguous_prefix_is_not_guessed(self):
        self.assertIsNone(S.match_venue("rand", ["Randwick", "Randwick Kensington"]))


class TestSnapshotShape(unittest.TestCase):
    def test_counts_races_not_dict_keys(self):
        # `races[key]` 係 {"meeting":…, "races_by_analyst":…}。當佢係 list 去
        # len() 嘅話,每個場次都會數到 2。
        entry = {"meeting": {}, "races_by_analyst": {
            "Kelvin": [{"race_number": 1}, {"race_number": 2}, {"race_number": 3}]}}
        self.assertEqual(S.race_numbers_in_snapshot(entry), ["1", "2", "3"])

    def test_empty_and_malformed(self):
        self.assertEqual(S.race_numbers_in_snapshot(None), [])
        self.assertEqual(S.race_numbers_in_snapshot([]), [])
        self.assertEqual(S.race_numbers_in_snapshot({"races_by_analyst": {}}), [])

    def test_signature_ignores_generated_at(self):
        base = {"meetings": [{"date": "2026-08-05", "venue": "Hobart"}],
                "races": {"2026-08-05|Hobart": {
                    "races_by_analyst": {"Kelvin": [{"race_number": 1}]}}}}
        a = dict(base, meta={"generated_at": "2026-08-05T01:00:00"})
        b = dict(base, meta={"generated_at": "2026-08-05T09:00:00"})
        self.assertEqual(S.snapshot_signature(a), S.snapshot_signature(b))

    def test_signature_notices_a_rescore_that_reorders_picks(self):
        # 2026-08-05 早更：場地 Soft 6→Soft 5、兩隻退出、排名改咗，但場次同場號
        # 一個都冇變。舊指紋話「冇變」，於是重評分嘅成果發佈唔上去。
        def snap(picks, going):
            return {"meetings": [], "races": {"k": {"races_by_analyst": {"Kelvin": [
                {"race_number": 1, "going": going, "top_picks": picks}]}}}}
        a = snap([{"rank": 1, "horse_number": 6, "grade": "B"}], "Soft 6")
        b = snap([{"rank": 1, "horse_number": 3, "grade": "A"}], "Soft 5")
        self.assertNotEqual(S.snapshot_signature(a), S.snapshot_signature(b))
        self.assertEqual(S.snapshot_signature(a), S.snapshot_signature(snap(
            [{"rank": 1, "horse_number": 6, "grade": "B"}], "Soft 6")))

    def test_signature_notices_a_new_race(self):
        a = {"meetings": [], "races": {"k": {"races_by_analyst": {"K": [{"race_number": 1}]}}}}
        b = {"meetings": [], "races": {"k": {"races_by_analyst": {
            "K": [{"race_number": 1}, {"race_number": 2}]}}}}
        self.assertNotEqual(S.snapshot_signature(a), S.snapshot_signature(b))


class TestArchiveKey(unittest.TestCase):
    def test_folder_name_to_dashboard_key(self):
        self.assertEqual(
            S.archive_dashboard_key("2026-08-01 Rosehill Gardens Race 1-10"),
            "2026-08-01|Rosehill Gardens")
        self.assertEqual(S.archive_dashboard_key("2026-03-28 Flemington"),
                         "2026-03-28|Flemington")


def _state(going="Good 4", jockeys=None, barriers=None, field=None):
    jockeys = jockeys if jockeys is not None else {"1": "A Smith", "2": "B Jones"}
    barriers = barriers if barriers is not None else {"1": "3", "2": "7"}
    field = field if field is not None else sorted(jockeys)
    return {"going": going, "jockeys": jockeys, "barriers": barriers,
            "field": field, "scratched": []}


class TestMaterialChange(unittest.TestCase):
    def test_no_change_means_no_rescore(self):
        stored = {1: _state()}
        self.assertEqual(S.diff_race_state(stored, {1: _state()}), {})

    def test_scratching(self):
        live = {1: _state(jockeys={"1": "A Smith"}, barriers={"1": "3"})}
        delta = S.diff_race_state({1: _state()}, live)[1]
        self.assertEqual(delta["scratchings"], ["2"])
        self.assertEqual(delta["field_size"], [2, 1])

    def test_emergency_gaining_a_start(self):
        live = {1: _state(jockeys={"1": "A Smith", "2": "B Jones", "3": "C Lee"},
                          barriers={"1": "3", "2": "7", "3": "9"})}
        self.assertEqual(S.diff_race_state({1: _state()}, live)[1]["emergencies_in"],
                         ["3"])

    def test_jockey_and_barrier_swap(self):
        live = {1: _state(jockeys={"1": "A Smith", "2": "Z Brown"},
                          barriers={"1": "3", "2": "1"})}
        delta = S.diff_race_state({1: _state()}, live)[1]
        self.assertEqual(delta["jockeys"], {"2": ["B Jones", "Z Brown"]})
        self.assertEqual(delta["barriers"], {"2": ["7", "1"]})

    def test_going_upgrade(self):
        live = {1: _state(going="Soft 6")}
        self.assertEqual(S.diff_race_state({1: _state()}, live)[1]["going"],
                         ["Good 4", "Soft 6"])

    def test_blank_live_going_is_not_a_change(self):
        # 攞唔到場地狀況 ≠ 場地狀況變咗。空值唔應該觸發重評分。
        self.assertEqual(S.diff_race_state({1: _state()}, {1: _state(going="")}), {})

    def test_race_missing_from_stored_is_skipped(self):
        self.assertEqual(S.diff_race_state({}, {9: _state()}), {})


class _FakeAcquire:
    """認得頭 N 版，之後一律拒絕（模擬 sportsbetform 穩定 403）。

    模仿真 `fetch_page` 嘅合約：拒絕嗰下會 trip circuit breaker。
    """

    def __init__(self, allow: int, cached: set[str] | None = None):
        self.allow = allow
        self.cached = cached or set()
        self.requests: list[str] = []

    def cache_path(self, url):
        hit = any(url.endswith(f"/{r}/") for r in self.cached)

        class _P:
            def exists(self_inner):
                return hit
        return _P()

    def fetch_page(self, runlog, url, force=False, where=""):
        if runlog.site_refusing:
            return None
        self.requests.append(url)
        if len(self.requests) <= self.allow:
            return "<html>"
        runlog.trip_site_gate(where or url)
        return None


class TestSiteCircuitBreaker(unittest.TestCase):
    """個站明確拒絕之後就唔應該再敲門 —— 逐場敲落去會延長封鎖。"""

    def _runlog(self):
        import tempfile
        from datetime import date as _date
        tmp = Path(tempfile.mkdtemp()) / "run.json"
        return S.RunLog("test", _date(2026, 8, 5), tmp)

    @contextlib.contextmanager
    def _patched(self, fake):
        import sb_browser_fetch
        real_fetch, real_cache = S.fetch_page, sb_browser_fetch.cache_path
        S.fetch_page = fake.fetch_page
        sb_browser_fetch.cache_path = fake.cache_path
        try:
            yield
        finally:
            S.fetch_page = real_fetch
            sb_browser_fetch.cache_path = real_cache

    def test_stops_at_first_stable_refusal(self):
        runlog = self._runlog()
        fake = _FakeAcquire(allow=2)
        with self._patched(fake):
            ready = S.warm_race_pages(runlog, "446502",
                                      ["1", "2", "3", "4", "5", "6", "7"], "test")
        self.assertEqual(ready, ["1", "2"])
        # 拒絕之後**唔可以**再打 4 個請求。
        self.assertEqual(len(fake.requests), 3)
        self.assertTrue(runlog.site_refusing)

    def test_cached_pages_cost_nothing(self):
        runlog = self._runlog()
        fake = _FakeAcquire(allow=0, cached={"1", "2", "3"})
        with self._patched(fake):
            ready = S.warm_race_pages(runlog, "446502", ["1", "2", "3"], "test")
        self.assertEqual(ready, ["1", "2", "3"])
        self.assertEqual(fake.requests, [])
        self.assertFalse(runlog.site_refusing)

    def test_gate_short_circuits_later_meetings(self):
        runlog = self._runlog()
        runlog.trip_site_gate("earlier meeting")
        fake = _FakeAcquire(allow=99)
        with self._patched(fake):
            ready = S.warm_race_pages(runlog, "446511", ["1", "2"], "test")
        self.assertEqual(ready, [])
        self.assertEqual(fake.requests, [])


class TestBrowserOnlyInvariants(unittest.TestCase):
    """「只行真瀏覽器」要靠兩個不變式撐住，唔係靠記得。

    2026-08-05 實測 sportsbetform：curl_cffi 403、headless Chrome（連真 Chrome
    嘅 headless）都 403、只有 headed 真 Chrome 200。所以任何一段 Python 出網都係
    敲一道明講唔得嘅門 —— 攞唔到嘢，仲會延長封鎖。
    """

    def test_cache_only_env_blocks_every_python_fetch(self):
        import tempfile
        sys.path.insert(0, str(HERE.parents[1]))
        import claw_sportsbet_form as claw
        with tempfile.TemporaryDirectory() as tmp:
            f = claw.SportsbetFormFetcher(delay=0, cache_dir=tmp, verbose=False,
                                          cache_only=True)
            # cache miss + cache_only → 直接 None，一個請求都唔會出。
            self.assertIsNone(f.get("https://www.sportsbetform.com.au/1/2/"))
            # cache hit 仍然要讀得返。
            path = f._cache_path("https://www.sportsbetform.com.au/3/4/")
            path.write_text("<html>cached</html>", encoding="utf-8")
            self.assertEqual(f.get("https://www.sportsbetform.com.au/3/4/"),
                             "<html>cached</html>")

    def test_run_cmd_forces_cache_only_on_every_subprocess(self):
        # 唔可以靠逐個 call site 記得傳 —— 一個漏咗就靜靜咁出網。
        captured = {}
        import subprocess as sp
        real = sp.run

        def fake_run(cmd, **kwargs):
            captured.update(kwargs.get("env") or {})

            class _R:
                returncode = 0
                stdout = ""
            return _R()

        sp.run = fake_run
        try:
            S.run_cmd(["/usr/bin/true"])
        finally:
            sp.run = real
        self.assertEqual(captured.get("WC_SB_CACHE_ONLY"), "1")


class TestScratchingsMustRebuildTheField(unittest.TestCase):
    """退出馬唔可以只靠重評分 —— 一定要重寫 Racecard 再落 Facts/Logic。

    2026-08-05 實測：早更偵測到 Canterbury 7 場共 24 隻退出馬，但只跑
    `au_auto_orchestrator`（由現有 Logic 重算），於是 R2 #6 Blenheim Girl 退出咗
    仍然排第二。退出馬係喺 `write_meeting` 寫 `status:Scratched` 嗰層剔走嘅。
    """

    def test_field_level_fields_are_classified(self):
        for field in ("scratchings", "emergencies_in", "barriers", "jockeys",
                      "field_size"):
            self.assertIn(field, S.FIELD_LEVEL_CHANGES, field)
        # 只係場地變就唔應該觸發成套重建（貴好多）。
        self.assertNotIn("going", S.FIELD_LEVEL_CHANGES)

    def test_refresh_rebuilds_on_field_change_and_rescores_on_going_only(self):
        import inspect
        src = inspect.getsource(S.refresh_one_meeting)
        self.assertIn("FIELD_LEVEL_CHANGES", src)
        self.assertIn("rebuild_meeting_from_cache", src)
        # 只有 going 變嗰條路仍然行純重評分。
        self.assertIn("AU_AUTO_ORCH", src)

    def test_rebuild_rewrites_racecard_before_rebuilding_logic(self):
        import inspect
        src = inspect.getsource(S.rebuild_meeting_from_cache)
        claw_at = src.index("CLAW")
        orch_at = src.index("AU_ORCH")
        self.assertLess(claw_at, orch_at,
                        "一定要先重寫 Racecard，再重建 Facts/Logic")

    def test_venue_from_folder(self):
        self.assertEqual(S.venue_from_folder("2026-08-05 Murray Bridge Race 1-8"),
                         "Murray Bridge")
        self.assertEqual(S.venue_from_folder("2026-03-28 Flemington"), "Flemington")


class TestResultsRefreshDecision(unittest.TestCase):
    """「要唔要重抓賽果頁」一定要睇覆蓋率，唔可以睇「賽果檔存唔存在」。

    半份賽果檔（晚更跑嗰陣最後一場仲未跑完）會令舊寫法之後每次都跳過重抓、
    由同一份舊 cache 重建同一份半份賽果 —— 場次永遠 partial_results、永遠唔會
    歸檔、永遠留喺 dashboard。
    """

    def _review_source(self):
        import inspect
        return inspect.getsource(S.review_one_meeting)

    def test_does_not_gate_refresh_on_file_existence(self):
        src = self._review_source()
        self.assertNotIn("if not results.exists():\n            refresh", src)

    def test_refresh_is_gated_on_coverage(self):
        src = self._review_source()
        self.assertIn("len(covered) < len(expected)", src)
        # 重抓之後一定要再 build 一次，否則覆蓋率永遠唔會更新。
        after = src.split("len(covered) < len(expected)", 1)[1]
        self.assertIn("refresh_result_pages", after)
        self.assertIn("build_results_file", after)


class TestBrowserFetchesRenderedDom(unittest.TestCase):
    """一定要 cache render 後嘅 DOM，唔可以係 raw body。

    賠率由 `OddsAgent.min.js` 填，raw body 永遠冇 —— 所以 2026-08-05 之前每個
    Formguide 都寫 `Flucs:$- $-`。實測 raw vs rendered 對所有其他 parser 輸出
    完全一致，所以呢個切換零代價。
    """

    def test_get_uses_goto_and_waits_for_render(self):
        import inspect
        sys.path.insert(0, str(HERE.parents[1]))
        from sb_browser_fetch import BrowserFetcher
        src = inspect.getsource(BrowserFetcher.get)
        self.assertIn("page.goto", src)
        self.assertIn("render_wait_ms", src)
        self.assertIn("page.content()", src)
        # in-page fetch 已經退役 —— 佢攞 raw body，冇賠率。
        self.assertNotIn("_FETCH_JS", src)

    def test_origin_page_no_longer_required(self):
        # `goto` 唔受同源限制，所以舊嗰個「同源起始頁」機制冇用咗，
        # 亦順手省咗每個 run 一個請求。舊 caller 傳 origin_* 唔應該炸。
        from sb_browser_fetch import BrowserFetcher
        bf = BrowserFetcher(origin_url="https://example.invalid/",
                            origin_candidates=["https://example.invalid/x/"])
        self.assertFalse(hasattr(bf, "origin_candidates"))


class TestPartialMeetingResumes(unittest.TestCase):
    """半份抽取一定要當「未做完」，否則餘下嘅場次永遠冇人補。"""

    def test_full_meeting_is_complete(self):
        self.assertTrue(S.meeting_is_complete(list(range(1, 10)),
                                              list(range(1, 10)), 9))

    def test_one_of_nine_is_not_complete(self):
        # 2026-08-05 Hobart：抽到 1 場就俾個站拒絕。
        self.assertFalse(S.meeting_is_complete([1], [1], 9))

    def test_pages_without_scores_is_not_complete(self):
        self.assertFalse(S.meeting_is_complete(list(range(1, 10)), [], 9))

    def test_more_than_expected_still_complete(self):
        # 索引偶爾少報一場，多過預期唔應該當未做完。
        self.assertTrue(S.meeting_is_complete([1, 2, 3], [1, 2, 3], 2))

    def test_zero_expected_is_never_complete(self):
        self.assertFalse(S.meeting_is_complete([], [], 0))


class TestFetchPacing(unittest.TestCase):
    def test_floor_is_enforced(self):
        import os
        previous = os.environ.get("WC_AU_FETCH_DELAY")
        try:
            os.environ["WC_AU_FETCH_DELAY"] = "1"
            # 12 秒下限係實測出嚟嘅，唔可以由 env 調到更快。
            self.assertGreaterEqual(S.fetch_delay(), S.MIN_FETCH_DELAY)
            os.environ["WC_AU_FETCH_DELAY"] = "40"
            self.assertEqual(S.fetch_delay(), 40.0)
            os.environ["WC_AU_FETCH_DELAY"] = "rubbish"
            self.assertEqual(S.fetch_delay(), S.DEFAULT_FETCH_DELAY)
        finally:
            if previous is None:
                os.environ.pop("WC_AU_FETCH_DELAY", None)
            else:
                os.environ["WC_AU_FETCH_DELAY"] = previous


if __name__ == "__main__":
    unittest.main()
