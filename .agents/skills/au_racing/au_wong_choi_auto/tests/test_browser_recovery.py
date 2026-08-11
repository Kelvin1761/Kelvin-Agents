#!/usr/bin/env python3
"""瀏覽器自己死咗 ≠ 個站拒絕。

2026-08-08 晚更：Chrome 開足 15 分鐘後個 page 死咗，`page.goto` 拋
`TargetClosedError`。個 fetcher 把佢記成 stop_reason，上層 circuit breaker 於是
報「個站明確拒絕（穩定非 200）」、放棄埋餘下五個 08-09 場次、退避 38 分鐘、
最後成個賽日流失 —— 而 Sportsbet 由頭到尾冇回過一個非 200。

一個本機故障扮成遠端封鎖，會令應對完全相反：真封鎖要收手，瀏覽器死要重開。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

AU = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AU))

from sb_browser_fetch import BrowserFetcher  # noqa: E402


class _Dead(Exception):
    pass


class TargetClosedError(Exception):
    pass


class BrowserDeathClassificationTests(unittest.TestCase):
    def test_target_closed_is_browser_death(self):
        exc = TargetClosedError(
            "Page.goto: Target page, context or browser has been closed")
        self.assertTrue(BrowserFetcher._is_browser_death(exc))

    def test_renderer_crash_is_browser_death(self):
        self.assertTrue(BrowserFetcher._is_browser_death(_Dead("Target crashed")))

    def test_a_real_refusal_is_not_browser_death(self):
        # HTTP 403 / 攔截頁行另一條路，唔可以被當成「重開就得」。
        self.assertFalse(BrowserFetcher._is_browser_death(_Dead("HTTP 403 forbidden")))

    def test_a_timeout_is_not_browser_death(self):
        # timeout 唔重開 —— 重開一個健康瀏覽器解決唔到慢頁，只會多敲一次門。
        self.assertFalse(BrowserFetcher._is_browser_death(_Dead("Timeout 90000ms exceeded")))


class RecycleTests(unittest.TestCase):
    def test_recycle_clears_the_handles_so_the_next_call_relaunches(self):
        bf = BrowserFetcher.__new__(BrowserFetcher)
        closed = []

        class _Obj:
            def close(self_inner): closed.append("closed")

        class _PW:
            def stop(self_inner): closed.append("stopped")

        bf._page, bf._ctx, bf._pw = _Obj(), _Obj(), _PW()
        bf._recycle()
        self.assertEqual(closed, ["closed", "closed", "stopped"])
        self.assertIsNone(bf._page)
        self.assertIsNone(bf._ctx)
        self.assertIsNone(bf._pw)

    def test_recycle_survives_handles_that_are_already_dead(self):
        # 個 page 已經死咗嘅時候 close() 自己都會拋 —— 唔可以喺清理途中炸。
        bf = BrowserFetcher.__new__(BrowserFetcher)

        class _Boom:
            def close(self_inner): raise TargetClosedError("already closed")
            def stop(self_inner): raise TargetClosedError("already closed")

        bf._page, bf._ctx, bf._pw = _Boom(), _Boom(), _Boom()
        bf._recycle()
        self.assertIsNone(bf._page)


class ProactiveRecycleTests(unittest.TestCase):
    """重開得返嚟係好事，但唔死一開始更好。

    2026-08-08 兩次死亡分別喺開機後約 30 版同約 64 版，而部機得 8 GB 實體記憶體、
    swap 用咗 5,721/7,168 MB，Chrome 一個 crash 報告都冇 —— 即係俾系統喺記憶體
    壓力下收走。所以抽夠一定版數就自己重開，唔等佢死。
    """

    def _fetcher(self):
        bf = BrowserFetcher.__new__(BrowserFetcher)
        bf._page = object()
        bf._ctx = bf._pw = None
        bf._since_launch = 0
        bf.log = lambda *a, **k: None
        return bf

    def test_counter_resets_on_recycle(self):
        bf = self._fetcher()
        bf._since_launch = 99
        bf._recycle()
        self.assertEqual(bf._since_launch, 0)
        self.assertIsNone(bf._page)

    def test_threshold_is_a_positive_bound(self):
        # 0 或者負數會令每一版都重開，慢到抽唔完一個場次。
        self.assertGreater(BrowserFetcher._RECYCLE_EVERY, 0)

    def test_threshold_is_below_the_observed_death_points(self):
        # 實測死亡點約 30 同約 64 版 —— 封頂一定要喺兩者之下先有預防作用。
        self.assertLess(BrowserFetcher._RECYCLE_EVERY, 30)


if __name__ == "__main__":
    unittest.main()


class NetworkBlipTests(unittest.TestCase):
    """本機網絡斷 ≠ 個站拒絕。

    2026-08-11 晚更：WiFi 中途變咗，Chrome 拋 `net::ERR_NETWORK_CHANGED`。舊 code
    當成「個站明確拒絕」trip circuit breaker，六個 08-12 場次得一個抽到，其餘五個
    全部放棄。同 08-08 `TargetClosedError` 一模一樣嘅誤判 —— 本機故障扮成遠端封鎖，
    而兩者應對相反：真封鎖要收手，網絡斷要等一等再試。
    """

    def test_chrome_network_errors_are_recognised(self):
        for msg in ("Page.goto: net::ERR_NETWORK_CHANGED at https://x",
                    "net::ERR_INTERNET_DISCONNECTED",
                    "net::ERR_CONNECTION_RESET",
                    "net::ERR_NAME_NOT_RESOLVED",
                    "net::ERR_CONNECTION_TIMED_OUT"):
            self.assertTrue(BrowserFetcher._is_network_blip(_Dead(msg)), msg)

    def test_a_real_refusal_is_not_a_network_blip(self):
        # 403 同攔截頁要照樣收手 —— 唔可以無限重試一個真封鎖。
        for msg in ("HTTP 403 Forbidden", "只有 812 bytes（當攔截頁）"):
            self.assertFalse(BrowserFetcher._is_network_blip(_Dead(msg)), msg)

    def test_browser_death_and_network_blip_are_separate_categories(self):
        # 兩者應對唔同：一個要重開瀏覽器，一個要等網絡返嚟。
        dead = _Dead("TargetClosedError: page has been closed")
        net = _Dead("net::ERR_NETWORK_CHANGED")
        self.assertTrue(BrowserFetcher._is_browser_death(dead))
        self.assertFalse(BrowserFetcher._is_network_blip(dead))
        self.assertTrue(BrowserFetcher._is_network_blip(net))

    def test_backoff_grows_and_is_bounded(self):
        self.assertGreaterEqual(BrowserFetcher._NETWORK_RETRIES, 2)
        self.assertGreaterEqual(BrowserFetcher._NETWORK_BACKOFF, 10)
