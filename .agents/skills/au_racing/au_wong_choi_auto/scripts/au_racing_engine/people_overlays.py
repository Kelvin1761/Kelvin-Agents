"""老馬調整＋練馬師剩餘表現 —— 實驗性上線（Kelvin 2026-11-22：「上左先，跟住 forward 再測試要唔要拎走」）。

兩個都喺新 log-loss 尺下 PASS（Holm），直接加落綜合分（overlay），各有回退開關：

* **老馬**（EXP-20261121-37）：8 歲或以上 −3.46 分（walk-forward β 中位，凍結）。`WC_AU_OLD_HORSE_LIVE=0` 回退。
  馬齡由 Racecard `Age:` 讀（`data_prep`，EXP-20261121-34），同 dashboard「N 歲老馬」標籤同一個定義。
* **練馬師剩餘表現**（EXP-20261122-02）：練馬師之前每匹出賽「入三甲 − 模型預計機率」累積，
  R = Σ ÷ (出賽 + 50)；overlay = 40 ×（R − 全場平均 R）。β 40 = 測試嘅凍結值（walk-forward 上限，無上限中位約 46）。
  `WC_AU_TRAINER_RESIDUAL_LIVE=0` 回退。
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


def old_horse_live() -> bool:
    return os.environ.get("WC_AU_OLD_HORSE_LIVE", "1") != "0"


def trainer_residual_live() -> bool:
    return os.environ.get("WC_AU_TRAINER_RESIDUAL_LIVE", "1") != "0"


def norm(name) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def old_horse_feature(age) -> float:
    return OLD_HORSE_PENALTY if old_horse_live() and isinstance(age, int) and age >= OLD_AGE else 0.0


def default_table_path() -> Path:
    override = os.environ.get("WC_AU_TRAINER_RESIDUAL_TABLE")
    if override:
        return Path(override)
    repo = Path(__file__).resolve().parents[6]
    marker = repo / ".wongchoi_au_data_root"
    root = Path(marker.read_text().strip()) if marker.exists() else repo / "data"
    return root / TABLE_NAME


@lru_cache(maxsize=4)
def _read(path: str, mtime: float) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get("trainers") or {}
    except (OSError, ValueError):
        return {}


def load_table(path: Path | None = None) -> dict:
    p = Path(path) if path else default_table_path()
    try:
        return _read(str(p), p.stat().st_mtime)
    except OSError:
        return {}


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
