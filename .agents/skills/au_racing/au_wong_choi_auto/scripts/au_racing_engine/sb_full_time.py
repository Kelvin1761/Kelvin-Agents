"""S2：Sportsbet 全程速度（情境標準）混入 pace_figure leaf —— 唯一 live 計算位置。

EXP-20261016-02 設計 → EXP-20261016-03 forward ship_eligible（1,812 場未睇過 Gold +1.27pp）→ EXP-20261127-02 移植
現行 live：C（S2 leaf + 保留速度分 + pace_perf 權重 × 0.177／0.108）PASS，Kelvin 2026-11-27 批准。

    本駒時間 = Sportsbet 頭馬時間 + 輸距 × 0.17 秒（今仗之前、唔計試閘／非標準賽）
    A_sb     = `full_time_speed.aggregate` 嘅 A 值（情境標準：場地、地況、班次、評分、路程曲線；同日變異）
    pace_figure_score' = 0.5 × pace_figure_score + 0.5 × (60 + 10 × 場內 z(A_sb))（冇 A_sb = z 0）

`WC_AU_S2_LIVE=0` 回退（leaf 混合同權重倍數一齊退）。事件表 `AU_SB_FullTime_Events.json.gz` 每晚建
（`au_sb_full_time_table.py`）；引擎用賽日之前嘅事件。冇表 = 唔混合（整場照舊 pace_figure）。
研究原版 `scratch/au_sb_total_speed_20261016.py` 保留做紀錄（S2 forward 凍結來源），live 唔 import 佢。
"""
from __future__ import annotations

import gzip
import json
import math
import os
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import full_time_speed as fts

SEC_PER_LENGTH = 0.17
TRIAL_RE = re.compile(r"\*\*\(TRIAL\)\*\*|\$0\s|(?:TRIAL|TRL|JUMP.?OUT)", re.I)
HEADER_RE = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\(\d+\)\s*$", re.M)
MARGIN_RE = re.compile(r"margin:\s*(-?[\d.]+)\s*L?\b")
WEIGHT_MULT = 0.177 / 0.108
EVENTS_NAME = "AU_SB_FullTime_Events.json.gz"


def s2_live() -> bool:
    return os.environ.get("WC_AU_S2_LIVE", "1") != "0"


class SparseContextStandard(fts.ContextStandard):
    """`ContextStandard` 嘅稀疏矩陣算法（同一條正規方程、同一組 penalty、同一個 IRLS；EXP-20261016-02 --check-sparse 核對過）。"""

    def __init__(self, events, segment):  # noqa: D401 - mirrors parent exactly
        from scipy import sparse
        self.segment = segment
        self.keys = []
        self.penalties = [1e-6, 1.0, 1.0]
        for kind, penalty in (("track", 20.0), ("going", 40.0), ("track_band", 30.0),
                              ("track_going", 40.0), ("rating", 20.0), ("track_rail", 40.0),
                              ("class", 20.0)):
            for key in sorted({self.category(event, kind) for event in events}):
                self.keys.append((kind, key))
                self.penalties.append(penalty)
        self.index = {key: i + 3 for i, key in enumerate(self.keys)}
        rows, cols, vals = [], [], []
        for r, event in enumerate(events):
            logd = math.log(event["distance"] / 1400)
            for c, v in ((0, 1.0), (1, logd), (2, logd * logd)):
                rows.append(r); cols.append(c); vals.append(v)
            for kind in ("track", "going", "track_band", "track_going", "rating", "track_rail", "class"):
                i = self.index.get((kind, self.category(event, kind)))
                if i is not None:
                    rows.append(r); cols.append(i); vals.append(1.0)
        x = sparse.csr_matrix((vals, (rows, cols)), shape=(len(events), len(self.index) + 3))
        y = np.array([math.log(event[segment] / self.length(event)) for event in events])
        weights = np.ones(len(events))
        pen = np.diag(self.penalties)
        for _ in range(3):
            xtw = x.T.multiply(weights[None, :]).tocsr()
            self.beta = np.linalg.solve((xtw @ x).toarray() + pen, xtw @ y)
            residual = np.abs(y - x @ self.beta)
            weights = np.minimum(1.0, 0.03 / np.maximum(residual, 1e-9))


def _run_context(line: str) -> dict:
    from .engine_core import _formguide_run_context   # noqa: PLC0415 —— 同研究一樣嘅解析
    return _formguide_run_context(line)


def block_runs(body: str, target_date: str, raw=None, first_seen=None):
    """一匹馬嘅 Formguide 段落 → 往績事件 key 列表；`raw` 畀咗就順手累積事件（建表用）。"""
    keys = []
    for line in body.splitlines():
        run = fts.RUN.match(line)
        if not run:
            continue
        if TRIAL_RE.search(line) or "ResultStatus:NON_STANDARD" in line:
            continue
        run_date = run[3]
        if run_date >= target_date:
            continue
        ctx = _run_context(line)
        margin = MARGIN_RE.search(line)
        if "winning_time" not in ctx or margin is None:
            continue
        key = (fts.normalize_venue_name(run[1]), run_date, int(run[2]), int(run[4]))
        if raw is not None:
            ev = raw[key]
            ev["first_seen"] = min(ev["first_seen"], first_seen or target_date)
            ev["wt"].add(ctx["winning_time"])
            cond = run[5]
            ev["going"].add(fts.condition_key(re.sub(r"\d+$", "", cond) or cond))
            rating = re.search(r"(10|[1-9])$", cond)
            ev["rating"].add(rating[1] if rating else "unknown")
            ev["class"].add(fts.class_key(line))
            ev["rows"][block_name(body)] = ctx["winning_time"] + float(margin[1]) * SEC_PER_LENGTH
        keys.append(key)
    return sorted(set(keys), key=lambda k: k[1], reverse=True)


def block_name(body: str) -> str:
    m = HEADER_RE.search(body)
    return fts.norm(m[2]) if m else ""


def formguide_blocks(text: str) -> list[tuple[str, str]]:
    heads = list(HEADER_RE.finditer(text))
    return [(fts.norm(h[2]), text[h.start(): heads[i + 1].start() if i + 1 < len(heads) else len(text)])
            for i, h in enumerate(heads)]


def build_events(sources) -> tuple[list[dict], dict]:
    """sources = [(target_date, folder)] → (事件列表, audit)。同 EXP-20261016-02 `parse_corpus` 一樣嘅規則。"""
    raw = defaultdict(lambda: {"wt": set(), "rows": {}, "going": set(), "rating": set(), "class": set(),
                               "first_seen": "9999-99-99"})
    audit = defaultdict(int)
    for target_date, folder in sources:
        for fg in sorted(Path(folder).glob("*Race * Formguide.md")):
            for _name, body in formguide_blocks(fg.read_text(encoding="utf-8", errors="replace")):
                block_runs(body, target_date, raw=raw, first_seen=target_date)
    events = []
    for key, ev in raw.items():
        if len(ev["wt"]) != 1:
            audit["conflict_events"] += 1
            continue
        total = next(iter(ev["wt"]))
        if not 8 < key[3] / total < 22:
            audit["implausible_speed_events"] += 1
            continue
        events.append({
            "key": list(key), "track": key[0], "date": key[1], "distance": key[3],
            "going": sorted(ev["going"])[0], "rating": sorted(ev["rating"])[0], "rail": "unknown",
            "class": sorted(ev["class"])[0], "total": total, "first_seen": ev["first_seen"],
            "rows": [{"horse": h, "time": t, "distance": key[3], "key": list(key)} for h, t in ev["rows"].items()],
        })
    events.sort(key=lambda e: e["date"])
    audit["events"] = len(events)
    return events, dict(audit)


# ── live：事件表 → 賽日 lookup → 全場 z ───────────────────────────────────────

def _data_root() -> Path:
    repo = Path(__file__).resolve().parents[6]
    marker = repo / ".wongchoi_au_data_root"
    return Path(marker.read_text().strip()) if marker.exists() else repo / "data"


def default_events_path() -> Path:
    override = os.environ.get("WC_AU_SB_FULLTIME_EVENTS")
    return Path(override) if override else _data_root() / EVENTS_NAME


@lru_cache(maxsize=2)
def _read_events(path: str, mtime: float) -> tuple:
    try:
        rows = json.loads(gzip.decompress(Path(path).read_bytes()).decode("utf-8")).get("events") or []
    except (OSError, ValueError):
        return ()
    for e in rows:
        e["key"] = tuple(e["key"])
        for r in e["rows"]:
            r["key"] = tuple(r["key"])
    return tuple(rows)


@lru_cache(maxsize=8)
def _lookup(path: str, mtime: float, date: str):
    events = list(_read_events(path, mtime))
    if not events:
        return None
    original = fts.ContextStandard
    fts.ContextStandard = SparseContextStandard
    try:
        return fts.context_lookup(events, date)[0]
    finally:
        fts.ContextStandard = original


def lookup_for(date: str, path: Path | None = None):
    p = Path(path) if path else default_events_path()
    try:
        return _lookup(str(p), p.stat().st_mtime, date)
    except OSError:
        return None


def prepare_field(logic_data: dict, meeting_dir: Path, race_no: int, date: str, distance, going,
                  events_path: Path | None = None) -> bool:
    """逐匹寫 `horse["sb_full_time"] = {raw, z, status}`；冇表／冇 Formguide → 全場 z 0（照混合），回傳 False。"""
    horses = [h for h in (logic_data.get("horses") or {}).values() if isinstance(h, dict)]
    for h in horses:
        h.pop("sb_full_time", None)          # 唔准用上次評分留低嘅舊 z（Sol 2026-11-27）
    if not s2_live() or not horses:
        return False
    lookup = lookup_for(date, events_path) if date else None
    fg = sorted(Path(meeting_dir).glob(f"* Race {race_no} Formguide.md"))
    if not lookup or not fg:
        # 冇表／冇 Formguide：全場當冇全程速度（z 0）照混 —— 唔可以「唔混合但權重照乘」，
        # 嗰個係消融證實有害嘅淨權重狀態（EXP-20261127-02 E arm）。
        for h in horses:
            h["sb_full_time"] = {"raw": None, "z": 0.0, "status": "no_table" if not lookup else "no_formguide"}
        return False
    blocks = dict(formguide_blocks(fg[0].read_text(encoding="utf-8", errors="replace")))
    dm = re.search(r"\d{3,5}", str(distance or ""))
    dist = int(dm[0]) if dm else 1400
    gkey = fts.condition_key(re.sub(r"\s*\d+$", "", str(going or "")))
    raws = []
    for h in horses:
        name = fts.norm(h.get("horse_name"))
        runs = block_runs(blocks.get(name, ""), date) if name in blocks else []
        values, _n, _rel = fts.aggregate(runs, name, date, dist, gkey, lookup)
        raws.append(values["A"])
    for h, raw, z in zip(horses, raws, fts.zscores(raws)):
        h["sb_full_time"] = {"raw": None if raw is None else round(float(raw), 6),
                             "z": round(float(z), 6) if raw is not None else 0.0,
                             "status": "ok" if raw is not None else "no_history"}
    return True


def blend(pace_figure: float, horse_data: dict) -> tuple[float, dict | None]:
    """→ (新 pace_figure_score, detail)；冇 `sb_full_time`（未 prepare）= 原分。"""
    detail = horse_data.get("sb_full_time")
    if not s2_live() or not isinstance(detail, dict):
        return pace_figure, None
    z = float(detail.get("z") or 0.0)
    return 0.5 * float(pace_figure) + 0.5 * (60.0 + 10.0 * z), {**detail, "original": round(float(pace_figure), 6)}
