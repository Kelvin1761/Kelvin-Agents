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
  python3 build_comprehensive_stats.py           # 重算並同現有檔比對，唔寫
  python3 build_comprehensive_stats.py --write   # 重算並覆寫（會 backup .bak）

⚠️ --write 之後 ratings 會包含最新賽果：production 評分更準，但 backtest
基準線要重新建立（新數據對舊賽日有 lookahead）。建議每個賽日賽前行一次。
"""
from __future__ import annotations

import os
os.environ.setdefault("PYTHONUTF8", "1")
import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING, is_materialized_file  # noqa: E402

DB_ROOT = HK_RACING / "HKJC_Race_Results_Database"
STATS_ROOT = DB_ROOT / "comprehensive_stats"

STATIC_SEASONS = {
    "24_25": {"csv": "race_results_24_25.csv", "results_dir": "hkjc results 2024 25"},
    "25_26": {"csv": "race_results_25_26.csv", "results_dir": "hkjc results 2025 26"},
}

RESULTS_SEASON_RE = re.compile(r"^hkjc results (\d{4}) (\d{2})$")
BASE_COLUMNS = (
    "Date", "Venue", "Track", "Distance", "Horse", "Jockey", "Trainer",
    "Rank", "Win", "Place", "Odds", "Profit",
)
TRAINER_RECENCY_HALF_LIFE_DAYS = 90
TRAINER_RECENCY_RELATIVE_PATH = Path("experimental") / "trainer_recency_90d_stats.csv"


def season_key_from_results_dir(name: str) -> str | None:
    """Convert ``hkjc results 2026 27`` to the stats key ``26_27``."""
    match = RESULTS_SEASON_RE.fullmatch(str(name or "").strip())
    if not match:
        return None
    return f"{match.group(1)[-2:]}_{match.group(2)}"


def discover_seasons(db_root: Path | None = None) -> dict[str, dict[str, object]]:
    """Discover every canonical season, including a results-only new season.

    Historical seasons keep their materialized base CSV requirement.  A newly
    opened season legitimately has no consolidated CSV yet, so its completed
    ``full_day_results.json`` files are the base until one is produced.
    """
    root = Path(db_root or DB_ROOT)
    seasons: dict[str, dict[str, object]] = {
        key: {**value, "base_required": True}
        for key, value in STATIC_SEASONS.items()
    }
    try:
        children = list(root.iterdir())
    except OSError:
        children = []
    for path in children:
        if not path.is_dir():
            continue
        key = season_key_from_results_dir(path.name)
        if not key:
            continue
        seasons.setdefault(
            key,
            {
                "csv": f"race_results_{key}.csv",
                "results_dir": path.name,
                "base_required": False,
            },
        )
    return dict(sorted(seasons.items()))


SEASONS = discover_seasons()

VENUE_NORM = {
    "ST": "沙田",
    "HV": "跑馬地",
    "Sha Tin": "沙田",
    "ShaTin": "沙田",
    "Happy Valley": "跑馬地",
    "HappyValley": "跑馬地",
}
DISTANCE_RE = re.compile(r"(\d{3,4})\s*米")


def race_metadata(race: dict) -> tuple[float | None, str]:
    """Recover distance/surface from the result header tables.

    HKJC's JSON does not expose dedicated fields here, but the official header
    remains present in ``sectional_times`` / ``cumulative_times``.
    """
    header = json.dumps(
        race.get("sectional_times") or race.get("cumulative_times") or "",
        ensure_ascii=False,
    )
    distance_match = DISTANCE_RE.search(header)
    distance = float(distance_match.group(1)) if distance_match else None
    if "全天候" in header or "泥地" in header:
        track = "AWT"
    elif "草地" in header:
        track = "Turf"
    else:
        track = "Unknown"
    return distance, track


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_base_rows(season_key: str) -> pd.DataFrame:
    config = SEASONS[season_key]
    path = STATS_ROOT / season_key / str(config["csv"])
    if is_materialized_file(path):
        df = pd.read_csv(path, encoding="utf-8-sig")
        df["Date"] = df["Date"].astype(str)
        return df
    if bool(config.get("base_required", False)):
        raise RuntimeError(
            f"HKJC source CSV is not materialized locally: {path}. "
            "Mark the statistics folder Available offline before rebuilding/PIT replay."
        )
    results_dir = DB_ROOT / str(config["results_dir"])
    if not results_dir.exists():
        raise RuntimeError(f"HKJC results-only season is unavailable: {results_dir}")
    return pd.DataFrame(columns=BASE_COLUMNS)


def append_new_meetings(season_key: str, base: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """快照後賽日由 full_day_results.json 追加；路程／泥草從官方 header 還原。"""
    results_dir = DB_ROOT / SEASONS[season_key]["results_dir"]
    if not results_dir.exists():
        return base, []
    max_date = str(base["Date"].max()) if not base.empty else ""
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
            distance, track = race_metadata(race)
            for row in race.get("results", []):
                pos = _num(re.sub(r"\D", "", str(row.get("pos", ""))) or None)
                if pos is None or pos <= 0:
                    continue
                odds = _num(row.get("win_odds"))
                win = 1 if pos == 1 else 0
                new_rows.append({
                    "Date": day_dir.name,
                    "Venue": venue,
                    "Track": track,
                    "Distance": distance,
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
    appended = pd.DataFrame(new_rows)
    if base.empty:
        return appended, added_dates
    return pd.concat([base, appended], ignore_index=True), added_dates


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
