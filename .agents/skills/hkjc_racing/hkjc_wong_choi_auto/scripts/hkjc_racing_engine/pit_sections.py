"""段速 FT 組件（EXP-20261114-04 FT_b50；Kelvin 2026-11-14 決定上線）：前段＋全程對 as-of 標準、扣當日快慢。

同一個 function 畀 live 引擎同離線回放 arm 用 —— live 實作同測試版本結構上一樣。
表（`pit_sections.json`，由 `hkjc_pit_sections_build.py` 每個賽日後重建，放本機資料根，唔放外置碟）：
  standards[season]["track|dist|cls|i"] = 之前季入頭三分段中位數（n ≥ 20；另有 cls = "ALL" 後備）
  variant["date|track"] = {"first": 秒／400 米, "l400": 秒}（當日全場對自己班次標準嘅偏差中位數）
  z = {"first_v": [mean, sd], "total_v": [mean, sd]}（2024-08 前，固定）
定義同 `docs/experiments/patches/hkjc_hist_sectional_features_v2.py`（EXP-20261114-04 用）一樣：
  每仗：dv = 分段 − 標準（今仗班次標準；冇就嗰仗班次）
        first = dv[0] /（第一段長 / 400）− variant.first
        total = Σdv /（路程 / 400）− mean(variant.first, variant.l400)
  近 6 仗（賽日之前、有標準嘅仗）1/k 加權，最少 2 仗；取負（越大越好）
組件：speed' = clip(speed + b × 9.45 × mean(clip(z_first), clip(z_total)))，b = 0.5，clip ±2.5；任何一個冇值 → 唔郁
"""
from __future__ import annotations

import json
from pathlib import Path

B = 0.5
SPEED_SD = 9.45
CLASS_CODE = {"第一班": "C1", "第二班": "C2", "第三班": "C3", "第四班": "C4", "第五班": "C5",
              "1": "C1", "2": "C2", "3": "C3", "4": "C4", "5": "C5", "C1": "C1", "C2": "C2", "C3": "C3", "C4": "C4", "C5": "C5"}
_TABLE: dict | None = None


def season_of(iso: str) -> int:
    return int(iso[:4]) if int(iso[5:7]) >= 9 else int(iso[:4]) - 1


def load_table(path: str | Path | None = None) -> dict | None:
    global _TABLE
    if path is None and _TABLE is not None:
        return _TABLE
    if path is None:
        import wongchoi_paths
        path = Path(wongchoi_paths.HK_RACING) / "HKJC_Sections" / "pit_sections.json"
    p = Path(path)
    if not p.exists():
        return None
    _TABLE = json.loads(p.read_text(encoding="utf-8"))
    return _TABLE


def _std(table, season, track, dist, cls, n):
    st = (table.get("standards") or {}).get(str(season)) or {}
    out = []
    for i in range(n):
        v = st.get(f"{track}|{dist}|{cls}|{i}")
        if v is None:
            v = st.get(f"{track}|{dist}|ALL|{i}")
        if v is None:
            return None
        out.append(v)
    return out


def ft_values(runs: list[dict], race_date: str, today_cls: str | None, table: dict) -> tuple[float | None, float | None]:
    """runs：由新到舊；每個 {date, track(ST/HV/AWT), dist, cls(C1..C5/OT), secs[...]}。返回 (first_v, total_v)。"""
    season = season_of(race_date)
    tcls = CLASS_CODE.get(str(today_cls or ""), "OT")
    acc = {"first_v": [], "total_v": []}
    # 同 v2 一樣：先揀賽日前最近 6 仗（有完整分段、≥3 段），再剔冇標準嘅
    nsec = table.get("nsec") or {}
    eligible = [r for r in runs if r["date"] < race_date and r.get("dist") and len(r.get("secs") or []) >= 3
                and len(r["secs"]) == nsec.get(f"{r['track']}|{r['dist']}", len(r["secs"]))][:6]   # 冇跑完（段數唔齊）唔計
    for r in eligible:
        secs = r["secs"]
        n = len(secs)
        st = _std(table, season, r["track"], r["dist"], tcls, n) or _std(table, season, r["track"], r["dist"], r.get("cls") or "OT", n)
        if st is None:
            continue
        dv = [a - b for a, b in zip(secs, st)]
        first_len = r["dist"] - 400 * (n - 1)
        v = (table.get("variant") or {}).get(f"{r['date']}|{r['track']}") or {}
        acc["first_v"].append(dv[0] / (first_len / 400) - v.get("first", 0.0))
        total_adj = (v.get("first", 0.0) + v.get("l400", 0.0)) / 2 if v else 0.0
        acc["total_v"].append(sum(dv) / (r["dist"] / 400) - total_adj)
    out = []
    for k in ("first_v", "total_v"):
        xs = acc[k]
        if len(xs) < 2:
            out.append(None)
            continue
        w = [1.0 / i for i in range(1, len(xs) + 1)]
        out.append(-sum(x * wi for x, wi in zip(xs, w)) / sum(w))
    return out[0], out[1]


def ft_points(first_v: float | None, total_v: float | None, table: dict) -> float:
    """加落 speed_score 嘅分（clip 前）；任何一個冇值 = 0。"""
    if first_v is None or total_v is None:
        return 0.0
    z = table.get("z") or {}
    zs = []
    for k, x in (("first_v", first_v), ("total_v", total_v)):
        m, s = z.get(k, [0.0, 1.0])
        zs.append(max(-2.5, min(2.5, (x - m) / (s or 1.0))))
    return B * SPEED_SD * (zs[0] + zs[1]) / 2
