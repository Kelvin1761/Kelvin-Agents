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


# 佔位／未知人名 —— 抓佢哋一定 404，但一樣會食掉一個 max_profiles 名額。
JUNK_NAMES = {"", "unknown", "n/a", "na", "tbа", "tba", "-", "vacant"}


def _is_junk(name) -> bool:
    return str(name or "").strip().lower() in JUNK_NAMES


def _prioritise(triples):
    """按出現次數（＝當日策騎／派馬數）由多到少排。

    ⚠️ 呢個好緊要。`max_profiles` 一場只補得幾十個，而一個馬場有 60–95 個
    不重複騎練，所以**次序決定咗邊個攞到名額**。以前係「邊個喺 Race 1 先出現」，
    即係一個得一隻馬嘅見習騎師可以霸咗 Ciaron Maher（全澳最大馬房、逐場都有馬）
    個位。實測 12 個馬場：練馬師覆蓋率得 33–59%，而缺失名單每一場都有 Ciaron Maher。

    `wanted` 由抽取器逐匹馬 append，所以重複次數本身就係權重，唔使另外傳。
    """
    counts = {}
    order = []
    for kind, slug, name in triples:
        key = (kind, slug)
        if key not in counts:
            counts[key] = 0
            order.append((kind, slug, name))
        counts[key] += 1
    return sorted(order, key=lambda t: -counts[(t[0], t[1])])


def stale_keys(wanted, cache: dict, ttl_days: int = DEFAULT_TTL_DAYS):
    """`wanted` = [(kind, name)]；回傳需要抓嘅 (kind, slug, name)，按重要性排序。"""
    return stale_slugs([(kind, slugify(name), name) for kind, name in wanted],
                       cache, ttl_days)


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
    直接嚟，比人名推導可靠（`jockey.slug` / `trainer.slug` 每場都有）。

    輸出按出現次數排序（見 `_prioritise`），因為 `max_profiles` 令次序等於優先權。
    """
    wanted = [(kind, slug, name) for kind, slug, name in triples
              if slug and not _is_junk(name) and not _is_junk(slug)]
    out = []
    for kind, slug, name in _prioritise(wanted):
        entry = cache.get(f"{kind}|{slug}")
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
            record = {
                "name": got_name or name,
                "stats": stats,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                # 返回名同要求名唔夾 = slug 推導撞錯人，標出嚟唔好靜靜當啱
                "name_mismatch": bool(got_name and slugify(got_name) != slug),
            }
            cache[f"{kind}|{slug}"] = record
            # 別名 key：抽取器用 payload 嘅真 slug 存，但評分引擎手上只有顯示名，
            # 所以佢查嘅係 `slugify(顯示名)`。兩者唔一定一樣 ——
            #   Braith Nock A               → 存 braith-nock，引擎查 braith-nock-a
            #   P Moody & Katherine Coleman → 存 peter-moody-katherine-coleman
            # 咁就變成「抓到咗數據但用唔到」。實測 150 個記錄有 2 個中招。
            # ⚠️ 呢個同 `name_mismatch` 係兩件事：嗰個問「抓返嚟係咪同一個人」
            # （呢兩個係，所以正確咁 False）；呢度問「人名查唔查得返出嚟」。
            for alias_name in {name, got_name or ""}:
                alias = slugify(alias_name)
                if alias and alias != slug:
                    cache[f"{kind}|{alias}"] = dict(record, alias_of=f"{kind}|{slug}")
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


# ── 獨立補數工具 ────────────────────────────────────────────────────────────
# 淨係靠抽取時補數係唔夠嘅：一個馬場有 60–95 個不重複騎練，但 `max_profiles`
# 一次得幾十個，所以覆蓋率長期停喺騎師 50–70% / 練馬師 33–59%。呢個 CLI 令
# 兩次抽取之間都可以慢慢追，唔使加重任何一次抽取嘅負載。

def people_in_meetings(meeting_dirs, verbose=True):
    """由 Logic.json 抽 (kind, slug, name)，逐匹馬一個 entry（重複＝權重）。"""
    out = []
    for md in meeting_dirs:
        try:
            paths = sorted(md.glob("Race_*_Logic.json"))
        except OSError:
            continue
        for lp in paths:
            try:
                data = json.loads(lp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for horse in (data.get("horses") or {}).values():
                if not isinstance(horse, dict):
                    continue
                for kind in ("jockey", "trainer"):
                    name = (horse.get(kind) or "").strip()
                    if name and not _is_junk(name):
                        out.append((kind, slugify(name), name))
        if verbose:
            print(f"   掃完 {md.name}（累計 {len(out)} 個人次）")
    return out


def _live_meeting_dirs():
    from wongchoi_paths import AU_RACING

    root = Path(AU_RACING)
    return [p for p in sorted(root.iterdir()) if p.is_dir() and p.name != "Archive"]


def _main():
    import argparse

    ap = argparse.ArgumentParser(description="Racenet 騎練 profile cache 維護")
    ap.add_argument("cmd", choices=("status", "backfill", "repair-aliases"))
    ap.add_argument("--limit", type=int, default=10,
                    help="今次最多抓幾多個（預設 10，刻意細 —— Racenet 脆弱）")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    ap.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    ap.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    ap.add_argument("--names", nargs="*", metavar="kind:Name",
                    help='唔掃 meeting，直接指定，例如 trainer:"Ciaron Maher"')
    args = ap.parse_args()

    cache = load_cache()

    if args.cmd == "repair-aliases":
        # 補返舊記錄嘅人名別名（唔使上網）。新抓嘅由 `refresh` 自動寫。
        added = 0
        for key, entry in list(cache.items()):
            if not isinstance(entry, dict) or entry.get("alias_of"):
                continue
            kind, _, slug = key.partition("|")
            alias = slugify(entry.get("name") or "")
            if alias and alias != slug and f"{kind}|{alias}" not in cache:
                cache[f"{kind}|{alias}"] = dict(entry, alias_of=key)
                print(f"   + {kind}|{alias}  →  {key}   ({entry.get('name')})")
                added += 1
        if added:
            cache_path().write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print(f"補咗 {added} 個別名，cache 共 {len(cache)} 個 key")
        return

    if args.names:
        wanted = []
        for item in args.names:
            kind, _, name = item.partition(":")
            wanted.append((kind.strip(), slugify(name), name.strip()))
    else:
        wanted = people_in_meetings(_live_meeting_dirs())

    todo = stale_slugs(wanted, cache, args.ttl_days)
    counts = {}
    for kind, slug, _ in wanted:
        counts[(kind, slug)] = counts.get((kind, slug), 0) + 1
    distinct = len(counts)
    have = distinct - len(todo)
    print(f"\ncache {len(cache)} 個記錄；掃到 {distinct} 個不重複騎練，"
          f"已有夠新嘅 {have}（{100 * have / max(1, distinct):.0f}%），仲差 {len(todo)}")
    if todo:
        print("\n最值得補嘅（按出賽次數排）：")
        for kind, slug, name in todo[:15]:
            print(f"   {counts[(kind, slug)]:>3} 次  {kind:8} {name}")

    if args.cmd == "status" or not todo:
        return
    print(f"\n開始補數，今次上限 {args.limit} 個，每個請求隔 {args.delay:g} 秒……")
    refresh(todo, ttl_days=args.ttl_days, delay=args.delay, retries=args.retries,
            max_profiles=args.limit, exact_slugs=True)


if __name__ == "__main__":
    import sys as _sys

    # `wongchoi_paths` 住喺 repo 根 —— 由 .agents/skills/au_racing/ 上返三層。
    _sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    _main()
