"""同程最佳時間（對全場）—— 報告顯示用，**唔入評分**。

EXP-20261025-08：同程最佳時間將上名馬拉入頭 5（top3_capture@5 +1.1pp），但用嚟加分會推走
首選（Good −1.6～−2.2pp），四個 arm 全部 REJECT。所以只喺段速維度嘅數據錨點顯示，
畀人自己睇，引擎冇任何地方讀佢。

算法同 `docs/experiments/patches/hkjc_arm_same_course_best_time.py` 一樣：

    標準    = 嗰場賽日之前同 (場地, 跑道, 路程, 班次) 頭馬時間中位數（≥8 場；唔夠退返同路程）
    variant = 當日各場頭馬時間 − 標準 嘅中位數（每個賽日、場地、跑道一個）
    adj     = 完成時間 − variant
    最佳    = 賽日**之前**、同場地＋跑道＋路程 adj 最細值

資料嚟自 `build_comprehensive_stats.load_all_completed_rows()`（每個 process 載入一次）。
任何讀取失敗都返回空 dict —— 顯示欄位冇咗唔可以令評分失敗。
"""
from __future__ import annotations

import importlib.util
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
MIN_HISTORY = 8
_HISTORY = None


def _load_rows():
    spec = importlib.util.spec_from_file_location(
        "bcs_same_course_display", REPO / ".agents/scripts/build_comprehensive_stats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_all_completed_rows()


def build_history(rows) -> dict:
    """HorseID → [(date, cell, adj, raw)]。每個 adj 只用嗰日之前嘅標準同嗰日自己嘅 variant。"""
    import numpy as np
    import pandas as pd

    df = rows[rows["Rank"].notna() & rows["Distance"].notna() & rows["RaceNo"].notna()].copy()
    ids = df["Horse"].astype(str).str.extract(r"\(([A-Z]\d{3})\)\s*$")[0]
    df["HorseID"] = df["HorseID"].fillna(ids) if "HorseID" in df else ids
    df = df[df["HorseID"].notna()]
    df["Date"] = df["Date"].astype(str)
    df["race"] = df["Date"] + "_" + df["Venue"].astype(str) + "_" + df["RaceNo"].astype(int).astype(str)
    df["cell"] = list(zip(df["Venue"], df["Track"], df["Distance"].astype(int)))
    df["cls"] = df["RaceClass"].fillna("?") if "RaceClass" in df else "?"
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
    hist = defaultdict(list)
    for r in timed.itertuples():
        v = variant.get((r.Date, r.Venue, r.Track), np.nan)
        adj = float(r.FinishTimeSec) - (0.0 if v != v else float(v))
        hist[r.HorseID].append((r.Date, r.cell, adj, float(r.FinishTimeSec)))
    return hist


def _history():
    global _HISTORY
    if _HISTORY is None:
        try:
            _HISTORY = build_history(_load_rows())
        except Exception:  # noqa: BLE001 — display field must never break scoring
            _HISTORY = {}
    return _HISTORY


def race_cell(race_context: dict):
    venue = str(race_context.get("venue") or "").strip()
    track_text = str(race_context.get("track") or "")
    track = "AWT" if "AWT" in track_text or "全天候" in track_text or "泥" in track_text else "Turf"
    distance = re.search(r"\d{3,4}", str(race_context.get("distance") or ""))
    if venue not in ("沙田", "跑馬地") or not distance:
        return None
    return venue, track, int(distance.group(0))


def _clock(seconds: float) -> str:
    minutes, rest = divmod(seconds, 60.0)
    return f"{int(minutes)}:{rest:05.2f}" if minutes else f"{rest:.2f}"


def field_best_times(race_date: str, cell, codes: dict, history: dict | None = None) -> dict:
    """{horse_key: 顯示字串}。codes = {horse_key: horse_code}。冇同程紀錄嘅馬都有一句。"""
    if not cell or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(race_date or "")):
        return {}
    hist = _history() if history is None else history
    if not hist:
        return {}
    best = {}
    for key, code in codes.items():
        runs = [(adj, raw) for day, c, adj, raw in hist.get(code, ()) if day < race_date and c == cell]
        if runs:
            adj, raw = min(runs)
            best[key] = (adj, raw, len(runs))
    venue, track, distance = cell
    label = f"{venue}{'泥地' if track == 'AWT' else '草地'}{distance}m"
    order = sorted(best, key=lambda k: best[k][0])
    top = best[order[0]][0] if order else None
    out = {}
    for key in codes:
        if key not in best:
            out[key] = f"{label} 未有往績（全場 {len(best)}/{len(codes)} 匹有同程時間）｜僅供參考，未入評分"
            continue
        adj, raw, n = best[key]
        rank = order.index(key) + 1
        gap = "全場最快" if rank == 1 else f"慢全場最快 {adj - top:.2f}s"
        out[key] = (f"{label} 最佳 {_clock(raw)}（扣場地快慢 {_clock(adj)}，{n} 仗）"
                    f"｜全場第 {rank}/{len(best)}，{gap}｜僅供參考，未入評分")
    return out
