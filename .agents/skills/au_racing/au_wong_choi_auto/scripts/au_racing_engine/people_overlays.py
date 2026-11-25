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
  **版本化＋自動回退（EXP-20261125-08）**：每晚重建另存一份版本檔，引擎經 `AU_Trainer_Residual.active.json`
  （版本 id＋sha256）讀；冇指針就照舊讀 live 檔。回退 = 指針指返上一版（`au_residual_versions.py`）。
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
    """T3 overlay —— 2026-11-22 Kelvin 揀 R2 取代（EXP-20261122-04 正面對決），預設關。"""
    return os.environ.get("WC_AU_PEOPLE_PRIZE_LIVE", "0") != "0"


# ── R2（EXP-20261122-04，Kelvin 2026-11-22「好用 R2」）：騎師分／練馬師分 = 一半勝率分、一半總獎金分 ──
# 總獎金分 = 語料 leaf 平均 + 語料 leaf SD ×（log 總獎金 − 語料平均）÷ 語料 SD；常數凍結（08-05 起 3,736 場，只用特徵分佈）。
PRIZE_LEAF_MIX = 0.5
PRIZE_LEAF_STATS = {"jockey": (56.3193, 9.7056, 6.308, 0.502), "trainer": (56.1736, 10.4523, 5.9585, 0.7765)}


def prize_leaf_live() -> bool:
    return os.environ.get("WC_AU_PEOPLE_PRIZE_LEAF_LIVE", "1") != "0"


def prize_leaf_blend(kind: str, name, current: float, meeting_date: str, table: dict | None = None):
    """→ (新 leaf 分, 總獎金分 或 None)。冇快照／開關關 → 原分。"""
    if not prize_leaf_live():
        return current, None
    tab = table if table is not None else load_prize_table()
    value = prize_raw(kind, name, meeting_date, tab) if tab else None
    if value is None:
        return current, None
    lm, ls, pm, ps = PRIZE_LEAF_STATS[kind]
    prize_score = max(0.0, min(100.0, lm + ls * (value - pm) / ps))
    return max(0.0, min(100.0, (1 - PRIZE_LEAF_MIX) * current + PRIZE_LEAF_MIX * prize_score)), round(prize_score, 2)


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


def live_table_path() -> Path:
    """每晚重建直接寫嘅「live」檔（EXP-20261125-08 之前引擎只讀呢個）。"""
    override = os.environ.get("WC_AU_TRAINER_RESIDUAL_TABLE")
    return Path(override) if override else _data_root() / TABLE_NAME


def pointer_path(live: Path | None = None) -> Path:
    """版本指針（EXP-20261125-08）：`AU_Trainer_Residual.active.json`，同 live 檔同一個資料夾。"""
    live = Path(live) if live else live_table_path()
    return live.with_name(live.stem + ".active.json")


@lru_cache(maxsize=8)
def _resolve_pointer(pointer: str, mtime_ns: int) -> str | None:
    """指針 → 已驗 sha256 嘅版本檔；任何唔對（壞 JSON、檔唔見、sha 唔啱）→ None（即讀返 live 檔）。
    版本檔寫咗就唔會改，所以按指針 mtime cache 就夠。"""
    import hashlib
    try:
        ptr = json.loads(Path(pointer).read_text(encoding="utf-8"))
        target = Path(pointer).parent / str(ptr["file"])
        if hashlib.sha256(target.read_bytes()).hexdigest() != ptr["sha256"]:
            return None
        return str(target)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def default_table_path() -> Path:
    """引擎讀嘅表：有 `WC_AU_TRAINER_RESIDUAL_TABLE` → 照用（測試／研究）；否則有效版本指針 → 指住嘅版本檔；
    冇指針或者指針壞咗 → live 檔（同 EXP-20261125-08 之前一模一樣）。"""
    if os.environ.get("WC_AU_TRAINER_RESIDUAL_TABLE"):
        return live_table_path()
    live = live_table_path()
    ptr = pointer_path(live)
    try:
        resolved = _resolve_pointer(str(ptr), ptr.stat().st_mtime_ns)
    except OSError:
        return live
    return Path(resolved) if resolved else live


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
