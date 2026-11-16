"""賽績 pattern（EXP-20261115-15；Kelvin 2026-11-15「forward shadow 同顯示標籤兩樣都做」）—— 純顯示＋forward shadow，唔入分。

全部由 Logic 欄位計（live 同 shadow 一樣）：
  老馬贏後：在港出賽 ≥ 35 仗（_data.total_starts 生涯總數；hk_starts 只計近幾季，唔用）、上仗第 1（last_6_finishes 第一個）、
            唔係高班（今仗評分 < 95 而且唔係一／二班）。回放殘差 dev −11.2pp、holdout −9.7pp（CI 唔跨零）。
  降班＋評分跌返贏馬分：今仗班次低過上仗（recent_6_detail 第 1 仗）、今仗評分 ≤ 近 6 仗最近一次贏馬時評分（rating_trend）。
            回放殘差 dev +5.2pp、holdout +5.2pp（CI 唔跨零）。
兩樣都罕見（每季 ~100 匹），排名層 A/B 冇功效 → forward 判。
回放定義用 HKJC 馬匹頁（老馬另有「在港 ≥ 4 年」、贏馬分睇全部往績）；live 只有近 6 仗，所以呢度係近似。
"""
from __future__ import annotations

import re

CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
OLD_STARTS = 35
ELITE_RATING = 95
RATING_NEAR_WIN = 2


def class_no(text) -> int | None:
    m = re.search(r"第([一二三四五])班", str(text or ""))
    return CN[m.group(1)] if m else None


def _finishes(horse: dict) -> list[int | None]:
    out = []
    for p in str(horse.get("last_6_finishes") or "").split("-"):
        p = p.strip()
        out.append(int(p) if p.isdigit() else None)
    return out


def _ratings(data: dict) -> list[float]:
    head = str(data.get("rating_trend") or "").split(" → ")[0]
    out = []
    for x in head.split("→"):
        try:
            out.append(float(x.strip()))
        except ValueError:
            return []
    return out


_WIN_TABLE: dict | None = None


def load_win_table(path=None) -> dict:
    """本機 HKJC_Sections/win_ratings.json（hkjc_pit_sections_build 每次賽後重建）；冇就空。"""
    global _WIN_TABLE
    if path is None and _WIN_TABLE is not None:
        return _WIN_TABLE
    import json
    from pathlib import Path
    if path is None:
        import wongchoi_paths
        path = Path(wongchoi_paths.HK_RACING) / "HKJC_Sections" / "win_ratings.json"
    p = Path(path)
    _WIN_TABLE = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _WIN_TABLE


def flags(horse: dict, race_class, race_date: str | None = None, win_table: dict | None = None) -> dict:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    try:
        starts = int(data.get("total_starts") or data.get("hk_starts") or horse.get("career_race_starts") or 0)   # hk_starts 只計近幾季
    except (TypeError, ValueError):
        starts = 0
    fin = _finishes(horse)
    rating = data.get("current_rating")
    try:
        rating = float(rating) if rating not in (None, "") else None
    except (TypeError, ValueError):
        rating = None
    today_cls = class_no(race_class)
    elite = (rating is not None and rating >= ELITE_RATING) or (today_cls is not None and today_cls <= 2)
    out = {"old_won_last": bool(starts >= OLD_STARTS and fin and fin[0] == 1 and not elite), "starts": starts}
    m = re.match(r"第1仗\([^)]*?(第[一二三四五]班)", str(data.get("recent_6_detail") or ""))
    last_cls = class_no(m.group(1)) if m else None
    ratings = _ratings(data)
    win_rating = next((r for f, r in zip(fin, ratings) if f == 1), None)
    if win_rating is None and race_date:
        # 近 6 仗冇贏：用 HKJC 馬匹頁贏馬評分表（日期早過今仗嘅最近一次）
        from .market_history import horse_code
        table = win_table if win_table is not None else load_win_table()
        wins = [w for w in ((table.get("horses") or {}).get(horse_code(horse)) or []) if w[0] < str(race_date)[:10]]
        if wins:
            win_rating = float(wins[-1][1])
    out["classdrop_rating_back"] = bool(today_cls and last_cls and today_cls > last_cls and rating is not None
                                        and win_rating is not None and rating <= win_rating)
    # Kelvin 2026-11-17：唔降班都要標「評分跌返／接近贏馬分」。回放（EXP-20261115-15）單獨殘差 dev +1.4、holdout +0.1
    # → 冇穩定訊號，只係留意；降班＋跌返先有訊號（+5.2／+5.2，上面 classdrop_rating_back）。接近 = 高過贏馬分 ≤ 2 分。
    out["rating_near_win"] = bool(not out["classdrop_rating_back"] and rating is not None and win_rating is not None
                                  and rating <= win_rating + RATING_NEAR_WIN)
    out["rating"], out["win_rating"] = rating, win_rating
    return out
