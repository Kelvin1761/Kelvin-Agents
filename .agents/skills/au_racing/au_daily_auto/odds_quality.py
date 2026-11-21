"""Evidence checks for captured/displayed prices; never used by scoring."""
from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo("Australia/Sydney")


def valid_price(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        price = float(value)
    except (ValueError, TypeError, OverflowError):
        return False
    return math.isfinite(price) and price > 1.0


def has_prices(prices: object) -> bool:
    """A timestamp/empty object does not prove that any prices were captured."""
    return isinstance(prices, dict) and any(
        isinstance(pair, (list, tuple)) and len(pair) == 2
        and valid_price(pair[0]) and valid_price(pair[1])
        for pair in prices.values()
    )


def snapshot_day(key: object) -> str | None:
    raw, separator, tag = str(key).partition("|")
    if not separator or tag not in {"analysis", "morning-refresh", "morning-rebuild"}:
        return None
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    # Historical naive keys were written in Sydney local time.
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(SYDNEY)
    return stamp.date().isoformat()


def has_snapshot(snapshots: object, *, day: str | None = None) -> bool:
    return isinstance(snapshots, dict) and any(
        snapshot_day(key) is not None
        and (day is None or snapshot_day(key) == day)
        and has_prices(prices)
        for key, prices in snapshots.items()
    )


def dashboard_odds_issues(payload: dict, day: str | None = None) -> list[str]:
    """Check the values actually transported to AU horse cards, per race."""
    issues = []
    for meeting in payload.get("meetings") or []:
        if str(meeting.get("region") or "").upper() != "AU":
            continue
        if day and meeting.get("date") != day:
            continue
        key = f"{meeting.get('date')}|{meeting.get('venue')}"
        entry = (payload.get("races") or {}).get(key) or {}
        listing = (entry.get("races_by_analyst") or {}).get("auto")
        if listing is None:
            listing = [race for races in (entry.get("races_by_analyst") or {}).values()
                       if isinstance(races, list) for race in races]
        seen = set()
        for race in listing:
            number = race.get("race_number")
            if number in seen:
                continue
            seen.add(number)
            horses = race.get("horses") or []
            priced = sum(valid_price(h.get("market_win_odds"))
                         and valid_price(h.get("market_place_odds")) for h in horses)
            if not horses or priced < len(horses):
                issues.append(f"{key} R{number}: dashboard win/place odds {priced}/{len(horses)} runners")
    return issues


# ---------------------------------------------------------------- 快照有冇入錯場
# 2026-11-21：raceId 清單亂序令 25 個場次嘅早更賠率入錯場（Cranbourne R1 攞咗 R2 嘅價），
# 落注單印錯價、ROI 用錯價結算。寫快照（`record_odds_from_cache`）、揀價（`au_betting.odds_at`）
# 同健康檢查**一律用呢個判斷**，唔好各自寫一套。
MAX_OUTSIDE_FIELD = 1        # 遲退出馬可能仲有價，容許 1 匹唔喺名單
MATCH_OTHER = 0.15           # 同另一場分析時嘅贏賠中位 |log 比| 細過呢個 = 「明顯似另一場」
FAR_FROM_OWN = 0.40          # 同自己嗰場分析時嘅贏賠中位 |log 比| 大過呢個 = 「唔似自己」


def field_numbers(folder, race) -> set | None:
    """Racecard 嘅出賽馬號；冇 Racecard → None（唔判）。"""
    import re
    from pathlib import Path
    files = sorted(Path(folder).glob(f"* Race {race} Racecard.md"))
    if not files:
        return None
    text = files[0].read_text(encoding="utf-8", errors="replace")
    numbers = {int(n) for n in re.findall(r"^(\d+)\.\s+\S", text, re.M)}
    return numbers or None


def win_prices(prices: object) -> dict:
    out = {}
    for num, pair in (prices or {}).items() if isinstance(prices, dict) else ():
        if isinstance(pair, (list, tuple)) and pair and valid_price(pair[0]):
            try:
                out[int(num)] = float(pair[0])
            except (TypeError, ValueError):
                continue
    return out


def _distance(a: dict, b: dict) -> float | None:
    common = [n for n in a if n in b]
    if len(common) < 5:
        return None
    logs = sorted(abs(math.log(a[n] / b[n])) for n in common)
    mid = len(logs) // 2
    return logs[mid] if len(logs) % 2 else (logs[mid - 1] + logs[mid]) / 2


def outside_field(prices: object, field: set | None) -> str | None:
    """**硬證據**：有 > MAX_OUTSIDE_FIELD 匹馬號唔喺出賽名單 → 原因；否則 None。
    呢個先可以自動跳過快照（寫入時唔寫、揀價時唔揀）。"""
    wins = win_prices(prices)
    if not wins or not field:
        return None
    outside = sorted(set(wins) - set(field))
    if len(outside) > MAX_OUTSIDE_FIELD:
        return f"馬號唔喺出賽名單：{outside}"
    return None


def snapshot_problem(prices: object, race, *, field: set | None, references: dict) -> str | None:
    """呢個快照係咪屬於 `race`？唔屬於 → 原因；睇唔出 → None。

    `references` = {場號: 嗰場分析時（最早）快照嘅價}。兩個條件：
      1. 硬證據 `outside_field`；
      2. **軟證據**：價錢明顯似同場另一場（< MATCH_OTHER，≥ 5 匹共同）而唔似自己（> FAR_FROM_OWN）。
         真嘅大市場變動都會觸發（實測 2026-10-04 Ballina R7），所以軟證據**只報警，唔自動跳過**。
    """
    hard = outside_field(prices, field)
    if hard:
        return hard
    wins = win_prices(prices)
    if not wins:
        return None
    own_key = str(race)
    own_ref = win_prices(references.get(own_key))
    own = _distance(wins, own_ref) if own_ref else None
    if own is None or own <= FAR_FROM_OWN:
        return None
    best, best_d = None, None
    for key, ref in references.items():
        if str(key) == own_key:
            continue
        d = _distance(wins, win_prices(ref))
        if d is not None and (best_d is None or d < best_d):
            best, best_d = key, d
    if best_d is not None and best_d < MATCH_OTHER:
        return f"價錢似 R{best}（{best_d:.2f}）唔似自己（{own:.2f}）"
    return None


def reference_snapshots(history: dict) -> dict:
    """{場號: 最早快照嘅價}（通常係晚更分析時，當時直接由該場 Formguide 寫入）。"""
    out = {}
    for race, snaps in (history or {}).items():
        if isinstance(snaps, dict) and snaps:
            out[str(race)] = snaps[sorted(snaps)[0]]
    return out


def misfiled_snapshots(folder, history: dict) -> list[tuple[str, str, str]]:
    """全場次掃描 → [(場號, 快照 key, 原因)]，唔計每場最早嗰個（佢就係參考）。"""
    refs = reference_snapshots(history)
    found = []
    for race, snaps in (history or {}).items():
        if not isinstance(snaps, dict):
            continue
        field = field_numbers(folder, race)
        for key in sorted(snaps)[1:]:
            reason = snapshot_problem(snaps[key], race, field=field, references=refs)
            if reason:
                found.append((str(race), key, reason))
    return found
