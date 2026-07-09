#!/usr/bin/env python3
"""build_comprehensive_stats.py — 重建 HKJC comprehensive_stats 衍生 CSV

引擎（hkjc_wong_choi_auto）食嘅統計檔全部係靜態快照，之前冇生成器。
呢個 script 由 race_results_{season}.csv 重新聚合出引擎消耗嘅檔案，
並可以由季度賽果資料夾（full_day_results.json）自動追加快照之後嘅新賽日
（新賽日 rows 冇距離／班次 → 只入 master／組合／換騎／場地統計，
 同程統計維持由 race_results 主表計）。

重建檔案（每季）：
  jockey_master_stats.csv / trainer_master_stats.csv      ← 連續實績評分用
  jockey_distance_stats.csv / trainer_distance_stats.csv  ← 同程調整用
  jockey_venue_track_stats.csv                            ← 場地統計（顯示/實驗）
  general_pre_race_priors/jockey_trainer_combo_priors.csv ← 騎練組合用
  general_pre_race_priors/jockey_change_priors.csv        ← 換騎先驗用

用法：
  python3 build_comprehensive_stats.py --check   # 重算並同現有檔比對，唔寫
  python3 build_comprehensive_stats.py --write   # 重算並覆寫（會 backup .bak）

⚠️ --write 之後 ratings 會包含最新賽果：production 評分更準，但 backtest
基準線要重新建立（新數據對舊賽日有 lookahead）。建議每個賽日賽前行一次。
"""
import os
os.environ.setdefault("PYTHONUTF8", "1")
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING  # noqa: E402

DB_ROOT = HK_RACING / "HKJC_Race_Results_Database"
STATS_ROOT = DB_ROOT / "comprehensive_stats"

SEASONS = {
    "24_25": {"csv": "race_results_24_25.csv", "results_dir": "hkjc results 2024 25"},
    "25_26": {"csv": "race_results_25_26.csv", "results_dir": "hkjc results 2025 26"},
}

VENUE_NORM = {"ST": "沙田", "HV": "跑馬地", "Sha Tin": "沙田", "Happy Valley": "跑馬地"}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_base_rows(season_key: str) -> pd.DataFrame:
    path = STATS_ROOT / season_key / SEASONS[season_key]["csv"]
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["Date"] = df["Date"].astype(str)
    return df


def append_new_meetings(season_key: str, base: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """快照之後嘅賽日由 full_day_results.json 追加（冇距離/班次欄）。"""
    results_dir = DB_ROOT / SEASONS[season_key]["results_dir"]
    if not results_dir.exists():
        return base, []
    max_date = base["Date"].max()
    new_rows, added_dates = [], []
    for day_dir in sorted(results_dir.iterdir()):
        if not day_dir.is_dir() or day_dir.name <= max_date:
            continue
        fp = day_dir / "full_day_results.json"
        if not fp.exists():
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for race_key, race in data.items():
            if not isinstance(race, dict):
                continue
            venue = VENUE_NORM.get(str(race.get("venue", "")).strip(), str(race.get("venue", "")).strip())
            for row in race.get("results", []):
                pos = _num(re.sub(r"\D", "", str(row.get("pos", ""))) or None)
                if pos is None or pos <= 0:
                    continue
                odds = _num(row.get("win_odds"))
                win = 1 if pos == 1 else 0
                new_rows.append({
                    "Date": day_dir.name,
                    "Venue": venue,
                    "Track": "Unknown",
                    "Distance": None,
                    "Horse": str(row.get("horse_name", "")),
                    "Jockey": str(row.get("jockey", "")).strip(),
                    "Trainer": str(row.get("trainer", "")).strip(),
                    "Rank": pos,
                    "Win": win,
                    "Place": 1 if pos <= 3 else 0,
                    "Odds": odds,
                    "Profit": (odds - 1.0) if (win and odds) else (-1.0 if odds else 0.0),
                })
        added_dates.append(day_dir.name)
    if not new_rows:
        return base, []
    return pd.concat([base, pd.DataFrame(new_rows)], ignore_index=True), added_dates


def agg(df: pd.DataFrame, keys: list[str], with_profit: bool = False) -> pd.DataFrame:
    cols = {"Win": "Wins", "Rank": "Starts", "Place": "Places"}
    g = df.groupby(keys, dropna=True).agg(
        Wins=("Win", "sum"), Starts=("Win", "count"), Places=("Place", "sum"),
        **({"Profit": ("Profit", "sum")} if with_profit else {}),
    ).reset_index()
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


def check_against_existing(season_key: str, built: dict) -> None:
    root = STATS_ROOT / season_key
    for rel, new_df in built.items():
        path = root / rel
        if not path.exists():
            print(f"  ⚠️ {rel}: 現有檔唔存在")
            continue
        old = pd.read_csv(path, encoding="utf-8-sig")
        key = new_df.columns[0]
        old_starts = pd.to_numeric(old.get("Starts", pd.Series(dtype=float)), errors="coerce").sum()
        new_starts = new_df["Starts"].sum()
        print(f"  {rel}: rows {len(old)}→{len(new_df)}  ΣStarts {old_starts:.0f}→{new_starts:.0f}")
        sample = new_df.sort_values("Starts", ascending=False).head(1)
        if len(sample):
            name = sample.iloc[0][key]
            old_row = old[old[key] == name]
            if len(old_row):
                print(f"    抽查 {name}: 舊 Starts={old_row.iloc[0].get('Starts')} → 新 Starts={sample.iloc[0]['Starts']}")


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
    args = ap.parse_args()

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
    if not args.write:
        print("\n（只 check，未寫入。確認無誤請加 --write；建議每賽日賽前行一次。）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
