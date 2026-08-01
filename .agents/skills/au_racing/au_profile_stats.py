#!/usr/bin/env python3
"""AU 騎師／練馬師 Racenet profile 統計 —— 共享 TTL cache + 抽取整合。

點解要呢個：`jockey_ly` / `trainer_ly`（formguide payload 內嘅去年總數）係我哋
唯一嘅騎練數據，而佢哋每次 extraction 都由當時嘅 formguide 帶落嚟，所以其實
唔會過時。真正缺嘅係 formguide **冇**嘅欄位：

    winPercentage  placePercentage  roi / lastYearRoi / seasonRoi  totalRuns

呢啲只喺 profile 頁有。本 module 負責維護一個**共享、有 TTL 嘅** cache，
令每次抽取都用到夠新嘅數字，而唔使自己養一個會過時嘅資料庫。

負載控制（Racenet 好脆弱，實測機率性 403，成功率約 22%／請求）：
  * 只抓 cache 內冇、或者過咗 TTL 嘅人物 —— 跑熟之後每場邊際成本得幾個
  * 每個請求之間有 delay，403 會重試但有上限
  * 每場抽取有 `max_profiles` 硬上限，唔會因為一個大 meeting 就爆量
  * 逐個即時落盤，中斷唔會蝕
  * **失敗係非致命** —— 攞唔到就用返 cache 內舊值／跳過，抽取流程照走

⚠️ 已知限制：per-track（`statsByTrack`）同 人馬組合（`statsByJockey`/`statsByTrainer`）
只喺 `api.racenet.com.au/racing` GraphQL 有，而嗰個 host 對我哋硬 403
（POST / GET / headless Playwright / punters.com.au 鏡像全部試過）。
profile 頁 HTML 只帶摘要。所以呢度只做得到摘要。
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TTL_DAYS = 21          # 統計變得慢，三星期夠新
DEFAULT_DELAY = 8.0            # 秒。Racenet 脆弱，唔好調低。
DEFAULT_RETRIES = 4
DEFAULT_MAX_PROFILES = 25      # 每次抽取最多補幾多個人物
PROFILE_URL = "https://www.racenet.com.au/profiles/{kind}/{slug}"
STATS_KEYS = ("totalRuns", "totalPlaces", "lastYearRuns", "lastYearPlaces",
              "lastTenRuns", "lastTenPlaces", "lastTenFigure",
              "winPercentage", "placePercentage",
              "currentSeasonRuns", "currentSeasonPlaces",
              "roi", "lastYearRoi", "seasonRoi")


def cache_path() -> Path:
    """同其他 AU 參考數據一齊放喺 AU_Racing 根目錄。"""
    from wongchoi_paths import AU_RACING

    return Path(AU_RACING) / "AU_Profile_Stats_Cache.json"


def slugify(name: str) -> str:
    """Racenet slug 規則：去 accent、細寫、& 同 ' 當空白／刪走、其餘轉連字號。

    對得上實測樣本：`Annabel & Rob Archibald` → `annabel-rob-archibald`、
    `Ben, Will & Jd Hayes` → `ben-will-jd-hayes`。
    """
    text = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    text = text.lower().replace("&", " ").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def load_cache(path: Path | None = None) -> dict:
    path = path or cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _is_fresh(entry: dict, ttl_days: int) -> bool:
    stamp = entry.get("fetched_at")
    if not stamp:
        return False
    try:
        fetched = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched).days < ttl_days


def stale_keys(wanted, cache: dict, ttl_days: int = DEFAULT_TTL_DAYS):
    """`wanted` = [(kind, name)]；回傳需要抓嘅 (kind, slug, name)，已去重。"""
    out, seen = [], set()
    for kind, name in wanted:
        slug = slugify(name)
        if not slug:
            continue
        key = f"{kind}|{slug}"
        if key in seen:
            continue
        seen.add(key)
        entry = cache.get(key)
        if entry and _is_fresh(entry, ttl_days):
            continue
        out.append((kind, slug, name))
    return out


def _extract_stats(page, html: str, tmp: Path):
    """離線 Playwright 讀 `window.__NUXT__` —— NUXT blob 係 minify 咗嘅 IIFE，
    regex 拆好易錯（同 claw_racenet_scraper 同一做法）。"""
    tmp.write_text(html, encoding="utf-8")
    page.goto(f"file://{tmp}", wait_until="domcontentloaded")
    nuxt = page.evaluate("() => window.__NUXT__")
    if not isinstance(nuxt, dict):
        return None, None
    found = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("__typename") == "Stats" and "winPercentage" in node:
                found.setdefault("stats", node)
            if node.get("__typename") in ("Jockey", "Trainer") and node.get("slug"):
                found.setdefault("profile", node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(nuxt)
    stats = found.get("stats")
    if not stats:
        return (found.get("profile") or {}).get("name"), None
    trimmed = {k: stats[k] for k in STATS_KEYS if stats.get(k) is not None}
    return (found.get("profile") or {}).get("name"), (trimmed or None)


def stale_slugs(triples, cache: dict, ttl_days: int = DEFAULT_TTL_DAYS):
    """同 `stale_keys` 一樣，但收 (kind, slug, name) —— slug 由 Racenet payload
    直接嚟，比人名推導可靠（`jockey.slug` / `trainer.slug` 每場都有）。"""
    out, seen = [], set()
    for kind, slug, name in triples:
        if not slug:
            continue
        key = f"{kind}|{slug}"
        if key in seen:
            continue
        seen.add(key)
        entry = cache.get(key)
        if entry and _is_fresh(entry, ttl_days):
            continue
        out.append((kind, slug, name))
    return out


def refresh(wanted, *, ttl_days=DEFAULT_TTL_DAYS, delay=DEFAULT_DELAY,
            retries=DEFAULT_RETRIES, max_profiles=DEFAULT_MAX_PROFILES,
            path=None, verbose=True, exact_slugs=False) -> dict:
    """補抓過期／缺失嘅 profile，回傳更新後嘅 cache。失敗係非致命。

    `wanted` 預設係 [(kind, name)]；`exact_slugs=True` 時收 [(kind, slug, name)]。
    """
    path = path or cache_path()
    cache = load_cache(path)
    todo = (stale_slugs(wanted, cache, ttl_days) if exact_slugs
            else stale_keys(wanted, cache, ttl_days))
    if not todo:
        if verbose:
            print(f"   騎練 profile: {len(cache)} 個已足夠新，唔使抓")
        return cache
    capped = todo[:max_profiles]
    if verbose:
        print(f"   騎練 profile: 需要補 {len(todo)} 個，今次抓 {len(capped)} 個"
              f"（cache {len(cache)}，TTL {ttl_days} 日）")

    try:
        from curl_cffi import requests
        from playwright.sync_api import sync_playwright
    except ImportError as exc:      # 抽取流程唔應該因為呢個而死
        if verbose:
            print(f"   ⚠️ 缺 dependency（{exc}），略過 profile 更新")
        return cache

    tmp = path.parent / ".profile_tmp.html"
    ok = 0
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    try:
        for kind, slug, name in capped:
            html = None
            for _ in range(retries):
                time.sleep(delay)
                try:
                    resp = requests.get(PROFILE_URL.format(kind=kind, slug=slug),
                                        impersonate="chrome120", timeout=45)
                except Exception:      # noqa: BLE001 — 網絡問題唔應該中斷抽取
                    continue
                if resp.status_code == 200:
                    html = resp.text
                    break
                if resp.status_code == 404:
                    break              # slug 推導唔啱，唔使再試
            if not html:
                continue
            got_name, stats = _extract_stats(page, html, tmp)
            if not stats:
                continue
            cache[f"{kind}|{slug}"] = {
                "name": got_name or name,
                "stats": stats,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                # 返回名同要求名唔夾 = slug 推導撞錯人，標出嚟唔好靜靜當啱
                "name_mismatch": bool(got_name and slugify(got_name) != slug),
            }
            path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            ok += 1
    finally:
        browser.close()
        pw.stop()
        tmp.unlink(missing_ok=True)
    if verbose:
        print(f"   騎練 profile: 成功補 {ok}/{len(capped)} 個，cache 共 {len(cache)}")
    return cache


def lookup(cache: dict, kind: str, name: str):
    """按人名攞統計；名唔夾嘅記錄唔會回傳（寧可冇數據，唔要錯數據）。"""
    entry = cache.get(f"{kind}|{slugify(name)}")
    if not entry or entry.get("name_mismatch"):
        return None
    return entry.get("stats")
