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

做法：開一次 persistent context，之後逐個 URL `page.goto()` → 等 JS 填完 →
`page.content()` 攞**render 後**嘅 DOM 落 cache。

⚠️ 一定要 render 後嘅 DOM，唔可以用 in-page `fetch()` 攞 raw body：賠率由
`OddsAgent.min.js` 填，raw body 永遠冇（所以 2026-08-05 之前每個 Formguide 都寫
`Flucs:$- $-`）。實測 raw vs rendered 對所有其他 parser 輸出**完全一致**
（同一版 19 匹、142 條往績、8 個 coverage 指標全部相同），所以呢個切換零代價。

用法：
    with BrowserFetcher(delay=25) as bf:
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

class BrowserRefused(RuntimeError):
    """個站明確拒絕（非 200 或者攔截頁）。唔應該重試。"""


def cache_path(url: str) -> Path:
    """一定要同 `SportsbetFormFetcher._cache_path` 完全一樣，否則寫咗攞唔返。"""
    import hashlib
    return Path(CACHE_DIR) / (hashlib.sha1(url.encode()).hexdigest() + ".html")


class BrowserFetcher:
    def __init__(self, delay: float = 25.0, profile_dir: Path | None = None,
                 verbose: bool = True, log=None, render_wait_ms: int = 5000,
                 **_ignored):
        # `**_ignored` 收走舊 caller 傳嘅 origin_url / origin_candidates ——
        # `goto` 唔受同源限制，所以起始頁機制已經冇用（以前係為咗 in-page fetch）。
        self.delay = max(float(delay), 12.0)
        self.render_wait_ms = int(render_wait_ms)
        self.profile_dir = Path(profile_dir or DEFAULT_PROFILE)
        self.verbose = verbose
        self.log = log or (lambda m: print(f"   {m}", flush=True))
        self.requests_made = 0
        self.stop_reason: str | None = None
        self._since_launch = 0
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

    def _profile_in_use(self) -> bool:
        """有另一個**活住**嘅 process 用住同一個 profile？"""
        import subprocess
        try:
            done = subprocess.run(["pgrep", "-f", str(self.profile_dir)],
                                  capture_output=True, text=True, timeout=20)
        except Exception:  # noqa: BLE001
            return False
        import os
        others = [int(x) for x in (done.stdout or "").split() if x.isdigit()
                  and int(x) != os.getpid()]
        return bool(others)

    def _clear_stale_profile_lock(self) -> bool:
        """上一次 run 硬死留低嘅 Chrome 會鎖住 profile，下次點都開唔到。

        ⚠️ **只可以殺已經冇 process 揸住嘅 profile。** 2026-08-05 實測：呢個
        function 原本無條件 `pkill -f <profile>`，於是一個 ad-hoc 抓取一開，就
        殺咗背景個人頁 backfill 嗰個 Chrome（兩者共用同一個 profile），backfill
        做到 40/207 就死。而家：有活住嘅兄弟就唔殺，改用臨時 profile 讓路。
        """
        import subprocess
        if self._profile_in_use():
            self.log("⚠️ 另一個 process 用住同一個 profile —— 唔殺佢，改用臨時 profile")
            import tempfile
            self.profile_dir = Path(tempfile.mkdtemp(prefix="sb_chrome_"))
            return True
        try:
            done = subprocess.run(["pkill", "-f", str(self.profile_dir)],
                                  capture_output=True, timeout=20)
        except Exception:  # noqa: BLE001
            return False
        if done.returncode == 0:
            self.log(f"🧹 清走上次留低嘅 Chrome（profile {self.profile_dir.name}）")
            time.sleep(3)
            return True
        return False

    # 瀏覽器自己死咗嘅特徵。⚠️ 呢啲**唔係個站拒絕** —— page/context 冚咗、
    # renderer crash、CDP 連線斷。2026-08-08 實測：Chrome 開足 15 分鐘之後
    # page 死咗，個 fetcher 記成「個站明確拒絕（穩定非 200）」，circuit breaker
    # 於是放棄埋餘下五個場次、退避 38 分鐘、最後成個賽日流失。個站由頭到尾
    # 冇回過一個非 200。對瀏覽器死亡嘅正確應對係重開，唔係收工。
    _BROWSER_DEATH = ("targetclosed", "has been closed", "target crashed",
                      "browser has been closed", "connection closed",
                      "websocket", "pipe closed")
    _BROWSER_RETRIES = 2
    # 抽夠幾多版就主動重開一次。⚠️ 呢個係預防，唔係反應。2026-08-08 實測：部機
    # 得 8 GB 實體記憶體、swap 7,168 MB 入面用咗 5,721 MB，而 Chrome 一個 crash
    # 報告都冇 —— 即係唔係佢自己炸，係喺記憶體壓力下個 target 俾系統收走。
    # 兩次死亡分別喺開機後約 30 版同約 64 版，所以 25 版封頂留足緩衝。
    # 重開得 8 秒，相對 25 版 × 25 秒嘅節奏成本可以忽略。
    # ⚠️ 刻意唔郁 launch flag（`--disable-gpu`、關圖片之類）：呢個站 200 vs 403
    # 完全取決於似唔似真瀏覽器，慳嗰幾十 MB 唔值得賭個 fingerprint。
    _RECYCLE_EVERY = int(os.environ.get("WC_SB_RECYCLE_EVERY", "25"))

    @classmethod
    def _is_browser_death(cls, exc) -> bool:
        blob = f"{type(exc).__name__} {exc}".lower()
        return any(sig in blob for sig in cls._BROWSER_DEATH)

    def _recycle(self) -> None:
        """冚咗個 page/context/playwright，令下次 `_ensure_page` 重開。"""
        for obj in (self._page, self._ctx):
            try:
                if obj is not None:
                    obj.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self._page = self._ctx = self._pw = None
        self._since_launch = 0

    def _ensure_page(self):
        """開瀏覽器。⚠️ 唔再需要「同源起始頁」—— `goto` 唔受同源限制。"""
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

        if self._page is not None and self._since_launch >= self._RECYCLE_EVERY:
            self.log(f"♻️ 抽咗 {self._since_launch} 版 —— 主動重開瀏覽器封頂記憶體")
            self._recycle()

        attempt = 0
        while True:
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
                response = page.goto(url, timeout=90000,
                                     wait_until="domcontentloaded")
                break
            except Exception as exc:  # noqa: BLE001
                self.requests_made += 1
                self._last_request = time.time()
                if self._is_browser_death(exc) and attempt < self._BROWSER_RETRIES:
                    attempt += 1
                    self.log(f"♻️ 瀏覽器死咗（{type(exc).__name__}）—— 重開再試 "
                             f"{attempt}/{self._BROWSER_RETRIES}：{url}")
                    self._recycle()
                    time.sleep(5)
                    continue
                # 重開之後仲死，或者根本唔係瀏覽器死亡（例如 timeout）。
                kind = "瀏覽器重開 %d 次之後仲係死" % attempt if attempt else "page.goto 失敗"
                self.stop_reason = f"{kind}（{type(exc).__name__}: {exc}）"
                self.log(f"⛔ {self.stop_reason}")
                return None

        try:
            status = response.status if response else None
            if status == 200:
                # 等 `OddsAgent.min.js` 填賠率。⚠️ 一定要 render 後嘅 DOM 而唔係
                # raw body：賠率由 JS 填，raw body 永遠冇（2026-08-05 前一直
                # `Flucs:$- $-`）。實測 raw vs rendered 對所有其他 parser 輸出
                # **完全一致**（19 匹、142 條往績、8 個 coverage 指標全部相同），
                # 所以呢個切換唔會蝕任何嘢。
                page.wait_for_timeout(self.render_wait_ms)
            text = page.content()
        except Exception as exc:  # noqa: BLE001
            self.stop_reason = f"讀唔到內容（{type(exc).__name__}: {exc}）"
            self.log(f"⛔ {self.stop_reason}")
            return None
        finally:
            self.requests_made += 1
            self._since_launch += 1
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
    with BrowserFetcher(delay=args.delay) as bf:
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
