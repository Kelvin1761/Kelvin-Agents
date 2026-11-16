"""大細盤精選：開波前對返 Sportsbet，原盤收咗就作廢不計（Kelvin 2026-11-17）。

精選係 21:00 凍結嘅紙上盤。如果之後 Sportsbet 將嗰個「球員 - 項目」大細盤成個收走，嗰注其實落唔到，
照計會令紀錄計咗一注冇人落得到嘅注。所以每次開波前嘅 odds refresh 之後，逐場對一次：

- ``open``：原線、原邊仲有價。
- ``line_moved``：個球員嗰個項目仲有大細盤，但唔係原線。只係記低，**照計**（21:00 落咗嘅注唔受影響）。
- ``withdrawn``：嗰個球員嗰個項目嘅大細盤成個冇咗（同場其他球員同一項目仲有盤，證明唔係抽取失敗）。
  一旦見到就**永久**作廢，之後盤口返嚟都唔變（唔可以睇住結果揀返）。
- ``unknown``：成場嗰個項目都冇大細盤（抽取失敗或者未開），唔下判斷。

只係睇開波前嘅檔：已開波場次嘅 odds 檔會被 refresh 原封不動保留，呢度亦唔會再查。作廢嘅決定只靠盤口，
完全唔睇賽果，所以唔會令紀錄偏向有利結果。結果寫入當日資料夾嘅 ``Featured_Availability.json``，
`nba_tracking` 讀返嚟將對應精選標做 ``void``（``void_reason = market_withdrawn``）。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

FILE = "Featured_Availability.json"
CATEGORY = {"pts": "points", "reb": "rebounds", "ast": "assists", "fg3m": "threes_made"}
WITHDRAWN = "withdrawn"


def _key(pick: dict) -> list:
    return [pick.get("player"), pick.get("market"), float(pick.get("ou_line")), pick.get("side")]


def _line(lines: dict, target: float) -> dict | None:
    for raw, sides in (lines or {}).items():
        try:
            if abs(float(raw) - target) < 1e-9:
                return sides if isinstance(sides, dict) else None
        except (TypeError, ValueError):
            continue
    return None


def classify(odds: dict, pick: dict) -> str:
    """One pick against one freshly scraped ``Sportsbet_Odds_<tag>.json``."""
    by_player = (odds.get("player_props_two_way") or {}).get(CATEGORY.get(pick.get("market"), ""))
    if not by_player:
        return "unknown"
    lines = by_player.get(pick.get("player"))
    if not lines:
        return WITHDRAWN
    sides = _line(lines, float(pick["ou_line"]))
    return "open" if sides and sides.get(pick.get("side")) else "line_moved"


def read(folder: Path) -> dict[str, dict]:
    try:
        data = json.loads((Path(folder) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def withdrawn(folders: Iterable[Path]) -> dict[str, dict]:
    """game_tag → entry, for every pick ever seen withdrawn in any of ``folders``."""
    out: dict[str, dict] = {}
    for folder in folders:
        for tag, entry in read(folder).items():
            if isinstance(entry, dict) and entry.get("withdrawn_at"):
                out.setdefault(tag, entry)
    return out


def matches(entry: dict | None, pick: dict) -> bool:
    try:
        return bool(entry) and entry.get("pick") == _key(pick)
    except (TypeError, ValueError):
        return False


def check(folder: Path, picks: Iterable[dict], tags: set[str], *, now: datetime) -> list[dict]:
    """Classify each pending pick of a game in ``tags``; persist; return the newly withdrawn."""
    folder = Path(folder)
    state = read(folder)
    newly = []
    for pick in picks:
        tag = pick.get("game_tag")
        if tag not in tags:
            continue
        try:
            odds = json.loads((folder / f"Sportsbet_Odds_{tag}.json").read_text(encoding="utf-8"))
            key = _key(pick)
        except (OSError, ValueError, TypeError, KeyError):
            continue
        status = classify(odds, pick)
        entry = state.get(tag) if isinstance(state.get(tag), dict) else None
        if entry is None or entry.get("pick") != key:
            entry = {"pick": key, "checks": []}
        entry["checks"] = (entry.get("checks") or [])[-20:] + [{"at": now.isoformat(), "status": status}]
        entry["last_status"] = status
        if status == WITHDRAWN and not entry.get("withdrawn_at"):
            entry["withdrawn_at"] = now.isoformat()
            newly.append({**pick, "withdrawn_at": entry["withdrawn_at"]})
        state[tag] = entry
    if state:
        temp = folder / (FILE + ".tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(folder / FILE)
    return newly


def message(target_date: str, picks: list[dict]) -> str:
    from nba_engine.featured import describe
    lines = [f"➖ NBA {target_date} 大細盤精選：Sportsbet 已收盤，作廢不計"]
    lines += [f"{str(p.get('game_tag', '')).replace('_', '@')}｜{describe({**p, 'stat': p.get('stat') or ''})}"
              for p in picks]
    lines.append("原盤搵唔到就唔好落，唔好換線或者用 N+ 代替。紀錄同 ROI 唔計呢幾注。")
    return "\n".join(lines)
