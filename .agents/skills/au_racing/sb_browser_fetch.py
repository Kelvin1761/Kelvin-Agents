#!/usr/bin/env python3
"""由真瀏覽器 session 攞 sportsbetform 頁面，寫落同一個 cache。

**點解只可以行真瀏覽器**（2026-08-05 實測，同一時間同一個 IP）：

| 方式 | `/{date}/` 索引頁 | 賽事頁 |
|---|---|---|
| curl_cffi (`impersonate="chrome120"`) | 403 | 一個冷卻窗大約 8 版之後 403 |
| Playwright bundled chromium, headless | 403 | — |
| Playwright **真 Chrome**, `headless=True` | **403** | — |
| Playwright **真 Chrome**, `headless=False` | **200** | 200 |

所以被偵測嘅係 **headless 本身**，唔係邊個 Chrome、亦唔係 IP。結論：
`channel="chrome"` + `headless=False` + persistent profile 係唯一穩定路徑。
實測舊 bridge loop 用真瀏覽器 10 秒一版連續幾百版零 403，而 curl_cffi 25 秒都被封 ——
真瀏覽器唔止唔會被封，實際上比 curl_cffi 又快又穩。

⚠️ 呢個唔係用嚟繞過偵測。我哋照守原本嘅規則：保守節奏、撞到任何非 200 即刻停低
唔重試。**唔會**加任何目的係擊敗 bot detection 嘅嘢（唔改 `navigator.webdriver`、
唔用 `--disable-blink-features=AutomationControlled`、唔輪換 fingerprint / UA / proxy）。
Headed 真 Chrome 係「用個站本來 serve 緊嘅方式去讀」，上面嗰啲唔係。

⚠️ 一定要 headed，所以要有 active GUI login session（鎖住螢幕冇問題，登出就唔得），
而且每次跑會彈一個 Chrome 窗。呢個係 browser-only 換返嚟嘅代價。

做法：開一次 persistent context → navigate 去**同源**一版（索引頁）→ 之後逐個 URL
喺 page 裏面 `fetch()` 攞 raw HTML。要 raw HTML 而唔係 `page.content()`：下游全部
parser 都係食原始 markup 嘅 regex，serialize 過嘅 DOM 未必對得上。

用法：
    with BrowserFetcher(delay=25, origin_url=f"{BASE}/2026-08-05/") as bf:
        html = bf.get(f"{BASE}/446508/3396067/")          # cache 有就唔出網
        html = bf.get(url, force=True)                    # 賽後重抓，覆蓋 cache
        if bf.stop_reason: ...                            # 個站拒絕過
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claw_sportsbet_form import BASE, CACHE_DIR  # noqa: E402

MIN_BYTES = 5000          # 同 fetcher / bridge 一致 —— 細過呢個多數係攔截頁
DEFAULT_PROFILE = Path(os.environ.get("WC_SB_BROWSER_PROFILE", "")) \
    if os.environ.get("WC_SB_BROWSER_PROFILE") \
    else Path.home() / ".cache" / "wongchoi" / "sb_chrome_profile"

# 喺 page 裏面攞 raw body。回 [status, text] —— 唔喺 JS 度做判斷，交返 Python。
_FETCH_JS = """
async (url) => {
  const r = await fetch(url, { credentials: 'include' });
  const t = await r.text();
  return [r.status, t];
}
"""


class BrowserRefused(RuntimeError):
    """個站明確拒絕（非 200 或者攔截頁）。唔應該重試。"""


def cache_path(url: str) -> Path:
    """一定要同 `SportsbetFormFetcher._cache_path` 完全一樣，否則寫咗攞唔返。"""
    import hashlib
    return Path(CACHE_DIR) / (hashlib.sha1(url.encode()).hexdigest() + ".html")


class BrowserFetcher:
    def __init__(self, delay: float = 25.0, origin_url: str | None = None,
                 profile_dir: Path | None = None, verbose: bool = True,
                 log=None):
        self.delay = max(float(delay), 12.0)
        self.origin_url = origin_url or f"{BASE}/"
        self.profile_dir = Path(profile_dir or DEFAULT_PROFILE)
        self.verbose = verbose
        self.log = log or (lambda m: print(f"   {m}", flush=True))
        self.requests_made = 0
        self.stop_reason: str | None = None
        self._pw = None
        self._ctx = None
        self._page = None
        self._last_request = 0.0

    # -- lifecycle --------------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False

    def close(self) -> None:
        for closer in (getattr(self._ctx, "close", None),
                       getattr(self._pw, "stop", None)):
            try:
                if closer:
                    closer()
            except Exception:  # noqa: BLE001 — 收工失敗唔應該蓋過真正嘅結果
                pass
        self._ctx = self._page = self._pw = None

    def _launch(self):
        # ⚠️ `channel="chrome"` = 系統裝嘅真 Chrome；`headless=False` 唔可以改。
        # 兩者任何一樣走轉頭都會變 403（實測）。
        return self._pw.chromium.launch_persistent_context(
            str(self.profile_dir), channel="chrome", headless=False,
            viewport={"width": 1280, "height": 900},
            args=["--window-size=1280,900"])

    def _clear_stale_profile_lock(self) -> bool:
        """上一次 run 硬死留低嘅 Chrome 會鎖住 profile，下次點都開唔到。

        只殺**用我哋自己個 profile 目錄**嘅 process（路徑獨一無二），唔會碰
        Kelvin 自己嗰個 Chrome。冇呢一步，一次硬死就會令之後每晚都靜靜咁失敗。
        """
        import subprocess
        try:
            done = subprocess.run(["pkill", "-f", str(self.profile_dir)],
                                  capture_output=True, timeout=20)
        except Exception:  # noqa: BLE001
            return False
        killed = done.returncode == 0
        if killed:
            self.log(f"🧹 清走上次留低嘅 Chrome（profile {self.profile_dir.name}）")
            time.sleep(3)
        return killed

    def _ensure_page(self):
        """開瀏覽器 + 落一版同源頁。同源係 `fetch()` 嘅前提。"""
        if self._page is not None:
            return self._page
        from playwright.sync_api import sync_playwright
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        try:
            self._ctx = self._launch()
        except Exception as exc:  # noqa: BLE001
            self.log(f"⚠️ 開唔到（{type(exc).__name__}: {str(exc)[:120]}）—— "
                     f"試清 profile lock 之後再開一次")
            if not self._clear_stale_profile_lock():
                raise
            self._ctx = self._launch()
        self._page = self._ctx.new_page()
        if self.verbose:
            self.log(f"🌐 真 Chrome 已開（profile {self.profile_dir}）")
        self._pace()
        response = self._page.goto(self.origin_url, timeout=90000,
                                   wait_until="domcontentloaded")
        self.requests_made += 1
        self._last_request = time.time()
        status = response.status if response else None
        if status != 200:
            self.stop_reason = f"同源起始頁 HTTP {status}：{self.origin_url}"
            raise BrowserRefused(self.stop_reason)
        if self.verbose:
            self.log(f"✅ 同源起始頁 {self.origin_url}")
        return self._page

    def _pace(self) -> None:
        wait = self.delay - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)

    # -- fetching ---------------------------------------------------------
    def get(self, url: str, force: bool = False) -> str | None:
        """回 HTML；cache 有而且唔 force 就唔出網。拒絕回 None 並記 `stop_reason`。

        ⚠️ `force=True` 係賽後重抓用嘅：賽前落嘅同一條 URL 冇賽果行，靠 cache
        讀永遠都係「未跑」。
        """
        target = cache_path(url)
        if not force and target.exists():
            if self.verbose:
                self.log(f"（cache）{url}")
            return target.read_text(encoding="utf-8")
        if self.stop_reason:
            return None
        if not url.startswith(BASE):
            raise ValueError(f"只可以攞 {BASE} 嘅頁：{url}")

        try:
            page = self._ensure_page()
        except BrowserRefused:
            return None
        except Exception as exc:  # noqa: BLE001 — 開唔到瀏覽器 = 今次做唔到
            self.stop_reason = f"開唔到真 Chrome（{type(exc).__name__}: {exc}）"
            self.log(f"⛔ {self.stop_reason}")
            return None

        self._pace()
        try:
            status, text = page.evaluate(_FETCH_JS, url)
        except Exception as exc:  # noqa: BLE001
            self.stop_reason = f"page.fetch 失敗（{type(exc).__name__}: {exc}）"
            self.log(f"⛔ {self.stop_reason}")
            return None
        finally:
            self.requests_made += 1
            self._last_request = time.time()

        if status != 200:
            # 撞到任何非 200 就即刻停，唔重試 —— 個站話唔得就收工。
            self.stop_reason = f"HTTP {status} {url}"
            self.log(f"⛔ {self.stop_reason} —— 停低唔重試")
            return None
        if len(text) < MIN_BYTES:
            self.stop_reason = f"只有 {len(text)} bytes（當攔截頁）{url}"
            self.log(f"⛔ {self.stop_reason} —— 停低唔重試")
            return None

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        if self.verbose:
            self.log(f"✅ {len(text):,} bytes  {url}")
        return text


def main() -> int:
    """細測：攞一版索引頁。`python3 sb_browser_fetch.py 2026-08-05`"""
    import argparse
    ap = argparse.ArgumentParser(description="真瀏覽器攞 sportsbetform 頁面")
    ap.add_argument("day", help="YYYY-MM-DD")
    ap.add_argument("--delay", type=float, default=25.0)
    args = ap.parse_args()
    url = f"{BASE}/{args.day}/"
    with BrowserFetcher(delay=args.delay, origin_url=url) as bf:
        html = bf.get(url, force=True)
    if not html:
        print(f"❌ {bf.stop_reason}")
        return 1
    from claw_sportsbet_form import parse_date_index
    index = parse_date_index(html)
    print(f"✅ {len(html):,} bytes、{len(index)} 個場次")
    for slug, meta in sorted(index.items()):
        print(f"   {slug:22} mid={meta['meetingId']:>8} races={len(meta['races'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
