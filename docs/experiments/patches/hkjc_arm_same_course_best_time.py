"""EXP-20261025-08: 同程最佳時間（對全場）加入 段速表現 —— 預先登記固定分段。

輸入：賽果庫（`build_comprehensive_stats.load_all_completed_rows`）每匹馬賽日**之前**、
同場地＋同跑道＋同路程嘅完成時間，扣走嗰日場地 variant：

    variant(日, 場地, 跑道) = 當日各場頭馬時間 − (路程, 班次) 標準 嘅中位數
    標準 = 嗰場賽日**之前**同 (場地, 跑道, 路程, 班次) 頭馬時間中位數（≥8 場；唔夠退返同路程）
    adj  = 完成時間 − variant

b = 每匹馬 adj 最細值（同程最佳時間）。gap = b − 全場 b 最細值（秒）。
全場有 b 嘅馬 < 3 匹 → 成場唔加減；冇同程紀錄嘅馬 → 0。

分段（加落 `speed_score`，clip 0–100）：
    gap < 0.3       → +K
    0.3 ≤ gap < 0.6 → +K/2
    0.6 ≤ gap < 1.0 → 0
    1.0 ≤ gap < 1.5 → −K/2
    gap ≥ 1.5       → −K
K 由 `WC_SAME_COURSE_K` 傳入，只准 3 / 6 / 9。

接線同 EXP-20261016-52 一樣：包住 orchestrator 嘅 `_load_formline_opponent_summaries`
注入 `same_course_best_gap`，再 patch `engine_core.SpeedScorer.compute`（所有返回路徑之後加，唔計 signals）。
"""
import importlib.util
import os
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

K = float(os.environ["WC_SAME_COURSE_K"])
assert K in (3.0, 6.0, 9.0), K
ARM_NAME = f"same_course_best_k{int(K)}"
REPO = Path(__file__).resolve().parents[3]
MIN_HISTORY = 8
MIN_FIELD = 3


def _load_bcs():
    spec = importlib.util.spec_from_file_location("bcs_same_course", REPO / ".agents/scripts/build_comprehensive_stats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_history(rows):
    """HorseID → [(date, cell, adj)]；每個 adj 只用嗰日之前嘅標準同嗰日自己嘅 variant。"""
    df = rows[rows["Rank"].notna() & rows["Distance"].notna() & rows["RaceNo"].notna()].copy()
    df["HorseID"] = df["HorseID"].fillna(df["Horse"].astype(str).str.extract(r"\(([A-Z]\d{3})\)\s*$")[0])
    df = df[df["HorseID"].notna()]
    df["Date"] = df["Date"].astype(str)
    df["race"] = df["Date"] + "_" + df["Venue"].astype(str) + "_" + df["RaceNo"].astype(int).astype(str)
    df["cell"] = list(zip(df["Venue"], df["Track"], df["Distance"].astype(int)))
    df["cls"] = df["RaceClass"].fillna("?")
    timed = df[df["FinishTimeSec"].notna()]
    win = timed.groupby("race").agg(Date=("Date", "first"), Venue=("Venue", "first"), Track=("Track", "first"),
                                    cell=("cell", "first"), cls=("cls", "first"), wt=("FinishTimeSec", "min"))
    cell_hist, cc_hist, dev = defaultdict(list), defaultdict(list), {}
    for _, g in win.groupby("Date", sort=True):
        for r in g.itertuples():
            a, b = cc_hist[(r.cell, r.cls)], cell_hist[r.cell]
            std = np.median(a) if len(a) >= MIN_HISTORY else np.median(b) if len(b) >= MIN_HISTORY else None
            dev[r.Index] = np.nan if std is None else r.wt - std
        for r in g.itertuples():
            cc_hist[(r.cell, r.cls)].append(r.wt)
            cell_hist[r.cell].append(r.wt)
    win["dev"] = pd.Series(dev)
    variant = win.groupby(["Date", "Venue", "Track"])["dev"].median()
    timed = timed.assign(variant=[variant.get(k, np.nan) for k in zip(timed["Date"], timed["Venue"], timed["Track"])])
    timed = timed.assign(adj=timed["FinishTimeSec"] - timed["variant"].fillna(0.0))
    hist = defaultdict(list)
    for r in timed.itertuples():
        hist[r.HorseID].append((r.Date, r.cell, float(r.adj)))
    return hist


def best_time(hist, horse_id, race_date, cell):
    vals = [adj for day, c, adj in hist.get(horse_id, ()) if day < race_date and c == cell]
    return min(vals) if vals else None


def band(gap):
    if gap < 0.3:
        return K, "同程時間全場最快 0.3s 內"
    if gap < 0.6:
        return K / 2, "同程時間接近全場最快"
    if gap < 1.0:
        return 0.0, "同程時間中等"
    if gap < 1.5:
        return -K / 2, "同程時間慢全場最快 1s 以上"
    return -K, "同程時間慢全場最快 1.5s 以上"


def race_cell(race_context):
    venue = str(race_context.get("venue") or "").strip()
    track = "AWT" if "AWT" in str(race_context.get("track") or "") or "全天候" in str(race_context.get("track") or "") else "Turf"
    distance = re.search(r"\d{3,4}", str(race_context.get("distance") or ""))
    return (venue, track, int(distance.group(0))) if venue in ("沙田", "跑馬地") and distance else None


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine import engine_core
    from hkjc_racing_engine.scoring import clip_score

    hist = build_history(_load_bcs().load_all_completed_rows())
    load = orch._load_formline_opponent_summaries

    def wrapped(race_file, race_context, horses):
        summaries = load(race_file, race_context, horses)
        day, cell = str(race_context.get("race_date") or ""), race_cell(race_context)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or cell is None:
            return summaries
        best = {}
        for key, horse in horses.items():
            code = str((horse or {}).get("horse_code") or "").strip() if isinstance(horse, dict) else ""
            b = best_time(hist, code, day, cell) if code else None
            if b is not None:
                best[key] = b
        if len(best) < MIN_FIELD:
            return summaries
        top = min(best.values())
        summaries = dict(summaries)
        for key, b in best.items():
            summaries[key] = {**summaries.get(key, {}), "same_course_best_gap": round(b - top, 2)}
        return summaries

    orch._load_formline_opponent_summaries = wrapped

    cls = engine_core.SpeedScorer
    original = cls.compute

    def compute(self):
        score, note = original(self)
        gap = self._data().get("same_course_best_gap")
        if gap is None:
            return score, note
        delta, why = band(float(gap))
        self.detail = list(getattr(self, "detail", []) or []) + [
            {"factor": "同程最佳時間", "value": f"+{float(gap):.2f}s", "delta": round(delta, 2), "why": why}]
        return clip_score(score + delta), note

    cls.compute = compute
