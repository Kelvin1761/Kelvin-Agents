#!/usr/bin/env python3
"""AU 落注嗰刻嘅價（早更 Sportsbet 定額）：配對去 dump（EXP-20261125-05，系統升級第二輪第 1 項）。

點解：市場尺用收市價（SP／BSP）—— 收市價已經消化晒所有資訊。如果模型喺**朝早價**以外有資訊，
之後先慢慢反映落 SP，咁早啲落注就可能有優勢。呢個價就係量呢樣嘢用。

定義（保守，唔使開跑時間）：每個場次資料夾 `Odds.json` 入面，**賽日悉尼時間 10:30 之前**最後一張快照
（即係 10:00 朝早 run 見到嘅價；前一晚 22:00 run 嘅快照都計）。AU 冇賽事喺 10:30 前開跑，所以一定係賽前價。
價只做評估基準：唔入模型、唔揀注。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

SYD = ZoneInfo("Australia/Sydney")
CUTOFF = time(10, 30)


def _au_root() -> Path:
    marker = Path.home() / ".wongchoi_au_data_root"
    return Path(os.environ.get("WONGCHOI_AU_DATA_ROOT") or marker.read_text(encoding="utf-8").strip())


def odds_index(root: Path | None = None) -> dict[str, Path]:
    """→ {場次資料夾名: Odds.json 路徑}（root 同 Archive/ 都搵）。"""
    root = root or _au_root()
    out = {}
    for base in (root, root / "Archive"):
        if not base.is_dir():
            continue
        for d in base.iterdir():
            p = d / "Odds.json"
            if p.is_file():
                out.setdefault(d.name, p)
    return out


def early_prices(path: Path, race_date: str) -> dict[str, dict[str, float]]:
    """→ {場次號: {馬號: 獨贏價}}，用賽日 10:30（悉尼）前最後一張快照。"""
    try:
        snaps = json.loads(path.read_text(encoding="utf-8")).get("snapshots") or []
    except (OSError, ValueError):
        return {}
    cutoff = datetime.combine(datetime.fromisoformat(race_date).date(), CUTOFF, SYD)
    best = None
    for s in snaps:
        try:
            t = datetime.fromisoformat(s["captured_at"])
        except (KeyError, ValueError):
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=SYD)
        if t < cutoff and (best is None or t > best[0]):
            best = (t, s.get("races") or {})
    if best is None:
        return {}
    out = {}
    for race_no, runners in best[1].items():
        prices = {}
        for n, quotes in (runners or {}).items():
            try:
                v = float((quotes or {}).get("Sportsbet-FixedWin"))
            except (TypeError, ValueError):
                continue
            if v > 1:
                prices[str(n)] = v
        out[str(race_no)] = prices
    return out


def attach(races: list[dict], index: dict[str, Path] | None = None) -> dict:
    """將早更價寫入每匹 row["early"]（配唔到 = None）。→ 配對統計。dump row 要有 `n`（馬號）。"""
    index = odds_index() if index is None else index
    cache: dict[str, dict] = {}
    stats = {"races": 0, "races_complete": 0, "rows": 0, "rows_priced": 0, "no_odds_file": 0}
    for r in races:
        stats["races"] += 1
        path = index.get(r.get("meeting", ""))
        if path is None:
            stats["no_odds_file"] += 1
            for x in r["rows"]:
                x["early"] = None
            stats["rows"] += len(r["rows"])
            continue
        if r["meeting"] not in cache:
            cache[r["meeting"]] = early_prices(path, r["date"])
        prices = cache[r["meeting"]].get(str(r["race"])) or {}
        complete = True
        for x in r["rows"]:
            stats["rows"] += 1
            v = prices.get(str(x.get("n")))
            x["early"] = v
            stats["rows_priced"] += v is not None
            complete &= v is not None
        stats["races_complete"] += complete
    return stats
