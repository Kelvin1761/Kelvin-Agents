#!/usr/bin/env python3
"""唔開瀏覽器攞 sportsbetform 頁面（curl_cffi），寫落同 `BrowserFetcher` 一模一樣嘅 cache。

**點解而家可以唔使 Chrome**（2026-11-17 實測，同一部機同一個 IP，每版隔 25 秒）：

| 頁面 | curl_cffi | 同瀏覽器 cache 比較 |
|---|---|---|
| `/{meetingId}/{raceId}/` 賽前 | 200 | 往績、馬匹區塊、Speedmap 全部一樣；退出馬仲**新過**22:00 嗰版（API 證實） |
| `/{meetingId}/{raceId}/` 賽後 | 200 | 當日名次／頭馬距離／SP 一樣，所有往績一樣 |
| `/{YYYY-MM-DD}/` 索引頁 | 200 | parse 到 10 個場次（之前記錄係 403） |
| `?view=Speedmap` | 200 | 一樣（除咗夜晚新退出嗰匹） |
| `/Jockey|Trainer/{id}/` | 200 | 13/13 逐格一樣 |
| `/form/<CODE>.html`（API `longFormLink`） | 200 | 往績 1,700/1,705 條逐項一樣 |

`sb_browser_fetch.py` 個表（2026-08-05：curl_cffi 403）當時係真；個站之後放寬咗。所以呢度
**唔假設佢會一直放寬**：撞到任何非 200／攔截頁即刻停低唔重試，同 `BrowserFetcher` 一樣；
`HybridFetcher` 會喺 HTTP 被拒絕嗰刻轉返真 Chrome 做埋今次 run 餘下嘅頁。

唯一唔同：**賠率**。賽事頁嘅賠率由 `OddsAgent.min.js` 填，raw HTML 永遠空（`parse_odds_html`
回 `{}`）。所以每攞一版賽事頁，就經 sportsbet.com.au API（`RacecardWithContext`，同 NBA／網球
一樣嘅 host，從來冇封過）寫一個 **sidecar** `<cache>.odds.json`，格式同 `parse_odds_html` 一樣：
`{馬號: {"Sportsbet-FixedWin": w, "Sportsbet-FixedPlace": p}}`。讀賠率一律經
`claw_sportsbet_form.cached_page_odds()`：HTML 有就用 HTML（瀏覽器路徑），冇先讀 sidecar。
賠率唔入評分（`_write_odds_snapshot` docstring），只係 Formguide Flucs、`Odds.json`、落注同市場警號用。

⚠️ 唔係用嚟繞過偵測：唔改 UA、唔輪換 fingerprint／proxy、唔重試被拒絕嘅頁。
開跑時間（`meta["start"]`）都係 JS 填，但全 repo 冇人讀，所以唔補。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claw_sportsbet_form import BASE  # noqa: E402
from sb_browser_fetch import MIN_BYTES, cache_path  # noqa: E402

API = "https://www.sportsbet.com.au/apigw/sportsbook-racing/Sportsbook/Racing/"
MEETING_IDS = Path(__file__).resolve().parent / "data" / "sb_archive_meeting_ids.json"
RACE_URL = re.compile(r"^" + re.escape(BASE) + r"/(\d{5,7})/(\d{5,9})/$")
TITLE = re.compile(r"<title>\s*([A-Z][A-Za-z' \-]+?)\s+Race\s+(\d+)\s*</title>")
SYDNEY = timezone(timedelta(hours=10))   # 只用嚟揀「今日／聽日」；DST 差一個鐘唔影響


def odds_sidecar_path(url: str) -> Path:
    return cache_path(url).with_suffix(".odds.json")


def _norm(value) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


class HttpFetcher:
    """同 `BrowserFetcher` 一樣嘅介面（`get(url, force)`、`stop_reason`、`network_reason`、
    `launch_reason`、`last_page_error`、`timeout_streak`、`requests_made`、`reset_gate`、`close`）。"""

    _NETWORK_RETRIES = 3
    _NETWORK_BACKOFF = 20
    _TIMEOUT_GATE_STREAK = 3

    def __init__(self, delay: float = 25.0, verbose: bool = True, log=None, session=None,
                 api_session=None, mapping_path: Path | None = None, **_ignored):
        self.delay = max(float(delay), 12.0)
        self.verbose = verbose
        self.log = log or (lambda m: print(f"   {m}", flush=True))
        if session is None:
            from curl_cffi import requests
            session = requests.Session(impersonate="chrome120")
        self.session = session
        self.api_session = api_session or session
        self.mapping_path = Path(mapping_path or MEETING_IDS)
        self.requests_made = 0
        self.stop_reason: str | None = None
        self.network_reason: str | None = None
        self.launch_reason: str | None = None     # 冇瀏覽器，永遠 None；留住俾 caller 一樣咁讀
        self.last_page_error: str | None = None
        self.timeout_streak = 0
        self.odds_written = 0
        self.odds_missed: list[str] = []
        self._last_request = 0.0
        self._allracing: dict[str, tuple[float, dict]] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False

    def close(self) -> None:
        pass

    def reset_gate(self) -> None:
        self.stop_reason = None
        self.network_reason = None
        self.last_page_error = None
        self.timeout_streak = 0

    def _pace(self) -> None:
        wait = self.delay - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)

    def get(self, url: str, force: bool = False) -> str | None:
        target = cache_path(url)
        if not force and target.exists():
            if self.verbose:
                self.log(f"（cache）{url}")
            return target.read_text(encoding="utf-8")
        if self.stop_reason or self.network_reason:
            return None
        if not url.startswith(BASE):
            raise ValueError(f"只可以攞 {BASE} 嘅頁：{url}")
        net_attempt = 0
        while True:
            self._pace()
            try:
                r = self.session.get(url, timeout=45)
            except Exception as exc:  # noqa: BLE001
                self.requests_made += 1
                self._last_request = time.time()
                blob = f"{type(exc).__name__} {exc}".lower()
                if "timeout" in blob or "timed out" in blob:
                    # 同 BrowserFetcher：單版 timeout 唔係封鎖；連續三版先收手
                    self.timeout_streak += 1
                    self.last_page_error = f"呢版 timeout（{type(exc).__name__}）"
                    if self.timeout_streak < self._TIMEOUT_GATE_STREAK:
                        self.log(f"⏱️ {self.last_page_error} —— 當單版失敗：{url}")
                        return None
                    self.stop_reason = f"連續 {self.timeout_streak} 版 timeout（完全冇回應）"
                    self.log(f"⛔ {self.stop_reason}")
                    return None
                if net_attempt < self._NETWORK_RETRIES:
                    net_attempt += 1
                    wait = self._NETWORK_BACKOFF * net_attempt
                    self.log(f"📡 網絡問題（{type(exc).__name__}）—— 等 {wait} 秒再試 "
                             f"{net_attempt}/{self._NETWORK_RETRIES}：{url}")
                    time.sleep(wait)
                    continue
                self.network_reason = f"網絡試咗 {net_attempt} 次都唔通（{type(exc).__name__}）"
                self.log(f"📡 {self.network_reason}")
                return None
            break
        self.requests_made += 1
        self._last_request = time.time()
        text = r.text or ""
        if r.status_code != 200:
            self.stop_reason = f"HTTP {r.status_code} {url}"
            self.log(f"⛔ {self.stop_reason} —— 停低唔重試")
            return None
        if len(text) < MIN_BYTES:
            self.stop_reason = f"只有 {len(text)} bytes（當攔截頁）{url}"
            self.log(f"⛔ {self.stop_reason} —— 停低唔重試")
            return None
        self.timeout_streak = 0
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        if self.verbose:
            self.log(f"✅ {len(text):,} bytes  {url}（HTTP）")
        if RACE_URL.match(url):
            self._write_odds_sidecar(url, text)
        return text

    # -- 賠率 sidecar --------------------------------------------------------
    def _write_odds_sidecar(self, url: str, html: str) -> None:
        """賽事頁 → API 賠率 → `<cache>.odds.json`。任何失敗都唔影響攞頁，只記低。"""
        try:
            odds, event_id = self.api_odds(url, html)
        except Exception as exc:  # noqa: BLE001
            odds, event_id = None, f"{type(exc).__name__}: {exc}"
        if not odds:
            self.odds_missed.append(f"{url}（{event_id or '搵唔到對應賽事'}）")
            return
        odds_sidecar_path(url).write_text(json.dumps({
            "source": "sportsbet_api_racecard", "event_id": event_id,
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "odds": {str(k): v for k, v in sorted(odds.items())},
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        self.odds_written += 1

    def _all_racing(self, day: str) -> dict:
        hit = self._allracing.get(day)
        if hit and time.time() - hit[0] < 300:
            return hit[1]
        resp = self.api_session.get(API + f"AllRacing/{day}", timeout=30)
        data = resp.json() if resp.status_code == 200 else {}
        self._allracing[day] = (time.time(), data)
        return data

    def _candidate_days(self, meeting_id: str) -> list[str]:
        try:
            mapping = json.loads(self.mapping_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            mapping = {}
        for meta in mapping.values():
            if str(meta.get("meetingId")) == meeting_id and meta.get("date"):
                return [meta["date"]]
        today = datetime.now(SYDNEY).date()
        return [str(today + timedelta(days=d)) for d in (0, 1, -1)]

    def api_odds(self, url: str, html: str) -> tuple[dict, str | None]:
        """→ ({馬號: {"Sportsbet-FixedWin", "Sportsbet-FixedPlace"}}, sportsbet event id)。

        對應：meetingId → 對應表嘅日期 → `AllRacing/{日期}` 入面同名馬場 → 同場次號。
        唔唯一就放棄（寧願冇賠率都唔好貼錯場）。
        """
        m, t = RACE_URL.match(url), TITLE.search(html)
        if not m or not t:
            return {}, None
        venue, race_no = _norm(t.group(1)), int(t.group(2))
        found = []
        for day in self._candidate_days(m.group(1)):
            stack = [self._all_racing(day)]
            while stack:
                o = stack.pop()
                if isinstance(o, dict):
                    if "events" in o and _norm(o.get("name")) == venue:
                        found += [e for e in o["events"] or [] if int(e.get("raceNumber") or 0) == race_no]
                    stack.extend(o.values())
                elif isinstance(o, list):
                    stack.extend(o)
            if found:
                break
        ids = {e.get("id") for e in found if e.get("id")}
        if len(ids) != 1:
            return {}, (f"{len(ids)} 個候選賽事" if ids else None)
        event_id = ids.pop()
        resp = self.api_session.get(API + f"Events/{event_id}/RacecardWithContext", timeout=30)
        if resp.status_code != 200:
            return {}, f"API {resp.status_code}"
        out = {}
        for market in (resp.json().get("racecardEvent") or {}).get("markets") or []:
            for sel in market.get("selections") or []:
                num = sel.get("runnerNumber")
                if not num or sel.get("isOut") or str(sel.get("statusCode") or "") == "S":
                    continue
                price = next((p for p in sel.get("prices") or [] if p.get("priceCode") == "L"), {})
                win, place = price.get("winPrice"), price.get("placePrice")
                if win:
                    out[int(num)] = {"Sportsbet-FixedWin": float(win)}
                    if place:
                        out[int(num)]["Sportsbet-FixedPlace"] = float(place)
        return out, str(event_id)


class HybridFetcher:
    """先行 HTTP；HTTP 一被**拒絕**（非 200／攔截頁／連續 timeout）就轉真 Chrome 做埋今次 run。

    本機網絡斷（`network_reason`）唔轉 —— 換 Chrome 一樣出唔到門，照舊交俾 caller 嘅 network gate。
    轉咗就唔會轉返 HTTP：同一個 run 內，個站已經話過唔畀。
    """

    def __init__(self, delay: float = 25.0, log=None, http: HttpFetcher | None = None,
                 browser_factory=None, **kwargs):
        self.log = log or (lambda m: print(f"   {m}", flush=True))
        self.http = http or HttpFetcher(delay=delay, log=self.log, **kwargs)
        self._browser_factory = browser_factory or (lambda: _browser(delay, self.log, kwargs))
        self.browser = None
        self.fallback_reason: str | None = None

    @property
    def active(self):
        return self.browser if self.browser is not None else self.http

    def __getattr__(self, name):
        # stop_reason / network_reason / launch_reason / last_page_error / timeout_streak
        if name in {"stop_reason", "network_reason", "launch_reason", "last_page_error",
                    "timeout_streak"}:
            return getattr(self.active, name, None)
        raise AttributeError(name)

    @property
    def requests_made(self) -> int:
        return self.http.requests_made + (self.browser.requests_made if self.browser else 0)

    def get(self, url: str, force: bool = False) -> str | None:
        if self.browser is None:
            html = self.http.get(url, force=force)
            if html is not None or not self.http.stop_reason:
                return html
            self.fallback_reason = self.http.stop_reason
            self.log(f"🔁 HTTP 被拒絕（{self.fallback_reason}）—— 今次 run 餘下嘅頁轉返真 Chrome")
            self.browser = self._browser_factory()
        return self.browser.get(url, force=force)

    def reset_gate(self) -> None:
        self.http.reset_gate()
        if self.browser is not None and hasattr(self.browser, "reset_gate"):
            self.browser.reset_gate()

    def close(self) -> None:
        self.http.close()
        if self.browser is not None:
            self.browser.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False


def _browser(delay, log, kwargs):
    from sb_browser_fetch import BrowserFetcher
    return BrowserFetcher(delay=delay, log=log, **kwargs)


def make_fetcher(delay: float = 25.0, log=None, **kwargs):
    """排程用：`WC_SB_FETCH=browser` 行舊真 Chrome；其他（預設）行 HTTP + Chrome 後備。"""
    if os.environ.get("WC_SB_FETCH", "").strip().lower() == "browser":
        return _browser(delay, log, kwargs)
    return HybridFetcher(delay=delay, log=log, **kwargs)
