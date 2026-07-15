#!/usr/bin/env python3
"""
review_auto_weighting.py — HKJC Auto weighting review with walk-forward validation.

Purpose:
1. Re-score archived HKJC Logic JSON files with the current Auto engine.
2. Compare the current weighting/formula set against the prior calibrated set.
3. Summarize matrix-level signal strength using actual results.
4. Surface season-level deterministic trend candidates from 24/25 + 25/26 data.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from copy import deepcopy
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
ENGINE_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts" / "racing_engine"
sys.path.insert(0, str(ENGINE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine_core import RacingEngine  # noqa: E402
from features.draw import DrawScorer  # noqa: E402
from features.form import FormScorer  # noqa: E402
from features.jockey import JockeyScorer  # noqa: E402
from features.speed import SpeedScorer  # noqa: E402
from features.trainer import TrainerScorer  # noqa: E402
from hkjc_results_db import (  # noqa: E402
    get_analysis_archive_root,
    get_comprehensive_stats_root,
    get_season_csvs,
    get_season_results_roots,
)
from matrix_mapper import MATRIX_FORMULAS as CURRENT_MATRIX_FORMULAS  # noqa: E402
from scoring import MATRIX_WEIGHTS as CURRENT_MATRIX_WEIGHTS  # noqa: E402
from scoring import FEATURE_KEYS, clip_score, parse_float  # noqa: E402

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


PREVIOUS_MATRIX_WEIGHTS = {
    "sectional": 0.22,
    "trainer_signal": 0.16,
    "stability": 0.18,
    "race_shape": 0.20,
    "class_advantage": 0.06,
    "horse_health": 0.09,
    "form_line": 0.09,
}

PREVIOUS_MATRIX_FORMULAS = {
    "stability": (("form_score", 0.50), ("consistency_score", 0.40), ("confidence_score", 0.10)),
    "sectional": (("speed_score", 0.75), ("track_going_score", 0.25)),
    "race_shape": (("draw_score", 0.70), ("distance_score", 0.15), ("weight_score", 0.15)),
    "trainer_signal": (("jockey_score", 0.55), ("trainer_score", 0.45)),
    "horse_health": (("risk_score", 0.55), ("weight_score", 0.35), ("confidence_score", 0.10)),
    "form_line": (("formline_strength_score", 0.55), ("margin_trend_score", 0.30), ("same_distance_signal_score", 0.15)),
    "class_advantage": (("class_score", 0.75), ("distance_score", 0.25)),
}

HORSE_HEALTH_RISK_ONLY_FORMULAS = {
    **CURRENT_MATRIX_FORMULAS,
    "horse_health": (("risk_score", 1.00),),
}

ML_7D_WEIGHT_SHADOW = {
    "sectional": 0.1849,
    "trainer_signal": 0.2209,
    "stability": 0.0919,
    "race_shape": 0.2560,
    "class_advantage": 0.1335,
    "horse_health": 0.0378,
    "form_line": 0.0749,
}

MODEL_SPECS = {
    "previous_calibrated": {
        "formulas": PREVIOUS_MATRIX_FORMULAS,
        "weights": PREVIOUS_MATRIX_WEIGHTS,
    },
    "current_live": {
        "formulas": CURRENT_MATRIX_FORMULAS,
        "weights": CURRENT_MATRIX_WEIGHTS,
    },
    "candidate_ml_7d_weight_shadow": {
        "formulas": CURRENT_MATRIX_FORMULAS,
        "weights": ML_7D_WEIGHT_SHADOW,
    },
}


def load_published_mainline_predictions(meeting_dir: Path) -> dict[int, list[int]]:
    csv_path = meeting_dir / "HKJC_Auto_Scoring.csv"
    if not csv_path.exists():
        return {}

    by_race: dict[int, list[dict]] = defaultdict(list)
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    for row in df.to_dict(orient="records"):
        try:
            race_num = int(row.get("race_number"))
            horse_num = int(row.get("horse_number"))
        except (TypeError, ValueError):
            continue
        try:
            rank = int(float(row.get("rank", 999)))
        except (TypeError, ValueError):
            rank = 999
        try:
            ability = float(row.get("ability_score", 0.0))
        except (TypeError, ValueError):
            ability = 0.0
        by_race[race_num].append(
            {
                "rank": rank,
                "horse_num": horse_num,
                "ability": ability,
            }
        )

    predictions: dict[int, list[int]] = {}
    for race_num, rows in by_race.items():
        rows.sort(key=lambda item: (item["rank"], -item["ability"], item["horse_num"]))
        predictions[race_num] = [item["horse_num"] for item in rows[:4]]
    return predictions


OUTER_WEIGHT_GRID = {
    "sectional": [0.18, 0.20, 0.22],
    "trainer_signal": [0.16, 0.18, 0.20],
    "stability": [0.12, 0.14, 0.16],
    "race_shape": [0.24, 0.26, 0.28],
    "class_advantage": [0.08, 0.10, 0.12],
    "horse_health": [0.05, 0.07, 0.09],
    "form_line": [0.03, 0.05, 0.07],
}

STATS_ROOT = get_comprehensive_stats_root()

DEBUT_PRIOR_FILES = {
    "trainer": STATS_ROOT / "24_25" / "debut_pre_race_priors" / "trainer_uplift.csv",
    "jockey": STATS_ROOT / "24_25" / "debut_pre_race_priors" / "jockey_uplift.csv",
    "combo": STATS_ROOT / "24_25" / "debut_pre_race_priors" / "combo_edge.csv",
}


class DebutPriors:
    def __init__(self) -> None:
        self.trainer = self._load_map(DEBUT_PRIOR_FILES["trainer"], ["Trainer"])
        self.jockey = self._load_map(DEBUT_PRIOR_FILES["jockey"], ["Jockey"])
        self.combo = self._load_map(DEBUT_PRIOR_FILES["combo"], ["Jockey", "Trainer"])

    def _load_map(self, path: Path, keys: list[str]) -> dict[tuple[str, ...], dict]:
        if not path.exists():
            return {}
        df = pd.read_csv(path)
        records = {}
        for row in df.to_dict(orient="records"):
            records[tuple(str(row[key]).strip() for key in keys)] = row
        return records

    def apply(self, horse: dict, features: dict[str, float], _race_context: dict | None = None) -> dict[str, float]:
        if not (horse.get("is_debut") or horse.get("debut_runner") or horse.get("career_tag") == "DEBUT"):
            return features

        updated = deepcopy(features)
        trainer = str(horse.get("trainer") or "").strip()
        jockey = str(horse.get("jockey") or "").strip()
        trainer_row = self.trainer.get((trainer,))
        jockey_row = self.jockey.get((jockey,))
        combo_row = self.combo.get((jockey, trainer))

        trainer_adj = self._trainer_adjustment(trainer_row)
        jockey_adj = self._jockey_adjustment(jockey_row)
        combo_adj = self._combo_adjustment(combo_row)

        updated["trainer_score"] = clip_score(updated.get("trainer_score", 60) + trainer_adj + combo_adj * 0.7)
        updated["jockey_score"] = clip_score(updated.get("jockey_score", 60) + jockey_adj + combo_adj * 0.3)
        updated["confidence_score"] = clip_score(updated.get("confidence_score", 60) + self._confidence_adjustment(trainer_row, jockey_row, combo_row))
        return updated

    def _trainer_adjustment(self, row: dict | None) -> float:
        if not row or float(row.get("DebutStarts", 0)) < 60:
            return 0.0
        uplift = float(row.get("WinRateUplift", 0))
        place_uplift = float(row.get("PlaceRateUplift", 0))
        if uplift >= 2.5 or place_uplift >= 4.0:
            return 4.0
        if uplift >= 1.0 or place_uplift >= 2.0:
            return 2.0
        if uplift <= -2.0 and place_uplift <= -3.0:
            return -3.0
        return 0.0

    def _jockey_adjustment(self, row: dict | None) -> float:
        if not row or float(row.get("DebutStarts", 0)) < 70:
            return 0.0
        uplift = float(row.get("WinRateUplift", 0))
        place_uplift = float(row.get("PlaceRateUplift", 0))
        if uplift >= 1.5 or place_uplift >= 2.5:
            return 3.0
        if uplift >= 0.5 or place_uplift >= 1.0:
            return 1.5
        if uplift <= -1.5 and place_uplift <= -2.0:
            return -2.0
        return 0.0

    def _combo_adjustment(self, row: dict | None) -> float:
        if not row or float(row.get("Starts", 0)) < 18:
            return 0.0
        win_edge = float(row.get("WinEdgeVsMean", 0))
        place_edge = float(row.get("PlaceEdgeVsMean", 0))
        if win_edge >= 6.0 or place_edge >= 8.0:
            return 3.0
        if win_edge >= 3.0 or place_edge >= 4.0:
            return 1.5
        if win_edge <= -3.0 and place_edge <= -3.0:
            return -1.5
        return 0.0

    def _confidence_adjustment(self, trainer_row: dict | None, jockey_row: dict | None, combo_row: dict | None) -> float:
        hits = 0
        if trainer_row and float(trainer_row.get("DebutStarts", 0)) >= 60:
            hits += 1
        if jockey_row and float(jockey_row.get("DebutStarts", 0)) >= 70:
            hits += 1
        if combo_row and float(combo_row.get("Starts", 0)) >= 18:
            hits += 1
        if hits >= 3:
            return 3.0
        if hits == 2:
            return 2.0
        if hits == 1:
            return 1.0
        return 0.0


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
    "class_distance": [
        STATS_ROOT / "24_25" / "general_pre_race_priors" / "class_distance_priors.csv",
        STATS_ROOT / "25_26" / "general_pre_race_priors" / "class_distance_priors.csv",
    ],
    "weight_class": [
        STATS_ROOT / "24_25" / "general_pre_race_priors" / "weight_class_priors.csv",
        STATS_ROOT / "25_26" / "general_pre_race_priors" / "weight_class_priors.csv",
    ],
    "draw_bias": [
        STATS_ROOT / "24_25" / "draw_bias_stats.csv",
        STATS_ROOT / "25_26" / "draw_bias_stats.csv",
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
        grouped = (
            df.groupby(keys, dropna=False)[["Wins", "Starts", "Places"]]
            .sum()
            .reset_index()
        )
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
        records = {}
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
        distance = str((race_context or {}).get("distance") or "").replace("m", "").strip()

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

        jockey_changed = _is_jockey_changed(horse)
        if jockey_changed is True:
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
        starts = row["starts"]
        win_rate = row["win_rate"]
        place_rate = row["place_rate"]
        if starts < 80:
            return 0.0
        if win_rate >= 14.0 or place_rate >= 36.0:
            return 4.0
        if win_rate >= 11.0 or place_rate >= 30.0:
            return 2.0
        if win_rate <= 7.0 and place_rate <= 23.0:
            return -2.0
        return 0.0

    def _jockey_distance_adjustment(self, row: dict) -> float:
        starts = row["starts"]
        win_rate = row["win_rate"]
        place_rate = row["place_rate"]
        if starts < 80:
            return 0.0
        if win_rate >= 15.0 or place_rate >= 40.0:
            return 3.0
        if win_rate >= 10.0 or place_rate >= 30.0:
            return 1.5
        if win_rate <= 6.0 and place_rate <= 22.0:
            return -2.0
        return 0.0

    def _trainer_distance_adjustment(self, row: dict) -> float:
        starts = row["starts"]
        win_rate = row["win_rate"]
        place_rate = row["place_rate"]
        if starts < 80:
            return 0.0
        if win_rate >= 12.0 or place_rate >= 34.0:
            return 2.0
        if win_rate >= 9.0 or place_rate >= 28.0:
            return 1.0
        if win_rate <= 5.0 and place_rate <= 20.0:
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


class ClassDistanceWeightPriors:
    def __init__(self) -> None:
        self.class_distance = self._load_grouped(GENERAL_PRIOR_FILES["class_distance"], ["RaceClass", "Venue", "Track", "Distance"])
        self.weight_class = self._load_grouped(GENERAL_PRIOR_FILES["weight_class"], ["RaceClass", "WtBucket"])

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
        race_context = race_context or {}
        race_class = _normalize_race_class(race_context.get("race_class"))
        venue = _normalize_venue(race_context.get("venue"))
        track = _normalize_track(horse, race_context)
        distance = _normalize_distance(race_context.get("distance"))
        weight = _horse_weight_value(horse)
        weight_bucket = _weight_bucket(weight)

        distance_adj = 0.0
        class_adj = 0.0
        weight_adj = 0.0

        class_distance_row = self.class_distance.get((race_class, venue, track, distance))
        if class_distance_row and class_distance_row["starts"] >= 80:
            place_rate = class_distance_row["place_rate"]
            win_rate = class_distance_row["win_rate"]
            if place_rate >= 27.0 or win_rate >= 9.0:
                distance_adj += 3.0
                class_adj += 1.0
            elif place_rate <= 22.0 and win_rate <= 7.5:
                distance_adj -= 2.0
                class_adj -= 1.0

        weight_row = self.weight_class.get((race_class, weight_bucket))
        if weight_row and weight_row["starts"] >= 120:
            place_rate = weight_row["place_rate"]
            win_rate = weight_row["win_rate"]
            if place_rate >= 28.0 or win_rate >= 9.5:
                weight_adj += 3.0
                class_adj += 1.0
            elif place_rate <= 20.0 and win_rate <= 6.0:
                weight_adj -= 3.0
                class_adj -= 1.0

        updated["distance_score"] = clip_score(updated.get("distance_score", 60.0) + distance_adj)
        updated["class_score"] = clip_score(updated.get("class_score", 60.0) + class_adj)
        updated["weight_score"] = clip_score(updated.get("weight_score", 60.0) + weight_adj)
        return updated


class DrawHistoryPriors:
    def __init__(self, mode: str = "all") -> None:
        self.mode = mode
        self.draw_bias = self._load_grouped(GENERAL_PRIOR_FILES["draw_bias"], ["Venue", "Track", "Distance", "Draw"])
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
        race_context = race_context or {}
        draw = horse.get("barrier") or horse.get("draw")
        try:
            draw_num = int(draw)
        except (TypeError, ValueError):
            return updated

        venue = _normalize_venue(race_context.get("venue"))
        track = _normalize_track(horse, race_context)
        distance = _normalize_distance(race_context.get("distance"))
        jockey = str(horse.get("jockey") or "").strip()

        adjustment = 0.0
        draw_bias_row = self.draw_bias.get((venue, track, distance, str(draw_num)))
        if draw_bias_row and draw_bias_row["starts"] >= 60:
            if draw_bias_row["win_rate"] >= 11.0 or draw_bias_row["place_rate"] >= 30.0:
                adjustment += 3.0
            elif draw_bias_row["win_rate"] <= 4.5 and draw_bias_row["place_rate"] <= 18.0:
                adjustment -= 3.0

        jockey_draw_row = self.jockey_draw.get((jockey, str(draw_num)))
        if jockey_draw_row and jockey_draw_row["starts"] >= 40:
            if jockey_draw_row["win_rate"] >= 14.0 or jockey_draw_row["place_rate"] >= 36.0:
                adjustment += 2.0
            elif jockey_draw_row["win_rate"] <= 4.0 and jockey_draw_row["place_rate"] <= 18.0:
                adjustment -= 2.0

        horse_draw_adj = _horse_draw_history_adjustment(horse, draw_num)
        adjustment += horse_draw_adj

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


def trackwork_sectional_candidate(horse: dict, features: dict[str, float], _race_context: dict | None = None) -> dict[str, float]:
    updated = deepcopy(features)
    candidate = candidate_speed_score(horse)
    if candidate is not None:
        updated["speed_score"] = candidate
    return updated


def race_sectional_candidate(horse: dict, features: dict[str, float], race_context: dict | None = None) -> dict[str, float]:
    updated = deepcopy(features)
    candidate = candidate_race_sectional_score(horse, race_context or {})
    if candidate is not None:
        updated["speed_score"] = candidate
    return updated


def race_sectional_non_debut_candidate(horse: dict, features: dict[str, float], race_context: dict | None = None) -> dict[str, float]:
    updated = deepcopy(features)
    candidate = candidate_race_sectional_score(horse, race_context or {}, mode="non_debut")
    if candidate is not None:
        updated["speed_score"] = candidate
    return updated


def race_sectional_complete_candidate(horse: dict, features: dict[str, float], race_context: dict | None = None) -> dict[str, float]:
    updated = deepcopy(features)
    candidate = candidate_race_sectional_score(horse, race_context or {}, mode="complete_only")
    if candidate is not None:
        updated["speed_score"] = candidate
    return updated


def race_sectional_non_debut_complete_candidate(horse: dict, features: dict[str, float], race_context: dict | None = None) -> dict[str, float]:
    updated = deepcopy(features)
    candidate = candidate_race_sectional_score(horse, race_context or {}, mode="non_debut_complete")
    if candidate is not None:
        updated["speed_score"] = candidate
    return updated


def race_sectional_strong_only_candidate(horse: dict, features: dict[str, float], race_context: dict | None = None) -> dict[str, float]:
    updated = deepcopy(features)
    candidate = candidate_race_sectional_score(horse, race_context or {}, mode="strong_only")
    if candidate is not None:
        updated["speed_score"] = candidate
    return updated


def draw_context_candidate(horse: dict, features: dict[str, float], _race_context: dict | None = None) -> dict[str, float]:
    updated = deepcopy(features)
    score = candidate_draw_score(horse)
    if score is not None:
        updated["draw_score"] = score
    return updated


def draw_hkjc_anchor_candidate(horse: dict, features: dict[str, float], _race_context: dict | None = None) -> dict[str, float]:
    updated = deepcopy(features)
    score = candidate_draw_hkjc_anchor_score(horse)
    if score is not None:
        updated["draw_score"] = score
    return updated


def draw_hkjc_anchor_no_bleed_candidate(horse: dict, features: dict[str, float], race_context: dict | None = None) -> dict[str, float]:
    updated = draw_hkjc_anchor_candidate(horse, features, race_context)
    horse_clean = deepcopy(horse)
    if isinstance(horse_clean.get("_data"), dict):
        horse_clean["_data"]["draw_verdict"] = ""
    engine = RacingEngine(horse_clean, race_context or {})
    track_score, _note, _source = engine._track_going_score(updated)
    updated["track_going_score"] = clip_score(track_score)
    confidence_score, _note, _source = engine._confidence_score(updated)
    updated["confidence_score"] = clip_score(confidence_score)
    return updated


def consistency_context_candidate(horse: dict, features: dict[str, float], _race_context: dict | None = None) -> dict[str, float]:
    updated = deepcopy(features)
    score = candidate_consistency_score(horse, features)
    if score is not None:
        updated["consistency_score"] = score
    return updated


def horse_health_context_candidate(horse: dict, features: dict[str, float], _race_context: dict | None = None) -> dict[str, float]:
    updated = deepcopy(features)
    score = candidate_health_risk_score(horse)
    if score is not None:
        updated["risk_score"] = score
    return updated


def candidate_draw_score(horse: dict) -> float | None:
    draw = horse.get("barrier") or horse.get("draw")
    try:
        draw = int(draw)
    except (TypeError, ValueError):
        return None

    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}

    if draw <= 4:
        score = 75.0
    elif draw <= 8:
        score = 65.0
    else:
        score = 50.0

    fit = str(data.get("draw_position_fit") or "")
    verdict = str(data.get("draw_verdict") or "")
    trend = str(data.get("position_pi") or "")

    if "✅匹配" in fit:
        score += 5.0
    elif "❌錯配" in fit:
        score -= 9.0
    elif "偏好走外但起步在內" in fit or "偏好走內但被迫走外" in fit:
        score -= 6.0
    elif "需主動切入內疊" in fit:
        score -= 4.0

    if "✅有利" in verdict:
        score += 3.0
    elif "❌不利" in verdict:
        score -= 5.0

    if "上升軌" in trend:
        score += 2.0
    elif "微升" in trend:
        score += 1.0
    elif "微跌" in trend:
        score -= 1.0
    elif "衰退中" in trend:
        score -= 3.0

    return clip_score(score)


def candidate_draw_hkjc_anchor_score(horse: dict) -> float | None:
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    verdict = str(data.get("draw_verdict") or "")
    if not verdict:
        return None

    place_match = re.search(r"上名(\d+(?:\.\d+)?)%", verdict)
    win_match = re.search(r"勝(\d+(?:\.\d+)?)%", verdict)
    place_pct = float(place_match.group(1)) if place_match else None
    win_pct = float(win_match.group(1)) if win_match else None

    if place_pct is None and win_pct is None:
        return None

    score = 60.0
    if place_pct is not None:
        score += (place_pct - 24.0) * 1.0
    if win_pct is not None:
        score += (win_pct - 8.0) * 0.75

    if "✅有利" in verdict:
        score += 1.5
    elif "❌不利" in verdict:
        score -= 1.5

    return clip_score(score)


def candidate_speed_score(horse: dict) -> float | None:
    entries = ((horse.get("trackwork") or {}).get("entries") or [])
    best_sectional = None
    for entry in entries:
        if entry.get("type") != "gallop":
            continue
        split = _last_open_sectional(entry.get("details") or "")
        if split is None:
            split = _fallback_open_sectional(entry.get("times") or [])
        if split is None:
            continue
        if best_sectional is None or split < best_sectional:
            best_sectional = split
    if best_sectional is None:
        return None

    if best_sectional < 23.2:
        score = 78.0
    elif best_sectional < 24.4:
        score = 68.0
    elif best_sectional < 25.8:
        score = 62.0
    else:
        score = 60.0

    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    finish_time_level = str(data.get("finish_time_adj_level") or "")
    energy_trend = str(data.get("energy_trend") or "")
    l400_trend = str(data.get("l400_trend") or "")

    if "仍具競爭力" in finish_time_level:
        score += 6.0
    elif "接近平均" in finish_time_level:
        score += 2.0
    elif "仍偏慢" in finish_time_level:
        score -= 4.0
    elif "明顯落後" in finish_time_level:
        score -= 8.0

    if "上升" in energy_trend and "✅" in energy_trend:
        score += 2.0
    elif "下降" in energy_trend and "⚠️" in energy_trend:
        score -= 2.0

    if "上升" in l400_trend and "✅" in l400_trend:
        score += 2.0
    elif "衰退中" in l400_trend:
        score -= 2.0
    elif "波動" in l400_trend:
        score -= 1.0

    return clip_score(score)


def candidate_race_sectional_score(horse: dict, race_context: dict, mode: str = "all") -> float | None:
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    is_debut = bool(horse.get("is_debut") or horse.get("debut_runner") or horse.get("career_tag") == "DEBUT")
    if mode in {"non_debut", "non_debut_complete"} and is_debut:
        return None

    signals = 0
    score = 60.0
    strong_signals = 0

    raw_l400 = parse_float(data.get("raw_l400"))
    if raw_l400 is not None:
        signals += 1
        if raw_l400 <= 22.4:
            score += 8.0
            strong_signals += 1
        elif raw_l400 <= 23.0:
            score += 5.0
            strong_signals += 1
        elif raw_l400 <= 23.6:
            score += 2.0
        elif raw_l400 >= 24.6:
            score -= 5.0
            strong_signals += 1
        elif raw_l400 >= 24.0:
            score -= 2.0

    finish_time_level = str(data.get("finish_time_adj_level") or "")
    if finish_time_level:
        signals += 1
        if "仍具競爭力" in finish_time_level:
            score += 8.0
            strong_signals += 1
        elif "持續快於標準" in finish_time_level:
            score += 6.0
            strong_signals += 1
        elif "略快於標準" in finish_time_level:
            score += 4.0
        elif "接近平均" in finish_time_level:
            score += 1.0
        elif "仍偏慢" in finish_time_level:
            score -= 4.0
            strong_signals += 1
        elif "明顯落後" in finish_time_level:
            score -= 8.0
            strong_signals += 1

    energy_trend = str(data.get("energy_trend") or "")
    if energy_trend:
        signals += 1
        if "上升" in energy_trend and "✅" in energy_trend:
            score += 4.0
            strong_signals += 1
        elif "穩定" in energy_trend:
            score += 1.5
        elif "下降" in energy_trend and "⚠️" in energy_trend:
            score -= 4.0
            strong_signals += 1

    l400_trend = str(data.get("l400_trend") or "")
    if l400_trend:
        signals += 1
        if "上升" in l400_trend and "✅" in l400_trend:
            score += 3.0
            strong_signals += 1
        elif "穩定" in l400_trend:
            score += 1.5
        elif "波動" in l400_trend:
            score -= 1.0
        elif "衰退中" in l400_trend:
            score -= 4.0
            strong_signals += 1

    engine_type = str(data.get("engine_type") or "")
    if engine_type:
        signals += 1
        if "漸進加速型" in engine_type:
            score += 3.0
            strong_signals += 1
        elif "均速型" in engine_type:
            score += 1.5
        elif "混合型" in engine_type and "信心: 低" in engine_type:
            score -= 2.0
        elif "快開慢收型" in engine_type:
            score -= 2.5
            strong_signals += 1
        if "信心: 低" in engine_type:
            score -= 1.0

    distance_text = str(data.get("best_distance") or "")
    distance = _normalize_distance(race_context.get("distance"))
    if distance_text and distance:
        signals += 1
        if distance_text.startswith(f"{distance}m") or f"今仗 {distance}m =" in distance_text:
            score += 1.5
        elif "未跑過" in distance_text:
            score -= 1.5

    if mode in {"complete_only", "non_debut_complete"} and signals < 5:
        return None
    if mode == "strong_only" and (signals < 4 or strong_signals < 2):
        return None
    if signals < 2:
        return None
    return clip_score(score)


def candidate_consistency_score(horse: dict, features: dict[str, float]) -> float | None:
    if horse.get("is_debut") or horse.get("debut_runner") or horse.get("career_tag") == "DEBUT":
        return None

    detail = str(((horse.get("_data") or {}).get("recent_6_detail")) or "")
    runs = _parse_recent_runs(detail)
    if not runs:
        return None

    weights = [1.00, 0.85, 0.70, 0.55, 0.45, 0.35]
    weighted_total = sum(weights[: len(runs)])
    close_credit = 0.0
    poor_debit = 0.0
    severe_debit = 0.0

    for idx, run in enumerate(runs[:6]):
        weight = weights[idx]
        rank = run["rank"]
        margin = run["margin"]

        if rank <= 3:
            close_credit += weight
            continue
        if rank <= 5 and margin is not None and margin <= 3.0:
            close_credit += weight * 0.75
        elif rank <= 7 and margin is not None and margin <= 2.5:
            close_credit += weight * 0.40

        if rank >= 8 and margin is not None and margin >= 5.0:
            poor_debit += weight
        elif rank >= 6 and margin is not None and margin >= 7.0:
            poor_debit += weight * 0.70

        if rank >= 10 and margin is not None and margin >= 8.0:
            severe_debit += weight

    close_ratio = close_credit / weighted_total if weighted_total else 0.0
    poor_ratio = poor_debit / weighted_total if weighted_total else 0.0
    severe_ratio = severe_debit / weighted_total if weighted_total else 0.0

    score = 58.0 + close_ratio * 18.0 - poor_ratio * 14.0 - severe_ratio * 10.0

    margin_trend = str(((horse.get("_data") or {}).get("margin_trend")) or "")
    if "收窄中" in margin_trend:
        score += 4.0
    elif "擴大中" in margin_trend:
        score -= 4.0
    elif "波動" in margin_trend:
        score -= 1.0

    finish_positions = [run["rank"] for run in runs[:6]]
    if len(finish_positions) >= 5:
        recent_avg = sum(finish_positions[:3]) / 3.0
        older_avg = sum(finish_positions[3:6]) / 3.0
        if recent_avg + 1.0 < older_avg:
            score += 3.0
        elif recent_avg > older_avg + 1.0:
            score -= 3.0

    return clip_score(score)


def candidate_health_risk_score(horse: dict) -> float | None:
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    score = 68.0

    medical = str(data.get("medical_flags") or "")
    if "✅ 無醫療事故記錄" in medical:
        score += 2.0
    elif medical and medical != "N/A":
        score -= 12.0
        if _has_recovery_evidence(horse):
            score += 6.0
    else:
        score -= 5.0

    days = parse_float(horse.get("days_since_last") or data.get("days_since_last"))
    weight_trend = str(data.get("weight_trend") or "")
    weight_span = _weight_trend_span(weight_trend)

    if days is not None:
        if days <= 7:
            score += 2.0 if (weight_span is not None and weight_span <= 14.0) else -1.0
        elif days <= 21:
            score += 2.0
        elif days <= 45:
            score += 1.0
        elif days <= 75:
            score += 0.0
        else:
            score -= 3.0

    if "急劇變化" in weight_trend:
        score -= 5.0
    elif "顯著轉輕" in weight_trend:
        score -= 3.0
    elif "顯著轉重" in weight_trend:
        score -= 2.0
    elif "微增" in weight_trend or "微減" in weight_trend:
        score += 1.0

    if weight_span is not None:
        if weight_span <= 12.0:
            score += 3.0
        elif weight_span <= 18.0:
            score += 1.5
        elif weight_span <= 24.0:
            score += 0.0
        elif weight_span <= 32.0:
            score -= 2.0
        else:
            score -= 4.0

    trackwork_health = str(data.get("trackwork_health") or "")
    if "操練放緩" in trackwork_health:
        score -= 1.5
    elif "risk_flags=[]" in trackwork_health or "risk_flags: []" in trackwork_health:
        score += 0.5

    if "swimming=0" in trackwork_health and days is not None and days <= 21:
        score -= 1.0
    if "blank_days=3" in trackwork_health or "blank_days=4" in trackwork_health:
        score -= 0.5

    return clip_score(score)


def _weight_trend_span(weight_trend: str) -> float | None:
    match = re.search(r"波幅(\d+(?:\.\d+)?)lb", weight_trend)
    if match:
        return float(match.group(1))
    return None


def _has_recovery_evidence(horse: dict) -> bool:
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    finishes = [int(item) for item in re.findall(r"\b\d+\b", str(horse.get("last_6_finishes") or ""))[:3]]
    if any(rank <= 3 for rank in finishes):
        return True
    finish_time_level = str(data.get("finish_time_adj_level") or "")
    if "仍具競爭力" in finish_time_level or "持續快於標準" in finish_time_level:
        return True
    raw_l400 = parse_float(data.get("raw_l400"))
    if raw_l400 is not None and raw_l400 <= 23.4:
        return True
    return False


def _parse_recent_runs(detail: str) -> list[dict[str, float | int | None]]:
    runs: list[dict[str, float | int | None]] = []
    for rank_text, margin_text in re.findall(r":\s*(\d+)名\s+([^|,]+)", str(detail or "")):
        try:
            rank = int(rank_text)
        except ValueError:
            continue
        runs.append({
            "rank": rank,
            "margin": _margin_to_float(margin_text.strip()),
        })
    return runs


def _margin_to_float(value: str) -> float | None:
    text = str(value or "").strip()
    if not text or text in {"-", "--", "N/A"}:
        return None
    if "平頭馬" in text:
        return 0.0
    if "短馬頭位" in text:
        return 0.05
    if "頭位" in text:
        return 0.1
    if "頸位" in text:
        return 0.25
    if "多個馬位" in text:
        return 8.0

    total = 0.0
    matched = False
    for part in text.split("-"):
        part = part.strip()
        if not part:
            continue
        if "/" in part:
            numerator, denominator = part.split("/", 1)
            try:
                total += float(numerator) / float(denominator)
                matched = True
            except ValueError:
                continue
            continue
        try:
            total += float(part)
            matched = True
        except ValueError:
            continue
    if matched:
        return total
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
        if not jockey_name:
            continue
        return jockey_name != current_jockey
    return None


def _normalize_race_class(value: object) -> str:
    text = str(value or "").strip().upper()
    mapping = {
        "C5": "Class 5",
        "C4": "Class 4",
        "C3": "Class 3",
        "C2": "Class 2",
        "C1": "Class 1",
        "CLASS 5": "Class 5",
        "CLASS 4": "Class 4",
        "CLASS 3": "Class 3",
        "CLASS 2": "Class 2",
        "CLASS 1": "Class 1",
    }
    return mapping.get(text, text.title() if text else "Unknown")


def _normalize_venue(value: object) -> str:
    text = str(value or "").strip()
    if text in {"", "Unknown"}:
        return "跑馬地" if "HappyValley" in str(value or "") else "沙田" if "ShaTin" in str(value or "") else "跑馬地"
    if text in {"HV", "Happy Valley", "跑馬地"}:
        return "跑馬地"
    if text in {"ST", "Sha Tin", "沙田"}:
        return "沙田"
    return text


def _normalize_track(horse: dict, race_context: dict) -> str:
    text = str(race_context.get("surface") or race_context.get("track") or "").strip().upper()
    if text in {"AWT", "AW", "ALL WEATHER", "DIRT"}:
        return "AWT"
    return "Turf"


def _normalize_distance(value: object) -> str:
    return str(value or "").replace("m", "").strip()


def _horse_weight_value(horse: dict) -> float | None:
    value = horse.get("_data", {}).get("weight_carried") if isinstance(horse.get("_data"), dict) else None
    if value is None:
        value = horse.get("weight")
    return parse_float(value)


def _weight_bucket(weight: float | None) -> str:
    if weight is None:
        return "Medium (121-126)"
    if weight <= 115:
        return "Light (<=115)"
    if weight <= 120:
        return "Med-Light (116-120)"
    if weight <= 126:
        return "Medium (121-126)"
    if weight <= 130:
        return "Med-Heavy (127-130)"
    return "Heavy (131+)"


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


def _tie_break_draw_bonus(horse: dict, race_context: dict, features: dict[str, float]) -> float:
    bonus = 0.0
    draw = horse.get("barrier") or horse.get("draw")
    try:
        draw_num = int(draw)
    except (TypeError, ValueError):
        return 0.0

    fit = str(((horse.get("_data") or {}).get("draw_position_fit")) or "")
    trend = str(((horse.get("_data") or {}).get("position_pi")) or "")
    verdict = str(((horse.get("_data") or {}).get("draw_verdict")) or "")

    if "✅匹配" in fit:
        bonus += 1.5
    elif "❌錯配" in fit:
        bonus -= 2.0
    elif "偏好走外但起步在內" in fit or "偏好走內但被迫走外" in fit:
        bonus -= 1.5
    elif "需主動切入內疊" in fit:
        bonus -= 1.0

    if "上升軌" in trend:
        bonus += 0.8
    elif "衰退中" in trend:
        bonus -= 0.8

    if "✅有利" in verdict:
        bonus += 0.7
    elif "❌不利" in verdict:
        bonus -= 0.7

    bonus += _horse_draw_history_adjustment(horse, draw_num) * 0.5

    venue = _normalize_venue(race_context.get("venue"))
    distance = _normalize_distance(race_context.get("distance"))
    if venue == "跑馬地" and distance == "1650":
        if draw_num in {1, 2, 3, 7, 8}:
            bonus += 0.5
        if draw_num in {11, 12}:
            bonus -= 0.5

    if clip_score(features.get("draw_score", 60.0)) <= 55.0:
        bonus *= 1.15
    return bonus


def _compact_horse_for_archive_review(horse: dict) -> dict:
    """Keep only fields used after per-horse candidate scoring is complete.

    Archived Logic horses can contain large form, trackwork and narrative
    payloads.  Retaining every payload for every race made routine reflector
    archive reviews consume unnecessary memory and could terminate before the
    meeting report was written.  Draw tie-break diagnostics only need this
    small immutable snapshot.
    """
    data = horse.get("_data") or {}
    return {
        "barrier": horse.get("barrier"),
        "draw": horse.get("draw"),
        "_data": {
            "draw_position_fit": data.get("draw_position_fit"),
            "position_pi": data.get("position_pi"),
            "draw_verdict": data.get("draw_verdict"),
        },
    }


def _last_open_sectional(details: str) -> float | None:
    text = str(details or "")
    without_paren = re.sub(r"\([^)]*\)", " ", text)
    values = [float(m.group(1)) for m in re.finditer(r"(?<!\d)(\d{2,3}\.\d)(?!\d)", without_paren)]
    valid = [value for value in values if 20.0 <= value <= 40.0]
    if valid:
        return valid[-1]
    return None


def _fallback_open_sectional(values: list[float]) -> float | None:
    valid = [float(value) for value in values if 20.0 <= float(value) <= 40.0]
    if not valid:
        return None
    if len(valid) >= 2 and valid[-1] < valid[-2] - 3.0:
        return valid[-2]
    return valid[-1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review HKJC Auto weighting using archived logic + actual results")
    parser.add_argument(
        "--meeting-root",
        action="append",
        default=[],
        help="Root folder to scan for HKJC meeting directories. Can be repeated.",
    )
    parser.add_argument(
        "--results-root",
        action="append",
        default=[],
        help="Root folder containing YYYY-MM-DD/full_day_results.json. Can be repeated.",
    )
    parser.add_argument(
        "--season-csv",
        action="append",
        default=[],
        help="Season results CSV to include in trend review. Can be repeated.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown text")
    return parser.parse_args()


def default_meeting_roots() -> list[Path]:
    return [
        get_analysis_archive_root(),
        ROOT,
    ]


def default_results_roots() -> list[Path]:
    return get_season_results_roots() + [get_analysis_archive_root()]


def default_season_csvs() -> list[Path]:
    return get_season_csvs()


def hk_meeting_dirs(roots: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    meetings: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("Race_*_Logic.json"):
            meeting_dir = path.parent
            name = meeting_dir.name
            if "ShaTin" not in name and "HappyValley" not in name:
                continue
            if meeting_dir in seen:
                continue
            seen.add(meeting_dir)
            meetings.append(meeting_dir)
    return sorted(meetings)


def build_results_index(results_roots: list[Path]) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for root in results_roots:
        if not root.exists():
            continue
        for pattern in ("full_day_results.json", "*全日賽果.json"):
            for path in root.rglob(pattern):
                date_dir = path.parent.name
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_dir):
                    index.setdefault(date_dir, path)
                    continue
                match = re.match(r"(\d{4}-\d{2}-\d{2})", path.parent.name)
                if match:
                    index.setdefault(match.group(1), path)
    return index


def meeting_date(meeting_dir: Path) -> str | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", meeting_dir.name)
    return match.group(1) if match else None


def venue_from_meeting_dir(meeting_dir: Path) -> str:
    name = meeting_dir.name
    if "HappyValley" in name:
        return "跑馬地"
    if "ShaTin" in name:
        return "沙田"
    return "Unknown"


def dedup_race_key(date: str | None, venue: str, race_num: int) -> tuple[str | None, str, int]:
    return (date, _normalize_venue(venue), race_num)


def load_results(path: Path) -> dict[int, dict[int, int]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    results: dict[int, dict[int, int]] = {}
    for race_key, race_data in data.items():
        try:
            race_num = int(str(race_key).replace("Race_", "").replace("Race ", ""))
        except ValueError:
            continue
        positions: dict[int, int] = {}
        for row in race_data.get("results", []):
            try:
                positions[int(row["horse_no"])] = int(row["pos"])
            except (KeyError, TypeError, ValueError):
                continue
        if positions:
            results[race_num] = positions
    return results


def race_num_from_path(path: Path) -> int:
    match = re.search(r"Race_(\d+)_Logic\.json$", path.name)
    return int(match.group(1)) if match else 0


def compute_full_feature_scores(horse: dict, race_context: dict) -> dict[str, float]:
    engine = RacingEngine(horse, race_context)
    feature_scores: dict[str, float] = {}

    for name, scorer_class in {
        "jockey_score": JockeyScorer,
        "trainer_score": TrainerScorer,
        "draw_score": DrawScorer,
        "form_score": FormScorer,
        "speed_score": SpeedScorer,
    }.items():
        score, _note = scorer_class(horse, race_context).compute()
        feature_scores[name] = clip_score(score)

    for name, func in {
        "class_score": engine._class_score,
        "distance_score": engine._distance_score,
        "track_going_score": engine._track_going_score,
        "weight_score": engine._weight_score,
        "consistency_score": engine._consistency_score,
        "risk_score": engine._risk_score,
        "confidence_score": engine._confidence_score,
    }.items():
        score, _note, _source = func(feature_scores)
        feature_scores[name] = clip_score(score)

    derived = {
        "formline_strength_score": engine._formline_strength_score(),
        "margin_trend_score": engine._margin_trend_score(),
        "same_distance_signal_score": engine._same_distance_signal_score(),
        "trackwork_trend_score": engine._trackwork_trend_score(),
    }
    for name, (score, _note, _source) in derived.items():
        feature_scores[name] = clip_score(score)

    for key in FEATURE_KEYS:
        feature_scores[key] = clip_score(feature_scores.get(key, 60))

    feature_scores, _notes, _sources = engine._apply_mainline_context(feature_scores, {})
    return {key: clip_score(feature_scores.get(key, 60)) for key in feature_scores}


def compute_matrix_scores(features: dict[str, float], formulas: dict[str, tuple[tuple[str, float], ...]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for key, components in formulas.items():
        scores[key] = round(sum(clip_score(features.get(name, 60)) * weight for name, weight in components), 4)
    return scores


def compute_ability(matrix_scores: dict[str, float], weights: dict[str, float]) -> float:
    return round(sum(matrix_scores[key] * weight for key, weight in weights.items()), 4)


def evaluate_model(scored: list[dict], actual_pos: dict[int, int], model_key: str) -> dict:
    ranked = sorted(
        scored,
        key=lambda item: (
            item["models"][model_key].get("rank_score", item["models"][model_key]["ability"]),
            item["models"][model_key]["ability"],
        ),
        reverse=True,
    )
    picks = [item["horse_num"] for item in ranked[:4]]
    actual_top3 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:3]]
    actual_top4 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:4]]
    actual_top3_set = set(actual_top3)
    hits = sum(1 for horse in picks[:3] if horse in actual_top3_set)
    winner = actual_top3[0] if actual_top3 else None
    winner_rank = next((idx for idx, row in enumerate(ranked, start=1) if row["horse_num"] == winner), len(ranked) + 1)
    pick1_finish = actual_pos.get(picks[0], 99) if picks else 99
    top4_hits = sum(1 for horse in picks if horse in set(actual_top4))
    order_issue = False
    if len(picks) >= 4:
        order_issue = min(actual_pos.get(picks[2], 99), actual_pos.get(picks[3], 99)) < min(
            actual_pos.get(picks[0], 99), actual_pos.get(picks[1], 99)
        )
    return {
        "picks": picks,
        "gold": hits == 3,
        "good": len(picks) >= 2 and picks[0] in actual_top3_set and picks[1] in actual_top3_set,
        "min_threshold": hits >= 2,
        "single": hits >= 1,
        "champion": bool(picks and picks[0] == winner),
        "top3_has_champion": bool(winner in set(picks[:3])),
        "winner_rank": winner_rank,
        "mrr": 1.0 / winner_rank if winner_rank > 0 else 0.0,
        "pick1_finish": pick1_finish,
        "top4_hits": top4_hits,
        "order_issue": order_issue,
    }


def evaluate_pick_order(picks: list[int], actual_pos: dict[int, int]) -> dict:
    actual_top3 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:3]]
    actual_top4 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:4]]
    actual_top3_set = set(actual_top3)
    winner = actual_top3[0] if actual_top3 else None
    hits = sum(1 for horse in picks[:3] if horse in actual_top3_set)
    winner_rank = next((idx for idx, horse in enumerate(picks, start=1) if horse == winner), len(actual_pos) + 1)
    pick1_finish = actual_pos.get(picks[0], 99) if picks else 99
    top4_hits = sum(1 for horse in picks[:4] if horse in set(actual_top4))
    order_issue = False
    if len(picks) >= 4:
        order_issue = min(actual_pos.get(picks[2], 99), actual_pos.get(picks[3], 99)) < min(
            actual_pos.get(picks[0], 99), actual_pos.get(picks[1], 99)
        )
    return {
        "picks": picks[:4],
        "gold": hits == 3,
        "good": len(picks) >= 2 and picks[0] in actual_top3_set and picks[1] in actual_top3_set,
        "min_threshold": hits >= 2,
        "single": hits >= 1,
        "champion": bool(picks and picks[0] == winner),
        "top3_has_champion": bool(winner in set(picks[:3])),
        "winner_rank": winner_rank,
        "mrr": 1.0 / winner_rank if winner_rank > 0 else 0.0,
        "pick1_finish": pick1_finish,
        "top4_hits": top4_hits,
        "order_issue": order_issue,
    }


def summarize_model_races(model_races: list[dict]) -> dict:
    total = len(model_races)
    if total == 0:
        return {}
    return {
        "races": total,
        "gold": sum(item["gold"] for item in model_races),
        "good": sum(item["good"] for item in model_races),
        "min_threshold": sum(item["min_threshold"] for item in model_races),
        "single": sum(item["single"] for item in model_races),
        "champion": sum(item["champion"] for item in model_races),
        "top3_has_champion": sum(item["top3_has_champion"] for item in model_races),
        "order_issue": sum(item["order_issue"] for item in model_races),
        "avg_winner_rank": round(sum(item["winner_rank"] for item in model_races) / total, 3),
        "mrr": round(sum(item["mrr"] for item in model_races) / total, 4),
        "avg_pick1_finish": round(sum(item["pick1_finish"] for item in model_races) / total, 3),
        "avg_top4_hits": round(sum(item["top4_hits"] for item in model_races) / total, 3),
    }


def candidate_outer_weight_sets() -> list[dict[str, float]]:
    keys = list(OUTER_WEIGHT_GRID.keys())
    candidates: list[dict[str, float]] = []
    for values in product(*(OUTER_WEIGHT_GRID[key] for key in keys)):
        weights = {key: round(value, 2) for key, value in zip(keys, values)}
        if abs(sum(weights.values()) - 1.0) > 1e-9:
            continue
        if not (weights["race_shape"] >= weights["trainer_signal"] >= weights["class_advantage"]):
            continue
        if weights["race_shape"] < weights["sectional"]:
            continue
        if weights["form_line"] > weights["horse_health"]:
            continue
        if weights["stability"] < 0.12 or weights["trainer_signal"] < 0.16:
            continue
        candidates.append(weights)
    return candidates


def score_weight_candidate(all_races: list[dict], weights: dict[str, float]) -> dict:
    model_races = []
    for race in all_races:
        actual_pos = race["actual_pos"]
        scored = []
        for horse in race["horses"]:
            matrix_scores = horse["models"]["current_live"]["matrix_scores"]
            scored.append({
                "horse_num": horse["horse_num"],
                "ability": compute_ability(matrix_scores, weights),
            })
        ranked = sorted(scored, key=lambda item: item["ability"], reverse=True)
        picks = [item["horse_num"] for item in ranked[:4]]
        actual_top3 = [horse_num for horse_num, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:3]]
        actual_top4 = [horse_num for horse_num, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:4]]
        actual_top3_set = set(actual_top3)
        hits = sum(1 for horse_num in picks[:3] if horse_num in actual_top3_set)
        winner = actual_top3[0] if actual_top3 else None
        winner_rank = next((idx for idx, row in enumerate(ranked, start=1) if row["horse_num"] == winner), len(ranked) + 1)
        pick1_finish = actual_pos.get(picks[0], 99) if picks else 99
        top4_hits = sum(1 for horse_num in picks if horse_num in set(actual_top4))
        order_issue = False
        if len(picks) >= 4:
            order_issue = min(actual_pos.get(picks[2], 99), actual_pos.get(picks[3], 99)) < min(
                actual_pos.get(picks[0], 99), actual_pos.get(picks[1], 99)
            )
        model_races.append({
            "gold": hits == 3,
            "good": len(picks) >= 2 and picks[0] in actual_top3_set and picks[1] in actual_top3_set,
            "min_threshold": hits >= 2,
            "single": hits >= 1,
            "champion": bool(picks and picks[0] == winner),
            "top3_has_champion": bool(winner in set(picks[:3])),
            "winner_rank": winner_rank,
            "mrr": 1.0 / winner_rank if winner_rank > 0 else 0.0,
            "pick1_finish": pick1_finish,
            "top4_hits": top4_hits,
            "order_issue": order_issue,
        })
    return summarize_model_races(model_races)


def pick_best_outer_weight_candidate(all_races: list[dict]) -> tuple[dict[str, float] | None, dict | None]:
    best_weights = None
    best_stats = None
    baseline = summarize_model_races([race["models"]["current_live"] for race in all_races])
    for weights in candidate_outer_weight_sets():
        stats = score_weight_candidate(all_races, weights)
        if not stats:
            continue
        if best_stats is None:
            best_weights, best_stats = weights, stats
            continue
        current_tuple = (
            stats["champion"],
            stats["min_threshold"],
            stats["mrr"],
            stats["top3_has_champion"],
            -stats["avg_pick1_finish"],
        )
        best_tuple = (
            best_stats["champion"],
            best_stats["min_threshold"],
            best_stats["mrr"],
            best_stats["top3_has_champion"],
            -best_stats["avg_pick1_finish"],
        )
        if current_tuple > best_tuple:
            best_weights, best_stats = weights, stats
    if best_stats == baseline:
        return None, None
    return best_weights, best_stats


def summarize_outer_weight_subset(all_races: list[dict], weights: dict[str, float], only_debut: bool = False) -> dict:
    subset = [race for race in all_races if (race["has_debut"] if only_debut else True)]
    if not subset:
        return {}
    return score_weight_candidate(subset, weights)


def apply_draw_tiebreak(scored: list[dict], race_context: dict, model_key: str) -> list[dict]:
    rows = []
    if not scored:
        return rows
    abilities = sorted((item["models"][model_key]["ability"] for item in scored), reverse=True)
    threshold = 1.5
    for item in scored:
        ability = item["models"][model_key]["ability"]
        near_pack = sum(1 for other in abilities if abs(other - ability) <= threshold)
        rank_score = ability
        if near_pack >= 2:
            rank_score += _tie_break_draw_bonus(item["horse"], race_context, item["feature_scores"])
        clone = dict(item)
        clone_models = dict(clone["models"])
        clone_model = dict(clone_models[model_key])
        clone_model["rank_score"] = round(rank_score, 4)
        clone_models[model_key] = clone_model
        clone["models"] = clone_models
        rows.append(clone)
    return rows


def apply_draw_micro_tiebreak(scored: list[dict], race_context: dict, model_key: str) -> list[dict]:
    rows = []
    if not scored:
        return rows
    base_ranked = sorted(scored, key=lambda item: item["models"][model_key]["ability"], reverse=True)
    boosts: dict[int, float] = {}
    if len(base_ranked) >= 4:
        third = base_ranked[2]
        fourth = base_ranked[3]
        third_ability = third["models"][model_key]["ability"]
        fourth_ability = fourth["models"][model_key]["ability"]
        if abs(third_ability - fourth_ability) <= 0.8:
            boosts[third["horse_num"]] = _tie_break_draw_bonus(third["horse"], race_context, third["feature_scores"])
            boosts[fourth["horse_num"]] = _tie_break_draw_bonus(fourth["horse"], race_context, fourth["feature_scores"])
    for item in scored:
        ability = item["models"][model_key]["ability"]
        rank_score = ability + boosts.get(item["horse_num"], 0.0)
        clone = dict(item)
        clone_models = dict(clone["models"])
        clone_model = dict(clone_models[model_key])
        clone_model["rank_score"] = round(rank_score, 4)
        clone_models[model_key] = clone_model
        clone["models"] = clone_models
        rows.append(clone)
    return rows


def _form_micro_bonus(features: dict[str, float]) -> float:
    return clip_score(features.get("form_score", 60.0)) / 100.0


def apply_top2_safety_swap(
    scored: list[dict],
    race_context: dict,
    model_key: str,
    *,
    max_gap: float = 0.35,
    min_edge: float = 0.2,
    shift: float = 0.2,
) -> list[dict]:
    rows = []
    if not scored:
        return rows
    ranked = sorted(
        scored,
        key=lambda item: (
            -item["models"][model_key].get("rank_score", item["models"][model_key]["ability"]),
            -item["models"][model_key]["ability"],
            item["horse_num"],
        ),
    )
    boosts: dict[int, float] = {}
    if len(ranked) >= 3:
        second = ranked[1]
        third = ranked[2]
        second_score = float(second["models"][model_key].get("rank_score", second["models"][model_key]["ability"]))
        third_score = float(third["models"][model_key].get("rank_score", third["models"][model_key]["ability"]))
        if second_score - third_score <= max_gap:
            second_edge = _tie_break_draw_bonus(second["horse"], race_context, second["feature_scores"]) + _form_micro_bonus(second["feature_scores"])
            third_edge = _tie_break_draw_bonus(third["horse"], race_context, third["feature_scores"]) + _form_micro_bonus(third["feature_scores"])
            if third_edge - second_edge >= min_edge:
                boosts[second["horse_num"]] = -shift
                boosts[third["horse_num"]] = shift
    for item in scored:
        rank_score = float(item["models"][model_key].get("rank_score", item["models"][model_key]["ability"])) + boosts.get(item["horse_num"], 0.0)
        clone = dict(item)
        clone_models = dict(clone["models"])
        clone_model = dict(clone_models[model_key])
        clone_model["rank_score"] = round(rank_score, 4)
        clone_models[model_key] = clone_model
        clone["models"] = clone_models
        rows.append(clone)
    return rows


def apply_live_rank_ordering(scored: list[dict], race_context: dict, model_key: str) -> list[dict]:
    rows = apply_draw_micro_tiebreak(scored, race_context, model_key)
    return apply_top2_safety_swap(rows, race_context, model_key)


def _race_shape_score(item: dict, model_key: str) -> float:
    return float(item["models"][model_key]["matrix_scores"].get("race_shape", 0.0))


def _is_hv_middle_distance(race_context: dict) -> bool:
    venue = _normalize_venue(race_context.get("venue"))
    distance = _normalize_distance(race_context.get("distance"))
    return venue == "跑馬地" and distance in {"1650", "1800"}


def apply_draw_micro_tiebreak_constrained(
    scored: list[dict],
    race_context: dict,
    model_key: str,
    *,
    hv_only: bool = False,
    min_race_shape: float | None = None,
    max_gap: float = 0.8,
    min_bonus_edge: float = 0.0,
) -> list[dict]:
    rows = []
    if not scored:
        return rows
    base_ranked = sorted(scored, key=lambda item: item["models"][model_key]["ability"], reverse=True)
    boosts: dict[int, float] = {}
    if len(base_ranked) >= 4:
        third = base_ranked[2]
        fourth = base_ranked[3]
        third_ability = third["models"][model_key]["ability"]
        fourth_ability = fourth["models"][model_key]["ability"]
        race_shape_ok = True
        if min_race_shape is not None:
            race_shape_ok = min(_race_shape_score(third, model_key), _race_shape_score(fourth, model_key)) >= min_race_shape
        venue_ok = True
        if hv_only:
            venue_ok = _is_hv_middle_distance(race_context)
        if abs(third_ability - fourth_ability) <= max_gap and race_shape_ok and venue_ok:
            third_bonus = _tie_break_draw_bonus(third["horse"], race_context, third["feature_scores"])
            fourth_bonus = _tie_break_draw_bonus(fourth["horse"], race_context, fourth["feature_scores"])
            if abs(third_bonus - fourth_bonus) >= min_bonus_edge:
                boosts[third["horse_num"]] = third_bonus
                boosts[fourth["horse_num"]] = fourth_bonus
    for item in scored:
        ability = item["models"][model_key]["ability"]
        rank_score = ability + boosts.get(item["horse_num"], 0.0)
        clone = dict(item)
        clone_models = dict(clone["models"])
        clone_model = dict(clone_models[model_key])
        clone_model["rank_score"] = round(rank_score, 4)
        clone_models[model_key] = clone_model
        clone["models"] = clone_models
        rows.append(clone)
    return rows


def matrix_diagnostics(rows: list[dict]) -> dict[str, dict]:
    per_matrix: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for race in rows:
        horses = race["horses"]
        actual = race["actual_pos"]
        actual_sorted = sorted(actual.items(), key=lambda item: item[1])
        if not actual_sorted:
            continue
        winner = actual_sorted[0][0]
        for matrix_name in CURRENT_MATRIX_FORMULAS:
            ranked = sorted(horses, key=lambda item: item["models"]["current_live"]["matrix_scores"][matrix_name], reverse=True)
            winner_rank = next((idx for idx, row in enumerate(ranked, start=1) if row["horse_num"] == winner), len(ranked) + 1)
            top_pick = ranked[0]["horse_num"] if ranked else None
            top_pick_finish = actual.get(top_pick, 99)
            winner_score = next(
                row["models"]["current_live"]["matrix_scores"][matrix_name]
                for row in horses
                if row["horse_num"] == winner
            )
            field_mean = sum(row["models"]["current_live"]["matrix_scores"][matrix_name] for row in horses) / len(horses)
            per_matrix[matrix_name]["winner_rank"].append(float(winner_rank))
            per_matrix[matrix_name]["winner_score_edge"].append(float(winner_score - field_mean))
            per_matrix[matrix_name]["top_pick_win"].append(1.0 if top_pick_finish == 1 else 0.0)
            per_matrix[matrix_name]["top_pick_top3"].append(1.0 if top_pick_finish <= 3 else 0.0)
    summary: dict[str, dict] = {}
    for matrix_name, stats in per_matrix.items():
        count = len(stats["winner_rank"])
        if count == 0:
            continue
        summary[matrix_name] = {
            "races": count,
            "avg_winner_rank": round(sum(stats["winner_rank"]) / count, 3),
            "avg_winner_score_edge": round(sum(stats["winner_score_edge"]) / count, 3),
            "top_pick_win_rate": round(sum(stats["top_pick_win"]) / count, 4),
            "top_pick_top3_rate": round(sum(stats["top_pick_top3"]) / count, 4),
        }
    return summary


def slice_hv_middle_distance(race: dict) -> bool:
    return _is_hv_middle_distance(race["race_context"])


def slice_hv_middle_distance_shape60(race: dict) -> bool:
    if not slice_hv_middle_distance(race):
        return False
    ranked = sorted(race["horses"], key=lambda item: item["models"]["current_live"]["ability"], reverse=True)
    if len(ranked) < 4:
        return False
    return min(_race_shape_score(ranked[2], "current_live"), _race_shape_score(ranked[3], "current_live")) >= 60.0


def summarize_slice(all_races: list[dict], model_names: list[str], predicate) -> dict[str, dict]:
    subset = [race for race in all_races if predicate(race)]
    summary = {
        model_name: summarize_model_races([race["models"][model_name] for race in subset])
        for model_name in model_names
    }
    return {
        "races": len(subset),
        "models": {name: stats for name, stats in summary.items() if stats},
    }


def summarize_models_for_races(races: list[dict], model_names: list[str]) -> dict[str, dict]:
    return {
        model_name: summarize_model_races([race["models"][model_name] for race in races])
        for model_name in model_names
        if races and model_name in races[0]["models"]
    }


def summarize_meeting_models(
    all_races: list[dict],
    model_names: list[str],
    best_outer_weights: dict[str, float] | None = None,
) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for race in all_races:
        grouped[Path(race["meeting"]).name].append(race)

    payload: dict[str, dict] = {}
    for meeting_name, meeting_races in sorted(grouped.items()):
        meeting_models = summarize_models_for_races(meeting_races, model_names)
        if best_outer_weights:
            outer_summary = score_weight_candidate(meeting_races, best_outer_weights)
            if outer_summary:
                meeting_models["candidate_outer_weights_retune"] = outer_summary
        payload[meeting_name] = {
            "meeting_dir": meeting_races[0]["meeting"],
            "date": meeting_races[0]["date"],
            "venue": _normalize_venue(meeting_races[0]["race_context"].get("venue")),
            "races": len(meeting_races),
            "models": {name: stats for name, stats in meeting_models.items() if stats},
        }
    return payload


def review_season_trends(csv_paths: list[Path]) -> dict:
    frames = [pd.read_csv(path) for path in csv_paths if path.exists()]
    if not frames:
        return {}
    df = pd.concat(frames, ignore_index=True)
    df["VenueDistance"] = df["Venue"].astype(str) + "_" + df["Distance"].astype(str)
    win_rates = (
        df.groupby(["Venue", "Distance", "Draw"])["Win"].mean().reset_index().sort_values(["Venue", "Distance", "Draw"])
    )
    draw_spread = (
        win_rates.groupby(["Venue", "Distance"])["Win"].agg(["max", "min", "mean"]).reset_index().sort_values("max", ascending=False)
    )
    draw_spread["spread"] = (draw_spread["max"] - draw_spread["min"]).round(4)

    trainer_distance = (
        df.groupby(["Trainer", "Distance"])
        .agg(starts=("Win", "size"), win_rate=("Win", "mean"), place_rate=("Place", "mean"))
        .reset_index()
    )
    trainer_distance = trainer_distance[trainer_distance["starts"] >= 18].sort_values("win_rate", ascending=False).head(12)

    jockey_distance = (
        df.groupby(["Jockey", "Distance"])
        .agg(starts=("Win", "size"), win_rate=("Win", "mean"), place_rate=("Place", "mean"))
        .reset_index()
    )
    jockey_distance = jockey_distance[jockey_distance["starts"] >= 18].sort_values("win_rate", ascending=False).head(12)

    weight_bucket = (
        df.groupby("WtBucket")
        .agg(starts=("Win", "size"), win_rate=("Win", "mean"), place_rate=("Place", "mean"))
        .reset_index()
        .sort_values("win_rate", ascending=False)
    )

    return {
        "rows": len(df),
        "draw_spread_top": draw_spread.head(10).to_dict(orient="records"),
        "trainer_distance_top": trainer_distance.to_dict(orient="records"),
        "jockey_distance_top": jockey_distance.to_dict(orient="records"),
        "weight_bucket": weight_bucket.to_dict(orient="records"),
    }


def run_review(
    meeting_roots: list[Path],
    results_roots: list[Path],
    season_csvs: list[Path],
    include_races: bool = False,
    routine: bool = False,
) -> dict:
    debut_priors = DebutPriors()
    trainer_signal_priors = TrainerSignalPriors()
    class_distance_weight_priors = ClassDistanceWeightPriors()
    draw_history_priors = DrawHistoryPriors("all")
    draw_history_debut_priors = DrawHistoryPriors("debut_only")
    draw_history_low_confidence_priors = DrawHistoryPriors("low_confidence_only")
    draw_history_selective_priors = DrawHistoryPriors("debut_or_low_confidence")
    model_specs = {
        **MODEL_SPECS,
        "candidate_debut_overlay": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": debut_priors.apply,
        },
        "candidate_class_distance_weight_joint": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": class_distance_weight_priors.apply,
        },
        "candidate_draw_history_context": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": draw_history_priors.apply,
        },
        "candidate_draw_history_debut_only": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": draw_history_debut_priors.apply,
        },
        "candidate_draw_history_low_confidence": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": draw_history_low_confidence_priors.apply,
        },
        "candidate_draw_history_selective": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": draw_history_selective_priors.apply,
        },
        "candidate_trainer_signal_context": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": trainer_signal_priors.apply,
        },
        "candidate_sectional_context": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": trackwork_sectional_candidate,
        },
        "candidate_race_sectional_score": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": race_sectional_candidate,
        },
        "candidate_race_sectional_score_non_debut": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": race_sectional_non_debut_candidate,
        },
        "candidate_race_sectional_score_complete": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": race_sectional_complete_candidate,
        },
        "candidate_race_sectional_score_non_debut_complete": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": race_sectional_non_debut_complete_candidate,
        },
        "candidate_race_sectional_score_strong_only": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": race_sectional_strong_only_candidate,
        },
        "candidate_consistency_context": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": consistency_context_candidate,
        },
        "candidate_horse_health_context": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": horse_health_context_candidate,
        },
        "candidate_horse_health_risk_only": {
            "formulas": HORSE_HEALTH_RISK_ONLY_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": horse_health_context_candidate,
        },
        "candidate_draw_context": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": draw_context_candidate,
        },
        "candidate_draw_hkjc_anchor": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": draw_hkjc_anchor_candidate,
        },
        "candidate_draw_hkjc_anchor_no_bleed": {
            "formulas": CURRENT_MATRIX_FORMULAS,
            "weights": CURRENT_MATRIX_WEIGHTS,
            "feature_transform": draw_hkjc_anchor_no_bleed_candidate,
        },
    }
    if routine:
        # Routine meeting reflection needs representative structural candidates,
        # not every historical ablation.  The full profile remains available to
        # dedicated research commands.  This keeps the default reflector fast
        # enough to finish before writing its meeting report.
        routine_models = {
            "current_live",
            "candidate_ml_7d_weight_shadow",
            "candidate_class_distance_weight_joint",
            "candidate_trainer_signal_context",
            "candidate_sectional_context",
            "candidate_race_sectional_score_non_debut",
            "candidate_consistency_context",
            "candidate_horse_health_risk_only",
            "candidate_draw_hkjc_anchor_no_bleed",
        }
        model_specs = {
            name: spec for name, spec in model_specs.items() if name in routine_models
        }
    results_index = build_results_index(results_roots)
    meetings = hk_meeting_dirs(meeting_roots)
    all_races: list[dict] = []
    coverage = {
        "meetings": 0,
        "races": 0,
        "horses": 0,
        "debut_horses": 0,
        "debut_races": 0,
        "duplicate_races_skipped": 0,
        "published_mainline_meetings": 0,
        "published_mainline_races": 0,
        "skipped_meetings": [],
    }
    seen_race_keys: set[tuple[str | None, str, int]] = set()

    for meeting_dir in meetings:
        date = meeting_date(meeting_dir)
        result_path = results_index.get(date or "")
        if not result_path:
            coverage["skipped_meetings"].append(str(meeting_dir))
            continue
        published_predictions = load_published_mainline_predictions(meeting_dir)
        actual_results = load_results(result_path)
        meeting_had_race = False
        meeting_has_published_mainline = False
        meeting_venue = venue_from_meeting_dir(meeting_dir)
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=race_num_from_path):
            race_num = race_num_from_path(logic_path)
            actual_pos = actual_results.get(race_num)
            if not actual_pos:
                continue
            race_key = dedup_race_key(date, meeting_venue, race_num)
            if race_key in seen_race_keys:
                coverage["duplicate_races_skipped"] += 1
                continue
            seen_race_keys.add(race_key)
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_context = logic.get("race_analysis", {})
            race_context = dict(race_context)
            race_context.setdefault("venue", meeting_venue)
            horses = []
            has_debut = False
            for horse_num_text, horse in logic.get("horses", {}).items():
                try:
                    horse_num = int(horse_num_text)
                except ValueError:
                    continue
                features = compute_full_feature_scores(horse, race_context)
                models = {}
                if horse.get("is_debut") or horse.get("debut_runner") or horse.get("career_tag") == "DEBUT":
                    has_debut = True
                    coverage["debut_horses"] += 1
                for model_name, spec in model_specs.items():
                    transformed = spec.get("feature_transform", lambda _horse, vals, _ctx=None: vals)(horse, features, race_context)
                    matrix_scores = compute_matrix_scores(transformed, spec["formulas"])
                    ability = compute_ability(matrix_scores, spec["weights"])
                    models[model_name] = {"matrix_scores": matrix_scores, "ability": ability}
                horses.append({
                    "horse_num": horse_num,
                    "horse_name": horse.get("horse_name", ""),
                    "horse": _compact_horse_for_archive_review(horse),
                    "feature_scores": {
                        "draw_score": features.get("draw_score", 60.0),
                        "form_score": features.get("form_score", 60.0),
                    },
                    "models": models,
                })
            if not horses:
                continue
            meeting_had_race = True
            coverage["races"] += 1
            coverage["horses"] += len(horses)
            if has_debut:
                coverage["debut_races"] += 1
            race_models = {}
            for model_name in model_specs:
                race_models[model_name] = evaluate_model(horses, actual_pos, model_name)
            published_picks = published_predictions.get(race_num)
            if published_picks:
                race_models["published_mainline"] = evaluate_pick_order(published_picks, actual_pos)
                coverage["published_mainline_races"] += 1
                meeting_has_published_mainline = True
            race_models["candidate_draw_tiebreak_ordering"] = evaluate_model(
                apply_draw_tiebreak(horses, race_context, "current_live"),
                actual_pos,
                "current_live",
            )
            race_models["candidate_draw_micro_tiebreak"] = evaluate_model(
                apply_draw_micro_tiebreak(horses, race_context, "current_live"),
                actual_pos,
                "current_live",
            )
            race_models["candidate_draw_micro_tiebreak_hv_mid"] = evaluate_model(
                apply_draw_micro_tiebreak_constrained(
                    horses,
                    race_context,
                    "current_live",
                    hv_only=True,
                    max_gap=0.8,
                ),
                actual_pos,
                "current_live",
            )
            race_models["candidate_draw_micro_tiebreak_hv_mid_shape60"] = evaluate_model(
                apply_draw_micro_tiebreak_constrained(
                    horses,
                    race_context,
                    "current_live",
                    hv_only=True,
                    min_race_shape=60.0,
                    max_gap=0.8,
                ),
                actual_pos,
                "current_live",
            )
            race_models["candidate_draw_micro_tiebreak_hv_mid_shape60_gap06"] = evaluate_model(
                apply_draw_micro_tiebreak_constrained(
                    horses,
                    race_context,
                    "current_live",
                    hv_only=True,
                    min_race_shape=60.0,
                    max_gap=0.6,
                ),
                actual_pos,
                "current_live",
            )
            race_models["candidate_draw_micro_tiebreak_hv_mid_shape60_gap08_edge05"] = evaluate_model(
                apply_draw_micro_tiebreak_constrained(
                    horses,
                    race_context,
                    "current_live",
                    hv_only=True,
                    min_race_shape=60.0,
                    max_gap=0.8,
                    min_bonus_edge=0.5,
                ),
                actual_pos,
                "current_live",
            )
            race_entry = {
                "meeting": str(meeting_dir),
                "date": date,
                "race": race_num,
                "has_debut": has_debut,
                "race_context": race_context,
                "actual_pos": actual_pos,
                "horses": horses,
                "models": race_models,
            }
            all_races.append(race_entry)
        if meeting_had_race:
            coverage["meetings"] += 1
        if meeting_has_published_mainline:
            coverage["published_mainline_meetings"] += 1

    model_summary = {
        model_name: summarize_model_races([race["models"][model_name] for race in all_races]) for model_name in model_specs
    }
    model_roles = {
        "previous_calibrated": "legacy_reference",
        "current_live": "production_mainline",
    }
    published_races = [race["models"]["published_mainline"] for race in all_races if "published_mainline" in race["models"]]
    if published_races:
        model_summary["published_mainline"] = summarize_model_races(published_races)
        model_roles["published_mainline"] = "historical_gate"
    model_summary["candidate_draw_tiebreak_ordering"] = summarize_model_races(
        [race["models"]["candidate_draw_tiebreak_ordering"] for race in all_races]
    )
    model_summary["candidate_draw_micro_tiebreak"] = summarize_model_races(
        [race["models"]["candidate_draw_micro_tiebreak"] for race in all_races]
    )
    model_summary["candidate_draw_micro_tiebreak_hv_mid"] = summarize_model_races(
        [race["models"]["candidate_draw_micro_tiebreak_hv_mid"] for race in all_races]
    )
    model_summary["candidate_draw_micro_tiebreak_hv_mid_shape60"] = summarize_model_races(
        [race["models"]["candidate_draw_micro_tiebreak_hv_mid_shape60"] for race in all_races]
    )
    model_summary["candidate_draw_micro_tiebreak_hv_mid_shape60_gap06"] = summarize_model_races(
        [race["models"]["candidate_draw_micro_tiebreak_hv_mid_shape60_gap06"] for race in all_races]
    )
    model_summary["candidate_draw_micro_tiebreak_hv_mid_shape60_gap08_edge05"] = summarize_model_races(
        [race["models"]["candidate_draw_micro_tiebreak_hv_mid_shape60_gap08_edge05"] for race in all_races]
    )
    debut_race_summary = {
        model_name: summarize_model_races([race["models"][model_name] for race in all_races if race["has_debut"]])
        for model_name in model_specs
    }
    published_debut_races = [
        race["models"]["published_mainline"] for race in all_races if race["has_debut"] and "published_mainline" in race["models"]
    ]
    if published_debut_races:
        debut_race_summary["published_mainline"] = summarize_model_races(published_debut_races)
    debut_race_summary["candidate_draw_tiebreak_ordering"] = summarize_model_races(
        [race["models"]["candidate_draw_tiebreak_ordering"] for race in all_races if race["has_debut"]]
    )
    debut_race_summary["candidate_draw_micro_tiebreak"] = summarize_model_races(
        [race["models"]["candidate_draw_micro_tiebreak"] for race in all_races if race["has_debut"]]
    )
    debut_race_summary["candidate_draw_micro_tiebreak_hv_mid"] = summarize_model_races(
        [race["models"]["candidate_draw_micro_tiebreak_hv_mid"] for race in all_races if race["has_debut"]]
    )
    debut_race_summary["candidate_draw_micro_tiebreak_hv_mid_shape60"] = summarize_model_races(
        [race["models"]["candidate_draw_micro_tiebreak_hv_mid_shape60"] for race in all_races if race["has_debut"]]
    )
    debut_race_summary["candidate_draw_micro_tiebreak_hv_mid_shape60_gap06"] = summarize_model_races(
        [race["models"]["candidate_draw_micro_tiebreak_hv_mid_shape60_gap06"] for race in all_races if race["has_debut"]]
    )
    debut_race_summary["candidate_draw_micro_tiebreak_hv_mid_shape60_gap08_edge05"] = summarize_model_races(
        [race["models"]["candidate_draw_micro_tiebreak_hv_mid_shape60_gap08_edge05"] for race in all_races if race["has_debut"]]
    )

    best_outer_weights, best_outer_summary = (
        (None, None) if routine else pick_best_outer_weight_candidate(all_races)
    )
    if best_outer_weights and best_outer_summary:
        model_summary["candidate_outer_weights_retune"] = best_outer_summary
        debut_race_summary["candidate_outer_weights_retune"] = summarize_outer_weight_subset(all_races, best_outer_weights, only_debut=True)

    for model_name in model_summary:
        model_roles.setdefault(model_name, "experimental")

    meeting_summary = summarize_meeting_models(
        all_races,
        list(model_specs.keys()) + [
            "published_mainline",
            "candidate_draw_tiebreak_ordering",
            "candidate_draw_micro_tiebreak",
            "candidate_draw_micro_tiebreak_hv_mid",
            "candidate_draw_micro_tiebreak_hv_mid_shape60",
            "candidate_draw_micro_tiebreak_hv_mid_shape60_gap06",
            "candidate_draw_micro_tiebreak_hv_mid_shape60_gap08_edge05",
        ],
        best_outer_weights=best_outer_weights,
    )

    race_records = []
    if include_races:
        race_records = [
            {
                "meeting": race["meeting"],
                "date": race["date"],
                "race": race["race"],
                "has_debut": race["has_debut"],
                "actual_pos": race["actual_pos"],
                "models": {
                    model_name: {
                        "picks": model_payload.get("picks", []),
                        "gold": model_payload.get("gold", False),
                        "good": model_payload.get("good", False),
                        "min_threshold": model_payload.get("min_threshold", False),
                        "single": model_payload.get("single", False),
                        "champion": model_payload.get("champion", False),
                        "top3_has_champion": model_payload.get("top3_has_champion", False),
                        "winner_rank": model_payload.get("winner_rank"),
                        "mrr": model_payload.get("mrr", 0.0),
                        "pick1_finish": model_payload.get("pick1_finish"),
                        "top4_hits": model_payload.get("top4_hits", 0),
                        "order_issue": model_payload.get("order_issue", False),
                    }
                    for model_name, model_payload in race["models"].items()
                },
            }
            for race in all_races
        ]

    return {
        "coverage": coverage,
        "model_roles": model_roles,
        "model_summary": model_summary,
        "debut_race_summary": debut_race_summary,
        "meeting_summary": meeting_summary,
        "race_records": race_records,
        "slice_summary": {
            "hv_middle_distance": summarize_slice(
                all_races,
                [
                    "current_live",
                    "candidate_draw_micro_tiebreak",
                    "candidate_draw_micro_tiebreak_hv_mid",
                    "candidate_draw_micro_tiebreak_hv_mid_shape60",
                    "candidate_draw_micro_tiebreak_hv_mid_shape60_gap06",
                    "candidate_draw_micro_tiebreak_hv_mid_shape60_gap08_edge05",
                ],
                slice_hv_middle_distance,
            ),
            "hv_middle_distance_shape60": summarize_slice(
                all_races,
                [
                    "current_live",
                    "candidate_draw_micro_tiebreak",
                    "candidate_draw_micro_tiebreak_hv_mid",
                    "candidate_draw_micro_tiebreak_hv_mid_shape60",
                    "candidate_draw_micro_tiebreak_hv_mid_shape60_gap06",
                    "candidate_draw_micro_tiebreak_hv_mid_shape60_gap08_edge05",
                ],
                slice_hv_middle_distance_shape60,
            ),
        },
        "matrix_diagnostics": matrix_diagnostics(all_races),
        "season_trends": review_season_trends(season_csvs),
        "best_outer_weights": best_outer_weights,
        "ml_7d_weight_shadow": ML_7D_WEIGHT_SHADOW,
    }


def render_markdown(review: dict) -> str:
    coverage = review["coverage"]
    lines = [
        "# HKJC Auto Weighting Review",
        "",
        "## Coverage",
        f"- Meetings reviewed: {coverage['meetings']}",
        f"- Races reviewed: {coverage['races']}",
        f"- Horses rescored: {coverage['horses']}",
        f"- Debut races in sample: {coverage['debut_races']}",
        f"- Debut horses in sample: {coverage['debut_horses']}",
        f"- Duplicate races skipped by dedup: {coverage['duplicate_races_skipped']}",
    ]
    if coverage["skipped_meetings"]:
        lines.append(f"- Skipped meetings without matched results: {len(coverage['skipped_meetings'])}")

    lines.extend([
        "",
        "## Fixed ML Shadow Weights",
        "",
        f"- candidate_ml_7d_weight_shadow: `{json.dumps(review['ml_7d_weight_shadow'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Walk-Forward",
        "",
        "| Model | Races | Gold | Good | Min | Single | Champion | Top3 Champ | Order Issue | Avg Winner Rank | MRR | Avg Pick1 Finish | Avg Top4 Hits |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for model_name, stats in review["model_summary"].items():
        if not stats:
            continue
        lines.append(
            f"| {model_name} | {stats['races']} | {stats['gold']} | {stats['good']} | {stats['min_threshold']} | "
            f"{stats['single']} | {stats['champion']} | {stats['top3_has_champion']} | {stats['order_issue']} | "
            f"{stats['avg_winner_rank']} | {stats['mrr']} | {stats['avg_pick1_finish']} | {stats['avg_top4_hits']} |"
        )

    lines.extend([
        "",
        "## Debut-Race Slice",
        "",
        "| Model | Races | Gold | Good | Min | Single | Champion | Top3 Champ | Order Issue | Avg Winner Rank | MRR | Avg Pick1 Finish | Avg Top4 Hits |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for model_name, stats in review["debut_race_summary"].items():
        if not stats:
            continue
        lines.append(
            f"| {model_name} | {stats['races']} | {stats['gold']} | {stats['good']} | {stats['min_threshold']} | "
            f"{stats['single']} | {stats['champion']} | {stats['top3_has_champion']} | {stats['order_issue']} | "
            f"{stats['avg_winner_rank']} | {stats['mrr']} | {stats['avg_pick1_finish']} | {stats['avg_top4_hits']} |"
        )

    slice_summary = review.get("slice_summary") or {}
    for slice_name, payload in slice_summary.items():
        if not payload or not payload.get("models"):
            continue
        lines.extend([
            "",
            f"## Slice: {slice_name} ({payload['races']} races)",
            "",
            "| Model | Races | Gold | Good | Min | Single | Champion | Top3 Champ | Order Issue | Avg Winner Rank | MRR | Avg Pick1 Finish | Avg Top4 Hits |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for model_name, stats in payload["models"].items():
            lines.append(
                f"| {model_name} | {stats['races']} | {stats['gold']} | {stats['good']} | {stats['min_threshold']} | "
                f"{stats['single']} | {stats['champion']} | {stats['top3_has_champion']} | {stats['order_issue']} | "
                f"{stats['avg_winner_rank']} | {stats['mrr']} | {stats['avg_pick1_finish']} | {stats['avg_top4_hits']} |"
            )

    lines.extend([
        "",
        "## Matrix Signal",
        "",
        "| Matrix | Avg Winner Rank | Winner Score Edge | Top Pick Win Rate | Top Pick Top3 Rate |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for matrix_name, stats in sorted(review["matrix_diagnostics"].items()):
        lines.append(
            f"| {matrix_name} | {stats['avg_winner_rank']} | {stats['avg_winner_score_edge']} | "
            f"{stats['top_pick_win_rate']:.3f} | {stats['top_pick_top3_rate']:.3f} |"
        )

    trends = review.get("season_trends") or {}
    if trends:
        lines.extend([
            "",
            "## Season Trend Hints",
            f"- Combined result rows: {trends['rows']}",
            "",
            "### Draw Spread Hotspots",
            "| Venue | Distance | Max Win | Min Win | Mean Win | Spread |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for row in trends["draw_spread_top"][:8]:
            lines.append(
                f"| {row['Venue']} | {int(row['Distance'])} | {row['max']:.3f} | {row['min']:.3f} | "
                f"{row['mean']:.3f} | {row['spread']:.3f} |"
            )
        lines.extend([
            "",
            "### Trainer Distance Splits",
            "| Trainer | Distance | Starts | Win Rate | Place Rate |",
            "| --- | ---: | ---: | ---: | ---: |",
        ])
        for row in trends["trainer_distance_top"][:8]:
            lines.append(
                f"| {row['Trainer']} | {int(row['Distance'])} | {int(row['starts'])} | {row['win_rate']:.3f} | {row['place_rate']:.3f} |"
            )
        lines.extend([
            "",
            "### Jockey Distance Splits",
            "| Jockey | Distance | Starts | Win Rate | Place Rate |",
            "| --- | ---: | ---: | ---: | ---: |",
        ])
        for row in trends["jockey_distance_top"][:8]:
            lines.append(
                f"| {row['Jockey']} | {int(row['Distance'])} | {int(row['starts'])} | {row['win_rate']:.3f} | {row['place_rate']:.3f} |"
            )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    meeting_roots = [Path(p) for p in args.meeting_root] or default_meeting_roots()
    results_roots = [Path(p) for p in args.results_root] or default_results_roots()
    season_csvs = [Path(p) for p in args.season_csv] or default_season_csvs()
    review = run_review(meeting_roots, results_roots, season_csvs)
    if args.json:
        print(json.dumps(review, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(review))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
