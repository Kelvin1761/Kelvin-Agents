#!/usr/bin/env python3
"""Punters.com.au 登入 session —— 專用真 Chrome persistent profile。

點解要真瀏覽器（2026-10-13 實測）：`api.punters.com.au/racing` 用 script 直接
POST 會被 CloudFront 403。同 `sb_browser_fetch.py` 一樣，我哋用個站本來 serve
緊嘅方式去讀：headed 真 Chrome + persistent profile，喺 page 內 `fetch()`。
**唔加**任何擊敗 bot detection 嘅嘢（唔改 webdriver flag、唔輪換 UA／proxy）。

登入由用戶**自己**喺彈出嚟嘅 Chrome 窗做一次；呢度永遠唔處理密碼。
profile 喺 repo 外：`~/.cache/wongchoi/punters_chrome_profile`。

用法：
    python3 punters_session.py login     # 彈窗，等你登入（最多 15 分鐘）
    python3 punters_session.py status    # 只讀：印登入狀態（唔印 token）
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

SITE = "https://www.punters.com.au/"
RACING_API = "https://api.punters.com.au/racing"
DEFAULT_PROFILE = Path(os.environ.get("WC_PUNTERS_PROFILE", "")) \
    if os.environ.get("WC_PUNTERS_PROFILE") \
    else Path.home() / ".cache" / "wongchoi" / "punters_chrome_profile"

# 前端 `bs()` 用 `$rampart.token || rampart_token cookie` 做 Bearer（2026-10-13 讀 bundle）。
TOKEN_COOKIES = ("rampart_token",)


class PuntersRefused(RuntimeError):
    """個站拒絕（非 200／攔截頁）。唔應該重試。"""


class PuntersNotLoggedIn(RuntimeError):
    """profile 冇有效登入 —— 要用戶重新 `login`。"""


class PuntersSession:
    def __init__(self, profile_dir: Path | None = None, log=None):
        self.profile_dir = Path(profile_dir or DEFAULT_PROFILE)
        self.log = log or (lambda m: print(f"   {m}", flush=True))
        self._pw = self._ctx = self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        # ⚠️ channel="chrome" + headless=False：同 sb_browser_fetch 一樣，headless 會被攔。
        # 登入係用戶喺**普通** Chrome（冇自動化）手動做嘅 —— Punters 登入頁會拒絕
        # 自動化控制嘅 Chrome（2026-10-13 實測）。普通 Chrome 用 macOS Keychain
        # 加密 cookie，所以要剔走 Playwright 預設嘅假 keychain，否則讀唔返個 session。
        # 呢兩個 flag 只關 cookie 儲存，同偵測無關。
        self._ctx = self._pw.chromium.launch_persistent_context(
            str(self.profile_dir), channel="chrome", headless=False,
            viewport={"width": 1280, "height": 900},
            ignore_default_args=["--use-mock-keychain", "--password-store=basic"],
            args=["--window-size=1280,900"])
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        return self

    def __exit__(self, *_):
        for closer in (getattr(self._ctx, "close", None), getattr(self._pw, "stop", None)):
            try:
                if closer:
                    closer()
            except Exception:  # noqa: BLE001
                pass
        return False

    @property
    def page(self):
        return self._page

    def token(self) -> str | None:
        for c in self._ctx.cookies("https://www.punters.com.au"):
            if c["name"] in TOKEN_COOKIES and c["value"] and c["value"] != "none":
                return c["value"]
        return None

    def cookie_names(self) -> list[str]:
        return sorted({c["name"] for c in self._ctx.cookies("https://www.punters.com.au")})

    def ensure_on_site(self, url: str = SITE) -> None:
        if not (self._page.url or "").startswith("https://www.punters.com.au"):
            resp = self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if resp is None or resp.status != 200:
                raise PuntersRefused(f"goto {url} → {getattr(resp, 'status', None)}")
            self._page.wait_for_timeout(3000)

    def graphql(self, query: str, variables: dict, operation: str | None = None) -> dict:
        """喺 page 內 fetch；回傳 parsed JSON。任何失敗即 raise PuntersRefused，唔重試。"""
        tok = self.token()
        if not tok:
            raise PuntersNotLoggedIn("冇 token cookie —— 請重新 login")
        self.ensure_on_site()
        body = {"query": query, "variables": variables}
        if operation:
            body["operationName"] = operation
        try:
            res = self._page.evaluate(
                """async ([url, body, tok]) => {
                    const r = await fetch(url, {method: 'POST', credentials: 'include',
                        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok},
                        body: JSON.stringify(body)});
                    return {status: r.status, text: await r.text()};
                }""", [RACING_API, body, tok])
        except Exception as e:  # noqa: BLE001
            # 2026-10-13：瀏覽器 `TypeError: Failed to fetch` —— CloudFront 攔截頁冇 CORS header
            # 就係咁樣出現。分唔到係網絡定攔截，一律當拒絕：停、唔重試。
            raise PuntersRefused(f"fetch 失敗（可能係攔截）：{str(e).splitlines()[0][:200]}") from e
        if res["status"] != 200:
            raise PuntersRefused(f"graphql status {res['status']}: {res['text'][:200]}")
        return json.loads(res["text"])


def _cmd_login() -> int:
    """開一個**普通** Chrome（冇自動化）畀用戶手動登入；登入完關窗，再跑 `status`。"""
    import subprocess
    DEFAULT_PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.run(["open", "-na", "Google Chrome", "--args",
                    f"--user-data-dir={DEFAULT_PROFILE}", "--no-first-run", SITE], check=True)
    print("👉 請喺新開嘅 Chrome 窗登入 Punters，登入完**關咗個窗**，再跑 `status`。", flush=True)
    return 0


def _cmd_status() -> int:
    with PuntersSession() as s:
        s.page.goto(SITE, wait_until="domcontentloaded", timeout=60000)
        s.page.wait_for_timeout(4000)
        print("cookie 名：", s.cookie_names())
        print("登入 token：", "有" if s.token() else "冇")
        return 0 if s.token() else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    sys.exit({"login": _cmd_login, "status": _cmd_status}[cmd]())
