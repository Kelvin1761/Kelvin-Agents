"""上仗賠率組件（EXP-20261115-07；Kelvin 2026-11-15 批准測試市場歷史 —— 上線要 Kelvin 決定）。

**methodology**：只用之前賽事（日期嚴格早過今仗）嘅 HKJC 最終獨贏賠率；今仗賠率永遠唔用。
  raw' = raw + β₁·(上仗 log 賠率 − 場均) + β₂·(冇上仗紀錄 − 場均)
  β 凍結 = 回放 v2 全 dev（2019/20–2023/24，4,151 場）fit；冇上仗嘅馬用場均填、指示 = 1。
  外隊馬（tags.is_foreign）當中性：用場均、指示 = 0（Kelvin 2026-11-14：外隊馬冇本地資料唔扣分）。
回放：dev Δlog-loss −0.00195、holdout −0.00315（Holm 3 PASS）、AUC +0.0055。
表（`market_history.json`，由 `hkjc_pit_sections_build.py` 每個賽日後重建，放本機資料根）：
  {"version": 1, "last_date": ..., "horses": {馬號(L245): [[日期, 賠率], ...舊到新]}}
同一個 function 畀 live 同回放 arm 用。`ENABLED = False` = 退回（forward 退回 arm 用）。
"""
from __future__ import annotations

import json
import math
from bisect import bisect_left
from pathlib import Path

ENABLED = True
BETA_LOG_ODDS = -1.3646582688306614
BETA_MISSING = -3.052701912015252
_TABLE: dict | None = None


def load_table(path: str | Path | None = None) -> dict | None:
    global _TABLE
    if path is None and _TABLE is not None:
        return _TABLE
    if path is None:
        import wongchoi_paths
        path = Path(wongchoi_paths.HK_RACING) / "HKJC_Sections" / "market_history.json"
    p = Path(path)
    if not p.exists():
        return None
    _TABLE = json.loads(p.read_text(encoding="utf-8"))
    return _TABLE


def horse_code(horse: dict) -> str:
    code = str(horse.get("horse_code") or horse.get("hkjc_horse_id") or "")
    return code.rsplit("_", 1)[-1] if code else ""


def prev_log_odds(code: str, race_date: str, table: dict) -> float | None:
    runs = (table.get("horses") or {}).get(code) or []
    i = bisect_left([r[0] for r in runs], race_date)      # 嚴格早過今仗
    if i == 0:
        return None
    return math.log(float(runs[i - 1][1]))


def adjustments(horses: dict, race_date: str, table: dict) -> dict:
    """horses：{馬號: horse dict}（已評分嘅）→ {馬號: raw 加減}。"""
    from .tags import is_foreign
    vals, miss = {}, {}
    for k, h in horses.items():
        v = None if is_foreign(h) else prev_log_odds(horse_code(h), race_date, table)
        vals[k] = v
        miss[k] = 1.0 if (v is None and not is_foreign(h)) else 0.0
    obs = [v for v in vals.values() if v is not None]
    if not vals:
        return {}
    fill = sum(obs) / len(obs) if obs else 0.0
    x = {k: (fill if v is None else v) for k, v in vals.items()}
    mx = sum(x.values()) / len(x)
    mm = sum(miss.values()) / len(miss)
    return {k: BETA_LOG_ODDS * (x[k] - mx) + BETA_MISSING * (miss[k] - mm) for k in horses}


def apply(horses: dict, race_date: str | None, table: dict | None = None) -> int:
    """加落 ability_score_raw（喺 overlays 之後、grade／排名之前）。返回郁咗幾多匹；冇表／冇日期 → 唔郁。"""
    if not ENABLED or not race_date:
        return 0
    table = table if table is not None else load_table()
    if not table:
        return 0
    from .scoring import compute_grade, to_display_scale
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    n = 0
    for k, add in adjustments(scored, str(race_date)[:10], table).items():
        auto = scored[k]["python_auto"]
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["market_history_delta"] = round(add, 4)
        n += abs(add) > 1e-9
    return n
