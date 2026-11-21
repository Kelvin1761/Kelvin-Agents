"""Ladbrokes 定額賠率記錄（用戶 2026-11-21：「將 Ladbrokes 加入記錄器，同 Betfair 一齊每分鐘記」）。只讀，唔落注。

來源：Ladbrokes 網站自己用嘅公開 REST（唔使登入）：
    nextraces：`https://api.ladbrokes.com.au/rest/v1/racing/?method=nextraces&count=100`
    racecard ：`...?method=racecard&id=<race_id>` → entrants、prices（`<entrant>:<產品>:` → 分數賠率）、price_fluctuations

⚠️ 產品 ID 冇官方文件。2026-11-21 用網頁顯示嘅「Fixed Win／Place」對兩場（Gosford R6 7 匹派兩位、Morphettville R8 16 匹派三位）
逐匹核實：WIN = `15832bcb…`（7/7、16/16；另有 8 個 ID 永遠同值），PLACE = `7cf3eea6…`（兩場都全中；其餘候選只中一場）。
Ladbrokes 改 ID 嘅話每匹都會冇價 —— 每行記 `win_missing`，狀態檔會報覆蓋率，冇就推 Telegram（`mapping_health`）。

另外：Ladbrokes 網頁嘅「Tracker」（Backers／Staked 比例）喺私人 GraphQL，自動安全檢查判定未經授權存取，**冇做**。
密度：開跑前 20 分鐘內每次 run 都影；20–75 分鐘只喺分鐘數係 5 嘅倍數先影（T−60 窗口 10 分鐘闊，一定捉到）。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.ladbrokes.com.au/rest/v1/racing/"
HEADERS = {"User-Agent": "WongChoi-research/1.0 (personal, read-only)", "Accept": "application/json"}
THOROUGHBRED = "4a2788f8-e825-4d36-9894-efd4baf1cfae"
FIXED_WIN = "15832bcb-dd03-4f43-ab62-35f26be5eedb"
FIXED_PLACE = "7cf3eea6-5654-42be-9c2e-6de280e7bb34"
AHEAD_MIN, BEHIND_MIN, DENSE_MIN = 75, 10, 20
PAUSE_S = 0.4                    # 每個 racecard 之間停一停，唔好連續轟


class LadbrokesError(RuntimeError):
    pass


def _get(params: str) -> dict:
    req = urllib.request.Request(BASE + "?" + params, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError) as exc:
        raise LadbrokesError(f"{params.split('&')[0]}: {type(exc).__name__}") from None
    if body.get("status") != 200 or not isinstance(body.get("data"), dict):
        raise LadbrokesError(f"{params.split('&')[0]}: status {body.get('status')}")
    return body["data"]


def decimal(odds: dict | None) -> float | None:
    """分數賠率 → 十進制（27/10 → 3.70）；冇分子 = 冇價。"""
    if not odds or "numerator" not in odds or not odds.get("denominator"):
        return None
    return round(odds["numerator"] / odds["denominator"] + 1, 3)


def upcoming(now: datetime, get=_get) -> list[dict]:
    """未來 75 分鐘（同已過 10 分鐘）開跑嘅 AU 純種馬賽事。"""
    data = get("method=nextraces&count=100")
    out = []
    for rid in data.get("next_to_go_ids") or []:
        s = (data.get("race_summaries") or {}).get(rid) or {}
        start = (s.get("advertised_start") or {}).get("seconds")
        if s.get("category_id") != THOROUGHBRED or s.get("venue_country") != "AUS" or not start:
            continue
        mins = (start - now.timestamp()) / 60
        if -BEHIND_MIN <= mins <= AHEAD_MIN:
            out.append({**s, "minutes_to_start": mins})
    return out


def due(summary: dict, now: datetime) -> bool:
    return summary["minutes_to_start"] <= DENSE_MIN or now.minute % 5 == 0


def race_row(summary: dict, data: dict, now_ms: int) -> dict:
    final = next((m for m in (data.get("markets") or {}).values() if m.get("name") == "Final Field"), {})
    prices: dict[str, dict] = {}
    for key, val in (data.get("prices") or {}).items():
        parts = key.split(":")
        if len(parts) >= 2 and parts[1] in (FIXED_WIN, FIXED_PLACE):
            prices.setdefault(parts[0], {})["win" if parts[1] == FIXED_WIN else "place"] = decimal(val.get("odds"))
    flucs = data.get("price_fluctuations") or {}
    entrants = []
    for eid in final.get("entrant_ids") or []:
        e = (data.get("entrants") or {}).get(eid) or {}
        p = prices.get(eid, {})
        entrants.append({"id": eid, "number": e.get("number"), "name": e.get("name"), "barrier": e.get("barrier"),
                         "win": p.get("win"), "place": p.get("place"), "flucs": flucs.get(eid)})
    priced = [x for x in entrants if x["win"]]
    return {"ts": now_ms, "race": summary.get("race_id"), "meeting": summary.get("meeting_name"),
            "state": summary.get("venue_state"), "number": summary.get("race_number"),
            "start": (summary.get("advertised_start") or {}).get("seconds"),
            "entrants": entrants,
            "win_missing": len(entrants) - len(priced)}


def snapshot(now: datetime | None = None, get=_get, sleep=time.sleep) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = []
    for s in upcoming(now, get):
        if not due(s, now):
            continue
        try:
            data = get(f"method=racecard&id={s['race_id']}")
        except LadbrokesError:
            continue                    # 單場失敗唔影響其他場；覆蓋率喺狀態檔睇
        rows.append(race_row(s, data, int(now.timestamp() * 1000)))
        sleep(PAUSE_S)
    return rows


def mapping_health(rows: list[dict]) -> dict:
    """一日嘅 Ladbrokes 行：有幾多場、幾多場 ≥ 80% 馬有定額 WIN（產品 ID 失效 = 0）。"""
    races = {}
    for r in rows:
        n = len(r.get("entrants") or [])
        if n:
            races[r["race"]] = max(races.get(r["race"], 0.0), 1 - r.get("win_missing", n) / n)
    good = sum(1 for v in races.values() if v >= 0.8)
    return {"races": len(races), "races_priced": good}
