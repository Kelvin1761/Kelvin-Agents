from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[6]
import sys as _sys; _sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING
STATS_ROOT = HK_RACING / "HKJC_Race_Results_Database" / "comprehensive_stats"

GENERAL_PRIOR_FILES = {
    "combo": [
        STATS_ROOT / "24_25" / "general_pre_race_priors" / "jockey_trainer_combo_priors.csv",
        STATS_ROOT / "25_26" / "general_pre_race_priors" / "jockey_trainer_combo_priors.csv",
    ],
    "jockey_distance": [
        STATS_ROOT / "24_25" / "jockey_distance_stats.csv",
        STATS_ROOT / "25_26" / "jockey_distance_stats.csv",
    ],
    "trainer_distance": [
        STATS_ROOT / "24_25" / "trainer_distance_stats.csv",
        STATS_ROOT / "25_26" / "trainer_distance_stats.csv",
    ],
    "jockey_change": [
        STATS_ROOT / "24_25" / "general_pre_race_priors" / "jockey_change_priors.csv",
        STATS_ROOT / "25_26" / "general_pre_race_priors" / "jockey_change_priors.csv",
    ],
    "jockey_draw": [
        STATS_ROOT / "24_25" / "jockey_draw_performance.csv",
        STATS_ROOT / "25_26" / "jockey_draw_performance.csv",
    ],
}


class TrainerSignalPriors:
    def __init__(self) -> None:
        self.combo = self._load_grouped(GENERAL_PRIOR_FILES["combo"], ["Jockey", "Trainer"])
        self.jockey_distance = self._load_grouped(GENERAL_PRIOR_FILES["jockey_distance"], ["Jockey", "Distance"])
        self.trainer_distance = self._load_grouped(GENERAL_PRIOR_FILES["trainer_distance"], ["Trainer", "Distance"])
        self.jockey_change = self._load_jockey_change()

    def _load_grouped(self, paths: list[Path], keys: list[str]) -> dict[tuple[str, ...], dict]:
        frames = [pd.read_csv(path, encoding="utf-8-sig") for path in paths if path.exists()]
        if not frames:
            return {}
        df = pd.concat(frames, ignore_index=True)
        for column in ("Wins", "Starts", "Places"):
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
        grouped = df.groupby(keys, dropna=False)[["Wins", "Starts", "Places"]].sum().reset_index()
        records: dict[tuple[str, ...], dict] = {}
        for row in grouped.to_dict(orient="records"):
            starts = float(row.get("Starts", 0.0) or 0.0)
            wins = float(row.get("Wins", 0.0) or 0.0)
            places = float(row.get("Places", 0.0) or 0.0)
            key = tuple(str(row[item]).strip() for item in keys)
            records[key] = {
                "starts": starts,
                "wins": wins,
                "places": places,
                "win_rate": (wins / starts * 100.0) if starts else 0.0,
                "place_rate": (places / starts * 100.0) if starts else 0.0,
            }
        return records

    def _load_jockey_change(self) -> dict[bool, dict]:
        frames = [pd.read_csv(path, encoding="utf-8-sig") for path in GENERAL_PRIOR_FILES["jockey_change"] if path.exists()]
        if not frames:
            return {}
        df = pd.concat(frames, ignore_index=True)
        df["Wins"] = pd.to_numeric(df["Wins"], errors="coerce").fillna(0.0)
        df["Starts"] = pd.to_numeric(df["Starts"], errors="coerce").fillna(0.0)
        df["Places"] = pd.to_numeric(df["Places"], errors="coerce").fillna(0.0)
        grouped = df.groupby("JockeyChanged", dropna=False)[["Wins", "Starts", "Places"]].sum().reset_index()
        records: dict[bool, dict] = {}
        for row in grouped.to_dict(orient="records"):
            changed = str(row["JockeyChanged"]).strip().lower() == "true"
            starts = float(row["Starts"] or 0.0)
            wins = float(row["Wins"] or 0.0)
            places = float(row["Places"] or 0.0)
            records[changed] = {
                "starts": starts,
                "wins": wins,
                "places": places,
                "win_rate": (wins / starts * 100.0) if starts else 0.0,
                "place_rate": (places / starts * 100.0) if starts else 0.0,
            }
        return records
