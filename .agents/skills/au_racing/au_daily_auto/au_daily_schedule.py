#!/usr/bin/env python3
"""AU Wong Choi 每日自動排程 runner —— 兩個 mode，一個入口。

    --mode evening   22:00 Australia/Sydney
                     1. 覆盤 + 歸檔今日已完成嘅場次
                     2. 分析下一個可用賽日
                     3. 驗證 + 發佈 dashboard
    --mode morning   10:00 Australia/Sydney
                     1. 重新確認場地狀況 / 退出馬 / 換騎師 / 檔位 / 馬匹數
                     2. 有實質變動先重新評分
                     3. 驗證 + 發佈 dashboard

設計取向：**呢個檔淨係做編排**。抽取、Facts/Logic、評分、賽果、覆盤、dashboard
合併、Cloudflare 發佈全部 shell out 去現有命令，所以手動跑同排程跑係同一條路，
唔會有第二套邏輯靜靜咁行開。

⚠️ 網絡紀律（見 `au_wong_choi/SKILL.md`）：sportsbetform 對密集請求會 403，而個
封鎖係**持續**嘅（唔係即時恢復）。所以：預設 25 秒節奏、硬下限 12 秒、撞到穩定
非 200 即刻停低唔重試、抓過一定落 cache。快少少嘅代價唔係「慢啲」，係「今日之
內做唔到嘢」。

⚠️ 賽果嚟源：Sportsbet 賽事頁嘅往績第一行就係嗰場賽果，所以**賽後要重抓一次**
賽事頁（賽前 cache 冇賽果行）。重抓會覆蓋 cache，但 `write_meeting` 本身會丟走
賽後嗰行防洩漏，所以覆蓋唔會污染日後嘅重抽。
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

HERE = Path(__file__).resolve().parent
AU_SKILL = HERE.parent
PROJECT_ROOT = HERE.parents[3]
for _p in (str(PROJECT_ROOT), str(AU_SKILL)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from wongchoi_paths import AU_RACING, AU_RACING_MIRROR  # noqa: E402

ARCHIVE_ROOT = AU_RACING / "Archive"
# 兩個 CSV 係歸檔之後改嘅歷史庫；鏡像要連佢哋一齊，Drive 邊先算真副本。
MIRRORED_ROOT_FILES = ("AU_Historical_Raw_Race_Results.csv",
                       "AU_Backfill_Race_Results.csv")
DASHBOARD_DIR = PROJECT_ROOT / "Horse_Racing_Dashboard"
LOG_DIR = HERE / "logs"
WORK_DIR = HERE / "work"

CLAW = AU_SKILL / "claw_sportsbet_form.py"
SB_RESULTS = AU_SKILL / "sb_results.py"
MEETING_IDS = AU_SKILL / "data" / "sb_archive_meeting_ids.json"
AU_ORCH = AU_SKILL / "au_wong_choi" / "scripts" / "au_orchestrator.py"
AU_AUTO_ORCH = AU_SKILL / "au_wong_choi_auto" / "scripts" / "au_auto_orchestrator.py"
REFLECTOR = AU_SKILL / "au_reflector" / "scripts" / "au_reflector_orchestrator.py"
GENERATE_STATIC = DASHBOARD_DIR / "generate_static.py"
DEPLOY_SH = DASHBOARD_DIR / "deploy.sh"

TIMEZONE = "Australia/Sydney"
LIVE_SNAPSHOT_URL = "https://wongchoi-dashboard.pages.dev/dashboard-data.json"
NEXT_EVENTS_URL = ("https://www.sportsbet.com.au/apigw/sportsbook-racing/Sportsbook/"
                   "Racing/NextEvents?racingFilters=HR_DOMESTIC&groupByFilters=true")

MIN_FETCH_DELAY = 12.0
DEFAULT_FETCH_DELAY = 25.0

# Exit codes: 0 ok / 75 暫時性（值得再試）/ 1 硬失敗
EXIT_OK = 0
EXIT_TEMPORARY = 75
EXIT_FAILED = 1


class TemporaryFailure(RuntimeError):
    """要再試嘅失敗（網絡、rate limit、build/deploy 暫時炸）。"""


# ── run log ─────────────────────────────────────────────────────────────────
class RunLog:
    """結構化 run log。每一步都即刻寫落 disk —— 中途炸都仲有記錄。"""

    def __init__(self, mode: str, review_day: date, path: Path,
                 notify: bool = True):
        self.path = path
        self.notify_enabled = notify
        self.started = time.time()
        # Circuit breaker。一個場次成個抽唔到（穩定 403）之後，餘下嘅場次唔再
        # 出網 —— 個站已經明確講唔得，逐個場次照敲落去等於每場再敲三次門，
        # 而且會令封鎖延長。2026-08-05 實測：Canterbury 7 場全 403 之後，原本
        # 仲會去敲 Cranbourne / Doomben / Hobart / Murray Bridge 共 33 場。
        self.site_refusing = False
        self.data: dict = {
            "task_name": f"au-wong-choi-{mode}",
            "mode": mode,
            "timezone": TIMEZONE,
            "review_day": review_day.isoformat(),
            "started_at": stamp(),
            "completed_at": None,
            "status": "running",
            "duration_seconds": None,
            "steps": [],
            "meetings_processed": [],
            "races_archived": [],
            "races_added": [],
            "races_updated": [],
            "scratchings_detected": [],
            "track_changes_detected": [],
            "analysis_changes": [],
            "dashboard_validation": None,
            "cloudflare_deployment": None,
            "errors": [],
            "warnings": [],
            "retries": [],
        }
        self.flush()

    # -- helpers ----------------------------------------------------------
    def step(self, name: str, status: str, **detail) -> None:
        self.data["steps"].append({"step": name, "status": status,
                                   "at": stamp(), **detail})
        log(f"[{name}] {status}" + (f" {compact(detail)}" if detail else ""))
        self.flush()

    def meeting(self, name: str, status: str, **detail) -> None:
        self.data["meetings_processed"].append({"meeting": name, "status": status,
                                                "at": stamp(), **detail})
        log(f"   · {name}: {status}" + (f" {compact(detail)}" if detail else ""))
        self.flush()

    def warn(self, message: str) -> None:
        self.data["warnings"].append({"at": stamp(), "message": message})
        log(f"⚠️  {message}")
        self.flush()

    def error(self, step: str, message: str) -> None:
        self.data["errors"].append({"at": stamp(), "step": step, "message": message})
        log(f"❌ [{step}] {message}")
        self.flush()

    def trip_site_gate(self, where: str) -> None:
        if self.site_refusing:
            return
        self.site_refusing = True
        # ⚠️ 唔可以講死「非 200」。呢個閘接受任何 `stop_reason`，而 2026-08-08
        # 嗰次係我哋自己個 Chrome 死咗 —— 個站由頭到尾冇回過一個非 200，但條
        # 訊息叫我（同 Kelvin）去查 Sportsbet 嘅封鎖，查錯咗方向。理由照抄。
        self.warn(f"攞唔到頁，喺 {where} 停低 —— 今次 run 唔再出網攞頁，"
                  f"餘下嘅場次記做 pending，下一次排程再試")
        self.data["steps"].append({"step": "site-gate", "status": "tripped",
                                   "at": stamp(), "where": where})
        self.flush()

    def retry(self, what: str, attempt: int, reason: str) -> None:
        self.data["retries"].append({"at": stamp(), "what": what,
                                     "attempt": attempt, "reason": reason})
        log(f"🔁 retry {what} ({attempt}): {reason}")
        self.flush()

    def finish(self, status: str) -> None:
        self.data["status"] = status
        self.data["completed_at"] = stamp()
        self.data["duration_seconds"] = round(time.time() - self.started, 1)
        self.flush()
        log(f"=== run {status} in {self.data['duration_seconds']}s "
            f"→ {self.path.name} ===")
        self.notify()

    def notify(self) -> None:
        """把結果推去手機。⚠️ `--no-notify` 之下唔出聲 —— 驗證 run 逐個推一條
        「partial」出去，係最快令人開始無視通知嘅做法，而下次真出事就會漏。⚠️ 通知失敗唔可以令 run 失敗 —— 嘢已經做完，
        通知只係報告。所以成段包住，最多喺 log 講一句。"""
        if not getattr(self, "notify_enabled", True):
            log("[notify] 跳過（--no-notify）")
            return
        try:
            sys.path.insert(0, str(HERE))
            import au_notify

            sent = au_notify.send(self.data)
            if sent:
                log(f"[notify] {'; '.join(sent)}")
            # ⚠️ 失敗嗰陣多送一條診斷。真正嘅成本唔係修，係「由發現到有足夠資料
            # 判斷」嗰段 —— 出事時 Kelvin 唔喺電腦前，收到「❌ failed」之後要自己
            # 開機、搵 log、抄過嚟問。呢條訊息就係要消滅嗰一步。
            if self.data.get("status") in ("failed", "partial"):
                import au_diagnose

                text = au_diagnose.diagnose(self.data, au_diagnose.runs())
                au_diagnose.BUNDLE.write_text(text, encoding="utf-8")
                au_notify.push("🔎 " + au_diagnose.phone_summary(text))
        except Exception as exc:  # noqa: BLE001
            log(f"[notify] 送唔出（{type(exc).__name__}: {exc}）—— run 結果不受影響")

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self.path)


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def compact(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def log(message: str) -> None:
    # ⚠️ 目的地喺 call 嗰刻讀 env，唔係 import 嗰刻。2026-08-05 實測：跑 pytest
    # 嗰陣，測試嘅 `where="test 第 3 場"`、`$ /usr/bin/true` 全部寫入生產
    # log，插咗入一個 live 晚更 run 中間。run state JSON 有隔離（path 由 caller
    # 傳入），得呢個共用 log 冇 —— 而 log 就係明早唯一嘅診斷來源。
    log_dir = Path(os.environ.get("WC_AU_SCHED_LOG_DIR") or LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    line = f"[{stamp()}] {message}"
    print(line, flush=True)
    with (log_dir / "au_daily_schedule.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ── 小工具 ──────────────────────────────────────────────────────────────────
def local_today() -> date:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo(TIMEZONE)).date()
    return datetime.now().date()


def fetch_delay() -> float:
    """節奏。低過硬下限就拉返上去 —— 個下限係實測出嚟嘅，唔係品味。"""
    try:
        wanted = float(os.environ.get("WC_AU_FETCH_DELAY", DEFAULT_FETCH_DELAY))
    except ValueError:
        wanted = DEFAULT_FETCH_DELAY
    return max(wanted, MIN_FETCH_DELAY)


def normalise(value: object) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def venue_from_slug(slug: str) -> str:
    return slug.replace("_", " ").title()


#: 兩邊會用唔同寫法嘅字。⚠️ 2026-08-06 實測：索引頁出 `mount_isa`、API 出
#: `Mt Isa` —— 兩邊正規化之後係 `mountisa` vs `mtisa`，相等、前綴、第一個 token
#: 三步全部配唔到，於是 Mt Isa 被當**海外場次剔走**，一個真澳洲場次靜靜咁冇分析。
#: 展開成同一個寫法先比。
_VENUE_ALIASES = (("mount", "mt"), ("saint", "st"), ("port", "pt"))


def _venue_key(name: str) -> str:
    """正規化 + 展開常見縮寫，令 `mount_isa` 同 `Mt Isa` 對得上。"""
    key = normalise(name)
    for long, short in _VENUE_ALIASES:
        if key.startswith(long):
            key = short + key[len(long):]
    return key


def match_venue(slug: str, api_venues: list[str]) -> str | None:
    """索引頁嘅 slug → API 個馬場名。配唔到回 None。

    ⚠️ 唔可以要求逐字相等。索引頁用縮寫（`murray_bdge`、`mount_isa`），API 出
    全名或者另一個縮寫（`Murray Bridge`、`Mt Isa`）。所以：先展開縮寫再試相等 →
    前綴 → 第一個 token 相等而且只得一個候選。三步都配唔到就當配唔到 ——
    **配錯馬場比冇數據差**，因為會拉錯一個馬場嘅場地狀況入去評分。
    """
    want = _venue_key(slug)
    exact = [v for v in api_venues if _venue_key(v) == want]
    if exact:
        return exact[0]
    prefix = [v for v in api_venues
              if len(want) >= 6 and len(_venue_key(v)) >= 6
              and (_venue_key(v).startswith(want) or want.startswith(_venue_key(v)))]
    if len(prefix) == 1:
        return prefix[0]
    head = slug.split("_")[0].lower()
    if len(head) >= 5:
        token = [v for v in api_venues if v.split()[0].lower() == head]
        if len(token) == 1:
            return token[0]
    return None


def normalise_going(raw: object) -> str:
    """`Soft (5)` / `soft5` / `Good 4` → `Soft 5`；認唔到就回空字串。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    m = re.match(r"([A-Za-z]+)\s*\(?\s*(\d+)?\s*\)?", text)
    if not m:
        return ""
    word = m.group(1).title()
    if word not in {"Good", "Soft", "Heavy", "Firm", "Synthetic", "Slow"}:
        return ""
    grade = int(m.group(2)) if m.group(2) else None
    valid_grades = {
        "Firm": {1, 2},
        "Good": {3, 4},
        "Soft": {5, 6, 7},
        "Heavy": {8, 9, 10},
    }
    # Invalid numbers are commonly the adjacent temperature after flattened
    # HTML (``Track: Good`` + ``25°C``).  Keep the proven surface family but do
    # not publish a fictitious grade.
    if grade is not None and grade not in valid_grades.get(word, set()):
        return word
    return f"{word} {grade}" if grade is not None else word


def run_cmd(cmd: list[str], *, cwd: Path | None = None, timeout: int = 3600,
            env: dict | None = None) -> tuple[int, str]:
    """跑一個命令，回 (returncode, output)。絕不 raise —— 由 caller 決定嚴重性。"""
    log(f"$ {' '.join(str(c) for c in cmd)}")
    merged = os.environ.copy()
    # ⚠️ 所有 subprocess 一律 cache-only。sportsbetform 只行真瀏覽器（見
    # `browser()`），所以任何一段 Python 出網都係「敲一道已經明講唔得嘅門」：
    # 攞唔到嘢，仲會延長封鎖。呢個 env 令 `SportsbetFormFetcher` cache miss
    # 直接回 None，冇任何腳本可以繞過。
    merged["WC_SB_CACHE_ONLY"] = "1"
    # 晚更把 people TTL 設 0，令 `sb_people_stats.refresh` 用啱啱重抽嘅個人頁
    # 更新 cache（cache-only 之下唔會出網，所以呢個純粹係「唔跳過已有 entry」）。
    merged.setdefault("WC_SB_PEOPLE_TTL_DAYS", os.environ.get(
        "WC_SB_PEOPLE_TTL_DAYS", "21"))
    # ⚠️ 一定要 export repo root。`sb_people_stats.cache_path()` 要
    # `from wongchoi_paths import AU_RACING`（AU_RACING 搬去本機之後就更加要），
    # 而 claw 係用 cwd=au_racing 跑，repo root 唔喺 sys.path。缺咗呢個
    # `write_meeting` 個 `except Exception` 會靜靜食咗 ModuleNotFoundError，
    # `_people_cache` 變空，1,064 個 `(LY:)` token 全部寫成 `-`（2026-08-05 實測）。
    existing = merged.get("PYTHONPATH", "")
    root = str(PROJECT_ROOT)
    if root not in existing.split(os.pathsep):
        merged["PYTHONPATH"] = f"{root}{os.pathsep}{existing}" if existing else root
    if env:
        merged.update(env)
    try:
        done = subprocess.run([str(c) for c in cmd], cwd=str(cwd or PROJECT_ROOT),
                              env=merged, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout,
                              check=False,
                              # ⚠️ 一定要 errors="replace"。`text=True` 係嚴格
                              # UTF-8，而 `stderr=STDOUT` 把兩條 stream 合併 ——
                              # 兩個寫入者交錯就可以把一個多位元組字元切開，
                              # 於是出現孤立嘅 0xef。2026-08-13 實測：一個
                              # UnicodeDecodeError 殺死咗成個晚更 run，而嗰段
                              # 輸出只係 log 用。subprocess 輸出永遠唔應該有能力
                              # 令 run 死。亦要明寫 encoding —— launchd 底下
                              # locale 可能係 POSIX，`text=True` 會退去 ASCII。
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"
    out = (done.stdout or "").strip()
    if out:
        for line in out.splitlines()[-40:]:
            log(f"   | {line}")
    return done.returncode, out


# ── Sportsbet ───────────────────────────────────────────────────────────────
def browser(runlog: RunLog):
    """Run-scoped 真 Chrome session。第一次用先開，run 尾收工。

    ⚠️ **sportsbetform 只行真瀏覽器。** 2026-08-05 實測，同一時間同一個 IP：
    curl_cffi 403、Playwright bundled chromium headless 403、**真 Chrome headless
    亦 403**、真 Chrome headed 200。即係被偵測嘅係 headless 本身。詳表見
    `sb_browser_fetch.py`。

    代價講清楚：headed 要有 active GUI login session（鎖螢幕冇問題、登出就唔得），
    而且每次 run 會彈一個 Chrome 窗。
    """
    if getattr(runlog, "browser_session", None) is None:
        from claw_sportsbet_form import BASE
        from sb_browser_fetch import BrowserFetcher
        # 同源起始頁：`fetch()` 要同源，所以一定要先落一版。用當日索引頁 ——
        # 任何一版有效索引頁都做得到起點，成本係每個 run 多一個請求。
        runlog.browser_session = BrowserFetcher(
            delay=fetch_delay(),
            # 兩個候選：覆盤日索引頁，同今日索引頁。落唔到第一個唔應該令成個
            # run 報廢（起始頁係單點失敗位）。
            origin_candidates=[f"{BASE}/{runlog.data['review_day']}/",
                               f"{BASE}/{local_today().isoformat()}/"],
            log=lambda message: log(f"   {message}"))
    return runlog.browser_session


def close_browser(runlog: RunLog) -> None:
    session = getattr(runlog, "browser_session", None)
    if session is None:
        return
    runlog.step("browser", "closed", requests_made=session.requests_made,
                stop_reason=session.stop_reason)
    session.close()
    runlog.browser_session = None


def fetch_page(runlog: RunLog, url: str, *, force: bool = False,
               where: str = "") -> str | None:
    """經真 Chrome 攞一版 sportsbetform。拒絕就 trip circuit breaker。"""
    if runlog.site_refusing:
        return None
    session = browser(runlog)
    html = session.get(url, force=force)
    if html is None and session.stop_reason:
        runlog.trip_site_gate(f"{where or url}（{session.stop_reason}）")
    return html


def api_next_events(runlog: RunLog) -> list[dict]:
    """sportsbet.com.au NextEvents → 未來嘅 AU 平地賽事。

    ⚠️ 呢個 API 淨係回最近大約 30 場，所以只可以靠佢知「下一個賽日係幾號、有邊
    幾個馬場、官方場地狀況係乜」，**唔可以**靠佢數一日總共幾場。

    ⚠️ **呢一個仍然行 curl_cffi，係故意嘅，唔係漏咗。** 兩個原因：
      1. 佢係 `sportsbet.com.au`（另一個 host），從來冇封過我哋 —— 被封嘅係
         `sportsbetform.com.au`。
      2. 由 sportsbetform 嗰版 page 去 fetch 呢個 API 係跨域，CORS 會擋住讀 body，
         所以「全部改行瀏覽器」對呢一個 endpoint 技術上做唔到。
    """
    from claw_sportsbet_form import SportsbetFormFetcher
    fetcher = SportsbetFormFetcher(delay=fetch_delay(), use_cache=False,
                                   verbose=False, cache_only=False)
    try:
        response = fetcher.session.get(NEXT_EVENTS_URL, timeout=30)
        payload = response.json() if response.status_code == 200 else None
    except Exception as exc:  # noqa: BLE001
        runlog.warn(f"NextEvents API 攞唔到（{type(exc).__name__}: {exc}）")
        return []
    if not payload:
        runlog.warn("NextEvents API 回空")
        return []
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("id") and node.get("competitionName") and node.get("raceNumber"):
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return [e for e in found if e.get("country") == "Australia"]


def events_by_day(events: list[dict]) -> dict[str, dict[str, dict]]:
    """→ {'YYYY-MM-DD': {venue: {going, status, races_seen}}}"""
    out: dict[str, dict[str, dict]] = {}
    tz = ZoneInfo(TIMEZONE) if ZoneInfo else None
    for event in events:
        raw = event.get("startTime")
        try:
            when = datetime.fromtimestamp(int(raw), tz)
        except (TypeError, ValueError, OSError):
            continue
        day = when.date().isoformat()
        venue = str(event.get("competitionName") or "").strip()
        if not venue:
            continue
        slot = out.setdefault(day, {}).setdefault(
            venue, {"going": "", "status_codes": set(), "races_seen": set()})
        going = normalise_going(event.get("trackStatus"))
        if going:
            slot["going"] = going
        slot["status_codes"].add(str(event.get("statusCode") or ""))
        slot["races_seen"].add(int(event.get("raceNumber") or 0))
    for day in out.values():
        for slot in day.values():
            slot["status_codes"] = sorted(slot["status_codes"])
            slot["races_seen"] = sorted(slot["races_seen"])
    return out


def fetch_date_index(runlog: RunLog, day: str) -> dict:
    """`/{YYYY-MM-DD}/` → {slug: {date, meetingId, races}}。缺頁 = 暫時性失敗。"""
    from claw_sportsbet_form import BASE, parse_date_index
    html = fetch_page(runlog, f"{BASE}/{day}/", where=f"{day} 索引頁")
    if not html:
        raise TemporaryFailure(
            f"攞唔到 {day} 嘅場次索引頁（真 Chrome 開唔到或者個站拒絕）——"
            " 呢個係暫時性，下一個排程會再試")
    index = parse_date_index(html)
    # 索引頁淨係列當日，但 parse 出嚟嘅 date 係 YYYYMMDD，順手核對一次。
    wanted = day.replace("-", "")
    clean = {slug: meta for slug, meta in index.items() if meta.get("date") == wanted}
    if len(clean) != len(index):
        runlog.warn(f"{day} 索引頁有 {len(index) - len(clean)} 個非當日場次，已略過")
    return clean


# ── meeting 目錄 ────────────────────────────────────────────────────────────
def live_meeting_dirs() -> list[Path]:
    """AU_Racing 根目錄下嘅 live meeting folder（未歸檔嘅）。"""
    try:
        return sorted(p for p in AU_RACING.iterdir()
                      if p.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2} ", p.name))
    except OSError as exc:
        raise TemporaryFailure(f"讀唔到 AU_Racing（{type(exc).__name__}: {exc}）") from exc


def archived_meeting_names() -> set[str]:
    try:
        return {p.name for p in ARCHIVE_ROOT.iterdir() if p.is_dir()}
    except OSError:
        return set()


def meeting_day(folder: Path) -> date | None:
    try:
        return date.fromisoformat(folder.name[:10])
    except ValueError:
        return None


def race_numbers(folder: Path) -> list[int]:
    """由 Racecard 檔名數場次 —— 抽取一定寫呢個，Logic 就未必。"""
    numbers = set()
    for path in folder.glob("* Race * Racecard.md"):
        m = re.search(r"Race (\d+) Racecard\.md$", path.name)
        if m:
            numbers.add(int(m.group(1)))
    if not numbers:
        for path in folder.glob("Race_*_Logic.json"):
            m = re.search(r"Race_(\d+)_Logic\.json$", path.name)
            if m:
                numbers.add(int(m.group(1)))
    return sorted(numbers)


def find_meeting_dir(day: str, venue: str) -> Path | None:
    """live 根目錄同 Archive 一齊搵，回最新 mtime 嗰個。"""
    wanted = normalise(venue)
    hits: list[Path] = []
    for root in (AU_RACING, ARCHIVE_ROOT):
        try:
            for folder in root.iterdir():
                if folder.is_dir() and folder.name.startswith(day) \
                        and wanted in normalise(folder.name):
                    hits.append(folder)
        except OSError:
            continue
    if not hits:
        return None
    return sorted(hits, key=lambda p: p.stat().st_mtime_ns, reverse=True)[0]


def meeting_key(day: str, venue: str, n_races: int) -> str:
    """歷史命名慣例：`2026-08-01 Rosehill Gardens Race 1-10`。"""
    return f"{day} {venue} Race 1-{n_races}"


# ── meetingId 對應表 ────────────────────────────────────────────────────────
def load_mapping() -> dict:
    try:
        return json.loads(MEETING_IDS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_mapping(mapping: dict) -> None:
    """原子寫。呢個檔係 `sb_results.py` 攞賽果嘅唯一索引，寫崩就冇覆盤。

    ⚠️ 保持原本嘅**單行 compact** 格式。改成 indent 之後每次加一個場次都會出成個
    檔嘅 diff（1,540 行），真正嘅改動就淹死喺裡面。
    """
    tmp = MEETING_IDS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(mapping, ensure_ascii=False,
                              separators=(",", ":")), encoding="utf-8")
    tmp.replace(MEETING_IDS)


def ensure_mapping(runlog: RunLog, key: str, day: str, slug: str,
                   meeting_id: str, races: list[str]) -> None:
    """把場次寫入對應表。同名覆寫 = idempotent，唔會出重複 entry。"""
    mapping = load_mapping()
    entry = {"date": day, "slug": slug, "meetingId": str(meeting_id),
             "races": list(races)}
    if mapping.get(key) == entry:
        return
    mapping[key] = entry
    save_mapping(mapping)
    runlog.step("mapping-update", "ok", meeting=key, races=len(races))


def mapping_key_for(folder: Path) -> str | None:
    """meeting folder → 對應表 key。名一樣就直接用，否則靠日期+馬場配。"""
    mapping = load_mapping()
    if folder.name in mapping:
        return folder.name
    day = folder.name[:10]
    for key, meta in mapping.items():
        if meta.get("date") != day:
            continue
        if normalise(meta.get("slug", "")) in normalise(folder.name):
            return key
    return None


# ── 賽果 ────────────────────────────────────────────────────────────────────
def refresh_result_pages(runlog: RunLog, key: str) -> dict:
    """賽後重抓賽事頁，令 cache 有賽果行。

    ⚠️ 一定要 bypass cache —— 賽前抓落嚟嘅同一條 URL 冇賽果行，靠 cache 讀
    永遠都係「未跑」。撞到穩定拒絕就即刻停低，唔會敲落去。
    """
    from claw_sportsbet_form import BASE
    mapping = load_mapping()
    meta = mapping.get(key)
    if not meta:
        return {"refreshed": 0, "failed": 0, "reason": "對應表冇呢個場次"}
    if runlog.site_refusing:
        return {"refreshed": 0, "failed": 0, "reason": "個站今次 run 已經拒絕，唔敲門"}
    refreshed = failed = 0
    for race_id in meta["races"]:
        # 逐場一版，`force=True` 覆蓋賽前嗰版。`fetch_page` 撞到拒絕會 trip gate。
        html = fetch_page(runlog, f"{BASE}/{meta['meetingId']}/{race_id}/",
                          force=True, where=f"{key} 賽果頁重抓（raceId={race_id}）")
        if html:
            refreshed += 1
            continue
        failed += 1
        break
    return {"refreshed": refreshed, "failed": failed}


def build_results_file(runlog: RunLog, folder: Path, key: str) -> dict:
    """跑 `sb_results.py`。⚠️ 一定要傳 `--meeting-dir`，唔傳會寫落 CWD。"""
    rc, out = run_cmd([sys.executable, SB_RESULTS, "--meeting", key,
                       "--meeting-dir", str(folder)], timeout=1800)
    dest = folder / "Race_Results_Reflector.md"
    if rc != 0 or not dest.exists():
        return {"ok": False, "detail": out.splitlines()[-1] if out else f"rc={rc}"}
    text = dest.read_text(encoding="utf-8")
    found = sorted(int(m.group(1)) for m in re.finditer(r"^## Race (\d+)", text, re.M))
    return {"ok": True, "races_with_results": found}


# ── 步驟 1：覆盤 + 歸檔 ─────────────────────────────────────────────────────
def dashboard_au_meetings(runlog: RunLog) -> list[dict] | None:
    """live snapshot 上嘅 AU 場次。None = 攞唔到（唔可以安全決定歸檔邊個）。"""
    dest = download_live_snapshot(runlog, WORK_DIR / "live-dashboard-data.json")
    if dest is None:
        return None
    try:
        payload = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        runlog.warn(f"live snapshot 讀唔到：{exc}")
        return None
    return [{"date": str(m.get("date")), "venue": str(m.get("venue")),
             "key": f"{m.get('date')}|{m.get('venue')}"}
            for m in payload.get("meetings") or []
            if m.get("region") == "au"]


def corpus_meeting_days() -> set[str] | None:
    """`AU_Historical_Raw_Race_Results.csv` 有賽果嘅賽日。None = 讀唔到。

    ⚠️ 呢個 CSV 加上 `AU_Racing` **根目錄**嘅 meeting folder 就係 backtest 語料庫
    （`au_archive_calibrator.ARCHIVE_ROOT = AU_RACING`，而且用非遞歸 `iterdir()`）。
    所以「搬入 Archive/」= 由每個 backtest 消失。呢個 guard 就係唔畀自動化
    誤搬語料庫 —— 2026-08-04 實測過一次，33 個場次一鋪清袋。
    """
    import csv
    import signal as signal_module

    path = AU_RACING / "AU_Historical_Raw_Race_Results.csv"

    def _stall(*_):
        raise TimeoutError("Drive read stalled")

    previous = signal_module.signal(signal_module.SIGALRM, _stall)
    signal_module.alarm(90)
    try:
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            return {str(row.get("Date"))[:10] for row in csv.DictReader(handle)}
    except (OSError, ValueError, TimeoutError):
        return None
    finally:
        signal_module.alarm(0)
        signal_module.signal(signal_module.SIGALRM, previous)


# 補漏覆盤只回溯幾多日。收得緊係刻意：`AU_Racing` 根目錄同時係 backtest 語料庫
# （93 個場次），一個「掃晒舊場次」嘅規則會靜靜咁把成個語料庫搬入 Archive/。
REVIEW_BACKFILL_DAYS = 3


def unreviewed_local_meetings(review_day: date) -> list[dict]:
    """本機分析好、已經跑完、但 dashboard 從來冇過嘅場次。

    ⚠️ 覆盤名單本來淨係問 dashboard，理由係「錯過一晚，場次仍然掛喺 dashboard，
    下一晚照樣執行」。呢個前提喺**發佈失敗**嗰刻就唔成立：場次從來冇上過
    dashboard，所以永遠唔會排入覆盤。2026-08-07 實測：九個 08-08 場次分析齊咗，
    deploy 撞到 Cloudflare 25 MiB 上限失敗，於是佢哋既冇發佈、亦冇收過賽果、
    亦冇歸檔 —— 三樣嘢一次過靜咗。

    四道收窄，缺一不可：跑完咗、近 REVIEW_BACKFILL_DAYS 日、我哋真係評過分、
    未有覆盤報告。之後照樣行語料庫 guard。
    """
    out: list[dict] = []
    for folder in live_meeting_dirs():
        try:
            day = datetime.strptime(folder.name[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (review_day - timedelta(days=REVIEW_BACKFILL_DAYS) <= day <= review_day):
            continue
        if not list(folder.glob("Race_*_Auto_Analysis.md")):
            continue
        if (folder / f"{folder.name}_Reflector_Report.md").exists():
            continue
        key = archive_dashboard_key(folder.name)
        out.append({"key": key, "date": key.split("|")[0],
                    "venue": key.split("|")[1]})
    return out


def step_review_archive(runlog: RunLog, review_day: date, *,
                        no_archive: bool = False) -> list[str]:
    """覆盤 + 歸檔 **dashboard 上** 已跑完嘅場次。

    ⚠️ 揀場次嘅準則係「而家喺 live dashboard 上」，唔係「日期 <= 今日」。
    `AU_Racing` 根目錄同時係 backtest 語料庫，「所有舊場次都歸檔」會靜靜咁
    刪走成個語料庫。dashboard 成員資格同時亦係天然嘅後帳清單 —— 錯過一晚，
    場次仍然掛喺 dashboard，下一晚照樣執行。

    唔會歸檔：冇賽果（腰斷／改期／未出成績）、賽果唔齊、語料庫已收錄。
    """
    runlog.step("review-archive", "start", review_day=review_day.isoformat())
    archived: list[str] = []

    on_dashboard = dashboard_au_meetings(runlog)
    if on_dashboard is None:
        raise TemporaryFailure("攞唔到 live dashboard snapshot —— "
                               "唔知邊個場次應該歸檔，今次唔動任何 folder")

    due = [m for m in on_dashboard
           if m["date"] and date.fromisoformat(m["date"]) <= review_day]
    seen = {m["key"] for m in due}
    missed = [m for m in unreviewed_local_meetings(review_day)
              if m["key"] not in seen]
    if missed:
        runlog.warn(f"本機有 {len(missed)} 個已分析場次跑完咗但 dashboard 從來冇過"
                    f"（大概發佈失敗）—— 一併覆盤：{[m['key'] for m in missed]}")
        due += missed
    runlog.step("review-archive", "dashboard-scan",
                au_on_dashboard=[m["key"] for m in on_dashboard],
                due=[m["key"] for m in due])
    if not due:
        runlog.step("review-archive", "nothing-to-do")
        return archived

    corpus_days = corpus_meeting_days()
    if corpus_days is None:
        runlog.warn("讀唔到歷史賽果 CSV，語料庫 guard 今次唔可用（照行 dashboard 準則）")

    candidates: list[Path] = []
    for meeting in due:
        folder = find_meeting_dir(meeting["date"], meeting["venue"])
        if folder is None:
            runlog.meeting(meeting["key"], "no_local_folder",
                           detail="dashboard 有但本機冇 folder；dashboard build "
                                  "會照 Archive filter 處理")
            continue
        if folder.parent == ARCHIVE_ROOT:
            runlog.meeting(folder.name, "already_archived")
            archived.append(folder.name)
            continue
        if corpus_days is not None and meeting["date"] in corpus_days:
            runlog.meeting(folder.name, "archive_blocked_corpus",
                           detail="歷史賽果 CSV 已收錄呢個賽日 —— 搬走會由 "
                                  "backtest 語料庫消失，要人手決定")
            continue
        candidates.append(folder)

    for folder in candidates:
        try:
            outcome = review_one_meeting(runlog, folder, no_archive=no_archive,
                                         today=review_day)
        except TemporaryFailure as exc:
            # 一個場次暫時失敗唔應該停晒其他場次。
            runlog.meeting(folder.name, "temporary_failure", detail=str(exc))
            continue
        except Exception as exc:  # noqa: BLE001
            runlog.meeting(folder.name, "failed", detail=f"{type(exc).__name__}: {exc}")
            runlog.error("review-archive", f"{folder.name}: {exc}")
            continue
        if outcome.get("archived"):
            archived.append(folder.name)
            runlog.data["races_archived"].append(
                {"meeting": folder.name, "races": outcome.get("races", [])})
    runlog.step("review-archive", "done", archived=len(archived),
                candidates=len(candidates))
    return archived


# 賽果最多等幾日。實測 Sportsbet 係當晚就把賽果寫入馬匹往績（08-05 五個場次
# 22:24 已經齊），所以兩日係四倍緩衝。過咗就當「永遠唔會有」——取消／改期嘅場次
# 冇呢個上限會每晚白抽一次賽果頁、永遠 pending_results、永遠霸住 dashboard。
# ⚠️ 呢度故意唔靠索引頁「冇開跑時間」做取消偵測：實測嗰個訊號唔可靠（導覽同頁腳
# 項目一律 parse 成 0 場、`Murray Bridge` 同 `Mt Isa` 配對唔到、隔日索引頁根本冇
# 馬場行）。用一個會假陽性嘅訊號去決定移除場次，代價太大。
RESULTS_GIVE_UP_DAYS = 2


def results_overdue(folder: Path, today: date) -> int | None:
    """賽日過咗幾日（超過上限先回數字，否則 None）。"""
    try:
        day = datetime.strptime(folder.name[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    age = (today - day).days
    return age if age > RESULTS_GIVE_UP_DAYS else None


def date_has_results_elsewhere(day: str, exclude: Path) -> bool:
    """同一個賽日，另一個場次有冇收到賽果？

    ⚠️ 呢個就係「賽果傳播正唔正常」嘅證據。一個場次零賽果有兩個解釋 ——
    成個腰斷，或者賽果仲未傳到 —— 淨睇佢自己分唔到。但**同日另一個場次收到
    賽果**就排除咗第二個：傳播行緊。2026-08-09 Wagga 七場零賽果、零匹馬有當日
    出賽紀錄，而同日四個場次全部收齊並歸檔咗 —— 得一個解釋。
    """
    for base in (AU_RACING, ARCHIVE_ROOT):
        try:
            entries = list(base.glob(f"{day} *"))
        except OSError:
            continue
        for d in entries:
            if d == exclude or not d.is_dir():
                continue
            res = d / "Race_Results_Reflector.md"
            try:
                if res.exists() and res.stat().st_size > 200:
                    return True
            except OSError:
                continue
    return False


def archive_meeting(runlog: RunLog, folder: Path, races: list) -> dict:
    """搬入 Archive/。撞名唔覆蓋 —— 留返俾人手決定。"""
    destination = ARCHIVE_ROOT / folder.name
    if destination.exists():
        runlog.meeting(folder.name, "archive_conflict",
                       detail=f"Archive 已經有 {destination.name}")
        return {"races": races}
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.move(str(folder), str(destination))
    runlog.meeting(folder.name, "archived", races=races)
    return {"archived": True, "races": races}


def review_one_meeting(runlog: RunLog, folder: Path, *,
                       no_archive: bool = False,
                       today: date | None = None) -> dict:
    expected = race_numbers(folder)
    key = mapping_key_for(folder)
    if not key:
        # 對應表冇 = 從來未由索引頁解過 ID。試由當日索引補返。
        day = folder.name[:10]
        try:
            index = fetch_date_index(runlog, day)
        except TemporaryFailure as exc:
            runlog.meeting(folder.name, "pending_results",
                           reason=f"對應表冇 ID，索引頁又攞唔到：{exc}")
            return {}
        slug = index_slug_for(index, folder.name)
        if slug:
            key = folder.name
            ensure_mapping(runlog, key, day, slug, index[slug]["meetingId"],
                           index[slug]["races"])
        if not key:
            runlog.meeting(folder.name, "pending_results",
                           reason="索引頁搵唔到對應馬場")
            return {}

    report = folder / f"{folder.name}_Reflector_Report.md"
    results = folder / "Race_Results_Reflector.md"

    if not report.exists():
        # ⚠️ 判斷「要唔要重抓賽果頁」一定要睇**覆蓋率**，唔可以睇「賽果檔存唔存在」。
        # 舊寫法係 `if not results.exists(): refresh`，於是一個半份賽果檔（例如
        # 晚更跑嗰陣最後一場仲未跑完）會令之後每次 run 都跳過重抓、由同一份舊
        # cache 重建同一份半份賽果 —— 嗰個場次永遠 partial_results、永遠唔會歸檔、
        # 永遠留喺 dashboard。
        built = build_results_file(runlog, folder, key) if results.exists() \
            else {"ok": False, "races_with_results": []}
        covered = built.get("races_with_results") or []
        refreshed_this_run = False
        if len(covered) < len(expected):
            refreshed_this_run = True
            refresh = refresh_result_pages(runlog, key)
            runlog.step("results-refresh", "done", meeting=folder.name,
                        had_before=len(covered), expected=len(expected), **refresh)
            built = build_results_file(runlog, folder, key)
        overdue = results_overdue(folder, today or date.today())
        if not built.get("ok") and refreshed_this_run and \
                date_has_results_elsewhere(folder.name[:10], folder):
            # 新鮮重抽之後一場賽果都冇，而同日其他場次收到咗 —— 傳播正常，
            # 即係成個場次冇跑過。唔使等兩日上限，第二朝就有答案。
            runlog.warn(f"{folder.name}：新鮮重抽之後零賽果，而同日其他場次已經"
                        f"收到賽果 —— 當成個場次腰斷／棄賽，歸檔")
            runlog.meeting(folder.name, "meeting_abandoned",
                           expected_races=len(expected))
            if no_archive:
                return {"races": expected}
            return archive_meeting(runlog, folder, expected)
        if not built.get("ok"):
            if overdue is not None:
                # 等夠日子都冇賽果 —— 當係取消／改期。搬入 Archive/ 令佢離開
                # dashboard 同停止每晚重抽。Archive/ 唔係刪除，要覆盤可以搬返出嚟。
                runlog.warn(f"{folder.name}：賽日過咗 {overdue} 日仍然冇任何賽果，"
                            f"當係取消／改期 —— 歸檔（唔會有覆盤報告）")
                runlog.meeting(folder.name, "archived_unresolved",
                               days_overdue=overdue, expected_races=len(expected))
                if no_archive:
                    return {"races": expected}
                return archive_meeting(runlog, folder, expected)
            runlog.meeting(folder.name, "pending_results",
                           reason=built.get("detail", "賽果生成失敗"),
                           expected_races=len(expected))
            return {}
        found = built["races_with_results"]
        if len(found) < len(expected) and refreshed_this_run and found:
            # ⚠️ 同一次新鮮抽取入面，部分場次有賽果、部分冇 —— 呢個組合本身就係
            # 證據：有賽果嗰幾場證明咗賽果傳播正常，所以冇賽果嗰幾場係真係冇跑
            # （腰斷／棄賽），唔係「未出」。2026-08-09 Ballarat Synthetic 實測：
            # 八版同一分鐘內抽返，R1–R4 嘅馬最近一戰係 08-09，R5–R8 係七月。
            #
            # 三道收窄缺一不可：頁面**今次真係重抽過**（唔係讀舊 cache）、同場
            # **至少有一場出到賽果**（否則只係傳播未到）、而且賽日已經過去。
            # 冇呢三道就會把「賽果遲咗少少」誤判成腰斷，靜靜咁少報幾場。
            runlog.warn(f"{folder.name}：新鮮重抽之後仍然得 {len(found)}/"
                        f"{len(expected)} 場有賽果，而同場其他場次抽到 —— "
                        f"當餘下嘅係腰斷／棄賽，照覆盤已跑嘅部分")
            runlog.meeting(folder.name, "partial_meeting_abandoned",
                           races_with_results=found,
                           not_run=sorted(set(expected) - set(found)))
        elif len(found) < len(expected):
            # 唔齊唔歸檔。可能係腰斷／改期／賽果未出，全部要人手睇。
            if overdue is not None:
                runlog.warn(f"{folder.name}：賽日過咗 {overdue} 日，賽果仍然只有 "
                            f"{len(found)}/{len(expected)} 場 —— 歸檔，唔再等")
                runlog.meeting(folder.name, "archived_unresolved",
                               days_overdue=overdue, races_with_results=found,
                               missing=sorted(set(expected) - set(found)))
                if no_archive:
                    return {"races": expected}
                return archive_meeting(runlog, folder, expected)
            runlog.meeting(folder.name, "partial_results",
                           expected_races=expected, races_with_results=found,
                           missing=sorted(set(expected) - set(found)))
            return {}
        rc, out = run_cmd([sys.executable, REFLECTOR, str(folder),
                           "--skip-backtest"], timeout=3600)
        if rc != 0 or not report.exists():
            runlog.meeting(folder.name, "reflection_failed",
                           detail=out.splitlines()[-1] if out else f"rc={rc}")
            return {}
    else:
        runlog.step("reflection", "skipped-already-done", meeting=folder.name)

    if no_archive:
        runlog.meeting(folder.name, "reviewed_not_archived", races=expected)
        return {"races": expected}

    return archive_meeting(runlog, folder, expected)


# ── 步驟 2：分析下一個賽日 ─────────────────────────────────────────────────
def step_analyse_next_day(runlog: RunLog, review_day: date, *,
                          max_meetings: int = 0, rounds: int = 1,
                          round_gap: int = 900,
                          target_day: str | None = None) -> list[Path]:
    """發現 → 抽取 → 分析一個賽日嘅所有場次。回新分析好嘅目錄。

    `target_day` 唔畀就揀下一個可用賽日（晚更）。畀嘅話就做嗰日 —— 早更用嚟
    **補完當日賽日**。⚠️ 冇呢條路嘅話，一晚俾個站拒絕就等於嗰個賽日永久流失：
    晚更聽日嘅目標係再下一日，早更又淨係覆核已發佈嘅場次。2026-08-08 實測：
    六個 08-09 場次抽到一個，其餘五個 pending，冇任何後續步驟會再碰佢哋。
    """
    runlog.step("analyse-next-day", "start")
    events = api_next_events(runlog)
    by_day = events_by_day(events)
    if target_day:
        target = target_day
    else:
        future = sorted(d for d in by_day if date.fromisoformat(d) > review_day)
        if future:
            target = future[0]
        else:
            target = (review_day + timedelta(days=1)).isoformat()
            runlog.warn(f"NextEvents 冇下一個賽日資料，退回 {target}")

    api_venues = by_day.get(target, {})
    index = fetch_date_index(runlog, target)
    if not index:
        raise TemporaryFailure(f"{target} 索引頁冇任何場次")

    runlog.step("discover", "ok", race_day=target, index_meetings=len(index),
                api_venues=sorted(api_venues))

    # 索引頁係 meetingId / raceId 嘅權威，API 係「係唔係澳洲賽事 + 官方場地狀況」
    # 嘅權威。⚠️ 索引頁**唔止澳洲** —— 2026-08-05 嗰版 12 個場次裡面 6 個係英國／
    # 愛爾蘭／南非／加拿大（lingfield、pontefract、roscommon、kenilworth、
    # brighton、assiniboia_downs）。所以 API 配對係硬性要求，唔係警告：配唔到
    # 就唔分析，並且喺 log 列出被剔走嘅場次。
    if not api_venues:
        raise TemporaryFailure(
            f"{target} 攞唔到 API 澳洲場次名單 —— 唔可以由索引頁分辨澳洲同海外，"
            f"今次唔分析（索引頁有 {len(index)} 個場次）")

    planned: list[dict] = []
    excluded: list[str] = []
    for slug, meta in sorted(index.items()):
        match = match_venue(slug, sorted(api_venues))
        if not match:
            excluded.append(slug)
            continue
        planned.append({"slug": slug, "venue": match,
                        "meetingId": meta["meetingId"], "races": meta["races"],
                        "going": normalise_going(api_venues[match].get("going"))})
    if excluded:
        runlog.step("discover", "non-au-excluded", meetings=excluded,
                    reason="API 澳洲名單冇呢啲馬場")
    if not planned:
        raise TemporaryFailure(f"{target} 索引頁一個澳洲場次都配唔到")
    if max_meetings and len(planned) > max_meetings:
        dropped = [p["venue"] for p in planned[max_meetings:]]
        runlog.warn(f"--max-meetings={max_meetings}：略過 {len(dropped)} 個場次 "
                    f"{dropped}（唔係靜靜咁截，記低喺 log）")
        planned = planned[:max_meetings]

    # 實測（2026-08-05）：一個冷卻窗大約夠抽**一個**場次，之後個站又拒絕。所以
    # 「gate 一 trip 就放棄餘下場次」對一個 22:00 通宵 job 嚟講太早收工 ——
    # 由 22:00 到早更 10:00 有十二個鐘，等一陣再續係免費嘅。每一輪之間 gate 會
    # reset，已經抽好嘅場次全部 cache 命中，所以續跑唔會重打。
    analysed: list[Path] = []
    remaining = list(planned)
    dry_rounds = 0
    gap = round_gap
    for round_no in range(1, max(1, rounds) + 1):
        if not remaining:
            break
        if round_no > 1:
            runlog.step("analyse-next-day", "cooldown", round_no=round_no,
                        sleep_seconds=gap, dry_rounds=dry_rounds,
                        waiting_for=[p["venue"] for p in remaining])
            time.sleep(gap)
            runlog.site_refusing = False
        still: list[dict] = []
        progress = False
        for plan in remaining:
            try:
                folder, complete, gained = analyse_one_meeting(runlog, target, plan)
            except TemporaryFailure as exc:
                runlog.meeting(f"{target} {plan['venue']}", "pending_extraction",
                               detail=str(exc), round_no=round_no)
                still.append(plan)
                continue
            except Exception as exc:  # noqa: BLE001
                runlog.meeting(f"{target} {plan['venue']}", "failed",
                               detail=f"{type(exc).__name__}: {exc}")
                runlog.error("analyse-next-day", f"{plan['venue']}: {exc}")
                continue
            progress = progress or gained
            if folder is not None and folder not in analysed:
                analysed.append(folder)
            if not complete:
                # 半份抽取 —— 留喺清單，下一輪補齊剩低嘅場次。
                still.append(plan)
        # ⚠️ 「進展」要係**真嘅多咗場次**，唔係「冇拋 exception」。三個版本嘅坑：
        #   1. `not analysed`      —— 第一輪抽到一個之後就永遠唔 fire。
        #   2. len(still)==len(remaining) —— 半份場次留喺清單，個數一樣但有進展。
        #   3. 「冇 exception 就算進展」  —— 一個零增長嘅半份場次會令 dry_rounds
        #      永遠歸零，白等足六輪。所以要問 `gained`。
        if not progress:
            dry_rounds += 1
            # 退避：冷卻明顯長過 10 分鐘（實測），所以每次乾等就等長啲。
            gap = min(int(gap * 1.6), 3600)
        else:
            dry_rounds = 0
            gap = round_gap
        remaining = still
        if dry_rounds >= 3:
            runlog.warn(f"連續 {dry_rounds} 輪零進展 —— 當係真封鎖唔係冷卻，"
                        f"停止今晚嘅抽取，餘下交下一次排程")
            break
    if remaining:
        runlog.step("analyse-next-day", "still-pending",
                    meetings=[p["venue"] for p in remaining],
                    detail="下一次排程會續，已抽嘅場次全部 cache 命中唔會重打")
    runlog.step("analyse-next-day", "done", race_day=target,
                planned=len(planned), analysed=len(analysed),
                pending=len(remaining))
    return analysed


def warm_race_pages(runlog: RunLog, meeting_id: str, race_ids: list[str],
                    label: str) -> list[str]:
    """**逐場**攞賽事頁落 cache。撞到拒絕即刻停，回已經有 cache 嘅 raceId。

    ⚠️ 點解唔直接交 `claw_sportsbet_form.py` 成個馬場：佢內部個 loop 撞到一場
    403 之後會「跳過，繼續下一場」，於是一個已經明講唔得嘅站會俾我哋逐場再敲
    三次門（2026-08-05 實測 Canterbury 7 場 × 3 次）。喺呢度逐場暖 cache，第一場
    穩定拒絕就收手；之後 claw 全程 cache 命中（`WC_SB_CACHE_ONLY=1` 之下佢連想出
    網都唔可以），一個請求都唔會出。
    """
    from claw_sportsbet_form import BASE
    from sb_browser_fetch import cache_path
    ready: list[str] = []
    for index, race_id in enumerate(race_ids, 1):
        url = f"{BASE}/{meeting_id}/{race_id}/"
        if cache_path(url).exists():
            ready.append(race_id)
            continue
        if runlog.site_refusing:
            break
        if fetch_page(runlog, url, where=f"{label} 第 {index} 場（raceId={race_id}）"):
            ready.append(race_id)
            continue
        break
    return ready


def warm_people_pages(runlog: RunLog, race_ids: list[str], meeting_id: str,
                      label: str, limit: int | None = None,
                      force: bool = False) -> dict:
    """由已 cache 嘅賽事頁抽騎師／練馬師 ID，逐個把個人頁落 cache。

    ⚠️ 冇呢一步，`write_meeting` 之後嗰個 `sb_people_stats.refresh` 讀唔到個人頁，
    `(LY: N:w-p-s)` 全部變 `-`，而個 token 就係騎練往績入口 —— 覆蓋率由
    99%/95% 跌到 63%/51%（見 `sb_people_stats.refresh` docstring）。以前呢步靠
    curl_cffi 出網，靜靜咁 403 失敗；而家一律行真瀏覽器。
    """
    from claw_sportsbet_form import BASE
    from sb_browser_fetch import cache_path
    if limit is None:
        try:
            limit = int(os.environ.get("WC_AU_PEOPLE_PER_MEETING", "40"))
        except ValueError:
            limit = 40

    wanted: list[str] = []
    for race_id in race_ids:
        page = cache_path(f"{BASE}/{meeting_id}/{race_id}/")
        if not page.exists():
            continue
        for kind, pid in re.findall(r'href="/(Jockey|Trainer)/(\d+)/"',
                                    page.read_text(encoding="utf-8", errors="replace")):
            url = f"{BASE}/{kind}/{pid}/"
            # `force`（晚更）連已 cache 嘅都重抽 —— 「去年官方」係滾動 12 個月
            # 紀錄，賽季中段會變，21 日 TTL 之下最多滯後 3 個星期。
            if url not in wanted and (force or not cache_path(url).exists()):
                wanted.append(url)

    if not wanted:
        return {"needed": 0, "fetched": 0}
    dropped = wanted[limit:]
    todo = wanted[:limit]
    if dropped:
        runlog.warn(f"{label}: 個人頁今次只補 {len(todo)}/{len(wanted)}，"
                    f"餘下 {len(dropped)} 個下次補（TTL cache 會累積）")
    fetched = 0
    for url in todo:
        if runlog.site_refusing:
            break
        if fetch_page(runlog, url, force=force, where=f"{label} 個人頁"):
            fetched += 1
        else:
            break
    runlog.step("warm-people", "ok" if fetched == len(todo) else "partial",
                meeting=label, needed=len(wanted), fetched=fetched)
    return {"needed": len(wanted), "fetched": fetched}


def apply_ra_ratings(runlog: RunLog, folder: Path, day: str, venue: str) -> dict:
    """由 Racing Australia 補官方讓磅分入 Racecard，跟住落 Facts/Logic 就有值。

    ⚠️ 一定要喺 claw 之後、`au_orchestrator` 之前跑 —— claw 寫 Racecard（Sportsbet
    個 rating 欄實測 1,321 匹 **0%** 有值，所以全部寫 `Rating: -`），orchestrator
    再由 Racecard 砌 Facts/Logic。喺中間補返個數字，成條下游自動接上。

    ⚠️ RA 行 curl_cffi（實測 200），**唔經** `BrowserFetcher`，亦唔用 Sportsbet
    個 cache —— 兩個來源完全分離，所以 RA 唔會食 Sportsbet 嘅 rate budget，
    而 `WC_SB_CACHE_ONLY=1` 亦唔會擋住佢。

    失敗一律非致命：補唔到就照用 fallback（實測 fallback AUC 0.587 vs 官方 0.591）。
    """
    try:
        sys.path.insert(0, str(AU_SKILL))
        import ra_fields
        result = ra_fields.apply_to_meeting(
            folder, day, venue, ra_fields.Fetcher(delay=6.0, verbose=False))
    except Exception as exc:  # noqa: BLE001
        runlog.warn(f"{folder.name}: RA 讓磅分補唔到（{type(exc).__name__}: {exc}）"
                    f"—— 照用 fallback")
        return {"ok": False}
    if not result.get("ok"):
        runlog.warn(f"{folder.name}: RA 冇呢個場次（{result.get('reason')}）—— 照用 fallback")
        return result
    runlog.step("ra-ratings", "ok", meeting=folder.name,
                filled=result["filled"],
                no_official=result["no_official_rating"],
                ra_venue=result["ra_venue"])
    return result


def meeting_is_complete(have: list, scored: list, expected: int) -> bool:
    """一個場次「做完」= 抽到嘅場數同評到嘅場數都到齊索引話有嘅數。

    ⚠️ **唔可以**用「`Meeting_Summary.md` 存在」做完成標記。2026-08-05 實測：
    Hobart 抽到第 1 場就俾個站拒絕，`Meeting_Summary.md` 已經寫落去，於是下一次
    run 當佢做完，餘下 8 場永遠冇人補。
    """
    return expected > 0 and len(have) >= expected and len(scored) >= expected


def analyse_one_meeting(runlog: RunLog, day: str, plan: dict) -> tuple:
    """抽取 + 評分一個場次。**可以續**：半份抽取下一次會補齊。

    ⚠️ 「已經做完」唔可以只睇 `Meeting_Summary.md` 存在。2026-08-05 實測：Hobart
    第一版之後就俾個站拒絕，於是個 folder 只有 1 場但 `Meeting_Summary.md` 已經寫
    咗，下一次 run 見到就當「已完成」跳過 —— 餘下 8 場永遠冇人補。所以完成嘅定義
    係 **抽到嘅場數 >= 索引話有嘅場數**，唔夠就照續抽（已有嘅版全部 cache 命中）。
    """
    venue, races = plan["venue"], plan["races"]
    expected = len(races)
    existing = find_meeting_dir(day, venue)

    if existing is not None and existing.parent == ARCHIVE_ROOT:
        runlog.meeting(existing.name, "skipped_already_archived")
        return None, True, False

    have = race_numbers(existing) if existing is not None else []
    scored = sorted(int(re.search(r"Race_(\d+)_", p.name).group(1))
                    for p in existing.glob("Race_*_Auto_Analysis.md")) \
        if existing is not None else []
    complete = existing is not None and meeting_is_complete(have, scored, expected)

    if complete:
        runlog.meeting(existing.name, "skipped_already_analysed", races=len(scored))
        return existing, True, False

    if runlog.site_refusing and len(have) >= expected:
        # 頁都齊，只係未評分 —— 評分係純本機，唔使出網，照做。
        folder = existing
    elif runlog.site_refusing:
        raise TemporaryFailure("個站今次 run 已經明確拒絕，唔再敲門")
    else:
        folder = existing if existing is not None \
            else AU_RACING / meeting_key(day, venue, expected)
        ready = warm_race_pages(runlog, plan["meetingId"], races,
                                f"{day} {venue}")
        if not ready:
            raise TemporaryFailure("一場賽事頁都攞唔到（個站拒絕）")
        if len(ready) < expected:
            runlog.warn(f"{day} {venue}: 攞到 {len(ready)}/{expected} 場就停手，"
                        f"照分析攞到嗰啲，餘下等下一輪／下一次排程補")
        # 個人頁一定要喺 claw 之前落 cache —— claw 跑 `WC_SB_CACHE_ONLY=1`，
        # 唔會（亦唔可以）自己出網補。
        # ⚠️ 晚更 `force=True`：每個場次都重抽騎練統計（Kelvin 2026-08-05 決定）。
        # 晚更有十二個鐘，一個場次 90–100 個人物 × 25 秒 ≈ 40 分鐘，做得到；
        # 早更（10:00 → 最早一場 11:44）唔得，所以早更路徑唔會 force。
        warm_people_pages(runlog, ready, plan["meetingId"], f"{day} {venue}",
                          force=True)
        rc, out = run_cmd([sys.executable, CLAW,
                           "--meeting-url", f"https://www.sportsbetform.com.au/"
                                            f"{plan['meetingId']}/{ready[0]}/",
                           "--races", ",".join(ready),
                           "--out-dir", str(folder),
                           "--date", day, "--venue", venue,
                           "--delay", str(fetch_delay())],
                          cwd=AU_SKILL, timeout=7200)
        if rc != 0 or not (folder / "Meeting_Summary.md").exists():
            raise TemporaryFailure(
                f"抽取未完成（rc={rc}）：{out.splitlines()[-1] if out else '冇輸出'}")
        # 官方讓磅分：Sportsbet 冇，RA 有。一定要喺落 Facts/Logic 之前補。
        apply_ra_ratings(runlog, folder, day, venue)

    ensure_mapping(runlog, folder.name, day, plan["slug"], plan["meetingId"], races)

    got = race_numbers(folder)
    if not got:
        raise TemporaryFailure("抽取完但一場 Racecard 都冇")
    partial = len(got) < expected
    if partial:
        runlog.warn(f"{folder.name}: 索引話 {expected} 場，而家有 {len(got)} 場 "
                    f"{got} —— 照評分，未齊嘅下一輪補")

    # `--race-workers 1`：逐場處理，唔並行。並行只係省本機時間，但會令 log 交織
    # 難讀，而且一場出事嘅時候唔清楚係邊場。
    cmd = [sys.executable, AU_ORCH, str(folder), "--auto", "--skip-cloudflare-deploy",
           "--race-workers", "1"]
    if plan["going"]:
        cmd += ["--going", plan["going"]]
    else:
        runlog.warn(f"{folder.name}: 冇官方場地狀況，用 Logic 內嘅值評分")
    rc, out = run_cmd(cmd, timeout=10800)
    scored = sorted(int(re.search(r"Race_(\d+)_", p.name).group(1))
                    for p in folder.glob("Race_*_Auto_Analysis.md"))
    if rc != 0 and not scored:
        raise TemporaryFailure(
            f"分析失敗（rc={rc}）：{out.splitlines()[-1] if out else '冇輸出'}")
    if rc != 0:
        runlog.warn(f"{folder.name}: orchestrator rc={rc} 但有 {len(scored)} 場出咗分，"
                    f"當部分成功處理")
    complete = len(scored) >= expected and not partial
    # ⚠️ 呢個先係真正「分析時」嘅賠率 —— 一定要喺呢刻影，因為之後任何重建都會
    # 覆寫 Formguide。
    record_odds_snapshot(folder, "analysis")
    runlog.meeting(folder.name, "analysed" if complete else "analysed_partial",
                   races=scored, expected=expected, going=plan["going"] or None)
    runlog.data["races_added"].append({"meeting": folder.name, "races": scored,
                                       "expected_races": expected,
                                       "complete": complete,
                                       "going": plan["going"] or None})
    return folder, complete, len(got) > len(have)


# ── 步驟 3（morning）：場地 / 退出馬 / 人馬變動 ─────────────────────────────
MATERIAL_FIELDS = ("going", "scratchings", "jockeys", "barriers", "field_size")


def step_refresh_active(runlog: RunLog, today: date, *, max_meetings: int = 0,
                        rounds: int = 1, round_gap: int = 420) -> list[Path]:
    """重新確認 live dashboard 上每個場次嘅最新資料，有實質變動先重新評分。"""
    runlog.step("refresh-active", "start")
    # 同 review 一樣，準則係「而家掛喺 dashboard」而唔係 folder 日期 ——
    # 咁樣就唔會摸到 `AU_Racing` 根目錄嗰批 backtest 語料庫場次。
    on_dashboard = dashboard_au_meetings(runlog)
    if on_dashboard is None:
        raise TemporaryFailure("攞唔到 live dashboard snapshot —— 唔知要覆核邊個場次")
    folders: list[Path] = []
    for meeting in on_dashboard:
        if not meeting["date"] or date.fromisoformat(meeting["date"]) < today:
            # 已跑完嘅場次冇「最新退出馬」可言，交畀 evening job 覆盤／歸檔。
            continue
        folder = find_meeting_dir(meeting["date"], meeting["venue"])
        if folder is None or folder.parent == ARCHIVE_ROOT:
            runlog.meeting(meeting["key"], "refresh_skipped",
                           reason="本機冇 live folder")
            continue
        folders.append(folder)
    if max_meetings and len(folders) > max_meetings:
        dropped = [f.name for f in folders[max_meetings:]]
        runlog.warn(f"--max-meetings={max_meetings}：今次唔覆核 {dropped}"
                    f"（唔係靜靜咁截，記低喺 log）")
        folders = folders[:max_meetings]
    runlog.step("refresh-active", "dashboard-scan",
                au_on_dashboard=[m["key"] for m in on_dashboard],
                to_check=[f.name for f in folders])
    if not folders:
        runlog.step("refresh-active", "nothing-to-do")
        return []

    events = api_next_events(runlog)
    api = events_by_day(events)
    updated: list[Path] = []
    remaining = list(folders)
    dry_rounds = 0
    gap = round_gap
    for round_no in range(1, max(1, rounds) + 1):
        if not remaining:
            break
        if round_no > 1:
            # ⚠️ 早更嘅窗口比晚更窄好多（10:00 開工，最早一場大約 11:44 開跑），
            # 所以 plist 傳細啲嘅 --rounds / --round-gap。
            runlog.step("refresh-active", "cooldown", round_no=round_no,
                        sleep_seconds=gap,
                        waiting_for=[f.name for f in remaining])
            time.sleep(gap)
            runlog.site_refusing = False
        still: list[Path] = []
        for folder in remaining:
            try:
                changed = refresh_one_meeting(runlog, folder, api)
            except TemporaryFailure as exc:
                runlog.meeting(folder.name, "refresh_deferred", detail=str(exc),
                               round_no=round_no)
                still.append(folder)
                continue
            except Exception as exc:  # noqa: BLE001
                runlog.meeting(folder.name, "failed",
                               detail=f"{type(exc).__name__}: {exc}")
                runlog.error("refresh-active", f"{folder.name}: {exc}")
                continue
            if changed and folder not in updated:
                updated.append(folder)
        if len(still) == len(remaining):
            dry_rounds += 1
            gap = min(int(gap * 1.6), 1800)
        else:
            dry_rounds = 0
            gap = round_gap
        remaining = still
        if dry_rounds >= 2:
            runlog.warn(f"連續 {dry_rounds} 輪覆核唔到 —— 停止覆核，"
                        f"現有分析保持不變（唔會用半份資料去改分）")
            break
    if remaining:
        runlog.step("refresh-active", "still-pending",
                    meetings=[f.name for f in remaining],
                    detail="呢啲場次今次覆核唔到，分析保持原狀")
    runlog.step("refresh-active", "done", checked=len(folders),
                updated=len(updated), pending=len(remaining))
    return updated


def stored_race_state(folder: Path) -> dict[int, dict]:
    """由 Logic.json 讀返分析當時用嘅資料。"""
    state: dict[int, dict] = {}
    for path in sorted(folder.glob("Race_*_Logic.json")):
        m = re.search(r"Race_(\d+)_Logic\.json$", path.name)
        if not m:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        horses = data.get("horses") or {}
        state[int(m.group(1))] = {
            "going": normalise_going((data.get("race_analysis") or {}).get("going")),
            "jockeys": {str(k): str((v or {}).get("jockey") or "").strip()
                        for k, v in horses.items() if isinstance(v, dict)},
            "barriers": {str(k): str((v or {}).get("barrier") or "").strip()
                         for k, v in horses.items() if isinstance(v, dict)},
            "field": sorted(str(k) for k in horses),
        }
    return state


# ⚠️ 索引頁 slug 同場次夾名唔一定對得上，所以配對一定要用 `match_venue`，
# 唔可以用「slug 係唔係場次名嘅子串」。2026-08-12 實測：索引頁係
# `devonport_synthetic` 而場次夾係 `Devonport`，子串比對永遠唔中，於是重新推導
# 報「索引頁亦搵唔到對應馬場」。`match_venue` 已經處理呢類（Mt Isa / Murray Bdge
# 都係同一族），六個真 slug 全部配得中而且唔會亂配。
def index_slug_for(index: dict, folder_name: str) -> str | None:
    venue = re.sub(r"\s+Race\s+[\d\-]+$", "", folder_name[11:]).strip()
    for slug in index:
        if match_venue(slug, [venue]):
            return slug
    return None


def live_race_state(runlog: RunLog, folder: Path) -> tuple[dict[int, dict], str]:
    """重抓賽事頁 → 每場最新 going / 退出馬 / 騎師 / 檔位 / 馬匹數。"""
    from claw_sportsbet_form import BASE, parse_race, parse_runner_blocks
    key = mapping_key_for(folder)
    if not key:
        # ⚠️ 攞唔到就由當日索引頁重新推導 —— 覆盤路徑一直有做呢步，覆核冇，於是
        # 對應表一有缺失就直接放棄。2026-08-12 實測：五個場次因為對應表俾自動更新
        # 抹走，覆核全部報 `refresh_deferred`，退出馬同場地變化一個都冇覆核到。
        # 對應表係由索引頁推導出嚟嘅，所以缺失係補得返嘅，唔應該當成死路。
        day = folder.name[:10]
        try:
            index = fetch_date_index(runlog, day)
        except TemporaryFailure as exc:
            raise TemporaryFailure(
                f"對應表冇呢個場次，而索引頁又攞唔到（{exc}）") from exc
        slug = index_slug_for(index, folder.name)
        if slug:
            meta_i = index[slug]
            ensure_mapping(runlog, folder.name, day, slug,
                           meta_i["meetingId"], meta_i["races"])
            key = folder.name
            runlog.step("mapping-rederived", "ok", meeting=folder.name,
                        slug=slug)
        else:
            raise TemporaryFailure(
                f"對應表冇呢個場次，索引頁亦搵唔到對應馬場"
                f"（索引有：{sorted(index)[:8]}）")
    if runlog.site_refusing:
        raise TemporaryFailure("個站今次 run 已經拒絕，唔再敲門攞最新頁面")
    meta = load_mapping()[key]
    state: dict[int, dict] = {}
    going_seen = ""
    for race_id in meta["races"]:
        # 逐場一版，`force=True` 因為要最新退出馬／場地，唔可以讀舊 cache。
        # 撞到拒絕即停 —— 半份最新資料唔可以用嚟判斷「有冇變」。
        html = fetch_page(runlog, f"{BASE}/{meta['meetingId']}/{race_id}/",
                          force=True,
                          where=f"{key} 覆核重抓（raceId={race_id}）")
        if not html:
            raise TemporaryFailure(f"重抓賽事頁失敗（race_id={race_id}），停止重抓")
        parsed = parse_race(html)
        rno = (parsed["meta"] or {}).get("race_number")
        if rno is None:
            continue
        blocks = {b["name"].lower(): b for b in parse_runner_blocks(html)}
        overview = parsed["overview"]
        going = normalise_going((parsed["meta"] or {}).get("track_condition"))
        going_seen = going or going_seen
        state[int(rno)] = {
            "going": going,
            "scratched": sorted(str(n) for n, v in overview.items()
                                if v.get("scratched")),
            "jockeys": {str(n): str(v.get("jockey") or "").strip()
                        for n, v in overview.items() if not v.get("scratched")},
            "barriers": {str(n): str(blocks.get((v.get("name") or "").lower(), {})
                                     .get("barrier") or "").strip()
                         for n, v in overview.items() if not v.get("scratched")},
            "field": sorted(str(n) for n, v in overview.items()
                            if not v.get("scratched")),
        }
    return state, going_seen


def diff_race_state(stored: dict[int, dict], live: dict[int, dict]) -> dict:
    """→ {race_no: {field: (was, now)}}。只睇會影響排名嘅欄位。"""
    changes: dict[int, dict] = {}
    for rno, now in sorted(live.items()):
        was = stored.get(rno)
        if was is None:
            continue
        delta: dict = {}
        if now["going"] and now["going"] != was["going"]:
            delta["going"] = [was["going"], now["going"]]
        gone = sorted(set(was["field"]) - set(now["field"]))
        added = sorted(set(now["field"]) - set(was["field"]))
        if gone:
            delta["scratchings"] = gone
        if added:
            # 後備馬入替 —— 同退出馬一樣要重新評分。
            delta["emergencies_in"] = added
        jockey_swaps = {n: [was["jockeys"].get(n, ""), now["jockeys"][n]]
                        for n in now["jockeys"]
                        if n in was["jockeys"]
                        and normalise(was["jockeys"].get(n, "")) != normalise(now["jockeys"][n])
                        and now["jockeys"][n]}
        if jockey_swaps:
            delta["jockeys"] = jockey_swaps
        barrier_swaps = {n: [was["barriers"].get(n, ""), now["barriers"][n]]
                         for n in now["barriers"]
                         if n in was["barriers"] and now["barriers"][n]
                         and was["barriers"].get(n, "") != now["barriers"][n]}
        if barrier_swaps:
            delta["barriers"] = barrier_swaps
        if len(now["field"]) != len(was["field"]):
            delta["field_size"] = [len(was["field"]), len(now["field"])]
        if delta:
            changes[rno] = delta
    return changes


#: 會改變**出賽名單／每匹馬資料**嘅變動 —— 呢啲唔可以只重算分數。
FIELD_LEVEL_CHANGES = ("scratchings", "emergencies_in", "barriers", "jockeys",
                       "field_size")


def venue_from_folder(folder_name: str) -> str:
    return re.sub(r"\s+Race\s+[\d\-]+$", "", folder_name[11:]).strip()


RE_RANK_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", re.M)


def top_picks_snapshot(folder: Path, depth: int = 3) -> dict[int, list[tuple]]:
    """{場號: [(排名, 馬號, 馬名), …]}，由已生成嘅分析檔讀。

    ⚠️ 呢個係**我哋published咗嘅排名**，所以重評分前後各影一次就答得到
    「排名有冇郁」。之前冇人記低呢樣：run log 有退出馬、有場地變化，但唔知
    重評分之後頭幾揀究竟變咗未 —— 而嗰個先係 Kelvin 真正想知嘅嘢。
    """
    out: dict[int, list[tuple]] = {}
    for f in folder.glob("Race_*_Auto_Analysis.md"):
        m = re.search(r"Race_(\d+)_", f.name)
        if not m:
            continue
        body = f.read_text(errors="replace")
        i = body.find("全場綜合戰力排名")
        if i < 0:
            continue
        rows = RE_RANK_ROW.findall(body[i:i + 4000])[:depth]
        out[int(m.group(1))] = [(int(r), int(n), nm.strip()) for r, n, nm in rows]
    return out


def diff_top_picks(before: dict, after: dict) -> list[dict]:
    """邊幾場嘅頭幾揀真係郁咗。只報有變嗰啲。"""
    moved = []
    for rno in sorted(set(before) | set(after)):
        b = [(n, nm) for _r, n, nm in before.get(rno, [])]
        a = [(n, nm) for _r, n, nm in after.get(rno, [])]
        if b and a and b != a:
            moved.append({"race": rno,
                          "before": [f"{n} {nm}" for n, nm in b],
                          "after": [f"{n} {nm}" for n, nm in a]})
    return moved


def rebuild_meeting_from_cache(runlog: RunLog, folder: Path, key: str,
                               going: str) -> bool:
    """由**已重抓嘅** cache 頁重寫 Racecard/Formguide，再重建 Facts/Logic/評分。

    ⚠️ 點解唔可以只跑 `au_auto_orchestrator`（純重評分）：佢由現有
    `Race_N_Logic.json` 重算，而 Logic 係由通宵寫嘅 Racecard 砌出嚟 —— 一隻通宵
    之後才退出嘅馬仍然喺 Logic 裡面，於是照樣入榜。2026-08-05 實測：Canterbury
    7 場偵測到 24 隻退出馬，全部照樣排名，R2 #6 Blenheim Girl 仲排第二。
    退出馬要靠 `write_meeting` 寫 `status:Scratched`，落一層 pipeline 才會剔走。

    全程 cache-only（`run_cmd` 強制 `WC_SB_CACHE_ONLY=1`），零網絡請求 ——
    頁面係覆核嗰下已經 force-refresh 過嘅。
    """
    meta = load_mapping().get(key)
    if not meta:
        runlog.warn(f"{folder.name}: 對應表冇，重建唔到（只可以重評分）")
        return False
    venue = venue_from_folder(folder.name)
    # 順手補少量個人頁。⚠️ 早更窗口窄（10:00 開工、最早一場約 11:44），所以呢度
    # 用一個**細**限額（`WC_AU_PEOPLE_PER_REBUILD`，預設 10）而唔係晚更嗰個 40 ——
    # 補齊係晚更嘅工作，佢有十二個鐘。鄉郊場（Belmont / Hobart / Murray Bridge）
    # 嘅 `(LY:)` 靠幾晚累積收斂，唔會一次填滿。
    try:
        per_rebuild = int(os.environ.get("WC_AU_PEOPLE_PER_REBUILD", "10"))
    except ValueError:
        per_rebuild = 10
    if per_rebuild > 0:
        warm_people_pages(runlog, meta["races"], meta["meetingId"], folder.name,
                          limit=per_rebuild)
    rc, out = run_cmd([sys.executable, CLAW,
                       "--meeting-url", f"https://www.sportsbetform.com.au/"
                                        f"{meta['meetingId']}/{meta['races'][0]}/",
                       "--races", ",".join(meta["races"]),
                       "--out-dir", str(folder),
                       "--date", meta["date"], "--venue", venue,
                       "--delay", str(fetch_delay())],
                      cwd=AU_SKILL, timeout=3600)
    if rc != 0:
        runlog.warn(f"{folder.name}: 重寫 Racecard 失敗（rc={rc}）："
                    f"{out.splitlines()[-1] if out else '冇輸出'}")
        return False
    # claw 重寫咗 Racecard，所以 RA 讓磅分要再補一次（唔補就會退回 fallback）。
    apply_ra_ratings(runlog, folder, meta["date"], venue)
    cmd = [sys.executable, AU_ORCH, str(folder), "--auto",
           "--skip-cloudflare-deploy", "--race-workers", "1"]
    if going:
        cmd += ["--going", going]
    rc, out = run_cmd(cmd, timeout=10800)
    if rc != 0:
        runlog.warn(f"{folder.name}: 重建分析 rc={rc}："
                    f"{out.splitlines()[-1] if out else '冇輸出'}")
    return True


# 飛起幾多算警號。實測 430 匹頭兩選：基準入位率 54%，飛起 >25% 嗰 91 匹只有
# 32%（-23pp）。門檻再高訊號更強但樣本更細（>50% 得 40 匹 / 28%），25% 係平衡點。
DRIFT_WARN = 0.25


def market_drift(runlog: RunLog, folder: Path, key: str) -> list[dict]:
    """頭兩選之中，市場由分析時到而家飛起得好緊要嘅。

    ⚠️ 賠率**永遠唔入評分** —— 呢個純粹係開跑前嘅警號，同 `au_reflect_notify`
    嗰個事後統計係同一個訊號嘅賽前版本。呢個係整套嘢最直接有用嘅一樣：一隻到
    早上已經飛起 25% 嘅揀馬，歷史上入位率 32%，係正常 54% 嘅一半。

    ⚠️ 一定要喺**重建覆寫 Formguide 之前**叫。分析時嘅賠率只存喺 Formguide 度，
    一重建就被新頁面沖走，之後再比就永遠零差異。
    """
    from claw_sportsbet_form import BASE, SportsbetFormFetcher, parse_odds_html

    ids = load_mapping()
    meta = ids.get(key) or {}
    if not meta.get("races"):
        return []
    picks = top_picks_snapshot(folder, depth=2)
    fetch = SportsbetFormFetcher(delay=0.0, verbose=False)
    out: list[dict] = []
    for i, rid in enumerate(meta["races"], start=1):
        chosen = picks.get(i)
        if not chosen:
            continue
        was = market_odds_from_formguide(folder, i)
        cache = fetch._cache_path(f"{BASE}/{meta['meetingId']}/{rid}/")
        if not cache.exists():
            continue
        try:
            now = parse_odds_html(cache.read_text(errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        for rank, num, name in chosen:
            old = was.get(num)
            new = (now.get(num) or {}).get("Sportsbet-FixedWin")
            if not old or not new:
                continue
            try:
                move = (float(new) - float(old)) / max(float(old), 0.01)
            except (TypeError, ValueError):
                continue
            if move > DRIFT_WARN:
                out.append({"meeting": folder.name, "race": i, "rank": rank,
                            "horse": name, "was": float(old), "now": float(new),
                            "move": round(move, 3)})
    if out:
        runlog.data.setdefault("market_drift", []).extend(out)
        runlog.step("market-drift", "flagged", meeting=folder.name,
                    count=len(out))
    return out


RE_FG_WIN = re.compile(r"WinOdds:\s*([\d.]+|-)")


ODDS_HISTORY = "odds_history.json"


def record_odds_from_cache(runlog: RunLog, folder: Path, key: str,
                          label: str) -> int:
    """由**啱啱抽返嘅 cache 頁**影賠率，唔經 Formguide。

    ⚠️ 早更嗰刻 Formguide 仲未重寫（只有偵測到實質變動才會重建），所以讀 Formguide
    會攞到前一晚嘅舊價。要影當刻嘅市場價，一定要讀新抽嘅頁面。而且要**無論有冇
    重建都影** —— Kelvin 想開始用賠率，所以每次覆核都要留一個時間點，唔可以只喺
    「啱好有退出馬」嘅日子才有。
    """
    from claw_sportsbet_form import BASE, SportsbetFormFetcher, parse_odds_html

    meta = (load_mapping().get(key) or {})
    if not meta.get("races"):
        return 0
    fetch = SportsbetFormFetcher(delay=0.0, verbose=False)
    path = folder / ODDS_HISTORY
    try:
        hist = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hist = {}
    stamp_label = f"{datetime.now().isoformat(timespec='seconds')}|{label}"
    added = 0
    for i, rid in enumerate(meta["races"], start=1):
        cache = fetch._cache_path(f"{BASE}/{meta['meetingId']}/{rid}/")
        if not cache.exists():
            continue
        try:
            live = parse_odds_html(cache.read_text(errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        prices = {}
        for num, mk in live.items():
            w = mk.get("Sportsbet-FixedWin")
            pl = mk.get("Sportsbet-FixedPlace")
            if w:
                prices[str(num)] = [str(w), str(pl) if pl else "-"]
        if prices:
            hist.setdefault(str(i), {})[stamp_label] = prices
            added += 1
    if added:
        path.write_text(json.dumps(hist, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        runlog.step("odds-snapshot", "ok", meeting=folder.name, races=added,
                    label=label)
    return added


def record_odds_snapshot(folder: Path, label: str) -> int:
    """把每場嘅贏／位賠追加入 `odds_history.json`，**永不覆寫**。

    ⚠️ 冇呢個檔嘅話，賠率只存喺 Formguide，而 Formguide 每次重建都會被新頁面
    覆寫。2026-08-12 實測：三個場次嘅 Formguide 分別喺 19:09、19:13、20:53 寫
    （賽後），所以覆盤標「分析時賠率」其實係「最後一次重建時」。晚更之後早更
    一偵測到退出馬就會重寫，即係大部分日子嗰個「賽前賠率」其實係當朝 10:00
    嘅價，唔係前一晚。

    追加式：`{場號: {時間標籤: {馬號: [贏, 位]}}}`。時間標籤帶 ISO 時間同來源，
    所以之後可以明確講「呢個係 22:04 晚更嗰刻嘅價」。
    """
    path = folder / ODDS_HISTORY
    try:
        hist = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hist = {}
    stamp_label = f"{datetime.now().isoformat(timespec='seconds')}|{label}"
    added = 0
    for fg in folder.glob("*Formguide.md"):
        m = re.search(r"Race (\d+) Formguide", fg.name)
        if not m:
            continue
        rno = m.group(1)
        body = fg.read_text(errors="replace")
        starts = [(s.start(), int(s.group(1)))
                  for s in re.finditer(r"^\[(\d+)\]\s", body, re.M)]
        prices = {}
        for i, (pos, num) in enumerate(starts):
            end = starts[i + 1][0] if i + 1 < len(starts) else len(body)
            om = re.search(r"WinOdds:\s*([\d.]+|-)\s+PlcOdds:\s*([\d.]+|-)",
                           body[pos:end])
            if om and om.group(1) != "-":
                prices[str(num)] = [om.group(1), om.group(2)]
        if not prices:
            continue
        hist.setdefault(rno, {})[stamp_label] = prices
        added += 1
    if added:
        path.write_text(json.dumps(hist, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    return added


def earliest_odds(folder: Path, race_no: int) -> tuple[str, dict] | None:
    """最早一次捕捉嘅賠率 —— 即係真正「分析時」嗰個，同佢嘅時間。"""
    try:
        hist = json.loads((folder / ODDS_HISTORY).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    snaps = hist.get(str(race_no)) or {}
    if not snaps:
        return None
    when = sorted(snaps)[0]
    return when, snaps[when]


def market_odds_from_formguide(folder: Path, race_no: int) -> dict[int, str]:
    """{馬號: 分析時嘅贏賠}，由 Formguide 讀（即係我哋落分嗰刻嘅市場價）。"""
    fg = next(iter(folder.glob(f"*Race {race_no} Formguide.md")), None)
    if not fg:
        return {}
    body = fg.read_text(errors="replace")
    starts = [(m.start(), int(m.group(1)))
              for m in re.finditer(r"^\[(\d+)\]\s", body, re.M)]
    out = {}
    for i, (pos, num) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(body)
        m = RE_FG_WIN.search(body, pos, end)
        if m and m.group(1) != "-":
            out[num] = m.group(1)
    return out


def refresh_one_meeting(runlog: RunLog, folder: Path, api: dict) -> bool:
    stored = stored_race_state(folder)
    if not stored:
        runlog.meeting(folder.name, "refresh_skipped", reason="冇 Logic.json 可以比對")
        return False
    live, page_going = live_race_state(runlog, folder)
    if not live:
        raise TemporaryFailure("重抓到嘅頁面一場都 parse 唔到")

    day = folder.name[:10]
    official = ""
    for venue, slot in (api.get(day) or {}).items():
        if normalise(venue) in normalise(folder.name):
            official = normalise_going(slot.get("going"))
            break
    going = official or page_going

    # ⚠️ 喺任何重建之前做 —— 分析時嘅賠率只存喺 Formguide，一重建就沖走。
    _key = mapping_key_for(folder) or ""
    market_drift(runlog, folder, _key)
    # 每次覆核都影一個賠率時間點，唔理有冇實質變動。
    record_odds_from_cache(runlog, folder, _key, "morning-refresh")

    changes = diff_race_state(stored, live)
    for rno, delta in changes.items():
        if "scratchings" in delta or "emergencies_in" in delta:
            runlog.data["scratchings_detected"].append(
                {"meeting": folder.name, "race": rno,
                 "scratched": delta.get("scratchings", []),
                 "emergencies_in": delta.get("emergencies_in", [])})
        if "going" in delta:
            runlog.data["track_changes_detected"].append(
                {"meeting": folder.name, "race": rno, "change": delta["going"]})

    stored_going = {s["going"] for s in stored.values() if s["going"]}
    going_moved = bool(going) and going not in stored_going
    if going_moved:
        runlog.data["track_changes_detected"].append(
            {"meeting": folder.name, "race": "meeting",
             "change": [sorted(stored_going), going]})

    if not changes and not going_moved:
        runlog.meeting(folder.name, "unchanged", races=len(stored))
        return False

    # ⚠️ 兩條唔同嘅路，睇變動係邊一層：
    #   出賽名單／每匹馬資料變（退出馬、後備入替、換檔、換騎師）→ 一定要由 cache
    #     頁**重寫 Racecard**再落 Facts/Logic，因為退出馬係喺 Racecard 寫
    #     `status:Scratched` 嗰層剔走嘅。只重評分會令退出馬照樣入榜。
    #   只係場地狀況變 → `au_auto_orchestrator` 純重評分就夠，快好多。
    # 重評分之前影低而家published緊嘅頭三揀，之後再影一次 —— 兩者一比就答到
    # 「排名有冇郁」。冇呢個，run log 講得出退出馬同場地變化，但講唔出最重要嗰句。
    picks_before = top_picks_snapshot(folder)

    field_changed = sorted({field for delta in changes.values()
                            for field in delta if field in FIELD_LEVEL_CHANGES})
    if field_changed:
        runlog.step("rebuild", "field-level-change", meeting=folder.name,
                    fields=field_changed,
                    detail="重寫 Racecard → Facts → Logic → 評分（cache-only）")
        if not rebuild_meeting_from_cache(runlog, folder, mapping_key_for(folder) or "",
                                          going):
            raise TemporaryFailure("重建出賽名單失敗")
        reason = f"field-level change: {', '.join(field_changed)}"
    else:
        cmd = [sys.executable, AU_AUTO_ORCH, str(folder)]
        if going:
            cmd += ["--going", going]
        rc, out = run_cmd(cmd, timeout=7200)
        if rc != 0:
            raise TemporaryFailure(
                f"重新評分失敗（rc={rc}）：{out.splitlines()[-1] if out else '冇輸出'}")
        reason = "going change only"

    # 重建之後再影一次 —— 追加，唔覆寫，所以分析時嗰個價永遠留住。
    record_odds_snapshot(folder, "morning-rebuild")
    runlog.meeting(folder.name, "rescored", races=sorted(changes),
                   going=going or None, rebuilt=bool(field_changed))
    runlog.data["races_updated"].append(
        {"meeting": folder.name, "races": sorted(changes), "going": going or None,
         "rebuilt_field": bool(field_changed)})
    moved = diff_top_picks(picks_before, top_picks_snapshot(folder))
    if moved:
        runlog.step("rescore", "ranking-moved", meeting=folder.name,
                    races=[m["race"] for m in moved])
    runlog.data["analysis_changes"].append(
        {"meeting": folder.name, "going_applied": going or None,
         "reason": reason, "ranking_moved": moved,
         "changes": {str(k): v for k, v in changes.items()}})
    return True


# ── 步驟 4：dashboard 驗證 + 發佈 ──────────────────────────────────────────
def download_live_snapshot(runlog: RunLog, dest: Path) -> Path | None:
    """攞而家 live 嗰份 snapshot。**一定要繞開 CDN cache。**

    ⚠️ 唔繞嘅話會攞到舊副本，而呢個檔係下一份發佈嘅**底**。2026-08-09 實測：
    deploy 完成之後即刻讀，連續兩次都攞到上一版（`verify_live` 報 stale=True，
    第三次先追上）。`verify_live` 有重試頂得住，但呢個 function 冇 —— 攞到咩就
    當咩，然後成份新 snapshot 就砌喺一個過時嘅底上面，可以靜靜咁整跌上一個 run
    啱啱發佈嘅場次。加 cache-buster + no-cache header，兩者都要：query string 令
    edge 當佢係新 key，header 令中間任何 proxy 唔好回舊嘢。
    """
    url = f"{LIVE_SNAPSHOT_URL}?cb={int(time.time() * 1000)}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "WongChoi-AUDaily/1.0",
                      "Cache-Control": "no-cache, max-age=0",
                      "Pragma": "no-cache"})
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
            json.loads(payload)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(payload)
            return dest
        except Exception as exc:  # noqa: BLE001
            runlog.retry("live-snapshot", attempt, f"{type(exc).__name__}: {exc}")
            time.sleep(5 * attempt)
            # ⚠️ 重試要換一條新 cb。同一條 URL 重試等於再問 edge 攞返同一個
            # cache entry —— `verify_live` 嘅 poll 靠呢度先真係問到新嘢。
            request = urllib.request.Request(
                f"{LIVE_SNAPSHOT_URL}?cb={int(time.time() * 1000)}",
                headers=dict(request.headers))
    runlog.warn("攞唔到 live snapshot；build 會由 deploy.sh 自己下載")
    return None


def race_numbers_in_snapshot(entry: object) -> list[str]:
    """snapshot 一個場次入面嘅場次號。

    ⚠️ `races[key]` 係 `{"meeting": …, "races_by_analyst": {analyst: [race, …]}}`，
    **唔係**一個 list。之前當佢係 list 去 `len()`，每個場次都會數到 2（就係
    嗰兩個 key），一個 10 場嘅馬場睇落同一個空馬場一樣。
    """
    if not isinstance(entry, dict):
        return []
    numbers: set[str] = set()
    for races in (entry.get("races_by_analyst") or {}).values():
        if not isinstance(races, list):
            continue
        for race in races:
            if isinstance(race, dict):
                numbers.add(str(race.get("race_number")))
    return sorted(numbers, key=lambda x: (len(x), x))


def race_content_fingerprint(entry: object) -> list:
    """一個場次嘅**內容**指紋：逐場嘅排名、揀馬、評級、場地。

    ⚠️ 只比「場次同場號」係唔夠嘅。2026-08-05 早更實測：Belmont 場地由 Soft 6
    變 Soft 5、R1 #10 同 R5 #5 退出，重評分改咗排名 —— 但場次同場號一個都冇變，
    於是 `deploy-skipped-no-change` 把早更嘅成果扣咗喺本機，發佈唔上去。
    早更成個存在意義就係推新排名上去，所以指紋一定要食到排名。
    """
    if not isinstance(entry, dict):
        return []
    out = []
    for analyst, races in sorted((entry.get("races_by_analyst") or {}).items()):
        if not isinstance(races, list):
            continue
        for race in races:
            if not isinstance(race, dict):
                continue
            picks = [(p.get("rank"), p.get("horse_number"), p.get("grade"))
                     for p in (race.get("top_picks") or [])
                     if isinstance(p, dict)]
            out.append([analyst, str(race.get("race_number")),
                        str(race.get("going") or ""),
                        str(race.get("confidence") or ""),
                        race.get("horses_count"), picks])
    return out


def snapshot_signature(payload: dict) -> dict:
    """用嚟判斷「有冇實質變」——`generated_at` 每次都變，唔可以用嚟比。"""
    races = payload.get("races") or {}
    return {
        "meetings": sorted(f"{m['date']}|{m['venue']}"
                           for m in payload.get("meetings") or []),
        "races": {key: race_numbers_in_snapshot(value)
                  for key, value in sorted(races.items())},
        "content": {key: race_content_fingerprint(value)
                    for key, value in sorted(races.items())},
        "consensus": sorted((payload.get("consensus") or {}).keys()),
    }


def unpublished_local_meetings(payload: dict, already: list[Path],
                              today: date) -> list[Path]:
    """本機已經分析好、但即將發佈嗰份 snapshot 冇嘅場次（今日或之後）。

    ⚠️ 兩個 mode 嘅合併名單都係由「dashboard 上有乜」推導，所以一次發佈失敗
    **永遠冇人再試**：場次分析齊咗、就喺本機、但之後每個 run 都報「冇嘢做」。
    2026-08-07 實測：deploy 撞到 Cloudflare 25 MiB 上限連續失敗三次，九個已分析
    嘅場次消失兩日，期間 08-08 早更講 `refresh-active/nothing-to-do`。
    所以「要發佈乜」唔可以問 dashboard —— 要問本機有乜分析好而 dashboard 未有。
    """
    published = {f"{m.get('date')}|{m.get('venue')}"
                 for m in (payload.get("meetings") or [])}
    have = {f.name for f in already}
    out: list[Path] = []
    for folder in live_meeting_dirs():
        if folder.name in have:
            continue
        try:
            day = datetime.strptime(folder.name[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if day < today:
            continue  # 過去嘅場次交俾覆盤／歸檔，唔喺呢度硬塞返上去
        if archive_dashboard_key(folder.name) in published:
            continue  # 已經發佈過，要更新係早更覆核嘅責任
        if not list(folder.glob("Race_*_Auto_Analysis.md")):
            continue  # 淨係抽咗頁未評分 —— 唔算分析好
        out.append(folder)
    return out


def build_snapshot(runlog: RunLog, meeting_dirs: list[Path],
                   drop_keys: list[str] | None = None) -> tuple[Path, list[str]]:
    """由 live snapshot 剪走已歸檔場次，再串連合併每個場次 → 最終 JSON。

    ⚠️ `generate_static.py` 一次只食一個 `--au-meeting-dir`，所以第二個場次嘅
    `--base-snapshot` 一定要係第一個嘅輸出，唔係 live cache（會掉咗第一個）。

    ⚠️ 剪走一定要喺合併之前做，而且要真做。2026-08-05／08-06 兩個 run 都係
    喺呢一步之後撞牆：歸檔搬走咗 folder，但合併路徑只會**加**場次，於是發佈前
    驗證見到已歸檔場次仲喺 snapshot，正確咁拒絕發佈 —— Cloudflare 連續兩晚
    停喺舊版本，而 4 個新分析好嘅場次一直發佈唔上去。
    """
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    base = download_live_snapshot(runlog, WORK_DIR / "live-dashboard-data.json")
    current = base
    # ⚠️ 唔可以只信「今次 run 歸檔咗乜」。早更傳嘅係空名單，所以晚更歸檔完但發佈
    # 失敗之後，早更會把已歸檔場次原封不動再發佈一次，而佢自己嘅驗證仲會話冇問題
    # （expect_absent 係空）。真憑據係**本機 folder 而家喺 Archive/ 邊**，所以由
    # 即將發佈嗰份 snapshot 直接推導 —— 邊個 mode 發佈都一樣會自我修復。
    drops = list(drop_keys or [])
    if current is not None:
        try:
            payload = json.loads(current.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        for item in payload.get("meetings") or []:
            if (item.get("region") or "").upper() != "AU":
                continue  # HKJC 場次冇 AU folder，唔好當佢已歸檔
            key = f"{item.get('date')}|{item.get('venue')}"
            if key in drops:
                continue
            folder = find_meeting_dir(item.get("date"), item.get("venue"))
            if folder is not None and folder.parent == ARCHIVE_ROOT:
                drops.append(key)
                runlog.warn(f"{key} 已經歸檔但仲喺 dashboard —— 由發佈前 snapshot "
                            f"推導出嚟，今次剪走")
        # 反方向：本機分析好但 snapshot 冇嘅場次要補上去。上一晚發佈失敗嘅話，
        # 冇呢步就永遠冇人再發佈嗰批分析。
        missed = unpublished_local_meetings(payload, meeting_dirs, date.today())
        if missed:
            runlog.warn(f"本機有 {len(missed)} 個已分析場次未發佈（大概上一次發佈"
                        f"失敗）—— 今次補發：{[f.name for f in missed]}")
            meeting_dirs = list(meeting_dirs) + missed
    drop_keys = drops
    if drop_keys and current is not None:
        pruned = WORK_DIR / "pruned.json"
        cmd = [sys.executable, GENERATE_STATIC,
               "--base-snapshot", str(current),
               "--output-json", str(pruned),
               "--output-html", str(WORK_DIR / "pruned.html")]
        for key in drop_keys:
            cmd += ["--drop-meeting", key]
        rc, out = run_cmd(cmd, cwd=DASHBOARD_DIR, timeout=3600)
        if rc != 0 or not pruned.exists():
            raise TemporaryFailure(
                f"剪走已歸檔場次失敗（rc={rc}）："
                f"{out.splitlines()[-1] if out else '冇輸出'}")
        current = pruned
        runlog.step("dashboard-prune", "ok", dropped=drop_keys)
    # ⚠️ 合併之前要重新確認每個 folder 仲喺度。2026-08-10 實測：早更喺覆盤之前
    # 計好合併名單，覆盤跟住把兩個腰斷場次歸檔，於是名單指向已經搬走嘅路徑 ——
    # `generate_static` 照食，出咗兩個「零場次」嘅空殼加返落 snapshot，驗證即刻
    # 攔住咗發佈。合併一個已歸檔嘅場次無論點都係錯，所以喺呢度硬性擋。
    live_dirs = []
    for folder in meeting_dirs:
        if not folder.exists():
            runlog.warn(f"{folder.name} 喺合併之前已經唔喺度（多數係啱啱歸檔咗）"
                        f"—— 唔合併")
            continue
        if folder.parent == ARCHIVE_ROOT:
            runlog.warn(f"{folder.name} 已經歸檔 —— 唔合併（剪走先啱）")
            continue
        live_dirs.append(folder)
    meeting_dirs = live_dirs

    for i, folder in enumerate(meeting_dirs, 1):
        out_json = WORK_DIR / f"merge-{i:02d}.json"
        cmd = [sys.executable, GENERATE_STATIC,
               "--au-meeting-dir", str(folder),
               "--output-json", str(out_json),
               "--output-html", str(WORK_DIR / f"merge-{i:02d}.html")]
        if current is not None:
            cmd += ["--base-snapshot", str(current)]
        rc, out = run_cmd(cmd, cwd=DASHBOARD_DIR, timeout=3600)
        if rc != 0 or not out_json.exists():
            raise TemporaryFailure(
                f"合併 {folder.name} 失敗（rc={rc}）："
                f"{out.splitlines()[-1] if out else '冇輸出'}")
        current = out_json
        runlog.step("dashboard-merge", "ok", meeting=folder.name,
                    snapshot=out_json.name)
    if current is None:
        raise TemporaryFailure("冇 base snapshot 又冇場次可以合併")
    return current, drop_keys


# Cloudflare Pages 硬性拒收超過 25 MiB 嘅單一檔案。喺 24 就收手，留一格緩衝。
MAX_SNAPSHOT_MIB = 24.0


def shrink_to_fit(runlog: RunLog, snapshot: Path, today: date) -> Path:
    """太大就讓路：剪走已經跑完嘅 AU 場次，保住當日賽事一定發佈得出。

    ⚠️ 呢個係唯一一個「今晚嘅補救路徑救唔到」嘅失敗。2026-08-07 九個星期六場次
    令 snapshot 去到 32.5 MiB，deploy 連續三次被拒 —— 而體積唔會自己縮，所以佢
    每晚都會用同一個方式失敗。瘦身之後 19.1 MiB，即係大約 11–12 個場次會再撞牆。

    讓路次序係刻意嘅：已經跑完嘅場次等緊覆盤，佢哋喺 dashboard 上嘅價值最低，
    而且本機正本一直都喺度；當日／將來嘅賽事係人真係要睇嗰啲，一匹都唔剪。
    HKJC 場次唔屬於 AU 流程，亦唔剪。剪晒都仲超標就大聲報錯 —— 冇聲咁截係更差。
    """
    size = snapshot.stat().st_size / 1048576
    if size <= MAX_SNAPSHOT_MIB:
        return snapshot
    try:
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return snapshot
    past = [f"{m.get('date')}|{m.get('venue')}" for m in payload.get("meetings") or []
            if (m.get("region") or "").upper() == "AU"
            and (m.get("date") or "9999-12-31") < today.isoformat()]
    if not past:
        runlog.error("dashboard",
                     f"snapshot {size:.1f} MiB 超過 {MAX_SNAPSHOT_MIB} MiB，但冇"
                     f"已跑完嘅場次可以讓路 —— 全部都係當日或將來賽事，唔會剪")
        return snapshot
    runlog.warn(f"snapshot {size:.1f} MiB 超過 {MAX_SNAPSHOT_MIB} MiB —— 剪走 "
                f"{len(past)} 個已跑完場次讓路（本機正本冇動）：{past}")
    out = WORK_DIR / "shrunk.json"
    cmd = [sys.executable, GENERATE_STATIC,
           "--base-snapshot", str(snapshot), "--output-json", str(out),
           "--output-html", str(WORK_DIR / "shrunk.html")]
    for key in past:
        cmd += ["--drop-meeting", key]
    rc, _ = run_cmd(cmd, cwd=DASHBOARD_DIR, timeout=3600)
    if rc != 0 or not out.exists():
        runlog.error("dashboard", "縮細 snapshot 失敗 —— 照用原本嗰份")
        return snapshot
    after = out.stat().st_size / 1048576
    runlog.step("dashboard-shrink", "ok", before_mib=round(size, 1),
                after_mib=round(after, 1), dropped=past)
    if after > MAX_SNAPSHOT_MIB:
        runlog.error("dashboard",
                     f"剪走所有已跑完場次之後仲有 {after:.1f} MiB —— "
                     f"單日賽事本身已經超標，要縮細每匹馬嘅 payload")
    return out


def validate_snapshot(runlog: RunLog, snapshot: Path,
                      expect_absent: list[str]) -> dict:
    """發佈前驗證。任何一項 fail → 唔發佈。"""
    problems: list[str] = []
    try:
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        result = {"ok": False, "problems": [f"snapshot 讀唔到／唔係 JSON：{exc}"]}
        runlog.data["dashboard_validation"] = result
        return result

    meetings = payload.get("meetings") or []
    races = payload.get("races") or {}
    keys = [f"{m.get('date')}|{m.get('venue')}" for m in meetings]

    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        problems.append(f"重複場次：{duplicates}")

    for key in keys:
        entry = races.get(key)
        if not entry:
            problems.append(f"{key} 冇任何場次資料")
            continue
        numbers = race_numbers_in_snapshot(entry)
        if not numbers:
            problems.append(f"{key} 一場都冇（races_by_analyst 空)")
            continue
        for analyst, listing in ((entry.get("races_by_analyst") or {}).items()):
            if not isinstance(listing, list):
                continue
            seen = [str((r or {}).get("race_number")) for r in listing
                    if isinstance(r, dict)]
            duplicated = sorted({n for n in seen if seen.count(n) > 1})
            if duplicated:
                problems.append(f"{key} / {analyst} 有重複場次號：{duplicated}")

    orphans = sorted(set(races) - set(keys))
    if orphans:
        problems.append(f"races 有場次但 meetings 冇：{orphans}")

    archived_still_live = sorted(set(expect_absent) & set(keys))
    if archived_still_live:
        problems.append(f"已歸檔但仲喺 dashboard：{archived_still_live}")

    if not meetings:
        problems.append("snapshot 冇任何場次")

    result = {"ok": not problems, "problems": problems,
              "meetings": keys,
              "race_counts": {k: len(race_numbers_in_snapshot(races.get(k)))
                              for k in keys},
              "snapshot": str(snapshot)}
    runlog.data["dashboard_validation"] = result
    runlog.step("dashboard-validate", "ok" if not problems else "failed",
                meetings=len(keys), problems=len(problems))
    for problem in problems:
        runlog.error("dashboard-validate", problem)
    return result


def deploy_dashboard(runlog: RunLog, snapshot: Path) -> dict:
    """發佈。retry 3 次（build / wrangler 都會有暫時性失敗）。"""
    last = ""
    for attempt in range(1, 4):
        rc, out = run_cmd(["/bin/bash", str(DEPLOY_SH)], cwd=DASHBOARD_DIR,
                          timeout=3600,
                          env={"WC_DASHBOARD_BASE_SNAPSHOT": str(snapshot)})
        active = re.search(r"Active meetings only:\s*(\d+)", out or "")
        url = re.search(r"(https://[0-9a-f]+\.wongchoi-dashboard\.pages\.dev)", out or "")
        commit = re.search(r"Commit Hash:\s*(\S+)", out or "")
        if rc == 0:
            return {"ok": True, "attempts": attempt,
                    "active_meetings": int(active.group(1)) if active else None,
                    "deployment_url": url.group(1) if url else None,
                    "production_url": "https://wongchoi-dashboard.pages.dev",
                    "commit": commit.group(1) if commit else None,
                    "completed_at": stamp()}
        last = out.splitlines()[-1] if out else f"rc={rc}"
        runlog.retry("deploy", attempt, last)
        time.sleep(20 * attempt)
    return {"ok": False, "attempts": 3, "detail": last}


def verify_live(runlog: RunLog, expect_present: list[str],
                expect_absent: list[str], tries: int = 6,
                min_generated_at: str | None = None) -> dict:
    """核實 production alias。

    ⚠️ 兩個方向都要防：
      1. alias 落後 deploy（edge cache，實測大約一分鐘，而且**唔同 edge 唔同步**
         —— 同一分鐘內連續兩次讀可以一次新一次舊）。所以要 poll，一次舊唔算失敗。
      2. 讀到舊 snapshot 但「睇落對」。單靠場次名單比對係會出假綠燈嘅 ——
         舊 snapshot 一樣可以含住我哋期望嘅場次。所以仲要求 `generated_at`
         **新過今次 run 開始時間**。
    """
    floor = None
    if min_generated_at:
        try:
            floor = datetime.fromisoformat(min_generated_at)
        except ValueError:
            floor = None

    last: dict = {}
    for attempt in range(1, tries + 1):
        dest = WORK_DIR / "verify-live.json"
        if download_live_snapshot(runlog, dest) is None:
            time.sleep(15)
            continue
        payload = json.loads(dest.read_text(encoding="utf-8"))
        keys = [f"{m.get('date')}|{m.get('venue')}" for m in payload.get("meetings") or []]
        generated = (payload.get("meta") or {}).get("generated_at")
        missing = sorted(set(expect_present) - set(keys))
        lingering = sorted(set(expect_absent) & set(keys))
        stale = False
        if floor is not None and generated:
            try:
                seen = datetime.fromisoformat(str(generated))
                if seen.tzinfo is None:
                    seen = seen.astimezone()
                stale = seen < floor
            except ValueError:
                stale = False
        last = {"attempt": attempt, "generated_at": generated,
                "meetings": keys, "missing": missing, "still_present": lingering,
                "stale": stale, "ok": not missing and not lingering and not stale}
        if last["ok"]:
            runlog.step("verify-live", "ok", **{k: last[k] for k in
                                                ("generated_at", "meetings")})
            return last
        runlog.retry("verify-live", attempt,
                     f"missing={missing} still_present={lingering} stale={stale}")
        time.sleep(20)
    runlog.step("verify-live", "failed", **last)
    return last or {"ok": False, "detail": "冇讀到 live snapshot"}


def step_dashboard(runlog: RunLog, meeting_dirs: list[Path],
                   archived_names: list[str], *, skip_deploy: bool = False) -> bool:
    """合併 → 驗證 → 發佈 → 核實。回 True = 一切正常（含「冇變唔使發」）。"""
    runlog.step("dashboard", "start", merge=len(meeting_dirs),
                archived=len(archived_names))
    expect_absent = [archive_dashboard_key(name) for name in archived_names]

    snapshot, expect_absent = build_snapshot(runlog, meeting_dirs, expect_absent)
    snapshot = shrink_to_fit(runlog, snapshot, date.today())
    validation = validate_snapshot(runlog, snapshot, expect_absent)
    if not validation["ok"]:
        runlog.error("dashboard", "驗證唔過 —— 唔發佈")
        return False

    if skip_deploy:
        runlog.step("dashboard", "deploy-skipped-by-flag")
        return True

    # ⚠️ 今次真係改過嘢（新分析／重評分／歸檔）就一定要發佈，唔好行 no-change
    # 捷徑。指紋已經食排名，但「我哋知自己改過」係更硬嘅證據。
    # ⚠️ 要用 expect_absent（已含自動推導出嚟嘅剪走），唔係 archived_names。
    # 一個「只需要剪走」嘅早更 run，archived_names 係空，會走 no-change 捷徑，
    # 於是永遠修復唔到一份髒 snapshot。
    changed_this_run = bool(runlog.data["races_added"] or runlog.data["races_updated"]
                            or archived_names or expect_absent)
    # Idempotency：build 出嚟同 live 一模一樣就唔發佈，免得每晚都出一個新版本。
    live = WORK_DIR / "live-dashboard-data.json"
    if live.exists() and not changed_this_run:
        try:
            same = snapshot_signature(json.loads(snapshot.read_text(encoding="utf-8"))) \
                == snapshot_signature(json.loads(live.read_text(encoding="utf-8")))
        except ValueError:
            same = False
        if same:
            runlog.data["cloudflare_deployment"] = {
                "ok": True, "skipped": "no-change",
                "production_url": "https://wongchoi-dashboard.pages.dev"}
            runlog.step("dashboard", "deploy-skipped-no-change")
            return True

    result = deploy_dashboard(runlog, snapshot)
    runlog.data["cloudflare_deployment"] = result
    if not result["ok"]:
        runlog.error("dashboard", f"發佈失敗：{result.get('detail')}")
        return False

    expect_present = [f"{m['date']}|{m['venue']}" for m in
                      json.loads(snapshot.read_text(encoding="utf-8")).get("meetings") or []]
    verified = verify_live(runlog, expect_present, expect_absent,
                           min_generated_at=runlog.data["started_at"])
    runlog.data["cloudflare_deployment"]["verified"] = verified
    runlog.flush()
    return bool(verified.get("ok"))


# 連續幾多個檔寫唔入就收手。環境唔畀寫嘅話，試 248 次同試 8 次結果一樣。
MIRROR_FAIL_STREAK = 8


def step_mirror_reports(runlog: RunLog, meeting_dirs: list[Path]) -> None:
    """把今次動過嘅場次夾鏡像返 Google Drive（`WONGCHOI_AU_MIRROR_ROOT`）。

    AU_RACING 由 2026-08-05 起住本機硬碟，Drive 唔再係 source of truth。冇呢一步
    Drive 就會靜靜咁停留喺搬走嗰日，而 Kelvin 同 Windows 機都仲會去嗰邊睇。

    launchd 底下**照做得**：實測（三次）launchd 對 CloudStorage 嘅權限係一半一半
    —— `iterdir()` / 讀內容 `PermissionError`，但 `stat()` 同寫入 OK。呢個 step 只
    用 stat + 寫，即係剛好落喺容許嘅一邊。

    ⚠️ 但仍然係 best-effort：探測用「真試寫一次」，唔可以用 `.is_dir()`（stat 會
    成功，騙人）。寫唔入就 warn 一句照過 —— 分析同發佈已經做完，唔可以因為鏡像
    失敗而拖垮成個 run。
    """
    if AU_RACING_MIRROR is None:
        runlog.step("mirror", "not-configured")
        return

    probe = AU_RACING_MIRROR / ".au_mirror_write_probe"
    try:
        AU_RACING_MIRROR.mkdir(parents=True, exist_ok=True)
        probe.write_text(stamp(), encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        runlog.warn(f"鏡像寫唔入 {AU_RACING_MIRROR}（{type(exc).__name__}: {exc}）"
                    f"—— Drive 邊會停留喺舊版本。分析同發佈唔受影響。")
        runlog.step("mirror", "skipped-unwritable", reason=type(exc).__name__)
        return

    # ⚠️ 寫探測喺**根目錄**成功唔代表寫得入**子目錄**。2026-08-09 launchd 實測：
    # 探測過關，跟住 248 個檔全部失敗，而同一段 code 由 Terminal 跑就 242 個全部
    # 成功 —— 即係 launchd 嘅 CloudStorage 權限比探測到嘅窄。舊寫法 `except
    # OSError: failed += 1` 把真原因吞咗，所以份 log 淨係識講「248 個失敗」，
    # 睇極都唔知點解。而家：記低第一個真錯誤，而且連續失敗到一定數量就收手 ——
    # 環境唔畀寫嘅話，試 248 次同試 8 次結果一樣，但後者唔會嘈足一版。
    copied = failed = 0
    first_error: str | None = None
    streak = 0
    for src in [AU_RACING / n for n in MIRRORED_ROOT_FILES] + list(meeting_dirs):
        if streak >= MIRROR_FAIL_STREAK:
            break
        for item in ([src] if src.is_file() else sorted(src.rglob("*"))):
            if streak >= MIRROR_FAIL_STREAK:
                break
            if not item.is_file() or item.name == ".DS_Store":
                continue
            dst = AU_RACING_MIRROR / item.relative_to(AU_RACING)
            try:
                st = item.stat()
                if dst.exists():
                    d = dst.stat()
                    if d.st_size == st.st_size and int(d.st_mtime) >= int(st.st_mtime):
                        continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)
                copied += 1
                streak = 0
            except OSError as exc:
                failed += 1
                streak += 1
                if first_error is None:
                    first_error = f"{type(exc).__name__}: {exc}"

    gave_up = streak >= MIRROR_FAIL_STREAK
    runlog.step("mirror", "ok" if not failed else "partial",
                copied=copied, failed=failed, gave_up=gave_up or None,
                first_error=first_error, root=str(AU_RACING_MIRROR))
    if failed:
        runlog.warn(
            f"鏡像寫唔入（{failed} 個檔"
            + (f"，連續失敗 {MIRROR_FAIL_STREAK} 次所以收手" if gave_up else "")
            + f"）：{first_error} —— Drive 邊會停留喺舊版本，"
            f"本機正本同 Cloudflare 發佈唔受影響")


def archive_dashboard_key(folder_name: str) -> str:
    """`2026-08-01 Rosehill Gardens Race 1-10` → `2026-08-01|Rosehill Gardens`."""
    day = folder_name[:10]
    venue = re.sub(r"\s+Race\s+[\d\-]+$", "", folder_name[11:]).strip()
    return f"{day}|{venue}"


# ── mode 編排 ───────────────────────────────────────────────────────────────
#: 重試會解決嘅狀態 → run 報 partial（exit 75），下一次排程接住做。
RETRYABLE_STATUSES = {"pending_extraction", "refresh_deferred", "temporary_failure",
                      "reflection_failed", "analysed_partial"}
#: 要人手睇嘅狀態 → run 唔算失敗，但要喺 log 打出嚟，唔可以靜靜過。
ATTENTION_STATUSES = {"pending_results", "partial_results", "archive_blocked_corpus",
                      "archive_conflict", "no_local_folder", "failed"}


def finish_run(runlog: RunLog, dashboard_ok: bool, hard_temporary: bool) -> int:
    """由實際結果推 run 狀態，唔好一律報 ok。

    ⚠️ 一個「乜都覆核唔到」嘅早更 run 之前會報 `ok`，因為冇 exception 傳出嚟。
    咁樣睇 `last exit code` 就永遠見唔到問題。
    """
    close_browser(runlog)
    seen = {m.get("status") for m in runlog.data["meetings_processed"]}
    retryable = sorted(seen & RETRYABLE_STATUSES)
    attention = sorted(seen & ATTENTION_STATUSES)
    if attention:
        runlog.step("outcome", "needs-attention", statuses=attention)
    if not dashboard_ok:
        runlog.finish("failed")
        return EXIT_FAILED
    if hard_temporary or retryable:
        runlog.step("outcome", "partial", retryable=retryable or None,
                    detail="下一次排程會接住做")
        runlog.finish("partial")
        return EXIT_TEMPORARY
    runlog.finish("ok")
    return EXIT_OK


def push_reflection(runlog: RunLog, archived: list[str]) -> None:
    if not getattr(runlog, "notify_enabled", True):
        return
    """今次 run 有覆盤過嘅賽日，推一段逐個馬場嘅表現去手機。

    ⚠️ 只喺**今次真係歸檔過嘢**先推。唔係嘅話每晚都會重推同一份舊摘要，跟住你
    就會開始無視啲通知 —— 而下一次真出事嗰陣就係嗰個習慣害死你。

    賽日由歸檔到嘅 folder 名推導，唔用 `review_day`：補漏覆盤可以一次過執返幾日
    前嘅場次，嗰陣 review_day 唔等於嗰批場次嘅賽日。
    """
    days = sorted({name[:10] for name in archived if re.match(r"^\d{4}-\d{2}-\d{2}", name)})
    if not days:
        return
    try:
        sys.path.insert(0, str(HERE))
        import au_notify
        import au_reflect_notify
    except Exception as exc:  # noqa: BLE001
        log(f"[reflect-push] import 失敗（{type(exc).__name__}: {exc}）")
        return
    for day in days:
        try:
            text = au_reflect_notify.build(day)
            if not text:
                continue
            # 覆盤係內容 —— 額外收件人收得到。
            sent = au_notify.push(text, audience="content")
            runlog.step("reflect-push", "ok" if sent else "no-outlet", day=day,
                        detail="; ".join(sent) or None)
            push_betting(runlog, day, "settle")
        except Exception as exc:  # noqa: BLE001
            # 推送失敗唔可以令 run 失敗 —— 覆盤已經做完，呢個只係報告。
            runlog.step("reflect-push", "failed", day=day,
                        detail=f"{type(exc).__name__}: {exc}")


def push_betting(runlog: RunLog, day: str, mode: str) -> None:
    """落注相關嘅三條訊息。`mode` = list / update / settle。

    ⚠️ 實測 7 日 487 注：贏注 ≥2 ROI −23.3%、位注 ≥1.5 −12.1%，最好嗰個變體
    （位注 ≥1.5 剔走飛起 >25%）都係 −8.3%。差距係抽水。所以每條訊息都會帶住
    「實測 ROI 為負」呢句 —— 唔可以出一張落注單而唔講量到嘅結果。
    """
    if not getattr(runlog, "notify_enabled", True):
        return
    try:
        sys.path.insert(0, str(HERE))
        import au_betting
        import au_notify

        text = ({"list": lambda d: au_betting.bet_list(d, "first"),
                 "update": lambda d: au_betting.bet_list(d, "last"),
                 "settle": au_betting.settle}[mode])(day)
        if not text:
            return
        # 落注相關嘅三張都係內容 —— heison 一齊收。
        sent = au_notify.push(text, audience="content")
        runlog.step("betting-push", "ok" if sent else "no-outlet", mode=mode,
                    day=day, detail="; ".join(sent) or None)
    except Exception as exc:  # noqa: BLE001
        runlog.step("betting-push", "failed", mode=mode,
                    detail=f"{type(exc).__name__}: {exc}")


def push_run_summary(runlog: RunLog, mode: str) -> None:
    if not getattr(runlog, "notify_enabled", True):
        return
    """推一條人真係想睇嘅摘要。⚠️ 冇嘢好講就唔發 —— 「一切照舊」係雜訊，
    而雜訊嘅代價係下次真出事嗰條會俾人一齊略過。發佈嘅結果要喺呢個時候先讀得到，
    所以叫喺 step_dashboard 之後。"""
    try:
        sys.path.insert(0, str(HERE))
        import au_notify
        import au_run_summary

        text = (au_run_summary.morning if mode == "morning"
                else au_run_summary.evening)(runlog.data)
        if not text:
            return
        # ⚠️ 兩條都係**賽事內容**（退出馬、場地、排名、新分析上咗線冇），所以額外
        # 收件人收得到。運維訊息（診斷、體檢、自動補救）維持 primary —— 嗰啲有
        # 檔案路徑、commit、log 節錄，畀第三者係雜訊亦唔應該外傳。
        sent = au_notify.push(text, audience="content")
        runlog.step("run-summary", "ok" if sent else "no-outlet", mode=mode,
                    detail="; ".join(sent) or None)
    except Exception as exc:  # noqa: BLE001
        runlog.step("run-summary", "failed", detail=f"{type(exc).__name__}: {exc}")


def run_evening(runlog: RunLog, args, review_day: date) -> int:
    archived: list[str] = []
    analysed: list[Path] = []
    temporary = False

    if not args.skip_review:
        try:
            archived = step_review_archive(runlog, review_day,
                                           no_archive=args.no_archive)
        except TemporaryFailure as exc:
            runlog.error("review-archive", f"暫時性：{exc}")
            temporary = True
        if archived:
            push_reflection(runlog, archived)
    if not args.skip_analysis:
        try:
            analysed = step_analyse_next_day(runlog, review_day,
                                             max_meetings=args.max_meetings,
                                             rounds=args.rounds,
                                             round_gap=args.round_gap)
        except TemporaryFailure as exc:
            runlog.error("analyse-next-day", f"暫時性：{exc}")
            temporary = True

    ok = step_dashboard(runlog, analysed, archived, skip_deploy=args.skip_deploy)
    step_mirror_reports(runlog, analysed)
    push_run_summary(runlog, "evening")
    days = sorted({r["meeting"][:10] for r in runlog.data["races_added"]})
    for day in days:
        push_betting(runlog, day, "list")
    return finish_run(runlog, ok, temporary)


def run_morning(runlog: RunLog, args, today: date) -> int:
    temporary = False
    updated: list[Path] = []

    # ⚠️ 收拾尋日一定要行喺**計合併名單之前**。倒轉嘅話名單會喺覆盤歸檔之前
    # 影低，跟住合併一啲已經搬走嘅 folder，把空殼加返上 dashboard。
    if not args.skip_review:
        try:
            done = step_review_archive(runlog, today - timedelta(days=1))
            if done:
                push_reflection(runlog, done)
        except TemporaryFailure as exc:
            runlog.step("morning-review", "deferred", detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            runlog.error("morning-review", f"{type(exc).__name__}: {exc}")
            temporary = True

    if args.skip_refresh:
        # 唔出網。把 dashboard 上嘅場次由本機重新合併一次就算 —— 用嚟把已經改好
        # 但未發佈嘅分析推上去，唔會為咗觸發發佈而重抽幾十版。
        on_dashboard = dashboard_au_meetings(runlog) or []
        for meeting in on_dashboard:
            folder = find_meeting_dir(meeting["date"], meeting["venue"])
            if folder is not None and folder.parent != ARCHIVE_ROOT:
                updated.append(folder)
        runlog.step("refresh-active", "skipped-by-flag",
                    rebuilding=[f.name for f in updated])
    else:
        try:
            updated = step_refresh_active(runlog, today,
                                          max_meetings=args.max_meetings,
                                          rounds=args.rounds,
                                          round_gap=args.round_gap)
        except TemporaryFailure as exc:
            runlog.error("refresh-active", f"暫時性：{exc}")
            temporary = True

    # 補完當日賽日。晚更俾個站拒絕之後，呢個係唯一會再試嘅地方。已經齊嘅場次
    # 會即刻 `skipped_already_analysed`，所以冇新嘢做嗰陣成本近乎零。
    if not args.skip_analysis and not args.skip_refresh:
        try:
            filled = step_analyse_next_day(runlog, today,
                                           max_meetings=args.max_meetings,
                                           rounds=args.rounds,
                                           round_gap=args.round_gap,
                                           target_day=today.isoformat())
            for folder in filled:
                if folder not in updated:
                    updated.append(folder)
        except TemporaryFailure as exc:
            # 今日冇賽事、索引頁攞唔到 —— 都唔應該令早更失敗。
            runlog.step("fill-today", "skipped", detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            runlog.error("fill-today", f"{type(exc).__name__}: {exc}")
            temporary = True

    ok = step_dashboard(runlog, updated, [], skip_deploy=args.skip_deploy)
    step_mirror_reports(runlog, updated)
    push_run_summary(runlog, "morning")
    if updated:
        push_betting(runlog, sorted({f.name[:10] for f in updated})[0], "update")
    return finish_run(runlog, ok, temporary)


# ── 入口 ────────────────────────────────────────────────────────────────────
@contextlib.contextmanager
def single_run_lock():
    """兩個 mode 共用一把鎖 —— 佢哋都會動同一批目錄同同一個 dashboard。"""
    # ⚠️ 把鎖放喺**資料根**，唔可以放喺 checkout 入面。2026-08-09 排程搬咗去自己
    # 一個 worktree，如果鎖跟住 checkout 走，排程同一個由主 repo 手動開嘅 run 就
    # 各攞各鎖、同時郁同一批 folder、同一個 Chrome profile、同一個 dashboard ——
    # 正正係當初加鎖要防嗰件事。資料根係兩邊唯一共用嘅嘢。
    lock_path = Path(AU_RACING) / ".au_daily_schedule.lock"
    try:
        handle = lock_path.open("w")
    except OSError:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handle = (LOG_DIR / "au_daily_schedule.lock").open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


# 引擎相關嘅路徑。工作區呢幾個位一 dirty，跑出嚟嘅分數就唔係任何一個 commit
# 代表嘅版本 —— 呢個要講出嚟，唔可以扮唔知。
ENGINE_PATHS = (
    ".agents/skills/au_racing/au_wong_choi_auto/scripts",
    ".agents/skills/au_racing",
    "Horse_Racing_Dashboard/generate_static.py",
)


def engine_dirty_from_status(porcelain: str) -> list[str]:
    """`git status --porcelain` → 引擎入面相對 commit 改咗嘅已追蹤檔案。

    ⚠️ 只計已追蹤而且改咗嘅（`??` 係未追蹤，唔計）。一個未追蹤、冇人 import
    嘅新 script 唔會改變評分；cache 目錄更加唔會。冇呢個收窄嘅話每晚都會報
    「引擎 dirty」，跟住就冇人再信呢個警告。
    """
    out = set()
    for line in (porcelain or "").splitlines():
        if line.startswith("??") or len(line) < 4:
            continue
        path = line[3:].strip()
        if any(path.startswith(prefix) for prefix in ENGINE_PATHS):
            out.add(path)
    return sorted(out)


def code_version() -> dict:
    """排程實際跑緊邊個版本嘅模型。

    ⚠️ 排程執行嘅係工作區當時嘅狀態，唔係任何一個釘死嘅 ref —— 分支、未 commit
    嘅改動全部照跑。2026-08-09 實測：我啱啱 commit 完，幾分鐘後同一個工作區已經
    俾另一個 session 換咗去 `fix/tennis-…` 分支。嗰次啱啱好仍然含住所有 AU 修正，
    但嗰個係彩數唔係保證。模型一直喺度改，所以「呢份分析係邊個版本出嘅」一定要
    留低喺 run log，否則之後對唔返賬。
    """
    import subprocess

    def git(*args):
        try:
            out = subprocess.run(["git", *args], cwd=str(PROJECT_ROOT), timeout=30,
                                 capture_output=True, text=True)
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:  # noqa: BLE001
            return None

    dirty = git("status", "--porcelain") or ""
    # ⚠️ 只計**已追蹤而且相對 commit 改咗**嘅檔（`??` 係未追蹤，唔計）。一個未
    # 追蹤、冇人 import 嘅新 script 唔會改變評分；cache 目錄更加唔會。冇呢個收窄
    # 嘅話每晚都會報「引擎 dirty」，警告就冇人再信。
    engine_dirty = engine_dirty_from_status(dirty)
    return {"commit": (git("rev-parse", "--short", "HEAD") or "?"),
            "branch": (git("rev-parse", "--abbrev-ref", "HEAD") or "?"),
            "dirty_files": len(dirty.splitlines()),
            "engine_dirty": engine_dirty or None,
            "update_warning": os.environ.get("WC_AU_CODE_UPDATE_WARNING") or None}


def check_data_root(runlog: RunLog) -> bool:
    """AU 資料根 preflight。

    ⚠️ launchd 嘅 TCC context 同 Terminal 唔同 —— 實測 2026-08-04 有一次 deploy
    喺讀唔到 CloudStorage 嘅 context 跑，結果 archive filter 靜靜咁失效，發佈咗
    一份「乜都冇排除」嘅 dashboard。所以開工前要大聲講清楚讀唔讀得到。

    2026-08-05：AU_RACING 已經搬落本機硬碟，正因為 launchd 底下 CloudStorage 係
    `PermissionError: Operation not permitted`，每次排程一開工就死喺呢一步。所以
    行到呢度讀唔到，就唔再係 Full Disk Access 嘅問題 —— 而係 `AU_RACING` 指錯地方
    （`.wongchoi_au_data_root` / `WONGCHOI_AU_DATA_ROOT` 唔見咗，跌返 Drive）。
    """
    on_cloud = "CloudStorage" in str(AU_RACING)
    try:
        names = [p.name for p in AU_RACING.iterdir() if p.is_dir()]
    except OSError as exc:
        hint = ("`AU_RACING` 仍然指住 CloudStorage —— launchd 讀唔到雲端硬碟。"
                "檢查 run_au_daily_schedule.sh 有冇 export WONGCHOI_AU_DATA_ROOT，"
                "同 repo root 嘅 .wongchoi_au_data_root 仲在唔在。"
                if on_cloud else
                f"本機路徑都讀唔到，資料根可能未 mount 或者被搬走：{AU_RACING}")
        runlog.error("preflight", f"讀唔到 AU_Racing（{type(exc).__name__}: {exc}）—— "
                                 f"{hint} 分析同歸檔全部做唔到。")
        return False
    if on_cloud:
        runlog.warn(f"AU_RACING 住喺 CloudStorage（{AU_RACING}）—— 今次讀得到，但"
                    f"launchd 嘅 context 通常讀唔到。應該指去本機硬碟。")
    version = code_version()
    runlog.data["code_version"] = version
    runlog.step("preflight", "ok", au_meeting_folders=len(names),
                au_root=str(AU_RACING),
                mirror=str(AU_RACING_MIRROR) if AU_RACING_MIRROR else None,
                archive_readable=(ARCHIVE_ROOT / ".").is_dir(),
                **version)
    if version["engine_dirty"]:
        runlog.warn(
            f"引擎有 {len(version['engine_dirty'])} 個未 commit 嘅檔 —— 今次評分"
            f"唔對應任何一個 commit，之後對唔返賬："
            f"{version['engine_dirty'][:6]}")
    if version["update_warning"]:
        # wrapper 嘅 stderr 冇人會主動睇；放入 run JSON，完場 Telegram 摘要先會
        # 真正令 production branch 長期落後呢件事變成可見。
        runlog.warn(version["update_warning"])
    return True


def check_timezone(runlog: RunLog) -> None:
    """launchd 用本機 wall clock 開工。本機 TZ 唔係悉尼，排程時間就唔係悉尼時間。"""
    local = datetime.now().astimezone().tzname()
    if ZoneInfo is None:
        runlog.warn("冇 zoneinfo，日期用本機時間")
        return
    syd = datetime.now(ZoneInfo(TIMEZONE))
    if syd.utcoffset() != datetime.now().astimezone().utcoffset():
        runlog.warn(f"⚠️ 本機時區（{local}）唔等於 {TIMEZONE} —— launchd 嘅"
                    f" 22:00/10:00 已經唔係悉尼時間，要重新裝 plist 或者改機時區")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AU Wong Choi 每日自動排程 runner")
    parser.add_argument("--mode", choices=("evening", "morning"), required=True)
    parser.add_argument("--today", help="覆寫今日日期（YYYY-MM-DD），測試用")
    parser.add_argument("--skip-review", action="store_true",
                        help="evening：唔做覆盤／歸檔")
    parser.add_argument("--skip-analysis", action="store_true",
                        help="evening：唔分析下一個賽日")
    parser.add_argument("--no-archive", action="store_true",
                        help="evening：覆盤但唔搬 folder")
    parser.add_argument("--skip-deploy", action="store_true",
                        help="build + 驗證但唔發佈")
    parser.add_argument("--skip-refresh", action="store_true",
                        help="morning：唔出網覆核，直接由本機現有分析重建 + 發佈。"
                             "本機已經改過但發佈唔上去嗰陣用（唔會重抽任何一版）")
    parser.add_argument("--max-meetings", type=int, default=0,
                        help="每晚最多分析幾個場次（0 = 全部）")
    parser.add_argument("--rounds", type=int, default=8,
                        help="evening：個站拒絕之後最多再等幾輪（每個冷卻窗大約"
                             "夠抽一個場次）")
    parser.add_argument("--round-gap", type=int, default=900,
                        help="evening：每輪之間等幾秒（預設 900 = 15 分鐘）")
    parser.add_argument("--no-notify", action="store_true",
                        help="唔推任何通知。⚠️ 驗證用 —— 手動開嘅 run 逐個推一條"
                             "「partial」出去，會令真警報俾人一齊略過")
    parser.add_argument("--json", action="store_true", help="最後印出 run log JSON")
    args = parser.parse_args(argv)

    today = date.fromisoformat(args.today) if args.today else local_today()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"run-{args.mode}-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"

    with single_run_lock() as acquired:
        if not acquired:
            log("另一個 AU daily run 仲喺度跑，今次唔開工（避免撞車）。")
            return EXIT_OK
        runlog = RunLog(args.mode, today, log_path,
                        notify=not args.no_notify)
        check_timezone(runlog)
        log(f"=== AU Wong Choi {args.mode} run · day={today} "
            f"· fetch delay={fetch_delay()}s ===")
        if not check_data_root(runlog):
            runlog.finish("failed")
            return EXIT_FAILED
        try:
            if args.mode == "evening":
                code = run_evening(runlog, args, today)
            else:
                code = run_morning(runlog, args, today)
        except KeyboardInterrupt:
            close_browser(runlog)
            runlog.finish("interrupted")
            return EXIT_FAILED
        except Exception as exc:  # noqa: BLE001
            # 一定要收 Chrome —— 中途炸咗留一個 headed 窗喺度，下一次 run 會撞
            # 同一個 profile lock。
            close_browser(runlog)
            runlog.error(args.mode, f"{type(exc).__name__}: {exc}")
            runlog.finish("failed")
            return EXIT_FAILED
        if args.json:
            print(json.dumps(runlog.data, ensure_ascii=False, indent=2))
        return code


if __name__ == "__main__":
    raise SystemExit(main())
