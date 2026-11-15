#!/usr/bin/env python3
"""build_comprehensive_stats.py — 重建 HKJC comprehensive_stats 衍生 CSV

引擎（hkjc_wong_choi_auto）食嘅統計檔全部係靜態快照，之前冇生成器。
呢個 script 由 race_results_{season}.csv 重新聚合出引擎消耗嘅檔案，
並可以由季度賽果資料夾（full_day_results.json）自動追加快照之後嘅新賽日
（追加 rows 同主表一樣齊欄：完成時間、檔位、負磅、走位、班次…，
 見 `result_row`）。

重建檔案（每季）：
  jockey_master_stats.csv / trainer_master_stats.csv      ← 連續實績評分用
  jockey_distance_stats.csv / trainer_distance_stats.csv  ← 同程調整用
  jockey_venue_track_stats.csv                            ← 場地統計（顯示/實驗）
  general_pre_race_priors/jockey_trainer_combo_priors.csv ← 騎練組合用
  general_pre_race_priors/jockey_change_priors.csv        ← 換騎先驗用

用法：
  python3 build_comprehensive_stats.py           # 重算並同現有檔比對，唔寫
  python3 build_comprehensive_stats.py --write   # 重算並覆寫（會 backup .bak）

⚠️ --write 之後 ratings 會包含最新賽果：production 評分更準，但 backtest
基準線要重新建立（新數據對舊賽日有 lookahead）。建議每個賽日賽前行一次。
"""
from __future__ import annotations

import os
os.environ.setdefault("PYTHONUTF8", "1")
import argparse
import ast
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hkjc_completed_rows as _completed

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING, is_materialized_file  # noqa: E402

DB_ROOT = HK_RACING / "HKJC_Race_Results_Database"
STATS_ROOT = DB_ROOT / "comprehensive_stats"

STATIC_SEASONS = _completed.STATIC_SEASONS

RESULTS_SEASON_RE = _completed.RESULTS_SEASON_RE
BASE_COLUMNS = _completed.BASE_COLUMNS
TRAINER_RECENCY_HALF_LIFE_DAYS = 90
TRAINER_RECENCY_RELATIVE_PATH = Path("experimental") / "trainer_recency_90d_stats.csv"


season_key_from_results_dir = _completed.season_key_from_results_dir


def discover_seasons(db_root: Path | None = None) -> dict[str, dict[str, object]]:
    return _completed.discover_seasons(Path(db_root or DB_ROOT))


SEASONS = discover_seasons()

VENUE_NORM = _completed.VENUE_NORM
DISTANCE_RE = _completed.DISTANCE_RE


race_metadata = _completed.race_metadata


_num = _completed._num


# Same labels as the original snapshot builder (scratch/aggregate_all_stats.py),
# so appended rows group together with the materialized race_results CSV rows.
CLASS_LABELS = _completed.CLASS_LABELS


_header_rows = _completed._header_rows


_cell_after = _completed._cell_after


race_header = _completed.race_header


_finish_seconds = _completed._finish_seconds


_run_style = _completed._run_style


_odds_bucket = _completed._odds_bucket


_weight_bucket = _completed._weight_bucket


hkjc_season = _completed.hkjc_season


result_row = _completed.result_row


def load_base_rows(season_key: str) -> pd.DataFrame:
    return _completed.load_base_rows(season_key, _completed.FilesystemRows(DB_ROOT, STATS_ROOT, SEASONS, is_materialized_file))


def append_new_meetings(season_key: str, base: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    return _completed.append_new_meetings(season_key, base, _completed.FilesystemRows(DB_ROOT, STATS_ROOT, SEASONS, is_materialized_file))


def agg(df: pd.DataFrame, keys: list[str], with_profit: bool = False) -> pd.DataFrame:
    cols = {"Win": "Wins", "Rank": "Starts", "Place": "Places"}
    g = df.groupby(keys, dropna=True).agg(
        Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum"),
        **({"Profit": ("Profit", "sum")} if with_profit else {}),
    ).reset_index()
    for column in ("Wins", "Starts", "Places", "Profit"):
        if column in g:
            g[column] = pd.to_numeric(g[column], errors="coerce").fillna(0.0)
    g["WinRate"] = (g["Wins"] / g["Starts"] * 100).round(1)
    g["PlaceRate"] = (g["Places"] / g["Starts"] * 100).round(1)
    if with_profit:
        g["Profit"] = g["Profit"].round(1)
        g["ROI"] = (g["Profit"] / g["Starts"] * 100).round(1)
    return g


def build_change_priors(df: pd.DataFrame) -> pd.DataFrame:
    d = df.sort_values("Date").copy()
    d["PrevJockey"] = d.groupby("Horse")["Jockey"].shift(1)
    d = d[d["PrevJockey"].notna()]
    d["JockeyChanged"] = d["Jockey"] != d["PrevJockey"]
    g = d.groupby("JockeyChanged").agg(
        Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum"),
        AvgOdds=("Odds", "mean"),
    ).reset_index()
    g["AvgOdds"] = g["AvgOdds"].round(2)
    g["WinRate"] = (g["Wins"] / g["Starts"] * 100).round(1)
    g["PlaceRate"] = (g["Places"] / g["Starts"] * 100).round(1)
    g["Scope"] = "all"
    return g


def build_all(season_key: str, extend: bool = True):
    base = load_base_rows(season_key)
    added = []
    if extend:
        base, added = append_new_meetings(season_key, base)
    dist_rows = base[base["Distance"].notna()] if "Distance" in base else base
    if "Distance" in dist_rows:
        # Integer metres. A NaN anywhere in the season's rows makes the column
        # float, so the CSV said `1200.0` and the live engine (which looks up
        # "1200") missed every 騎師同程／練馬師同程 row from 2026-10-07
        # (EXP-20261018-02/04).
        dist_rows = dist_rows.copy()
        dist_rows["Distance"] = pd.to_numeric(dist_rows["Distance"], errors="coerce")
        dist_rows = dist_rows[dist_rows["Distance"].notna()]
        dist_rows["Distance"] = dist_rows["Distance"].round().astype(int)

    out = {}
    m = agg(base, ["Jockey"], with_profit=True)
    out["jockey_master_stats.csv"] = m[["Jockey", "Wins", "Starts", "Places", "Profit", "WinRate", "PlaceRate", "ROI"]]
    t = agg(base, ["Trainer"], with_profit=True)
    out["trainer_master_stats.csv"] = t[["Trainer", "Wins", "Starts", "Places", "Profit", "WinRate", "PlaceRate", "ROI"]]
    jd = agg(dist_rows, ["Jockey", "Distance"])
    out["jockey_distance_stats.csv"] = jd[["Jockey", "Distance", "Wins", "Starts", "Places", "WinRate"]]
    td = agg(dist_rows, ["Trainer", "Distance"])
    out["trainer_distance_stats.csv"] = td[["Trainer", "Distance", "Wins", "Starts", "Places", "WinRate"]]
    vt = agg(base, ["Jockey", "Venue", "Track"], with_profit=True)
    out["jockey_venue_track_stats.csv"] = vt[["Jockey", "Venue", "Track", "Wins", "Starts", "Places", "Profit", "WinRate", "ROI"]]
    combo = agg(base, ["Jockey", "Trainer"])
    out["general_pre_race_priors/jockey_trainer_combo_priors.csv"] = combo[["Jockey", "Trainer", "Wins", "Starts", "Places", "WinRate", "PlaceRate"]]
    out["general_pre_race_priors/jockey_change_priors.csv"] = build_change_priors(base)
    return out, added


def load_all_completed_rows() -> pd.DataFrame:
    """Return every completed result row across discovered seasons."""
    frames = []
    for season_key in SEASONS:
        base = load_base_rows(season_key)
        base, _added = append_new_meetings(season_key, base)
        frames.append(base)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=BASE_COLUMNS)


COVERAGE_COLUMNS = (
    "RaceNo", "RaceClass", "Track", "Distance", "Draw", "Odds", "ActualWt",
    "HorseWt", "FinishTimeSec", "RunningPos", "HorseID",
)


def coverage_regressions(rows: pd.DataFrame, recent_days: int = 60,
                         healthy: float = 0.90, dead: float = 0.50) -> list[str]:
    """Columns that used to be filled but have gone empty recently.

    Fill rate over the last ``recent_days`` vs the best calendar month before
    that. A column whose best month was ≥ ``healthy`` and is < ``dead`` now is
    a silent extraction break (2026-05-13 → 2026-10-25: finish time, draw,
    weights and horse ID all 0% while every consumer kept running).

    The reference is the best month, not the pooled older rows: pooling lets
    the dead period dilute its own baseline — five dead months had already
    pulled pooled coverage to 89%, under the alarm line.
    """
    if rows.empty:
        return []
    dates = pd.to_datetime(rows["Date"].astype(str), errors="coerce")
    cutoff = dates.max() - pd.Timedelta(days=recent_days)
    old_mask, new_mask = dates <= cutoff, dates > cutoff
    if not old_mask.any() or not new_mask.any():
        return []
    months = dates[old_mask].dt.to_period("M")
    out = []
    for column in COVERAGE_COLUMNS:
        if column in rows:
            best = rows.loc[old_mask, column].notna().groupby(months).mean().max()
            now = rows.loc[new_mask, column].notna().mean()
        else:
            best, now = 0.0, 0.0
        if best >= healthy and now < dead:
            out.append(f"{column}: 歷史最佳月 {best:.1%} → 近 {recent_days} 日 {now:.1%}"
                       f"（{int(new_mask.sum())} 行）")
    return out


def build_trainer_recency_snapshot(
    rows: pd.DataFrame,
    *,
    as_of_date: str | None = None,
    half_life_days: int = TRAINER_RECENCY_HALF_LIFE_DAYS,
) -> pd.DataFrame:
    """Build a shadow-only date-decayed trainer aggregate.

    The snapshot deliberately stays outside the live season folders.  It is
    consumed only by the registered prospective shadow, never by mainline
    trainer ratings.
    """
    cutoff_text = str(as_of_date or date.today().isoformat())
    cutoff = pd.Timestamp(cutoff_text)
    work = rows.copy()
    work["_date"] = pd.to_datetime(work["Date"], errors="raise")
    work = work[work["_date"] < cutoff].copy()
    if work.empty:
        return pd.DataFrame(
            columns=(
                "Trainer", "Wins", "Starts", "Places", "WinRate", "PlaceRate",
                "AsOfDate", "LatestResultDate", "HalfLifeDays",
            )
        )
    ages = (cutoff - work["_date"]).dt.days.astype(float)
    if (ages <= 0).any():
        raise ValueError("trainer recency snapshot must use strictly prior results")
    work["_weight"] = 0.5 ** (ages / float(half_life_days))
    work["_wins"] = pd.to_numeric(work["Win"], errors="coerce").fillna(0.0) * work["_weight"]
    work["_places"] = pd.to_numeric(work["Place"], errors="coerce").fillna(0.0) * work["_weight"]
    work["Trainer"] = work["Trainer"].astype(str).str.strip()
    work = work[work["Trainer"] != ""]
    latest = work["_date"].max().date().isoformat()
    output = work.groupby("Trainer")[["_wins", "_weight", "_places"]].sum().reset_index()
    output = output.rename(columns={"_wins": "Wins", "_weight": "Starts", "_places": "Places"})
    output["WinRate"] = output["Wins"] / output["Starts"] * 100.0
    output["PlaceRate"] = output["Places"] / output["Starts"] * 100.0
    output["AsOfDate"] = cutoff.date().isoformat()
    output["LatestResultDate"] = latest
    output["HalfLifeDays"] = int(half_life_days)
    numeric = ["Wins", "Starts", "Places", "WinRate", "PlaceRate"]
    output[numeric] = output[numeric].round(8)
    return output.sort_values("Trainer").reset_index(drop=True)


def write_trainer_recency_snapshot(snapshot: pd.DataFrame) -> Path:
    path = STATS_ROOT / TRAINER_RECENCY_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    snapshot.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def check_against_existing(season_key: str, built: dict) -> None:
    root = STATS_ROOT / season_key
    for rel, new_df in built.items():
        path = root / rel
        if not path.exists():
            print(f"  ⚠️ {rel}: 現有檔唔存在")
            continue
        old = pd.read_csv(path, encoding="utf-8-sig")
        old_starts = pd.to_numeric(old.get("Starts", pd.Series(dtype=float)), errors="coerce").sum()
        new_starts = new_df["Starts"].sum()
        print(f"  {rel}: rows {len(old)}→{len(new_df)}  ΣStarts {old_starts:.0f}→{new_starts:.0f}")
        sample = new_df.sort_values("Starts", ascending=False).head(1)
        if len(sample):
            metric_columns = {
                "Wins", "Starts", "Places", "Profit", "WinRate", "PlaceRate",
                "ROI", "AvgOdds",
            }
            keys = [column for column in new_df.columns if column not in metric_columns]
            old_mask = pd.Series(True, index=old.index)
            for key in keys:
                old_mask &= old[key].astype(str) == str(sample.iloc[0][key])
            old_row = old[old_mask]
            if len(old_row):
                label = " / ".join(str(sample.iloc[0][key]) for key in keys)
                print(f"    抽查 {label}: 舊 Starts={old_row.iloc[0].get('Starts')} → 新 Starts={sample.iloc[0]['Starts']}")


def write_out(season_key: str, built: dict) -> None:
    root = STATS_ROOT / season_key
    for rel, new_df in built.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        new_df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  ✅ 寫入 {rel}（{len(new_df)} rows，舊檔備份 .bak）")


def main() -> int:
    ap = argparse.ArgumentParser(description="重建 HKJC comprehensive_stats 衍生 CSV")
    ap.add_argument("--write", action="store_true", help="覆寫現有 CSV（預設只 check）")
    ap.add_argument("--no-extend", action="store_true", help="唔追加快照後嘅新賽日")
    ap.add_argument("--season", choices=list(SEASONS), help="只處理一季（預設全部）")
    ap.add_argument("--coverage-check", action="store_true",
                    help="只檢查追加 rows 有冇欄位靜靜變空（❌ → exit 1），唔重算")
    args = ap.parse_args()

    if args.coverage_check:
        rows = load_all_completed_rows()
        problems = coverage_regressions(rows)
        print(f"賽果庫 {len(rows)} 行，{rows['Date'].min()} → {rows['Date'].max()}")
        for line in problems:
            print(f"  ❌ {line}")
        if not problems:
            print("  ✅ 冇欄位變空")
        return 1 if problems else 0

    for season_key in ([args.season] if args.season else SEASONS):
        print(f"== {season_key} ==")
        built, added = build_all(season_key, extend=not args.no_extend)
        if added:
            print(f"  追加咗 {len(added)} 個新賽日：{added[0]} → {added[-1]}")
        else:
            print("  冇新賽日需要追加")
        if args.write:
            write_out(season_key, built)
        else:
            check_against_existing(season_key, built)
    # Research-only forward source.  Always rebuild from every season even when
    # --season limits the live aggregate check; otherwise a partial invocation
    # could silently truncate the cross-season decay history.
    recency = build_trainer_recency_snapshot(load_all_completed_rows())
    if args.write:
        path = write_trainer_recency_snapshot(recency)
        latest = recency["LatestResultDate"].iloc[0] if len(recency) else "none"
        print(
            f"  ✅ 寫入 shadow trainer recency：{path.relative_to(STATS_ROOT)} "
            f"（{len(recency)} trainers，latest={latest}）"
        )
    else:
        print(
            f"  shadow trainer recency check：{len(recency)} trainers，"
            f"half-life={TRAINER_RECENCY_HALF_LIFE_DAYS}日（未寫入）"
        )
    if not args.write:
        print("\n（只 check，未寫入。確認無誤請加 --write；建議每賽日賽前行一次。）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
