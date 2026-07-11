from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from matrix_mapper import map_features_to_matrix, map_features_to_matrix_scores
from scoring import (
    FEATURE_KEYS,
    MATRIX_WEIGHTS,
    CLASS_MICRO_WEIGHTS,
    CONSISTENCY_MICRO_WEIGHTS,
    SECTIONAL_MICRO_WEIGHTS,
    TRACK_MICRO_WEIGHTS,
    FORMLINE_MICRO_WEIGHTS,
    PACE_MICRO_WEIGHTS,
    JOCKEY_MICRO_WEIGHTS,
    TRAINER_MICRO_WEIGHTS,
    FIT_MICRO_WEIGHTS,
    clip_score,
    compute_grade,
    parse_float,
    parse_numbers,
    parse_record_line,
    parse_recent_finishes,
    safe_ratio,
    wet_form_feature,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[6]
import sys as _sys; _sys.path.insert(0, str(_PROJECT_ROOT))
from wongchoi_paths import AU_RACING as _AU_RACING
TRACK_RESOURCE_DIR = Path(__file__).resolve().parents[3] / "au_horse_analyst" / "resources"
AUTO_RESOURCE_DIR = Path(__file__).resolve().parents[2] / "resources"
ARCHIVE_AU_DIR = _AU_RACING
JOCKEY_TRAINER_COMBO_STATS_PATH = ARCHIVE_AU_DIR / "AU_Jockey_Trainer_Combo_Stats.csv"
JOCKEY_RATINGS_PATH = AUTO_RESOURCE_DIR / "AU_Jockey_Ratings.csv"
TRAINER_RATINGS_PATH = AUTO_RESOURCE_DIR / "AU_Trainer_Ratings.csv"
TRACK_PROFILE_CACHE: dict[tuple[str, int], dict] = {}
JOCKEY_TRAINER_COMBO_CACHE: dict[tuple[str, str, str], dict] | None = None
TRAINER_TRACK_CACHE: dict[tuple[str, str], dict] | None = None
JOCKEY_RATINGS_CACHE: dict[str, dict] | None = None
TRAINER_RATINGS_CACHE: dict[str, dict] | None = None
DRAW_BIAS_MATRIX_CACHE: dict | None = None
DRAW_BIAS_MATRIX_PATH = Path(__file__).resolve().parent / "au_draw_bias_matrix.json"

# Standard 600m times (seconds) per track/distance-bin, computed from archive data
_STANDARD_600M = {
    'Randwick': {1000:33.74,1100:34.47,1200:34.44,1300:34.69,1400:35.11,1500:35.52,1600:35.19,1700:34.86,1800:35.47,2000:35.72,2400:35.13,2600:35.87},
    'Rosehill': {1100:34.13,1200:34.66,1300:34.65,1400:34.89,1500:34.95,1800:35.28,2000:35.19,2400:35.62},
    'Flemington': {1000:33.64,1100:33.61,1200:34.06,1400:34.51,1500:34.44,1600:34.78,1700:35.41,1800:35.17,2000:35.2,2600:35.96},
    'Caulfield': {1000:34.15,1100:34.43,1200:34.84,1400:35.27,1500:34.92,1600:35.75,1700:35.9,1800:35.86,2000:35.9,2400:36.78},
    'Sandown': {1000:33.01,1100:34.08,1200:34.57,1300:34.36,1400:34.8,1500:34.5,1600:34.94,1700:35.96,1800:35.04,2200:35.5,2400:35.44,2600:36.04},
    'Warwick Farm': {1000:33.45,1100:34.36,1200:34.31,1300:35.33,1400:35.07,1600:35.54,2200:35.73,2400:35.81},
    'Newcastle': {1000:33.31,1200:35.0,1300:34.7,1400:34.82,1500:34.8,1600:35.32,2000:35.54,2200:36.75,2400:35.11},
    'Kembla Grange': {1000:33.41,1200:34.28,1300:34.5,1400:34.91,1500:35.12,1600:35.25,2000:35.94,2400:36.25},
    'Moonee Valley': {1000:34.42,1200:35.44,1500:36.16,1600:36.1,2200:36.22,2600:36.9},
    'Canterbury': {1100:35.01,1200:35.27,1300:35.46,1600:35.81,2000:36.22},
    'Hawkesbury': {1000:33.33,1100:33.94,1300:34.28,1400:34.6,1500:34.44,1600:34.78,1800:35.1,2000:34.8,2200:35.73},
    'Pakenham': {1000:33.68,1100:34.57,1200:34.67,1400:35.53,1600:35.89,2000:35.97,2600:36.69},
    'Kensington': {1000:33.77,1100:34.37,1200:34.7,1300:35.17,1400:35.13,1600:35.24,1800:35.76,2400:36.02},
    'Eagle Farm': {1000:33.7,1200:34.4,1300:34.93,1400:35.07,1500:35.85,1600:35.33,1800:36.16,2200:35.98,2400:36.56},
    'Wyong': {1000:33.69,1100:34.45,1200:34.72,1300:34.92,1400:35.35,1600:35.08,2000:36.62,2200:35.57},
    'Geelong': {1100:34.6,1200:34.95,1300:35.24,1400:35.39,1500:35.7,1600:36.12,1700:35.92,2000:36.52,2200:36.49,2400:36.74},
    'Cranbourne': {1000:34.72,1200:35.55,1300:35.98,1400:36.26,1500:36.05,1600:36.68,2000:36.72,2600:37.57},
    'Bendigo': {1000:34.57,1100:34.88,1300:35.36,1400:35.56,1500:36.28,1600:35.94,2200:36.99,2400:36.02},
    'Gosford': {1000:34.15,1100:34.9,1200:35.25,1600:35.61,2000:36.17,2200:35.68},
    'Scone': {1000:34.39,1100:34.4,1200:34.66,1300:34.98,1400:35.24,1600:35.37,1700:35.04,2200:36.08},
    'Mornington': {1000:34.56,1200:35.32,1500:36.28,1600:36.38,2000:37.2,2400:36.5},
    'Sale': {1000:34.42,1100:35.26,1200:35.05,1400:35.6,1600:36.03,1700:36.08,2200:36.74},
    'Ballarat': {1000:33.72,1100:34.62,1200:34.76,1400:34.8,1500:35.36,1600:35.83,2000:36.24,2600:37.8},
    'Doomben': {1100:34.22,1200:34.52,1400:35.03,1600:35.09,2000:35.98,2200:35.63},
    'Morphettville': {1100:34.24,1200:34.57,1600:35.54,1800:36.43,2000:37.24,2600:36.51},
    'Gold Coast': {1000:34.03,1100:33.69,1200:34.75,1300:34.43,1400:35.03,1800:36.68,2200:36.7},
    'Sunshine Coast': {1000:34.43,1100:33.73,1200:35.11,1300:34.8,1400:35.6,1600:35.65,1800:36.26,2400:37.04},
    'Ascot': {1000:33.79,1100:34.76,1200:34.59,1400:34.73,1500:34.62,1600:34.63,1800:35.53,2200:35.55,2400:36.27},
    'Warrnambool': {1000:35.66,1100:35.58,1200:36.32,1400:36.92,1700:36.74,2000:38.06,2400:38.44,2600:40.75},
    'Muswellbrook': {1000:34.09,1300:35.2,1500:35.42,1800:36.61},
    'Goulburn': {1000:34.98,1100:35.45,1200:35.63,1300:36.26,1400:36.01,1500:36.77,1600:36.55,2200:36.96},
    'Tamworth': {1000:34.34,1200:35.16,1400:35.76,1600:36.44,2200:35.86},
    'Wagga': {1000:34.16,1200:34.44,1300:35.23,1400:35.05,1600:35.13,1800:36.43,2000:35.15,2600:36.8},
    'Seymour': {1000:34.46,1100:34.67,1200:35.33,1300:35.51,1400:35.9,1600:35.7,2000:36.64},
    'Kyneton': {1100:34.78,1200:35.7,1500:36.18,2000:36.5},
    'Taree': {1000:35.19,1300:36.24,1400:37.08,1600:36.75,2000:36.4},
}
_DISTANCE_ONLY_L600 = {1000:33.95,1100:34.42,1200:34.76,1300:34.98,1400:35.1,1500:35.23,1600:35.5,1700:35.66,1800:35.55,2000:35.79,2200:36.12,2400:35.84,2600:36.4}

TRACK_NAME_CLEANUP = [
    (' Gardens', ''), ('Grd ', ''), ('Heath', ''), ('Lakeside', ''), (' Hillside', ''),
    ('Sportsbet-', ''), ('Sportsbet ', ''), ('Royal ', ''), (' Park', ''), (' Synthetic', ''),
]


def _distance_bin(dist_m: int) -> int:
    for b in (1000,1100,1200,1300,1400,1500,1600,1700,1800,2000,2200,2400,2600):
        if dist_m <= b:
            return b
    return 2600


def _normalize_track_name(name: str) -> str:
    n = str(name or '').strip()
    for old, new in TRACK_NAME_CLEANUP:
        n = n.replace(old, new)
    return n.strip()


def _lookup_standard_l600(track: str, distance_m: int) -> float | None:
    norm = _normalize_track_name(track)
    dbin = _distance_bin(distance_m)
    return _STANDARD_600M.get(norm, {}).get(dbin) or _DISTANCE_ONLY_L600.get(dbin)
VENUE_TRACK_MAP = {
    "randwick": "04b_track_randwick.md",
    "rosehill": "04b_track_rosehill.md",
    "flemington": "04b_track_flemington.md",
    "caulfield": "04b_track_caulfield.md",
    "moonee valley": "04b_track_moonee_valley.md",
    "eagle farm": "04b_track_eagle_farm.md",
    "doomben": "04b_track_doomben.md",
    "warwick farm": "04b_track_warwick_farm.md",
    "canterbury": "04b_track_provincial.md",
    "provincial": "04b_track_provincial.md",
}

VENUE_STATE_MAP = {
    "randwick": "NSW",
    "rosehill": "NSW",
    "warwick farm": "NSW",
    "hawkesbury": "NSW",
    "gosford": "NSW",
    "canterbury": "NSW",
    "wyong": "NSW",
    "newcastle": "NSW",
    "kembla": "NSW",
    "flemington": "VIC",
    "caulfield": "VIC",
    "cranbourne": "VIC",
    "pakenham": "VIC",
    "sale": "VIC",
    "sandown": "VIC",
    "moonee valley": "VIC",
    "eagle farm": "QLD",
    "doomben": "QLD",
}

METRO_VENUE_TOKENS = (
    "randwick", "rosehill", "warwick farm", "canterbury",
    "flemington", "caulfield", "sandown", "moonee valley",
    "eagle farm", "doomben",
)


def _normalize_identity_text(value) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_rating_identity(value) -> str:
    text = _normalize_identity_text(value)
    text = text.replace("(J-Mac)", "").strip()
    return text.lower()


def _load_jockey_trainer_combo_stats():
    global JOCKEY_TRAINER_COMBO_CACHE, TRAINER_TRACK_CACHE
    if JOCKEY_TRAINER_COMBO_CACHE is not None and TRAINER_TRACK_CACHE is not None:
        return JOCKEY_TRAINER_COMBO_CACHE, TRAINER_TRACK_CACHE

    combo_cache: dict[tuple[str, str, str], dict] = {}
    trainer_cache: dict[tuple[str, str], dict] = {}
    if JOCKEY_TRAINER_COMBO_STATS_PATH.exists():
        with JOCKEY_TRAINER_COMBO_STATS_PATH.open("r", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                track = _normalize_identity_text(row.get("Track")).lower()
                jockey = _normalize_identity_text(row.get("Jockey")).lower()
                trainer = _normalize_identity_text(row.get("Trainer")).lower()
                if not track or not trainer:
                    continue
                runs = int(parse_float(row.get("Total Runs")) or 0)
                wins = int(parse_float(row.get("Wins")) or 0)
                places = int(parse_float(row.get("Places (Top 3)")) or 0)
                win_rate = (wins / runs) if runs else 0.0
                place_rate = (places / runs) if runs else 0.0
                if jockey:
                    combo_cache[(track, jockey, trainer)] = {
                        "runs": runs,
                        "wins": wins,
                        "places": places,
                        "win_rate": win_rate,
                        "place_rate": place_rate,
                    }
                trainer_bucket = trainer_cache.setdefault((track, trainer), {"runs": 0, "wins": 0, "places": 0})
                trainer_bucket["runs"] += runs
                trainer_bucket["wins"] += wins
                trainer_bucket["places"] += places
    for stats in trainer_cache.values():
        runs = stats["runs"] or 0
        stats["win_rate"] = (stats["wins"] / runs) if runs else 0.0
        stats["place_rate"] = (stats["places"] / runs) if runs else 0.0

    JOCKEY_TRAINER_COMBO_CACHE = combo_cache
    TRAINER_TRACK_CACHE = trainer_cache
    return combo_cache, trainer_cache
def _load_draw_bias_matrix():
    global DRAW_BIAS_MATRIX_CACHE
    if DRAW_BIAS_MATRIX_CACHE is None:
        if DRAW_BIAS_MATRIX_PATH.exists():
            try:
                with open(DRAW_BIAS_MATRIX_PATH, "r", encoding="utf-8") as f:
                    DRAW_BIAS_MATRIX_CACHE = json.load(f)
            except Exception as e:
                print(f"Error loading Draw Bias Matrix: {e}")
                DRAW_BIAS_MATRIX_CACHE = {}
        else:
            DRAW_BIAS_MATRIX_CACHE = {}
    return DRAW_BIAS_MATRIX_CACHE

def _load_named_rating_stats():
    global JOCKEY_RATINGS_CACHE, TRAINER_RATINGS_CACHE
    if JOCKEY_RATINGS_CACHE is not None and TRAINER_RATINGS_CACHE is not None:
        return JOCKEY_RATINGS_CACHE, TRAINER_RATINGS_CACHE

    def load_csv(path: Path) -> dict[str, dict]:
        cache: dict[str, dict] = {}
        if not path.exists():
            return cache
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                payload = {
                    "name": _normalize_identity_text(row.get("name")),
                    "canonical_name": _normalize_identity_text(row.get("canonical_name")),
                    "tier": _normalize_identity_text(row.get("tier")),
                    "base_score": float(parse_float(row.get("base_score")) or 60),
                    "confidence": _normalize_identity_text(row.get("confidence")),
                    "source": _normalize_identity_text(row.get("source")),
                    "notes": _normalize_identity_text(row.get("notes")),
                }
                for key in {payload["name"], payload["canonical_name"]}:
                    normalized = _normalize_rating_identity(key)
                    if normalized:
                        cache[normalized] = payload
        return cache

    JOCKEY_RATINGS_CACHE = load_csv(JOCKEY_RATINGS_PATH)
    TRAINER_RATINGS_CACHE = load_csv(TRAINER_RATINGS_PATH)
    return JOCKEY_RATINGS_CACHE, TRAINER_RATINGS_CACHE


# BUGFIX 2026-07-03: ported the fixed header/meta regexes from build_au_logic —
# the enrich path still used the pre-fix versions, so a horse with 負重: 未知/N/A
# was silently dropped (its record rows bled into the previous horse's block and
# its facts features collapsed to neutral), and an unrated horse failed the whole
# racecard meta line. Groups keep the same order (num/name/barrier/jockey/trainer/
# weight); rating group(2) is now optional.
FIELD_TRAILER_RE = re.compile(r"\s*\|\s*負重:\s*(?:[0-9.]+kg|未知|N/A|-)\s*$")
HORSE_BLOCK_RE = re.compile(
    r"^### 馬匹 #(\d+) (.+?) \(檔位 (\d+)\)"
    r"(?:\s*\| 騎師: ([^|]+?))?"
    r"(?:\s*\| 練馬師: ([^|\n\r]+?))?"
    r"(?:\s*\| 負重: (?:([0-9.]+)kg|未知|N/A|-))?$",
    re.M,
)
RACECARD_HORSE_RE = re.compile(r"^\d+\.\s+(.+?)\s+\((\d+)\)$")
RACECARD_META_RE = re.compile(
    r"^Trainer:\s.*?\|\sJockey:\s.*?\|\sWeight:\s*([0-9.]+)(?:kg)?(?:\s*\([^|]*\))?\s*\|\sAge:\s.*?\|\sRating:\s*([0-9.]+)?"
)


class RacingEngine:
    def __init__(self, horse_data, race_context, facts_section="", facts_path=None):
        self.horse_data = horse_data
        self.race_context = race_context or {}
        self.facts_section = facts_section or ""
        self.facts_path = Path(facts_path) if facts_path else None
        self.data = horse_data.get("_data", {}) if isinstance(horse_data.get("_data"), dict) else {}
        self.reason_codes = []
        self.risk_flags = []
        self.provenance = {}
        # 人馬配搭分逐項調整紀錄（因子、加減分、原始數據）— 供報告完整追溯
        self.jt_fit_detail = None
        self._record_entry_cache = None
        self._official_entry_cache = None
        self._sectional_trend_cache = None
        self._formline_row_cache = None
        self._track_context_cache = None
        self._track_family_cache = None
        self._latest_l600_rt_cache = None
        self._sectional_breakdown_cache = None
        self._formguide_shape_cache = None
        self.horse_data["horse_name"] = self._clean_identity(self.horse_data.get("horse_name"))
        self.horse_data["jockey"] = self._clean_identity(self.horse_data.get("jockey"))
        self.horse_data["trainer"] = self._clean_identity(self.horse_data.get("trainer"))

    def _speed_map(self):
        speed_map = self.race_context.get("speed_map")
        return speed_map if isinstance(speed_map, dict) else {}

    def _speed_map_field(self, *keys):
        speed_map = self._speed_map()
        for key in keys:
            value = speed_map.get(key)
            if value not in (None, "", [], {}):
                return value
        for key in keys:
            value = self.race_context.get(key)
            if value not in (None, "", [], {}):
                return value
        return ""

    def analyze_horse(self):
        feature_scores = {}
        feature_notes = {}

        for name, func in {
            "form_score": self._form_score,
            "trial_score": self._trial_score,
            "sectional_score": self._sectional_score,
            "pace_map_score": self._pace_map_score,
            "jockey_score": self._jockey_score,
            "trainer_score": self._trainer_score,
            "jockey_horse_fit_score": self._jockey_horse_fit_score,
            "class_score": self._class_score,
            "rating_score": self._rating_score,
            "weight_score": self._weight_score,
            "distance_score": self._distance_score,
            "track_score": self._track_score,
            "formline_score": self._formline_score,
            "consistency_score": self._consistency_score,
            "health_score": self._health_score,
            "confidence_score": self._confidence_score,
            "pace_figure_score": self._pace_figure_score,
        }.items():
            score, note, source = func()
            feature_scores[name] = clip_score(score)
            feature_notes[name] = note
            self.provenance[name] = source

        for key in FEATURE_KEYS:
            feature_scores[key] = clip_score(feature_scores.get(key, 60))
            feature_notes.setdefault(key, "資料不足，以中性 60 分處理。")
            self.provenance.setdefault(key, "missing_neutral")

        # ── Mild context mismatch penalties ──
        cs = feature_scores.get("class_score", 60)
        ts = feature_scores.get("track_score", 60)
        if feature_scores.get("form_score", 60) >= 72 and cs < 60:
            feature_scores["form_score"] = feature_scores["form_score"] - 4
            feature_notes["form_score"] = feature_notes.get("form_score", "") + "；級數偏弱，近績分小收 −4"
            fd = getattr(self, "form_detail", None)
            if isinstance(fd, dict):
                fd["bonus"].append({"delta": -4.0, "factor": "[環境] 級數偏弱收回",
                                    "evidence": "近績分亢奮但級數分偏弱"})
                fd["final"] = round(clip_score(feature_scores["form_score"]), 2)
        if feature_scores.get("consistency_score", 60) >= 72 and ts < 60:
            feature_scores["consistency_score"] = feature_scores["consistency_score"] - 4
            feature_notes["consistency_score"] = feature_notes.get("consistency_score", "") + "；場地未明，穩定性分小收 −4"
            cd = getattr(self, "consistency_detail", None)
            if isinstance(cd, dict):
                cd["adjustments"].append({"delta": -4.0, "factor": "[環境] 場地未明收回",
                                          "evidence": "穩定度偏高但場地分未達中性"})
                cd["final"] = round(clip_score(feature_scores["consistency_score"]), 2)
        jt_fit = feature_scores.get("jockey_horse_fit_score", 60)
        if jt_fit >= 72 and cs < 58:
            feature_scores["jockey_horse_fit_score"] = jt_fit - 3
            feature_notes["jockey_horse_fit_score"] = feature_notes.get("jockey_horse_fit_score", "") + "；[環境] 級數偏弱，騎練加成已收回"
        # ── Class/form interaction: class_move × form_line ──
        entries = self._official_entries()
        if entries and len(entries) >= 2:
            class_moves = [str(e.get("class_move", "")) for e in entries[:4] if e.get("class_move")]
            if class_moves:
                drops = sum(1 for c in class_moves if "降班" in c)
                big_drops = sum(1 for c in class_moves if "大幅降班" in c)
                rises = sum(1 for c in class_moves if "升班" in c and "降" not in c)
                fl_score = feature_scores.get("formline_score", 60)
                fl_strong = fl_score >= 72
                fl_decent = fl_score >= 65
                fl_weak = fl_score <= 52
                if big_drops >= 1:
                    if fl_strong:
                        feature_scores["formline_score"] = clip_score(fl_score + 4)
                        feature_notes["formline_score"] = feature_notes.get("formline_score", "") + "；[級數] 大幅降班 × 強賽績線 → 正面訊號"
                        self.reason_codes.append("class_drop_strong_formline")
                    elif fl_decent:
                        feature_scores["formline_score"] = clip_score(fl_score + 3)
                        feature_notes["formline_score"] = feature_notes.get("formline_score", "") + "；[級數] 大幅降班 × 中等賽績線 → 中度正面"
                    elif fl_weak:
                        feature_scores["formline_score"] = clip_score(fl_score + 1)
                        feature_notes["formline_score"] = feature_notes.get("formline_score", "") + "；[級數] 大幅降班，賽績線偏弱，保守加分"
                elif drops >= 1:
                    if fl_strong:
                        feature_scores["formline_score"] = clip_score(fl_score + 3)
                        feature_notes["formline_score"] = feature_notes.get("formline_score", "") + "；[級數] 降班 × 強賽績線 → 正面訊號"
                        self.reason_codes.append("class_drop_strong_formline")
                    elif fl_decent:
                        feature_scores["formline_score"] = clip_score(fl_score + 1)
                        feature_notes["formline_score"] = feature_notes.get("formline_score", "") + "；[級數] 降班 × 中等賽績線 → 小幅度加分"
                elif rises >= 2:
                    if fl_strong:
                        feature_scores["formline_score"] = clip_score(fl_score + 1)
                        feature_notes["formline_score"] = feature_notes.get("formline_score", "") + "；[級數] 持續升班 × 強賽績線 → 保守加分"
                    elif fl_weak:
                        feature_scores["formline_score"] = clip_score(fl_score - 2)
                        feature_notes["formline_score"] = feature_notes.get("formline_score", "") + "；[級數] 升班 × 弱賽績線 → 不宜過信"
                        self.reason_codes.append("class_rise_weak_formline")
                elif rises >= 1:
                    if fl_strong:
                        feature_scores["formline_score"] = clip_score(fl_score + 1)
                        feature_notes["formline_score"] = feature_notes.get("formline_score", "") + "；[級數] 升班 × 強賽績線 → 可保守加分"
                    elif fl_weak:
                        feature_scores["formline_score"] = clip_score(fl_score - 2)
                        feature_notes["formline_score"] = feature_notes.get("formline_score", "") + "；[級數] 升班 × 弱賽績線 → 有保留"

        matrix_scores = map_features_to_matrix_scores(feature_scores)
        matrix = map_features_to_matrix(feature_scores)
        pure_7d_score = round(sum(matrix_scores[key] * MATRIX_WEIGHTS[key] for key in MATRIX_WEIGHTS), 4)
        base_7d_score = pure_7d_score
        # Report-only post-7D modifiers (dynamic weights, soft-shape, diversity, barrier,
        # soft-wetproof, place-tightening, micro-rank, wet-condition) were retired
        # 2026-06-22: ML-refuted (barrier net-negative; place-tightening overfit) and
        # never entered ranking/display. Ranking + 綜合戰力分 = pure 7D + wet_form feature only.

        # Wet-form going-suitability feature: 0 on dry going, folded into ability on
        # Soft/Heavy. base_7d_score stays pure 7D; 綜合戰力分 (ability_score) becomes
        # wet-aware on wet tracks. Walk-forward validated (Soft box-trifecta +2.2pp OOS).
        wet_form_feat = wet_form_feature(self._today_going(), self.data.get("going_stats_line"))
        ability_score = round(pure_7d_score + wet_form_feat, 4)
        grade = compute_grade(ability_score)

        matrix_reasoning = self._matrix_reasoning(matrix_scores, feature_scores, feature_notes)
        advantages = self._advantages(feature_scores, matrix_scores)
        disadvantages = self._disadvantages(feature_scores, matrix_scores)
        core_logic = self._core_logic(feature_scores, matrix_scores, advantages, disadvantages)
        grade_transparency = self._au_grade_computation_transparency(matrix_scores, matrix, feature_scores, base_7d_score, ability_score, grade)

        return {
            "version": "AU_AUTO_SCORE_V3",
            "pure_7d_score": round(pure_7d_score, 4),
            "base_7d_score": base_7d_score,
            "final_rank_score": ability_score,
            "ability_score": ability_score,
            "rank_score": ability_score,
            "wet_form_feature": round(wet_form_feat, 4),
            "grade": grade,
            "race_context": {
                "going": self._today_going(),
                "meeting_bias": self._meeting_bias_brief(),
                "track_geometry": self._track_geometry_brief(),
            },
            "matrix": matrix,
            "matrix_scores": matrix_scores,
            "matrix_reasoning": matrix_reasoning,
            "feature_scores": {key: round(feature_scores[key], 2) for key in FEATURE_KEYS},
            "feature_notes": {key: feature_notes.get(key, "") for key in FEATURE_KEYS},
            "core_logic": core_logic,
            "data_readout": self._data_readout(feature_scores, matrix_scores),
            "advantages": advantages,
            "disadvantages": disadvantages,
            "grade_transparency": grade_transparency,
            "jt_fit_detail": self.jt_fit_detail,
            "stability_detail": {
                "form": getattr(self, "form_detail", {}) or {},
                "consistency": getattr(self, "consistency_detail", {}) or {},
            },
            "pace_perf_detail": {
                "pace": getattr(self, "pace_figure_detail", {}) or {},
                "sectional": {k: self._sectional_breakdown().get(k)
                              for k in ("base", "items", "score", "has_pi")},
                "trial": getattr(self, "trial_detail", {}) or {},
            },
            "jt_signal_detail": {
                "jockey": getattr(self, "jockey_detail", {}) or {},
                "trainer": getattr(self, "trainer_detail", {}) or {},
            },
            "race_shape_detail": {
                "pace_map": getattr(self, "pace_map_detail", {}) or {},
                "track": getattr(self, "track_detail", {}) or {},
            },
            "class_weight_detail": {
                "class": getattr(self, "class_detail", {}) or {},
                "rating": getattr(self, "rating_detail", {}) or {},
                "weight": getattr(self, "weight_detail", {}) or {},
            },
            "formline_rows": self._formline_rows(),
            "reason_codes": sorted(set(self.reason_codes)),
            "risk_flags": sorted(set(self.risk_flags)),
            "score_provenance": self.provenance,
        }

    def _get_class_tier(self, text):
        text = str(text).lower()
        if "group 1" in text or "g1" in text: return 1
        if "group 2" in text or "g2" in text or "group 3" in text or "g3" in text: return 2
        if "listed" in text or "lr" in text or "open" in text: return 3
        bm_match = re.search(r"bm\s*(\d+)", text)
        if bm_match:
            rating = int(bm_match.group(1))
            if rating >= 88: return 4
            if rating >= 72: return 5
            if rating >= 64: return 6
            return 7
        if "class 6" in text or "class 5" in text: return 5
        if "class 4" in text or "class 3" in text: return 6
        if "class 2" in text or "class 1" in text: return 7
        if "maiden" in text: return 8
        return 7

    def _form_score(self):
        starts = self._career_starts()
        detail = {"rows": [], "avg": None, "bonus": [], "final": None, "note": ""}
        self.form_detail = detail
        if starts == 0:
            self.reason_codes.append("debut_form_neutral")
            detail["note"] = "初出馬無正式賽績，按保守 60 分處理"
            detail["final"] = 60.0
            return 60, "初出馬無正式賽績，近績分按保守 60 分處理。", "career_tag"

        entries = self._official_entries()
        if not entries:
            detail["note"] = "缺乏正式賽績（賽績表未有可用場次），按中性 60 分處理"
            detail["final"] = 60.0
            return 60, "缺乏正式賽績，近績分按 60 分處理。", "career_tag"

        today_class = self.race_context.get("race_class", "")
        today_tier = self._get_class_tier(today_class)

        total_weighted_score = 0.0
        total_applied_weights = 0.0
        notes = []

        for i, entry in enumerate(entries[:4]):
            place = parse_float(entry.get("placing"))
            if place is None:
                continue

            if place == 1: base_pts = 100
            elif place == 2: base_pts = 85
            elif place == 3: base_pts = 75
            elif place <= 5: base_pts = 60
            else: base_pts = 40

            if i == 0: decay = 1.0
            elif i == 1: decay = 0.8
            elif i == 2: decay = 0.6
            else: decay = 0.4

            entry_tier = self._get_class_tier(entry.get("class", ""))
            delta = today_tier - entry_tier

            if delta >= 2: class_mult = 1.2
            elif delta == 1: class_mult = 1.1
            elif delta == 0: class_mult = 1.0
            elif delta == -1: class_mult = 0.85
            else: class_mult = 0.7

            race_score = base_pts * class_mult
            total_weighted_score += race_score * decay
            total_applied_weights += decay
            # cols[1]（engine 內叫 kind）先係嗰仗嘅真班次（BM64/Maiden…）；
            # entry["class"] 從來冇呢個欄位。真班次入計分已 A/B 反證（蝕 GGP 換 champ），
            # 所以只作顯示；乘數維持「今場級別基準係數」（全場統一）。
            kind_text = str(entry.get("kind") or "").strip()
            cls = kind_text if kind_text not in ("", "-", "正式") else ""
            detail["rows"].append({
                "idx": i + 1,
                "place": int(place),
                "cls": cls,
                "base": base_pts,
                "mult": class_mult,
                "decay": decay,
            })

            if place <= 5 and cls:
                tier_true = self._get_class_tier(cls)
                if tier_true < today_tier:
                    notes.append(f"曾於較強班次（{cls}）入前五")
                elif tier_true > today_tier:
                    notes.append(f"曾於較弱班次（{cls}）入前五")

        if total_applied_weights > 0:
            avg_score = total_weighted_score / total_applied_weights
        else:
            avg_score = 60

        score = min(100.0, max(0.0, avg_score))
        detail["avg"] = round(score, 2)

        if self._is_maiden_race():
            # 2026-07-10：新馬補充由「試閘名次」改為「試閘 L600 時間」（用戶提出）。
            # A/B：時間版全檔 GGP +1、A窗 +1（good +0.7pp）、無指標倒退；名次版無增益，
            # 兩者取大亦無增益 → 淨用時間。門檻沿用 _trial_score 嘅 17.5/17.0 m/s。
            trial_speed = parse_float(self.data.get("timing_trial_600m_avg_speed"))
            if trial_speed and trial_speed >= 17.5:
                score += 5
                self.reason_codes.append("maiden_trial_time_proxy")
                notes.append("試閘時間快，作近績補充參考")
                detail["bonus"].append({"delta": 5.0, "factor": "新馬試閘時間補充",
                                        "evidence": f"試閘 L600 平均速度 {trial_speed:.2f} m/s（≥17.5 屬快）"})
            elif trial_speed and trial_speed >= 17.0:
                score += 3
                detail["bonus"].append({"delta": 3.0, "factor": "新馬試閘時間補充",
                                        "evidence": f"試閘 L600 平均速度 {trial_speed:.2f} m/s（≥17.0 屬中上）"})

        # 劣績中性回歸（2026-07-10）：診斷證實偏弱近績被罰過盡（<55帶 1仗馬實際前三率
        # 24.6% 反高過 3-4仗馬 21.8%），偏強分係真訊號唔收（反向變體 A/B 反證會蝕）。
        # 60 分以下向中性收縮 ×n/(n+2)，樣本越少收越多。
        # A/B（702場）：全檔案 GGP +4、A窗 +1、B窗 +1、box4 淨 +2 場，無窗口倒退。
        scored_n = len(detail["rows"])
        if scored_n and score < 60.0:
            shrunk = 60.0 + (score - 60.0) * (scored_n / (scored_n + 2.0))
            detail["bonus"].append({
                "delta": round(shrunk - score, 2),
                "factor": "劣績中性回歸",
                "evidence": f"{scored_n}場計分樣本，偏弱分向中性收縮（×{scored_n}/{scored_n + 2}）",
            })
            notes.append("偏弱近績已按樣本量向中性回歸")
            score = shrunk

        detail["final"] = round(clip_score(score), 2)
        # 表達（2026-07-12 用戶要求）：近績序列行先，方向語精簡（強/偏強/中/偏弱）。
        final = clip_score(score)
        seq = str(self.data.get("recent_form") or self.horse_data.get("recent_form") or "").strip()
        seq_txt = f"近績 {seq}" if seq else "近績"
        if final >= 80:
            direction = "加權後強"
        elif final >= 70:
            direction = "加權後偏強"
        elif final > 52:
            direction = "加權後中性"
        else:
            direction = "加權後偏弱"
        # 撇走冗長套話，只留精簡方向 + 真班次備註
        note_str = "；".join([f"{seq_txt}，{direction}"] + list(dict.fromkeys(notes)))
        return score, f"{note_str}。近績分 {final:.1f}。", "recent_form+class_weighted"


    def _trial_score(self):
        detail = {"base": None, "adjustments": [], "final": None, "note": ""}
        self.trial_detail = detail
        trial_places = self._trial_places()
        starts = self._career_starts()
        is_maiden = self._is_maiden_race()
        if not trial_places:
            base = 58 if starts == 0 else 60
            detail["base"] = base
            detail["final"] = base
            detail["note"] = "無試閘紀錄，按保守中性處理"
            return base, "試閘訊號有限，試閘分保守處理。", "trial_table"
        good = sum(1 for place in trial_places[:3] if place <= 3)
        score = 56
        detail["base"] = 56

        def add(delta, factor, evidence=""):
            nonlocal score
            score += delta
            detail["adjustments"].append({"delta": round(float(delta), 2),
                                          "factor": factor, "evidence": evidence})

        if good:
            add(good * 9, "試閘前三獎勵", f"近3次試閘{good}次前三（每次 +9）")
        trial_count = int(parse_float(self.data.get("trial_count")) or len(trial_places))
        latest_trial = trial_places[0] if trial_places else None
        if starts == 0:
            add(4, "初出馬備戰", "未出賽，試閘係主要備戰證據")
            if is_maiden:
                add(2, "新馬賽初出加碼", "")
                self.reason_codes.append("maiden_debut_trial_boost")
        if latest_trial == 1:
            add(4, "最近試閘頭馬", "最近一課試閘勝出")
            if is_maiden:
                add(2, "新馬賽加碼", "")
        elif latest_trial is not None and latest_trial <= 3:
            add(2, "最近試閘前三", f"最近一課試閘第{int(latest_trial)}")
            if is_maiden:
                add(1, "新馬賽加碼", "")
        if trial_count >= 4 and safe_ratio(good, max(1, min(3, trial_count))) >= 0.66:
            add(2, "試閘密度高兼交代穩", f"共{trial_count}次試閘，前列比例高")
            if is_maiden and trial_count >= 6 and safe_ratio(good, trial_count) >= 0.6:
                add(3, "新馬賽密集備戰加碼", "")
                self.reason_codes.append("maiden_trial_density_boost")
        # Maiden: trial speed as direct signal
        if is_maiden:
            tw_trial = self.data.get("timing_trial_600m_avg_speed")
            if tw_trial and tw_trial >= 17.5:
                add(4, "試閘時間快", f"試閘 L600 平均 {tw_trial:.2f} m/s（≥17.5 屬快）")
                self.reason_codes.append("maiden_fast_trial_speed")
            elif tw_trial and tw_trial >= 17.0:
                add(2, "試閘時間中上", f"試閘 L600 平均 {tw_trial:.2f} m/s")
        # Trial video qualitative signals (from trial comments)
        trial_signals = self.data.get("trial_video_signals") or {}
        if trial_signals:
            restrained = trial_signals.get("restrained", 0)
            competitive = trial_signals.get("competitive", 0)
            weakened = trial_signals.get("weakened", 0)
            led = trial_signals.get("led", 0)
            improving = trial_signals.get("improving", 0)
            full_test = trial_signals.get("full_test", 0)
            if restrained >= 1:
                add(4 if starts == 0 or is_maiden else 2, "試閘被拑制", "留力行完，仲有貨賣")
                self.reason_codes.append("trial_restrained_signal")
            if competitive >= 2:
                add(4, "試閘有爭勝", "多課試閘見爭勝心")
            elif competitive >= 1:
                add(2, "試閘有爭勝", "")
            if led >= 2 and competitive >= 1:
                add(3, "帶放兼有爭勝", "")
                self.reason_codes.append("trial_led_competitive")
            elif led >= 1 and competitive >= 1:
                add(1, "帶放兼有爭勝", "")
            if improving >= 1:
                add(2, "試閘走勢改善", "")
            if weakened >= 2:
                add(-4, "試閘轉弱", "多課試閘尾段乏力")
            elif weakened >= 1:
                add(-2, "試閘轉弱", "")
            if full_test >= 2 and competitive == 0:
                add(-3, "盡試冇料", "多課全力試但未見競爭力")
        detail["final"] = round(clip_score(score), 2)
        return score, f"近試閘前 3 名次 {trial_places[:3]}，有 {good} 次前列，並按最近一課/試閘密度修正，試閘分 {clip_score(score):.1f}。", "trial_table"

    def _sectional_breakdown(self):
        if self._sectional_breakdown_cache is not None:
            return self._sectional_breakdown_cache
        entries = self._official_entries()
        latest_entry = entries[0] if entries else {}
        latest_place = parse_float(latest_entry.get("placing")) if latest_entry else None
        recent_top4 = sum(1 for entry in entries[:3] if (parse_float(entry.get("placing")) or 99) <= 4)
        forgiveness_count = self._forgiveness_count()

        w = SECTIONAL_MICRO_WEIGHTS
        base = w.get("base", 40.0)
        total_score = base
        notes = [f"基礎分 {base} 分"]
        items = []

        def add(delta, factor, evidence=""):
            """delta=0 都照入 items — 每個組件永遠有一行，用戶先睇到全貌。"""
            nonlocal total_score
            total_score += delta
            items.append({"delta": round(delta, 2), "factor": factor, "evidence": evidence})
            if delta:
                notes.append(f"{factor} ({delta:+.2f})")

        # 1. Average PI (定位→終點位置增益)
        pi_from_entries = []
        for entry in entries:
            pi_val = parse_float(entry.get("pi"))
            if pi_val is not None:
                pi_from_entries.append(pi_val)

        if not pi_from_entries:
            # 2026-07-10：無 PI 時嘅試閘時間補償 REMOVED — 舊 bonus 非單調（最快 +0、
            # 較慢 +3.97，ML search 殘骸），三個修法 A/B「完全移除」最好（GGP +2）。
            # 試閘證據由試閘分（同維度 leaf）獨力承擔。
            add(0.0, "位置增益（PI）", "缺 L400 PI 數據 — 呢匹馬近仗冇官方 PI 紀錄")
            add(0.0, "末段極速（L600 峰值）", "缺 PI 時不參與評分")
            add(0.0, "增益兌現", "不適用（無 PI 數據）")
            notes.append("缺 L400 PI 數據，段速證據薄，維持基礎分")
        else:
            avg_pi = sum(pi_from_entries) / len(pi_from_entries)
            n_pi = len(pi_from_entries)

            if avg_pi >= 4.0:
                add(w.get("pi_extreme_bonus", 25.0), "位置增益（PI）極佳",
                    f"近{n_pi}仗末段平均追前 {avg_pi:.1f} 個位（≥4 屬頂級後勁）")
            elif avg_pi >= 2.0:
                add(w.get("pi_excellent_bonus", 15.0), "位置增益（PI）優秀",
                    f"近{n_pi}仗末段平均追前 {avg_pi:.1f} 個位")
            elif avg_pi >= 0.0:
                add(w.get("pi_pass_bonus", 5.0), "位置增益（PI）達標",
                    f"近{n_pi}仗末段平均 {avg_pi:+.1f} 個位（冇失地）")
            else:
                add(0.0, "位置增益（PI）",
                    f"近{n_pi}仗末段平均俾人過 {abs(avg_pi):.1f} 個位——缺乏後勁")

            # 2. Distance-Adjusted L600 Peak
            tw_best = self.data.get("timing_600m_best_speed")
            if tw_best and tw_best > 0:
                best_l600 = 600.0 / tw_best
                # 防禦（2026-07-11）：可信 L600 帶 31-42s（舊 writer 分佈 31.4-41.9）。
                # 帶外＝上游污染（曾出過「快過標準 9 秒」假象），唔採用。
                if not (31.0 <= best_l600 <= 42.0):
                    add(0.0, "末段極速（L600 峰值）",
                        f"時間數據異常（{best_l600:.2f}s 超出可信範圍），唔採用")
                    race_dist = None
                else:
                    race_dist = self._distance_from_text(self.race_context.get("distance", ""))
                if race_dist and race_dist >= 600:
                    std_l600 = _lookup_standard_l600(self._current_venue_name(), race_dist)
                    if std_l600 and std_l600 > 0:
                        delta = best_l600 - std_l600
                        if delta <= -0.6:
                            add(w.get("l600_extreme_bonus", 15.0), "末段極速（L600 峰值）破標準",
                                f"生涯最快 {best_l600:.2f}s，快過場地標準 {std_l600:.2f}s 成 {abs(delta):.2f}s")
                        elif delta <= -0.3:
                            add(w.get("l600_excellent_bonus", 5.0), "末段極速（L600 峰值）優秀",
                                f"生涯最快 {best_l600:.2f}s，快過場地標準 {abs(delta):.2f}s")
                        else:
                            add(0.0, "末段極速（L600 峰值）",
                                f"生涯最快 {best_l600:.2f}s，未快過場地標準（{std_l600:.2f}s）")
                    else:
                        add(0.0, "末段極速（L600 峰值）", "此場地/路程無標準時間可比")
            else:
                add(0.0, "末段極速（L600 峰值）", "缺 L600 時間數據")

            # peak_pi / PI trend 項 2026-07-10 REMOVED — ablation 全指標零變化（惰性噪音）。

            # 3. Realization & Forgiveness
            if avg_pi > 0 and recent_top4 > 0:
                add(w.get("realization_bonus", 10.0), "增益兌現",
                    f"近3仗有{recent_top4}次前四——追位真係換到名次")
            elif avg_pi > 2.0 and forgiveness_count >= 1:
                add(w.get("forgiveness_bonus", 5.0), "增益未兌現但有寬恕",
                    "有受阻/蝕位背景，追位未反映在名次")
            else:
                add(0.0, "增益兌現", "PI 未達門檻或近仗未入前四")

        total_score = min(100.0, max(0.0, total_score))

        self._sectional_breakdown_cache = {
            "score": total_score,
            "base": base,
            "items": items,
            "has_pi": bool(pi_from_entries),
            "notes": "；".join(notes) if notes else "-",
            "label": "Base 35.8 + PI/L600 累加",
        }
        return self._sectional_breakdown_cache
    def _sectional_score(self):
        target_line = str(self.data.get("target_distance_line") or "")
        entries = self._official_entries()
        latest_entry = entries[0] if entries else {}
        latest_place = parse_float(latest_entry.get("placing")) if latest_entry else None
        latest_flags = self._entry_note_flags(latest_entry) if latest_entry else {"positive": [], "negative": []}
        race_bucket = self._race_class_bucket()
        wet_state = self._wet_state()
        recent_top3 = sum(1 for entry in entries[:3] if (parse_float(entry.get("placing")) or 99) <= 3)
        breakdown = self._sectional_breakdown()
        score = breakdown["score"]
        notes = []
        # 短判語行先（逐項計法喺 pace_perf_detail 攤開，唔使喺度重覆）
        if not breakdown.get("has_pi"):
            notes.append("缺 L400 PI 數據，只有基礎分")
        elif score >= 60:
            notes.append("PI 位置增益證據正面")
        elif score >= 45:
            notes.append("PI 證據一般")
        else:
            notes.append("PI 證據偏弱")
        if entries and latest_flags["positive"] and latest_place is not None and latest_place <= 4:
            notes.append("上仗直路受阻/蝕位，裸名次未完全反映輸出")
        if "← 今仗 ❌" in target_line:
            notes.append("今仗路程本身仍要再驗證，段速投射唔可過份放大")
        if (
            race_bucket in {"bm58", "bm72"}
            and self._field_size_bucket() == "Field 9-12"
            and wet_state not in {"soft56", "soft7plus", "heavy"}
            and recent_top3 == 0
            and latest_place is not None
            and latest_place >= 5
        ):
            notes.append("中型好地場唔會單憑段速亮點就當成穩定入位本錢")

        return score, "；".join(notes) + f"。段速分 {clip_score(score):.1f}。" if notes else "段速實證有限，段速分中性處理。", "engine_line+sectional_trend+record_table+pf_metrics+formguide_notes"
    def _pace_map_score(self):
        w = PACE_MICRO_WEIGHTS
        barrier = parse_float(self.horse_data.get("barrier"))
        score = w.get("base", 60.0)
        notes = []
        detail = {"base": round(float(score), 1), "lines": []}
        self.pace_map_detail = detail
        if barrier is not None:
            if barrier <= 4:
                bucket = "inside"
            elif barrier <= 8:
                bucket = "middle"
            elif barrier <= 12:
                bucket = "outside"
            else:
                bucket = "wide"

            # BUGFIX 2026-07-03: race_context has no "track" key in the live pipeline
            # (venue lives in meeting_intelligence/track_profile) and distance carries
            # an "m" suffix while the matrix keys are bare digits — both locks meant
            # the per-track draw-bias stats NEVER matched and every race fell to the
            # global bucket. Resolve venue via _current_venue_name and strip units.
            track = str(self.race_context.get("track") or self._current_venue_name() or "").title()
            distance = re.sub(r"[^0-9]", "", str(self.race_context.get("distance", "")))
            field_size = int(self._field_summary().get("count") or 10)

            if field_size <= 8:
                f_cat = "field_1_8"
                expected_wr = 1.0 / max(field_size, 1)
            elif field_size <= 12:
                f_cat = "field_9_12"
                expected_wr = 1.0 / max(field_size, 1)
            else:
                f_cat = "field_13_plus"
                expected_wr = 1.0 / max(field_size, 1)

            matrix = _load_draw_bias_matrix()
            stats = None
            source_level = ""

            # Cascading lookup
            if track in matrix.get("tracks", {}):
                trk_data = matrix["tracks"][track]
                if distance in trk_data.get("distances", {}):
                    d_stats = trk_data["distances"][distance].get(bucket, {})
                    if d_stats.get("sample_size", 0) >= 10:
                        stats = d_stats
                        source_level = f"{track} {distance}m"
                if not stats:
                    t_stats = trk_data.get("track_general", {}).get(bucket, {})
                    if t_stats.get("sample_size", 0) >= 30:
                        stats = t_stats
                        source_level = f"{track} 總體"

            if not stats:
                stats = matrix.get("global_general", {}).get(f_cat, {}).get(bucket, {})
                source_level = f"全澳 {f_cat} 總體"

            bucket_zh = {"inside": "內檔", "middle": "中檔", "outside": "外檔", "wide": "大外檔"}.get(bucket, bucket)
            if stats and stats.get("sample_size", 0) > 0:
                win_rate = stats.get("win_rate", expected_wr)
                raw_modifier = (win_rate - expected_wr) * 100 * w.get("modifier_multiplier", 1.0)
                # 對稱化：勝率統計嘅波幅（尤其細樣本）用 cap 收窄，避免單一檔位被過度加減。
                cap_min, cap_max = w.get("modifier_cap_min", -6.0), w.get("modifier_cap_max", 6.0)
                modifier = max(cap_min, min(cap_max, raw_modifier))
                score += modifier
                # 內部 bucket/f_cat 係 lookup key（"inside"/"field_1_8" 等），唔應該直
                # 接印出嚟畀人睇 —— 呢度加返中文顯示名，內部 lookup 邏輯完全冇改。
                source_level_zh = re.sub(r"field_(\d+)_(\d+|plus)",
                                          lambda m: (f"{m.group(1)}-{m.group(2)}騎陣容" if m.group(2) != "plus"
                                                     else f"{m.group(1)}騎以上陣容"),
                                          source_level)
                n_samp = int(stats.get("sample_size", 0))
                detail["lines"] = [
                    f"檔位 {int(barrier)}（{bucket_zh}）→ {source_level_zh}：歷史勝率 {win_rate * 100:.0f}%，"
                    f"場均基準 {expected_wr * 100:.0f}%（{n_samp} 場樣本）",
                    f"勝率差 → 檔位修正 {modifier:+.1f} 分" + (
                        f"（原始 {raw_modifier:+.1f}，因樣本波幅封頂於 {modifier:+.1f}）"
                        if abs(raw_modifier - modifier) > 0.05 else ""),
                ]
                notes.append(f"檔位 {int(barrier)}（{bucket_zh}）據 {source_level_zh} 統計勝率為 {win_rate*100:.1f}%（基準 {expected_wr*100:.1f}%）")
                if modifier > 2:
                    notes.append("排位具統計優勢")
                elif modifier < -2:
                    notes.append("排位具統計劣勢")
            else:
                # 完全無統計時嘅絕對 fallback。fallback_wide_pen 已係 0（外檔唔硬罰），
                # 所以只喺真正有加減分時先出 note，唔好「有講冇分」。
                wide_pen = w.get("fallback_wide_pen", 0.0)
                inside_bonus = w.get("fallback_inside_bonus", 2.0)
                if barrier >= 12 and abs(wide_pen) > 0.05:
                    score += wide_pen
                    notes.append(f"外檔（{bucket_zh}）無統計數據，保守修正 {wide_pen:+.1f}")
                    detail["lines"] = [f"檔位 {int(barrier)}（{bucket_zh}）無統計數據 → 保守修正 {wide_pen:+.1f}"]
                elif barrier <= 4 and abs(inside_bonus) > 0.05:
                    score += inside_bonus
                    notes.append(f"內檔（{bucket_zh}）無統計數據，輕微加分 {inside_bonus:+.1f}")
                    detail["lines"] = [f"檔位 {int(barrier)}（{bucket_zh}）無統計數據 → 輕微加分 {inside_bonus:+.1f}"]
                else:
                    detail["lines"] = [f"檔位 {int(barrier)}（{bucket_zh}）無足夠統計數據 → 維持中性基礎分"]

        # ── Pace-bias term (uses already-parsed speed_map roles + predicted_pace) ──
        # Racing prior (the model's own collapse_point rule): a slow/controlled tempo
        # advantages on-pace/leader runners and compromises closers; a hot/fast tempo
        # does the reverse. Previously the parsed role buckets were ignored here, so the
        # race_shape dimension carried only a thin draw-bias signal. This adds a small,
        # capped, deterministic pace adjustment from data we already extract.
        pace_adj, pace_note = self._pace_bias_adjustment()
        if abs(pace_adj) >= 0.01:
            score += pace_adj
            notes.append(pace_note)
            detail["lines"].append(f"步速形勢修正 {pace_adj:+.1f}")

        detail["final"] = round(clip_score(score), 2)
        return score, "；".join(notes) + f"。檔位分 {clip_score(score):.1f}。" if notes else "檔位中性，分數不變。", "barrier+empirical_bias+pace_role"

    def _pace_bias_adjustment(self):
        """Return (modifier, note) from this horse's pace role vs predicted tempo.
        Modifier is capped at ±4 and only fires when the speed map is confident
        enough (a recognised role and a non-neutral predicted pace)."""
        # Shadow / opt-in only. A clean A/B over the Flemington+Randwick archive
        # (336 races) showed this term is a wash-to-slightly-negative on the
        # headline Good rate (39.58%→38.39%) while raising perfect-race Gold
        # (10→14) — it does NOT pass the improvement gate, so it is OFF by default.
        # Enable for further tuning/experiments with WC_PACE_BIAS=1.
        if os.environ.get("WC_PACE_BIAS", "0") != "1":
            return 0.0, ""
        speed_map = self._speed_map()
        if not speed_map:
            return 0.0, ""
        horse_num = int(parse_float(self.horse_data.get("horse_number") or self.horse_data.get("number")) or 0)
        if not horse_num:
            return 0.0, ""

        def bucket(name):
            return {int(x) for x in (speed_map.get(name) or []) if str(x).strip().isdigit() or isinstance(x, int)}

        role = None
        for name in ("leaders", "on_pace", "pressers", "mid_pack", "closers"):
            if horse_num in bucket(name):
                role = name
                break
        if role is None:
            return 0.0, ""

        pace = str(speed_map.get("predicted_pace") or speed_map.get("expected_pace") or "")
        n_lead = len(bucket("leaders"))
        n_press = len(bucket("pressers"))
        # Classify tempo: slow/controlled vs hot/fast vs neutral.
        slow = any(t in pace for t in ("極慢", "慢", "controlled", "slow")) or (n_lead == 0 and n_press <= 1)
        fast = any(t in pace for t in ("極快", "快", "hot", "fast", "genuine")) or (n_lead + n_press >= 5)
        if slow == fast:  # neutral or ambiguous → no adjustment
            return 0.0, ""

        if slow:
            table = {"leaders": 3.0, "on_pace": 3.0, "pressers": 1.5, "mid_pack": 0.0, "closers": -3.0}
            tempo = "慢步速"
        else:
            table = {"closers": 3.0, "mid_pack": 1.0, "pressers": -1.0, "on_pace": -2.0, "leaders": -3.0}
            tempo = "快步速"
        adj = max(-4.0, min(4.0, table.get(role, 0.0)))
        if abs(adj) < 0.01:
            return 0.0, ""
        role_zh = {"leaders": "領放", "on_pace": "貼前", "pressers": "跟前", "mid_pack": "守中", "closers": "後上"}
        sign = "受惠" if adj > 0 else "受制"
        return adj, f"步速形勢: 預測{tempo}，本馬屬{role_zh.get(role, role)}{sign} ({adj:+.1f})"

    def _jockey_rating_profile(self, jockey: str):
        if not jockey:
            return None
        jockey_cache, _ = _load_named_rating_stats()
        return jockey_cache.get(_normalize_rating_identity(jockey))

    def _trainer_rating_profile(self, trainer: str):
        if not trainer:
            return None
        _, trainer_cache = _load_named_rating_stats()
        return trainer_cache.get(_normalize_rating_identity(trainer))

    def _rating_tier_text(self, tier: str, kind: str):
        if kind == "jockey":
            mapping = {
                "T1": "Tier 1 頂級騎師",
                "T2": "Tier 2 主力騎師",
                "T3": "Tier 3 發展型騎師",
            }
        else:
            mapping = {
                "T1": "Tier 1 精英馬房",
                "T2": "Tier 2 主力馬房",
                "T3": "Tier 3 標準馬房",
            }
        return mapping.get(str(tier or "").strip(), "中性級別")

    # LY（去年官方全季）收縮參數：prior=archive 池化騎師上名率（702場實測 0.365 —
    # 唔好用 0.30 直覺值，會全體抬高）、k=收縮樣本、spread=映射斜率。
    # A/B（2026-07-11，702場，修正 regex 後真數據）：LY 全面取代 curated DB → A窗蝕
    # （96 vs 100）；「DB 命中用 DB、冇先用 LY 補」@prior .365/s100 = GGP 475→478、
    # A窗 100、B窗 37→40，champ +0.9pp、box4 +0.5pp，全指標零倒退，同時擊敗
    # 「非 DB 歸中性」(476) → LY 普及層（鄉村/新面孔騎師）有真訊號。
    _JOCKEY_LY_PRIOR = 0.365
    _JOCKEY_LY_K = 20.0
    _JOCKEY_LY_SPREAD = 100.0

    def _jockey_ly_score(self):
        ly = self.data.get("jockey_ly") or {}
        rides = parse_float(ly.get("rides"))
        if not rides or rides <= 0:
            return None
        places = float(parse_float(ly.get("places")) or 0)
        rate = (places + self._JOCKEY_LY_K * self._JOCKEY_LY_PRIOR) / (rides + self._JOCKEY_LY_K)
        score = clip_score(60.0 + (rate - self._JOCKEY_LY_PRIOR) * self._JOCKEY_LY_SPREAD)
        return score, rate, int(rides), places

    def _jockey_score(self):
        jockey = self._clean_identity(self.horse_data.get("jockey"))
        detail = {"lines": [], "source": ""}
        self.jockey_detail = detail
        rating = self._jockey_rating_profile(jockey)
        if rating:
            score = rating["base_score"]
            tier_text = self._rating_tier_text(rating.get("tier"), "jockey")
            note = f"{jockey} · {tier_text}"
            if rating.get("confidence") == "provisional":
                note += "（暫定補名）"
            detail["source"] = "db"
            detail["lines"] = [f"{tier_text} → {clip_score(score):.0f} 分"]
            jly = self.data.get("jockey_ly") or {}
            if jly.get("rides"):
                rides = int(jly["rides"]); places = int(jly.get("places") or 0); wins = int(jly.get("wins") or 0)
                detail["lines"].append(
                    f"去年官方：{rides} 騎、{wins} 冠 {places} 上名"
                    f"（勝率 {wins / rides * 100:.0f}%、上名率 {places / rides * 100:.0f}%）")
            return score, f"{note}，騎師分 {clip_score(score):.1f}。", "jockey_rating_db"

        # 普及覆蓋層（2026-07-11）：DB 冇名（尤其鄉村/外州騎師）用 LY 官方全季統計，
        # 上名率經樣本收縮 — 細樣本鄉村好成績會被拉返向平均，唔會亂畀高分。
        ly = self._jockey_ly_score()
        if ly is not None:
            score, rate, rides, places = ly
            raw_rate = places / rides if rides else 0
            detail["source"] = "ly"
            detail["lines"] = [
                f"去年官方全季：{rides} 騎、上名 {int(places)} 次（原始上名率 {raw_rate * 100:.0f}%）",
                f"樣本收縮（樣本越少越拉向基準）後 {rate * 100:.0f}%，全國基準 {self._JOCKEY_LY_PRIOR * 100:.0f}%",
                f"高過基準加分、低過扣分 → {clip_score(score):.1f} 分（60 為中性）",
            ]
            return score, (f"{jockey} 去年官方 {rides} 騎、上名 {int(places)} 次"
                           f"（收縮後上名率 {rate * 100:.0f}%，全國基準 {self._JOCKEY_LY_PRIOR * 100:.0f}%），"
                           f"騎師分 {clip_score(score):.1f}。"), "jockey_ly_stats"

        # 最後 fallback：舊 token 名單（LY 100% 覆蓋下極少用到）
        score = 60
        elite_tokens = (
            "McDonald", "Rawiller", "Pike", "Allen", "King", "Melham",
            "Collett", "Berry", "Clark", "Hyeronimus", "Schiller", "Lloyd",
            "Shinn", "Zahra", "Lane", "Bowman", "Kah", "Prebble", "Parr"
        )
        solid_tokens = ("McEvoy", "Layt", "Bayliss", "Moore", "Roper", "Costin", "Bullock", "Gibbons", "Jones")
        if any(token in jockey for token in elite_tokens):
            score += JOCKEY_MICRO_WEIGHTS.get("elite_bonus", 12.0)
            detail["source"] = "token"
            detail["lines"] = [f"名單 fallback：高階騎師 +{JOCKEY_MICRO_WEIGHTS.get('elite_bonus', 12.0):.0f} → {clip_score(score):.0f} 分"]
            return score, f"{jockey} 屬高階騎師，騎師分 {clip_score(score):.1f}。", "jockey_name_fallback"
        if any(token in jockey for token in solid_tokens):
            score += JOCKEY_MICRO_WEIGHTS.get("solid_bonus", 6.0)
            detail["source"] = "token"
            detail["lines"] = [f"名單 fallback：一級半騎師 +{JOCKEY_MICRO_WEIGHTS.get('solid_bonus', 6.0):.1f} → {clip_score(score):.0f} 分"]
            return score, f"{jockey} 屬有基本把握嘅一級半騎師，騎師分 {clip_score(score):.1f}。", "jockey_name_fallback"
        detail["source"] = "neutral"
        detail["lines"] = ["資料庫／官方統計均無記錄 → 中性 60 分"]
        return score, f"{jockey or '騎師資料'} 屬中性配置，騎師分 {clip_score(score):.1f}。", "jockey_name_fallback"

    def _trainer_score(self):
        trainer = self._clean_identity(self.horse_data.get("trainer"))
        rating = self._trainer_rating_profile(trainer)
        score = rating["base_score"] if rating else 60
        detail = {"base": round(float(score), 1), "base_label": "", "adjustments": [],
                  "final": None, "ly_line": ""}
        self.trainer_detail = detail
        tly = self.data.get("trainer_ly") or {}
        if tly.get("rides"):
            _r = int(tly["rides"]); _p = int(tly.get("places") or 0); _w = int(tly.get("wins") or 0)
            detail["ly_line"] = (f"去年官方：{_r} 場、{_w} 冠 {_p} 上名"
                                 f"（勝率 {_w / _r * 100:.0f}%、上名率 {_p / _r * 100:.0f}%）")
        notes = []

        def add(delta, factor, evidence=""):
            nonlocal score
            score += delta
            detail["adjustments"].append({"delta": round(float(delta), 2),
                                          "factor": factor, "evidence": evidence})
            notes.append(factor)

        if rating:
            tier_text = self._rating_tier_text(rating.get("tier"), "trainer")
            tier_note = tier_text
            if rating.get("confidence") == "provisional":
                tier_note += "（暫定補名）"
            detail["base_label"] = tier_text
            notes.append(tier_note)
        else:
            strong_tokens = (
                "Waller", "Maher", "Waterhouse", "Bott", "Hayes", "Baker",
                "Freedman", "Price", "Payne", "Pride", "Snowden", "Charlton",
                "Hawkes", "O'Shea", "Conners", "Cummings", "Gollan", "Lees", "Neasham", "Moody"
            )
            if any(token in trainer for token in strong_tokens):
                add(TRAINER_MICRO_WEIGHTS.get("elite_bonus", 12.0), "全國強勢班底", "名單 fallback")
                detail["base_label"] = "資料庫無記錄，中性起步"
            else:
                detail["base_label"] = "資料庫無記錄，中性起步"
        if "Waller" in trainer and self._career_starts() == 0:
            add(TRAINER_MICRO_WEIGHTS.get("waller_debut_bonus", 4.0), "初出馬由 Waller 系統部署", "")
            self.reason_codes.append("waller_debut_positive")
        track_stats = self._trainer_track_stats()
        track_ev = (f"馬房同場館 {int(track_stats.get('runs', 0))} 次、"
                    f"上名率 {track_stats.get('place_rate', 0.0) * 100:.0f}%")
        if track_stats.get("runs", 0) >= 20 and track_stats.get("place_rate", 0.0) >= 0.44:
            add(TRAINER_MICRO_WEIGHTS.get("track_high_vol_high_place_bonus", 7.0),
                "今場場館高密度高上名", track_ev)
        elif track_stats.get("runs", 0) >= 12 and track_stats.get("place_rate", 0.0) >= 0.40:
            add(TRAINER_MICRO_WEIGHTS.get("track_med_vol_high_place_bonus", 5.0),
                "今場場館穩定上名", track_ev)
        elif track_stats.get("runs", 0) >= 8 and track_stats.get("place_rate", 0.0) >= 0.32:
            add(TRAINER_MICRO_WEIGHTS.get("track_med_vol_med_place_bonus", 3.0),
                "今場場館有基本對位", track_ev)
        elif track_stats.get("runs", 0) >= 8 and track_stats.get("place_rate", 0.0) < 0.18:
            add(TRAINER_MICRO_WEIGHTS.get("track_low_place_pen", -2.0),
                "今場場館樣本未見承托", track_ev)
        detail["final"] = round(clip_score(score), 2)
        note = "；".join(notes) if notes else f"{trainer or '練馬師資料'} 反映馬房部署基礎"
        return score, f"{note}，練馬師分 {clip_score(score):.1f}。", "trainer_name+trainer_track_stats"

    def _jockey_horse_fit_score(self):
        jockey = self._clean_identity(self.horse_data.get("jockey"))
        trainer = self._clean_identity(self.horse_data.get("trainer"))
        score = 60
        notes = []
        weight = parse_float(self.horse_data.get("weight"))
        trial_count = int(parse_float(self.data.get("trial_count")) or len(self._trial_places()))
        trial_top3 = int(parse_float(self.data.get("trial_top3_count")) or sum(1 for place in self._trial_places() if place <= 3))
        status_cycle = self._status_cycle_text()
        stage_stats = self._stage_stats()
        top_jockey = self._is_top_jockey(jockey)
        top_trainer = self._is_top_trainer(trainer)
        current_formal_rides = self._current_jockey_formal_rides()
        current_formal_places = self._current_jockey_formal_places()
        current_formal_wins = self._current_jockey_formal_wins()
        current_trial_rides = self._current_jockey_trial_rides()
        current_trial_top3 = self._current_jockey_trial_top3()
        latest_official_jockey = self._latest_official_jockey()
        latest_official_rides = self._latest_official_jockey_formal_rides()
        latest_official_places = self._latest_official_jockey_formal_places()
        latest_official_wins = self._latest_official_jockey_formal_wins()
        best_formal_jockey = self._best_formal_jockey()
        best_formal_rides = self._best_formal_jockey_rides()
        best_formal_places = self._best_formal_jockey_places()
        best_formal_wins = self._best_formal_jockey_wins()
        current_vs_best = self._current_vs_best_jockey_brief()
        jockey_change_signal = self._jockey_change_signal()
        combo_stats = self._current_track_combo_stats()
        trainer_track_stats = self._trainer_track_stats()
        current_place_rate = safe_ratio(current_formal_places, current_formal_rides)
        latest_official_place_rate = safe_ratio(latest_official_places, latest_official_rides)

        # 逐項加減分都經 add() 記錄（因子＋原始數據），令報告可以完整追溯人馬配搭分。
        adjustments = []
        base_score = float(score)

        def add(delta, note_text, evidence=""):
            nonlocal score
            delta = float(delta)
            score += delta
            notes.append(note_text)
            if delta:
                adjustments.append({
                    "factor": note_text,
                    "delta": round(delta, 2),
                    "evidence": str(evidence or "").strip(),
                })

        # debut_top_trainer / young_top_jt 權重已被 ML 歸零 — 死支 2026-07-11 刪除，
        # 免報告出「有講冇分」嘅因子。
        if trial_count >= 2 and trial_top3 >= 2:
            add(FIT_MICRO_WEIGHTS.get("trial_ok_bonus", 4.0), "試閘交代密度足夠",
                f"近期試閘{trial_count}課、{trial_top3}課入前三")
            if top_jockey or top_trainer:
                add(FIT_MICRO_WEIGHTS.get("trial_ok_top_jt_bonus", 2.0), "備戰同騎練配置方向一致",
                    "試閘密度足夠且配頂級騎/練")
        if current_formal_rides > 0:
            add(min(FIT_MICRO_WEIGHTS.get("current_formal_cap", 6.0), current_formal_places * FIT_MICRO_WEIGHTS.get("current_formal_mult", 2.0) + current_formal_wins * FIT_MICRO_WEIGHTS.get("current_formal_mult", 2.0)),
                f"現役騎師曾策騎此駒 {current_formal_rides} 次正式賽",
                f"{jockey}策此駒{current_formal_rides}次：{current_formal_wins}勝{current_formal_places}上名")
            if current_formal_places * 2 >= max(1, current_formal_rides):
                add(FIT_MICRO_WEIGHTS.get("current_basic_fit_bonus", 2.0), "現役騎師對此駒有基本交代",
                    f"上名{current_formal_places}次／{current_formal_rides}騎")
            if current_formal_rides >= 2 and current_place_rate >= 0.66:
                add(FIT_MICRO_WEIGHTS.get("current_high_fit_bonus", 2.0), "現役騎師對此駒配合率偏高",
                    f"配合率{current_place_rate * 100:.0f}%（{current_formal_rides}騎)")
        elif current_trial_rides > 0 and current_trial_top3 > 0:
            add(min(FIT_MICRO_WEIGHTS.get("current_trial_cap", 4.0), current_trial_top3 * FIT_MICRO_WEIGHTS.get("current_trial_mult", 2.0)),
                "現役騎師已透過試閘熟習此駒",
                f"{jockey}試閘策此駒{current_trial_rides}次、{current_trial_top3}次入前三")
        # 「歷來最佳配搭」family 2026-07-11 退出計分：best_formal_mult 被 ML search 推成
        # 負數（−0.06 — 沿用最佳配搭反而扣分，語義反轉 bug），成族 ablation 移除後
        # GGP +2／A窗 +1／B窗平 → 移除係贏。歷來最佳配搭資料仍喺數據錨點顯示。
        if best_formal_jockey and best_formal_rides > 0 and current_vs_best:
            notes.append(current_vs_best)
        if latest_official_jockey and latest_official_jockey != jockey and latest_official_rides > 0:
            # latest_upgrade_bonus 權重已被 ML 歸零 — 死支刪除（2026-07-11），
            # 免報告出現「有講冇分」嘅因子。
            if current_formal_rides == 0 and latest_official_place_rate >= 0.50:
                add(FIT_MICRO_WEIGHTS.get("leave_proven_jockey_pen", -4.0), "今場離開上仗已證明配搭",
                    f"上仗{latest_official_jockey}對此駒上名率{latest_official_place_rate * 100:.0f}%")
            elif current_formal_rides > 0 and latest_official_place_rate > current_place_rate + 0.20:
                add(FIT_MICRO_WEIGHTS.get("latest_downgrade_pen", -3.0), "今場騎師對此駒往績未及上仗騎師",
                    f"今場上名率{current_place_rate * 100:.0f}% vs 上仗{latest_official_jockey} {latest_official_place_rate * 100:.0f}%")
        # 同場館騎練組合 family 2026-07-11 退出計分（display-only）：成族逐項 ablation
        # 全指標零變化（觸發率太低/幅度太細）— 統計照喺 note 同錨點交代，唔再入分。
        combo_evidence = (f"{jockey}×{trainer}同場館{int(combo_stats.get('runs', 0))}次，"
                          f"上名率{combo_stats.get('place_rate', 0.0) * 100:.0f}%、勝率{combo_stats.get('win_rate', 0.0) * 100:.0f}%")
        if combo_stats.get("runs", 0) >= 5:
            if combo_stats.get("place_rate", 0.0) >= 0.45:
                notes.append(f"今場場館騎練組合已有穩定上名輸出（{combo_evidence}，不入分）")
            elif combo_stats.get("place_rate", 0.0) < 0.15:
                notes.append(f"今場場館騎練組合過往交代偏淡（{combo_evidence}，不入分）")
        if jockey_change_signal:
            if "沿用歷來最佳配搭" in jockey_change_signal:
                add(FIT_MICRO_WEIGHTS.get("signal_best_jockey_bonus", 4.0), "沿用歷來最佳人馬配搭", jockey_change_signal)
            elif "較強騎師" in jockey_change_signal:
                add(FIT_MICRO_WEIGHTS.get("signal_upgrade_bonus", 5.0), "今場屬升級換騎", jockey_change_signal)
            elif "換下較高級騎師" in jockey_change_signal:
                add(FIT_MICRO_WEIGHTS.get("signal_downgrade_pen", -4.0), "今場屬降級換騎", jockey_change_signal)
            elif "沿用上仗騎師" in jockey_change_signal:
                add(2, "沿用上仗騎師，部署連貫", jockey_change_signal)
            elif "試閘手接手" in jockey_change_signal:
                add(2, "試閘手接手，備戰線完整", jockey_change_signal)
            elif "回配" in jockey_change_signal:
                add(2, "回配熟手騎師", jockey_change_signal)
        # 雜項硬編碼調整 family 2026-07-11 退出計分（display-only）：成族 ablation
        # 全指標零變化。有意思嘅背景（減磅/週期/首仗二出往績）保留做 note。
        if status_cycle in {"First-up", "久休復出"} and stage_stats["first_up"]["places"] > 0:
            notes.append(f"過往首仗上陣有基本交代（{stage_stats['first_up'].get('runs', '')}次{stage_stats['first_up']['places']}上名，不入分）")
        if status_cycle in {"Second-up", "二出"} and stage_stats["second_up"]["places"] > 0:
            notes.append(f"二出歷史有承接（{stage_stats['second_up'].get('runs', '')}次{stage_stats['second_up']['places']}上名，不入分）")
        if "(a)" in jockey and weight and weight >= 58:
            notes.append(f"見習減磅可幫手化解負磅壓力（原負磅{weight:.1f}kg，不入分）")
        if trainer in {"", "Unknown"}:
            notes.append("馬房資料不完整")
        self.jt_fit_detail = {
            "base": round(base_score, 2),
            "final": round(clip_score(score), 2),
            "adjustments": adjustments,
        }
        note = "；".join(notes) if notes else "未見特別人馬部署訊號"
        return score, f"{note}。人馬配搭分 {clip_score(score):.1f}。", "jockey_trainer_fit+stage_stats+trial_continuity+formguide_jockey_history+track_combo_stats"

    def _matrix_reasoning(self, matrix_scores, feature_scores, feature_notes):
        return {
            "stability": self._reason_bundle(
                "stability",
                matrix_scores["stability"],
                feature_scores,
                feature_notes,
                "form_score",
                "consistency_score",
            ),
            "pace_perf": self._reason_bundle(
                "pace_perf",
                matrix_scores.get("pace_perf", 60),
                feature_scores,
                feature_notes,
                "pace_figure_score",
                "sectional_score",
                "trial_score",
            ),
            "race_shape": self._reason_bundle(
                "race_shape",
                matrix_scores["race_shape"],
                feature_scores,
                feature_notes,
                "pace_map_score",
            ),
            "jockey_trainer": self._reason_bundle(
                "jockey_trainer",
                matrix_scores["jockey_trainer"],
                feature_scores,
                feature_notes,
                "jockey_score",
                "trainer_score",
                "jockey_horse_fit_score",
            ),
            "class_weight": self._reason_bundle(
                "class_weight",
                matrix_scores["class_weight"],
                feature_scores,
                feature_notes,
                "class_score",
                "rating_score",
                "weight_score",
            ),
            "track": self._reason_bundle(
                "track",
                matrix_scores["track"],
                feature_scores,
                feature_notes,
                "track_score",
            ),
            "form_line": self._reason_bundle(
                "form_line",
                matrix_scores["form_line"],
                feature_scores,
                feature_notes,
                "formline_score",
                "form_score",
            ),
        }

    def _reason_bundle(self, key, score, feature_scores, feature_notes, *component_keys):
        label = self._matrix_label(key)
        return {
            "label": label,
            "score": round(clip_score(score), 2),
            "tone": self._matrix_summary(key, score),
            "text": self._describe_matrix(key, score, feature_scores),
            "components": [
                {
                    "key": component_key,
                    "label": self._feature_label(component_key),
                    "score": round(feature_scores.get(component_key, 60), 2),
                    "note": str(feature_notes.get(component_key, "")).strip(),
                }
                for component_key in component_keys
            ],
            "anchors": self._matrix_anchor_lines(key),
        }

    def _describe_matrix(self, key, score, feature_scores):
        describers = {
            "stability": self._describe_stability_matrix,
            "pace_perf": self._describe_pace_perf_matrix,
            "race_shape": self._describe_race_shape_matrix,
            "jockey_trainer": self._describe_jockey_trainer_matrix,
            "class_weight": self._describe_class_weight_matrix,
            "track": self._describe_track_matrix,
            "form_line": self._describe_form_line_matrix,
        }
        describer = describers.get(key)
        if describer:
            return describer(score, feature_scores)
        return self._matrix_summary(key, score)

    def _describe_pace_perf_matrix(self, score, feature_scores):
        """段速表現判讀 — 短而狠：一句定調 → 一句交叉解讀（真快定形勢造就／
        引擎定一 burst）→ 一句數據信心。逐項計法喺評分構成 detail 攤開，唔喺度重覆。"""
        pace = feature_scores.get("pace_figure_score", 60)
        sec = feature_scores.get("sectional_score", 60)
        pd = getattr(self, "pace_figure_detail", {}) or {}
        has_pf = pd.get("state") == "ok"
        has_pi = bool(self._sectional_breakdown().get("has_pi"))

        if has_pf and pace >= 72:
            verdict = "末段實測快過場均——真數據唔係投射，行到位末段就有波幅。"
        elif has_pf and pace <= 48:
            verdict = "末段實測明顯慢過場均，難靠速度取勝，要靠形勢或級數補。"
        elif has_pf and pace <= 56:
            verdict = "末段實測略慢過場均，速度面冇著數。"
        elif has_pf:
            verdict = "末段實測貼近場均，速度面中性。"
        elif has_pi:
            verdict = "冇實測段速，只有 PI 位置增益作旁證，呢一格參考價值有限。"
        else:
            verdict = "段速證據不足，呢一格唔好過份解讀。"

        cross = ""
        if has_pf and has_pi:
            if pace >= 68 and sec >= 55:
                cross = "PI 同實測方向一致，末段輸出可信度高。"
            elif pace >= 68 and sec < 45:
                cross = "實測快但 PI 平平——似短促一 burst 多過持續引擎，要行運先兌現。"
            elif pace < 56 and sec >= 60:
                cross = "PI 靚但實測唔快——之前嘅位置增益可能係場面崩潰執位，唔好照單全收。"

        conf = (f"強（實測 {int(pd.get('runs') or 0)} 場）" if has_pf
                else "中（只有 PI 位置增益）" if has_pi
                else "弱（只餘試閘／無數據）")
        return " ".join(x for x in (verdict, cross, f"段速證據信心：{conf}。") if x)

    def _describe_stability_matrix(self, score, feature_scores):
        recent = str(self.data.get("recent_form") or self.horse_data.get("recent_form") or "").strip()
        status = self._status_cycle_display() or "狀態週期未明"
        trend = self._deduped_trend_summary() or "近況輪廓未算鮮明"
        latest_note = self._latest_official_note_brief()
        forgiveness = self._forgiveness_brief()
        repeatability = self._repeatability_brief()
        # 缺料時直接省略該子句，唔好輸出「狀態週期未明」「輪廓未算鮮明」呢類佔位話
        status_known = bool(status) and "未明" not in status
        trend_known = bool(trend) and "未算鮮明" not in trend
        if self._career_starts() == 0:
            opener = "此駒正式賽樣本仍薄，呢一格主要靠備戰完整度、試閘交代同狀態週期去判備戰程度。"
        elif recent:
            opener = f"近績 {recent}"
            if status_known:
                opener += f"，處於{status}階段"
            if trend_known:
                opener += f"，走勢大致呈「{trend}」"
            opener += "。"
        elif status_known:
            opener = f"正式近績樣本有限，穩定性主要依賴 {status} 週期定位判斷。"
        else:
            opener = "正式近績樣本有限，穩定性主要靠試閘同備戰資料判斷。"
            
        if feature_scores["form_score"] >= 72 and feature_scores["consistency_score"] >= 68:
            assessment = "連仗交出接近表現證明戰鬥力企穩，唔係單靠一場偶發水準撐起，具備堅實嘅爭勝底氣。"
        elif feature_scores["form_score"] <= 58 or feature_scores["consistency_score"] <= 58:
            assessment = "近態未算企得好穩，評分上仍然要留低少少問號。"
        else:
            assessment = "近況有啲底，但未到可以完全放膽追捧嘅絕對穩定期。"
            
        if latest_note:
            assessment += f" 上仗備註：{latest_note}。"
        if forgiveness:
            assessment += f" 寬恕條件：{forgiveness}。"
        if repeatability:
            assessment += f" 同類設置下，{repeatability}。"
            
        return " ".join(part for part in (opener, assessment) if part)

    def _describe_race_shape_matrix(self, score, feature_scores):
        """短而狠：檔位一句定調 → 場地紀錄一句 → 一句形勢結論。
        逐項計法喺評分構成 detail 攤開，判讀唔覆述。"""
        style = self._running_style() or self._tactical_position_text() or ""
        style_parts = [p.strip() for p in str(style).split("/")]
        if len(style_parts) > 1 and len(set(style_parts)) == 1:
            style = style_parts[0]
        barrier = self.horse_data.get("barrier")
        pm = feature_scores["pace_map_score"]

        if pm >= 68:
            draw_v = f"排 {barrier} 檔據場地統計係著數位"
        elif pm <= 56:
            draw_v = f"排 {barrier} 檔據場地統計偏蝕，走位容錯較低"
        else:
            draw_v = f"排 {barrier} 檔屬中性"
        if style:
            draw_v += f"，預期「{style}」跑法"
        return draw_v + "。"

    def _describe_jockey_trainer_matrix(self, score, feature_scores):
        jockey = self._clean_identity(self.horse_data.get("jockey")) or "騎師資料未明"
        trainer = self._clean_identity(self.horse_data.get("trainer")) or "練馬師資料未明"

        # 判讀短而狠（2026-07-11 Phase C）：一句定調 → 最強訊號/主要扣分各一句，
        # 唔重覆逐項明細（明細喺評分構成 detail 攤開）。
        fit = feature_scores["jockey_horse_fit_score"]
        j_s = feature_scores["jockey_score"]
        t_s = feature_scores["trainer_score"]
        adjs = (self.jt_fit_detail or {}).get("adjustments") or []
        top_pos = max((a for a in adjs if a.get("delta", 0) > 0),
                      key=lambda a: a["delta"], default=None)
        top_neg = min((a for a in adjs if a.get("delta", 0) < 0),
                      key=lambda a: a["delta"], default=None)
        combo = f"由 {jockey} 配 {trainer}。"
        if fit >= 74:
            assessment = "騎練部署積極，人馬熟習度同備戰方向一致——有出擊意圖嘅配置。"
        elif fit <= 55 or (top_neg and top_neg.get("delta", 0) <= -3):
            assessment = "人馬部署有保留位，注碼上唔好當佢係主動出擊。"
        elif j_s >= 68 and t_s >= 66:
            assessment = "騎練有牌面，但同呢匹馬未見專屬默契。"
        elif j_s <= 58 and t_s <= 58:
            assessment = "騎練牌面平平，呢一格幫唔到手，要靠馬匹自己交代。"
        else:
            assessment = "人馬配置中性，未見明顯部署訊號。"
        if top_pos:
            assessment += f" 最強訊號：{top_pos['factor']}（{top_pos['delta']:+.1f}）。"
        if top_neg:
            assessment += f" 主要扣分：{top_neg['factor']}（{top_neg['delta']:+.1f}）。"
        # 歷來配套/最佳配搭/換騎/同場樣本等原始證據已喺數據錨點逐行列出，判讀唔重覆。
        return " ".join(part for part in (combo, assessment) if part)

    def _describe_class_weight_matrix(self, score, feature_scores):
        """短而狠：今場班次/負磅一句定調 → 一句能力對位結論。
        逐項計法（含 rating 缺失代理）喺評分構成 detail 攤開。"""
        class_move = self._class_move_display()
        weight = parse_float(self.horse_data.get("weight"))
        race_class = self._race_class_text()
        cs = feature_scores["class_score"]
        rs = feature_scores["rating_score"]
        ws = feature_scores["weight_score"]

        head = f"今仗 {race_class}"
        if weight is not None:
            head += f"，負 {weight:.1f}kg"
        if class_move and "降班" in class_move:
            head += "，降班係實際著數"
        elif class_move and "升班" in class_move:
            head += "，升班挑戰要打折睇"
        head += "。"

        if cs >= 68 and rs >= 66 and ws >= 68:
            verdict = "班次、能力對位同負磅都舒適，外在條件順手。"
        elif cs <= 56 or rs <= 56 or ws <= 56:
            verdict = "班次、能力對位或負磅其中一邊偏緊，要靠實力超水準兌現。"
        else:
            verdict = "班次、能力對位同負磅大致合理，未見明顯阻力亦未見甜頭。"
        return head + " " + verdict

    def _describe_track_matrix(self, score, feature_scores):
        """短而狠：場地/地狀適應一句定調 ＋（濕地）風險一句。逐項計法喺評分構成攤開。"""
        ts = feature_scores["track_score"]
        wet_state = self._wet_state()
        if ts >= 70:
            verdict = "同場/今日地狀有實績支持，場地唔會成為絆腳石。"
        elif ts <= 54:
            verdict = "場地/地狀往績未見支持，發揮要打折睇。"
        else:
            verdict = "場地適應有基礎，應付到今日地狀。"
        if wet_state in {"soft7plus", "heavy"} and not self._has_verified_wet_place():
            verdict += " 但爛地實績未經驗證，轉場風險高。"
        return verdict

    def _describe_form_line_matrix(self, score, feature_scores):
        formline = self._formline_level() or "賽績線摘要未明"
        latest_formal = self._latest_record_summary("正式")
        headwinner = self._formline_headwinner()
        followup = self._formline_followup_brief()

        # 純參考維度：權重 0，唔入綜合戰力分／排名（已 ML 驗證無上位訊號）。
        tag = "（僅供參考，不計入排名）"
        if feature_scores["formline_score"] >= 72:
            assessment = f"賽績線屬「{formline}」級別，對手線有強勁承接{tag}。"
        elif feature_scores["formline_score"] <= 56:
            assessment = f"賽績線級別評為「{formline}」，對手後續支持力弱{tag}。"
        else:
            assessment = f"賽績線屬「{formline}」級別，對手線有一定參考價值{tag}。"

        # 兌現度（franking）一句總結：對手其後有冇再贏，係條線可唔可信嘅關鍵
        all_rows = self._formline_rows()
        # 只計有效行（跳過查冊失敗嘅延續行），同數據錨點嘅明細表口徑一致
        rows = [r for r in all_rows
                if not (str(r.get("date", "")).strip() in {"查冊失敗", "-", ""} and not str(r.get("opponent", "")).strip())]
        frank = ""
        if rows:
            wins = 0
            failed = 0
            for row in rows:
                nr = str(row.get("next_result", ""))
                m = re.search(r"出\s*\d+\s*次:\s*(\d+)\s*勝", nr)
                if m and int(m.group(1)) > 0:
                    wins += 1
                if "查冊失敗" in nr:
                    failed += 1
            if wins >= 2:
                frank = f"兌現度高：{len(rows)}場當中{wins}場嘅對手其後再勝，條線已受賽果驗證。"
            elif wins == 1:
                frank = f"{len(rows)}場當中有1場嘅對手其後再勝，條線有基本背書。"
            elif failed == len(rows):
                frank = f"{len(rows)}場嘅對手後續查冊失敗，兌現度暫時無法驗證。"
            else:
                frank = f"{len(rows)}場嘅對手其後未有再勝，條線暫未有賽果背書。"

        details = []
        if headwinner:
            details.append(f"曾直接交手嘅頭馬：{headwinner}。")
        # 最近正式賽果同對手後續摘要已喺「數據」錨點列出，判讀唔重覆

        return " ".join(part for part in (assessment, frank, " ".join(details)) if part)

    def _l600_speed_brief(self):
        """原始 L600 速度（m/s）作跑法識別 — 各馬得分觸底但速度不同，畀用家分辨。"""
        data = self.data
        avg = parse_float(data.get("timing_600m_avg_speed"))
        best = parse_float(data.get("timing_600m_best_speed"))
        recent = parse_float(data.get("timing_600m_recent_speed"))
        if avg is None and best is None and recent is None:
            return ""
        parts = []
        if avg is not None:
            parts.append(f"平均 {avg:.2f}")
        if best is not None:
            parts.append(f"最快 {best:.2f}")
        if recent is not None:
            parts.append(f"近仗 {recent:.2f}")
        trend = str(data.get("timing_600m_trend") or "").strip()
        count = data.get("timing_l600_entries_count")
        tail = f"；趨勢 {trend}" if trend else ""
        cnt = f"（{count} 場樣本）" if count else ""
        return f"{' / '.join(parts)} m/s{tail}{cnt}"

    def _matrix_anchor_lines(self, key):
        if key == "stability":
            return self._anchor_lines(
                ("近績序列", str(self.data.get("recent_form") or self.horse_data.get("recent_form") or "").strip()),
                ("Last 10 / 警告", str(self.data.get("warning_line") or self.data.get("last10_raw") or "").strip()),
                ("狀態週期", self._status_cycle_display()),
                ("趨勢總評", self._deduped_trend_summary()),
                ("寬恕因素", self._forgiveness_brief()),
                ("上仗註腳", self._latest_official_note_brief()),
                ("最近正式賽果", self._latest_record_summary("正式")),
                ("試閘交代", self._trial_summary_text()),
            )
        if key == "pace_perf":
            pf_agg = (self.data.get("pf_metrics") or {}).get("pf_aggregates") or {}
            l600d = pf_agg.get("l600_delta_avg")
            pf_line = (f"對基準差 {float(l600d):+.2f}s（{int(pf_agg.get('pf_run_count') or 0)} 場樣本，負數=快過基準）"
                       if l600d is not None else "")
            # 逐項計法已喺評分構成 detail 攤開，錨點只留原始證據
            return self._anchor_lines(
                ("實測 L600（主訊號）", pf_line),
                ("近段 PI 走勢", self._sectional_trend_brief()),
                ("L600 原速（識別用·未入排名）", self._l600_speed_brief()),
                ("試閘交代", self._trial_summary_text()),
            )
        if key == "race_shape":
            # 跑法資訊合併成一條（標籤＋信心），唔再分開出 跑法信心／style evidence／預計走法；
            # 戰術劇本明確標示係「跑法×檔位模板」，唔係實測 trip。
            return self._anchor_lines(
                ("預期跑法", self._run_style_brief()),
                ("近仗 Settled Pattern", self._recent_settled_pattern_brief()),
                ("賽道幾何配套", self._track_fit_brief()),
                ("戰術劇本（跑法×檔位推演·非實測）", self._tactical_scenario_text()),
            )
        if key == "jockey_trainer":
            return self._anchor_lines(
                ("Section內部權重", "騎師 28% / 練馬師 20% / 人馬歷史與換騎 52%"),
                ("騎師 / 練馬師", self._jockey_trainer_pair_text()),
                ("人馬歷史", self._current_jockey_history_brief()),
                ("上仗正式賽騎師", self._latest_official_jockey_brief()),
                ("歷來最佳配搭", self._best_jockey_history_brief()),
                ("今場 vs 歷來最佳", self._current_vs_best_jockey_brief()),
                ("換騎訊號", self._jockey_change_signal()),
                ("同場騎練組合", self._track_combo_brief()),
                ("馬房場館履歷", self._trainer_track_brief()),
                ("已知合作騎師", self._known_jockeys_brief()),
                ("試閘交代", self._trial_summary_text()),
                ("狀態週期", self._status_cycle_display()),
                ("首次/二次上陣往績", str(self.data.get("stage_stats_line") or "").strip()),
            )
        if key == "class_weight":
            return self._anchor_lines(
                ("今場班次", self._race_class_text()),
                ("班次變動", self._class_move_display()),
                ("官方 Rating", self._horse_rating_text()),
                ("Rating 對位", self._field_rating_brief()),
                ("負磅", self._weight_text()),
                ("場內磅差", self._field_weight_brief()),
                ("最新PF/RT", self._latest_l600_rt_brief()),
                ("生涯背景", str(self.data.get("career_record_line") or "").strip()),
                ("上仗結果(Racecard)", str(self.data.get("last_finish_line") or "").strip()),
                ("最近正式賽果", self._latest_record_summary("正式")),
            )
        if key == "track":
            return self._anchor_lines(
                ("場地/路線紀錄", str(self.data.get("track_record_line") or "").strip()),
                ("地狀分拆", str(self.data.get("going_stats_line") or "").strip()),
                ("今場掛牌", self._today_going()),
                ("濕地血統", self._wet_bloodline_signal()),
                ("今日場地偏差", self._meeting_bias_brief()),
                ("賽道幾何", self._track_geometry_brief()),
                ("路段提示", self._track_distance_note_brief()),
                ("跑法/檔位配套", self._track_fit_brief()),
                ("最近正式賽果", self._latest_record_summary("正式")),
            )
        if key == "form_line":
            return self._anchor_lines(
                ("賽績線級別", self._formline_level()),
                ("頭馬", self._formline_headwinner()),
                ("對手後續摘要", self._formline_followup_brief()),
                ("最近正式賽果", self._latest_record_summary("正式")),
            )
        return []

    def _anchor_lines(self, *items):
        lines = []
        for label, value in items:
            text = str(value or "").strip()
            if text:
                lines.append(f"{label}: {text}")
        return lines

    def _matrix_label(self, key):
        return {
            "stability": "狀態與穩定性",
            "pace_perf": "段速表現",
            # 舊 key 保留畀歷史 Logic 檔顯示
            "sectional": "段速與引擎",
            "pace_figure": "段速實速（實測L600）",
            "race_shape": "檔位形勢",
            "jockey_trainer": "騎練訊號",
            "class_level": "級數門檻",
            "weight_pressure": "負磅壓力",
            "class_weight": "級數與負重",
            "track": "場地適性",
            "form_line": "賽績線",
        }.get(key, key)

    def _feature_label(self, key):
        return {
            "form_score": "近績分",
            "trial_score": "試閘分",
            "sectional_score": "段速分",
            "pace_figure_score": "段速實速分",
            "pace_map_score": "形勢分",
            "jockey_score": "騎師分",
            "trainer_score": "練馬師分",
            "jockey_horse_fit_score": "人馬配搭分",
            "class_score": "級數分",
            "rating_score": "Rating 分",
            "weight_score": "負磅分",
            "distance_score": "路程分",
            "track_score": "場地分",
            "formline_score": "賽績線分",
            "consistency_score": "穩定性分",
            "health_score": "健康分",
            "confidence_score": "信心分",
        }.get(key, key)

    def _matrix_summary(self, key, score):
        label = self._matrix_label(key)
        if score >= 74:
            return f"{label} 係今場其中一條主要支柱"
        if score >= 68:
            return f"{label} 屬正面支撐範圍"
        if score <= 55:
            return f"{label} 仍然係主要保留位"
        return f"{label} 暫時只算中性參考"

    def _au_grade_computation_transparency(self, matrix_scores, matrix_bands, feature_scores, base_7d_score, ability_score, grade):
        """AU version: Generate computation walkthrough for the 7D matrix."""
        # 舊「核心/半核心/輔助」角色標籤已死（同實際權重脫節，輸出表亦唔再印）；
        # 直接用 _matrix_label ＋ 實際權重，權重百分比先係唯一真相。
        dims = [(key, self._matrix_label(key), float(MATRIX_WEIGHTS.get(key, 0.0))) for key in MATRIX_WEIGHTS]
        rows = []
        lines = []
        weighted_sum = 0.0
        for key, label, weight in dims:
            raw_score = float(matrix_scores.get(key, 60))
            band = matrix_bands.get(key, "➖")
            contribution = round(raw_score * weight, 2)
            weighted_sum += contribution
            rows.append({"key": key, "label": label, "score": round(raw_score, 2),
                         "weight": weight, "contribution": contribution, "band": band})
            # 拿走 [核心/半核心/輔助] 標籤：權重百分比已經表達咗重要性，標籤多餘。
            lines.append(f"| {label} | {raw_score:.1f} | {weight * 100:.1f}% | {contribution:.2f} | {band} |")
        table = "\n".join([
            "| 維度 | 得分 | 權重 | 貢獻 | 判定 |",
            "|:---|---:|---:|---:|:---:|",
            *lines,
        ])
        summary = (
            f"{table}\n\n"
            f"**→ 官方 7D clean ranking score = {base_7d_score:.2f} 分；綜合戰力分 = {ability_score:.2f} 分 → Grade = [{grade}]**"
        )
        # 有計但唔直接入 7D 公式嘅分數 — 一併展示，唔收埋
        ref_bits = []
        for ref_key, ref_label in (("distance_score", "路程分"), ("health_score", "備戰完整度分"), ("confidence_score", "信心分")):
            val = feature_scores.get(ref_key)
            if isinstance(val, (int, float)):
                ref_bits.append(f"{ref_label} {float(val):.1f}")
        if ref_bits:
            summary += "\n**📎 參考分（不直接入7D公式）：** " + "、".join(ref_bits)
        if self.risk_flags:
            flag_descriptions = []
            for flag in sorted(set(self.risk_flags)):
                desc = self._au_risk_flag_description(flag)
                if desc:
                    flag_descriptions.append(f"  - {desc}")
            if flag_descriptions:
                summary += "\n\n**⚠️ 風險標記:**\n" + "\n".join(flag_descriptions)
        return {"detail_lines": lines, "rows": rows, "weighted_sum": round(weighted_sum, 2), "summary": summary}

    def _au_risk_flag_description(self, flag):
        mapping = {
            "high_consumption_load": "近仗走位消耗偏高，末段續航能力要再觀察",
            "top_weight": "頂磅環境要自己讓人，發揮要求更高",
            "pace_burn_risk": "若早段互燒，末段有機會先消耗後失速",
            "distance_unproven": "路程仍未正式證明，末端續航力未可完全信任",
            "debut_form_neutral": "初出馬缺正式賽經驗，變數自然較大",
            "debut_distance_unproven": "初出馬未經路程實戰驗證",
        }
        return mapping.get(flag, flag)

    def _clean_identity(self, value):
        text = str(value or "").strip()
        if not text:
            return ""
        text = FIELD_TRAILER_RE.sub("", text)
        return text.strip(" |")

    def _career_starts(self):
        value = parse_float(self.horse_data.get("career_race_starts"))
        starts = int(value or 0)
        if starts == 0:
            entries = self._official_entries()
            if entries:
                return len(entries)
        return starts

    def _trial_places(self):
        places = []
        for line in self.facts_section.splitlines():
            if "| 試閘 |" not in line:
                continue
            parts = [part.strip() for part in line.strip().strip("|").split("|")]
            if len(parts) < 8:
                continue
            place_text = parts[7]
            try:
                places.append(int(place_text))
            except ValueError:
                continue
        return places

    def _status_cycle_text(self):
        return str(self.horse_data.get("status_cycle") or "").strip()

    def _status_cycle_display(self):
        value = self._status_cycle_text()
        return {
            "First-up": "久休復出",
            "Second-up": "二出",
            "Third-up": "第三仗",
            "Deep Prep": "長期作戰期",
        }.get(value, value)

    def _deduped_trend_summary(self):
        trend = str(self.horse_data.get("trend_summary") or "").strip()
        status = self._status_cycle_display() or ""
        if not trend:
            return ""
        compact_trend = trend.replace("休後復出", "久休復出").replace("長休復出", "久休復出")
        if status and (compact_trend == status or compact_trend in status or status in compact_trend):
            return ""
        return trend

    def _tactical_position_text(self):
        plan = self.horse_data.get("tactical_plan")
        if isinstance(plan, dict):
            return str(plan.get("expected_position") or "").strip()
        return ""

    def _tactical_scenario_text(self):
        plan = self.horse_data.get("tactical_plan")
        if isinstance(plan, dict):
            return self._neutralize_pace_assumption(str(plan.get("race_scenario") or "").strip())
        return ""

    def _neutralize_pace_assumption(self, text: str) -> str:
        clean = str(text or "").strip()
        for src, dst in (
            ("於偏慢場面下，", "入直路前，"),
            ("在偏慢場面下，", "入直路前，"),
            ("於偏慢場面下", "入直路前"),
            ("在偏慢場面下", "入直路前"),
            ("偏慢場面下", "入直路前"),
            ("於極慢步速下，", "入直路前，"),
            ("在極慢步速下，", "入直路前，"),
            ("於極慢步速下", "入直路前"),
            ("在極慢步速下", "入直路前"),
            ("極慢步速下", "入直路前"),
            ("因應偏慢場面而", "視乎落位而"),
            ("因應偏慢場面", "視乎落位"),
            ("能從容控制場面節奏並", "若能順利放出並"),
            ("控制場面節奏", "控制走位主動權"),
            ("控制步速", "控制走位主動權"),
            ("以騎功彌補場面節奏劣勢", "以騎功修正走位成本"),
            ("場面節奏劣勢", "走位成本劣勢"),
        ):
            clean = clean.replace(src, dst)
        return clean

    # 名單統一（2026-07-11，Bug B）：以 rating DB tier 為唯一真相，token 名單只做
    # DB 冇名時嘅 fallback。舊四套獨立名單互相矛盾（Craig Williams/Damian Lane 喺
    # DB 係 T1 但舊 _is_top_jockey 唔認）。
    def _is_top_jockey(self, jockey: str) -> bool:
        rating = self._jockey_rating_profile(jockey)
        if rating:
            return str(rating.get("tier")) == "T1"
        return any(
            token in jockey
            for token in ("McDonald", "Rawiller", "Berry", "Clark", "Hyeronimus", "Schiller", "Lloyd", "King", "Collett")
        )

    def _is_top_trainer(self, trainer: str) -> bool:
        rating = self._trainer_rating_profile(trainer)
        if rating:
            return str(rating.get("tier")) == "T1"
        return any(
            token in trainer
            for token in ("Waller", "Maher", "Waterhouse", "Bott", "Pride", "Snowden", "Freedman", "Hawkes", "Charlton")
        )

    def _running_style(self):
        text = str(self.data.get("running_style_line") or self.data.get("race_shape_summary") or "")
        if text:
            return text
        for token in ("前領", "居中前", "中後", "後上", "前置", "中段"):
            if token in self.facts_section:
                return token
        return ""

    def _predicted_style(self):
        """Tactical position read (前置／守好位／守中／後上) + the WHY, for the 數據判讀.
        Reference only — never enters the rating matrix. Uses the pre-computed
        running_style_line / tactical_plan; WHY comes from the race scenario."""
        raw = self._running_style() or self._tactical_position_text()
        token = ""
        for cand in ("前領", "前置", "居中前", "跟前", "守好位", "中後", "後上",
                     "守中", "中段", "居中"):
            if cand in str(raw):
                token = cand
                break
        if not token:
            return None
        label_map = {"前領": "前置", "前置": "前置", "居中前": "守好位", "跟前": "守好位",
                     "守好位": "守好位", "中後": "後上", "後上": "後上",
                     "守中": "守中", "中段": "守中", "居中": "守中"}
        label = label_map.get(token, token)
        conf = re.sub(r"^.*?[:：]", "", self._style_confidence()).strip() or self._style_confidence().strip()
        why_bits = []
        scenario = self._tactical_scenario_text()
        if scenario:
            why_bits.append(scenario)
        else:
            shape = self._recent_settled_pattern_brief()
            if shape:
                why_bits.append(f"近仗走位：{shape}")
        return {"label": label, "conf": conf, "why": "；".join(why_bits)}

    def _record_entries(self):
        if self._record_entry_cache is not None:
            return self._record_entry_cache
        entries = []
        for cols in _record_rows(self.facts_section):
            entries.append({
                "kind": cols[1],
                "date": cols[2],
                "venue": cols[3],
                "distance": cols[4],
                "going": cols[5],
                "barrier": cols[6],
                "placing": cols[7],
                "class_move": cols[8],
                "trajectory": cols[9],
                "pi": cols[10] if len(cols) > 10 else "",
                "sectional_quality": cols[11] if len(cols) > 11 else "",
                "early_pace": cols[12] if len(cols) > 12 else "",
                "l600_rt": cols[13] if len(cols) > 13 else "",
                "run_style": cols[14] if len(cols) > 14 else "",
                "consumption": cols[15] if len(cols) > 15 else "",
                "notes": cols[16] if len(cols) > 16 else "",
                "forgiveness": cols[17] if len(cols) > 17 else "",
                "is_trial": "試閘" in cols[1],
            })
        self._record_entry_cache = entries
        return entries

    def _official_entries(self):
        if self._official_entry_cache is not None:
            return self._official_entry_cache
        self._official_entry_cache = [entry for entry in self._record_entries() if not entry["is_trial"]]
        return self._official_entry_cache

    def _sectional_trends(self):
        if self._sectional_trend_cache is not None:
            return self._sectional_trend_cache
        block = str(self.data.get("sectional_trend_line") or "")
        # FIX (2026-07-01): pi 趨勢標籤過去會貪婪 bleed 埋後面成條 "- L400 PI …→ 趨勢: X"，
        # 令 _run_style_score (:`"穩定" in pi_trend`) 實際 match 緊 L400 尾巴而唔係真 PI 趨勢。
        # 喺撞到「- L400」/「；」/行尾前停低，pi_trend 先係正確嘅定位→終點趨勢。
        pi_line = re.search(r"PI \(定位→終點\):\s*([^\n]+?)\s*→\s*趨勢:\s*([^\n]+?)(?=\s*[-–—]\s*L400|；|$)", block)
        l400_line = re.search(r"L400 PI \(400m→終點\):\s*([^\n]+?)\s*→\s*趨勢:\s*([^\n]+?)(?=\s*；|$)", block)
        self._sectional_trend_cache = {
            "pi_values": parse_numbers(pi_line.group(1)) if pi_line else [],
            "pi_trend": pi_line.group(2).strip() if pi_line else "",
            "l400_values": parse_numbers(l400_line.group(1)) if l400_line else [],
            "l400_trend": l400_line.group(2).strip() if l400_line else "",
        }
        return self._sectional_trend_cache

    def _latest_l600_rt_metrics(self):
        if self._latest_l600_rt_cache is not None:
            return self._latest_l600_rt_cache
        latest = self._official_entries()[0] if self._official_entries() else {}
        text = str(latest.get("l600_rt") or "").strip()
        l600_match = re.search(r"([+-]?\d+(?:\.\d+)?)", text)
        rt_match = re.search(r"RT\s*([+-]?\d+(?:\.\d+)?)", text, re.I)
        self._latest_l600_rt_cache = {
            "raw": text,
            "l600": float(l600_match.group(1)) if l600_match else None,
            "rt": float(rt_match.group(1)) if rt_match else None,
        }
        return self._latest_l600_rt_cache

    def _latest_l600_rt_brief(self):
        metrics = self._latest_l600_rt_metrics()
        if not metrics.get("raw") or metrics["raw"] == "-":
            return ""
        parts = []
        if metrics.get("l600") is not None:
            sign = "+" if metrics["l600"] > 0 else ""
            parts.append(f"L600 {sign}{metrics['l600']}")
        if metrics.get("rt") is not None:
            parts.append(f"RT {metrics['rt']}")
        return " / ".join(parts)

    def _entry_note_flags(self, entry):
        text = " ".join(
            str(entry.get(key) or "")
            for key in ("notes", "video", "stewards")
        )
        if not text.strip():
            return {"positive": [], "negative": []}
        positive = []
        negative = []
        for token, label in (
            ("Looking for run", "直路受阻"),
            ("Crowded", "受擠迫"),
            ("Steadied", "被迫收慢"),
            ("Across heels", "移出避腳"),
            ("Began awkwardly", "出閘笨拙"),
            ("lost ground", "起步蝕位"),
            ("Arguably should have won", "走勢好過名次"),
            ("Too much start", "起步讓步"),
            ("Widest straightening", "直路外疊"),
            # BUGFIX 2026-07-03: "no abs"(-normalities) is a CLEAN vet report — it was
            # sitting in the negative list and rendering as a risk flag.
            ("no abs", "賽後無明顯異常"),
        ):
            if token in text:
                positive.append(label)
        for token, label in (
            ("Worked early", "早段做多"),
            ("over-race", "沿途搶口"),
            ("slow recovery", "回氣偏慢"),
            ("weakened", "末段轉弱"),
        ):
            if token in text:
                negative.append(label)
        return {"positive": positive, "negative": negative}

    def _latest_official_note_brief(self):
        latest = self._official_entries()[0] if self._official_entries() else {}
        flags = self._entry_note_flags(latest)
        parts = []
        if flags["positive"]:
            parts.append(" / ".join(flags["positive"][:3]))
        if flags["negative"]:
            parts.append("風險: " + " / ".join(flags["negative"][:2]))
        return "；".join(parts)

    def _current_jockey_formal_rides(self):
        return int(parse_float(self.data.get("current_jockey_formal_rides")) or 0)

    def _current_jockey_formal_places(self):
        return int(parse_float(self.data.get("current_jockey_formal_places")) or 0)

    def _current_jockey_formal_wins(self):
        return int(parse_float(self.data.get("current_jockey_formal_wins")) or 0)

    def _current_jockey_trial_rides(self):
        return int(parse_float(self.data.get("current_jockey_trial_rides")) or 0)

    def _current_jockey_trial_top3(self):
        return int(parse_float(self.data.get("current_jockey_trial_top3")) or 0)

    def _latest_official_jockey(self):
        return self._clean_identity(self.data.get("latest_official_jockey"))

    def _latest_official_jockey_formal_rides(self):
        return int(parse_float(self.data.get("latest_official_jockey_formal_rides")) or 0)

    def _latest_official_jockey_formal_places(self):
        return int(parse_float(self.data.get("latest_official_jockey_formal_places")) or 0)

    def _latest_official_jockey_formal_wins(self):
        return int(parse_float(self.data.get("latest_official_jockey_formal_wins")) or 0)

    def _current_jockey_history_brief(self):
        direct = str(self.data.get("current_jockey_history_line") or "").strip()
        if direct:
            return direct
        rides = self._current_jockey_formal_rides()
        places = self._current_jockey_formal_places()
        wins = self._current_jockey_formal_wins()
        trial_rides = self._current_jockey_trial_rides()
        trial_top3 = self._current_jockey_trial_top3()
        jockey = self._clean_identity(self.horse_data.get("jockey")) or "今場騎師"
        if not any((rides, trial_rides)):
            return ""
        parts = []
        if rides:
            if rides == 1:
                if wins > 0:
                    parts.append(f"{jockey}曾與此馬合作 1 次，並錄得頭馬")
                elif places > 0:
                    parts.append(f"{jockey}曾與此馬合作 1 次，該次有前列名次")
                else:
                    parts.append(f"{jockey}曾與此馬合作 1 次，該次未見前列")
            elif wins > 0:
                parts.append(f"{jockey}與此馬過往合作 {rides} 次，錄得 {wins} 勝 {places} 入位，配搭有實績支持")
            elif places > 0:
                parts.append(f"{jockey}與此馬過往合作 {rides} 次，錄得 {places} 次上名，配搭有一定穩定性")
            else:
                parts.append(f"{jockey}與此馬過往合作 {rides} 次，未勝未入位，數據偏弱")
        if trial_rides:
            parts.append(f"試閘 {trial_rides} 次，{trial_top3} 次前三")
        return "；".join(parts)

    def _current_venue_name(self):
        return self._clean_identity(self._track_profile().get("venue") or self._meeting_intelligence().get("venue"))

    def _current_track_combo_stats(self):
        venue = self._current_venue_name().lower()
        jockey = self._clean_identity(self.horse_data.get("jockey")).lower()
        trainer = self._clean_identity(self.horse_data.get("trainer")).lower()
        if not venue or not jockey or not trainer:
            return {}
        combo_cache, _ = _load_jockey_trainer_combo_stats()
        return combo_cache.get((venue, jockey, trainer), {})

    def _trainer_track_stats(self):
        venue = self._current_venue_name().lower()
        trainer = self._clean_identity(self.horse_data.get("trainer")).lower()
        if not venue or not trainer:
            return {}
        _, trainer_cache = _load_jockey_trainer_combo_stats()
        return trainer_cache.get((venue, trainer), {})

    def _track_combo_brief(self):
        stats = self._current_track_combo_stats()
        venue = self._current_venue_name()
        if not stats or not venue:
            return ""
        place_rate = stats.get("place_rate", 0.0) * 100
        return f"{venue} 同場騎練 {stats.get('runs', 0)} 次，{stats.get('wins', 0)} 勝 {stats.get('places', 0)} 次上名，上名率 {place_rate:.0f}%"

    def _trainer_track_brief(self):
        stats = self._trainer_track_stats()
        venue = self._current_venue_name()
        if not stats or not venue:
            return ""
        place_rate = stats.get("place_rate", 0.0) * 100
        return f"{venue} 場館下馬房累積 {stats.get('runs', 0)} 次，{stats.get('wins', 0)} 勝 {stats.get('places', 0)} 次上名，上名率 {place_rate:.0f}%"

    def _best_formal_jockey(self):
        return self._clean_identity(self.data.get("best_formal_jockey"))

    def _best_formal_jockey_rides(self):
        return int(parse_float(self.data.get("best_formal_jockey_rides")) or 0)

    def _best_formal_jockey_places(self):
        return int(parse_float(self.data.get("best_formal_jockey_places")) or 0)

    def _best_formal_jockey_wins(self):
        return int(parse_float(self.data.get("best_formal_jockey_wins")) or 0)

    def _best_jockey_history_brief(self):
        direct = str(self.data.get("best_jockey_history_line") or "").strip()
        if direct:
            return direct
        jockey = self._best_formal_jockey()
        rides = self._best_formal_jockey_rides()
        places = self._best_formal_jockey_places()
        wins = self._best_formal_jockey_wins()
        if not jockey or not rides:
            return ""
        if wins > 0:
            return f"{jockey} 曾策 {rides} 次，錄得 {wins} 勝 {places} 入位，為此馬歷來最有依據的配搭"
        if places > 0:
            return f"{jockey} 曾策 {rides} 次，錄得 {places} 次上名，配搭有一定穩定性"
        return f"{jockey} 曾策 {rides} 次，數據偏弱"

    def _current_vs_best_jockey_brief(self):
        direct = str(self.data.get("current_vs_best_jockey_line") or "").strip()
        if direct:
            return direct
        current = self._clean_identity(self.horse_data.get("jockey"))
        best = self._best_formal_jockey()
        if not current or not best or current == best:
            return ""
        return f"今場由 {current} 接手，歷來最佳正式賽配搭為 {best}"

    def _known_jockeys_brief(self):
        return str(self.data.get("known_jockeys_line") or "").strip()

    def _latest_official_jockey_brief(self):
        latest = self._latest_official_jockey()
        rides = self._latest_official_jockey_formal_rides()
        places = self._latest_official_jockey_formal_places()
        wins = self._latest_official_jockey_formal_wins()
        if not latest:
            return ""
        if not rides:
            return latest
        return f"{latest} 曾策正式賽 {rides} 次，{wins} 勝 {places} 上名"

    def _jockey_rank_value(self, jockey: str) -> int:
        name = self._clean_identity(jockey)
        # 統一以 rating DB tier 行先（2026-07-11），token 名單降級做 fallback
        rating = self._jockey_rating_profile(name)
        if rating:
            return {"T1": 3, "T2": 2, "T3": 1}.get(str(rating.get("tier")), 0)
        if self._is_top_jockey(name):
            return 3
        if any(token in name for token in ("McEvoy", "Layt", "Bayliss", "Moore", "Roper", "Costin", "Parr", "Dolan", "Schiller")):
            return 2
        if "(a)" in name or any(token in name for token in ("Fitzgerald", "Panya")):
            return 1
        return 0

    def _jockey_change_signal(self):
        signal = str(self.data.get("jockey_change_signal") or "").strip()
        if signal:
            return signal
        current = self._clean_identity(self.horse_data.get("jockey"))
        latest_official = self._latest_official_jockey()
        latest_trial = self._clean_identity(self.data.get("latest_trial_jockey"))
        current_rate = safe_ratio(self._current_jockey_formal_places(), self._current_jockey_formal_rides())
        previous_rate = safe_ratio(self._latest_official_jockey_formal_places(), self._latest_official_jockey_formal_rides())
        if current and latest_official and current == latest_official:
            return "沿用上仗騎師"
        if current and latest_trial and current == latest_trial:
            return "試閘手接手"
        if latest_official and current:
            current_rank = self._jockey_rank_value(current)
            previous_rank = self._jockey_rank_value(latest_official)
            if self._current_jockey_formal_rides() > 0 and self._latest_official_jockey_formal_rides() > 0:
                if current_rate > previous_rate + 0.20 and self._current_jockey_formal_places() >= self._latest_official_jockey_formal_places():
                    return f"由 {latest_official} 轉配更合拍騎師 {current}"
                if previous_rate > current_rate + 0.20 and self._current_jockey_formal_rides() == 0:
                    return f"由 {latest_official} 離開已證明配搭"
            if current_rank > previous_rank:
                return f"由 {latest_official} 換上較強騎師 {current}"
            if current_rank < previous_rank:
                return f"由 {latest_official} 換下較高級騎師"
            if self._current_jockey_formal_rides() > 0:
                return f"回配 {current}"
            return f"由 {latest_official} 轉配 {current}"
        return ""

    def _sire_line(self):
        return str(self.data.get("sire_line") or "").strip()

    def _wet_bloodline_signal(self):
        sire = self._sire_line()
        if not sire:
            return ""
        positive = ("So You Think", "Savabeel", "Dundeel", "Tavistock")
        negative = ("Snitzel", "Rubick")
        if any(token in sire for token in positive):
            return "濕地血統偏正面"
        if any(token in sire for token in negative):
            return "濕地血統偏保留"
        return ""

    def _formline_rows(self):
        if self._formline_row_cache is not None:
            return self._formline_row_cache
        rows = []
        capture = False
        for line in self.facts_section.splitlines():
            text = line.strip()
            if text.startswith("- **🔗 賽績線"):
                capture = True
                continue
            if capture and text.startswith("- **🔧 引擎與距離"):
                break
            if not capture or not text.startswith("|") or "對手後續成績" in text or "強度評估" in text or "---" in text:
                continue
            cols = [col.strip() for col in text.strip("|").split("|")]
            offset = 1 if cols and (cols[0] == "#" or cols[0].isdigit()) else 0
            if len(cols) >= offset + 7:
                rows.append({
                    "date": cols[offset],
                    "race": cols[offset + 1],
                    "finish": cols[offset + 2],
                    "opponent": cols[offset + 3],
                    "next_class": cols[offset + 4],
                    "next_result": cols[offset + 5],
                    "strength": cols[offset + 6],
                })
        self._formline_row_cache = rows
        return rows

    def _same_track_stats(self):
        return self._parse_record_stats(self.data.get("track_stats_line") or "")

    def _going_stats(self):
        return self._parse_going_stats(self.data.get("going_stats_line") or "")

    def _meeting_intelligence(self):
        data = self.race_context.get("meeting_intelligence")
        return data if isinstance(data, dict) else {}

    def _track_profile(self):
        data = self.race_context.get("track_profile")
        return data if isinstance(data, dict) else {}

    def _today_going(self):
        return str(
            self._meeting_intelligence().get("going")
            or self._speed_map_field("going", "track_condition")
            or self.race_context.get("going")
            or ""
        ).strip()

    def _wet_state(self):
        going = self._today_going()
        number_match = re.search(r"(Soft|Heavy)\s*([0-9]+)", going, re.I)
        if not number_match:
            return ""
        kind = number_match.group(1).lower()
        level = int(number_match.group(2))
        if kind == "heavy":
            return "heavy"
        if level >= 7:
            return "soft7plus"
        if level >= 5:
            return "soft56"
        return ""

    def _track_context(self):
        if self._track_context_cache is not None:
            return self._track_context_cache
        meeting = self._meeting_intelligence()
        profile = self._track_profile()
        bias_text = " ".join(
            part for part in (
                str(meeting.get("bias_summary") or "").strip(),
                str(profile.get("distance_note") or "").strip(),
                " / ".join(profile.get("key_traits") or []),
                str(profile.get("going_note") or "").strip(),
            )
            if part
        )
        straight_m = int(parse_float(profile.get("straight_m")) or 0)
        distance_band = ""
        distance_m = self._distance_m()
        if 1000 <= distance_m <= 1100:
            distance_band = "1000-1100m"
        elif 1200 <= distance_m <= 1300:
            distance_band = "1200-1300m"
        elif 1400 <= distance_m <= 1600:
            distance_band = "1400-1600m"
        going = self._today_going()
        going_bucket = "好地"
        if "Heavy" in going or "重" in going:
            going_bucket = "重地"
        elif "Soft" in going or "軟" in going:
            going_bucket = "軟地"
        self._track_context_cache = {
            "meeting_bias": str(meeting.get("bias_summary") or "").strip(),
            "rail_position": str(meeting.get("rail_position") or "").strip(),
            "straight_m": straight_m,
            "distance_band": distance_band,
            "distance_note": str(profile.get("distance_note") or "").strip(),
            "front_bias": any(token in bias_text for token in ("front runners", "前置", "前領偏差", "On-pace bias", "利放頭", "跟前")),
            "inside_advantage": any(token in bias_text for token in ("內檔", "內疊", "省位", "箱位", "切線優勢")),
            "outside_penalty": any(token in bias_text for token in ("外檔", "外疊", "地獄排位", "白走", "難以從包尾大幅度追越")),
            "short_straight": 0 < straight_m <= 330,
            "fair_track": any(token in bias_text for token in ("relatively fair", "公平", "不會太極端", "未見特別鮮明")),
            "going_bucket": going_bucket,
        }
        return self._track_context_cache

    def _stage_stats(self):
        line = str(self.data.get("stage_stats_line") or "")
        first_up_match = re.search(r"^([^|]+)", line)
        second_up_match = re.search(r"二出:\s*([^\n]+)", line)
        return {
            "first_up": self._parse_record_stats(first_up_match.group(1).strip() if first_up_match else ""),
            "second_up": self._parse_record_stats(second_up_match.group(1).strip() if second_up_match else ""),
        }

    def _parse_record_stats(self, text):
        stats = parse_record_line(text)
        if stats:
            return stats
        return {"starts": 0, "wins": 0, "seconds": 0, "thirds": 0, "places": 0}

    def _parse_going_stats(self, text):
        output = {}
        for label in ("好地", "軟地", "重地"):
            match = re.search(rf"{label}:\s*([^|]+)", text)
            output[label] = self._parse_record_stats(match.group(1).strip() if match else "")
        return output

    def _distance_m(self):
        match = re.search(r"(\d+)", str(self.race_context.get("distance") or ""))
        return int(match.group(1)) if match else 0

    def _meeting_bias_brief(self):
        return str(self._track_context().get("meeting_bias") or "").strip()

    def _track_geometry_brief(self):
        profile = self._track_profile()
        venue = str(profile.get("venue") or self._meeting_intelligence().get("venue") or "").strip()
        parts = []
        if venue:
            parts.append(venue)
        straight_m = int(parse_float(profile.get("straight_m")) or 0)
        circumference_m = int(parse_float(profile.get("circumference_m")) or 0)
        dims = []
        if circumference_m:
            dims.append(f"周長 {circumference_m}m")
        if straight_m:
            dims.append(f"直路 {straight_m}m")
        if dims:
            parts.append(" / ".join(dims))
        traits = []
        for item in profile.get("key_traits") or []:
            clean = str(item).strip()
            if not clean:
                continue
            clean = clean.replace("Tight-turning 急彎賽道", "急彎賽道")
            clean = clean.replace("On-Pace BIAS 前領偏差", "前置偏差")
            clean = clean.replace("On-Pace Bias 前領偏差", "前置偏差")
            traits.append(clean)
        if traits:
            parts.append(" / ".join(traits[:2]))
        return " | ".join(parts)

    def _track_distance_note_brief(self):
        return str(self._track_context().get("distance_note") or "").strip()

    def _track_fit_brief(self):
        context = self._track_context()
        style = self._running_style() or self._tactical_position_text()
        barrier = parse_float(self.horse_data.get("barrier"))
        bits = []
        if context.get("front_bias"):
            if any(token in style for token in ("前", "跟前", "居中前")):
                bits.append("跑法同偏前置場地輪廓相對對位")
            elif any(token in style for token in ("後", "中後")):
                bits.append("跑法要克服偏前置場地輪廓")
        if barrier is not None:
            if context.get("inside_advantage") and barrier <= 4:
                bits.append("內檔可放大省位價值")
            elif context.get("outside_penalty") and barrier >= 9:
                bits.append("外檔仍有額外走位成本")
        if context.get("short_straight") and any(token in style for token in ("後", "中後", "後上")):
            bits.append("短直路令後追 timing 更緊")
        if not bits and context.get("fair_track"):
            bits.append("場地整體偏公平，主要睇自身適性")
        return "；".join(bits)

    def _has_verified_wet_place(self):
        stats = self._going_stats()
        return any(stats[label]["places"] > 0 for label in ("軟地", "重地"))

    def _pace_confidence(self):
        return str(self._speed_map_field("pace_confidence") or "").strip()

    def _style_confidence(self):
        return str(self.data.get("style_confidence_line") or self._speed_map_field("style_confidence") or "").strip()

    def _run_style_brief(self):
        """單一 canonical 跑法顯示：clean 標籤（前置／守好位／守中／後上）＋信心。
        取代舊有分散嘅 跑法信心 / style evidence / 預計走法 三條重覆欄位，
        亦統一咗之前三個函數各自俾出唔同字串嘅問題。"""
        ps = self._predicted_style()
        if ps and ps.get("label"):
            label, conf = ps["label"], (ps.get("conf") or "")
        else:
            label = (self._running_style() or self._tactical_position_text() or "").strip()
            conf = re.sub(r"^.*?[:：]", "", self._style_confidence()).strip()
        if not label:
            return ""
        return f"{label}（信心{conf}）" if conf else label

    def _formguide_shape_stats(self):
        if self._formguide_shape_cache is not None:
            return self._formguide_shape_cache
        stats = {
            "settled_pattern": str(self.data.get("recent_settled_pattern_line") or "").strip(),
            "pos400_pattern": str(self.data.get("recent_400_pattern_line") or "").strip(),
            "consensus_bucket": str(self.data.get("recent_shape_consensus") or "").strip(),
            "consensus_count": int(parse_float(self.data.get("recent_shape_consensus_count")) or 0),
            "entropy": int(parse_float(self.data.get("recent_shape_entropy")) or 0),
            "front_count": int(parse_float(self.data.get("recent_shape_front_count")) or 0),
            "mid_count": int(parse_float(self.data.get("recent_shape_mid_count")) or 0),
            "back_count": int(parse_float(self.data.get("recent_shape_back_count")) or 0),
            "inside_count": int(parse_float(self.data.get("recent_shape_inside_count")) or 0),
            "wide_no_cover_count": int(parse_float(self.data.get("recent_shape_wide_no_cover_count")) or 0),
            "early_work_count": int(parse_float(self.data.get("recent_shape_early_work_count")) or 0),
            "summary_line": str(self.data.get("recent_shape_summary_line") or "").strip(),
        }
        self._formguide_shape_cache = stats
        return stats

    def _recent_settled_pattern_brief(self):
        stats = self._formguide_shape_stats()
        parts = []
        if stats["settled_pattern"]:
            parts.append(f"Settled {stats['settled_pattern']}")
        if stats["summary_line"]:
            parts.append(stats["summary_line"])
        return "；".join(parts)

    def _has_last10_warning(self):
        return bool(str(self.data.get("warning_line") or "").strip())

    def _latest_official_text(self):
        latest = self._official_entries()[0] if self._official_entries() else {}
        return " ".join(str(latest.get(key) or "") for key in ("notes", "forgiveness", "trajectory"))

    def _spell_days(self):
        explicit = parse_float(self.data.get("spell_days"))
        if explicit is not None and explicit > 0:
            return int(explicit)
        latest_date = str(self.data.get("latest_official_date") or "").strip()
        if not latest_date and self._official_entries():
            latest_date = str(self._official_entries()[0].get("date") or "").strip()
        meeting_date = str(
            self._meeting_intelligence().get("date")
            or self.race_context.get("date")
            or ""
        ).strip()
        latest = _parse_iso_date(latest_date)
        meeting = _parse_iso_date(meeting_date)
        if not latest or not meeting:
            return 0
        return max(0, (meeting - latest).days)

    def _trial_summary_text(self):
        trial_count = int(parse_float(self.data.get("trial_count")) or len(self._trial_places()))
        trial_top3 = int(parse_float(self.data.get("trial_top3_count")) or sum(1 for place in self._trial_places() if place <= 3))
        if trial_count <= 0:
            return ""
        return f"共 {trial_count} 次試閘，其中 {trial_top3} 次跑入前三"

    def _class_move_display(self):
        class_move = str(self.horse_data.get("class_move") or self.data.get("class_move") or "").strip()
        if class_move == "=":
            return "班次維持不變"
        return class_move or "班次資料未明"

    def _race_class_text(self):
        return str(self.race_context.get("race_class") or "").strip()

    def _race_class_bucket(self):
        text = self._race_class_text().lower()
        if "group 1" in text:
            return "group1"
        if "group 2" in text or "group 3" in text:
            return "group23"
        if "listed" in text:
            return "listed"
        bm_match = re.search(r"bm\s*(\d+)", text)
        if bm_match:
            rating = int(bm_match.group(1))
            if rating >= 88:
                return "bm88"
            if rating >= 72:
                return "bm72"
            return "bm58"
        if "maiden" in text:
            return "maiden"
        return ""

    def _is_maiden_race(self):
        return self._race_class_bucket() == "maiden"

    def _field_summary(self):
        data = self.race_context.get("field_summary")
        return data if isinstance(data, dict) else {}

    def _field_size_bucket(self):
        count = int(self._field_summary().get("count") or 0)
        if count >= 13:
            return "Field 13+"
        if count >= 9:
            return "Field 9-12"
        if count > 0:
            return "Field <=8"
        return ""

    def _repeatability_brief(self):
        track_stats = self._same_track_stats()
        track_line = str(self.data.get("track_record_line") or "")
        if "同場同程: 1:" in track_line:
            return "同場同程已有直接對位"
        if track_stats["starts"] >= 2 and track_stats["places"] >= 2:
            return "同場樣本已形成重覆前列交代"
        if track_stats["starts"] >= 2 and track_stats["places"] == 0:
            return "同場樣本已有累積，但仍未形成穩定交代"
        return ""

    def _field_weight_delta(self):
        weight = parse_float(self.horse_data.get("weight"))
        field = self._field_summary()
        if weight is None or not field:
            return {}
        max_weight = parse_float(field.get("max_weight"))
        avg_weight = parse_float(field.get("avg_weight"))
        min_weight = parse_float(field.get("min_weight"))
        return {
            "to_top": (max_weight - weight) if max_weight is not None else None,
            "to_avg": (avg_weight - weight) if avg_weight is not None else None,
            "to_bottom": (weight - min_weight) if min_weight is not None else None,
        }

    def _venue_tier(self, venue: str):
        text = self._clean_identity(venue).lower()
        return "metro" if any(token in text for token in METRO_VENUE_TOKENS) else ("provincial" if text else "")

    def _weight_text(self):
        weight = parse_float(self.horse_data.get("weight"))
        if weight is None:
            return ""
        return f"{weight:.1f}kg"

    def _field_weight_brief(self):
        delta = self._field_weight_delta()
        if delta.get("to_top") is None:
            return ""
        parts = []
        if delta["to_top"] is not None:
            parts.append(f"較頂磅輕 {delta['to_top']:.1f}kg")
        if delta.get("to_avg") is not None:
            sign = "+" if delta["to_avg"] > 0 else ""
            parts.append(f"較場均 {sign}{delta['to_avg']:.1f}kg")
        return "；".join(parts)

    def _horse_rating(self):
        return parse_float(self.horse_data.get("rating") or self.data.get("horse_rating"))

    def _horse_rating_text(self):
        rating = self._horse_rating()
        return f"{rating:.1f}" if rating is not None else ""

    def _field_rating_delta(self):
        rating = self._horse_rating()
        field = self._field_summary()
        if rating is None or not field:
            return {}
        avg_rating = parse_float(field.get("avg_rating"))
        top3_cutoff = parse_float(field.get("top3_rating_cutoff"))
        rating_stdev = parse_float(field.get("rating_stdev"))
        return {
            "to_avg": (rating - avg_rating) if avg_rating is not None else None,
            "to_top3": (rating - top3_cutoff) if top3_cutoff is not None else None,
            "stdev": rating_stdev if rating_stdev is not None else None,
        }

    def _field_rating_brief(self):
        delta = self._field_rating_delta()
        rating = self._horse_rating()
        if rating is None:
            return ""
        parts = [f"今場評分 {rating:.1f}"]
        if delta.get("to_avg") is not None:
            sign = "+" if delta["to_avg"] > 0 else ""
            parts.append(f"較場均 {sign}{delta['to_avg']:.1f}")
        if delta.get("to_top3") is not None:
            if delta["to_top3"] >= 0:
                parts.append("已達場內前三 rating 門檻")
            else:
                parts.append(f"離前三 rating 門檻差 {abs(delta['to_top3']):.1f}")
        return "；".join(parts)

    def _l400_text(self):
        l400 = parse_float(self.horse_data.get("raw_l400") or self.data.get("raw_l400"))
        if l400 is None:
            return ""
        return f"{l400:.2f} 秒"

    def _jockey_trainer_pair_text(self):
        jockey = self._clean_identity(self.horse_data.get("jockey"))
        trainer = self._clean_identity(self.horse_data.get("trainer"))
        if jockey and trainer:
            return f"{jockey} / {trainer}"
        return jockey or trainer

    def _engine_distance_brief(self):
        line = str(self.data.get("engine_line") or "").strip()
        if not line:
            return ""
        engine_match = re.search(r"引擎:\s*([^|]+)", line)
        distance_match = re.search(r"今仗\s+([0-9]+m)\s+\(([^)]+)\):\s*([^|]+)", line)
        confidence_match = re.search(r"信心:\s*([^|]+)", line)
        parts = []
        if engine_match:
            engine_raw = engine_match.group(1).strip()
            # engine_raw 通常係「Type A/B (混合型)」— 內部代碼 + 已有嘅中文譯名同時存在；
            # 淨係留中文譯名，內部代碼對用戶冇意思。冇括號就照用原文（已經係中文）。
            zh_match = re.search(r"（([^）]+)）|\(([^)]+)\)", engine_raw)
            engine_label = (zh_match.group(1) or zh_match.group(2)) if zh_match else engine_raw
            parts.append(f"引擎輪廓 {engine_label}")
        if distance_match:
            parts.append(f"今次 {distance_match.group(1)} 以上 {distance_match.group(2).strip()} 系列作投射")
        if confidence_match:
            parts.append(f"路程信心 {confidence_match.group(1).strip()}")
        return "；".join(parts) if parts else line

    @staticmethod
    def _clean_trend_label(raw):
        # 顯示用：剝走 bleed 入趨勢標籤嘅 L400 子句 / 重覆「→ 趨勢:」，scoring cache 不受影響。
        first = re.split(r"\s*[-–—]\s*L400|L400 PI|；", str(raw or ""))[0]
        return first.strip() or "未明"

    def _sectional_trend_brief(self):
        # 只出一條 PI 序列（定位→終點）＋趨勢；舊版同時印 PI 同 L400 PI 兩條近乎一樣嘅序列，重覆。
        trends = self._sectional_trends()
        values = trends.get("pi_values") or trends.get("l400_values")
        raw = trends.get("pi_trend") if trends.get("pi_values") else trends.get("l400_trend")
        if not values:
            return ""
        seq = ", ".join(str(int(v)) if float(v).is_integer() else str(v) for v in values)
        return f"PI {seq}（{self._clean_trend_label(raw)}）"

    def _formline_followup_brief(self):
        rows = self._formline_rows()
        if not rows:
            return ""
        wins = 0
        for row in rows:
            result = row.get("next_result", "")
            match = re.search(r"出\s*\d+\s*次:\s*(\d+)\s*勝", result)
            if match and int(match.group(1)) > 0:
                wins += 1
        if wins == 0:
            return "對手後續暫未見明顯贏馬延續"
        counts = self._formline_followup_counts()
        parts = []
        if counts["higher"] > 0:
            parts.append(f"當中 {counts['higher']} 匹對手其後升上更高班出賽，對手成色有正面指標")
        if counts["same"] > 0:
            parts.append(f"{counts['same']} 匹對手其後繼續同班角逐，對手線有基本延續")
        if counts["lower"] > 0:
            parts.append(f"{counts['lower']} 匹對手其後要降班出賽，支持力度較有限")
        if not parts:
            parts.append(f"對手後續有 {wins} 匹再贏")
        parts.append(f"合共 {wins} 匹具後續交代")
        return "；".join(parts)

    def _formline_followup_counts(self):
        counts = {"higher": 0, "same": 0, "lower": 0}
        for row in self._formline_rows():
            next_class = str(row.get("next_class", "") or "")
            if any(token in next_class for token in ("Metro+省", "Group", "Listed", "G1", "G2", "G3", "LR")):
                counts["higher"] += 1
            elif any(token in next_class for token in ("省賽", "Maiden", "BM", "CL")):
                counts["lower"] += 1
            elif next_class and next_class != "-":
                counts["same"] += 1
        return counts

    def _formline_headwinner(self):
        rows = self._formline_rows()
        for row in rows:
            opponent = str(row.get("opponent", "") or "")
            if "頭馬" in opponent:
                return opponent
        return ""

    def _formline_level(self):
        text = str(self.data.get("formline_line") or "").strip()
        text = text.replace("✅", "").replace("⚠️", "").strip()
        if self._formline_rows() and ("無資料" in text or "未有出賽" in text):
            return "待驗證 (有對手線，未有後續承接)"
        if self._formline_rows() and self._is_misleading_formline_headline(text):
            return self._formline_inferred_level() or text
        return text

    def _is_misleading_formline_headline(self, text):
        clean = str(text or "")
        return bool(
            re.search(r"強組比例:\s*0(?:\.0)?/1", clean)
            and any(token in clean for token in ("強", "極強"))
            and self._formline_support_summary()[0] < 1.0
        )

    def _formline_support_summary(self):
        valid = 0
        support = 0.0
        for row in self._formline_rows():
            strength = str(row.get("strength") or "")
            if not strength or strength == "-":
                continue
            if not any(token in strength for token in ("組", "強", "弱")):
                continue
            valid += 1
            if "超強" in strength or "極強" in strength:
                support += 2.0
            elif "強組" in strength:
                support += 1.0
            elif "中組" in strength:
                support += 0.5
        return support, valid

    def _formline_support_text(self, support, valid):
        if valid <= 0:
            return "0/0"
        support_text = str(int(support)) if float(support).is_integer() else f"{support:.1f}"
        return f"{support_text}/{valid}"

    def _formline_inferred_signal(self):
        support, valid = self._formline_support_summary()
        if valid <= 0:
            return "neutral" if self._formline_rows() else ""
        ratio = support / valid
        if support >= 2 and ratio >= 0.7:
            return "elite"
        if support >= 1 and ratio >= 0.5:
            return "strong"
        if ratio >= 0.3:
            return "medium_strong"
        if ratio >= 0.15:
            return "medium_weak"
        return "weak"

    def _formline_inferred_level(self):
        signal = self._formline_inferred_signal()
        if not signal:
            return ""
        if signal == "neutral":
            return "待驗證 (有對手線，未有後續承接)"
        support, valid = self._formline_support_summary()
        label_map = {
            "elite": "極強",
            "strong": "強",
            "medium_strong": "中強",
            "medium_weak": "中弱",
            "weak": "❌ 弱",
        }
        return f"{label_map.get(signal, '待驗證')} (承接分: {self._formline_support_text(support, valid)})"

    def _latest_record_summary(self, record_type="正式"):
        for cols in _record_rows(self.facts_section):
            kind = cols[1]
            is_trial = "試閘" in kind
            if record_type == "正式" and is_trial:
                continue
            if record_type == "試閘" and not is_trial:
                continue
            return self._record_row_summary(cols)
        return ""

    def _record_row_summary(self, cols):
        kind = cols[1]
        date = cols[2]
        venue = cols[3]
        distance = cols[4]
        going = cols[5]
        barrier = cols[6]
        placing = cols[7]
        trajectory = cols[9] if len(cols) > 9 else ""
        parts = [date, venue, distance, f"場地 {going}"]
        if barrier and barrier != "-":
            parts.append(f"檔位 {barrier}")
        parts.append(f"名次 {placing}")
        if trajectory and trajectory != "-":
            parts.append(f"走勢 {trajectory}")
        if "試閘" in kind:
            parts.insert(0, "試閘")
        return " | ".join(parts)

    def _class_score(self):
        career_starts = self._career_starts()
        class_move = str(self.horse_data.get("class_move") or self.data.get("class_move") or "")
        official_entries = self._official_entries()
        race_class = self._race_class_text()
        race_bucket = self._race_class_bucket()
        latest_rt = self._latest_l600_rt_metrics().get("rt")
        latest_place = parse_float((official_entries[0] or {}).get("placing")) if official_entries else None
        
        current_tier = self._venue_tier(self._meeting_intelligence().get("venue") or self._track_profile().get("venue") or "")
        latest_tier = self._venue_tier((official_entries[0] or {}).get("venue") if official_entries else "")

        w = CLASS_MICRO_WEIGHTS
        score = 60.0
        notes = []
        cdetail = {"base": 60.0, "notes": [], "final": None}
        self.class_detail = cdetail

        if career_starts == 0:
            score = w.get("career0_base", 56.0)
            notes.append("初出馬未有正式班際證明")
            if "2-y-o" in race_class.lower() or "2yo" in race_class.lower():
                score += w.get("career0_2yo_bonus", 2.0)
                notes.append("2歲馬初出常有爆發力")
        elif career_starts <= 5:
            if latest_place is not None and latest_place <= 3:
                score += w.get("career5_placed_bonus", 2.0)
                notes.append("出賽少但已上名，有進步空間")
            else:
                score += w.get("career5_unplaced_pen", -2.0)
                notes.append("經驗較薄且未證明實力")
        elif career_starts >= 15:
            if race_bucket == "maiden":
                score += w.get("career15_maiden_pen", -4.0)
                notes.append("多跑仍未能於處女馬賽勝出，班底已見底")
            elif latest_place is not None and latest_place >= 6:
                score += w.get("career15_unplaced_pen", -2.0)
                notes.append("多跑但近期未有表現，級數可能見頂")
            elif latest_place is not None and latest_place <= 3:
                score += w.get("career15_placed_bonus", 2.0)
                notes.append("作戰經驗豐富且近況有承接")

        if "降班" in class_move:
            score += w.get("class_drop_bonus", 6.0)
            notes.append("班次有回落")
        elif "大幅升班" in class_move or "升班" in class_move:
            # class_up_pen 已被 ML 推零；只喺真正有扣分時先出 note，唔好「有講冇分」。
            up_pen = w.get("class_up_pen", 0.0)
            if abs(up_pen) > 0.05:
                score += up_pen
                notes.append("今場對手層次轉強")


        if current_tier == "metro" and latest_tier == "provincial":
            if latest_rt is not None and latest_rt >= 68:
                notes.append("省賽轉都會，但 RT 證明夠跑都會區")
            else:
                score += w.get("metro_prov_pen", -3.0)
                notes.append("省賽轉都會，鄉鎮賽績含金量成疑")

        if latest_rt is not None:
            if latest_rt >= 68:
                score += w.get("rt_high_bonus", 4.0)
                notes.append("最新 RT rating 顯示具備能力")
            elif latest_rt <= 58:
                score += w.get("rt_low_pen", -4.0)
                notes.append("最新 RT rating 偏低")

        cdetail["notes"] = list(notes)
        cdetail["final"] = round(clip_score(score), 2)
        note_text = "；".join(notes) if notes else "班次資料未見鮮明傾向"
        return clip_score(score), f"{note_text}，級數分 {clip_score(score):.1f}。", "class_move+record_table+formline_followups"

    def _rating_score(self):
        rating = self._horse_rating()
        field = self._field_summary()
        rated_count = int(field.get("rated_count") or 0)
        rdetail = {"lines": [], "source": ""}
        self.rating_detail = rdetail
        if rating is None or rated_count < 2:
            # 處女/未評分馬（全場多數冇官方讓磅分）：唔好死中性 60 令成 70% 塌陷，
            # 改為借用級數分做代理（班次/升降/RT 仍有能力訊號）。
            # A/B（2026-07-11）：A窗 100→101、gold 微升、其餘持平、無倒退。
            class_proxy = clip_score(self._class_score()[0])
            rdetail["source"] = "proxy"
            rdetail["lines"] = [
                "呢場多數馬未有官方讓磅分（處女／未評分賽事常見）",
                f"改以級數分 {class_proxy:.1f} 作能力代理（唔死當中性）",
            ]
            return class_proxy, (f"未有足夠官方讓磅分（多見於處女賽），"
                                 f"改以級數分 {class_proxy:.1f} 作能力代理。"), "class_proxy"

        avg_rating = parse_float(field.get("avg_rating"))
        stdev = parse_float(field.get("rating_stdev")) or 0.0
        top3_cutoff = parse_float(field.get("top3_rating_cutoff"))
        race_bucket = self._race_class_bucket()
        notes = [f"今場官方 rating 為 {rating:.1f}"]

        adjustment = 0.0
        if avg_rating is not None:
            delta = rating - avg_rating
            if stdev >= 0.5:
                z_value = delta / stdev
                adjustment += max(-12.0, min(12.0, z_value * 6.0))
                if z_value >= 1.0:
                    notes.append("高於場均逾一個標準差")
                elif z_value >= 0.4:
                    notes.append("高於場均")
                elif z_value <= -1.0:
                    notes.append("低於場均逾一個標準差")
                elif z_value <= -0.4:
                    notes.append("低於場均")
                else:
                    notes.append("與場均接近")
            else:
                adjustment += max(-6.0, min(6.0, delta * 1.5))
                if delta > 0.8:
                    notes.append("高於場均")
                elif delta < -0.8:
                    notes.append("低於場均")
                else:
                    notes.append("與場均接近")

        if top3_cutoff is not None:
            if rating >= top3_cutoff:
                adjustment += 1.5
                notes.append("rating 已達場內前三門檻")
            elif rating + 1.0 < top3_cutoff:
                adjustment -= 1.0
                notes.append("rating 未達場內前三門檻")

        if race_bucket in {"bm58", "bm72", "bm88"}:
            adjustment *= 0.9
            notes.append("BM handicap rating 訊號已輕量 temper")
        elif race_bucket == "maiden":
            adjustment *= 0.8
            notes.append("處女馬 rating 波動較大，只作保守參考")

        score = clip_score(60.0 + adjustment)
        rdetail["source"] = "official"
        vs = ("高過場均" if adjustment > 0.5 else "低過場均" if adjustment < -0.5 else "同場均接近")
        rdetail["lines"] = [
            f"官方讓磅分 {rating:.1f}"
            + (f"，場均 {avg_rating:.1f}" if avg_rating is not None else ""),
            f"{vs} → 對位修正 {adjustment:+.1f} 分（60 為中性）",
        ]
        return score, f"{'；'.join(notes)}，Rating 分 {score:.1f}。", "racecard_rating+field_relative"

    def _pace_figure_score(self):
        """實測段速: field-relative racenet L600-vs-benchmark.
        Lower l600_delta (faster than the race benchmark) → higher score. Neutral
        60 when the runner has no PF data or the field has <3 with data (→ this
        component is rank-neutral on no-PF races). scale 20 reproduces the
        validated backtest config. See scoring.MATRIX_WEIGHTS note."""
        pf_agg = (self.data.get("pf_metrics") or {}).get("pf_aggregates") or {}
        detail = {"value": None, "mean": None, "stdev": None, "z": None,
                  "runs": int(pf_agg.get("pf_run_count") or 0), "final": 60.0, "state": ""}
        self.pace_figure_detail = detail
        value = pf_agg.get("l600_delta_avg")
        field = self._field_summary()
        count = int(field.get("l600_delta_field_count") or 0)
        if value is None or count < 3:
            detail["state"] = "no_pf"
            return 60, "無實測段速數據（racenet PuntingForm 未覆蓋此馬近績），段速實速分中性 60。", "missing_neutral"
        mean = parse_float(field.get("l600_delta_field_mean"))
        stdev = parse_float(field.get("l600_delta_field_stdev")) or 0.0
        if mean is None or stdev <= 0.0:
            detail["state"] = "no_spread"
            return 60, "同場實測段速無有效分散，段速實速分中性處理。", "no_spread"
        z = (float(value) - mean) / stdev
        score = clip_score(60 - z * 20.0)  # faster-than-benchmark (negative delta/z) → higher
        detail.update({"value": round(float(value), 2), "mean": round(mean, 2),
                       "stdev": round(stdev, 2), "z": round(z, 2),
                       "final": round(score, 1), "state": "ok"})
        direction = "快過" if float(value) < 0 else "慢過"
        note = (f"近{detail['runs']}場實測末段平均{direction}賽事基準 {abs(float(value)):.2f} 秒，"
                f"段速實速分 {score:.1f}。")
        return score, note, "pf_l600_delta_field_relative"

    def _is_wfa_or_sw_race(self):
        text = self._race_class_text().lower()
        return "weight for age" in text or "wfa" in text or "set weights" in text or "sw" in text

    def _weight_score(self):
        weight = parse_float(self.horse_data.get("weight"))
        wdetail = {"base": 62.0, "weight": None, "notes": [], "final": None}
        self.weight_detail = wdetail
        if weight is None:
            wdetail["final"] = 60.0
            return 60, "負磅資料不足，負磅分中性處理。", "missing_neutral"

        score = 62
        wdetail["weight"] = round(float(weight), 1)
        notes = []
        wet_state = self._wet_state()
        class_move = self._class_move_display()
        is_wfa_or_sw = self._is_wfa_or_sw_race()

        if is_wfa_or_sw:
            notes.append("定磅賽事不計讓磅劣勢")
        else:
            if weight <= 54.5:
                score = 68
                notes.append("負輕磅有明顯優勢")
            elif weight >= 60.0:
                score = 56
                self.risk_flags.append("top_weight")
                notes.append("頂磅環境要自己讓人")

            if wet_state in {"soft7plus", "heavy"} and weight >= 59.0:
                score -= 4
                notes.append("爛地加重磅消耗顯著")

            if "降班" in class_move and weight <= 56.5:
                score += 3
                notes.append("降班配輕磅，外在門檻大幅下降")
            elif "升班" in class_move and weight >= 58.0:
                score -= 3
                notes.append("升班兼高負磅，雙重打擊")
            elif "升班" in class_move and weight <= 54.0:
                score += 1
                notes.append("升班配輕磅，有助彌補級數差距")

        wdetail["notes"] = list(notes)
        wdetail["final"] = round(clip_score(score), 2)
        note_text = "；".join(notes) if notes else f"今場負磅 {weight:.1f}kg"
        return clip_score(score), f"{note_text}，負磅分 {clip_score(score):.1f}。", "weight+wet_track+class_move"

    def _distance_score(self):
        line = str(self.data.get("engine_line") or "")
        target_line = str(self.data.get("target_distance_line") or "")
        trends = self._sectional_trends()
        official_entries = self._official_entries()
        target_distance = self._distance_m()
        score = 60
        notes = []
        if "⭐最佳 ← 今場 ✅" in target_line or "最佳 ← 今場 ✅" in line:
            score = 78
            notes.append("今場已屬已證明射程")
        elif "今場 ✅" in line:
            score = 72
            notes.append("引擎線對今次路程屬正面")
        elif "← 今場 ❌" in target_line:
            score = 54
            notes.append("距離分佈顯示今場未必係最舒服射程")
        elif "未跑過且無相近近績" in line:
            score = 50
            notes.append("今次屬未證明路程")
        elif "未跑過" in line:
            score = 55
            notes.append("今場仍屬半投射路程")
        same_distance_places = 0
        near_distance_places = 0
        for entry in official_entries[:6]:
            entry_distance = self._entry_distance_m(entry)
            if not entry_distance or not target_distance:
                continue
            placing = parse_float(entry.get("placing"))
            if placing is None or placing > 3:
                continue
            if entry_distance == target_distance:
                same_distance_places += 1
            elif abs(entry_distance - target_distance) <= 100:
                near_distance_places += 1
        if same_distance_places:
            score += min(4, same_distance_places * 2)
            notes.append("正式賽同程已有上名承接")
        elif near_distance_places:
            score += min(2, near_distance_places)
            notes.append("相近路程已有基本對位樣本")
        if "上升" in trends.get("l400_trend", "") and score >= 60:
            score += 2
            notes.append("L400 趨勢向上，增程投射唔算亂估")
        elif "微跌" in trends.get("l400_trend", "") and target_distance and target_distance >= 1600:
            score -= 1
            notes.append("末段趨勢略放，長途尾段續航仍要防")
        note_text = "；".join(notes) if notes else "路程資料未見鮮明優劣"
        return score, f"{note_text}，路程分 {clip_score(score):.1f}。", "engine_line+target_distance_line+sectional_trend+record_table"

    def _track_score(self):
        track_stats = self._same_track_stats()
        going_stats = self._going_stats()
        track_context = self._track_context()
        wet_state = self._wet_state()
        going_bucket = track_context.get("going_bucket", "")
        going_sample = going_stats.get(going_bucket, {})
        
        w = TRACK_MICRO_WEIGHTS
        score = w.get("base", 60.0)
        notes = []
        tdetail = {"base": round(float(score), 1), "final": None}
        self.track_detail = tdetail

        if track_stats["places"] > 0:
            score += min(9, track_stats["places"] * w.get("same_track_place_bonus", 3.0) + track_stats["wins"] * w.get("same_track_win_bonus", 2.0))
            notes.append("同場有實際上名支持")
        elif track_stats["starts"] >= 2 and track_stats["places"] == 0:
            score += w.get("same_track_poor_pen1", -3.0)
            notes.append("同場已有多次出賽但仍未交到成績")
        elif track_stats["starts"] > 0 and track_stats["places"] == 0:
            score += w.get("same_track_poor_pen2", -2.0)
            notes.append("有同場出賽紀錄但仍未交到成績")

        if going_sample.get("starts", 0) > 0 and going_sample.get("places", 0) > 0:
            score += min(10, going_sample["places"] * w.get("going_place_bonus", 3.0))
            notes.append(f"{going_bucket} 樣本顯示對今場掛牌有基本適應")
            if going_sample.get("wins", 0) > 0 and going_bucket in {"軟地", "重地"}:
                score += w.get("going_win_bonus", 2.0)
                notes.append(f"{going_bucket} 曾贏馬，地狀證明更實淨")
        elif going_sample.get("starts", 0) >= 2 and going_sample.get("places", 0) == 0:
            score += w.get("going_poor_pen1_wet", -5.0) if going_bucket in {"軟地", "重地"} else w.get("going_poor_pen1_dry", -4.0)
            notes.append(f"{going_bucket} 多次出賽仍未有前列，適應性要保守")
        elif going_sample.get("starts", 0) > 0 and going_sample.get("places", 0) == 0:
            score += w.get("going_poor_pen2_wet", -4.0) if going_bucket in {"軟地", "重地"} else w.get("going_poor_pen2_dry", -3.0)
            notes.append(f"{going_bucket} 成績未見支持")

        if wet_state in {"soft7plus", "heavy"}:
            if not self._has_verified_wet_place():
                score += w.get("wet_unverified_pen", -5.0)
                notes.append("爛地實績未經驗證，轉場風險極高")
            elif wet_state == "heavy":
                heavy_stats = going_stats.get("重地", {})
                if heavy_stats.get("wins", 0) > 0:
                     score += w.get("heavy_win_bonus", 3.0)
                     notes.append("重地曾奪冠，泥漿戰力極強")
                     self.reason_codes.append("proven_heavy_specialist")
                elif heavy_stats.get("places", 0) > 0:
                     score += w.get("heavy_place_bonus", 2.0)
                     notes.append("具備重地作戰能力")
                elif heavy_stats.get("starts", 0) >= 2 and heavy_stats.get("places", 0) == 0:
                     score += w.get("heavy_poor_pen", -3.0)
                     notes.append("重地多次出賽全無表現，適應力有疑慮")
                     self.risk_flags.append("poor_heavy_performance")
            
            wet_bloodline = self._wet_bloodline_signal()
            if wet_bloodline == "正面" and not self._has_verified_wet_place():
                score += w.get("wet_bloodline_bonus", 3.0)
                notes.append("缺乏濕地實績，但血統輪廓顯示適合爛地")

        # 場地／地狀往績記錄行先（用戶要求）：一眼睇到同場、好/軟/重地實績
        rec_bits = []
        same = re.match(r"\s*(\d+:\d+-\d+-\d+)", str(self.data.get("track_stats_line") or ""))
        if same and same.group(1) != "0:0-0-0":
            rec_bits.append(f"同場 {same.group(1)}")
        gsl = str(self.data.get("going_stats_line") or "")
        gm = re.match(r"\s*(\d+:\d+-\d+-\d+)", gsl)
        if gm and gm.group(1) != "0:0-0-0":
            rec_bits.append(f"好地 {gm.group(1)}")
        for lab, key in (("軟地", "軟地"), ("重地", "重地")):
            mm = re.search(rf"{key}:\s*(\d+:\d+-\d+-\d+)", gsl)
            if mm and mm.group(1) != "0:0-0-0":
                rec_bits.append(f"{lab} {mm.group(1)}")
        rec_prefix = ("；".join(rec_bits) + "；") if rec_bits else ""
        tdetail["final"] = round(clip_score(score), 2)
        tdetail["notes"] = ([f"往績 {' / '.join(rec_bits)}"] if rec_bits else []) + list(notes)
        body = f"{rec_prefix}{'；'.join(notes) if notes else '場地資料未見鮮明優劣'}"
        return clip_score(score), f"{body}。場地分 {clip_score(score):.1f}。", "track_stats+going_stats+wet_track"

    def _formline_future_wins(self):
        rows = self._formline_rows()
        return sum(
            1 for row in rows
            if re.search(r"出\s*\d+\s*次:\s*(\d+)\s*勝", row.get("next_result", ""))
            and int(re.search(r"出\s*\d+\s*次:\s*(\d+)\s*勝", row.get("next_result", "")).group(1)) > 0
        )

    def _formline_strong_opponents(self):
        return sum(1 for row in self._formline_rows() if any(token in row.get("strength", "") for token in ("強", "極強", "超強")))

    def _formline_signal(self):
        text = str(self.data.get("formline_line") or "")
        has_rows = bool(self._formline_rows())
        if has_rows and self._is_misleading_formline_headline(text):
            inferred = self._formline_inferred_signal()
            if inferred:
                return inferred
        if "極強" in text or "超強組" in text:
            return "elite"
        elif "中強" in text:
            return "medium_strong"
        elif "中組" in text:
            return "medium"
        elif "中弱" in text:
            return "medium_weak"
        elif "強" in text:
            return "strong"
        elif "弱" in text:
            return "weak"
        elif "待驗證" in text:
            return "neutral"
        elif "無資料" in text or "未有出賽" in text:
            if has_rows:
                return "neutral"
            return "unknown"
        return "neutral"

    def _formline_score(self):
        signal = self._formline_signal()
        w = FORMLINE_MICRO_WEIGHTS
        mapping = {
            "elite": w.get("elite_base", 78.0),
            "strong": w.get("strong_base", 72.0),
            "medium_strong": w.get("med_strong_base", 68.0),
            "medium": w.get("med_base", 64.0),
            "medium_weak": w.get("med_weak_base", 56.0),
            "weak": w.get("weak_base", 50.0),
            "neutral": w.get("neutral_base", 58.0),
            "unknown": w.get("unknown_base", 58.0),
        }
        score = mapping.get(signal, w.get("unknown_base", 58.0))
        
        future_win_hits = self._formline_future_wins()
        strong_hits = self._formline_strong_opponents()
        followups = self._formline_followup_counts()
        headwinner = self._formline_headwinner()

        if future_win_hits:
            score += min(6, future_win_hits * w.get("future_win_bonus", 3.0))
        if strong_hits:
            score += min(4, strong_hits * w.get("strong_opp_bonus", 2.0))
        if followups["higher"] > 0:
            score += min(4, followups["higher"] * w.get("followup_higher_bonus", 2.0))
        if followups["same"] >= 2:
            score += w.get("followup_same_bonus", 2.0)
        if followups["lower"] >= 3 and followups["higher"] == 0:
            score += w.get("followup_lower_pen", -2.0)
        if headwinner and any(token in headwinner for token in ("頭馬", "亞軍")):
            score += w.get("headwinner_bonus", 2.0)

        row_strength_text = " ".join(str(row.get("strength") or "") for row in self._formline_rows())
        has_strong_row = any(token in row_strength_text for token in ("強組", "超強組", "極強組"))
        has_medium_row = "中組" in row_strength_text
        has_weak_row = "弱組" in row_strength_text
        text = str(self.data.get("formline_line") or "")
        if has_strong_row:
            score = max(score, w.get("med_strong_base", 68.0))
        elif has_weak_row and not has_medium_row:
            score = min(score, w.get("med_weak_base", 56.0) - 2.0)
        if ("無資料" in text or "未有出賽" in text) and not self._formline_rows():
            score = min(score, 60.0)

        signal_zh = {"elite": "頂級", "strong": "強", "medium_strong": "中強", "medium": "中等",
                     "medium_weak": "中偏弱", "weak": "弱", "neutral": "中性", "unknown": "資料不足"}
        notes = [f"賽績線級別{signal_zh.get(signal, signal)}"]
        if future_win_hits:
            notes.append(f"曾交手對手其後有 {future_win_hits} 場勝出")
        if strong_hits:
            notes.append(f"曾與 {strong_hits} 隻強組對手交手")
        if followups["higher"] > 0:
            notes.append(f"{followups['higher']} 匹對手其後升班出賽（對手成色指標）")
        if followups["same"] >= 2:
            notes.append(f"{followups['same']} 匹對手其後同班出賽")
        if followups["lower"] >= 3 and followups["higher"] == 0:
            notes.append("對手多數其後降班出賽，含金量有限")
        if headwinner and any(token in headwinner for token in ("頭馬", "亞軍")):
            notes.append(f"曾與 {headwinner} 直接交手")
        if has_strong_row:
            notes.append("賽績線含強組往績")
        elif has_weak_row and not has_medium_row:
            notes.append("賽績線多屬弱組")
        return clip_score(score), f"{'；'.join(notes)}，賽績線分 {clip_score(score):.1f}。", "formline+opponent_followups+class_followups+headwinner"

    def _consistency_score(self):
        w = CONSISTENCY_MICRO_WEIGHTS
        starts = self._career_starts()
        detail = {"base": None, "base_label": "基礎分", "adjustments": [],
                  "display_notes": [], "final": None}
        self.consistency_detail = detail
        if starts == 0:
            base0 = w.get("career0_base", 58.0)
            detail["base"] = round(base0, 2)
            detail["base_label"] = "初出馬固定分（以備戰完整度代替穩定樣本）"
            detail["final"] = round(clip_score(base0), 2)
            return base0, f"初出馬以備戰完整度代替穩定樣本，跑法穩定性 {clip_score(base0):.1f} 分。", "career_tag"

        score = w.get("base", 58.0)
        detail["base"] = round(score, 2)
        notes = []

        def add(delta, factor, evidence=""):
            nonlocal score
            score += delta
            detail["adjustments"].append({"delta": round(delta, 2),
                                          "factor": factor, "evidence": evidence})

        recent = parse_recent_finishes(self.data.get("recent_form"))
        if recent:
            window = recent[:6]
            places = sum(1 for x in window if x <= 3)
            poor = sum(1 for x in window if x >= 8)
            if places:
                add(places * w.get("recent_place_bonus", 7.0), "近績前三獎勵",
                    f"近{len(window)}仗{places}次前三（每次 {w.get('recent_place_bonus', 7.0):+.2f}）")
            if poor:
                add(poor * w.get("recent_poor_pen", -5.0), "大敗懲罰",
                    f"近{len(window)}仗{poor}次第八或以後（每次 {w.get('recent_poor_pen', -5.0):+.2f}）")
            notes.append(f"近仗有{places}次前三、{poor}次大敗")

            # 寬恕補償已退出計分（2026-07-10 A/B：移除對排名零影響，box4 微升）；
            # 寬恕背景改為純顯示解讀，唔再入分。
            if poor >= 2 and self._forgiveness_count() >= 2:
                detail["display_notes"].append("大敗場次多具寬恕理由（顯示參考，不入分）")
                notes.append("大敗場次多具寬恕理由（不入分）")

        # 輸距趨勢（2026-07-10 新增，用戶提出、HK 引擎亦有同類 credit）：
        # 近 2 仗平均輸距 vs 之前場次，改善/惡化 ≥2L → ±3。
        # A/B：全檔 GGP +1、A窗 +1、winT3 +0.6pp，無指標倒退；放近績側反而蝕（已反證）。
        margins = []
        for entry in self._official_entries()[:4]:
            m = re.search(r"\(([-+]?\d+(?:\.\d+)?)L\)", str(entry.get("placing") or ""))
            if m:
                margins.append(float(m.group(1)))
        if len(margins) >= 3:
            recent_margin = sum(margins[:2]) / 2
            older_margin = sum(margins[2:]) / len(margins[2:])
            improvement = recent_margin - older_margin
            mt = w.get("margin_trend_bonus", 3.0)
            if improvement >= 2.0:
                add(mt, "輸距趨勢改善",
                    f"近2仗平均輸距較之前收窄 {improvement:.1f}L")
                notes.append("輸距趨勢改善")
            elif improvement <= -2.0:
                add(-mt, "輸距趨勢惡化",
                    f"近2仗平均輸距較之前擴大 {abs(improvement):.1f}L")
                notes.append("輸距趨勢惡化")

        run_styles = [entry.get("run_style", "") for entry in self._official_entries()[:4] if entry.get("run_style") and entry.get("run_style") != "-"]
        # 樣本閘：得 1 場有跑法記錄唔構成「連貫」，要 ≥2 場全一致先畀分
        # （2026-07-10 A/B：全檔案 GGP +2、A窗 +1、B窗 +1、冠軍 +0.3pp，無指標倒退）
        if len(run_styles) >= 2 and len(set(run_styles)) == 1:
            add(w.get("run_style_bonus", 3.0), "跑法連貫獎勵",
                f"近{len(run_styles)}場正式賽跑法全部一致")
            notes.append("近期跑法連貫")

        if "穩定" in self._sectional_trends().get("pi_trend", ""):
            add(w.get("pi_stable_bonus", 2.0), "PI 走勢穩定獎勵", "段速 PI 趨勢呈穩定")

        repeatability = self._repeatability_brief()
        if "重覆前列交代" in repeatability or "直接對位" in repeatability:
            add(w.get("repeat_bonus", 2.0), "重複交代獎勵", repeatability)
            notes.append("派彩/對位具重複性")
        elif "未形成穩定交代" in repeatability:
            add(w.get("no_repeat_pen", -1.0), "未形成穩定交代", repeatability)

        detail["final"] = round(clip_score(score), 2)
        note_str = "；".join(notes) if notes else "未見特別跑法或表現穩定特徵"
        return score, f"{note_str}。跑法穩定性 {clip_score(score):.1f} 分。", "run_style+sectional_trend+repeatability"

    def _confidence_score(self):
        anchors = 0
        for value in (
            self.data.get("recent_form"),
            self.data.get("engine_line"),
            self.data.get("formline_line"),
            self.data.get("sectional_trend_line"),
            self.data.get("track_record_line"),
            self.data.get("going_stats_line"),
            self.data.get("stage_stats_line"),
            self._speed_map_field("tactical_nodes"),
            self._clean_identity(self.horse_data.get("trainer")),
            self._clean_identity(self.horse_data.get("jockey")),
            self._tactical_scenario_text(),
            self._meeting_bias_brief(),
            self._latest_l600_rt_brief(),
            self._current_jockey_history_brief(),
        ):
            if value and str(value).strip() not in {"N/A", "Unknown"}:
                anchors += 1
        score = 30 + anchors * 4
        if self._career_starts() == 0:
            score -= 4
        elif len(self._official_entries()) >= 3:
            score += 2
        if self._style_confidence() in {"高", "High"}:
            score += 3
        elif self._style_confidence() in {"低", "Low"}:
            score -= 1
        if str(self._speed_map_field("source") or "").strip():
            score += 2
        if self._formline_rows():
            score += 1
        if self._current_jockey_formal_rides() > 0 or self._current_jockey_trial_rides() > 0:
            score += 2
        if self._latest_l600_rt_brief():
            score += 1
        if self._has_last10_warning():
            score -= 4
        unresolved_forgiveness = sum(1 for entry in self._official_entries()[:4] if entry.get("forgiveness") == "[需判定]")
        if unresolved_forgiveness:
            score -= 1
        return score, f"可用分析錨點 {anchors}/14，並按 style confidence、正式樣本、jockey history、source 同 warnings 校正後，信心分 {clip_score(score):.1f}。", "data_coverage+style_meta+warnings+formline+jockey_history"

    def _health_score(self):
        if os.environ.get("WC_DISABLE_AU_HEALTH_SCORE") == "1":
            return 60.0, "健康/備戰分以 validation flag 暫作中性 60。", "disabled_neutral"
        score = 60.0
        notes = []
        warning_text = " ".join(
            str(value or "")
            for value in (
                self.data.get("warning_line"),
                self.data.get("gear_line"),
                self._latest_official_text(),
            )
        ).lower()
        if self._has_last10_warning():
            score -= 1.5
            notes.append("Last10/警告存在")
        if any(token in warning_text for token in ("lame", "cardiac", "bleed", "poor recovery", "vet", "vetted", "examined by vet")):
            score -= 2.0
            notes.append("近績有獸醫/健康疑點")
        if any(token in warning_text for token in ("slow recovery", "respiratory", "heart", "eased down")):
            score -= 1.5
            notes.append("恢復或呼吸/心肺訊號需保守")

        spell = self._spell_days()
        if 14 <= spell <= 45:
            score += 1.0
            notes.append(f"休後 {spell} 日屬正常間隔")
        elif spell > 90:
            trial_speed = parse_float(self.data.get("timing_trial_600m_avg_speed"))
            if trial_speed:
                score += 0.5
                notes.append(f"久休 {spell} 日但有試閘時間支撐")
            else:
                score -= 1.0
                notes.append(f"久休 {spell} 日而缺少試閘時間支撐")

        gear_line = str(self.data.get("gear_line") or "")
        if gear_line:
            if "Blinkers: Yes" in gear_line:
                score += 0.4
                notes.append("配戴 blinkers")
            changes = str(self.data.get("gear_changes") or "")
            if changes and changes.lower() != "none":
                score += 0.3
                notes.append("有 gear change 訊號")

        note = "；".join(notes) if notes else "未見明確健康或備戰扣分訊號"
        return score, f"{note}。備戰完整度分 {clip_score(score):.1f}。", "warnings+spell+gear"

    def _advantages(self, feature_scores, matrix_scores):
        items = []
        if matrix_scores.get("pace_perf", 60) >= 72:
            if feature_scores["distance_score"] >= 72:
                items.append("段速表現同路程配套對得上，唔係靠空想投射")
            else:
                items.append("段速底子唔差，末段輸出有條件交到貨")
        if matrix_scores["jockey_trainer"] >= 72:
            trainer = self._clean_identity(self.horse_data.get("trainer")) or "馬房"
            items.append(f"{trainer} 呢邊嘅部署訊號偏正面，人馬配搭有基本支持")
        if matrix_scores["track"] >= 70:
            items.append("場地或場館適性有實際證據，唔係紙上談兵")
        if matrix_scores["stability"] >= 70:
            items.append("近期交代密度夠，狀態線唔算飄")
        # BUGFIX 2026-07-03: matrix key is class_weight — the old class_level /
        # weight_pressure keys never exist, so this bullet could never fire.
        if matrix_scores.get("class_weight", 60) >= 68:
            items.append("班次同負磅未見吃力，發揮門檻唔高")
        if self._forgiveness_count() >= 2:
            items.append("近仗至少有一兩場蝕位或受阻，紙面名次可能低估真身")
        if self._formline_followup_counts()["higher"] > 0:
            items.append("對手後續升班仲交到貨，賽績線唔薄")
        if self._career_starts() == 0 and feature_scores["trial_score"] >= 72:
            items.append("初出前備戰唔差，試閘交代比一般新馬清晰")
        return items[:3] or ["整體結構平均，未見特別爆點，但亦唔算有明顯穿崩位"]

    def _disadvantages(self, feature_scores, matrix_scores):
        items = []
        if matrix_scores["race_shape"] <= 55:
            items.append("步速配腳未算理想，走位成本可能會先食蝕")
        if matrix_scores.get("class_weight", 60) <= 55:
            items.append("班次或負磅面前仍有壓力，容錯空間唔大")
        if matrix_scores["track"] <= 55:
            items.append("場地適性仍未有清楚支持，轉場條件未必幫到手")
        # 賽績線維度權重=0（純顯示、唔入排名），唔應該出現喺「主要風險」結論
        # 誤導用戶以為佢有份計分。2026-07-11 移除。
        if feature_scores["confidence_score"] <= 52:
            items.append("可用證據鏈未算完整，臨場變數自然會放大")
        if self._career_starts() == 0:
            items.append("初出馬正式實戰樣本仍然空白，臨場變數自然較大")
        if "pace_burn_risk" in self.risk_flags:
            items.append("若前段搶得太急，末段有互燒風險")
        if "distance_unproven" in self.risk_flags:
            items.append("路程仍未正式證明，去到最後 200 米未必一樣撐得住")
        if "top_weight" in self.risk_flags:
            items.append("頂磅環境下要自己讓人，發揮要求會更高")
        return items[:3] or ["主要變數仍然係臨場步速同對手反應，安全邊際只算一般"]

    def _au_readout_band(self, trend):
        t = str(trend or "")
        if any(w in t for w in ("上升", "進步", "加強", "改善", "受捧", "合拍", "已驗證", "升級")):
            return "✅"
        if any(w in t for w in ("下降", "退步", "放緩", "回落", "受冷", "轉差", "未驗證")):
            return "⚠️"
        return "➖"

    def _data_readout(self, feature_scores, matrix_scores):
        """Structured, fully-Chinese 數據判讀 rows for AU (label/value/trend/band/reason).
        Feeds the report + dashboard. Mirrors the HKJC readout using AU data lines."""
        rows = []

        def add(label, value, trend, band=None, reason=""):
            value = str(value or "").strip()
            trend = str(trend or "").strip()
            if value or trend:
                rows.append({"label": label, "value": value, "trend": trend,
                             "band": band or self._au_readout_band(trend), "reason": reason})

        def present(v):
            return v is not None and str(v).strip() not in ("", "N/A", "-", "--")

        d = self.data
        rf = d.get("recent_form") or self.horse_data.get("recent_form")
        if present(rf):
            add("近績", str(rf).strip(), "")
        l4 = self._l400_text()
        if l4:
            add("段速", l4, "")
        et = str(d.get("engine_type_line") or "")
        if present(et):
            m = re.search(r"（([^）]+)）|\(([^)]+)\)", et)  # keep the Chinese type, drop 'Type A/B'
            add("段速型態", (m.group(1) or m.group(2)) if m else et, "")
        dp = str(d.get("distance_profile_line") or "")
        # only the clean "今仗 1717m: …" segment; skip the messy "今仗 | ≥2000m" form
        m = re.search(r"今仗\s*\d+\s*m[：:]?\s*[^|（(]+", dp)
        if m:
            seg = m.group(0).strip(" -：:")
            band = "✅" if "✅" in m.group(0) else ("⚠️" if "⚠️" in m.group(0) else "➖")
            seg = re.sub(r"[✅⚠️]", "", seg).strip()
            add("今仗路程", seg, "", band=band)
        cm = d.get("class_move")
        if present(cm):
            cm_s = str(cm).strip()
            cband = "✅" if "降班" in cm_s else ("➖" if "升班" in cm_s else "➖")
            add("班次走向", cm_s, "", band=cband)
        # 檔位 + running-position bucket (AU has no per-barrier historical table,
        # so show the position bucket, not fabricated stats).
        bar = self.horse_data.get("barrier")
        if bar not in (None, "", 0):
            try:
                bn = int(bar)
                bucket = "內檔" if bn <= 4 else ("中檔" if bn <= 8 else ("外檔" if bn <= 12 else "極外檔"))
                add("檔位", f"{bn}檔", bucket, band="✅" if bn <= 4 else ("⚠️" if bn >= 13 else "➖"))
            except (TypeError, ValueError):
                pass
        # 預測跑法 — tactical position read (前置／守好位／守中／後上). Reference only:
        # explicitly NOT in the rating matrix. 戰術劇本（race scenario）只喺「檔位形勢」
        # 7D 維度出一次，呢度唔再塞落 reason，避免同一段劇本重覆四次。
        ps = self._predicted_style()
        if ps:
            add("預測跑法", ps["label"],
                f"信心{ps['conf']}" if ps["conf"] else "",
                band="➖")
        counts = self._formline_followup_counts()
        opp = self._formline_headwinner() if hasattr(self, "_formline_headwinner") else ""
        validated = counts["higher"] + counts["same"] + counts["lower"]
        field = set(self.race_context.get("field_horse_names") or []) if isinstance(getattr(self, "race_context", None), dict) else set()
        mine = self.horse_data.get("horse_name")
        h2h = sorted({nm for r in self._formline_rows() for nm in field
                      if nm and nm != mine and nm in str(r.get("opponent", ""))})
        if h2h:
            add("賽績線", "重遇" + "、".join(h2h), "曾交手", band="✅",
                reason=f"今場重遇曾交手對手{'、'.join(h2h)}")
        elif validated or opp:
            cls_bits = []
            if counts["higher"]:
                cls_bits.append(f"{counts['higher']}匹其後升班出賽")
            if counts["same"]:
                cls_bits.append(f"{counts['same']}匹同班出賽")
            if counts["lower"]:
                cls_bits.append(f"{counts['lower']}匹降班出賽")
            head = f"曾交手頭馬「{opp}」" if opp else "近仗對手線"
            add("賽績線", f"曾鬥頭馬「{opp}」" if opp else "近仗對手",
                "對手線有延續" if validated else "對手未驗證",
                band="✅" if validated else "➖",
                reason="；".join([head] + cls_bits) if cls_bits else head)
        mt = d.get("current_market_trend")
        if present(mt):
            band = "✅" if "受捧" in str(mt) else ("⚠️" if "受冷" in str(mt) else "➖")
            add("市場走勢", str(mt).strip(), "", band=band)
        gs = str(d.get("going_stats_line") or "")
        if present(gs):
            add("場地往績", gs.split("|")[0].strip(), "")
        cur = self._clean_identity(self.horse_data.get("jockey"))
        cur_line = str(d.get("current_jockey_history_line") or "")
        best_line = str(d.get("best_jockey_history_line") or "")
        if cur:
            up = best_line and cur and cur not in best_line  # today's rider ≠ the best historical one
            add("騎師", cur, "", reason=cur_line[:48] or None)
            if up and present(best_line):
                add("騎師往績", "", "最佳拍檔非今仗", band="➖", reason=best_line[:48])
        return rows

    def _core_logic(self, feature_scores, matrix_scores, advantages, disadvantages):
        """Data-grounded verdict: a concrete 七維 framing sentence, then the actual
        strengths and concerns (reusing the already-specific advantages/disadvantages).
        Drops the generic '做主軸 / 保留型 / 走勢未算鮮明' filler."""
        name = self.horse_data.get("horse_name", "此駒")
        ordered = sorted(matrix_scores.items(), key=lambda kv: kv[1], reverse=True)
        top_dim = self._matrix_label(ordered[0][0])
        low_dim = self._matrix_label(ordered[-1][0])
        sents = [f"{name}今場七維評分以{top_dim}（{ordered[0][1]:.0f}）最強、{low_dim}（{ordered[-1][1]:.0f}）最弱。"]
        real_adv = [a for a in (advantages or []) if "整體結構平均" not in a]
        real_dis = [d for d in (disadvantages or []) if "主要變數仍然係臨場步速" not in d]
        if real_adv:
            sents.append("優勢在於" + "；".join(real_adv[:3]) + "。")
        if real_dis:
            sents.append("要留意" + "；".join(real_dis[:3]) + "。")
        if not real_adv and not real_dis:
            sents.append("整體結構平均，未見特別爆點亦無明顯穿崩，臨場步速與形勢將係關鍵。")
        if self._career_starts() == 0:
            sents.append("初出馬正式賽績空白，以上以備戰及試閘數據作背景參考，須臨場驗證。")
        return re.sub(r"\s{2,}", " ", "".join(sents)).strip()

    def _forgiveness_brief(self):
        count = self._forgiveness_count()
        if count <= 0:
            return ""
        latest_flag = ""
        for entry in self._official_entries()[:4]:
            forgiveness = str(entry.get("forgiveness") or "").strip()
            if forgiveness and forgiveness not in {"[-]", "[需判定]"}:
                latest_flag = forgiveness
                break
        if latest_flag:
            return f"近四仗有 {count} 次可作寬恕，最近焦點為 {latest_flag}"
        return f"近四仗有 {count} 次可作寬恕"

    def _forgiveness_count(self):
        count = 0
        for entry in self._official_entries()[:4]:
            note = entry.get("notes", "")
            forgiveness = entry.get("forgiveness", "")
            if any(token in note for token in ("Too much start", "Worked early", "Crowded", "Bumped", "Steadied", "Looking for run")):
                count += 1
                continue
            if forgiveness and forgiveness not in {"[-]", "[需判定]"}:
                count += 1
        return count

    def _entry_distance_m(self, entry):
        return self._distance_from_text(entry.get("distance"))

    def _distance_from_text(self, value):
        match = re.search(r"(\d+)", str(value or ""))
        return int(match.group(1)) if match else 0


def enrich_logic_from_facts(logic_data: dict, facts_path: Path) -> dict:
    text = facts_path.read_text(encoding="utf-8")
    race_analysis = logic_data.setdefault("race_analysis", {})
    speed_map = race_analysis.setdefault("speed_map", {})
    auto_speed_map = _parse_speed_map(text)
    race_number = _extract_first_int(str(race_analysis.get("race_number") or facts_path.name), r"(\d+)")
    racecard_profiles = _load_racecard_profiles(facts_path, race_number)
    formguide_digests = _load_formguide_digests(facts_path, race_number)
    meeting_intelligence = _load_meeting_intelligence(facts_path, race_number)
    track_profile = _load_track_profile(
        meeting_intelligence.get("venue", ""),
        _distance_to_int(race_analysis.get("distance") or ""),
    )
    for key, value in auto_speed_map.items():
        if not speed_map.get(key):
            speed_map[key] = value
    for key in ("track_bias", "tactical_nodes", "collapse_point"):
        if key in speed_map:
            speed_map[key] = _normalize_speed_map_text(speed_map.get(key))
    if meeting_intelligence.get("going") and not speed_map.get("going"):
        speed_map["going"] = meeting_intelligence["going"]
    if meeting_intelligence:
        race_analysis["meeting_intelligence"] = meeting_intelligence
    if track_profile:
        race_analysis["track_profile"] = track_profile
    race_analysis["context_completeness"] = _context_completeness(meeting_intelligence, track_profile)
    if meeting_intelligence.get("going"):
        race_analysis["going"] = meeting_intelligence["going"]
    if meeting_intelligence.get("bias_summary"):
        race_analysis["track_bias"] = meeting_intelligence["bias_summary"]

    sections = _parse_horse_sections(text)
    for horse_num, horse in logic_data.get("horses", {}).items():
        section = sections.get(str(horse_num), {})
        racecard_profile = racecard_profiles.get(
            _normalize_horse_name(section.get("horse_name") or horse.get("horse_name"))
        ) or {}
        formguide = formguide_digests.get(str(horse_num), {})
        facts_section = section.get("raw_text", "")
        data = horse.setdefault("_data", {})
        data.pop("eem_summary", None)
        data.pop("eem_style", None)
        _merge_prefer_clean(horse, "horse_name", section.get("horse_name"))
        _merge_prefer_clean(horse, "jockey", section.get("jockey"))
        _merge_prefer_clean(horse, "trainer", section.get("trainer"))
        _merge_if_missing(horse, "rating", racecard_profile.get("horse_rating"))
        _merge_if_missing(horse, "weight", section.get("weight"))
        _merge_if_missing(horse, "barrier", section.get("barrier"))
        horse["tactical_plan"] = _build_tactical_plan(
            int(section.get("barrier") or horse.get("barrier") or 0),
            facts_section,
        )
        _merge_data_value(data, "horse_rating", racecard_profile.get("horse_rating"))
        _merge_data_value(data, "last10_raw", section.get("last10_raw"))
        _merge_data_value(data, "recent_form", section.get("recent_form"))
        _merge_data_value(data, "career_record_line", section.get("career_line"))
        _merge_data_value(data, "engine_line", section.get("engine_line"))
        _merge_data_value(data, "formline_line", section.get("formline_line"))
        _merge_data_value(data, "consumption_summary", section.get("consumption_summary"))
        _merge_data_value(data, "sectional_trend_line", section.get("sectional_trend_line"))
        _merge_data_value(data, "running_style_line", section.get("running_style_line"))
        _merge_data_value(data, "style_confidence_line", section.get("style_confidence_line"))
        _merge_data_value(data, "engine_type_line", section.get("engine_type_line"))
        _merge_data_value(data, "engine_confidence_line", section.get("engine_confidence_line"))
        _merge_data_value(data, "distance_profile_line", section.get("distance_profile_line"))
        _merge_data_value(data, "target_distance_line", section.get("target_distance_line"))
        _merge_data_value(data, "class_move", section.get("class_move"))
        _merge_data_value(data, "formal_count", section.get("formal_count"))
        _merge_data_value(data, "trial_count", section.get("trial_count"))
        _merge_data_value(data, "trial_top3_count", section.get("trial_top3_count"))
        _merge_data_value(data, "track_record_line", section.get("track_line"))
        _merge_data_value(data, "track_stats_line", section.get("track_stats_line"))
        _merge_data_value(data, "going_stats_line", section.get("going_stats_line"))
        _merge_data_value(data, "stage_stats_line", section.get("stage_stats_line"))
        _merge_data_value(data, "timing_600m_avg_speed", formguide.get("timing_600m_avg_speed"))
        _merge_data_value(data, "timing_600m_recent_speed", formguide.get("timing_600m_recent_speed"))
        _merge_data_value(data, "timing_600m_trend", formguide.get("timing_600m_trend"))
        _merge_data_value(data, "timing_600m_best_speed", formguide.get("timing_600m_best_speed"))
        _merge_data_value(data, "timing_l600_entries_count", formguide.get("timing_l600_entries_count"))
        _merge_data_value(data, "timing_speed_variance", formguide.get("timing_speed_variance"))
        _merge_data_value(data, "trial_video_signals", formguide.get("trial_video_signals"))
        _merge_data_value(data, "timing_trial_600m_avg_speed", formguide.get("timing_trial_600m_avg_speed"))
        _merge_data_value(data, "facts_section", facts_section)
        _merge_data_value(data, "last_finish_line", section.get("last_finish_line"))
        _merge_data_value(data, "warning_line", section.get("warning_line"))
        _merge_data_value(data, "sire_line", formguide.get("sire_line"))
        _merge_data_value(data, "current_market_line", formguide.get("current_market_line"))
        _merge_data_value(data, "current_market_first", formguide.get("current_market_first"))
        _merge_data_value(data, "current_market_last", formguide.get("current_market_last"))
        _merge_data_value(data, "current_market_low", formguide.get("current_market_low"))
        _merge_data_value(data, "current_market_trend", formguide.get("current_market_trend"))
        _merge_data_value(data, "gear_line", formguide.get("gear_line"))
        _merge_data_value(data, "has_blinkers", formguide.get("has_blinkers"))
        _merge_data_value(data, "gear_changes", formguide.get("gear_changes"))
        _merge_data_value(data, "latest_official_date", formguide.get("latest_official_date"))
        _merge_data_value(data, "latest_official_jockey", formguide.get("latest_official_jockey"))
        _merge_data_value(data, "latest_official_last_flucs", formguide.get("latest_official_last_flucs"))
        _merge_data_value(data, "latest_official_market_trend", formguide.get("latest_official_market_trend"))
        _merge_data_value(data, "latest_official_jockey_formal_rides", formguide.get("latest_official_jockey_formal_rides"))
        _merge_data_value(data, "latest_official_jockey_formal_places", formguide.get("latest_official_jockey_formal_places"))
        _merge_data_value(data, "latest_official_jockey_formal_wins", formguide.get("latest_official_jockey_formal_wins"))
        _merge_data_value(data, "latest_trial_jockey", formguide.get("latest_trial_jockey"))
        _merge_data_value(data, "current_jockey_formal_rides", formguide.get("current_jockey_formal_rides"))
        _merge_data_value(data, "current_jockey_formal_places", formguide.get("current_jockey_formal_places"))
        _merge_data_value(data, "current_jockey_formal_wins", formguide.get("current_jockey_formal_wins"))
        _merge_data_value(data, "current_jockey_trial_rides", formguide.get("current_jockey_trial_rides"))
        _merge_data_value(data, "current_jockey_trial_top3", formguide.get("current_jockey_trial_top3"))
        _merge_data_value(data, "current_jockey_history_line", formguide.get("current_jockey_history_line"))
        _merge_data_value(data, "best_formal_jockey", formguide.get("best_formal_jockey"))
        _merge_data_value(data, "best_formal_jockey_rides", formguide.get("best_formal_jockey_rides"))
        _merge_data_value(data, "best_formal_jockey_places", formguide.get("best_formal_jockey_places"))
        _merge_data_value(data, "best_formal_jockey_wins", formguide.get("best_formal_jockey_wins"))
        _merge_data_value(data, "best_jockey_history_line", formguide.get("best_jockey_history_line"))
        _merge_data_value(data, "current_vs_best_jockey_line", formguide.get("current_vs_best_jockey_line"))
        _merge_data_value(data, "known_jockeys_line", formguide.get("known_jockeys_line"))
        _merge_data_value(data, "jockey_change_signal", formguide.get("jockey_change_signal"))
        _merge_data_value(data, "official_market_support_count", formguide.get("official_market_support_count"))
        _merge_data_value(data, "official_market_miss_count", formguide.get("official_market_miss_count"))
        _merge_data_value(data, "recent_settled_pattern_line", formguide.get("recent_settled_pattern_line"))
        _merge_data_value(data, "recent_400_pattern_line", formguide.get("recent_400_pattern_line"))
        _merge_data_value(data, "recent_shape_consensus", formguide.get("recent_shape_consensus"))
        _merge_data_value(data, "recent_shape_entropy", formguide.get("recent_shape_entropy"))
        _merge_data_value(data, "recent_shape_consensus_count", formguide.get("recent_shape_consensus_count"))
        _merge_data_value(data, "recent_shape_front_count", formguide.get("recent_shape_front_count"))
        _merge_data_value(data, "recent_shape_mid_count", formguide.get("recent_shape_mid_count"))
        _merge_data_value(data, "recent_shape_back_count", formguide.get("recent_shape_back_count"))
        _merge_data_value(data, "recent_shape_inside_count", formguide.get("recent_shape_inside_count"))
        _merge_data_value(data, "recent_shape_wide_no_cover_count", formguide.get("recent_shape_wide_no_cover_count"))
        _merge_data_value(data, "recent_shape_early_work_count", formguide.get("recent_shape_early_work_count"))
        _merge_data_value(data, "recent_shape_summary_line", formguide.get("recent_shape_summary_line"))
        if not str(data.get("current_jockey_history_line") or "").strip():
            current_jockey = _clean_identity(horse.get("jockey"))
            best_jockey = _clean_identity(data.get("best_formal_jockey"))
            if current_jockey:
                if best_jockey and best_jockey != current_jockey:
                    data["current_jockey_history_line"] = f"{current_jockey} 暫未見正式賽或試閘合作紀錄"
                else:
                    data["current_jockey_history_line"] = f"{current_jockey} 暫未見正式賽合作紀錄"
    return logic_data


def _merge_if_missing(target, key, value):
    if value in (None, "", "Unknown"):
        return
    if target.get(key) in (None, "", 0, "Unknown"):
        target[key] = value


def _merge_prefer_clean(target, key, value):
    clean_value = _clean_identity(value)
    if clean_value in ("", "Unknown"):
        return
    existing = target.get(key)
    clean_existing = _clean_identity(existing)
    if existing in (None, "", "Unknown", 0) or clean_existing != existing or existing != clean_value:
        target[key] = clean_value


def _merge_data_value(target, key, value):
    if value in (None, ""):
        return
    existing = target.get(key)
    if existing in (None, "", "Unknown"):
        target[key] = value


def _parse_speed_map(text: str) -> dict:
    block_match = re.search(
        r"### 🗺️ 自動步速圖.*?(?=^=+|\Z)",
        text,
        re.M | re.S,
    )
    if not block_match:
        return {}
    block = block_match.group(0)
    def field(name):
        match = re.search(rf"- \*\*{re.escape(name)}:\*\* (.+)$", block, re.M)
        return match.group(1).strip() if match else ""
    return {
        "predicted_pace": field("predicted_pace"),
        "expected_pace": field("predicted_pace"),
        "pace_confidence": field("pace_confidence"),
        "style_confidence": field("style_confidence"),
        "leaders": _parse_num_list(field("leaders")),
        "pressers": _parse_num_list(field("pressers")),
        "on_pace": _parse_num_list(field("on_pace")),
        "mid_pack": _parse_num_list(field("mid_pack")),
        "closers": _parse_num_list(field("closers")),
        "style_evidence": field("style_evidence"),
        "track_bias": _normalize_speed_map_text(field("track_bias")),
        "tactical_nodes": _normalize_speed_map_text(field("tactical_nodes")),
        "collapse_point": _normalize_speed_map_text(field("collapse_point")),
        "going": field("going"),
        "source": field("source"),
    }


def _parse_num_list(text):
    return [int(x) for x in re.findall(r"\d+", str(text or ""))]


def _parse_horse_sections(text: str) -> dict:
    matches = list(HORSE_BLOCK_RE.finditer(text))
    sections = {}
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end]
        horse_num = match.group(1)
        sections[horse_num] = {
            "horse_name": match.group(2).strip(),
            "barrier": int(match.group(3)),
            "jockey": (match.group(4) or "").strip() or "Unknown",
            "trainer": (match.group(5) or "").strip() or "Unknown",
            "weight": parse_float(match.group(6)),
            "last10_raw": _capture(block, r"Last 10 字串:\s*`?([^`\n]+)`?"),
            "recent_form": _capture(block, r"近績序列解讀: `?([^`\n]+)`?"),
            "career_line": _capture(block, r"生涯: ([^\n]+)"),
            "track_line": _capture(block, r"同場: ([^\n]+)") or _capture(block, r"好地: ([^\n]+)"),
            "track_stats_line": _capture(block, r"同場: ([^\n]+)"),
            "going_stats_line": _capture(block, r"好地: ([^\n]+)"),
            "stage_stats_line": _capture(block, r"初出: ([^\n]+)"),
            "last_finish_line": _capture(block, r"上仗結果\(Racecard\): ([^\n]+)"),
            "warning_line": _capture(block, r"⚠️ 警告: ([^\n]+)"),
            "engine_line": _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)"),
            "formline_line": _capture(block, r"\*\*綜合評估:\*\* ([^\n]+)"),
            "consumption_summary": _capture_multiline(block, r"- \*\*⚡ 走位消耗摘要:\*\*(.*?)(?=\n- \*\*🔗|\n- \*\*🔧|\n### |\Z)"),
            "sectional_trend_line": _capture_multiline(block, r"- \*\*📊 段速趨勢.*?\*\*(.*?)(?=\n- \*\*⚡|\n### |\Z)"),
            "running_style_line": _extract_running_style_line(block),
            "style_confidence_line": _extract_running_style_confidence(block),
            "engine_type_line": _extract_engine_type_line(block),
            "engine_confidence_line": _extract_engine_confidence(block),
            "distance_profile_line": _extract_distance_profile_line(block),
            "target_distance_line": _extract_target_distance_line(block),
            "class_move": _extract_latest_class_move(block),
            "formal_count": _count_formal_rows(block),
            "trial_count": _count_trial_rows(block),
            "trial_top3_count": _count_trial_top3(block),
            "raw_text": block,
        }
    return sections


def _capture(text, pattern):
    match = re.search(pattern, text, re.M)
    return match.group(1).strip() if match else ""


def _capture_multiline(text, pattern):
    match = re.search(pattern, text, re.M | re.S)
    return " ".join(line.strip() for line in match.group(1).splitlines() if line.strip()) if match else ""


def _record_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        text = line.strip()
        if not text.startswith("|") or "| 類型 |" in text or "|---" in text:
            continue
        cols = [col.strip() for col in text.strip("|").split("|")]
        if len(cols) >= 10:
            rows.append(cols)
    return rows


def _count_trial_rows(block: str) -> int:
    return sum(1 for cols in _record_rows(block) if "試閘" in cols[1])


def _count_formal_rows(block: str) -> int:
    return sum(1 for cols in _record_rows(block) if "試閘" not in cols[1])


def _count_trial_top3(block: str) -> int:
    total = 0
    for cols in _record_rows(block):
        if "試閘" not in cols[1]:
            continue
        match = re.search(r"\d+", cols[7])
        if match and int(match.group(0)) <= 3:
            total += 1
    return total


def _extract_latest_class_move(block: str) -> str:
    for cols in _record_rows(block):
        if "試閘" in cols[1]:
            continue
        return cols[8]
    return ""


def _extract_running_style_line(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"跑法:\s*([^|]+)", engine_block)
    return match.group(1).strip() if match else ""


def _extract_running_style_confidence(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"跑法:\s*[^|]+\|\s*信心:\s*([^|]+)", engine_block)
    return match.group(1).strip() if match else ""


def _extract_engine_type_line(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"引擎:\s*([^|]+)", engine_block)
    return match.group(1).strip() if match else ""


def _extract_engine_confidence(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"引擎:\s*[^|]+\|\s*信心:\s*([^|]+)", engine_block)
    return match.group(1).strip() if match else ""


def _extract_distance_profile_line(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"距離分佈:\s*([^\n]+)", engine_block)
    return match.group(1).strip() if match else ""


def _extract_target_distance_line(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"今仗\s+[0-9]+m\s+\([^)]+\):\s*([^\n]+)", engine_block)
    return match.group(0).strip() if match else ""


def _build_tactical_plan(barrier: int, block: str) -> dict:
    style = _extract_running_style_line(block)
    latest_official = next((cols for cols in _record_rows(block) if "試閘" not in cols[1]), None)
    latest_run_style = latest_official[14].strip() if latest_official and len(latest_official) > 14 else ""
    latest_consumption = latest_official[15].strip() if latest_official and len(latest_official) > 15 else ""
    latest_notes = latest_official[16].strip() if latest_official and len(latest_official) > 16 else ""
    expected_position = _expected_position_label(style, latest_run_style, barrier)
    race_scenario = _tactical_scenario_text(expected_position, barrier, latest_consumption, latest_notes)
    return {
        "expected_position": expected_position,
        "race_scenario": race_scenario,
    }


def _expected_position_label(style: str, latest_run_style: str, barrier: int) -> str:
    text = f"{style} {latest_run_style}".strip()
    if any(token in text for token in ("前置", "跟前", "居中前", "前領", "領放")):
        return "前置 / 跟前"
    if any(token in text for token in ("後上", "中後", "後追")):
        return "中後 / 後上"
    if barrier <= 3:
        return "守中 / 內欄"
    return "守中 / 居中"


def _tactical_scenario_text(expected_position: str, barrier: int, consumption: str, notes: str) -> str:
    if "前置" in expected_position:
        if barrier <= 4:
            text = f"出閘後可憑{barrier}檔主動守住前列，首彎前以省位切入為先，入直路前保持走位主動權。"
        elif barrier <= 8:
            text = f"出閘後宜先推前爭位，盡量喺首彎前切入前列，避免中段被迫走外疊。"
        else:
            text = f"外檔下若要保持前置，需要出閘後即時推前搶位；若未能順利切入，走位成本會較高。"
    elif "中後" in expected_position or "後上" in expected_position:
        if barrier <= 4:
            text = f"可先靠{barrier}檔節省腳程守中後列，等待入直路前望空再逐步推進。"
        elif barrier <= 8:
            text = "預計先留居中後列搵遮擋，入直路前再逐步移出追勢。"
        else:
            text = "外檔下宜先收後搵遮擋，避免早段白白走外疊，入直路前再逐步移出追勢。"
    else:
        if barrier <= 3:
            text = f"出閘後可先憑{barrier}檔貼欄守中，首彎前減少白走，入直路前再搵位發力。"
        elif barrier <= 8:
            text = "預計先守中列或中內疊，沿途以慳位為主，入直路前再視乎空位逐步推進。"
        else:
            text = "外檔下先求順利搵遮擋守中，避免長時間無遮擋走外疊，末段再逐步移出。"
    if any(token in notes for token in ("Looking for run", "Crowded", "Steadied", "Across heels")):
        text += " 入直路前亦要留意望空同移位時機。"
    return text


def _formguide_path_for_facts(facts_path: Path, race_number: int = 0) -> Path | None:
    race_number = race_number or _extract_race_number_from_text_or_name(facts_path.read_text(encoding="utf-8"), facts_path.name)
    matches = sorted(facts_path.parent.glob(f"*Race {race_number} Formguide.md"))
    return matches[0] if matches else None


def _load_formguide_digests(facts_path: Path, race_number: int = 0) -> dict[str, dict]:
    formguide_path = _formguide_path_for_facts(facts_path, race_number)
    if not formguide_path or not formguide_path.exists():
        return {}
    text = formguide_path.read_text(encoding="utf-8")
    sections = list(re.finditer(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", text, re.M))
    output: dict[str, dict] = {}
    for idx, match in enumerate(sections):
        start = match.start()
        end = sections[idx + 1].start() if idx + 1 < len(sections) else len(text)
        section = text[start:end]
        output[match.group(1)] = _summarize_formguide_section(section, match.group(2).strip())
    return output


def _extract_race_number_from_text_or_name(text: str, filename: str) -> int:
    match = re.search(r"Race[ _](\d+)", filename)
    if match:
        return int(match.group(1))
    header = re.search(r"RACE\s+(\d+)", text)
    return int(header.group(1)) if header else 1


def _parse_trial_video_signals(trial_entries: list[dict]) -> dict:
    signals = {"restrained": 0, "full_test": 0, "competitive": 0, "weakened": 0,
               "led": 0, "improving": 0}
    for e in trial_entries:
        video = str(e.get("video") or "").lower()
        if not video or video == "none":
            continue
        if any(t in video for t in ['held together','not asked','not extended','under restraint','ridden quietly','held together','untested']):
            signals["restrained"] += 1
        if any(t in video for t in ['urged along','pushed along','asked for effort','ridden along','hard ridden','ridden out']):
            signals["full_test"] += 1
        if any(t in video for t in ['kept chasing','chased hard','made ground','kept closing','fought','prevail','kept going','battled']):
            signals["competitive"] += 1
        # BUGFIX 2026-07-03: 'beaten' matched "unbeaten" and 'battled' double-counted
        # against the competitive list; word-boundary 'beaten', drop 'battled' here.
        if re.search(r"\bbeaten\b", video) or any(t in video for t in ['weakened','drifted','tired','faded','gave ground','wd badly','wd latter']):
            signals["weakened"] += 1
        # BUGFIX 2026-07-03: bare 'led' matched "settled"/"bustled" — boilerplate in
        # trial comments — inflating the led count. Word-boundary it.
        if re.search(r"\bled\b", video) or any(t in video for t in ['leader','found lead','narrow lead','tracked leader','sett fence']):
            signals["led"] += 1
        if any(t in video for t in ['improved','passed runner','made ground late','kept coming','wound-up']):
            signals["improving"] += 1
    return signals


def _summarize_formguide_section(section: str, horse_name: str) -> dict:
    current_jockey = _capture(section, r"\|\s*J:\s*([^(\n|]+)")
    sire_line = _capture(section, r"Sire:\s*([^|]+)")
    current_market_line = _capture(section, r"^Flucs:\s*(.+)$")
    current_market_values = _parse_fluc_values(current_market_line)
    gear_line = _capture(section, r"^Gear:\s*(.+)$")
    gear_changes = _capture(gear_line, r"Changes:\s*(.+)$") if gear_line else ""
    entries = _parse_formguide_entries(section, horse_name)
    official_entries = [entry for entry in entries if not entry["is_trial"]]
    trial_entries = [entry for entry in entries if entry["is_trial"]]
    latest_official = official_entries[0] if official_entries else {}
    latest_trial = trial_entries[0] if trial_entries else {}
    timing_summary = _build_timing_summary(official_entries, trial_entries)
    trial_video_signals = _parse_trial_video_signals(trial_entries)
    recent_shape = _summarize_recent_shape(official_entries)

    jockey_stats: dict[str, dict] = {}
    for entry in entries:
        jockey = _clean_identity(entry.get("jockey"))
        if not jockey:
            continue
        bucket = jockey_stats.setdefault(jockey, {"formal_rides": 0, "formal_places": 0, "formal_wins": 0, "trial_rides": 0, "trial_top3": 0})
        finish_pos = entry.get("finish_pos")
        if entry["is_trial"]:
            bucket["trial_rides"] += 1
            if finish_pos is not None and finish_pos <= 3:
                bucket["trial_top3"] += 1
        else:
            bucket["formal_rides"] += 1
            if finish_pos is not None and finish_pos <= 3:
                bucket["formal_places"] += 1
            if finish_pos == 1:
                bucket["formal_wins"] += 1

    current_bucket = jockey_stats.get(_clean_identity(current_jockey), {})
    best_jockey_name, best_jockey_bucket = _best_jockey_name_and_bucket(jockey_stats)
    known_jockeys = [
        _jockey_summary_line(name, stats)
        for name, stats in sorted(jockey_stats.items(), key=lambda item: _jockey_bucket_sort_key(item[1]), reverse=True)
        if stats.get("formal_rides")
    ]
    supported_official = 0
    missed_supported = 0
    for entry in official_entries:
        last_flucs = parse_float(entry.get("last_flucs"))
        finish_pos = entry.get("finish_pos")
        if last_flucs is not None and last_flucs <= 3.5:
            supported_official += 1
            if finish_pos is None or finish_pos > 3:
                missed_supported += 1

    return {
        "sire_line": sire_line,
        "current_market_line": current_market_line,
        "current_market_first": current_market_values[0] if current_market_values else "",
        "current_market_last": current_market_values[-1] if current_market_values else "",
        "current_market_low": min(current_market_values) if current_market_values else "",
        "current_market_trend": _market_trend_label(current_market_values),
        "gear_line": gear_line,
        "has_blinkers": "Blinkers: Yes" in gear_line,
        "gear_changes": gear_changes,
        "latest_official_date": latest_official.get("date") or "",
        "latest_official_jockey": _clean_identity(latest_official.get("jockey")),
        "latest_official_last_flucs": latest_official.get("last_flucs") or "",
        "latest_official_market_trend": _market_trend_label(_parse_fluc_values(latest_official.get("flucs") or latest_official.get("last_flucs") or "")),
        "latest_official_jockey_formal_rides": jockey_stats.get(_clean_identity(latest_official.get("jockey")), {}).get("formal_rides", 0),
        "latest_official_jockey_formal_places": jockey_stats.get(_clean_identity(latest_official.get("jockey")), {}).get("formal_places", 0),
        "latest_official_jockey_formal_wins": jockey_stats.get(_clean_identity(latest_official.get("jockey")), {}).get("formal_wins", 0),
        "latest_trial_jockey": _clean_identity(latest_trial.get("jockey")),
        "current_jockey_formal_rides": current_bucket.get("formal_rides", 0),
        "current_jockey_formal_places": current_bucket.get("formal_places", 0),
        "current_jockey_formal_wins": current_bucket.get("formal_wins", 0),
        "current_jockey_trial_rides": current_bucket.get("trial_rides", 0),
        "current_jockey_trial_top3": current_bucket.get("trial_top3", 0),
        "current_jockey_history_line": _current_jockey_history_line(
            _clean_identity(current_jockey),
            current_bucket,
            best_jockey_name,
            best_jockey_bucket,
        ),
        "best_formal_jockey": best_jockey_name,
        "best_formal_jockey_rides": best_jockey_bucket.get("formal_rides", 0),
        "best_formal_jockey_places": best_jockey_bucket.get("formal_places", 0),
        "best_formal_jockey_wins": best_jockey_bucket.get("formal_wins", 0),
        "best_jockey_history_line": _jockey_history_line(best_jockey_name, best_jockey_bucket),
        "current_vs_best_jockey_line": _jockey_compare_line(_clean_identity(current_jockey), current_bucket, best_jockey_name, best_jockey_bucket),
        "known_jockeys_line": " / ".join(known_jockeys[:4]),
        "jockey_change_signal": _derive_jockey_change_signal(
            _clean_identity(current_jockey),
            _clean_identity(latest_official.get("jockey")),
            _clean_identity(latest_trial.get("jockey")),
            current_bucket,
            jockey_stats.get(_clean_identity(latest_official.get("jockey")), {}),
            best_jockey_name,
            best_jockey_bucket,
        ),
        "official_market_support_count": supported_official,
        "official_market_miss_count": missed_supported,
        "recent_settled_pattern_line": recent_shape["settled_pattern_line"],
        "recent_400_pattern_line": recent_shape["pos400_pattern_line"],
        "recent_shape_consensus": recent_shape["consensus_bucket"],
        "recent_shape_entropy": recent_shape["entropy"],
        "recent_shape_consensus_count": recent_shape["consensus_count"],
        "recent_shape_front_count": recent_shape["front_count"],
        "recent_shape_mid_count": recent_shape["mid_count"],
        "recent_shape_back_count": recent_shape["back_count"],
        "recent_shape_inside_count": recent_shape["inside_count"],
        "recent_shape_wide_no_cover_count": recent_shape["wide_no_cover_count"],
        "recent_shape_early_work_count": recent_shape["early_work_count"],
        "recent_shape_summary_line": recent_shape["summary_line"],
        "trial_video_signals": trial_video_signals,
        "timing_600m_avg_speed": timing_summary["avg_600m_speed"],
        "timing_600m_recent_speed": timing_summary["recent_600m_speed"],
        "timing_600m_trend": timing_summary["trend_600m_speed"],
        "timing_600m_best_speed": timing_summary["best_600m_speed"],
        "timing_same_dist_600m_speed": timing_summary["same_dist_600m_speed"],
        "timing_l600_entries_count": timing_summary["l600_entries_count"],
        "timing_speed_variance": timing_summary.get("speed_variance"),
        "timing_trial_600m_avg_speed": timing_summary.get("trial_600m_avg_speed"),
    }


def _build_timing_summary(official_entries: list[dict], trial_entries: list[dict]) -> dict:
    l600_speeds = []
    for entry in official_entries:
        split = entry.get("l600_split_seconds")
        if split and 20 < split < 50:
            l600_speeds.append(600.0 / split)
    recent_speeds = l600_speeds[:3]
    recent_avg = sum(recent_speeds) / len(recent_speeds) if recent_speeds else None
    avg_speed = sum(l600_speeds) / len(l600_speeds) if l600_speeds else None
    best_speed = max(l600_speeds) if l600_speeds else None
    trend = ""
    if len(l600_speeds) >= 3:
        older = l600_speeds[2:][:2] if len(l600_speeds) >= 4 else [l600_speeds[-1]]
        newer = l600_speeds[:2]
        if len(older) >= 2 and len(newer) >= 2:
            old_avg = sum(older) / len(older)
            new_avg = sum(newer) / len(newer)
            delta = new_avg - old_avg
            if delta > 0.8:
                trend = "sharp_improving"
            elif delta > 0.3:
                trend = "improving"
            elif delta > -0.3:
                trend = "stable"
            elif delta > -0.8:
                trend = "declining"
            else:
                trend = "sharp_declining"
    trial_l600 = []
    for entry in trial_entries:
        split = entry.get("l600_split_seconds")
        if split and 20 < split < 50:
            trial_l600.append(600.0 / split)
    trial_avg = sum(trial_l600) / len(trial_l600) if trial_l600 else None
    speed_variance = None
    if len(l600_speeds) >= 3:
        mean_s = sum(l600_speeds) / len(l600_speeds)
        speed_variance = round(sum((s - mean_s) ** 2 for s in l600_speeds) / len(l600_speeds), 3)
    return {
        "avg_600m_speed": round(avg_speed, 2) if avg_speed else None,
        "recent_600m_speed": round(recent_avg, 2) if recent_avg else None,
        "best_600m_speed": round(best_speed, 2) if best_speed else None,
        "trend_600m_speed": trend,
        "same_dist_600m_speed": None,
        "l600_entries_count": len(l600_speeds),
        "trial_600m_avg_speed": round(trial_avg, 2) if trial_avg else None,
        "speed_variance": speed_variance,
    }


def _parse_time_to_seconds(text: str) -> float | None:
    match = re.search(r"(\d{2}):(\d{2})\.(\d{3})", text)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2)) + int(match.group(3)) / 1000.0


def _parse_iso_date(text: str):
    match = re.search(r"(\d{4}-\d{2}-\d{2})", str(text or ""))
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d")
    except ValueError:
        return None


def _parse_formguide_entries(section: str, horse_name: str) -> list[dict]:
    pattern = re.compile(r"^(\S.+?)\s+R(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+m)\s+cond:(\S+)\s+\$([0-9,]+)", re.M)
    entries = []
    hn_clean = horse_name.split("(")[0].strip().lower()
    matches = list(pattern.finditer(section))
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section)
        block = section[start:end]
        header = block.splitlines()[0] if block.splitlines() else ""
        prize_str = match.group(6).replace(",", "")
        is_trial = "**(TRIAL)**" in header or prize_str == "0"
        jockey_match = re.search(r"\$[0-9,]+\s+(.+?)\s+\((\d+|None)\)\s+(\S+kg|Nonekg)", header)
        jockey = jockey_match.group(1).strip() if jockey_match else ""
        flucs_match = re.search(r"Flucs:([$\d\s.]+)", header)
        flucs = flucs_match.group(1).strip() if flucs_match else ""
        fluc_values = _parse_fluc_values(flucs)
        result_line_match = re.search(r"^(1-.+?)$", block, re.M)
        result_line = result_line_match.group(1).strip() if result_line_match else ""
        finish_pos = None
        margin = None
        if result_line and hn_clean:
            for pos_m in re.finditer(r"(\d+)-([^(]+)\s*\(([^)]+)\)(?:\s+(\d+\.?\d*)L)?", result_line):
                name_in_result = pos_m.group(2).strip().lower()
                if hn_clean[:6] in name_in_result or name_in_result[:6] in hn_clean:
                    finish_pos = int(pos_m.group(1))
                    if pos_m.group(4):
                        margin = float(pos_m.group(4))
                    break
        note = _capture(block, r"^Note:\s*(.+)$")
        stewards = _capture(block, r"^Stewards:\s*(.+)$")
        video = _capture(block, r"^Video:\s*(.+)$")
        winner_time = _parse_time_to_seconds(header)
        l600_split = None
        l600_match = re.search(r"\(?600m\s*/\s*(\d{2}:\d{2}\.\d{3})\)?", header)
        if l600_match:
            l600_split = _parse_time_to_seconds(l600_match.group(1))
        entries.append({
            "date": match.group(3),
            "is_trial": is_trial,
            "jockey": jockey,
            "flucs": flucs,
            "last_flucs": fluc_values[-1] if fluc_values else "",
            "finish_pos": finish_pos,
            "margin": margin,
            "settled_pos": _parse_running_position(header, "Settled"),
            "pos_400": _parse_running_position(header, "400m"),
            "pos_800": _parse_running_position(header, "800m"),
            "winner_time_seconds": winner_time,
            "l600_split_seconds": l600_split,
            "note": note,
            "stewards": stewards,
            "video": video,
        })
    return entries


def _parse_running_position(header: str, marker: str) -> int | None:
    match = re.search(rf"(\d+)(?:st|nd|rd|th)@{re.escape(marker)}", str(header or ""), re.I)
    return int(match.group(1)) if match else None


def _entry_shape_bucket(entry: dict) -> str:
    settled = entry.get("settled_pos")
    if isinstance(settled, int):
        if settled <= 3:
            return "front"
        if settled <= 6:
            return "mid"
        return "back"
    text = " ".join(str(entry.get(key) or "") for key in ("video", "note", "stewards")).lower()
    if any(token in text for token in (" led", "leader", "front")):
        return "front"
    if any(token in text for token in ("rear", "towards rear", "backmarker")):
        return "back"
    if any(token in text for token in ("midfield", "sett 4th", "sett 5th", "sett 6th")):
        return "mid"
    return ""


def _summarize_recent_shape(entries: list[dict]) -> dict:
    official = entries[:4]
    settled = [entry.get("settled_pos") for entry in official if isinstance(entry.get("settled_pos"), int)]
    pos400 = [entry.get("pos_400") for entry in official if isinstance(entry.get("pos_400"), int)]
    bucket_counts = Counter()
    inside_count = 0
    wide_no_cover_count = 0
    early_work_count = 0
    for entry in official:
        bucket = _entry_shape_bucket(entry)
        if bucket:
            bucket_counts[bucket] += 1
        text = " ".join(str(entry.get(key) or "") for key in ("video", "note", "stewards"))
        lower = text.lower()
        if any(token in lower for token in ("sett fence", " fence", "rails", "inside")):
            inside_count += 1
        if any(token in text for token in ("WNC", "without cover", "3WNC", "4WNC", "very wide", "Widest")):
            wide_no_cover_count += 1
        if any(token in lower for token in ("worked early", "do some work", "unable to cross", "riding mnt forward", "obliged to do some work")):
            early_work_count += 1
    non_zero = [(bucket, count) for bucket, count in bucket_counts.items() if count > 0]
    consensus_bucket = ""
    consensus_count = 0
    if non_zero:
        consensus_bucket, consensus_count = max(non_zero, key=lambda item: item[1])
    summary_parts = []
    if settled:
        summary_parts.append("Settled " + "→".join(str(pos) for pos in settled))
    if bucket_counts:
        summary_parts.append(
            f"front {bucket_counts.get('front', 0)} / mid {bucket_counts.get('mid', 0)} / back {bucket_counts.get('back', 0)}"
        )
    if wide_no_cover_count:
        summary_parts.append(f"白走/WNC {wide_no_cover_count} 次")
    if early_work_count:
        summary_parts.append(f"早段做多 {early_work_count} 次")
    return {
        "settled_pattern_line": "→".join(str(pos) for pos in settled),
        "pos400_pattern_line": "→".join(str(pos) for pos in pos400),
        "consensus_bucket": consensus_bucket,
        "consensus_count": consensus_count,
        "entropy": len(non_zero),
        "front_count": bucket_counts.get("front", 0),
        "mid_count": bucket_counts.get("mid", 0),
        "back_count": bucket_counts.get("back", 0),
        "inside_count": inside_count,
        "wide_no_cover_count": wide_no_cover_count,
        "early_work_count": early_work_count,
        "summary_line": "；".join(summary_parts),
    }


def _parse_fluc_values(text: str) -> list[float]:
    values = []
    for match in re.findall(r"\$?([0-9]+(?:\.[0-9]+)?)", str(text or "")):
        try:
            values.append(float(match))
        except ValueError:
            continue
    return values


def _market_trend_label(values: list[float]) -> str:
    if len(values) < 2:
        return ""
    first = values[0]
    last = values[-1]
    if last <= first * 0.9:
        return "持續受捧"
    if last >= first * 1.1:
        return "後段轉冷"
    return "大致持平"


def _jockey_history_line(current_jockey: str, bucket: dict) -> str:
    if not current_jockey or not bucket:
        return ""
    parts = []
    if bucket.get("formal_rides", 0):
        parts.append(f"{current_jockey} 曾策正式賽 {bucket['formal_rides']} 次，{bucket['formal_wins']} 勝 {bucket['formal_places']} 上名")
    if bucket.get("trial_rides", 0):
        parts.append(f"試閘 {bucket['trial_rides']} 次，{bucket['trial_top3']} 次前三")
    return "；".join(parts)


def _current_jockey_history_line(current_jockey: str, bucket: dict, best_jockey: str, best_bucket: dict) -> str:
    direct = _jockey_history_line(current_jockey, bucket)
    if direct:
        return direct
    if current_jockey:
        if best_jockey and best_bucket.get("formal_rides", 0):
            return f"{current_jockey} 暫未見正式賽或試閘合作紀錄"
        return f"{current_jockey} 暫未見正式賽合作紀錄"
    return ""


def _jockey_bucket_sort_key(bucket: dict) -> tuple[int, int, int, int]:
    return (
        int(bucket.get("formal_wins", 0)),
        int(bucket.get("formal_places", 0)),
        int(bucket.get("formal_rides", 0)),
        int(bucket.get("trial_top3", 0)),
    )


def _best_jockey_name_and_bucket(jockey_stats: dict[str, dict]) -> tuple[str, dict]:
    formal_only = [(name, stats) for name, stats in jockey_stats.items() if stats.get("formal_rides")]
    if not formal_only:
        return "", {}
    name, stats = max(formal_only, key=lambda item: _jockey_bucket_sort_key(item[1]))
    return name, stats


def _jockey_summary_line(jockey: str, bucket: dict) -> str:
    if not jockey or not bucket or not bucket.get("formal_rides"):
        return jockey or ""
    return f"{jockey}({bucket.get('formal_wins', 0)}-{bucket.get('formal_places', 0)}/{bucket.get('formal_rides', 0)})"


def _jockey_compare_line(current_jockey: str, current_bucket: dict, best_jockey: str, best_bucket: dict) -> str:
    if not current_jockey or not best_jockey or current_jockey == best_jockey:
        return ""
    if current_bucket.get("formal_rides", 0):
        return (
            f"今場由 {current_jockey} 接手，個別正式賽合作為 "
            f"{current_bucket.get('formal_wins', 0)} 勝 {current_bucket.get('formal_places', 0)} 上名 / {current_bucket.get('formal_rides', 0)} 次；"
            f"歷來最佳配搭為 {best_jockey} 的 {best_bucket.get('formal_wins', 0)} 勝 {best_bucket.get('formal_places', 0)} 上名 / {best_bucket.get('formal_rides', 0)} 次"
        )
    return (
        f"今場由 {current_jockey} 首次或少合作接手，歷來最佳正式賽配搭為 "
        f"{best_jockey} 的 {best_bucket.get('formal_wins', 0)} 勝 {best_bucket.get('formal_places', 0)} 上名 / {best_bucket.get('formal_rides', 0)} 次"
    )


def _derive_jockey_change_signal(
    current_jockey: str,
    latest_official: str,
    latest_trial: str,
    current_bucket: dict,
    latest_official_bucket: dict,
    best_jockey: str = "",
    best_bucket: dict | None = None,
) -> str:
    best_bucket = best_bucket or {}
    latest_official_bucket = latest_official_bucket or {}
    current_place_rate = safe_ratio(current_bucket.get("formal_places", 0), current_bucket.get("formal_rides", 0))
    latest_place_rate = safe_ratio(latest_official_bucket.get("formal_places", 0), latest_official_bucket.get("formal_rides", 0))
    if current_jockey and latest_official and current_jockey == latest_official:
        if best_jockey and current_jockey == best_jockey and best_bucket.get("formal_places", 0) > 0:
            return "沿用歷來最佳配搭"
        return "沿用上仗騎師"
    if current_jockey and latest_trial and current_jockey == latest_trial:
        return "試閘手接手"
    if current_jockey and best_jockey and current_jockey == best_jockey and current_jockey != latest_official:
        return f"回配歷來最佳騎師 {current_jockey}"
    if current_jockey and current_bucket.get("formal_rides", 0) > 0 and latest_official and current_jockey != latest_official:
        if current_place_rate > latest_place_rate and current_bucket.get("formal_places", 0) >= latest_official_bucket.get("formal_places", 0):
            return f"回配較合拍騎師 {current_jockey}"
        return f"回配 {current_jockey}"
    if current_jockey and latest_official and current_jockey != latest_official:
        if current_place_rate >= 0.5 and current_bucket.get("formal_places", 0) >= 2 and latest_official_bucket.get("formal_rides", 0) > 0 and current_place_rate > latest_place_rate:
            return f"由 {latest_official} 轉配更合拍騎師 {current_jockey}"
        if latest_official_bucket.get("formal_rides", 0) > 0 and latest_place_rate >= 0.5 and current_bucket.get("formal_rides", 0) == 0:
            return f"由 {latest_official} 離開已證明配搭"
        return f"由 {latest_official} 轉配 {current_jockey}"
    return ""


def _normalize_speed_map_text(text: str) -> str:
    value = str(text or "")
    value = value.replace("EEM/settled", "video/settled")
    return value


def _load_meeting_intelligence(facts_path: Path, race_number: int = 0) -> dict:
    meeting_path = facts_path.parent / "_Meeting_Intelligence_Package.md"
    if meeting_path.exists():
        intelligence = _parse_meeting_intelligence(meeting_path.read_text(encoding="utf-8"), facts_path.parent.name)
    else:
        intelligence = {}
    fallback = _meeting_context_from_extractor_files(facts_path, race_number)
    for key, value in fallback.items():
        if value and not intelligence.get(key):
            intelligence[key] = value
    if fallback:
        intelligence["source"] = _merge_sources(intelligence.get("source"), fallback.get("source"))
    return intelligence


def _meeting_context_from_extractor_files(facts_path: Path, race_number: int = 0) -> dict:
    folder = facts_path.parent
    context = {
        "venue": _venue_from_folder_name(folder.name),
        "date": _capture(folder.name, r"(\d{4}-\d{2}-\d{2})"),
        "weather_summary": "",
        "track_summary": "",
        "going": "",
        "rail_position": "",
        "bias_summary": "",
        "surface": "",
        "source": "",
    }
    sources: list[str] = []

    summary_path = folder / "Meeting_Summary.md"
    if summary_path.exists():
        summary = summary_path.read_text(encoding="utf-8")
        context["date"] = _first_clean(_capture(summary, r"^Date:\s*([^\n]+)"), context["date"])
        context["going"] = _first_clean(_capture(summary, r"^Track Condition:\s*([^\n]+)"), context["going"])
        context["surface"] = _first_clean(_capture(summary, r"^Surface:\s*([^\n]+)"), context["surface"])
        context["weather_summary"] = _first_clean(_capture(summary, r"^Weather:\s*([^\n]+)"), context["weather_summary"])
        context["rail_position"] = _first_clean(_capture(summary, r"^Rails?:\s*([^\n]+)"), context["rail_position"])
        sources.append("Meeting_Summary.md")

    race_number = race_number or _extract_first_int(facts_path.name, r"Race[ _](\d+)")
    racecards = sorted(folder.glob(f"*Race {race_number} Racecard.md"))
    if racecards:
        racecard = racecards[0].read_text(encoding="utf-8")
        meta_line = _first_line_matching(racecard, r"^Track:")
        if meta_line:
            context["going"] = _first_clean(_capture(meta_line, r"Track:\s*([^|]+)"), context["going"])
            context["weather_summary"] = _first_clean(_capture(meta_line, r"Weather:\s*([^|]+)"), context["weather_summary"])
            context["rail_position"] = _first_clean(_capture(meta_line, r"Rail:\s*([^|]+)"), context["rail_position"])
            sources.append(racecards[0].name)

    if context["going"]:
        context["track_summary"] = context["going"]
    context["source"] = " + ".join(dict.fromkeys(sources + (["folder_name"] if context["venue"] else [])))
    return {key: value for key, value in context.items() if value}


def _venue_from_folder_name(name: str) -> str:
    value = re.sub(r"^\d{4}-\d{2}-\d{2}[_\s-]*", "", str(name or "")).strip()
    value = re.sub(r"\bRace\s*\d+.*$", "", value, flags=re.I).strip(" _-")
    value = value.replace("_", " ").strip()
    return value


def _first_line_matching(text: str, pattern: str) -> str:
    regex = re.compile(pattern)
    for line in str(text or "").splitlines():
        if regex.search(line.strip()):
            return line.strip()
    return ""


def _first_clean(value: str, fallback: str = "") -> str:
    clean = str(value or "").strip().strip(" |")
    return clean or str(fallback or "").strip()


def _merge_sources(primary: str, fallback: str) -> str:
    parts = []
    for raw in (primary, fallback):
        for part in re.split(r"\s+\+\s+|;", str(raw or "")):
            clean = part.strip()
            if clean and clean not in parts:
                parts.append(clean)
    return " + ".join(parts)


def _context_completeness(meeting_intelligence: dict, track_profile: dict) -> dict:
    return {
        "venue": bool(meeting_intelligence.get("venue")),
        "date": bool(meeting_intelligence.get("date")),
        "going": bool(meeting_intelligence.get("going")),
        "rail_position": bool(meeting_intelligence.get("rail_position")),
        "weather_summary": bool(meeting_intelligence.get("weather_summary")),
        "track_profile": bool(track_profile),
    }


def _parse_meeting_intelligence(text: str, fallback_venue: str = "") -> dict:
    venue_match = re.search(r"Venue:\s*([^\n]+)", text)
    date_match = re.search(r"Date:\s*([^\n]+)", text)
    weather_block = _section_text(text, "## Weather / 天氣狀況", "## Track Condition / 場地狀況")
    track_block = _section_text(text, "## Track Condition / 場地狀況", "## Track Bias / 賽道偏差預測")
    bias_block = _section_text(text, "## Track Bias / 賽道偏差預測", "## Sources / 資料來源")
    source_block = _section_text(text, "## Sources / 資料來源")
    going_match = re.search(r"Track condition extracted:\s*([^\n.]+)", track_block)
    rail_match = re.search(r"Rail position .*?:\s*([^\n.]+)", track_block)
    return {
        "venue": (venue_match.group(1).strip() if venue_match else fallback_venue).strip(),
        "date": date_match.group(1).strip() if date_match else "",
        "weather_summary": _compact_text(weather_block),
        "track_summary": _compact_text(track_block),
        "going": going_match.group(1).strip() if going_match else "",
        "rail_position": rail_match.group(1).strip() if rail_match else "",
        "bias_summary": _compact_text(bias_block),
        "source": _compact_text(source_block),
    }


def _load_track_profile(venue: str, distance_m: int = 0) -> dict:
    if not str(venue or "").strip():
        return {}
    cache_key = (str(venue).lower().strip(), int(distance_m or 0))
    cached = TRACK_PROFILE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    venue_lower = venue.lower().strip()
    track_file = None
    for key, filename in VENUE_TRACK_MAP.items():
        if key in venue_lower:
            track_file = TRACK_RESOURCE_DIR / filename
            break
    if not track_file or not track_file.exists():
        fallback = TRACK_RESOURCE_DIR / "04b_track_provincial.md"
        track_file = fallback if fallback.exists() else None
    if not track_file or not track_file.exists():
        return {}
    text = track_file.read_text(encoding="utf-8")
    section = _track_venue_section(text, venue) or text
    profile = {
        "venue": venue,
        "circumference_m": _track_table_int(section, "周長") or _extract_first_int(section, r"(?:賽道)?周長:\**\s*([0-9]+)m"),
        "straight_m": _track_table_int(section, "直路") or _extract_first_int(section, r"直路(?:長度)?:\**\s*([0-9]+)m"),
        "direction": _track_table_text(section, "方向") or _capture(section, r"賽道風向:\**\s*([^\n]+)"),
        "key_traits": _extract_track_traits(section),
        "distance_note": _compact_text(_track_distance_note(section, distance_m) or _track_distance_note(text, distance_m)),
        "going_note": _compact_text(_section_text(section, "## 🌧️ 天氣與場地互動 (Track Condition Bias)") or _section_text(text, "## 🌧️ 天氣與場地互動 (Track Condition Bias)")),
        "source_file": track_file.name,
    }
    TRACK_PROFILE_CACHE[cache_key] = profile
    return profile


def _track_venue_section(text: str, venue: str) -> str:
    venue_words = [re.escape(part) for part in re.split(r"\s+", str(venue or "").strip()) if part]
    if not venue_words:
        return ""
    venue_pattern = r"\s+".join(venue_words)
    match = re.search(rf"(^##\s+.*{venue_pattern}.*?\n.*?)(?=^##\s+|\Z)", text, re.I | re.M | re.S)
    return match.group(1).strip() if match else ""


def _track_table_text(text: str, label: str) -> str:
    match = re.search(rf"^\|\s*\*\*{re.escape(label)}\*\*\s*\|\s*([^|\n]+)", text, re.M)
    return match.group(1).strip() if match else ""


def _track_table_int(text: str, label: str) -> int:
    value = _track_table_text(text, label)
    match = re.search(r"([0-9]+)", value)
    return int(match.group(1)) if match else 0


def _track_distance_note(text: str, distance_m: int) -> str:
    if distance_m <= 0:
        return ""
    sections = (
        (range(1000, 1101), r"### 1000m & 1100m .*?\n"),
        (range(1200, 1301), r"### 1200m & 1300m\n"),
        (range(1400, 1601), r"### 1400m & 1600m\n"),
    )
    for distance_range, heading in sections:
        if distance_m not in distance_range:
            continue
        match = re.search(rf"({heading}.*?)(?=\n### |\n## |\Z)", text, re.S)
        if match:
            return match.group(1)
    return ""


def _extract_track_traits(text: str) -> list[str]:
    line = _capture(text, r"特徵標籤:\**\s*([^\n]+)")
    traits = []
    for item in re.split(r"/|,|\|", line):
        clean = item.strip().strip("[]`")
        clean = clean.replace("ON-PACE", "On-Pace").replace("TIGHT-TURNING", "Tight-turning")
        if clean:
            traits.append(clean)
    if not traits:
        traits.extend(_compact_text(item) for item in re.findall(r"^\-\s+(.+)$", text, re.M))
    return traits


def _section_text(text: str, start: str, end: str | None = None) -> str:
    if start not in text:
        return ""
    pattern = re.escape(start) + r"(.*)"
    if end:
        pattern = re.escape(start) + r"(.*?)(?=" + re.escape(end) + r"|\Z)"
    match = re.search(pattern, text, re.S)
    return match.group(1).strip() if match else ""


def _compact_text(text: str) -> str:
    value = str(text or "").replace("*", "")
    value = re.sub(r"^###\s*", "", value, flags=re.M)
    value = re.sub(r"^\-\s*", "", value, flags=re.M)
    return " ".join(value.split())


# ── Barrier bias lookup tables ──
# Derived from AU_Racing_Historical_Stats.md venue-level barrier analysis.
# Values represent ability_score adjustment: positive = advantage, negative = disadvantage.

def _distance_to_int(distance: str) -> int:
    match = re.search(r"(\d+)", str(distance or ""))
    return int(match.group(1)) if match else 0


def _extract_first_int(text: str, pattern: str) -> int:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0


def _clean_identity(value):
    text = str(value or "").strip()
    if not text:
        return ""
    text = FIELD_TRAILER_RE.sub("", text)
    return text.strip(" |")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _normalize_horse_name(name: str) -> str:
    return _slug(re.sub(r"\s*\([^)]*\)", "", str(name or "")))


def _load_racecard_profiles(facts_path: Path, race_number: int) -> dict[str, dict]:
    if race_number <= 0:
        return {}
    candidates = sorted(facts_path.parent.glob(f"*Race {race_number} Racecard.md"))
    if not candidates:
        return {}
    lines = candidates[0].read_text(encoding="utf-8").splitlines()
    profiles: dict[str, dict] = {}
    index = 0
    while index < len(lines):
        horse_match = RACECARD_HORSE_RE.match(lines[index].strip())
        if not horse_match or index + 1 >= len(lines):
            index += 1
            continue
        meta_match = RACECARD_META_RE.match(lines[index + 1].strip())
        if meta_match:
            horse_name = _clean_identity(horse_match.group(1))
            profiles[_normalize_horse_name(horse_name)] = {
                # rating group is optional (unrated horses) — keep the weight either way
                "horse_rating": float(meta_match.group(2)) if meta_match.group(2) else None,
                "declared_weight": float(meta_match.group(1)),
            }
        index += 2
    return profiles
