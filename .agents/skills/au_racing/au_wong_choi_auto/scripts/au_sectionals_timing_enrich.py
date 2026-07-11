#!/usr/bin/env python3
"""Per-meeting timing_600m_* enrichment from racenet sectionals pages.

背景（2026-07-11）：timing_600m_*／timing_trial_* 嘅原始寫入代碼已喺 repo 失傳，
上游 enrichment 自 2026-06-19 起斷供。真數據源＝每場賽事 form-guide 嘅 /sectionals
子頁（apollo 內含每匹馬過去每仗嘅乾淨 sectionalTime.l600.time，連試閘）。

用法（賽前 pipeline Step 3.5，喺 build_au_logic 之後、orchestrator 之前）:
    python3 au_sectionals_timing_enrich.py "<meeting_dir>"

行為：
  - Discovery 雙路：form-guide meeting 頁（未來賽事會 hydrate）→ 失敗再試
    results 頁（過往賽事 apollo 先有 Event slugs）。
  - 語義跟舊 writer：只用最近 5 場官方賽（95.5% 舊 entries_count ≤5），
    避免全生涯陳年慢時間污染 avg/best。
  - 原始 runs 存入 _data.l600_run_history（幂等標記＋日後重算免 scrape）。
  - 全程行 racenet_transport（warmup/jitter/cooldown 反封鎖）；被封即優雅收工，
    引擎對 missing timing 本身有中性處理，唔會爆。
"""
from __future__ import annotations

import argparse
import json
import re
import statistics as st
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent.parent))  # au_racing (racenet_transport)

from racenet_transport import fetch_nuxt_data, RacenetBlockedError  # noqa: E402
from au_archive_calibrator import normalize_horse_name, get_true_horse_name  # noqa: E402

# 可信 L600 秒數帶：以舊 writer 年代 10,296 個隱含時間定（min 31.4 / p1 32.5 /
# p99 37.6 / max 41.9）。sectionals 欄有大量帶外垃圾（<25s、>60s、中位 41.8 嘅
# 混合單位），帶外一律唔採用 — 之前 25-60s 太鬆，曾製造「快過場地標準 9 秒」嘅假象。
L600_SANE = (31.0, 42.0)
RECENT_CAP = 5


def meeting_slug(dirname: str) -> tuple[str, str] | None:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(.*?)\s+Race\s", dirname)
    if not m:
        return None
    date = f"{m.group(1)}{m.group(2)}{m.group(3)}"
    track = m.group(4).lower().replace("'", "").replace(" ", "-")
    return track, date


def _apollo(payload) -> dict:
    ap = payload.get("apollo", {}) if isinstance(payload, dict) else {}
    return ap.get("defaultClient") or ap.get("horseClient") or {}


def discover_race_urls(track: str, date: str) -> dict[int, str]:
    """Return {race_number: form-guide race URL}. Tries form-guide meeting page
    (hydrates for upcoming meetings) then the results page (past meetings)."""
    base = f"https://www.racenet.com.au/form-guide/horse-racing/{track}-{date}"
    for probe in (base, f"https://www.racenet.com.au/results/horse-racing/{track}-{date}"):
        try:
            dc = _apollo(fetch_nuxt_data(probe))
        except RacenetBlockedError:
            raise
        except Exception as exc:
            print(f"  discovery fetch fail ({probe.rsplit('/', 2)[-2]}): {type(exc).__name__}")
            continue
        urls = {}
        for k, v in dc.items():
            if str(k).startswith("Event:") and isinstance(v, dict) and v.get("slug") and v.get("eventNumber"):
                urls[int(v["eventNumber"])] = f"{base}/{v['slug']}"
        if urls:
            return urls
    return {}


def collect_runs(payload) -> tuple[dict, dict]:
    comps, runs = {}, {}

    def walk(o):
        if isinstance(o, dict):
            tn = o.get("__typename")
            if tn == "Competitor" and o.get("id") and o.get("name"):
                comps[str(o["id"])] = o["name"]
            if tn == "SelectionResult" and "isTrial" in o:
                cid = str(o.get("competitorId") or "")
                sect = o.get("sectionalTime") or {}
                l600 = None
                if isinstance(sect.get("l600"), dict):
                    l600 = sect["l600"].get("time")
                runs.setdefault(cid, []).append({
                    "isTrial": bool(o.get("isTrial")),
                    "date": str(o.get("meetingDate") or ""),
                    "cond": str(o.get("trackCondition") or ""),
                    "l600": l600,
                })
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(payload)
    return comps, runs


def timing_fields(entries: list[dict]) -> dict:
    def speeds(rows, cap=RECENT_CAP):
        out = []
        for r in sorted(rows, key=lambda r: r["date"], reverse=True):
            t = r.get("l600")
            if t and L600_SANE[0] <= float(t) <= L600_SANE[1]:
                out.append((round(600.0 / float(t), 2), r))
        return out[:cap]

    official = speeds([r for r in entries if not r["isTrial"]])
    trials = speeds([r for r in entries if r["isTrial"]])
    fields: dict = {}
    if official:
        sp = [s for s, _ in official]
        fields["timing_600m_avg_speed"] = round(st.mean(sp), 2)
        fields["timing_600m_best_speed"] = max(sp)
        fields["timing_600m_recent_speed"] = sp[0]
        fields["timing_l600_entries_count"] = len(sp)
        if len(sp) >= 2:
            fields["timing_speed_variance"] = round(st.pstdev(sp), 3)
            newer = st.mean(sp[:2])
            older = st.mean(sp[2:]) if len(sp) > 2 else sp[1]
            fields["timing_600m_trend"] = ("improving" if newer - older >= 0.15
                                           else "declining" if newer - older <= -0.15
                                           else "stable")
        dry = [s for s, r in official if r["cond"].lower() in ("good", "firm")]
        if dry:
            fields["timing_dry_avg_speed"] = round(st.mean(dry), 2)
    if trials:
        fields["timing_trial_600m_avg_speed"] = round(st.mean([s for s, _ in trials]), 2)
    return fields


def main():
    parser = argparse.ArgumentParser(description="AU sectionals timing enrichment (per meeting)")
    parser.add_argument("meeting_dir", help="Meeting directory containing Race_*_Logic.json")
    args = parser.parse_args()
    meeting = Path(args.meeting_dir).resolve()
    slug = meeting_slug(meeting.name)
    if not slug:
        print(f"cannot parse meeting slug from: {meeting.name}")
        return 0
    track, date = slug

    pending = []
    for lp in sorted(meeting.glob("Race_*_Logic.json"),
                     key=lambda p: int(re.search(r"Race_(\d+)_", p.name).group(1))):
        logic = json.loads(lp.read_text(encoding="utf-8"))
        # key 存在（就算係 []＝查過但無數據）即當已處理 — 冪等，重跑唔會白 fetch
        if any("l600_run_history" not in (h.get("_data") or {})
               for h in logic.get("horses", {}).values()):
            pending.append((lp, logic))
    if not pending:
        print("timing already enriched for all races — nothing to do")
        return 0

    try:
        race_urls = discover_race_urls(track, date)
    except RacenetBlockedError as exc:
        print(f"BLOCKED during discovery — skipping enrichment (engine handles missing timing): {exc}")
        return 0
    if not race_urls:
        print("no race urls discovered — skipping enrichment")
        return 0
    print(f"discovered {len(race_urls)} race urls for {track}-{date}")

    total = 0
    for lp, logic in pending:
        rn = int(re.search(r"Race_(\d+)_", lp.name).group(1))
        url = race_urls.get(rn)
        if not url:
            print(f"  R{rn}: no url, skip")
            continue
        try:
            payload = fetch_nuxt_data(url + "/sectionals")
        except RacenetBlockedError as exc:
            print(f"BLOCKED at R{rn} — stopping gracefully: {exc}")
            break
        except Exception as exc:
            print(f"  R{rn} fetch fail: {type(exc).__name__} {str(exc)[:100]}")
            continue
        comps, runs = collect_runs(payload)
        by_name = {normalize_horse_name(n): cid for cid, n in comps.items()}
        updated = changed = 0
        for hnum, horse in logic.get("horses", {}).items():
            d = horse.setdefault("_data", {})
            if "l600_run_history" in d:
                continue
            cid = by_name.get(normalize_horse_name(get_true_horse_name(horse)))
            entries = runs.get(cid or "", [])
            fields = timing_fields(entries) if entries else {}
            if fields:
                d.update(fields)
                d["l600_run_history"] = entries[:12]
                updated += 1
            else:
                # 查過但呢匹馬無 sectionals 數據 — 落空標記，重跑唔使再 fetch
                d["l600_run_history"] = []
            changed += 1
        if changed:
            lp.write_text(json.dumps(logic, ensure_ascii=False, indent=2), encoding="utf-8")
            total += updated
        print(f"  R{rn}: horses updated {updated}")
    print(f"TOTAL horses enriched: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
