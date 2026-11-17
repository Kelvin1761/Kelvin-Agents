"""AU 賽日 Betfair 交易所價（只讀）→ 俾 dashboard 落注格底用細灰字顯示。

Kelvin 2026-11-17：「primarily use sportsbet odds as ROI and dashboard display, but start seeing if we can
display the betfair odds probably bottom of the box in a smaller grey text that is not editable」。

所以呢度**唔入 ROI、唔入評分、唔預填輸入格**，只係影一個時間點嘅最佳買入價（back），
同 Sportsbet 賠率分開存（`betfair_odds_history.json`，追加式）。

對馬：Betfair AU 嘅 `runnerName` 冇馬號（例：`Smoke Screen`），市場名喺唔帶 MARKET_DESCRIPTION 時亦冇
場次號，所以**用馬名對**：同一個場地同一日，一匹馬只會喺一場出現。名唔唯一就唔要（寧願冇價都唔好貼錯）。

⚠️ 2026-11-17 19:00 起 `listMarketCatalogue` 加任何 description 投影都回 `UNEXPECTED_ERROR`
（連 60 秒記錄器都係），17:02 之前正常。所以呢度失敗只會跳過，唔可以影響 Sportsbet 賠率或者成個 run。
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import betfair_client as bf  # noqa: E402

SYDNEY = ZoneInfo("Australia/Sydney")
HARNESS = re.compile(r"\b(Pace|Trot|Pacers?|Trotters?)\b", re.I)
BOOK_CHUNK = 40                      # EX_BEST_OFFERS weight 5 × 40 = 200
ENV_FILE = Path.home() / ".wongchoi_betfair.env"


def norm(name: object) -> str:
    """馬名比較用：細楷、淨係字母數字（`Don't Back Down` == `Dont Back Down`）。"""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^\d+\.\s*", "", str(name or "")).lower())


def load_env_file(path: Path = ENV_FILE) -> bool:
    """排程主 process 冇 source Betfair env（只有 auxiliary job 有）→ 呢度讀入 `os.environ`。

    已經有 `BETFAIR_APP_KEY` 就唔郁。**永遠唔會印、唔會寫出任何值。**
    """
    if os.environ.get("BETFAIR_APP_KEY"):
        return True
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        if re.fullmatch(r"BETFAIR_[A-Z_]+", key):
            os.environ.setdefault(key, value.strip().strip("'\""))
    return bool(os.environ.get("BETFAIR_APP_KEY"))


def _day_window(day: date) -> tuple[str, str]:
    start = datetime.combine(day, time(0, 0), SYDNEY).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.strftime(fmt), end.strftime(fmt)


def _venue_matches(bf_venue: str, ours: str) -> bool:
    a, b = norm(bf_venue), norm(ours)
    return bool(a) and (a == b or b.startswith(a) or a.startswith(b))   # Sandown ↔ Sandown Lakeside


def venue_prices(day: date, venue: str, rpc=bf.rpc) -> dict[str, dict[str, float]]:
    """→ `{馬名(norm): {"win": 最佳買入價, "place": 最佳買入價}}`，只收有價嘅。

    任何 Betfair 錯誤直接拋 `BetfairError`，由 caller 決定點樣跳過。
    """
    lo, hi = _day_window(day)
    markets = []
    for kind in ("WIN", "PLACE"):
        found = rpc("listMarketCatalogue", {
            "filter": {"eventTypeIds": ["7"], "marketCountries": ["AU"], "marketTypeCodes": [kind],
                       "marketStartTime": {"from": lo, "to": hi}},
            "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
            "maxResults": 200}) or []
        markets += [(kind, m) for m in found]
    venues = {(m.get("event") or {}).get("venue") for _, m in markets}
    hits = [v for v in venues if v and _venue_matches(v, venue)]
    if len(hits) != 1:          # 冇或者唔唯一（例如兩個 Sandown）→ 唔貼
        return {}
    mine = [(k, m) for k, m in markets if (m.get("event") or {}).get("venue") == hits[0]
            and not HARNESS.search(m.get("marketName") or "")]
    names: dict[tuple[str, int], str] = {}
    for kind, m in mine:
        for r in m.get("runners") or []:
            names[(m["marketId"], r.get("selectionId"))] = norm(r.get("runnerName"))
    kind_of = {m["marketId"]: kind for kind, m in mine}
    ids = list(kind_of)
    out: dict[str, dict[str, float]] = {}
    seen: dict[tuple[str, str], int] = {}
    for i in range(0, len(ids), BOOK_CHUNK):
        books = rpc("listMarketBook", {"marketIds": ids[i:i + BOOK_CHUNK], "priceProjection": {
            "priceData": ["EX_BEST_OFFERS"], "exBestOffersOverrides": {"bestPricesDepth": 1}}}) or []
        for book in books:
            if book.get("status") != "OPEN" or book.get("inplay"):
                continue
            kind = "win" if kind_of.get(book.get("marketId")) == "WIN" else "place"
            for r in book.get("runners") or []:
                if r.get("status") != "ACTIVE":
                    continue
                name = names.get((book.get("marketId"), r.get("selectionId")))
                back = ((r.get("ex") or {}).get("availableToBack") or [{}])[0].get("price")
                if not name or not back:
                    continue
                seen[(name, kind)] = seen.get((name, kind), 0) + 1
                out.setdefault(name, {})[kind] = float(back)
    for (name, kind), count in seen.items():   # 同名出現喺兩場 → 對唔準，成匹唔要
        if count > 1:
            out.pop(name, None)
    return out
