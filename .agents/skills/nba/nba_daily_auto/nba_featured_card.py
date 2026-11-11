"""大細盤精選（EXP-20261110-01）嘅 Telegram 文字：21:00 紙上盤 card 同覆盤結果。

精選本身喺 `nba_engine.featured` 計、寫入每場 sidecar（同報告 SHA 綁定）；dashboard 嘅
`featured_records` 用同一個 `daily_top`。呢度淨係將兩樣嘢變成文字。覆盤只報中／唔中，
唔報 ROI —— AGENTS.md：ROI 一律經統一板（`wongchoi_roi`），唔准喺各旺財訊息另加 ROI 段。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from nba_engine.featured import daily_top, describe

HEADER_NOTE = "前向測試 EXP-20261110-01：未證實賺錢，唔好落真錢。每場一注、每日最多 10 注。"
HOW_TO_FIND = ("Sportsbet 搵法：Basketball → NBA → 揀返場波 → 搵 market「球員名 - Points／Rebounds／Assists／"
               "Made Threes」→ 揀 Over／Under。下面用嘅係 Sportsbet 原名。")


def snapshot_picks(snapshot: Path) -> list[dict]:
    """Every game's featured pick in this snapshot, then the same-day cap."""
    picks = []
    for sidecar in sorted(Path(snapshot).glob("Game_*_Full_Analysis.md.market_legs.json")):
        tag = sidecar.name[len("Game_"):-len("_Full_Analysis.md.market_legs.json")]
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for pick in payload.get("featured") or []:
            if isinstance(pick, dict) and isinstance(pick.get("edge"), (int, float)):
                picks.append({**pick, "game_tag": tag})
    return daily_top(picks)


def _line(i: int, pick: dict) -> str:
    return (f"{i}. {pick['game_tag'].replace('_', '@')}｜{describe(pick)} @{pick['price']:g}\n"
            f"   模型 {pick['p_model'] * 100:.0f}% 對 市場 {pick['p_fair'] * 100:.0f}%（{pick['edge'] * 100:+.1f}pp）")


def card(target_date: str, picks: list[dict]) -> str:
    lines = [f"⭐ NBA 大細盤精選（紙上盤）｜{target_date}", HEADER_NOTE, ""]
    if not picks:
        lines.append("今晚冇大細盤 edge ≥ 5pp（或者 Sportsbet 未開大細盤）。")
    else:
        lines += [_line(i, p) for i, p in enumerate(picks, 1)]
        lines += ["", HOW_TO_FIND, "Dashboard：NBA →「⭐ 大細盤精選」分頁（有直達 Sportsbet 連結、紀錄同累計表現）。"]
    return "\n".join(lines)


def postgame_lines(target_date: str, records: Iterable[dict[str, Any]]) -> str | None:
    rows = [r for r in records if r.get("day") == target_date and r.get("tracking_kind") == "featured"]
    if not rows:
        return None
    mark = {"won": "✅", "lost": "❌", "void": "➖", "pending": "⏳"}
    out = []
    for r in rows:
        leg = (r.get("legs") or [{}])[0]
        actual = leg.get("actual")
        shown = "作廢" if actual == "void" else ("待結算" if actual is None else f"實際 {actual:g}")
        out.append(f"{mark.get(r.get('state'), '⏳')} {describe({**leg, 'stat': leg.get('stat') or ''})}"
                   f" @{r['odds']:g}（{shown}）")
    won = sum(r.get("state") == "won" for r in rows)
    lost = sum(r.get("state") == "lost" for r in rows)
    return "\n".join([f"⭐ 大細盤精選（紙上盤）：{len(rows)} 注｜中 {won}｜未中 {lost}", *out])
