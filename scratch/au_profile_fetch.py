#!/usr/bin/env python3
"""抓 Racenet 騎師／練馬師 profile 摘要統計（可續跑、有禮貌、可驗證）。

背景：`api.racenet.com.au/racing` GraphQL 有 statsByTrack / statsByJockey，
但 API host 硬 403（POST/GET/headless Playwright 全部，punters.com.au 鏡像一樣）。
唯一穿到嘅係 `curl_cffi` + `impersonate=chrome120` 打 www 嘅 HTML profile 頁，
成功率約 1/3。嗰度只有摘要 `stats`，冇 per-track / per-combo——
但摘要已經包含我哋而家冇嘅：currentSeason、lastTen、**roi / lastYearRoi / seasonRoi**、
topJockey / topCompetitor。而現有 `jockey_ly`（同一來源嘅去年總數）已經係
第四強 leaf（ρ 0.163），所以呢批更新鮮嘅同族欄位值得一試。

設計（Kelvin 兩次提醒過 Racenet 脆弱）：
  * 逐個順序，delay 可調，403 重試有 backoff
  * **逐個即時落盤**，隨時 Ctrl-C 唔會蝕，重跑自動 skip 已有嘅
  * 連續失敗達上限就停，唔會盲衝
  * 回傳嘅 name 同要求嘅名唔夾就標記 mismatch，唔會靜靜當啱
  * `--limit` 先試一小批

用法：
    python3 scratch/au_profile_fetch.py --kind jockey --limit 8
    python3 scratch/au_profile_fetch.py --kind trainer --limit 8
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))

from curl_cffi import requests  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from au_archive_calibrator import HISTORICAL_RESULTS_CSV  # noqa: E402

OUT = Path(__file__).resolve().parent / "au_profile_stats.json"
URL = "https://www.racenet.com.au/profiles/{kind}/{slug}"
# NUXT payload 用簡寫變數，所以直接由渲染好嘅 HTML 抽 stats 物件比較穩陣。
STATS_KEYS = ("totalRuns", "lastYearRuns", "lastTenRuns", "lastTenFigure",
              "winPercentage", "placePercentage", "currentSeasonRuns",
              "roi", "lastYearRoi", "seasonRoi")


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " ").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def top_names(kind: str, limit: int):
    col = "Jockey" if kind == "jockey" else "Trainer"
    counts = Counter()
    with HISTORICAL_RESULTS_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            name = str(row.get(col) or "").strip()
            if name:
                counts[name] += 1
    return [(n, c) for n, c in counts.most_common(limit)]


def parse_stats(page, html: str, tmp: Path):
    """離線用 Playwright 評估 `window.__NUXT__` —— NUXT blob 係 minify 咗嘅
    IIFE（變數用位置參數還原），regex 拆好易錯。同現有 claw scraper 同一做法。"""
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
    profile, stats = found.get("profile"), found.get("stats")
    if not stats:
        return (profile or {}).get("name"), None
    trimmed = {k: stats.get(k) for k in STATS_KEYS if stats.get(k) is not None}
    for extra in ("lastYearPlaces", "lastTenPlaces", "currentSeasonPlaces", "totalPlaces"):
        if stats.get(extra) is not None:
            trimmed[extra] = stats[extra]
    return (profile or {}).get("name"), (trimmed or None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=("jockey", "trainer"), required=True)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--delay", type=float, default=8.0,
                    help="每個請求之間秒數。Racenet 脆弱，唔好調低。")
    ap.add_argument("--retries", type=int, default=6)
    ap.add_argument("--abort-after", type=int, default=6)
    ap.add_argument("--max-requests", type=int, default=400,
                    help="硬性請求上限，防止走數")
    args = ap.parse_args()

    store = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    tmp = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/"
               "cfa8f109-e5a2-4fa7-8f2e-ee027dea6ecc/scratchpad/_profile_tmp.html")
    todo = [(n, c) for n, c in top_names(args.kind, args.limit)
            if f"{args.kind}|{slugify(n)}" not in store]
    print(f"{args.kind}: 頭 {args.limit} 個，未抓 {len(todo)} 個")
    ok = fail = mismatch = 0
    consecutive = 0
    attempts_used = 0

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    for name, runs in todo:
        slug = slugify(name)
        if attempts_used >= args.max_requests:
            print(f"\n⏹ 已達請求上限 {args.max_requests}，停止。重跑會續。")
            break
        html = None
        for attempt in range(1, args.retries + 1):
            if attempts_used >= args.max_requests:
                break
            time.sleep(args.delay)
            attempts_used += 1
            try:
                r = requests.get(URL.format(kind=args.kind, slug=slug),
                                 impersonate="chrome120", timeout=45)
            except Exception as exc:  # noqa: BLE001
                print(f"  {slug}: {type(exc).__name__}")
                continue
            if r.status_code == 200:
                html = r.text
                break
            if r.status_code == 404:
                print(f"  {slug}: 404（slug 推導唔啱？）")
                break
        if not html:
            fail += 1
            consecutive += 1
            print(f"  ✗ {slug} ({runs} runs) 攞唔到")
            if consecutive >= args.abort_after:
                print(f"\n⛔ 連續失敗 {consecutive} 個，停止。重跑會續。")
                break
            continue
        got_name, stats = parse_stats(page, html, tmp)
        if not stats:
            fail += 1; consecutive += 1
            print(f"  ✗ {slug}: 抽唔到 stats")
            continue
        flag = ""
        if got_name and slugify(got_name) != slug:
            mismatch += 1
            flag = f"  ⚠️ 名唔夾: 要 {name} / 返 {got_name}"
        store[f"{args.kind}|{slug}"] = {"name": got_name or name, "runs_in_archive": runs,
                                        "stats": stats}
        OUT.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
        ok += 1; consecutive = 0
        print(f"  ✓ {slug:26} {json.dumps(stats, ensure_ascii=False)[:150]}{flag}")

    browser.close(); pw.stop()
    print(f"\n成功 {ok} / 失敗 {fail} / 名唔夾 {mismatch}"
          f"；用咗 {attempts_used} 個請求"
          f"（成功率 {100*ok/max(1,attempts_used):.0f}%）；累計 {len(store)} 個 profile")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
