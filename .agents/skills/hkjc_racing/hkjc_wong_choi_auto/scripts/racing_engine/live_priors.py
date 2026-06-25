from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

import pandas as pd

from scoring import clip_score, parse_float

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

_LIVE_DRAW_PRIORS: DrawHistoryPriors | None = None
_LIVE_TRAINER_PRIORS: TrainerSignalPriors | None = None


def apply_live_feature_priors(horse: dict, features: dict[str, float], race_context: dict | None = None) -> dict[str, float]:
    draw_priors, trainer_priors = get_live_prior_stack()
    transformed = draw_priors.apply(horse, features, race_context)
    return trainer_priors.apply(horse, transformed, race_context)


def get_live_prior_stack() -> tuple["DrawHistoryPriors", "TrainerSignalPriors"]:
    global _LIVE_DRAW_PRIORS, _LIVE_TRAINER_PRIORS
    if _LIVE_DRAW_PRIORS is None:
        _LIVE_DRAW_PRIORS = DrawHistoryPriors("all")
    if _LIVE_TRAINER_PRIORS is None:
        _LIVE_TRAINER_PRIORS = TrainerSignalPriors()
    return _LIVE_DRAW_PRIORS, _LIVE_TRAINER_PRIORS


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

    def apply(self, horse: dict, features: dict[str, float], race_context: dict | None = None) -> dict[str, float]:
        updated = deepcopy(features)
        jockey = str(horse.get("jockey") or "").strip()
        trainer = str(horse.get("trainer") or "").strip()
        distance = _normalize_distance((race_context or {}).get("distance"))

        jockey_adj = 0.0
        trainer_adj = 0.0

        horse_history = _current_jockey_horse_history(horse)
        if horse_history:
            jockey_adj += self._horse_history_adjustment(horse_history)

        combo_row = self.combo.get((jockey, trainer))
        if combo_row:
            combo_adj = self._combo_adjustment(combo_row)
            jockey_adj += combo_adj * 0.55
            trainer_adj += combo_adj * 0.45

        if distance:
            jockey_distance_row = self.jockey_distance.get((jockey, distance))
            if jockey_distance_row:
                jockey_adj += self._jockey_distance_adjustment(jockey_distance_row)
            trainer_distance_row = self.trainer_distance.get((trainer, distance))
            if trainer_distance_row:
                trainer_adj += self._trainer_distance_adjustment(trainer_distance_row)

        if _is_jockey_changed(horse) is True:
            jockey_adj += self._jockey_change_adjustment()

        updated["jockey_score"] = clip_score(updated.get("jockey_score", 60.0) + jockey_adj)
        updated["trainer_score"] = clip_score(updated.get("trainer_score", 60.0) + trainer_adj)
        return updated

    def _horse_history_adjustment(self, row: dict) -> float:
        starts = row["starts"]
        place_rate = row["place_rate"]
        avg_finish = row["avg_finish"]
        wins = row["wins"]
        if starts >= 2 and (wins >= 1 or place_rate >= 50.0) and avg_finish <= 5.0:
            return 4.0
        if starts >= 3 and place_rate >= 33.0 and avg_finish <= 5.5:
            return 2.0
        if starts >= 3 and place_rate == 0.0 and avg_finish >= 7.0:
            return -4.0
        if starts >= 5 and place_rate <= 20.0 and avg_finish >= 6.5:
            return -2.0
        return 0.0

    def _combo_adjustment(self, row: dict) -> float:
        if row["starts"] < 80:
            return 0.0
        if row["win_rate"] >= 14.0 or row["place_rate"] >= 36.0:
            return 4.0
        if row["win_rate"] >= 11.0 or row["place_rate"] >= 30.0:
            return 2.0
        if row["win_rate"] <= 7.0 and row["place_rate"] <= 23.0:
            return -2.0
        return 0.0

    def _jockey_distance_adjustment(self, row: dict) -> float:
        if row["starts"] < 80:
            return 0.0
        if row["win_rate"] >= 15.0 or row["place_rate"] >= 40.0:
            return 3.0
        if row["win_rate"] >= 10.0 or row["place_rate"] >= 30.0:
            return 1.5
        if row["win_rate"] <= 6.0 and row["place_rate"] <= 22.0:
            return -2.0
        return 0.0

    def _trainer_distance_adjustment(self, row: dict) -> float:
        if row["starts"] < 80:
            return 0.0
        if row["win_rate"] >= 12.0 or row["place_rate"] >= 34.0:
            return 2.0
        if row["win_rate"] >= 9.0 or row["place_rate"] >= 28.0:
            return 1.0
        if row["win_rate"] <= 5.0 and row["place_rate"] <= 20.0:
            return -1.5
        return 0.0

    def _jockey_change_adjustment(self) -> float:
        keep = self.jockey_change.get(False)
        change = self.jockey_change.get(True)
        if not keep or not change:
            return 0.0
        if keep["win_rate"] >= change["win_rate"] + 1.0 and keep["place_rate"] >= change["place_rate"] + 3.0:
            return -1.5
        return 0.0


class DrawHistoryPriors:
    def __init__(self, mode: str = "all") -> None:
        self.mode = mode
        self.jockey_draw = self._load_grouped(GENERAL_PRIOR_FILES["jockey_draw"], ["Jockey", "Draw"])

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

    def apply(self, horse: dict, features: dict[str, float], race_context: dict | None = None) -> dict[str, float]:
        updated = deepcopy(features)
        if not self._eligible(horse, features):
            return updated
        draw_num = _draw_number(horse)
        if draw_num is None:
            return updated

        jockey = str(horse.get("jockey") or "").strip()

        adjustment = 0.0

        jockey_draw_row = self.jockey_draw.get((jockey, str(draw_num)))
        if jockey_draw_row and jockey_draw_row["starts"] >= 40:
            if jockey_draw_row["win_rate"] >= 14.0 or jockey_draw_row["place_rate"] >= 36.0:
                adjustment += 2.0
            elif jockey_draw_row["win_rate"] <= 4.0 and jockey_draw_row["place_rate"] <= 18.0:
                adjustment -= 2.0

        adjustment += _horse_draw_history_adjustment(horse, draw_num)
        updated["draw_score"] = clip_score(updated.get("draw_score", 60.0) + adjustment)
        return updated

    def _eligible(self, horse: dict, features: dict[str, float]) -> bool:
        is_debut = bool(horse.get("is_debut") or horse.get("debut_runner") or horse.get("career_tag") == "DEBUT")
        confidence = clip_score(features.get("confidence_score", 60.0))
        if self.mode == "debut_only":
            return is_debut
        if self.mode == "low_confidence_only":
            return confidence <= 60.0
        if self.mode == "debut_or_low_confidence":
            return is_debut or confidence <= 60.0
        return True


def _draw_number(horse: dict) -> int | None:
    draw = horse.get("barrier") or horse.get("draw")
    try:
        return int(draw)
    except (TypeError, ValueError):
        return None


def _current_jockey_horse_history(horse: dict) -> dict | None:
    block = str(((horse.get("_data") or {}).get("jockey_combo_block")) or "")
    current_jockey = str(horse.get("jockey") or "").strip()
    if not block or not current_jockey:
        return None
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|") or "← 今場" not in line:
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 8:
            continue
        jockey_name = parts[0].replace("← 今場", "").strip()
        if jockey_name and current_jockey not in jockey_name and jockey_name not in current_jockey:
            continue
        try:
            starts = float(parts[1])
            wins = float(parts[2])
            places = float(parts[4])
            avg_finish = float(parts[5])
            place_rate_text = parts[7].replace("%", "").strip()
            place_rate = float(place_rate_text) if place_rate_text else (places / starts * 100.0 if starts else 0.0)
        except ValueError:
            continue
        return {
            "starts": starts,
            "wins": wins,
            "places": places,
            "avg_finish": avg_finish,
            "place_rate": place_rate,
        }
    return None


def _is_jockey_changed(horse: dict) -> bool | None:
    block = str(((horse.get("_data") or {}).get("jockey_combo_block")) or "")
    current_jockey = str(horse.get("jockey") or "").strip()
    if not block or not current_jockey:
        return None
    recent_lines = []
    capture = False
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if "近6場騎師歷史" in line:
            capture = True
            continue
        if not capture:
            continue
        if line.startswith("|") and "|" in line[1:]:
            recent_lines.append(line)
    for line in recent_lines:
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 4 or parts[0] in {"#", "---"}:
            continue
        jockey_name = parts[2]
        if jockey_name:
            return jockey_name != current_jockey
    return None


def _normalize_venue(value: object) -> str:
    text = str(value or "").strip()
    if text in {"HV", "Happy Valley", "跑馬地"}:
        return "跑馬地"
    if text in {"ST", "Sha Tin", "沙田"}:
        return "沙田"
    if text in {"", "Unknown"}:
        return "跑馬地" if "HappyValley" in str(value or "") else "沙田"
    return text


def _normalize_track(horse: dict, race_context: dict) -> str:
    text = str(race_context.get("surface") or race_context.get("track") or "").strip().upper()
    if text in {"AWT", "AW", "ALL WEATHER", "DIRT"}:
        return "AWT"
    return "Turf"


def _normalize_distance(value: object) -> str:
    return str(value or "").replace("m", "").strip()


def _horse_draw_history_adjustment(horse: dict, draw_num: int) -> float:
    fit = str(((horse.get("_data") or {}).get("draw_position_fit")) or "")
    if not fit:
        return 0.0
    draw_bucket = "內檔" if draw_num <= 4 else "中檔" if draw_num <= 8 else "外檔"
    pattern = rf"{draw_bucket}\([^)]*\)上名率(\d+)%\((\d+)/(\d+)\)"
    match = re.search(pattern, fit)
    if not match:
        return 0.0
    rate = float(match.group(1))
    starts = float(match.group(3))
    if starts < 5:
        return 0.0
    if rate >= 45.0:
        return 2.0
    if rate <= 15.0:
        return -2.0
    return 0.0
