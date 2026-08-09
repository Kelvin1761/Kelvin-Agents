#!/usr/bin/env python3
"""輕量 backfill：只抽每匹馬歷史 run 嘅 `eventStarters` / `margin`，唔重跑 pipeline。

Racenet 好脆弱（實測會 403），所以呢個 script 刻意保守：

  * 順序、單線程，每次請求之間有 delay（預設 4s，`--delay` 可調）
  * 403 / 非 200 用 exponential backoff 重試（預設 3 次）
  * 連續失敗達 `--abort-after`（預設 5）就停，唔會盲衝
  * **逐場即時寫入** output JSON → 隨時 Ctrl-C 都唔會蝕，重跑會自動 skip 已完成
  * 完全唔寫任何嘢入 Drive meeting folder（只寫 scratch/）
  * `--limit` 可以先跑幾個 meeting 驗證

抽嘅係 FormGuidePrint payload 內每個 selection 嘅 `forms[]`，即係
`claw_racenet_scraper.py` 用嘅同一個來源，所以欄位語義一致。

用法：
    python3 scratch/au_starters_backfill.py --limit 3            # 先試 3 個 meeting
    python3 scratch/au_starters_backfill.py                      # 全量（會續跑）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))

from curl_cffi import requests  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from au_archive_calibrator import ARCHIVE_ROOT  # noqa: E402

OUT = Path(__file__).resolve().parent / "au_starters_backfill.json"
PRINT_URL = ("https://www.racenet.com.au/form-guide/horse-racing/print"
             "?meetingSlug={meeting}&eventSlug=race-{race}&printSlug=print-form")
MEETING_DIR = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(.*?)(?:\s+Race\s+(\d+)-(\d+))?$")


def slugify_venue(venue: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", venue.strip().lower()).strip("-")


def discover_meetings():
    """(date, venue, slug, n_races) for every archived AU meeting folder."""
    out = []
    for folder in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
        m = MEETING_DIR.match(folder.name)
        if not m or not m.group(1):
            continue
        date, venue, _, last = m.group(1), m.group(2).strip(), m.group(3), m.group(4)
        n_races = int(last) if last else len(list(folder.glob("Race_*_Logic.json"))) or 0
        if not n_races:
            n_races = len(list(folder.glob("*Formguide.md")))
        if not n_races:
            continue
        slug = f"{slugify_venue(venue)}-{date.replace('-', '')}"
        out.append({"date": date, "venue": venue, "slug": slug,
                    "races": n_races, "folder": folder.name})
    return out


def fetch_nuxt(page, meeting_slug, race_no, *, retries, delay, tmp):
    url = PRINT_URL.format(meeting=meeting_slug, race=race_no)
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, impersonate="chrome120", timeout=45)
            if resp.status_code == 200:
                tmp.write_text(resp.text, encoding="utf-8")
                page.goto(f"file://{tmp}", wait_until="domcontentloaded")
                nuxt = page.evaluate("() => window.__NUXT__")
                if nuxt:
                    return nuxt, None
                return None, "no_nuxt"
            err = f"HTTP {resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            backoff = delay * (2 ** attempt)
            print(f"      retry {attempt}/{retries - 1} after {err} — sleep {backoff:.0f}s",
                  flush=True)
            time.sleep(backoff)
    return None, err


def parse_runs(nuxt):
    """[{horse, date, venue, race_no, distance, place, starters, margin}] for the race."""
    fetch = nuxt.get("fetch", {}) or {}
    key = next((k for k in fetch if k.startswith("FormGuidePrint")), None)
    if not key:
        return None
    selections = (fetch.get(key) or {}).get("selections") or []
    if not selections:
        return None
    rows = []
    for sel in selections:
        if not isinstance(sel, dict):
            continue
        horse = ((sel.get("competitor") or {}).get("name")
                 if isinstance(sel.get("competitor"), dict) else None) or sel.get("name")
        for pr in (sel.get("forms") or []):
            if not isinstance(pr, dict):
                continue
            rows.append({
                "horse": horse,
                "date": str(pr.get("meetingDate") or "")[:10],
                "venue": pr.get("meetingName"),
                "race_no": pr.get("eventNumber"),
                "distance": pr.get("eventDistance"),
                "place": pr.get("finishPosition"),
                "starters": pr.get("eventStarters"),
                "margin": pr.get("margin"),
                "is_trial": bool(pr.get("isTrial")),
            })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=4.0,
                    help="每次請求之間嘅秒數（預設 4，Racenet 脆弱請勿調低）")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--abort-after", type=int, default=5,
                    help="連續失敗幾多場就停")
    ap.add_argument("--limit", type=int, default=0, help="只跑頭 N 個 meeting（0 = 全部）")
    args = ap.parse_args()

    store = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"races": {}}
    done = store["races"]
    meetings = discover_meetings()
    if args.limit:
        meetings = meetings[: args.limit]

    pending = [(mt, r) for mt in meetings for r in range(1, mt["races"] + 1)
               if f"{mt['slug']}|{r}" not in done]
    print(f"meetings {len(meetings)}  已完成 {len(done)} 場  待抽 {len(pending)} 場")
    print(f"pacing: delay {args.delay}s, retries {args.retries}, "
          f"abort after {args.abort_after} consecutive failures\n", flush=True)
    if not pending:
        print("冇嘢要抽。")
        return

    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / "au_starters_tmp.html"
    consecutive = 0
    ok = fail = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            for mt, race_no in pending:
                key = f"{mt['slug']}|{race_no}"
                time.sleep(args.delay)
                nuxt, err = fetch_nuxt(page, mt["slug"], race_no,
                                       retries=args.retries, delay=args.delay, tmp=tmp)
                rows = parse_runs(nuxt) if nuxt else None
                if rows:
                    done[key] = rows
                    ok += 1
                    consecutive = 0
                    starters = sum(1 for r in rows if r.get("starters"))
                    print(f"  ✓ {mt['date']} {mt['venue']} R{race_no}: "
                          f"{len(rows)} runs, starters {starters}", flush=True)
                else:
                    fail += 1
                    consecutive += 1
                    print(f"  ✗ {mt['date']} {mt['venue']} R{race_no}: "
                          f"{err or 'no_selections'} (連續失敗 {consecutive})", flush=True)
                # 逐場即時落盤 —— 隨時中斷都唔蝕
                OUT.write_text(json.dumps(store), encoding="utf-8")
                if consecutive >= args.abort_after:
                    print(f"\n⛔ 連續失敗 {consecutive} 場，停止以免再壓 Racenet。"
                          f" 已抽 {ok} 場，重跑會自動續。")
                    break
        except KeyboardInterrupt:
            print("\n中斷 — 已抽嘅場次已落盤，重跑會自動續。")
        finally:
            browser.close()
            OUT.write_text(json.dumps(store), encoding="utf-8")

    total_runs = sum(len(v) for v in done.values())
    with_starters = sum(1 for v in done.values() for r in v if r.get("starters"))
    with_margin = sum(1 for v in done.values() for r in v if r.get("margin") is not None)
    print(f"\n本次成功 {ok} / 失敗 {fail}；累計 {len(done)} 場、{total_runs} runs")
    print(f"  starters 有值: {with_starters}/{total_runs}"
          f" = {100*with_starters/max(1,total_runs):.1f}%")
    print(f"  margin  有值: {with_margin}/{total_runs}"
          f" = {100*with_margin/max(1,total_runs):.1f}%")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
