#!/usr/bin/env python3
"""AU Betfair 市場走勢記錄器（EXP-20261106-02 修訂：用 API 自己記錄，Basic 歷史數據資料檢查唔過）。**唔落注**。

    au_betfair_logger.py snapshot            # launchd 每 60 秒：未來 75 分鐘開跑嘅 AU 純種馬 WIN＋PLACE 市場，最佳買／賣價＋LTP
    au_betfair_logger.py settle [--date D]   # 每晚：配結果（WINNER／LOSER）同 BSP
    au_betfair_logger.py status --output F   # forward tracker 讀：有齊 T−60、T−5 快照兼已結算嘅場數

資料：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/betfair-market-log/<悉尼日期>/{catalogue,snapshots,settle}.jsonl`
（外置碟；冇掛載就停手唔寫，結束碼 3，每晚結算時推 Telegram）。
delayed key：價延遲 1–180 秒（每行記 `delayed`），冇成交量。harness（Pace／Trot）剔走。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import betfair_client as bf  # noqa: E402

SYDNEY = ZoneInfo("Australia/Sydney")
# 用戶 2026-11-06：數據放外置碟（Mac 內置碟位唔多）。⚠️ 唔用 symlink（AGENTS.md：拔碟 = 靜靜讀空）；
# 寫之前確認碟有掛載，冇就停手、唔寫入內置碟（否則 /Volumes/... 會靜靜變成本機資料夾）。
LOG_ROOT = Path(os.environ.get("WONGCHOI_BETFAIR_LOG_ROOT",
                               "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/betfair-market-log"))
STATE_DIR = HERE.parent / "au_daily_auto" / "work"


class DiskOffline(RuntimeError):
    pass


def ensure_log_root(root: Path | None = None) -> Path:
    """外置碟路徑（/Volumes/<碟>/...）一定要個碟真係掛載咗；其他路徑（測試）照用。"""
    root = root or LOG_ROOT
    parts = root.parts
    if len(parts) > 2 and parts[1] == "Volumes" and not os.path.ismount(os.path.join("/", parts[1], parts[2])):
        raise DiskOffline(f"外置碟 {parts[2]} 冇掛載")
    root.mkdir(parents=True, exist_ok=True)
    return root
HARNESS = re.compile(r"\b(Pace|Trot|Pacers?|Trotters?)\b", re.I)
AHEAD_MIN, BEHIND_MIN = 75, 10
QUIET_HOURS = range(1, 9)        # 悉尼 01:00–08:59 冇 AU 賽事，唔 call API
BOOK_CHUNK = 40                  # EX_BEST_OFFERS weight 5 × 40 = 200（Betfair 上限）
TARGET_RACES = 2000             # 只計 WIN（預先登記嘅分析）；PLACE 只係記錄，分析要另開協議
MARKET_TYPES = ("WIN", "PLACE")  # 用戶 2026-11-06：「can we track place as well」
WINDOWS = {"t60": (70, 60), "t15": (18, 15), "t5": (8, 5)}   # 開跑前 [早, 遲] 分鐘內最後一張未開跑快照


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day_dir(when: datetime) -> Path:
    path = ensure_log_root() / when.astimezone(SYDNEY).strftime("%Y-%m-%d")
    path.mkdir(parents=True, exist_ok=True)
    return path


def append(path: Path, rows: list[dict]) -> None:
    if rows:
        with path.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read(path: Path) -> list[dict]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return []


def is_thoroughbred(market: dict) -> bool:
    return not HARNESS.search(market.get("marketName") or "")


def catalogue(now: datetime, rpc=bf.rpc) -> list[dict]:
    flt = {"eventTypeIds": ["7"], "marketCountries": ["AU"], "marketTypeCodes": list(MARKET_TYPES),
           "marketStartTime": {"from": iso(now - timedelta(minutes=BEHIND_MIN)),
                               "to": iso(now + timedelta(minutes=AHEAD_MIN))}}
    out = rpc("listMarketCatalogue", {"filter": flt, "maxResults": 200,
                                      "marketProjection": ["MARKET_START_TIME", "RUNNER_DESCRIPTION", "EVENT",
                                                           "MARKET_DESCRIPTION"]})
    markets = out or []
    kind = lambda m: (m.get("description") or {}).get("marketType")  # noqa: E731
    key = lambda m: ((m.get("event") or {}).get("id"), m.get("marketStartTime"))  # noqa: E731
    wins = [m for m in markets if kind(m) in ("WIN", None) and is_thoroughbred(m)]
    # PLACE 市場名係「To Be Placed」，冇 Pace／Trot 字眼 —— 一定要跟返同 event 同開跑時間嘅純種馬 WIN 市場先收
    win_keys = {key(m) for m in wins}
    return wins + [m for m in markets if kind(m) == "PLACE" and key(m) in win_keys]


def book_rows(markets: list[dict], now_ms: int, rpc=bf.rpc) -> list[dict]:
    starts = {m["marketId"]: m.get("marketStartTime") for m in markets}
    rows = []
    ids = list(starts)
    for i in range(0, len(ids), BOOK_CHUNK):
        books = rpc("listMarketBook", {"marketIds": ids[i:i + BOOK_CHUNK], "priceProjection": {
            "priceData": ["EX_BEST_OFFERS"], "exBestOffersOverrides": {"bestPricesDepth": 1}}}) or []
        for book in books:
            runners = []
            for r in book.get("runners") or []:
                ex = r.get("ex") or {}
                back = (ex.get("availableToBack") or [{}])[0]
                lay = (ex.get("availableToLay") or [{}])[0]
                runners.append({"id": r.get("selectionId"), "status": r.get("status"), "ltp": r.get("lastPriceTraded"),
                                "back": back.get("price"), "back_size": back.get("size"),
                                "lay": lay.get("price"), "lay_size": lay.get("size")})
            rows.append({"ts": now_ms, "market": book.get("marketId"), "start": starts.get(book.get("marketId")),
                         "status": book.get("status"), "inplay": book.get("inplay"), "winners": book.get("numberOfWinners"),
                         "delayed": book.get("isMarketDataDelayed"), "runners": runners})
    return rows


def cmd_snapshot(now: datetime | None = None, rpc=bf.rpc) -> int:
    now = now or datetime.now(timezone.utc)
    if now.astimezone(SYDNEY).hour in QUIET_HOURS:
        return 0
    markets = catalogue(now, rpc)
    if not markets:
        return 0
    folder = day_dir(now)
    seen = {m["market"] for m in read(folder / "catalogue.jsonl")}
    append(folder / "catalogue.jsonl", [{
        "market": m["marketId"], "type": (m.get("description") or {}).get("marketType"),
        "event_id": (m.get("event") or {}).get("id"), "name": m.get("marketName"), "start": m.get("marketStartTime"),
        "event": (m.get("event") or {}).get("name"), "venue": (m.get("event") or {}).get("venue"),
        "runners": [{"id": r.get("selectionId"), "name": r.get("runnerName")} for r in m.get("runners") or []],
    } for m in markets if m["marketId"] not in seen])
    rows = book_rows(markets, int(now.timestamp() * 1000), rpc)
    append(folder / "snapshots.jsonl", rows)
    return len(rows)


def cmd_settle(date_str: str, rpc=bf.rpc) -> int:
    folder = ensure_log_root() / date_str
    ids = sorted({m["market"] for m in read(folder / "catalogue.jsonl")})
    done = {s["market"] for s in read(folder / "settle.jsonl") if s.get("status") == "CLOSED"}
    todo = [i for i in ids if i not in done]
    rows = []
    for i in range(0, len(todo), BOOK_CHUNK):
        books = rpc("listMarketBook", {"marketIds": todo[i:i + BOOK_CHUNK],
                                       "priceProjection": {"priceData": ["SP_TRADED"]}}) or []
        for book in books:
            if book.get("status") != "CLOSED":
                continue
            rows.append({"market": book.get("marketId"), "status": "CLOSED", "runners": [
                {"id": r.get("selectionId"), "status": r.get("status"),
                 "bsp": (r.get("sp") or {}).get("actualSP")} for r in book.get("runners") or []]})
    append(folder / "settle.jsonl", rows)
    return len(rows)


def usable_race(snaps: list[dict], start_iso: str) -> dict | None:
    """有齊 T−60／T−15／T−5（各自窗口內最後一張未開跑快照）→ {window: snapshot}；否則 None。"""
    t0 = datetime.strptime(start_iso.replace("Z", "+0000")[:19] + "+0000", "%Y-%m-%dT%H:%M:%S%z").timestamp() * 1000
    picked = {}
    for key, (early, late) in WINDOWS.items():
        lo, hi = t0 - early * 60000, t0 - late * 60000
        cands = [s for s in snaps if lo <= s["ts"] <= hi and not s.get("inplay") and s.get("status") == "OPEN"]
        if not cands:
            return None
        picked[key] = max(cands, key=lambda s: s["ts"])
    return picked


def market_type(row: dict) -> str:
    return row.get("type") or "WIN"      # 2026-11-06 加 PLACE 之前嘅目錄冇 type，嗰陣只記 WIN


def collect_counts(root: Path = LOG_ROOT) -> dict:
    races = days = place = 0
    for folder in sorted(p for p in root.glob("20*") if p.is_dir()):
        cat = {m["market"]: m for m in read(folder / "catalogue.jsonl")}
        settled = {s["market"] for s in read(folder / "settle.jsonl") if s.get("status") == "CLOSED"}
        snaps = {}
        for s in read(folder / "snapshots.jsonl"):
            snaps.setdefault(s["market"], []).append(s)
        ok = [m for mid, m in cat.items() if mid in settled and m.get("start") and usable_race(snaps.get(mid, []), m["start"])]
        n = sum(market_type(m) == "WIN" for m in ok)
        races += n
        place += sum(market_type(m) == "PLACE" for m in ok)
        days += bool(n)
    return {"races": races, "days": days, "place_markets": place}


def cmd_status(output: Path) -> dict:
    counts = collect_counts(ensure_log_root())
    status = {"experiment": "EXP-20261106-02", "kind": "betfair_market_log", "target_races": TARGET_RACES,
              "races_collected": counts["races"], "race_days": counts["days"],
              "place_markets_collected": counts["place_markets"],
              "outcomes_visible": False, "state": "collecting",
              "generated_at": datetime.now(timezone.utc).isoformat()}
    output.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    return status


def notify_offline(reason: str) -> None:
    """外置碟冇掛載 → 推 Telegram（primary，淨係 Kelvin）；失敗唔影響結束碼。"""
    try:
        sys.path.insert(0, str(HERE.parent / "au_daily_auto"))
        import au_notify
        au_notify.push(f"⚠️ Betfair 市場走勢記錄停咗：{reason}。插返外置碟就會自動繼續（今日嘅快照冇咗）。",
                       title="🏇 AU Betfair 記錄", audience="primary")
    except Exception as exc:  # noqa: BLE001
        print(f"Telegram 推送失敗：{type(exc).__name__}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot")
    s = sub.add_parser("settle")
    s.add_argument("--date", help="悉尼日期 YYYY-MM-DD（預設：今日同昨日）")
    st = sub.add_parser("status")
    st.add_argument("--output", required=True)
    args = ap.parse_args()
    try:
        if args.cmd == "snapshot":
            print(f"snapshot rows {cmd_snapshot()}")
        elif args.cmd == "settle":
            today = datetime.now(SYDNEY).date()
            for d in ([args.date] if args.date else [str(today - timedelta(days=1)), str(today)]):
                print(f"settle {d}: {cmd_settle(d)} markets")
        else:
            print(json.dumps(cmd_status(Path(args.output)), ensure_ascii=False))
    except bf.BetfairError as exc:
        print(f"Betfair error: {exc}", file=sys.stderr)
        return 2
    except DiskOffline as exc:
        print(f"停手（冇寫入內置碟）：{exc}", file=sys.stderr)
        if args.cmd != "snapshot":          # 每晚結算時推一次 Telegram（快照每分鐘一次，唔推）
            notify_offline(str(exc))
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
