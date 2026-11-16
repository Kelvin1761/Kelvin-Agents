"""落注策略插頭 —— 每個策略 = 一個 function，回 (候選注 list, 備註 list)。

⚠️ 真正用邊個策略**未決定**（另一個研究跑緊）。預設 `none` = 一注都冇。
策略只係「提議」；所有開關、限額、重覆檢查都喺 `betfair_betting.run()` 做，策略繞唔過。

候選注格式（同 `--bets` JSON 一樣）：
    {"market_id": "1.234", "selection_id": 123, "side": "BACK", "stake": 5,
     "order_type": "LIMIT_ON_CLOSE", "min_price": 1.5, "strategy": "au_betting_place",
     "reason": "...", "label": "Randwick R3 #1 A (PLACE)"}

加新策略：寫一個 `def xxx(day, config, rpc, **kw) -> (bets, notes)`，加入 `STRATEGIES`；
上 live 之前仲要將佢個名加入 `betting_config.json` 嘅 `allowed_strategies`（第五道閘）。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
SYDNEY = ZoneInfo("Australia/Sydney")
HARNESS = re.compile(r"\b(Pace|Trot|Pacers?|Trotters?)\b", re.I)


def none(day: str, config: dict, rpc=None, **_kw):
    return [], ["策略 none：唔產生任何注（預設）"]


def json_file(day: str, config: dict, rpc=None, bets_in: str | None = None, **_kw):
    if not bets_in:
        return [], ["strategy=json 要 --bets-in"]
    data = json.loads(Path(bets_in).read_text(encoding="utf-8"))
    bets = data.get("bets") if isinstance(data, dict) else data
    return list(bets or []), [f"由 {bets_in} 讀咗 {len(bets or [])} 注"]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _race_no(name: str) -> int | None:
    m = re.match(r"\s*R(\d+)\b", name or "")
    return int(m.group(1)) if m else None


def _runner_no(name: str) -> int | None:
    m = re.match(r"\s*(\d+)\.", name or "")
    return int(m.group(1)) if m else None


def day_catalogue(day: str, rpc) -> list[dict]:
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=SYDNEY)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    flt = {"eventTypeIds": ["7"], "marketCountries": ["AU"], "marketTypeCodes": ["WIN", "PLACE"],
           "marketStartTime": {"from": start.astimezone(timezone.utc).strftime(fmt),
                               "to": (start + timedelta(days=1)).astimezone(timezone.utc).strftime(fmt)}}
    return rpc("listMarketCatalogue", {"filter": flt, "maxResults": 200,
                                       "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION",
                                                            "MARKET_DESCRIPTION"]}) or []


def index_markets(markets: list[dict]) -> dict:
    """→ {(venue_norm, race_no, "WIN"/"PLACE"): market}，harness 剔走（PLACE 跟同場 WIN 判斷）。"""
    kind = lambda m: (m.get("description") or {}).get("marketType")  # noqa: E731
    key = lambda m: ((m.get("event") or {}).get("id"), m.get("marketStartTime"))  # noqa: E731
    wins = {key(m): m for m in markets if kind(m) == "WIN" and not HARNESS.search(m.get("marketName") or "")}
    out = {}
    for m in markets:
        win = wins.get(key(m))
        if win is None:
            continue
        rno = _race_no(win.get("marketName"))
        venue = _norm((m.get("event") or {}).get("venue"))
        if rno and venue:
            out[(venue, rno, kind(m))] = m
    return out


def au_betting_place(day: str, config: dict, rpc=None, **_kw):
    """將現有紙上位注策略（`au_daily_auto/au_betting.py`，2026-08-12 規則）轉做 Betfair 候選注。

    ⚠️ 呢個策略紙上 ROI 係負（見 au_betting.bet_list 嘅警告）—— 呢度只係示範接駁，唔係建議。
    Sportsbet 位賠門檻 ≠ Betfair 位 BSP，所以 min_price 用設定（strategies.au_betting_place.min_price）。
    """
    if rpc is None:
        return [], ["au_betting_place 要連 Betfair 讀目錄（唔可以 offline）"]
    sys.path.insert(0, str(HERE.parents[3]))
    sys.path.insert(0, str(HERE.parent / "au_daily_auto"))
    import au_betting  # noqa: PLC0415

    st = (config.get("strategies") or {}).get("au_betting_place") or {}
    stake = float(st.get("stake") or (config.get("limits") or {}).get("min_stake") or 0)
    min_price = float(st.get("min_price") or (config.get("limits") or {}).get("min_bsp") or 0)
    which = st.get("which") or "last"
    mtype = "WIN" if au_betting.MODE == "win" else "PLACE"
    idx = index_markets(day_catalogue(day, rpc))
    bets, notes = [], []
    for folder in au_betting._folders(day):
        venue = au_betting._venue(folder.name)
        rows, _whens, tags = au_betting.meeting_bets(folder, which)
        if which == "last" and not any(t in au_betting.MORNING_TAGS for t in tags):
            notes.append(f"{venue}：早更未跑（快照 {tags}）—— 跳過，唔用前一晚嘅價")
            continue
        for r in rows:
            for num, name, odds in r["bets"]:
                m = idx.get((_norm(venue), r["race"], mtype))
                if m is None:
                    notes.append(f"{venue} R{r['race']}：Betfair 搵唔到 {mtype} 市場")
                    continue
                sel = next((x.get("selectionId") for x in m.get("runners") or []
                            if _runner_no(x.get("runnerName")) == num), None)
                if sel is None:
                    notes.append(f"{venue} R{r['race']} #{num}：Betfair 搵唔到呢匹馬")
                    continue
                bets.append({"market_id": m["marketId"], "selection_id": int(sel), "side": "BACK",
                             "stake": stake, "order_type": "LIMIT_ON_CLOSE", "min_price": min_price,
                             "strategy": "au_betting_place",
                             "reason": f"au_betting 頭兩選、SB 位賠 {odds:g}",
                             "label": f"{venue} R{r['race']} #{num} {name} ({mtype})"})
    return bets, notes


STRATEGIES = {"none": none, "json": json_file, "au_betting_place": au_betting_place}


def plan(name: str, *, day: str, config: dict, rpc=None, bets_in: str | None = None):
    fn = STRATEGIES.get(name)
    if fn is None:
        return [], [f"冇呢個策略：{name}（有：{sorted(STRATEGIES)}）"]
    return fn(day, config, rpc=rpc, bets_in=bets_in)
