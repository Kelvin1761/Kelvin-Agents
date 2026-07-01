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
from rank_adjustments import (
    jt_sample_size_rank_cap,
    narrow_overrated_rank_shield,

    market_free_rank_adjustment,
)
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
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "scripts"))  # .agents/scripts/
try:
    from formline_analyzer import analyze_formline as _fa_analyze_formline, _parse_margin as _fa_parse_margin, _extract_opponent_name as _fa_extract_name
    from jockey_trainer_analyzer import analyze_jockey_trainer as _jta_analyze_jockey_trainer
    _HAS_SHARED_LIBS = True
except ImportError:
    _HAS_SHARED_LIBS = False

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


TRIAL_CLASS_RE = re.compile(r"\*\*(TRIAL)\*\*")
FIELD_TRAILER_RE = re.compile(r"\s*\|\s*負重:\s*[0-9.]+kg\s*$")
HORSE_BLOCK_RE = re.compile(
    r"^### 馬匹 #(\d+) (.+?) \(檔位 (\d+)\)"
    r"(?: \| 騎師: ([^|]+))?"
    r"(?: \| 練馬師: ([^|]+?))?"
    r"(?: \| 負重: ([0-9.]+)kg)?$",
    re.M,
)
RACECARD_HORSE_RE = re.compile(r"^\d+\.\s+(.+?)\s+\((\d+)\)$")
RACECARD_META_RE = re.compile(
    r"^Trainer:\s.*?\|\sJockey:\s.*?\|\sWeight:\s*([0-9.]+)(?:kg)?(?:\s*\([^|]*\))?\s*\|\sAge:\s.*?\|\sRating:\s*([0-9.]+)"
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
            feature_notes["form_score"] = feature_notes.get("form_score", "") + "；[環境] 級數偏弱，亢奮已輕度收回"
        if feature_scores.get("consistency_score", 60) >= 72 and ts < 60:
            feature_scores["consistency_score"] = feature_scores["consistency_score"] - 4
            feature_notes["consistency_score"] = feature_notes.get("consistency_score", "") + "；[環境] 場地未明，穩定度已輕度收回"
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
        core_logic_transparency = self._au_core_logic_transparency(feature_scores, matrix_scores, matrix, base_7d_score, ability_score, grade)

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
            "core_logic_transparency": core_logic_transparency,
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
        if starts == 0:
            self.reason_codes.append("debut_form_neutral")
            return 60, "初出馬無正式賽績，近績分按保守 60 分處理。", "career_tag"
            
        entries = self._official_entries()
        if not entries:
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
            
            if place <= 5:
                if class_mult > 1.0:
                    notes.append(f"曾於較強班次入前五(降班優勢 x{class_mult})")
                elif class_mult < 1.0:
                    notes.append(f"曾於較弱班次入前五(升班折扣 x{class_mult})")
        
        if total_applied_weights > 0:
            avg_score = total_weighted_score / total_applied_weights
        else:
            avg_score = 60
            
        score = min(100.0, max(0.0, avg_score))
        
        if self._is_maiden_race():
            trial_count = int(parse_float(self.data.get("trial_count")) or 0)
            trial_top3 = int(parse_float(self.data.get("trial_top3_count")) or 0)
            if trial_count >= 4 and trial_top3 >= 3:
                score += 5
                self.reason_codes.append("maiden_trial_form_proxy")
                notes.append("試閘成績優異作賽績參考")
            elif trial_count >= 3 and trial_top3 >= 2:
                score += 3
        
        note_str = "；".join(list(dict.fromkeys(notes))) if notes else "近績一般"
        return score, f"採用班次及時間加權平均計算法，{note_str}。近績分 {clip_score(score):.1f}。", "recent_form+class_weighted"


    def _trial_score(self):
        trial_places = self._trial_places()
        starts = self._career_starts()
        is_maiden = self._is_maiden_race()
        if not trial_places:
            return 58 if starts == 0 else 60, "試閘訊號有限，試閘分保守處理。", "trial_table"
        good = sum(1 for place in trial_places[:3] if place <= 3)
        score = 56 + good * 9
        trial_count = int(parse_float(self.data.get("trial_count")) or len(trial_places))
        latest_trial = trial_places[0] if trial_places else None
        if starts == 0:
            score += 4
            if is_maiden:
                score += 2
                self.reason_codes.append("maiden_debut_trial_boost")
        if latest_trial == 1:
            score += 4
            if is_maiden:
                score += 2
        elif latest_trial is not None and latest_trial <= 3:
            score += 2
            if is_maiden:
                score += 1
        if trial_count >= 4 and safe_ratio(good, max(1, min(3, trial_count))) >= 0.66:
            score += 2
            if is_maiden and trial_count >= 6 and safe_ratio(good, trial_count) >= 0.6:
                score += 3
                self.reason_codes.append("maiden_trial_density_boost")
        # Maiden: trial speed as direct signal
        if is_maiden:
            tw_trial = self.data.get("timing_trial_600m_avg_speed")
            if tw_trial and tw_trial >= 17.5:
                score += 4
                self.reason_codes.append("maiden_fast_trial_speed")
            elif tw_trial and tw_trial >= 17.0:
                score += 2
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
                score += 4 if starts == 0 or is_maiden else 2
                self.reason_codes.append("trial_restrained_signal")
            if competitive >= 2:
                score += 4
            elif competitive >= 1:
                score += 2
            if led >= 2 and competitive >= 1:
                score += 3
                self.reason_codes.append("trial_led_competitive")
            elif led >= 1 and competitive >= 1:
                score += 1
            if improving >= 1:
                score += 2
            if weakened >= 2:
                score -= 4
            elif weakened >= 1:
                score -= 2
            if full_test >= 2 and competitive == 0:
                score -= 3
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
        total_score = w.get("base", 40.0)
        notes = [f"基礎分 {total_score} 分"]

        # 1. Average PI (Max 25)
        pi_from_entries = []
        for entry in entries:
            pi_val = parse_float(entry.get("pi"))
            if pi_val is not None:
                pi_from_entries.append(pi_val)

        if not pi_from_entries:
            tw_trial = self.data.get("timing_trial_600m_avg_speed")
            if tw_trial and tw_trial > 0:
                trial_l600 = 600.0 / tw_trial
                if trial_l600 <= 33.5:
                    total_score += w.get("trial_extreme_bonus", 40.0)
                    notes.append(f"初出/無紀錄馬: 試閘 L600 ({trial_l600:.1f}s) 極速補償 (+{w.get('trial_extreme_bonus', 40.0)})")
                elif trial_l600 <= 34.0:
                    total_score += w.get("trial_excellent_bonus", 25.0)
                    notes.append(f"初出/無紀錄馬: 試閘 L600 ({trial_l600:.1f}s) 優秀補償 (+{w.get('trial_excellent_bonus', 25.0)})")
                elif trial_l600 <= 34.8:
                    total_score += w.get("trial_pass_bonus", 10.0)
                    notes.append(f"初出/無紀錄馬: 試閘 L600 ({trial_l600:.1f}s) 合格補償 (+{w.get('trial_pass_bonus', 10.0)})")
                else:
                    notes.append(f"初出/無紀錄馬: 試閘 L600 ({trial_l600:.1f}s) 偏慢 (0)")
            else:
                notes.append("缺乏正式 L400 數據及試閘時間 (0)")
        else:
            recent_pi = sum(pi_from_entries[:2]) / len(pi_from_entries[:2]) if len(pi_from_entries) >= 1 else pi_from_entries[0]
            avg_pi = sum(pi_from_entries) / len(pi_from_entries)
            max_pi = max(pi_from_entries)

            if avg_pi >= 4.0:
                total_score += w.get("pi_extreme_bonus", 25.0)
                notes.append(f"平均 L400 PI 極佳 (+{w.get('pi_extreme_bonus', 25.0)})")
            elif avg_pi >= 2.0:
                total_score += w.get("pi_excellent_bonus", 15.0)
                notes.append(f"平均 L400 PI 優秀 (+{w.get('pi_excellent_bonus', 15.0)})")
            elif avg_pi >= 0.0:
                total_score += w.get("pi_pass_bonus", 5.0)
                notes.append(f"平均 L400 PI 達標 (+{w.get('pi_pass_bonus', 5.0)})")
            else:
                notes.append("平均 L400 PI 為負，缺乏後勁 (0)")

            # 2. Distance-Adjusted L600 Peak (Max 15)
            tw_best = self.data.get("timing_600m_best_speed")
            if tw_best and tw_best > 0:
                best_l600 = 600.0 / tw_best
                race_dist = self._distance_from_text(self.race_context.get("distance", ""))
                if race_dist and race_dist >= 600:
                    std_l600 = _lookup_standard_l600(self._current_venue_name(), race_dist)
                    if std_l600 and std_l600 > 0:
                        delta = best_l600 - std_l600
                        if delta <= -0.6:
                            total_score += w.get("l600_extreme_bonus", 15.0)
                            notes.append(f"最佳 L600 ({best_l600:.2f}s vs 標準 {std_l600:.2f}s) 突破路程極限 (+{w.get('l600_extreme_bonus', 15.0)})")
                        elif delta <= -0.3:
                            total_score += w.get("l600_excellent_bonus", 5.0)
                            notes.append(f"最佳 L600 ({best_l600:.2f}s) 達該路程優秀級別 (+{w.get('l600_excellent_bonus', 5.0)})")
                        else:
                            notes.append(f"最佳 L600 ({best_l600:.2f}s) 未見路程極速優勢 (0)")

            # 3. Trend & Peak PI (Max 10)
            if max_pi >= 6.0:
                total_score += w.get("peak_pi_bonus", 5.0)
                notes.append(f"生涯曾交出頂峰級別 PI 爆發 (+{w.get('peak_pi_bonus', 5.0)})")
            if recent_pi > avg_pi + 2.0:
                total_score += w.get("trend_up_bonus", 5.0)
                notes.append(f"近期 PI 呈現強烈上升軌 (+{w.get('trend_up_bonus', 5.0)})")
            elif recent_pi < avg_pi - 3.0:
                total_score = max(0, total_score + w.get("trend_down_pen", -10.0))
                notes.append(f"近期 PI 嚴重退步 ({w.get('trend_down_pen', -10.0)})")

            # 4. Realization & Forgiveness (Max 10)
            if avg_pi > 0 and recent_top4 > 0:
                total_score += w.get("realization_bonus", 10.0)
                notes.append(f"高 PI 成功兌現為前列成績 (+{w.get('realization_bonus', 10.0)})")
            elif avg_pi > 2.0 and forgiveness_count >= 1:
                total_score += w.get("forgiveness_bonus", 5.0)
                notes.append(f"高 PI 未兌現但有受阻/寬恕背景 (+{w.get('forgiveness_bonus', 5.0)})")

        total_score = min(100.0, max(0.0, total_score))
        
        self._sectional_breakdown_cache = {
            "score": total_score,
            "notes": "；".join(notes) if notes else "-",
            "label": "Base 40 + PI/L600 累加"
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
        notes.append(
            "段速採用 Zero-based (L400 PI + L600 Peak) 模型累積計分"
        )
        if breakdown.get("notes") and breakdown["notes"] != "-":
            notes.append(breakdown["notes"])
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
        if barrier is not None:
            if barrier <= 4:
                bucket = "inside"
            elif barrier <= 8:
                bucket = "middle"
            elif barrier <= 12:
                bucket = "outside"
            else:
                bucket = "wide"

            track = self.race_context.get("track", "").title()
            distance = str(self.race_context.get("distance", ""))
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

            if stats and stats.get("sample_size", 0) > 0:
                win_rate = stats.get("win_rate", expected_wr)
                modifier = (win_rate - expected_wr) * 100 * w.get("modifier_multiplier", 1.0)
                # Dampen the modifier slightly to avoid over-punishing wide draws in tiny samples
                modifier = max(w.get("modifier_cap_min", -6.0), min(w.get("modifier_cap_max", 6.0), modifier))
                score += modifier
                notes.append(f"檔位 {int(barrier)} ({bucket}) 據 {source_level} 統計勝率為 {win_rate*100:.1f}% (基準 {expected_wr*100:.1f}%)")
                if modifier > 2:
                    notes.append("排位具統計優勢")
                elif modifier < -2:
                    notes.append("排位具統計劣勢")
            else:
                # Absolute fallback if matrix fails completely
                if barrier >= 12:
                    score += w.get("fallback_wide_pen", -4.0)
                    notes.append("排位外檔，無統計數據參考")
                elif barrier <= 4:
                    score += w.get("fallback_inside_bonus", 2.0)
                    notes.append("排位內檔，無統計數據參考")

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

    def _jockey_score(self):
        jockey = self._clean_identity(self.horse_data.get("jockey"))
        rating = self._jockey_rating_profile(jockey)
        if rating:
            score = rating["base_score"]
            tier_text = self._rating_tier_text(rating.get("tier"), "jockey")
            note = f"{jockey} 按 AU 騎師資料庫列作 {tier_text}"
            if rating.get("confidence") == "provisional":
                note += "（暫定補名）"
            return score, f"{note}，騎師分 {clip_score(score):.1f}。", "jockey_rating_db"

        score = 60
        elite_tokens = (
            "McDonald", "Rawiller", "Pike", "Allen", "King", "Melham",
            "Collett", "Berry", "Clark", "Hyeronimus", "Schiller", "Lloyd",
            "Shinn", "Zahra", "Lane", "Bowman", "Kah", "Prebble", "Parr"
        )
        solid_tokens = ("McEvoy", "Layt", "Bayliss", "Moore", "Roper", "Costin", "Bullock", "Gibbons", "Jones")
        if any(token in jockey for token in elite_tokens):
            score += JOCKEY_MICRO_WEIGHTS.get("elite_bonus", 12.0)
            return score, f"{jockey} 屬高階騎師，騎師分 {clip_score(score):.1f}。", "jockey_name_fallback"
        if any(token in jockey for token in solid_tokens):
            score += JOCKEY_MICRO_WEIGHTS.get("solid_bonus", 6.0)
            return score, f"{jockey} 屬有基本把握嘅一級半騎師，騎師分 {clip_score(score):.1f}。", "jockey_name_fallback"
        if "(a)" in jockey or "Fitzgerald" in jockey:
            score += JOCKEY_MICRO_WEIGHTS.get("apprentice_fresh_bonus", 2.0)
            return score, f"{jockey} 有減磅/新鮮手感因素，騎師分 {clip_score(score):.1f}。", "jockey_name_fallback"
        return score, f"{jockey or '騎師資料'} 屬中性配置，騎師分 {clip_score(score):.1f}。", "jockey_name_fallback"

    def _trainer_score(self):
        trainer = self._clean_identity(self.horse_data.get("trainer"))
        rating = self._trainer_rating_profile(trainer)
        score = rating["base_score"] if rating else 60
        notes = []
        if rating:
            tier_text = self._rating_tier_text(rating.get("tier"), "trainer")
            tier_note = f"馬房按 AU 練馬師資料庫列作 {tier_text}"
            if rating.get("confidence") == "provisional":
                tier_note += "（暫定補名）"
            notes.append(tier_note)
        else:
            strong_tokens = (
                "Waller", "Maher", "Waterhouse", "Bott", "Hayes", "Baker",
                "Freedman", "Price", "Payne", "Pride", "Snowden", "Charlton",
                "Hawkes", "O'Shea", "Conners", "Cummings", "Gollan", "Lees", "Neasham", "Moody"
            )
            if any(token in trainer for token in strong_tokens):
                score += TRAINER_MICRO_WEIGHTS.get("elite_bonus", 12.0)
                notes.append("馬房屬全國強勢班底")
        if "Waller" in trainer and self._career_starts() == 0:
            score += TRAINER_MICRO_WEIGHTS.get("waller_debut_bonus", 4.0)
            self.reason_codes.append("waller_debut_positive")
            notes.append("初出馬由 Waller 系統部署")
        track_stats = self._trainer_track_stats()
        if track_stats.get("runs", 0) >= 20 and track_stats.get("place_rate", 0.0) >= 0.44:
            score += TRAINER_MICRO_WEIGHTS.get("track_high_vol_high_place_bonus", 7.0)
            notes.append("馬房喺今場場館屬高密度高上名輸出")
        elif track_stats.get("runs", 0) >= 12 and track_stats.get("place_rate", 0.0) >= 0.40:
            score += TRAINER_MICRO_WEIGHTS.get("track_med_vol_high_place_bonus", 5.0)
            notes.append("馬房喺今場場館有穩定上名輸出")
        elif track_stats.get("runs", 0) >= 8 and track_stats.get("place_rate", 0.0) >= 0.32:
            score += TRAINER_MICRO_WEIGHTS.get("track_med_vol_med_place_bonus", 3.0)
            notes.append("馬房喺今場場館有基本對位")
        elif track_stats.get("runs", 0) >= 8 and track_stats.get("place_rate", 0.0) < 0.18:
            score += TRAINER_MICRO_WEIGHTS.get("track_low_place_pen", -2.0)
            notes.append("馬房近場館樣本未見明顯承托")
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

        if self._career_starts() == 0 and top_trainer:
            score += FIT_MICRO_WEIGHTS.get("debut_top_trainer_bonus", 8.0)
            notes.append("初出馬由強勢馬房部署")
        if self._career_starts() <= 5 and top_jockey and top_trainer:
            score += FIT_MICRO_WEIGHTS.get("young_top_jt_bonus", 6.0)
            notes.append("輕賽齡馬配頂級騎練")
        if trial_count >= 2 and trial_top3 >= 2:
            score += FIT_MICRO_WEIGHTS.get("trial_ok_bonus", 4.0)
            notes.append("試閘交代密度足夠")
            if top_jockey or top_trainer:
                score += FIT_MICRO_WEIGHTS.get("trial_ok_top_jt_bonus", 2.0)
                notes.append("備戰同騎練配置方向一致")
        if current_formal_rides > 0:
            score += min(FIT_MICRO_WEIGHTS.get("current_formal_cap", 6.0), current_formal_places * FIT_MICRO_WEIGHTS.get("current_formal_mult", 2.0) + current_formal_wins * FIT_MICRO_WEIGHTS.get("current_formal_mult", 2.0))
            notes.append(f"現役騎師曾策騎此駒 {current_formal_rides} 次正式賽")
            if current_formal_places * 2 >= max(1, current_formal_rides):
                score += FIT_MICRO_WEIGHTS.get("current_basic_fit_bonus", 2.0)
                notes.append("現役騎師對此駒有基本交代")
            if current_formal_rides >= 2 and current_place_rate >= 0.66:
                score += FIT_MICRO_WEIGHTS.get("current_high_fit_bonus", 2.0)
                notes.append("現役騎師對此駒配合率偏高")
        elif current_trial_rides > 0 and current_trial_top3 > 0:
            score += min(FIT_MICRO_WEIGHTS.get("current_trial_cap", 4.0), current_trial_top3 * FIT_MICRO_WEIGHTS.get("current_trial_mult", 2.0))
            notes.append("現役騎師已透過試閘熟習此駒")
        if best_formal_jockey and best_formal_rides > 0:
            if jockey == best_formal_jockey:
                score += min(FIT_MICRO_WEIGHTS.get("best_formal_cap", 6.0), best_formal_places * FIT_MICRO_WEIGHTS.get("best_formal_mult", 2.0) + best_formal_wins * FIT_MICRO_WEIGHTS.get("best_formal_mult", 2.0))
                notes.append("今場沿用歷來最佳正式賽配搭")
            elif current_formal_rides == 0 and best_formal_places > 0:
                if self._jockey_rank_value(jockey) >= self._jockey_rank_value(best_formal_jockey):
                    score += FIT_MICRO_WEIGHTS.get("jockey_upgrade_vs_best_bonus", 2.0)
                    notes.append("雖未沿用歷來最佳配搭，但換上同級或更強騎師")
                else:
                    score += FIT_MICRO_WEIGHTS.get("jockey_downgrade_vs_best_pen", -4.0)
                    notes.append("今場未沿用歷來較合拍騎師")
            elif current_vs_best:
                notes.append(current_vs_best)
        if latest_official_jockey and latest_official_jockey != jockey and latest_official_rides > 0:
            if current_formal_rides > 0 and current_place_rate > latest_official_place_rate + 0.20:
                score += FIT_MICRO_WEIGHTS.get("latest_upgrade_bonus", 4.0)
                notes.append("今場接手騎師對此駒往績勝過上仗騎師")
            elif current_formal_rides == 0 and latest_official_place_rate >= 0.50:
                score += FIT_MICRO_WEIGHTS.get("leave_proven_jockey_pen", -4.0)
                notes.append("今場離開上仗已證明配搭")
            elif current_formal_rides > 0 and latest_official_place_rate > current_place_rate + 0.20:
                score += FIT_MICRO_WEIGHTS.get("latest_downgrade_pen", -3.0)
                notes.append("今場騎師對此駒往績未及上仗騎師")
        if combo_stats.get("runs", 0) >= 5:
            if combo_stats.get("place_rate", 0.0) >= 0.45:
                score += FIT_MICRO_WEIGHTS.get("combo_high_vol_high_place_bonus", 6.0)
                notes.append("今場場館騎練組合已有穩定上名輸出")
            elif combo_stats.get("place_rate", 0.0) >= 0.33:
                score += FIT_MICRO_WEIGHTS.get("combo_med_place_bonus", 3.0)
                notes.append("今場場館騎練組合有基本對位")
            elif combo_stats.get("place_rate", 0.0) < 0.15:
                score += FIT_MICRO_WEIGHTS.get("combo_low_place_pen", -2.0)
                notes.append("今場場館騎練組合過往交代偏淡")
            if combo_stats.get("win_rate", 0.0) >= 0.18:
                score += FIT_MICRO_WEIGHTS.get("combo_win_bonus", 1.0)
                notes.append("同場騎練組合有直接贏馬紀錄")
            if current_formal_rides == 0 and combo_stats.get("place_rate", 0.0) >= 0.33:
                score += FIT_MICRO_WEIGHTS.get("combo_no_ride_good_place_bonus", 2.0)
                notes.append("雖未曾策此駒，但同場騎練拍檔成熟")
        elif trainer_track_stats.get("runs", 0) >= 10 and top_jockey and trainer_track_stats.get("place_rate", 0.0) >= 0.35:
            score += FIT_MICRO_WEIGHTS.get("trainer_track_top_jockey_bonus", 2.0)
            notes.append("馬房場館對位配上強手，部署可信度提高")
        if jockey_change_signal:
            if "沿用歷來最佳配搭" in jockey_change_signal:
                score += FIT_MICRO_WEIGHTS.get("signal_best_jockey_bonus", 4.0)
                notes.append("沿用歷來最佳人馬配搭")
            elif "較強騎師" in jockey_change_signal:
                score += FIT_MICRO_WEIGHTS.get("signal_upgrade_bonus", 5.0)
                notes.append("今場屬升級換騎")
            elif "換下較高級騎師" in jockey_change_signal:
                score += FIT_MICRO_WEIGHTS.get("signal_downgrade_pen", -4.0)
                notes.append("今場屬降級換騎")
            elif "沿用上仗騎師" in jockey_change_signal:
                score += 2
                notes.append("沿用上仗騎師，部署連貫")
            elif "試閘手接手" in jockey_change_signal:
                score += 2
                notes.append("試閘手接手，備戰線完整")
            elif "回配" in jockey_change_signal:
                score += 2
                notes.append("回配熟手騎師")
        if status_cycle in {"First-up", "久休復出"} and stage_stats["first_up"]["places"] > 0:
            score += 2
            notes.append("過往 fresh run 有基本交代")
        if status_cycle in {"Second-up", "二出"} and stage_stats["second_up"]["places"] > 0:
            score += 2
            notes.append("二出歷史有承接")
        if "(a)" in jockey and weight and weight >= 58:
            score += 4
            notes.append("減磅可幫手化解負磅壓力")
        if status_cycle in {"Third-up", "第三仗", "二出", "Second-up"} and top_jockey:
            score += 2
            notes.append("狀態週期配合好手接管")
        if trainer_track_stats.get("runs", 0) >= 20 and trainer_track_stats.get("win_rate", 0.0) >= 0.12 and combo_stats.get("runs", 0) == 0:
            score += 2
            notes.append("即使人馬未深配，馬房同場館專精度仍有承托")
        if trainer in {"", "Unknown"}:
            score -= 5
            notes.append("馬房資料不完整")
        note = "；".join(notes) if notes else "暫未見特別鮮明嘅人馬部署加成"
        return score, f"{note}，並結合 stage stats / jockey history / 試閘連貫性 / track combo 消化後，人馬配合評為 {clip_score(score):.1f} 分。", "jockey_trainer_fit+stage_stats+trial_continuity+formguide_jockey_history+track_combo_stats"

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
            "sectional": self._reason_bundle(
                "sectional",
                matrix_scores["sectional"],
                feature_scores,
                feature_notes,
                "sectional_score",
                "trial_score",
                "distance_score",
            ),
            "race_shape": self._reason_bundle(
                "race_shape",
                matrix_scores["race_shape"],
                feature_scores,
                feature_notes,
                "pace_map_score",
                "track_score",
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
            "sectional": self._describe_sectional_matrix,
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

    def _describe_stability_matrix(self, score, feature_scores):
        recent = str(self.data.get("recent_form") or self.horse_data.get("recent_form") or "").strip()
        status = self._status_cycle_display() or "狀態週期未明"
        trend = self._deduped_trend_summary() or "近況輪廓未算鮮明"
        latest_note = self._latest_official_note_brief()
        forgiveness = self._forgiveness_brief()
        repeatability = self._repeatability_brief()
        if self._career_starts() == 0:
            opener = "此駒正式賽樣本仍薄，呢一格主要靠備戰完整度、試閘交代同狀態週期去判 ready 程度。"
        elif recent:
            opener = f"近績 {recent} 配合 {status} 階段，走勢大致呈「{trend}」。"
        else:
            opener = f"正式近績樣本有限，穩定性主要依賴 {status} 週期定位及「{trend}」走勢判斷。"
            
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

    def _describe_sectional_matrix(self, score, feature_scores):
        engine = self._engine_distance_brief()
        breakdown = self._sectional_breakdown()
        trial_text = self._trial_summary_text()
        pf_text = self._latest_l600_rt_brief()
        latest_note = self._latest_official_note_brief()

        if feature_scores["sectional_score"] >= 72:
            opener = "末段爆發力有實質數據支持，段速水準明顯高於同場平均值。"
        elif feature_scores["distance_score"] <= 56:
            opener = "段速指標暫時未算硬淨，關鍵在於今次路程投射能否如期落地。"
        else:
            opener = "段速線具備一定素材，但仍需配合路程性能及試閘走勢作進一步確認。"

        middle_bits = []
        if engine:
            middle_bits.append(f"{engine}。")
        # 只講走勢方向，唔再喺判讀度重印成串 PI（PI 數列已在資料錨點出一次）。
        trends = self._sectional_trends()
        pi_trend = self._clean_trend_label(trends.get("pi_trend") or trends.get("l400_trend"))
        if pi_trend and pi_trend != "未明":
            middle_bits.append(f"近段 PI 走勢{pi_trend}。")
        if pf_text:
            middle_bits.append(f"近期 PF 指標為 {pf_text}。")
        if trial_text:
            middle_bits.append(f"試閘走勢：{trial_text}。")
        if latest_note:
            middle_bits.append(f"上仗備註：{latest_note}。")
            
        return " ".join(part for part in (opener, " ".join(bit for bit in middle_bits if bit)) if part)

    def _describe_race_shape_matrix(self, score, feature_scores):
        style_conf = self._style_confidence() or "未明"
        style = self._running_style() or self._tactical_position_text() or "跑法未明"
        barrier = self.horse_data.get("barrier")
        geometry_fit = self._track_fit_brief()
        shape_brief = self._recent_settled_pattern_brief()

        opener = f"排 {barrier} 檔配合預期「{style}」跑法"
        if shape_brief:
            opener += f"（近仗 settled pattern 顯示 {shape_brief}），"
        else:
            opener += "，"
            
        if feature_scores["pace_map_score"] >= 68:
            assessment = "預期走位劇本與檔位結構高度脗合，走位成本唔會太蝕，形勢屬主動一方。"
        elif feature_scores["pace_map_score"] <= 56:
            assessment = "形勢相對被動。要發揮最高水準，極度依賴出閘落位順利及直路及時望空，走位容錯率較低。"
        else:
            assessment = f"形勢未算惡劣，但亦未見明顯場面紅利；跑法信心屬 {style_conf}。"
            
        parts = [opener + assessment]
        if geometry_fit:
            parts.append(f"賽道幾何配套：{geometry_fit}。")
        # 戰術劇本只喺資料錨點出一次（已標明係模板），判讀唔再覆述。
        return " ".join(parts)

    def _describe_jockey_trainer_matrix(self, score, feature_scores):
        jockey = self._clean_identity(self.horse_data.get("jockey")) or "騎師資料未明"
        trainer = self._clean_identity(self.horse_data.get("trainer")) or "練馬師資料未明"
        trial_text = self._trial_summary_text()
        status = self._status_cycle_display() or "狀態週期未明"
        history = self._current_jockey_history_brief()
        best_history = self._best_jockey_history_brief()
        current_vs_best = self._current_vs_best_jockey_brief()
        change_signal = self._jockey_change_signal()
        latest_official = self._latest_official_jockey_brief()
        track_combo = self._track_combo_brief()
        trainer_track = self._trainer_track_brief()
        
        combo = f"由 {jockey} 配 {trainer}，目前處於 {status} 階段"
        if trial_text:
            combo += f"，備戰方面 {trial_text}。"
        else:
            combo += "。"
            
        if feature_scores["jockey_horse_fit_score"] >= 74:
            assessment = "今次唔單止係強勢騎練組合，連備戰方向同人馬熟習度都高度一致，出擊意圖明顯。"
        elif feature_scores["jockey_score"] <= 60 and feature_scores["trainer_score"] <= 60:
            assessment = "人馬配置未見特別主動訊號，屬中性觀望格局。"
        else:
            assessment = "人馬合作有一定底子，具備基本承托力，但仍未去到最強烈嘅搏殺配搭。"
            
        details = []
        if history:
            details.append(f"歷來配套：{history}。")
        if best_history and best_history != history:
            details.append(f"最佳配搭：{best_history}。")
        if current_vs_best:
            details.append(f"{current_vs_best}。")
        if change_signal:
            details.append(f"換騎訊號：「{change_signal}」。")
        if track_combo:
            details.append(f"同場樣本：{track_combo}。")
        if trainer_track:
            details.append(f"馬房場館履歷：{trainer_track}。")
            
        return " ".join(part for part in (combo, assessment, " ".join(details)) if part)

    def _describe_class_level_matrix(self, score, feature_scores):
        class_move = self._class_move_display()
        race_class = self._race_class_text()
        career = str(self.data.get("career_record_line") or "").strip()
        latest_formal = self._latest_record_summary("正式")
        latest_rt = self._latest_l600_rt_brief()
        followups = self._formline_followup_counts()
        headwinner = self._formline_headwinner()
        opener = "級數呢一格會專注睇班次門檻同對手層次，唔再撈埋負磅一齊判。"
        parts = [f"今場班次判讀為「{class_move}」"]
        if race_class:
            parts.append(f"賽事層級為 {race_class}")
        if latest_rt:
            parts.append(f"最近 RT 指標為 {latest_rt}")
        if career:
            parts.append(f"生涯背景為 {career}")
        if latest_formal:
            parts.append(f"最近正式賽果為 {latest_formal}")
        if followups["higher"] > 0:
            parts.append(f"近仗對手有 {followups['higher']} 匹後續升班仍能交代")
        if headwinner:
            parts.append(f"最近關鍵對手線由 {headwinner} 帶出")
        middle = "，".join(parts) + "。"
        if feature_scores["class_score"] >= 72:
            assessment = "代表今場班次門檻唔算高，對手層次亦有一定承接。"
        elif feature_scores["class_score"] <= 56:
            assessment = "級數線仍有一定壓力，對手層次未必完全企得穩。"
        else:
            assessment = "班次層次屬可接受範圍，但未見到明顯級數甜頭。"
        close = f"綜合之後，呢一格只會定性為{self._matrix_tone_phrase(score)}。"
        return " ".join(part for part in (opener, middle, assessment, close) if part)

    def _describe_weight_pressure_matrix(self, score, feature_scores):
        weight = parse_float(self.horse_data.get("weight"))
        field_weight = self._field_weight_brief()
        class_move = self._class_move_display()
        jockey = self._clean_identity(self.horse_data.get("jockey"))
        wet_state = self._wet_state()
        status_cycle = self._status_cycle_text()
        opener = "負磅壓力呢一格會獨立睇體重、場內磅差、濕地加權同騎師減磅因素。"
        parts = []
        if weight is not None:
            parts.append(f"今場負磅為 {weight:.1f}kg")
        if field_weight:
            parts.append(field_weight)
        if wet_state:
            parts.append(f"場地屬 {wet_state}，濕地加權已計入")
        if "(a)" in jockey:
            parts.append(f"騎師 {jockey} 有減磅優惠")
        if "升班" in class_move and weight is not None and weight >= 58.0:
            parts.append("升班兼高負磅，雙重門檻")
        if "降班" in class_move and weight is not None and weight <= 56.5:
            parts.append("降班配輕磅，外在門檻雙重下調")
        if status_cycle == "Deep Prep" and weight is not None and weight >= 58.0:
            parts.append("長期作戰期再加高負磅要防平台位")
        middle = "，".join(parts) + "。" if parts else "負磅與場內磅差資料有限。"
        if feature_scores["weight_score"] >= 68:
            assessment = "代表今場負磅壓力唔算大，發揮門檻相對較低。"
        elif feature_scores["weight_score"] <= 56:
            assessment = "負磅壓力偏高，發揮時要自己讓人，容錯空間收窄。"
        else:
            assessment = "負磅屬可接受範圍，但未見明顯讓磅甜頭。"
        close = f"綜合之後，呢一格只會定性為{self._matrix_tone_phrase(score)}。"
        return " ".join(part for part in (opener, middle, assessment, close) if part)

    def _describe_class_weight_matrix(self, score, feature_scores):
        class_move = self._class_move_display()
        horse_rating = self._horse_rating()
        rating_brief = self._field_rating_brief()
        weight = parse_float(self.horse_data.get("weight"))
        career = str(self.data.get("career_record_line") or "").strip()
        latest_formal = self._latest_record_summary("正式")
        race_class = self._race_class_text()
        latest_rt = self._latest_l600_rt_brief()
        field_weight = self._field_weight_brief()
        
        parts = [f"今仗出戰 {race_class}"]
        if weight is not None:
            parts.append(f"負 {weight:.1f}kg")
        if class_move and class_move != "平磅":
            parts.append(f"（{class_move}）")
        opener = " ".join(parts) + "。"
        if horse_rating is not None:
            opener += f" 官方 rating 為 {horse_rating:.1f}。"
            
        if (
            feature_scores["class_score"] >= 68
            and feature_scores["rating_score"] >= 66
            and feature_scores["weight_score"] >= 68
        ):
            assessment = "班次門檻、官方 rating 對位同負磅壓力都屬舒適範圍，外在條件整體順手。"
        elif (
            feature_scores["class_score"] <= 56
            or feature_scores["rating_score"] <= 56
            or feature_scores["weight_score"] <= 56
        ):
            assessment = "班次、rating 對位或負磅其中一邊門檻偏高，發揮空間受限，講求自身實力超水準兌現。"
        else:
            assessment = "班次、rating 對位同負磅條件大致合理，未見明顯阻力，但亦未去到全面甜頭。"
            
        details = []
        if rating_brief:
            details.append(f"{rating_brief}。")
        if field_weight:
            details.append(field_weight)
        if latest_rt:
            details.append(f"最近 PF 指標為 {latest_rt}。")
        if career:
            details.append(f"生涯背景：{career}。")
        if latest_formal:
            details.append(f"最近正式賽果：{latest_formal}。")
            
        return " ".join(part for part in (opener, assessment, " ".join(details)) if part)

    def _describe_track_matrix(self, score, feature_scores):
        going = self._today_going() or "掛牌未明"
        track_stats = self._same_track_stats()
        track_context = self._track_context()
        going_bucket = track_context.get("going_bucket", "")
        going_sample = self._going_stats().get(going_bucket, {})
        wet_state = self._wet_state()
        
        if feature_scores["track_score"] >= 72:
            opener = "同場及掛牌紀錄有堅實數據支持，場地性能絕對唔會成為絆腳石。"
        elif feature_scores["track_score"] <= 56:
            opener = "場地性能未算企穩，發揮可能打折扣，需保守看待。"
        else:
            opener = "場地適應力具備基礎支持，應可應付今日地狀。"
            
        details = []
        if track_stats["starts"] > 0:
            if track_stats["places"] > 0:
                details.append("同場已有上名或勝出紀錄。")
            elif track_stats["starts"] >= 2:
                details.append("同場已有多次經驗，但成績暫未見突破。")
            
        if going != "掛牌未明":
            if going_sample.get("starts", 0) > 0 and going_sample.get("places", 0) > 0:
                details.append(f"今場 {going} 掛牌屬射程範圍。")
            elif going_sample.get("starts", 0) >= 2:
                details.append(f"今場 {going} 掛牌暫未見突出成績。")

        if wet_state in {"soft7plus", "heavy"} and not self._has_verified_wet_place():
            details.append("缺乏爛地實績證明，場地風險偏高。")
            
        return " ".join(part for part in (opener, " ".join(details)) if part)

    def _describe_form_line_matrix(self, score, feature_scores):
        formline = self._formline_level() or "賽績線摘要未明"
        latest_formal = self._latest_record_summary("正式")
        headwinner = self._formline_headwinner()
        followup = self._formline_followup_brief()
        
        if feature_scores["formline_score"] >= 72:
            assessment = f"最近締造嘅賽績線屬「{formline}」級別，對手線有強勁承接，賽績含金量十足。"
        elif feature_scores["formline_score"] <= 56:
            assessment = f"賽績線級別評為「{formline}」，對手後續支持力弱，賽績水準暫只可保守看待。"
        else:
            assessment = f"現有賽績線屬「{formline}」級別，對手線有一定參考價值，但未算極度深厚。"
            
        details = []
        if headwinner:
            details.append(f"頭馬為 {headwinner}。")
        if latest_formal:
            details.append(f"最近正式賽果：{latest_formal}。")
        if followup:
            details.append(followup)
            
        return " ".join(part for part in (assessment, " ".join(details)) if part)

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
        if key == "sectional":
            # AU 無 numeric L400 PI，段速分多數觸底 35.8（一致偏弱）；已驗證段速對排名
            # 影響極低，所以呢度只作識別用，並去掉重覆 PI 列印（PI 走勢一條就夠）。
            return self._anchor_lines(
                ("累積段速總分", f"{self._sectional_breakdown()['score']:.1f} / 100"),
                ("計分明細", self._sectional_breakdown()['notes']),
                ("近段速度 L600（識別用·未入排名）", self._l600_speed_brief()),
                ("近段 PI 走勢", self._sectional_trend_brief()),
                ("試閘交代", self._trial_summary_text()),
                ("說明", "段速分多數觸底（AU 無 numeric L400 PI），故各馬得分相近；真正可分辨嘅係上面 L600 原始速度。已驗證段速對排名影響極低，此分只作識別跑法，唔反映勝算"),
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
                ("stage stats", str(self.data.get("stage_stats_line") or "").strip()),
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
                ("Meeting bias", self._meeting_bias_brief()),
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
            "sectional": "段速與引擎",
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

    def _verdict_shape(self, matrix_scores):
        if matrix_scores["sectional"] >= 74 and matrix_scores["jockey_trainer"] >= 72:
            return "有主動爭勝條件嘅實力型"
        if matrix_scores["stability"] >= 68 and matrix_scores["race_shape"] >= 66:
            return "有機會坐正位置嘅可爭位份子"
        if matrix_scores["form_line"] >= 68:
            return "有賽績底氣支撐嘅跟進對象"
        return "要靠形勢幫手先容易兌現嘅保留型"

    def _matrix_summary(self, key, score):
        label = self._matrix_label(key)
        if score >= 74:
            return f"{label} 係今場其中一條主要支柱"
        if score >= 68:
            return f"{label} 屬正面支撐範圍"
        if score <= 55:
            return f"{label} 仍然係主要保留位"
        return f"{label} 暫時只算中性參考"

    def _matrix_tone_phrase(self, score):
        if score >= 74:
            return "今場其中一條主要支柱"
        if score >= 68:
            return "正面支撐範圍"
        if score <= 55:
            return "主要保留位"
        return "中性參考"

    def _au_grade_computation_transparency(self, matrix_scores, matrix_bands, feature_scores, base_7d_score, ability_score, grade):
        """AU version: Generate computation walkthrough for the 7D matrix."""
        roles = {
            "stability": ("狀態與穩定性", "半核心"),
            "sectional": ("段速與引擎", "核心"),
            "race_shape": ("檔位形勢", "半核心"),
            "jockey_trainer": ("騎練訊號", "半核心"),
            "class_weight": ("級數與負重", "輔助"),
            "track": ("場地適性", "輔助"),
            "form_line": ("賽績線", "輔助"),
        }
        dims = [(key, *roles[key], float(MATRIX_WEIGHTS.get(key, 0.0))) for key in MATRIX_WEIGHTS]
        lines = []
        weighted_sum = 0.0
        for key, label, role, weight in dims:
            raw_score = float(matrix_scores.get(key, 60))
            band = matrix_bands.get(key, "➖")
            contribution = round(raw_score * weight, 2)
            weighted_sum += contribution
            pct = f"{weight * 100:.1f}%"
            # 拿走 [核心/半核心/輔助] 標籤：權重百分比已經表達咗重要性，標籤多餘。
            lines.append(f"  - {label}：{raw_score:.1f}分 × 權重 {pct} = {contribution:.2f} → {band}")
        lines_text = "\n".join(lines)
        summary = (
            f"**🧮 7D 加權總分計算 (Python Auto Clean 7D):**\n\n"
            f"{lines_text}\n\n"
            f"**→ 官方 7D clean ranking score = {base_7d_score:.2f} 分；綜合戰力分 = {ability_score:.2f} 分 → Grade = [{grade}]**\n"
        )
        if self.risk_flags:
            flag_descriptions = []
            for flag in sorted(set(self.risk_flags)):
                desc = self._au_risk_flag_description(flag)
                if desc:
                    flag_descriptions.append(f"  - {desc}")
            if flag_descriptions:
                summary += f"\n**⚠️ 風險標記:**\n" + "\n".join(flag_descriptions) + "\n"
        return {"detail_lines": lines, "weighted_sum": round(weighted_sum, 2), "summary": summary}

    def _au_core_logic_transparency(self, feature_scores, matrix_scores, matrix_bands, base_7d_score, ability_score, grade):
        """AU version: Generate structured transparency block."""
        dims = [
            ("stability", "狀態與穩定性", "半核心"),
            ("sectional", "段速與引擎", "核心"),
            ("race_shape", "檔位形勢", "半核心"),
            ("jockey_trainer", "騎練訊號", "半核心"),
            ("class_weight", "級數與負重", "輔助"),
            ("track", "場地適性", "輔助"),
            ("form_line", "賽績線", "輔助"),
        ]
        score_lines = []
        core_strong = 0
        semi_strong = 0
        aux_strong = 0
        total_weak = 0
        for key, label, role in dims:
            raw_score = float(matrix_scores.get(key, 60))
            band = matrix_bands.get(key, "➖")
            score_lines.append(f"  - {label} [{role}]: {raw_score:.1f}分 → {band}")
            if band in ("✅✅", "✅"):
                if role == "核心":
                    core_strong += 1
                elif role == "半核心":
                    semi_strong += 1
                else:
                    aux_strong += 1
            if band in ("❌❌", "❌"):
                total_weak += 1
        scores_text = "\n".join(score_lines)
        parts = [
            "**🧮 Python 矩陣計算全記錄:**",
            "",
            "**7D 維度評分:**",
            scores_text,
            "",
            f"**統計:** 核心正面={core_strong} | 半核心正面={semi_strong} | 輔助正面={aux_strong} | 總負面={total_weak}",
            f"**7D Clean 排名分:** {base_7d_score:.1f}分",
            f"**綜合戰力分:** {ability_score:.1f}分",
            f"**Grade 查表:** {ability_score:.1f}分 → **[{grade}]**",
        ]
        if self.risk_flags:
            flag_summary = []
            for flag in sorted(set(self.risk_flags)):
                phrase = self._au_risk_flag_description(flag)
                if phrase:
                    flag_summary.append(f"  - {phrase}")
            if flag_summary:
                parts.append(f"\n**⚠️ 已觸發風險標記:**")
                parts.extend(flag_summary)
        return "\n".join(parts)

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

    def _consumption_summary(self):
        text = str(self.data.get("consumption_summary") or "").strip()
        if text:
            return text
        match = re.search(r"- \*\*⚡ 走位消耗摘要:\*\*(.*?)(?=\n- \*\*|\n### |\Z)", self.facts_section, re.M | re.S)
        if not match:
            return ""
        lines = []
        for line in match.group(1).splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            if cleaned.startswith("- "):
                cleaned = cleaned[2:]
            lines.append(cleaned)
        return " ".join(lines)

    def _is_top_jockey(self, jockey: str) -> bool:
        return any(
            token in jockey
            for token in ("McDonald", "Rawiller", "Berry", "Clark", "Hyeronimus", "Schiller", "Lloyd", "King", "Collett")
        )

    def _is_top_trainer(self, trainer: str) -> bool:
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

    def _fact_anchor_value(self, label: str) -> str:
        match = re.search(rf"\n  - {re.escape(label)}: ([^\n]+)", "\n" + self.facts_section)
        return match.group(1).strip() if match else ""

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
        ):
            if token in text:
                positive.append(label)
        for token, label in (
            ("Worked early", "早段做多"),
            ("over-race", "沿途搶口"),
            ("slow recovery", "回氣偏慢"),
            ("weakened", "末段轉弱"),
            ("no abs", "賽後無明顯異常"),
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

    def _wet_kind(self):
        going = self._today_going()
        match = re.search(r"(Soft|Heavy)", going, re.I)
        return match.group(1).lower() if match else ""

    def _going_level(self):
        going = self._today_going()
        match = re.search(r"(?:Soft|Heavy)\s*([0-9]+)", going, re.I)
        return int(match.group(1)) if match else 0

    def _wet_rail_degradation_active(self):
        race_number = int(parse_float(self.race_context.get("race_number")) or 0)
        wet_kind = self._wet_kind()
        going_level = self._going_level()
        if wet_kind == "heavy":
            return race_number >= 5
        return wet_kind == "soft" and going_level >= 6 and race_number >= 5

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

    def _run_style_bucket(self, text):
        value = str(text or "")
        if any(token in value for token in ("前置", "跟前", "居中前", "前領", "領放")):
            return "front"
        if any(token in value for token in ("後上", "中後", "後追")):
            return "back"
        if any(token in value for token in ("守中", "中段", "居中")):
            return "mid"
        return ""

    def _recent_shape_evidence(self):
        entries = self._official_entries()[:4]
        current_bucket = self._run_style_bucket(self._running_style() or self._tactical_position_text())
        styles = set()
        alignment = 0
        traffic_runs = 0
        wide_cost_runs = 0
        slow_start_runs = 0
        for entry in entries:
            bucket = self._run_style_bucket(entry.get("run_style") or entry.get("trajectory") or "")
            if bucket:
                styles.add(bucket)
            if current_bucket and bucket == current_bucket:
                alignment += 1
            flags = self._entry_note_flags(entry)
            positives = set(flags["positive"])
            negatives = set(flags["negative"])
            if positives & {"直路受阻", "受擠迫", "被迫收慢", "移出避腳"}:
                traffic_runs += 1
            if "直路外疊" in positives or "早段做多" in negatives:
                wide_cost_runs += 1
            if positives & {"出閘笨拙", "起步蝕位", "起步讓步"}:
                slow_start_runs += 1
        return {
            "alignment": alignment,
            "versatility": len(styles),
            "traffic_runs": traffic_runs,
            "wide_cost_runs": wide_cost_runs,
            "slow_start_runs": slow_start_runs,
        }

    def _recent_shape_evidence_brief(self):
        evidence = self._recent_shape_evidence()
        parts = []
        if evidence["alignment"]:
            parts.append(f"近仗對位 {evidence['alignment']} 次")
        if evidence["versatility"]:
            parts.append(f"走位 {evidence['versatility']} 類")
        if evidence["traffic_runs"]:
            parts.append(f"受阻 {evidence['traffic_runs']} 次")
        if evidence["wide_cost_runs"]:
            parts.append(f"白走/做多 {evidence['wide_cost_runs']} 次")
        if evidence["slow_start_runs"]:
            parts.append(f"起步失位 {evidence['slow_start_runs']} 次")
        return "；".join(parts)

    def _track_family_support(self):
        if self._track_family_cache is not None:
            return self._track_family_cache
        current = self._track_profile()
        current_venue = self._clean_identity(current.get("venue")).lower()
        current_direction = str(current.get("direction") or "").strip()
        current_straight = int(parse_float(current.get("straight_m")) or 0)
        current_tight = any(token in " ".join(current.get("key_traits") or []) for token in ("急彎", "Tight-turning"))
        stats = {
            "confidence": "Low",
            "same_venue_starts": 0,
            "same_venue_places": 0,
            "same_geometry_starts": 0,
            "same_geometry_places": 0,
            "same_direction_places": 0,
            "same_state_places": 0,
            "same_going_places": 0,
            "first_tight_turn": False,
            "interstate_shift": False,
        }
        if not current_venue:
            self._track_family_cache = stats
            return stats
        current_state = self._venue_state(current_venue)
        current_going = self._track_context().get("going_bucket", "")
        for entry in self._official_entries()[:6]:
            venue = self._clean_identity(entry.get("venue")).lower()
            if not venue:
                continue
            profile = _load_track_profile(venue)
            if not profile:
                continue
            placing = parse_float(entry.get("placing"))
            placed = placing is not None and placing <= 3
            entry_state = self._venue_state(venue)
            entry_direction = str(profile.get("direction") or "").strip()
            entry_straight = int(parse_float(profile.get("straight_m")) or 0)
            entry_tight = any(token in " ".join(profile.get("key_traits") or []) for token in ("急彎", "Tight-turning"))
            same_venue = venue == current_venue
            same_geometry = (
                entry_direction == current_direction
                and abs(entry_straight - current_straight) <= 45
                and entry_tight == current_tight
            )
            if same_venue:
                stats["same_venue_starts"] += 1
                if placed:
                    stats["same_venue_places"] += 1
            elif same_geometry:
                stats["same_geometry_starts"] += 1
                if placed:
                    stats["same_geometry_places"] += 1
            elif current_direction and entry_direction == current_direction and placed:
                stats["same_direction_places"] += 1
            if current_state and entry_state and current_state == entry_state and placed:
                stats["same_state_places"] += 1
            if current_going and placed:
                entry_going = str(entry.get("going") or "")
                if current_going == "好地" and any(token in entry_going for token in ("Good", "Firm", "好")):
                    stats["same_going_places"] += 1
                elif current_going == "軟地" and any(token in entry_going for token in ("Soft", "軟")):
                    stats["same_going_places"] += 1
                elif current_going == "重地" and any(token in entry_going for token in ("Heavy", "重")):
                    stats["same_going_places"] += 1
        stats["first_tight_turn"] = current_tight and stats["same_venue_starts"] == 0 and stats["same_geometry_starts"] == 0
        latest_venue = self._clean_identity((self._official_entries()[0] or {}).get("venue")).lower() if self._official_entries() else ""
        latest_state = self._venue_state(latest_venue)
        stats["interstate_shift"] = bool(current_state and latest_state and current_state != latest_state)
        if stats["same_venue_starts"] >= 2 and stats["same_venue_places"] > 0:
            stats["confidence"] = "High"
        elif (
            stats["same_venue_places"] > 0
            or stats["same_geometry_places"] > 0
            or stats["same_direction_places"] >= 2
            or (stats["same_state_places"] >= 2 and stats["same_going_places"] >= 1)
        ):
            stats["confidence"] = "Medium"
        self._track_family_cache = stats
        return stats

    def _track_family_confidence_brief(self):
        family = self._track_family_support()
        parts = [f"Track family {family['confidence']}"]
        if family["same_venue_starts"]:
            parts.append(f"同場 {family['same_venue_starts']} 場")
        if family["same_venue_places"]:
            parts.append(f"同場上名 {family['same_venue_places']} 次")
        if family["same_geometry_places"]:
            parts.append(f"同幾何上名 {family['same_geometry_places']} 次")
        elif family["same_direction_places"]:
            parts.append(f"同方向上名 {family['same_direction_places']} 次")
        elif family["same_state_places"]:
            parts.append(f"同州上名 {family['same_state_places']} 次")
        if family["same_going_places"]:
            parts.append(f"同地狀上名 {family['same_going_places']} 次")
        if family["first_tight_turn"]:
            parts.append("首次急彎考驗")
        if family["interstate_shift"]:
            parts.append("跨州轉場")
        return "；".join(parts)

    def _has_verified_wet_place(self):
        stats = self._going_stats()
        return any(stats[label]["places"] > 0 for label in ("軟地", "重地"))

    def _has_verified_wet_win(self):
        stats = self._going_stats()
        return any(stats[label]["wins"] > 0 for label in ("軟地", "重地"))

    def _pace_confidence(self):
        return str(self._speed_map_field("pace_confidence") or "").strip()

    def _style_confidence(self):
        return str(self.data.get("style_confidence_line") or self._speed_map_field("style_confidence") or "").strip()

    def _style_evidence_for_horse(self):
        evidence = str(self._speed_map_field("style_evidence") or "").strip()
        if not evidence:
            return ""
        horse_num = str(self.horse_data.get("horse_number") or self.horse_data.get("number") or "")
        if not horse_num:
            match = re.search(r"^### 馬匹 #(\d+)", self.facts_section, re.M)
            horse_num = match.group(1) if match else ""
        match = re.search(rf"#{re.escape(horse_num)}\s+([^;]+)", evidence)
        return match.group(1).strip() if match else ""

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

    def _pos400_progression_signal(self, pattern: str) -> str:
        """Analyse 400m position pattern for mid-race trending direction."""
        if not pattern:
            return ""
        positions = [-1]
        for part in pattern.split("→"):
            try:
                positions.append(int(part.strip()))
            except ValueError:
                continue
        if len(positions) < 3:
            return ""
        # Look at last 3 positions
        recent = positions[-3:]
        if len(recent) < 2:
            return ""
        if recent[-1] < recent[-2] and recent[-1] <= 4:
            return "improving"
        if recent[-1] > recent[-2] and recent[-1] >= 10:
            return "worsening"
        return "stable"

    def _forgiveness_count(self):
        count = 0
        for entry in self._official_entries()[:4]:
            note = entry.get("notes", "")
            if any(token in note for token in ("Too much start", "Worked early", "Crowded", "Bumped", "Steadied", "Looking for run")):
                count += 1
        return count

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

    def _consumption_brief(self):
        text = str(self.data.get("consumption_summary") or self._consumption_summary() or "").strip()
        if not text:
            return "走位消耗資料有限"
        clean = text.replace("\n", " ").replace("- ", "").replace("  ", " ").strip()
        clean = re.sub(r"\s*近\s*", " 近 ", clean, count=1)
        clean = clean.replace("加權累積消耗", "；加權累積消耗")
        clean = re.sub(r"\s*→\s*等級", "；等級", clean)
        return clean.strip("； ")

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

    def _venue_state(self, venue: str):
        text = self._clean_identity(venue).lower()
        for token, state in VENUE_STATE_MAP.items():
            if token in text:
                return state
        return ""

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
            parts.append(f"引擎輪廓 {engine_match.group(1).strip()}")
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
            parts.append(f"當中 {counts['higher']} 匹對手其後升班仍能再贏，反映賽績線含金量較高")
        if counts["same"] > 0:
            parts.append(f"{counts['same']} 匹對手其後同班再贏，反映賽績線有後續支持")
        if counts["lower"] > 0:
            parts.append(f"{counts['lower']} 匹對手其後降班再贏，支持力度較有限")
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

    def _consumption_weighted_score(self):
        text = str(self.data.get("consumption_summary") or self._consumption_summary() or "")
        match = re.search(r"加權累積消耗:\s*([0-9.]+)", text)
        return float(match.group(1)) if match else None

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
            score += w.get("class_up_pen", -4.0)
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

        note_text = "；".join(notes) if notes else "班次資料未見鮮明傾向"
        return clip_score(score), f"{note_text}，級數分 {clip_score(score):.1f}。", "class_move+record_table+formline_followups"

    def _rating_score(self):
        rating = self._horse_rating()
        field = self._field_summary()
        rated_count = int(field.get("rated_count") or 0)
        if rating is None or rated_count < 2:
            return 60, "官方 rating 或同場 rating 樣本不足，Rating 分中性處理。", "missing_neutral"

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
        return score, f"{'；'.join(notes)}，Rating 分 {score:.1f}。", "racecard_rating+field_relative"

    def _is_wfa_or_sw_race(self):
        text = self._race_class_text().lower()
        return "weight for age" in text or "wfa" in text or "set weights" in text or "sw" in text

    def _weight_score(self):
        weight = parse_float(self.horse_data.get("weight"))
        if weight is None:
            return 60, "負磅資料不足，負磅分中性處理。", "missing_neutral"
        
        score = 62
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

        return clip_score(score), f"{'；'.join(notes) if notes else '場地資料未見鮮明優劣'}。場地分 {clip_score(score):.1f}。", "track_stats+going_stats+wet_track"

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
            notes.append(f"{followups['higher']} 匹對手其後升班仍能再贏（含金量高）")
        if followups["same"] >= 2:
            notes.append(f"{followups['same']} 匹對手其後同班再贏")
        if followups["lower"] >= 3 and followups["higher"] == 0:
            notes.append("對手多數要降班先再贏，含金量有限")
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
        if starts == 0:
            return w.get("career0_base", 58.0), "初出馬以備戰完整度代替穩定樣本，跑法穩定性 58 分。", "career_tag"
            
        score = w.get("base", 58.0)
        notes = []
        
        recent = parse_recent_finishes(self.data.get("recent_form"))
        if recent:
            places = sum(1 for x in recent[:6] if x <= 3)
            poor = sum(1 for x in recent[:6] if x >= 8)
            score += (places * w.get("recent_place_bonus", 7.0)) + (poor * w.get("recent_poor_pen", -5.0))
            notes.append(f"近仗有{places}次前三、{poor}次大敗")
            
            if poor >= 2 and self._forgiveness_count() >= 2:
                score += w.get("forgiveness_bonus", 4.0)
                notes.append("大敗場次多具寬恕理由")
        
        run_styles = [entry.get("run_style", "") for entry in self._official_entries()[:4] if entry.get("run_style") and entry.get("run_style") != "-"]
        if run_styles and len(set(run_styles)) == 1:
            score += w.get("run_style_bonus", 3.0)
            notes.append("近期跑法連貫")
            
        if "穩定" in self._sectional_trends().get("pi_trend", ""):
            score += w.get("pi_stable_bonus", 2.0)
            
        repeatability = self._repeatability_brief()
        if "重覆前列交代" in repeatability or "直接對位" in repeatability:
            score += w.get("repeat_bonus", 2.0)
            notes.append("派彩/對位具重複性")
        elif "未形成穩定交代" in repeatability:
            score += w.get("no_repeat_pen", -1.0)
            
        note_str = "；".join(notes) if notes else "未見特別跑法或表現穩定特徵"
        return score, f"{note_str}。跑法穩定性 {clip_score(score):.1f} 分。", "run_style+sectional_trend+forgiveness+repeatability"

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

    def _jt_sample_size_rank_cap(self, matrix_scores):
        penalty = jt_sample_size_rank_cap(
            matrix_scores,
            self._current_jockey_formal_rides(),
            self._current_jockey_trial_rides(),
            self._best_formal_jockey_rides(),
            self._latest_official_jockey_formal_rides(),
            int(self._current_track_combo_stats().get("runs", 0)),
            int(self._trainer_track_stats().get("runs", 0)),
        )
        if penalty < 0:
            self.reason_codes.append("jt_sample_size_capped")
        return penalty

    def _narrow_overrated_rank_shield(self, matrix_scores):
        penalty = narrow_overrated_rank_shield(
            matrix_scores,
            self._wet_state(),
            int(self._field_summary().get("count", 0)),
        )
        if penalty < 0:
            self.reason_codes.append("narrow_overrated_shield")
        return penalty

    def _advantages(self, feature_scores, matrix_scores):
        items = []
        if matrix_scores["sectional"] >= 72:
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
        if matrix_scores.get("class_level", matrix_scores.get("weight_pressure", 60)) >= 68:
            items.append("班次未見吃力，發揮門檻唔高")
        elif matrix_scores.get("weight_pressure", matrix_scores.get("class_level", 60)) >= 68:
            items.append("負磅壓力唔算重，可更自如發揮")
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
        if matrix_scores.get("class_level", 60) <= 55 or matrix_scores.get("weight_pressure", 60) <= 55:
            items.append("班次或負磅面前仍有壓力，容錯空間唔大")
        if matrix_scores["track"] <= 55:
            items.append("場地適性仍未有清楚支持，轉場條件未必幫到手")
        if matrix_scores["form_line"] <= 55:
            items.append("賽績線含金量一般，對手後續未能幫手抬高可信度")
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
                cls_bits.append(f"{counts['higher']}匹其後升班再贏")
            if counts["same"]:
                cls_bits.append(f"{counts['same']}匹同班再贏")
            if counts["lower"]:
                cls_bits.append(f"{counts['lower']}匹降班再贏")
            head = f"曾交手頭馬「{opp}」" if opp else "近仗對手線"
            add("賽績線", f"曾勝對手「{opp}」" if opp else "近仗對手",
                "對手已驗證" if validated else "對手未驗證",
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

    def _core_opening(self, horse_name, matrix_scores):
        strong_key = max(matrix_scores, key=matrix_scores.get)
        strong_score = matrix_scores[strong_key]
        verdict = self._verdict_shape(matrix_scores)
        if strong_key == "sectional" and strong_score >= 74:
            return f"{horse_name} 今場最吸引唔係單睇名次，而係段速同引擎輪廓確實有料，整體屬於 {verdict}。"
        if strong_key == "jockey_trainer" and strong_score >= 72:
            return f"{horse_name} 今場個賣點唔止在人腳名氣，而係部署、備戰同落位劇本幾方面夾得埋，整體屬於 {verdict}。"
        if strong_key == "stability":
            return f"{horse_name} 今場評價建基於近況輪廓未散，唔係靠一次偶然爆冷撐起，整體屬於 {verdict}。"
        return f"{horse_name} 今場整體評價以 {self._matrix_label(strong_key)} 做主軸，現階段屬於 {verdict}。"

    def _core_status_line(self):
        recent = str(self.data.get("recent_form") or self.horse_data.get("recent_form") or "").strip()
        status = self._status_cycle_display() or "狀態週期未明"
        trend = self._deduped_trend_summary() or "走勢未算特別鮮明"
        if self._career_starts() == 0:
            trial_text = self._trial_summary_text()
            if trial_text:
                return f"佢而家仍然屬於正式賽空白樣本，但備戰面已有 {trial_text}，現時大致按 {status} 狀態去理解。"
            return f"佢而家仍然屬於正式賽空白樣本，現時主要按 {status} 去理解 ready 程度。"
        if recent:
            return f"近績序列 {recent} 配合 {status} 週期，走勢大致反映為「{trend}」。"
        return f"正式近績樣本未算厚，但現時週期屬 {status}，走勢大致可概括為「{trend}」。"

    def _core_sectional_line(self, feature_scores):
        l400 = self._l400_text()
        engine = self._engine_distance_brief()
        trend = self._sectional_trend_brief()
        pieces = []
        if engine:
            pieces.append(engine)
        if l400:
            pieces.append(f"L400 參考值係 {l400}")
        if trend:
            pieces.append(trend)
        if not pieces:
            return ""
        close = "呢條線基本證明到佢今次唔只係有名次，而係有對應輸出。" if feature_scores["sectional_score"] >= 72 else "呢條線未去到鐵證如山，但至少唔係完全空心。"
        return "段速同路程方面，" + "；".join(pieces) + f"；{close}"

    def _core_tactical_line(self):
        barrier = self.horse_data.get("barrier")
        position = self._tactical_position_text()
        scenario = self._tactical_scenario_text()
        track_fit = self._track_fit_brief()
        pieces = []
        if barrier not in (None, "", "-"):
            pieces.append(f"今次排 {barrier} 檔")
        if position:
            pieces.append(f"預計以「{position}」方式應戰")
        if track_fit:
            pieces.append(track_fit)
        if not pieces and not scenario:
            return ""
        text = "檔位同走位劇本方面，" + "，".join(pieces)
        if scenario:
            text += f"，{scenario}"
        return text + "。"

    def _core_formline_line(self):
        followup = self._formline_followup_brief()
        headwinner = self._formline_headwinner()
        formline = self._formline_level()
        pieces = []
        if formline:
            pieces.append(f"賽績線現時屬「{formline}」")
        if headwinner:
            pieces.append(f"最近關鍵對手線由 {headwinner} 帶出")
        if followup:
            pieces.append(f"對手後續大致係 {followup}")
        if not pieces:
            return ""
        return "對手線方面，" + "；".join(pieces) + "。"

    def _core_forgiveness_line(self):
        count = self._forgiveness_count()
        if count <= 0:
            return ""
        latest = self._latest_record_summary("正式")
        if latest:
            return f"另外近四仗有 {count} 次帶住受阻或蝕位背景，紙面名次未必完全反映真身，尤其最近正式一仗 {latest}。"
        return f"另外近四仗有 {count} 次帶住受阻或蝕位背景，紙面名次未必完全反映真身。"

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

    def _core_condition_branch(self, disadvantages):
        first_risk = disadvantages[0] if disadvantages else "臨場仍要靠節奏同落位幫手"
        wet_state = self._wet_state()
        if wet_state and not self._has_verified_wet_place():
            return f"若場地再向濕慢一邊走，而佢又交唔到已驗證濕地版本，{first_risk} 呢條風險就會即時放大。"
        if "pace_burn_risk" in self.risk_flags:
            return f"若早段搶位比預期更激，咁末段互燒就會成為最大變數，{first_risk}。"
        if any(token in self._tactical_scenario_text() for token in ("望空", "移出")):
            return f"若轉彎後未能及時望空或順利移出，咁末段就算有腳都未必可以一次過交晒，{first_risk}。"
        return f"只要臨場可以將自己最舒服嗰套部署跑返出嚟，佢就有機會兌現而家呢份評價；但若節奏同落位唔配合，{first_risk}。"

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
        if any(t in video for t in ['weakened','drifted','tired','faded','gave ground','beaten','wd badly','wd latter','battled']):
            signals["weakened"] += 1
        if any(t in video for t in ['led','leader','found lead','narrow lead','tracked leader','sett fence']):
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
_BARRIER_ADJ = {
    "flemington": {
        1: 1.0, 2: 0.5, 3: 0.0, 4: 2.5, 5: 2.0,
        6: 3.0, 7: 1.5, 8: -1.5, 9: -0.5, 10: 1.0,
        11: -0.5, 12: 0.0, 13: 0.5, 14: -0.5, 15: 0.0,
        16: 0.0, 17: -2.0,
    },
    "randwick": {
        1: 1.5, 2: 1.5, 3: 3.0, 4: 3.0, 5: 1.5,
        6: 0.0, 7: -0.5, 8: 1.0, 9: -0.5, 10: -2.5,
        11: -1.0, 12: -3.0, 13: -2.5, 14: -3.5, 15: -3.5,
        16: -3.5, 17: -1.5, 18: -3.5,
    },
}


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
                "horse_rating": float(meta_match.group(2)),
                "declared_weight": float(meta_match.group(1)),
            }
        index += 2
    return profiles
