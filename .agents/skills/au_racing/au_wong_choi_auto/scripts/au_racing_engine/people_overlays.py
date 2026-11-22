"""老馬調整＋練馬師剩餘表現 —— 實驗性上線（Kelvin 2026-11-22：「上左先，跟住 forward 再測試要唔要拎走」）。

兩個都喺新 log-loss 尺下 PASS（Holm），直接加落綜合分（overlay），各有回退開關：

* **老馬**（EXP-20261121-37）：8 歲或以上 −3.46 分（walk-forward β 中位，凍結）。`WC_AU_OLD_HORSE_LIVE=0` 回退。
  馬齡由 Racecard `Age:` 讀（`data_prep`，EXP-20261121-34），同 dashboard「N 歲老馬」標籤同一個定義。
* **練馬師剩餘表現**（EXP-20261122-02）：練馬師之前每匹出賽「入三甲 − 模型預計機率」累積，
  R = Σ ÷ (出賽 + 50)；overlay = 40 ×（R − 全場平均 R）。β 40 = 測試嘅凍結值（walk-forward 上限，無上限中位約 46）。
  `WC_AU_TRAINER_RESIDUAL_LIVE=0` 回退。
* **騎練總獎金**（EXP-20261122-03 T3，Kelvin 2026-11-22「好似老馬咁直接上線，再用 forward 監察」）：
  騎師、練馬師過去 12 個月總獎金（Sportsbet「Prize Money / Last 12 Months」組出賽數 × 組中位），log10(總額 + 1)；
  overlay = 5.51 ×（騎師 − 全場平均）＋ 4.43 ×（練馬師 − 全場平均）（walk-forward β 中位，凍結）；冇資料 = 唔計入平均、自己 0。
  ⚠️ 研究判 REJECT（Good 護欄：−0.23pp，下界 −1.29）但 log-loss 明顯好（−0.0028）—— Kelvin 選擇上線監察。
  表由 `au_people_prize_table.py` 每晚建（`<資料根>/AU_People_Prize.json`），只用賽日之前嘅快照。`WC_AU_PEOPLE_PRIZE_LIVE=0` 回退。
  表由 `au_trainer_residual_table.py` 每晚重建（`<資料根>/AU_Trainer_Residual.json`），每個練馬師存**逐日累積**，
  引擎只攞**賽日之前**最近一筆 —— 重評分舊場次都唔會前視。冇表／冇紀錄 = 0。
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

OLD_AGE = 8
OLD_HORSE_PENALTY = -3.46
TRAINER_BETA = 40.0
TRAINER_K = 50.0
TABLE_NAME = "AU_Trainer_Residual.json"
PRIZE_TABLE_NAME = "AU_People_Prize.json"
PRIZE_BETA_JOCKEY = 5.51
PRIZE_BETA_TRAINER = 4.43
PRIZE_MIDPOINTS = {"$0 - $5,000": 2500, "$5,001 - $10,000": 7500, "$10,001 - $20,000": 15000, "$20,001 - $50,000": 35000,
                   "$50,001 - $100,000": 75000, "$100,001 - $200,000": 150000, "$200,001 - $500,000": 350000,
                   "$500,000+": 750000}


def old_horse_live() -> bool:
    return os.environ.get("WC_AU_OLD_HORSE_LIVE", "1") != "0"


def trainer_residual_live() -> bool:
    return os.environ.get("WC_AU_TRAINER_RESIDUAL_LIVE", "1") != "0"


def norm(name) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\([^)]*\)", "", str(name or "")).lower())


def people_prize_live() -> bool:
    return os.environ.get("WC_AU_PEOPLE_PRIZE_LIVE", "1") != "0"


def log_total_prize(prize_money_table) -> float | None:
    """Sportsbet「Prize Money」表 → log10(過去 12 個月總獎金 + 1)；冇出賽 → None。"""
    import math
    t = (prize_money_table or {}).get("Last 12 Months") or {}
    if not sum((v or {}).get("starts") or 0 for v in t.values()):
        return None
    return math.log10(sum(((t.get(b) or {}).get("starts") or 0) * m for b, m in PRIZE_MIDPOINTS.items()) + 1)


def old_horse_feature(age) -> float:
    return OLD_HORSE_PENALTY if old_horse_live() and isinstance(age, int) and age >= OLD_AGE else 0.0


def _data_root() -> Path:
    repo = Path(__file__).resolve().parents[6]
    marker = repo / ".wongchoi_au_data_root"
    return Path(marker.read_text().strip()) if marker.exists() else repo / "data"


def default_table_path() -> Path:
    override = os.environ.get("WC_AU_TRAINER_RESIDUAL_TABLE")
    return Path(override) if override else _data_root() / TABLE_NAME


def default_prize_table_path() -> Path:
    override = os.environ.get("WC_AU_PEOPLE_PRIZE_TABLE")
    return Path(override) if override else _data_root() / PRIZE_TABLE_NAME


@lru_cache(maxsize=8)
def _read(path: str, mtime: float, field: str = "trainers") -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get(field) or {}
    except (OSError, ValueError):
        return {}


def load_table(path: Path | None = None) -> dict:
    p = Path(path) if path else default_table_path()
    try:
        return _read(str(p), p.stat().st_mtime)
    except OSError:
        return {}


def load_prize_table(path: Path | None = None) -> dict:
    p = Path(path) if path else default_prize_table_path()
    try:
        return _read(str(p), p.stat().st_mtime, "people")
    except OSError:
        return {}


def prize_raw(kind: str, name, meeting_date: str, table: dict) -> float | None:
    """賽日之前最近一份快照嘅 log10 總獎金；冇 → None。表：{"jockey|名": [[日期, 值], ...]}（日期升序）。"""
    if not name or not meeting_date:
        return None
    last = None
    for date, value in table.get(f"{kind}|{norm(name)}") or []:
        if str(date) >= str(meeting_date):
            break
        last = float(value)
    return last


def prize_feature(jockey, trainer, field_jockeys, field_trainers, meeting_date: str, table: dict | None = None) -> float:
    if not people_prize_live():
        return 0.0
    tab = table if table is not None else load_prize_table()
    if not tab:
        return 0.0
    total = 0.0
    for kind, me, field, beta in (("jockey", jockey, field_jockeys, PRIZE_BETA_JOCKEY),
                                  ("trainer", trainer, field_trainers, PRIZE_BETA_TRAINER)):
        mine = prize_raw(kind, me, meeting_date, tab)
        vals = [v for v in (prize_raw(kind, x, meeting_date, tab) for x in (field or [])) if v is not None]
        if mine is None or not vals:
            continue
        total += beta * (mine - sum(vals) / len(vals))
    return round(total, 4)


def trainer_raw(trainer, meeting_date: str, table: dict | None = None) -> float:
    """賽日之前最近一筆累積 → R；冇 → 0。表：{norm 名: [[日期, 累積剩餘, 出賽數], ...]}（日期升序）。"""
    if not trainer or not meeting_date:
        return 0.0
    rows = (table if table is not None else load_table()).get(norm(trainer)) or []
    last = None
    for date, resid, n in rows:
        if str(date) >= str(meeting_date):
            break
        last = (float(resid), float(n))
    return last[0] / (last[1] + TRAINER_K) if last else 0.0


def trainer_feature(trainer, field_trainers, meeting_date: str, table: dict | None = None) -> float:
    if not trainer_residual_live():
        return 0.0
    tab = table if table is not None else load_table()
    if not tab:
        return 0.0
    field = [t for t in (field_trainers or []) if t] or [trainer]
    mean = sum(trainer_raw(t, meeting_date, tab) for t in field) / len(field)
    return round(TRAINER_BETA * (trainer_raw(trainer, meeting_date, tab) - mean), 4)
