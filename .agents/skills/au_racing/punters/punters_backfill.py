#!/usr/bin/env python3
"""補 Punters 逐駒段速：語料入面每個 AU 場次 → 每場比賽一個請求。

    /usr/bin/python3 punters_backfill.py --from 2026-08-05 --max-requests 250
    /usr/bin/python3 punters_backfill.py --from 2026-08-05 --dry-run   # 只列計劃，唔出網

可以隨時中斷再跑：cache 有嘅唔會再請求。
exit：0 = 全部補齊；3 = 到本批上限、仲有未補；2 = 被拒，已停兼 Telegram 通知（唔好自動重試）。
⚠️ 一定要喺有 GUI login 嘅 session 跑（headed Chrome），每次會彈一個 Chrome 窗。
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
for p in (HERE, REPO, REPO / ".agents" / "skills" / "shared_racing" / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import punters_store as store  # noqa: E402
from punters_fetch import PuntersFetcher, StopFetching  # noqa: E402

FOLDER_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ _](.+?)[ _]Race")
FOREIGN_SLUG = re.compile(r"-(?:[a-z]{2})-\d{8}$")   # canterbury-park-us-20260810
RACES_RE = re.compile(r"Race[ _](\d+)(?:-(\d+))?")
PROGRESS_FILE = Path.home() / ".cache" / "wongchoi" / "punters_progress.json"
MILESTONE = 20                                          # 每過 20% Telegram 一次


def corpus_meetings(since: str, until: str | None, race_counts: dict | None = None) -> dict[str, set[str]]:
    import wongchoi_paths
    from corpus_paths import meeting_dirs
    out: dict[str, set[str]] = {}
    for d in meeting_dirs(wongchoi_paths.AU_RACING):
        m = FOLDER_RE.match(d.name)
        if not m:
            continue
        date, venue = m.group(1), m.group(2).replace("_", " ")
        if date < since or (until and date > until):
            continue
        out.setdefault(date, set()).add(venue)
        if race_counts is not None:
            r = RACES_RE.search(d.name[m.end() - 4:])
            n = (int(r.group(2) or r.group(1)) - int(r.group(1)) + 1) if r else 8
            race_counts[(date, venue)] = n
    return out


def _progress_state() -> dict:
    import json
    try:
        return json.loads(PROGRESS_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_progress(state: dict) -> None:
    import json
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(state))


# ETA 假設：同 run_punters_backfill.sh／punters_fetch 嘅節奏一致。
SEC_PER_REQUEST = 16 + 120 / 25          # 12–20 秒間隔 + 每 20–30 個請求停 1–3 分鐘
BATCH_REQUESTS = 250                      # 每批 200–300
BATCH_REST_SEC = 45 * 60                  # 批之間 30–60 分鐘
QUIET_HOURS = range(0, 7)                 # 凌晨唔跑


def eta(remaining_requests: int, now=None) -> "dt.datetime":
    """模擬分批＋休息＋凌晨停，估計幾時補完。"""
    now = now or dt.datetime.now()
    left = remaining_requests
    while left > 0:
        if now.hour in QUIET_HOURS:
            now = now.replace(hour=7, minute=0, second=0)
            continue
        n = min(left, BATCH_REQUESTS)
        now += dt.timedelta(seconds=n * SEC_PER_REQUEST)
        left -= n
        if left > 0:
            now += dt.timedelta(seconds=BATCH_REST_SEC)
    return now


def _eta_text(remaining: int) -> str:
    when = eta(remaining)
    day = "今日" if when.date() == dt.date.today() else ("聽日" if when.date() == dt.date.today() + dt.timedelta(days=1) else when.strftime("%m-%d"))
    return f"預計 {day} {when:%H:%M} 左右完成（仲有約 {remaining} 個請求）"


def report_progress(done: int, total: int, requests: int, live: bool) -> None:
    """跨過新一個 20% 先通知；狀態存檔，所以每批由頭數都唔會重複發。"""
    if not live or total <= 0:
        return
    pct = min(99, int(100 * done / total))      # 100% 留畀完成總結
    step = pct // MILESTONE * MILESTONE
    state = _progress_state()
    if step >= MILESTONE and step > state.get("last_milestone", 0):
        notify(f"🏇 Punters 段速補數 {step}%（{done}/{total} 場）\n本批已發 {requests} 個請求，冇被拒。\n"
               + _eta_text(max(0, total - done)))
        state["last_milestone"] = step
        _save_progress(state)


def coverage_summary(con) -> str:
    q = lambda s: con.execute(s).fetchone()  # noqa: E731
    races = q("SELECT COUNT(DISTINCT event_id) FROM selections")[0]
    runners = q("SELECT COUNT(*) FROM selections WHERE status='RESULTED'")[0]
    forms, fin, trials, trial_sec, comm = q(
        "SELECT COUNT(*), SUM(finish_split IS NOT NULL), SUM(is_trial=1),"
        " SUM(is_trial=1 AND finish_split IS NOT NULL), SUM(video_comment IS NOT NULL) FROM forms")
    anchors_with = q("SELECT COUNT(DISTINCT anchor_selection_id) FROM forms WHERE finish_split IS NOT NULL")[0]
    pred = q("SELECT SUM(pred_speed IS NOT NULL) FROM selections WHERE status='RESULTED'")[0]
    pct = lambda a, b: f"{100 * (a or 0) / b:.1f}%" if b else "-"  # noqa: E731
    return (f"比賽 {races}｜出賽馬 {runners}\n"
            f"有段速往績嘅馬：{anchors_with}（{pct(anchors_with, runners)}）\n"
            f"往績 {forms} 條，最後 200m 段速 {pct(fin, forms)}，評述 {pct(comm, forms)}\n"
            f"試閘 {trials or 0} 條，當中有段速 {trial_sec or 0}\n"
            f"Punters speed map：{pct(pred, runners)} 匹馬有")


def match_meetings(payload: dict, venues: set[str]) -> tuple[dict[str, dict], set[str]]:
    """corpus 場地 → Punters meeting。精確 key 先，再唯一 prefix；其餘當對唔到。"""
    cands = [m for m in (payload.get("data") or {}).get("meetings") or []
             if not m["slug"].endswith("-bt") and not FOREIGN_SLUG.search(m["slug"])]
    by_key = {store.venue_key((m.get("venue") or {}).get("name")): m for m in cands}
    matched, missing = {}, set()
    for v in venues:
        k = store.venue_key(v)
        m = by_key.get(k)
        if m is None:
            pref = [mm for kk, mm in by_key.items() if kk.startswith(k) or k.startswith(kk)]
            m = pref[0] if len(pref) == 1 else None
        if m is None:
            missing.add(v)
        else:
            matched[v] = m
    return matched, missing


def notify(text: str) -> None:
    try:
        import racing_telegram
        racing_telegram.load_env()
        racing_telegram.send_message(text)
    except Exception as e:  # noqa: BLE001 — 通知失敗唔可以蓋過真正結果
        print("   (Telegram 通知失敗)", e)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="since", default="2026-08-05")
    ap.add_argument("--to", dest="until")
    ap.add_argument("--max-requests", type=int, default=250)
    ap.add_argument("--dry-run", action="store_true", help="只用 cache，唔出網")
    a = ap.parse_args(argv)

    race_counts: dict = {}
    plan = corpus_meetings(a.since, a.until, race_counts)
    total_races = sum(race_counts.values())
    print(f"語料：{len(plan)} 日、{sum(map(len, plan.values()))} 個場次、約 {total_races} 場比賽")
    con = store.connect()
    stats = dict(days=0, meetings=0, races=0, races_cached=0, missing=[])
    rc = 0
    with PuntersFetcher(max_requests=a.max_requests, cache_only=a.dry_run) as f:
        try:
            for date in sorted(plan):
                payload = f.meetings(date)
                if payload is None:
                    continue                      # dry-run 未有 cache
                matched, missing = match_meetings(payload, plan[date])
                stats["missing"] += [f"{date} {v}" for v in sorted(missing)]
                store.ingest_meetings(con, date, payload, {m["slug"] for m in matched.values()})
                con.commit()
                stats["days"] += 1
                for venue, m in sorted(matched.items()):
                    stats["meetings"] += 1
                    for ev in sorted(m.get("events") or [], key=lambda e: e.get("eventNumber") or 0):
                        ids = [s["id"] for s in ev.get("selections") or []]
                        if not ids:
                            continue
                        before = f.requests_made
                        data = f.sectionals(ids)
                        if data is None:
                            continue
                        stats["races_cached" if f.requests_made == before else "races"] += 1
                        if f.requests_made >= 1 and not stats.get("start_notified") and not a.dry_run:
                            stats["start_notified"] = True
                            done = stats["races"] + stats["races_cached"]
                            notify(f"▶️ Punters 補數本批開始，第一個請求成功。已完成 {done}/{total_races} 場"
                                   f"（{100 * done // max(total_races, 1)}%）。\n" + _eta_text(max(0, total_races - done)))
                        store.ingest_forms(con, data, {i: date for i in ids})
                        con.commit()
                        report_progress(stats["races"] + stats["races_cached"], total_races,
                                        f.requests_made, live=not a.dry_run)
                if f.requests_made:
                    print(f"   {date} 完成｜本 run 請求 {f.requests_made}／cache {f.cache_hits}", flush=True)
        except StopFetching as e:
            con.commit()
            refused = not str(e).startswith("到達本 run 上限")
            print(("🛑 被拒，已停：" if refused else "⏸ ") + str(e))
            if refused:
                rc = 2
                notify(f"🛑 Punters 段速補數停咗：{e}\n已發 {f.requests_made} 個請求。唔會自動重試，要人睇。")
            else:
                rc = 3                            # 到上限：仲有嘢未補，下一批再嚟
        store.check_as_of(con)
        print(f"請求 {f.requests_made}｜cache {f.cache_hits}｜新場 {stats['races']}｜"
              f"cache 場 {stats['races_cached']}｜日 {stats['days']}｜場次 {stats['meetings']}")
        if stats["missing"]:
            print(f"⚠️ 對唔到 Punters 場次 {len(stats['missing'])} 個：", stats["missing"][:15])
        if rc == 0 and not a.dry_run and not _progress_state().get("done_notified"):
            summary = coverage_summary(con)
            print(summary)
            notify("✅ Punters 段速補數完成（100%）\n" + summary +
                   (f"\n⚠️ 對唔到場次 {len(stats['missing'])} 個" if stats["missing"] else ""))
            st = _progress_state()
            st["done_notified"] = True
            _save_progress(st)
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — 任何意外都要通知，唔可以靜靜死（2026-10-13 中過）
        notify(f"🛑 Punters 段速補數意外停咗：{type(exc).__name__}: {str(exc).splitlines()[0][:200]}")
        raise
