from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

from .preparation_cycle import preparation_cycle
from .full_time_speed import contribution as full_time_contribution
from . import pit as _pit
from . import speed as _speed
from . import class_rating as _class
from . import draw as _draw
from . import stability as _stab
from . import overseas as _overseas
from . import track_going as _track
from . import jockey_trainer as _jt
from .dimensions import DIMENSION_SPECS, RATING_SCORE_SHARE

from .matrix_mapper import (
    MATRIX_ADVANTAGE_CUTOFF,
    MATRIX_DISADVANTAGE_CUTOFF,
    MATRIX_FORMULAS,
    canonical_matrix_key,
    map_features_to_matrix,
    map_features_to_matrix_scores,
)
from .source_alignment import (
    HORSE_HEADER_RE,
    RACECARD_HORSE_RE,
    RACECARD_META_RE,
    clean_identity as _clean_identity,
    normalize_going,
    normalize_horse_name as _normalize_horse_name,
    race_source_candidates,
    validate_facts_horse_alignment,
    venue_from_meeting_name,
)
from .scoring import (
    ABILITY_FEATURE_KEYS,
    CLASS_SCORE_LIVE,
    CLASS_SCORE_LIVE_WEIGHT,
    FEATURE_KEYS,
    compose_matrix_score,
    MATRIX_WEIGHTS,
    CLASS_MICRO_WEIGHTS,
    CONSISTENCY_MICRO_WEIGHTS,
    SECTIONAL_MICRO_WEIGHTS,
    TRIAL_MICRO_WEIGHTS,
    PROVEN_CLASS_DECAY,
    PROVEN_CLASS_Z_WEIGHT,
    SPORTSBET_PQ_RECOVERY_ALPHA,
    clip_score,
    compute_grade,
    parse_float,
    parse_placing,
    parse_numbers,
    parse_record_line,
    parse_recent_finishes,
    safe_ratio,
)

from .data_prep import (  # noqa: F401  數據準備（EXP-20261103-14）；舊名照 re-export
    CLASSIFICATION_PARENT,
    CLASS_PRIZE_DECAY,
    CLASS_PRIZE_K,
    HORSE_BLOCK_RE,
    L600_RECENCY_DECAY,
    PF_BACKFILL_FILENAMES,
    PRIZE_COLUMN,
    PROVINCIAL_TRACK_FILE,
    SYNTHETIC_ONLY_VENUES,
    TRACK_GEOMETRY_ALIASES,
    TRACK_GEOMETRY_CACHE,
    TRACK_GEOMETRY_PATH,
    TRACK_PROFILE_CACHE,
    TRACK_RESOURCE_DIR,
    VENUE_TRACK_MAP,
    _FG_HORSE_HDR_RE,
    _FG_JT_LY_RE,
    _FORMGUIDE_HORSE_HEADER,
    _PERFORMANCE_QUALITY_CLASS_CREDIT,
    _PERFORMANCE_QUALITY_RECENCY_WEIGHTS,
    _PERFORMANCE_QUALITY_REFERENCE_PRIZE,
    _PF_BACKFILL_CACHE,
    _PF_SPLIT_KEYS,
    _PF_TOKEN_RE,
    _PRIZE_MIN_COLUMNS,
    _RUN_FINISH_RE,
    _RUN_POSITION_RE,
    _RUN_RACE_L600_RE,
    _RUN_VENUE_RE,
    _RUN_WINNING_TIME_RE,
    _SEC_PER_LENGTH,
    _TRAJ_FINISH_RE,
    _TRAJ_MARK_RE,
    _TRAJ_SETTLED_RE,
    _WINNING_TIME_TOKEN,
    _best_jockey_name_and_bucket,
    _build_tactical_plan,
    _build_timing_summary,
    _capture,
    _capture_multiline,
    _compact_text,
    _context_completeness,
    _count_formal_rows,
    _count_trial_rows,
    _count_trial_top3,
    _current_jockey_history_line,
    _derive_jockey_change_signal,
    _distance_to_int,
    _entry_shape_bucket,
    _expected_position_label,
    _extract_career_starts,
    _extract_career_tag,
    _extract_distance_profile_line,
    _extract_engine_confidence,
    _extract_engine_type_line,
    _extract_first_int,
    _extract_latest_class_move,
    _extract_race_meta,
    _extract_race_number,
    _extract_race_number_from_text_or_name,
    _extract_running_style_confidence,
    _extract_running_style_line,
    _extract_target_distance_line,
    _extract_track_traits,
    _fill_prize_column,
    _first_clean,
    _first_line_matching,
    _form_quality_digest,
    _formguide_path_for_facts,
    _formguide_run_context,
    _formguide_text,
    _geometry_fields,
    _jockey_bucket_sort_key,
    _jockey_compare_line,
    _jockey_history_line,
    _jockey_summary_line,
    _load_formguide_digests,
    _load_meeting_intelligence,
    _load_pf_backfill,
    _load_racecard_profiles,
    _load_track_geometry,
    _load_track_profile,
    _market_trend_label,
    _meeting_context_from_extractor_files,
    _meeting_dir,
    _merge_data_value,
    _merge_pf_sources,
    _merge_prefer_clean,
    _merge_sources,
    _mip_field,
    _mip_plain_text,
    _mip_section_value,
    _normalize_speed_map_text,
    _parse_field_size,
    _parse_fluc_values,
    _parse_formguide_entries,
    _parse_formguide_jt_ly,
    _parse_formguide_pf_metrics,
    _parse_horse_sections,
    _parse_iso_date,
    _parse_meeting_intelligence,
    _parse_num_list,
    _parse_num_map,
    _parse_pf_token,
    _parse_prize,
    _parse_running_position,
    _parse_speed_map,
    _parse_time_to_seconds,
    _parse_trial_video_signals,
    _parse_winning_time,
    _performance_quality_digest,
    _pf_aggregates,
    _pf_backfill_for_race,
    _pf_num,
    _pf_str,
    _prize_map_from_formguide,
    _record_rows,
    _replace_data_value,
    _section_text,
    _slug,
    _summarize_formguide_section,
    _summarize_recent_shape,
    _surface_kind,
    _tactical_scenario_text,
    _track_classification,
    _track_distance_note,
    _track_geometry_key,
    _track_table_int,
    _track_table_text,
    _track_venue_section,
    _validate_formguide_horse_alignment,
    _venue_from_folder_name,
    backfill_pf_metrics,
    backfill_prize_column,
    build_logic_from_facts,
    enrich_logic_from_facts,
    exact_race_class_level,
    horse_prize_level,
    horse_proven_class_level,
    normalise_field_barriers,
    normalise_synthetic_going,
    parse_trajectory,
    pi_from_trajectory,
    refresh_form_quality,
    refresh_pf_own_l600,
    refresh_trial_runs,
    today_class_move,
)
AUTO_RESOURCE_DIR = Path(__file__).resolve().parents[2] / "resources"

# User-accepted simplification, EXP-20261015-01: this is not a measured gain.
TRIAL_PERFORMANCE_START_CUTOFF = 6
# EXP-20261016-01 (user decision 2026-10-16): `trial_score` left the ranking
# entirely (dimensions.py); this cutoff still gates trial PF rows and the maiden
# trial-time proxy, which stay for horses under 6 starts.


def _bm_tier(rating):
    if rating >= 88: return 4
    if rating >= 72: return 5
    if rating >= 64: return 6
    return 7


# EXP-20261016-13 A/B 開關：False = 舊行為（讀唔存在嘅 `entry["class"]`）。
FORM_ENTRY_CLASS_TIER = True


def race_class_tier(text):
    """Race class label → (tier, recognised). Lower tier = higher class; 7 when unknown.

    EXP-20261016-05 (correctness fix): the old substring tests read sponsor words as
    class ("lr", "g1", "open" inside names) and missed the spelled-out labels the
    titles actually use ("BENCHMARK 78", "MDN", rating bands "0 - 56", "CL3").
    Tokens now need word boundaries; a label that says nothing about class
    ("HANDICAP", "SW") stays the unknown default 7.
    """
    t = str(text or "").lower()
    if re.search(r"\b(?:group\s*1|g1)\b", t): return 1, True
    if re.search(r"\b(?:group\s*[23]|g[23])\b", t): return 2, True
    if re.search(r"\b(?:listed|lr|open)\b", t): return 3, True
    m = re.search(r"\b(?:bm|benchmark)\s*(\d{2,3})\b", t)
    if m: return _bm_tier(int(m.group(1))), True
    m = re.search(r"\b0\s*-\s*(\d{2,3})\b", t)              # rating band "0 - 56" ≈ BM56
    if m: return _bm_tier(int(m.group(1))), True
    m = re.search(r"\b(?:rtg|rating)\s*(\d{2,3})\s*\+?", t)  # "RTG 66+" — floor of the band
    if m: return _bm_tier(int(m.group(1))), True
    m = re.search(r"\b(\d{2,3})\s*\+", t)                # "GRAD HCP 60+" — floor of the band
    if m: return _bm_tier(int(m.group(1))), True
    m = re.search(r"\b(?:class|cl|c)\s*([1-6])\b", t)      # "Class 3", "CL3", "HIGHWAY-C3"
    if m:
        n = int(m.group(1))
        return (5 if n >= 5 else 6 if n >= 3 else 7), True
    if re.search(r"\b(?:maiden|mdn)\b", t): return 8, True
    return 7, False


def trial_performance_applies(horse):
    """Unknown career totals retain trial evidence; only known starts gate it."""
    starts = parse_float(horse.get("career_race_starts"))
    return not (starts is not None and math.isfinite(starts)
                and starts >= TRIAL_PERFORMANCE_START_CUTOFF)


def trial_speed_raw(horse):
    """EXP-20261016-77：試閘 PF 行嘅個體 L600 平均（越細越快）；唔適用或者冇試閘 PF → None。"""
    if not trial_performance_applies(horse):
        return None
    metrics = ((horse.get("_data") or {}).get("pf_metrics") or {})
    source = (metrics.get("pf_aggregates") or {}).get("source", "")
    values = []
    for run in metrics.get("pf_runs") or []:
        if run.get("run_kind") != "trial" or run.get("l600_delta") is None:
            continue
        base = float(run["l600_delta"])
        margin = run.get("margin")
        own = (str(run.get("source") or source) == "sportsbet_race_context" and margin is not None)
        values.append(base + float(margin) * _SEC_PER_LENGTH if own else base)
    values = [v for v in values if math.isfinite(v)]
    return sum(values) / len(values) if values else None


def performance_pf_metrics(horse):
    """Same formal-only PF evidence for the runner and whole-field normalization.

    Trial rows stay in the raw `pf_metrics` for `trial_speed_raw` (試閘備戰) but never
    reach L600 環境分. Untagged legacy rows cannot safely be classified as trials.
    """
    metrics = ((horse.get("_data") or {}).get("pf_metrics") or {})
    # EXP-20261016-77（用戶 2026-10-16 決定）：L600 環境分只用正式賽，試閘 PF 行一律唔計；
    # 試閘速度改由 `trial_speed_score` 喺試閘備戰計。
    runs = metrics.get("pf_runs") or []
    kept = [run for run in runs if run.get("run_kind") != "trial"]
    if len(kept) == len(runs):
        return metrics
    source = (metrics.get("pf_aggregates") or {}).get("source", "unknown")
    return {**metrics, "pf_runs": kept,
            "pf_aggregates": _pf_aggregates([dict(run) for run in kept], source)}
JOCKEY_TRAINER_COMBO_STATS_PATH = AUTO_RESOURCE_DIR / "AU_Jockey_Trainer_Combo_Stats.csv"
JOCKEY_RATINGS_PATH = AUTO_RESOURCE_DIR / "AU_Jockey_Ratings.csv"
TRAINER_RATINGS_PATH = AUTO_RESOURCE_DIR / "AU_Trainer_Ratings.csv"
JOCKEY_TRAINER_COMBO_CACHE: dict[tuple[str, str, str], dict] | None = None
TRAINER_TRACK_CACHE: dict[tuple[str, str], dict] | None = None
JOCKEY_RATINGS_CACHE: dict[str, dict] | None = None
TRAINER_RATINGS_CACHE: dict[str, dict] | None = None

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


_FRONT_TOKENS = ("front runners", "前置", "前領偏差", "on-pace bias", "利放頭", "跟前")
_NEGATORS = ("唔利", "不利", "唔到", "難以", "冇優勢", "not favour", "against")


def _profile_front_bias(bias_text: str) -> bool:
    """成個場地係唔係真係偏前置 —— 逐行判斷，唔係掃全文。

    跳過兩類行：
      * 條件式行（`rail out` / `rail position` / `+3` 之類）—— 引擎唔知今日 rail
      * 否定式行（「唔利前置」）—— substring 掃描會當成正面訊號
    """
    for raw in str(bias_text or "").splitlines():
        line = raw.strip().lower()
        if not line:
            continue
        if "rail" in line or re.search(r"[+＋]\s*\d", line):
            continue
        if any(neg in line for neg in _NEGATORS):
            continue
        if any(tok in line for tok in _FRONT_TOKENS):
            return True
    return False


def _normalize_track_name(name: str) -> str:
    n = str(name or '').strip()
    for old, new in TRACK_NAME_CLEANUP:
        n = n.replace(old, new)
    return n.strip()


def _monotone(table: dict) -> dict:
    """Longer race ⇒ closing 600m cannot be FASTER (running max, short → long).

    2026-08-23：手嵌嘅 `_STANDARD_600M` 有 **41 處**物理上不可能嘅反轉，最嚴重
    Newcastle 2200m 36.75s → 2400m **35.11s（−1.64s）**、Bendigo 2200→2400 −0.97s、
    Morphettville 2000→2600 −0.73s、Randwick 2000→2400 −0.59s。多數係細樣本雜訊。
    反轉令該距離嘅 delta 方向唔一致地偏移，而且同下面嘅 bin 向上取整互相放大
    （實測 binned 同內插標準嘅差距達 **±2.1 秒**）。
    """
    out = {}
    run = float("-inf")
    for dist in sorted(table):
        run = max(run, table[dist])
        out[dist] = run
    return out


_STANDARD_600M_MONO = {t: _monotone(tbl) for t, tbl in _STANDARD_600M.items()}
_DISTANCE_ONLY_L600_MONO = _monotone(_DISTANCE_ONLY_L600)


def _lookup_standard_l600(track: str, distance_m: int) -> float | None:
    """該場地＋該距離嘅「標準」最後 600m 秒數。

    2026-08-23 兩個修正：

    1. **線性內插，唔再向上取整。** 原本行 `_distance_bin`（`dist <= bin`），
       所以一場 **1250m** 賽事同 **1300m** 嘅標準比 —— 長距離標準較慢，於是
       delta 偏負（睇落偏快）。實測 **18,175 / 54,914 個 pf_runs（33.1%）**
       距離短過自己個 bin。Gunroom 十仗五仗中招，`l600_delta_avg`
       由 −0.163 變 −0.123（慢 0.040 秒）。
    2. **標準表強制單調**（見 `_monotone`）。

    判決（653 場，contract `gold` ＝捕捉率）：
      內插 + 單調  Gold **+1.06 [+0.2, +2.1] ✅**  Pass +0.16  t3prec +0.05
                  Good位 −0.77  首選上名 −0.15
      walk-forward 3 個窗口：Gold **3/3 全正、從未負、平均 +1.02**；Pass 亦從未負；
                  t3prec 同首選上名 ±0.00（只內插而唔單調係 −0.07 / −0.41，較差）

    ⚠️ `_distance_bin` 仍然保留 —— 佢有其他 caller。
    """
    norm = _normalize_track_name(track)
    table = _STANDARD_600M_MONO.get(norm)
    source = table if (table and len(table) >= 2) else _DISTANCE_ONLY_L600_MONO
    dists = sorted(source)
    if not dists:
        return None
    if distance_m <= dists[0]:
        return source[dists[0]]
    if distance_m >= dists[-1]:
        return source[dists[-1]]
    for lo, hi in zip(dists, dists[1:]):
        if lo <= distance_m <= hi:
            if hi == lo:
                return source[lo]
            frac = (distance_m - lo) / (hi - lo)
            return source[lo] + frac * (source[hi] - source[lo])
    return None









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

# `track_score` 偏弱門檻（consistency −4 規則用）。EXP-20261016-70 將 track base 由 62.9 改 60，
# 門檻跟住由 60 改 57.1，維持原本「只有往績差或濕地未驗證先觸發」。




def _normalize_identity_text(value) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_rating_identity(value) -> str:
    text = _normalize_identity_text(value)
    text = text.replace("(J-Mac)", "").strip()
    return text.lower()


def _surname_token_match(name: str, tokens) -> bool:
    """姓氏 token 比對 —— 要**整個字**，唔可以係 substring。

    ⚠️ `token in name` 會令 `Clark` 中 `Sheridan Clarke`、`Bott` 中 `Shane Bottomley`。
    實測 836 場入面單係 T1 閘就擦錯 189 個位（已改為 DB-only，見 `_is_top_jockey`）。
    下面 `_jockey_rank_value` 嗰兩張名單係**純顯示**（`_jockey_change_signal` 嘅
    「較強／較高級騎師」分支明文唔入分），呢個窗口冇擦錯人，但 `Parr`⊃`Parry`、
    `Moore`⊃`Moorehouse` 呢啲隱患一樣存在，所以一併行呢個 helper。
    """
    if not name:
        return False
    return any(re.search(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])", name)
               for token in tokens)


def _load_jockey_trainer_combo_stats():
    global JOCKEY_TRAINER_COMBO_CACHE, TRAINER_TRACK_CACHE
    if JOCKEY_TRAINER_COMBO_CACHE is not None and TRAINER_TRACK_CACHE is not None:
        return JOCKEY_TRAINER_COMBO_CACHE, TRAINER_TRACK_CACHE

    combo_cache: dict[tuple[str, str, str], dict] = {}
    trainer_cache: dict[tuple[str, str], dict] = {}
    # Optional enrichment is bundled with the engine. Keeping this small snapshot
    # out of the Drive archive avoids placeholder timeouts and makes each scoring
    # run reproducible/offline. Failure still degrades to empty cached lookups.
    try:
        available = JOCKEY_TRAINER_COMBO_STATS_PATH.exists()
    except OSError:
        available = False
    if available:
        try:
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
        except OSError as exc:
            print(f"⚠️  J/T combo stats unavailable ({type(exc).__name__}) — scoring without them")
            combo_cache, trainer_cache = {}, {}
    for stats in trainer_cache.values():
        runs = stats["runs"] or 0
        stats["win_rate"] = (stats["wins"] / runs) if runs else 0.0
        stats["place_rate"] = (stats["places"] / runs) if runs else 0.0

    JOCKEY_TRAINER_COMBO_CACHE = combo_cache
    TRAINER_TRACK_CACHE = trainer_cache
    return combo_cache, trainer_cache
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
                base_score = parse_float(row.get("base_score"))
                payload = {
                    "name": _normalize_identity_text(row.get("name")),
                    "canonical_name": _normalize_identity_text(row.get("canonical_name")),
                    "tier": _normalize_identity_text(row.get("tier")),
                    "base_score": float(
                        60 if base_score is None else base_score
                    ),
                    "confidence": _normalize_identity_text(row.get("confidence")),
                    "source": _normalize_identity_text(row.get("source")),
                    "notes": _normalize_identity_text(row.get("notes")),
                    # 呢個 tier 判斷幾時已經存在（EXP-20261015-04）。歷史場次只准用
                    # `as_of < 賽事日期` 嘅行；冇日期嘅行喺歷史場次當中性。
                    "as_of": str(row.get("as_of") or "").strip()[:10],
                }
                for key in {payload["name"], payload["canonical_name"]}:
                    normalized = _normalize_rating_identity(key)
                    if normalized:
                        cache[normalized] = payload
        return cache

    JOCKEY_RATINGS_CACHE = load_csv(JOCKEY_RATINGS_PATH)
    TRAINER_RATINGS_CACHE = load_csv(TRAINER_RATINGS_PATH)
    return JOCKEY_RATINGS_CACHE, TRAINER_RATINGS_CACHE




# 對手後續走勢字串有兩種寫法（2026-08-04 起）：
#     「出 N 次: M 勝」    —— 對手有完整往績記錄
#     「見前三 N 次: M 勝」 —— 只由對手名單推導（partial），我哋只見到佢入前三
# 兩者嘅**勝出次數都係準嘅**（我哋見到佢全部前三），所以讀「M 勝」嗰陣兩種都要接。
# 分開兩個寫法係為咗唔好講大話 —— partial 嗰批唔知佢總共出過幾多次。
#
# ⚠️ 呢個常數存在嘅原因：加咗第二種寫法之後，四處獨立嘅 regex 一齊變成
# 只認第一種，即係新增嗰批對手會**靜靜咁**被當成「冇後續」。
# 呢個 repo 已經有五次同款缺陷（見 `scraper-silent-drop-failure-mode`）。
RE_OPP_FOLLOWUP = re.compile(r"(?:出|見前三)\s*\d+\s*次:\s*(\d+)\s*勝")


def finite_pf_number(value, field):
    """PF absence is None; observed numbers must be finite and cannot be bool."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"Invalid PF numeric value for {field}: boolean")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid PF numeric value for {field}") from exc
    if not math.isfinite(number):
        raise ValueError(f"Nonfinite PF numeric value for {field}")
    return number


# EXP-20261028-12：讓磅賽認字。量度用嘅 `scratch/au_fq_weight_class_dump_20261028.py::classify_title`
# 同呢度一致（handicap／hcp／benchmark／bm58／rating 0-64 組別，加截斷嘅 handicap 前綴）。
_HANDICAP_TITLE_RE = re.compile(r"\b(?:handicap|hcp|hcap|h'cap|benchmark|bm\s*\d+|rst\s*\d+)\b"
                                r"|\b(?:rating\s*)?\d{1,2}\s*-\s*\d{2,3}\b|\brating\s+\d", re.I)
_TRUNCATED_HANDICAP_RE = re.compile(r"\bh(?:a(?:n(?:d(?:i(?:c(?:a(?:p)?)?)?)?)?)?)\s*$", re.I)


def _is_handicap_title(title) -> bool:
    text = " ".join(str(title or "").replace("&amp;", "&").split())
    return bool(_HANDICAP_TITLE_RE.search(text)
                or (len(text) >= 40 and _TRUNCATED_HANDICAP_RE.search(text)))

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
        self.evidence_state = {}
        # 人馬配搭分逐項調整紀錄（因子、加減分、原始數據）— 供報告完整追溯
        self.jt_fit_detail = None
        self.preparation_parts = []
        self._record_entry_cache = None
        self._official_entry_cache = None
        self._sectional_trend_cache = None
        self._formline_row_cache = None
        self._track_context_cache = None
        self._track_family_cache = None
        self._sectional_breakdown_cache = None
        self._formguide_shape_cache = None
        self._pf_metrics_cache = None
        self.horse_data["horse_name"] = self._clean_identity(self.horse_data.get("horse_name"))
        self.horse_data["jockey"] = self._clean_identity(self.horse_data.get("jockey"))
        self.horse_data["trainer"] = self._clean_identity(self.horse_data.get("trainer"))

    def _pf_metrics(self):
        """Historical L600 evidence carried by this runner's form rows.

        Populated by enrichment, or by `backfill_pf_metrics` for archive Logic
        files built before the PF scraper existed. Both write `_data`, so the
        field-relative stats in `field_summary` and the per-runner score always
        see the same set of runs.

        Racenet can supply runner-level timing, but Sportsbet `Sectionals 600m`
        is race-level and repeats across runners from the same historical race.
        The shared legacy key is therefore L600 context, not guaranteed
        individual sectional speed.
        """
        if self._pf_metrics_cache is None:
            metrics = performance_pf_metrics(self.horse_data)
            self._pf_metrics_cache = metrics if isinstance(metrics, dict) else {}
        return self._pf_metrics_cache

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
        feature_scores, feature_notes = self._score_features()

        for key in FEATURE_KEYS:
            feature_scores[key] = clip_score(feature_scores.get(key, 60))
            feature_notes.setdefault(key, "資料不足，以中性 60 分處理。")
            self.provenance.setdefault(key, "missing_neutral")

        # 兩條「−4」情境扣分（近績分／級數、穩定性分／場地）已剷：重複計分（EXP-20261103-10）。
        # Complete class-adjusted margin evidence replaces the old consistency
        # leaf inside the stability matrix.  Where that evidence is unavailable,
        # copy the already-context-adjusted consistency score exactly so legacy
        # and thin-data races remain rank-identical.
        pq_source = self.provenance.get("performance_quality_score")
        if pq_source == "consistency_fallback":
            feature_scores["performance_quality_score"] = feature_scores.get(
                "consistency_score",
                60,
            )
            feature_notes["performance_quality_score"] = (
                "未有最少兩場同時包含輸距、獎金及出馬數嘅完整近績；"
                f"沿用跑法穩定性 {feature_scores['performance_quality_score']:.1f} 分。"
            )
            detail = getattr(self, "performance_quality_detail", {}) or {}
            detail["final"] = round(feature_scores["performance_quality_score"], 2)
            detail["fallback"] = "consistency_score"
            self.performance_quality_detail = detail
        elif pq_source == "sportsbet_complete_form_archive_recovery":
            observed = feature_scores.get("performance_quality_score", 60)
            consistency = feature_scores.get("consistency_score", 60)
            recovered = consistency + SPORTSBET_PQ_RECOVERY_ALPHA * (
                observed - consistency
            )
            feature_scores["performance_quality_score"] = clip_score(recovered)
            feature_notes["performance_quality_score"] = (
                feature_notes.get("performance_quality_score", "")
                + f"；舊檔完整 Sportsbet 往績以 {SPORTSBET_PQ_RECOVERY_ALPHA:.0%} "
                  "reliability 融合，避免回填證據取代原 captured Facts"
            )
            detail = getattr(self, "performance_quality_detail", {}) or {}
            detail["field_relative_recovered_score"] = round(float(observed), 2)
            detail["recovery_alpha"] = SPORTSBET_PQ_RECOVERY_ALPHA
            detail["consistency_anchor"] = round(float(consistency), 2)
            detail["final"] = round(feature_scores["performance_quality_score"], 2)
            self.performance_quality_detail = detail
        # 「人馬配搭 ≥72 兼級數分 <58 → −3」已剷：結構上觸發唔到（EXP-20261103-07）。
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

        # 近績質素分 (EXP-20261016-06) after every form / PQ context adjustment, so
        # its fallback is exactly the old stability composite of the final leaves.
        fq, fq_note, fq_source = self._merged_form_quality(feature_scores)
        fq, fq_note = self._trip_change_adjustment(fq, fq_note)
        feature_scores["form_quality_score"] = fq
        ts_score, ts_note = self._merged_trial_speed()
        feature_scores["trial_speed_score"] = ts_score
        feature_notes["trial_speed_score"] = ts_note
        self.provenance["trial_speed_score"] = "trial_pf_own_l600_field_relative"
        feature_notes["form_quality_score"] = fq_note
        self.provenance["form_quality_score"] = fq_source
        self.evidence_state["form_quality_score"] = (
            "observed" if fq_source == "form_quality_field_relative"
            else "derived" if fq_source == "form_quality_overseas_rating_proxy" else "fallback")

        # Export the same precision consumed by the matrix. This makes a saved
        # feature vector replayable by ML/refit without hidden rounding drift.
        feature_scores = {key: round(value, 6) for key, value in feature_scores.items()}
        matrix_scores = map_features_to_matrix_scores(feature_scores)
        matrix = map_features_to_matrix(feature_scores)
        pure_7d_score = round(compose_matrix_score(matrix_scores), 4)
        base_7d_score = pure_7d_score
        # Report-only post-7D modifiers (dynamic weights, soft-shape, diversity, barrier,
        # soft-wetproof, place-tightening, micro-rank, wet-condition) were retired
        # 2026-06-22: ML-refuted (barrier net-negative; place-tightening overfit) and
        # never entered ranking/display. Ranking + 綜合戰力分 = pure 7D + wet_form feature only.

        # Wet-form going-suitability feature: 0 on dry going, folded into ability on
        # Soft/Heavy. base_7d_score stays pure 7D; 綜合戰力分 (ability_score) becomes
        # wet-aware on wet tracks. Walk-forward validated (Soft box-trifecta +2.2pp OOS).
        wet_form_feat = _track.wet_overlay(self._today_going(), self.data.get("going_stats_line"))
        wet_form_detail = _track.wet_overlay_detail(self._today_going(), self.data.get("going_stats_line"))
        class_proof_feat, class_proof_detail = self._proven_class_feature()
        base_ability = round(pure_7d_score + wet_form_feat + class_proof_feat, 4)
        full_time_detail = self.horse_data.get("full_time_speed") or {}
        full_time_feature = full_time_contribution(self.horse_data, self.race_context)
        if not math.isfinite(full_time_feature):
            raise ValueError("non-finite AU full-time contribution")
        draw_feature = round(_draw.horse_adjustment(
            self.horse_data.get("barrier"), self._field_summary().get("barriers"), self._straight_course()), 4)
        ability_score = round(base_ability + full_time_feature + draw_feature, 4)
        grade = compute_grade(ability_score)

        data_coverage = self._data_coverage()
        matrix_reasoning = self._matrix_reasoning(matrix_scores, feature_scores, feature_notes)
        advantages = self._advantages(feature_scores, matrix_scores)
        disadvantages = self._disadvantages(feature_scores, matrix_scores)
        core_logic = self._core_logic(feature_scores, matrix_scores, advantages, disadvantages)
        prep_context = self._preparation_cycle()
        if prep_context['stage'] in {'first_up', 'second_up', 'third_up'}:
            core_logic += ' ' + prep_context['summary'] + '。'
            self.risk_flags.append(prep_context['summary'])
        grade_transparency = self._au_grade_computation_transparency(
            matrix_scores, matrix, feature_scores, base_7d_score, ability_score, grade,
            feature_notes=feature_notes,
            wet_form_feature=wet_form_feat,
            class_proof_feature=class_proof_feat,
            full_time_speed_feature=full_time_feature,
            draw_feature=draw_feature,
        )

        return {
            "version": "AU_AUTO_SCORE_V3",
            "pure_7d_score": round(pure_7d_score, 4),
            "base_7d_score": base_7d_score,
            "final_rank_score": ability_score,
            "ability_score": ability_score,
            "rank_score": ability_score,
            "wet_form_feature": round(wet_form_feat, 4),
            "wet_form_detail": wet_form_detail,
            "proven_class_feature": round(class_proof_feat, 4),
            "full_time_speed_feature": full_time_feature,
            "full_time_speed_detail": full_time_detail,
            "draw_feature": draw_feature,
            # EXP-20261009-04 回退影子：class_score 入 class_weight 對綜合分嘅貢獻。
            # 舊公式分數 = 綜合分 − 呢個數（矩陣冇 clip 嗰陣逐位一樣）。
            "class_score_live_delta": round(
                MATRIX_WEIGHTS["class_weight"] * CLASS_SCORE_LIVE_WEIGHT
                * (clip_score(feature_scores.get("class_score", 60)) - 60.0), 4)
            if CLASS_SCORE_LIVE else 0.0,
            "proven_class_detail": class_proof_detail,
            "grade": grade,
            "race_context": {
                "going": self._today_going(),
                "meeting_bias": self._meeting_bias_brief(),
                "track_geometry": self._track_geometry_brief(),
            },
            "matrix": matrix,
            "matrix_scores": matrix_scores,
            "data_coverage": data_coverage,
            "matrix_reasoning": matrix_reasoning,
            "feature_scores": {key: feature_scores[key] for key in FEATURE_KEYS},
            "feature_notes": {key: feature_notes.get(key, "") for key in FEATURE_KEYS},
            "core_logic": core_logic,
            "preparation_cycle": prep_context,
            "data_readout": self._data_readout(feature_scores, matrix_scores),
            "advantages": advantages,
            "disadvantages": disadvantages,
            "grade_transparency": grade_transparency,
            "jt_fit_detail": self.jt_fit_detail,
            "preparation_detail": getattr(self, "preparation_detail", None),
            "trial_speed_detail": getattr(self, "trial_speed_detail", None),
            "stability_detail": {
                "form": getattr(self, "form_detail", {}) or {},
                "consistency": getattr(self, "consistency_detail", {}) or {},
                "performance_quality": getattr(self, "performance_quality_detail", {}) or {},
                "form_quality": getattr(self, "form_quality_detail", {}) or {},
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
            "feature_evidence_state": self.evidence_state,
        }

    def _proven_class_feature(self) -> tuple[float, dict]:
        """高班實績 overlay（EXP-20260825-03）：0.5 × 場內 z；見 class_rating。"""
        raw = parse_float(self.data.get("proven_class_raw"))
        summary = self.race_context.get("field_summary") or {}
        z_score = self._proven_z()
        adjustment = _class.proven_class_overlay(z_score)
        mean = parse_float(summary.get("proven_class_field_mean"))
        stdev = parse_float(summary.get("proven_class_field_stdev"))
        r4 = lambda v: round(v, 4) if v is not None else None  # noqa: E731
        detail = {
            "raw": r4(raw),
            "field_count": int(summary.get("proven_class_field_count") or 0),
            "field_mean": r4(mean),
            "field_stdev": r4(stdev),
            "z_score": r4(z_score),
            "weight": PROVEN_CLASS_Z_WEIGHT,
            "adjustment": round(adjustment, 4),
            "state": "observed_field_relative" if z_score is not None else "missing_neutral",
        }
        return adjustment, detail

    def _score_features(self):
        feature_scores = {}
        feature_notes = {}
        for name in FEATURE_KEYS:
            score, note, source = getattr(self, f"_{name}")()
            feature_scores[name] = clip_score(score)
            feature_notes[name] = note
            self.provenance[name] = source
            self.evidence_state[name] = self._feature_evidence_state(name, source)
        return feature_scores, feature_notes

    # Ability-feeding features (per matrix_mapper). formline is weight-0 so it is
    # excluded from the coverage that reflects the actual ranking evidence.
    _COVERAGE_FEATURES = ABILITY_FEATURE_KEYS

    def _feature_evidence_state(self, name, source):
        """Classify evidence independently from the numeric score.

        A real observation can legitimately score exactly 60, while several
        no-data fallbacks intentionally use non-60 priors. Numeric equality is
        therefore not a valid completeness test.
        """
        if source in {"missing_neutral", "disabled_neutral"}:
            return "missing"
        if name == "form_score":
            return "observed" if (getattr(self, "form_detail", {}) or {}).get("rows") else "fallback"
        if name == "trial_score":
            return "observed" if self._trial_places() else "fallback"
        if name == "sectional_score":
            return "observed" if self._sectional_breakdown().get("has_pi") else "missing"
        if name == "pace_map_score":
            return "observed" if parse_float(self.horse_data.get("barrier")) is not None else "fallback"
        if name == "jockey_score":
            return "observed" if source in {
                "unified_place_rate",
                "jockey_rating_db",
            } else "fallback"
        if name == "trainer_score":
            # 統一率或者資料庫 tier 先算有證據（EXP-20261103-06）。舊判斷靠一句由來冇出現過嘅字串，所以永遠 observed。
            source = (getattr(self, "trainer_detail", {}) or {}).get("source")
            return "observed" if source in {"unified", "db"} else "fallback"
        if name == "jockey_horse_fit_score":
            # 試閘備戰嗰兩項分開計分，但照舊算人馬配搭有證據。
            return "derived" if (self.jt_fit_detail or {}).get("adjustments") or self.preparation_parts else "fallback"
        if name == "class_score":
            has_class_evidence = bool(
                self._official_entries()
                or self._class_move_today()
            )
            return "derived" if has_class_evidence else "fallback"
        if name == "rating_score":
            return "observed" if source == "racecard_rating+field_relative" else "fallback"
        if name == "weight_score":
            return "observed"
        if name == "track_score":
            detail = getattr(self, "track_detail", {}) or {}
            return "observed" if detail.get("notes") else "fallback"
        if name == "consistency_score":
            return "derived" if self._official_entries() else "fallback"
        if name == "performance_quality_score":
            return (
                "observed"
                if source in {
                    "class_adjusted_margin_field_relative",
                    "sportsbet_complete_form_archive_recovery",
                }
                else "fallback"
            )
        if name == "pace_figure_score":
            return "observed" if source == "pf_l600_delta_field_relative" else "missing"
        if name == "distance_score":
            return "derived" if self._official_entries() else "fallback"
        if name == "formline_score":
            return "derived" if self._formline_rows() else "fallback"
        if name == "confidence_score":
            return "derived"
        return "observed"

    def _data_coverage(self):
        """Fraction of ranking features backed by observed or derived evidence."""
        missing = [
            key
            for key in self._COVERAGE_FEATURES
            if self.evidence_state.get(key, "missing") not in {"observed", "derived"}
        ]
        total = len(self._COVERAGE_FEATURES)
        present = total - len(missing)
        pct = round(100.0 * present / total, 1)
        if pct >= 75:
            label = "高"        # confident: most features real
        elif pct >= 50:
            label = "中"
        else:
            label = "薄"        # thin: score rests on few real signals
        return {
            "coverage_pct": pct,
            "present": present,
            "total": total,
            "confidence": label,
            "missing_features": missing,
            "feature_states": {
                key: self.evidence_state.get(key, "missing")
                for key in self._COVERAGE_FEATURES
            },
        }

    def _get_class_tier(self, text):
        return race_class_tier(text)[0]

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
            # 生涯有正式賽，但 Sportsbet 往績頁冇嗰幾行（只剩試閘）。官方 Last 10
            # 解讀（已跳過試閘）仍然話我哋知名次 —— 唔可以當「冇證據」中性 60。
            # Last10 0 係未獲正式名次（亦可能取消資格），唔係確切第十名。
            # 有非標準正式賽果行時唔會走呢個缺表 fallback。
            # 冇馬群大細、冇班次，所以只用絕對名次階梯、班次乘數 1.0。
            fallback = (parse_recent_finishes(self.data.get("recent_form"), source_format=self.data.get("recent_form_format", "auto")) or [])[:min(starts, 4)]
            if not fallback:
                detail["note"] = "缺乏正式賽績（賽績表未有可用場次），按中性 60 分處理"
                detail["final"] = 60.0
                return 60, "缺乏正式賽績，近績分按 60 分處理。", "career_tag"
            today_class = self.race_context.get("race_class", "")
            entries = [{"placing": str(place), "field_size": None, "class": today_class,
                        "kind": "", "from_last10": True} for place in fallback]
            detail["source"] = "official_last10_without_form_lines"

        # Preserve the actual evidence separately from the prize proxy. A
        # sponsor title / historical HC is never proof of a race's BM class.
        detail["source_context"] = [
            {k: entry.get(k) for k in ("date", "venue", "going", "source_race_class", "prize")}
            for entry in entries[:4]
        ]
        today_surface = _surface_kind(self._today_going())
        differing = [e for e in entries[:4] if today_surface and _surface_kind(e.get("going"))
                     and _surface_kind(e.get("going")) != today_surface]
        if differing:
            detail["surface_transfer_note"] = (
                f"近四仗有 {len(differing)} 仗來自另一種跑道；今場"
                f"{'草地' if today_surface == 'turf' else '合成跑道'}。"
                "跨跑道成績轉移未有可靠校準，來源高分不等於今場適性已獲證明。")
            self.risk_flags.append("surface_transfer_unverified")

        today_class = self.race_context.get("race_class", "")
        today_tier, today_known = race_class_tier(today_class)

        total_weighted_score = 0.0
        total_applied_weights = 0.0
        notes = []

        for i, entry in enumerate(entries[:4]):
            place = parse_placing(entry.get("placing"))
            if place is None:
                continue

            # 名次 → base。有馬群大細時改用**場內百分位**（2026-07-31，用戶提出）：
            # 絕對名次唔理馬群，令「6 匹跑第 4」同「16 匹跑第 4」一律 base 60。
            # 5,066 場有真實馬群大細嘅 run 量到 21.5% base 評錯、11.0% 錯 ≥20 分，
            # 最大 cohort 係大場第 6+ 被當成細場跑最後（8.9%，應由 40 升到 60）。
            # 公式同 `shared_racing/eval_metrics.py` 嘅 top_pick_pct 一致：
            #   pct = (place − 1) / (field − 1)     0.0 = 頭馬，1.0 = 最後
            # 門檻由現行階梯反推 12 匹標準場（2/12→.09、3/12→.18、5/12→.36）。
            # A/B（713 場，覆蓋 33%）：dev Gold 34→36、any2 +0.82、winT3 +0.66、
            # 頭號推介跌落尾三分一 −0.82pp；holdout 競爭力 −1.87/+2.81，
            # 前三命中類指標動 1–2 場。冇馬群大細（舊 meeting）→ 完全沿用絕對名次。
            field_size = entry.get("field_size")
            if field_size and field_size >= 2 and place <= field_size:
                pct = (place - 1) / (field_size - 1)
                # A win over two rivals supplies less evidence than a win
                # over thirteen. Shrink only the winner's positive deviation
                # from 60 by (N-1)/(N+1); missing field sizes keep the legacy
                # fallback. This is evidence weighting, not a win probability.
                # EXP-20260902-06: fixed candidate, same-corpus RANKING_WIN;
                # terminal Gold/Good +2 races each, primary CIs cross zero.
                if pct <= 0.0: base_pts = 60 + 40 * (field_size - 1) / (field_size + 1)
                elif pct <= 0.12: base_pts = 85
                elif pct <= 0.25: base_pts = 75
                elif pct <= 0.50: base_pts = 60
                else: base_pts = 40
            elif place == 1: base_pts = 100
            elif place == 2: base_pts = 85
            elif place == 3: base_pts = 75
            elif place <= 5: base_pts = 60
            else: base_pts = 40

            if i == 0: decay = 1.0
            elif i == 1: decay = 0.8
            elif i == 2: decay = 0.6
            else: decay = 0.4

            # EXP-20261016-13（K2，§7 正確性修正）：以前讀 `entry["class"]`，呢個 key 由來冇存在，
            # entry_tier 永遠係 7，乘數變成由今場班次決定嘅全場常數（今場新馬賽 ×1.1、
            # Group 1 ×0.7）。改讀往績真班次 `source_race_class`；任何一邊認唔到就唔調（×1.0）。
            if FORM_ENTRY_CLASS_TIER:
                entry_tier, entry_known = race_class_tier(entry.get("source_race_class") or "")
                delta = today_tier - entry_tier if (today_known and entry_known) else 0
            else:
                delta = today_tier - self._get_class_tier(entry.get("class", ""))

            if delta >= 2: class_mult = 1.2
            elif delta == 1: class_mult = 1.1
            elif delta == 0: class_mult = 1.0
            elif delta == -1: class_mult = 0.85
            else: class_mult = 0.7

            race_score = base_pts * class_mult
            total_weighted_score += race_score * decay
            total_applied_weights += decay
            # cols[1] 係 row kind／歷史 horse HC，唔係 race class。Racenet `HC`
            # 曾經被錯寫成 `BMxx`，而缺 HC 又被錯寫成 `Maiden/SW`；兩者都會令
            # 解說將馬匹 rating 誤當賽事班次。新 Facts 會寫 `HCxx`／`正式`。
            # 呢欄只作證據顯示，唔參與 class multiplier。
            kind_text = str(entry.get("kind") or "").strip()
            cls = kind_text if kind_text.startswith("HC") else ""
            detail["rows"].append({
                "idx": i + 1,
                "place": int(place),
                "cls": cls,
                "base": base_pts,
                "mult": class_mult,
                "decay": decay,
                # 持久化馬群大細，令 replay / shadow test 唔使再由 Facts 反推
                "field_size": field_size,
                "historical_rating": entry.get("historical_rating"),
            })

        # 「近績被抬高」風險旗（2026-07-31，用戶提出嘅 Benbulben 型個案）：
        # 計分近仗睇落名次唔差（舊階梯 base ≥60），但實際係場內後半段位置
        # 或者輸一大截。archive 量化（2,139 個前三推介）：
        #   clean     n=2,077  勝 17.5%  前三 44.8%  跌落尾三分一 22.8%  平均 SP 10.2
        #   flattered n=   62  勝  9.7%  前三 41.9%  跌落尾三分一 40.3%  平均 SP 13.1
        # 效應大（尾三分一率差 17.5pp）但只佔 2.9% —— 八個全局計分修正全部 A/B 失敗
        # （見 2026-07-31 覆盤報告第 9 節），所以呢個只做**標示**，唔入分。
        # 門檻用**實際採用嘅 base**（唔係舊階梯）：馬群大細正規化會將「大場第 6」
        # 由 40 升到 60，而嗰場如果同時輸一大截，就正正係最需要標示嘅一場。
        # 用舊階梯做門檻會反而漏咗佢。
        flattered = heavy_defeats = 0
        for row, entry in zip(detail["rows"], entries[:4]):
            fs = row.get("field_size")
            back_half = bool(fs and fs >= 2
                             and (int(row["place"]) - 1) / (fs - 1) > 0.5)
            beaten = re.search(r"\(([-+]?\d+(?:\.\d+)?)L\)",
                               str(entry.get("placing") or ""))
            big_margin = bool(beaten and abs(float(beaten.group(1))) > 5.0)
            if big_margin:
                heavy_defeats += 1
            # 「被抬高」= 實際採用嘅 base 仍然 ≥60，但證據話居後 / 大敗。
            if int(row["base"]) >= 60 and (back_half or big_margin):
                flattered += 1
        detail["flattered_runs"] = flattered
        detail["heavy_defeat_runs"] = heavy_defeats
        if flattered:
            self.risk_flags.append("form_flattered")
            notes.append(f"{flattered} 場計分近仗名次好睇但實際居後/大敗（標示，不入分）")
        if heavy_defeats:
            notes.append(f"{heavy_defeats} 場計分近仗輸超過 5 個馬位（標示，不入分）")

        if total_applied_weights > 0:
            avg_score = total_weighted_score / total_applied_weights
        else:
            avg_score = 60

        score = min(100.0, max(0.0, avg_score))
        detail["avg"] = round(score, 2)

        # 2026-07-10「新馬試閘時間補充」（+5／+3）已剷走（EXP-20261016-76）：佢讀
        # `timing_trial_600m_avg_speed`，嗰個欄嚟自 Racenet 時代逐駒 600m 分段時間。轉 Sportsbet 之後
        # 頁面冇逐駒 600m（試閘行只有場級 L600 差 41.9%、頭馬時間 65.1%），乾淨窗 28,974 匹 0% 有值，
        # 規則由來冇觸發。試閘速度已經經 pace_figure（個體 L600，試閘 PF 行保留）入分，唔再重砌。

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

        # 班次調整（2026-07-31，用戶提出「狀態與穩定性要真正反映實力」）：
        # 原本 `class_mult` 係全場統一常數（見上面 entry["class"] 註釋），即係近績分
        # 完全唔理一匹馬嘅前列成績係喺乜班次做出嚟。用獎金做班次代理補上。
        #
        # 場內相對（同對手比）而唔係絕對值 —— 排名只喺場內比較，而且唔受今仗獎金
        # 缺失影響。場內中位數由 `field_summary.prize_level_field_median` 提供
        # （同 pace_figure 拿 l600_delta_field_mean 同一個 pattern）。
        # A/B（713 場）K=10：dev 全部指標變好或平，holdout 冇任何指標變差。
        # ⚠️ 一定要喺「劣績中性回歸」**之後**施加 —— A/B 驗證嘅版本係加喺最終
        # 近績分上面。放喺回歸之前會令回歸把班次調整一併damp（偏弱分 ×n/(n+2)），
        # 咁就同驗證過嘅公式唔同。
        field = self._field_summary() or {}
        field_median = parse_float(field.get("prize_level_field_median"))
        own_level = horse_prize_level(self.facts_section)
        if field_median is not None and own_level is not None:
            class_adj = CLASS_PRIZE_K * (own_level - field_median)
            if abs(class_adj) >= 0.05:
                score = clip_score(score + class_adj)
                detail["bonus"].append({
                    "delta": round(class_adj, 2),
                    "factor": "班次水平調整",
                    "evidence": (
                        f"近仗獎金水平 log10 {own_level:.2f} vs 全場中位 "
                        f"{field_median:.2f}（{'高' if class_adj > 0 else '低'}"
                        f"{abs(own_level - field_median):.2f}）"
                    ),
                })
                notes.append("已按近仗班次水平（獎金）校正"
                             if class_adj > 0 else "近仗班次水平（獎金）偏低已扣減")

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
        if not trial_performance_applies(self.horse_data):
            starts = int(parse_float(self.horse_data.get("career_race_starts")))
            note = (f"已跑 {starts} 場正式賽，試閘表現不入能力分；"
                    "試閘資料保留作備戰及騎師熟習背景。")
            detail.update(base=60.0, final=60.0, note=note,
                          excluded_by_career_starts=True)
            return 60.0, note, "disabled_neutral"
        trial_places = self._trial_places()
        starts = self._career_starts()
        is_maiden = self._is_maiden_race()
        if not trial_places:
            tw = TRIAL_MICRO_WEIGHTS
            base = (tw.get("no_trial_debut_base", 58.0) if starts == 0
                    else tw.get("no_trial_base", 60.0))
            detail["base"] = base
            detail["final"] = base
            detail["note"] = "無試閘紀錄，按保守中性處理"
            return base, "試閘訊號有限，試閘分保守處理。", "trial_table"
        good = sum(1 for place in trial_places[:3] if place <= 3)
        if good == 0:
            # Observed poor trials must not be rendered as if the horse merely
            # had no trial data.  The score already starts below neutral (56);
            # this flag makes the evidence visible without adding a second
            # numerical penalty for the same information.
            self.risk_flags.append("trial_no_recent_top3")
        tw = TRIAL_MICRO_WEIGHTS
        score = tw.get("base", 56.0)
        detail["base"] = score

        def add(delta, factor, evidence=""):
            nonlocal score
            score += delta
            detail["adjustments"].append({"delta": round(float(delta), 2),
                                          "factor": factor, "evidence": evidence})

        if good:
            add(good * tw.get("top3_mult", 9.0), "試閘前三獎勵",
                f"近3次試閘{good}次前三（每次 +{tw.get('top3_mult', 9.0):.0f}）")
        trial_count = int(parse_float(self.data.get("trial_count")) or len(trial_places))
        latest_trial = trial_places[0] if trial_places else None
        if starts == 0:
            add(tw.get("debut_prep_bonus", 4.0), "初出馬備戰", "未出賽，試閘係主要備戰證據")
            if is_maiden:
                add(tw.get("debut_maiden_bonus", 2.0), "新馬賽初出加碼", "")
                self.reason_codes.append("maiden_debut_trial_boost")
        if latest_trial == 1:
            add(tw.get("latest_win_bonus", 4.0), "最近試閘頭馬", "最近一課試閘勝出")
            if is_maiden:
                add(tw.get("latest_win_maiden_bonus", 2.0), "新馬賽加碼", "")
        elif latest_trial is not None and latest_trial <= 3:
            add(tw.get("latest_top3_bonus", 2.0), "最近試閘前三", f"最近一課試閘第{int(latest_trial)}")
            if is_maiden:
                add(tw.get("latest_top3_maiden_bonus", 1.0), "新馬賽加碼", "")
        if trial_count >= 4 and safe_ratio(good, max(1, min(3, trial_count))) >= 0.66:
            # 2026-09-03: the +2.0 density bonus that used to sit here was the
            # same evidence `preparation_score` already scores as 試閘交代密度足夠.
            # Measured over 20,882 runners: all 4,792 that fired here also fired
            # there, and 0 fired only here -- a strict subset. The two are not
            # equal in effect: trial_score transmits 0.0070 of a point to the
            # ability score and preparation_score transmits 0.2524, so the copy
            # here was worth +0.014 against the other's +0.853 (EXP-20260903-03).
            # Removing it changed 4,370 runners' scores and 0.00000pp of gold,
            # good_positional, pass, champion and top-3 precision on 1,384 dev
            # races. Kept: the maiden-only extra below, which is not duplicated.
            if is_maiden and trial_count >= 6 and safe_ratio(good, trial_count) >= 0.6:
                add(tw.get("density_maiden_bonus", 3.0), "新馬賽密集備戰加碼", "")
                self.reason_codes.append("maiden_trial_density_boost")
        # 新馬試閘時間快 +4／+2 已剷走（EXP-20261016-76）：`timing_trial_600m_avg_speed` 由來冇值。
        # Trial video signals were scored here (被拑制／盡試冇料／有爭勝／轉弱／
        # 帶放／走勢改善, ±2-4 points). They fired on 12 of 20,882 runners because
        # this source does not publish trial comments at all: of 77,336 `Video:`
        # lines inside a trial entry, 15 carry text (0.02%). Official runs do
        # carry them (85,948 lines), which is why the terms looked reasonable.
        # Removing them moved 2 runners and 0.00000pp of every headline metric
        # (EXP-20260903-03). `trial_video_signals` is still parsed and stored for
        # the report; if a future source starts publishing trial comments, the
        # scoring has to be re-derived and A/B'd rather than silently waking up.
        detail["final"] = round(clip_score(score), 2)
        return score, f"近試閘前 3 名次 {trial_places[:3]}，有 {good} 次前列，並按最近一課/試閘密度修正，試閘分 {clip_score(score):.1f}。", "trial_table"

    def _run_was_competitive(self, entry, max_lengths=3.0):
        """嗰場係唔係真係有競爭力（唔係大敗 / 唔係場內後半）。

        兩個條件都係「知道就判、唔知就唔判死」，避免因為缺數據而丟訊號：
          * 有馬群大細 → 場內百分位必須 ≤ 0.5
          * 有輸距     → 輸距必須 ≤ max_lengths
        兩樣都唔知 → 當有競爭力（保守，行為同修改前一致）。
        """
        place = parse_placing(entry.get("placing"))
        field = entry.get("field_size")
        if field and field >= 2 and place and place >= 1:
            if (place - 1) / (field - 1) > 0.5:
                return False
        beaten = re.search(r"\(([-+]?\d+(?:\.\d+)?)L\)", str(entry.get("placing") or ""))
        if beaten and abs(float(beaten.group(1))) > max_lengths:
            return False
        return True

    def _sectional_breakdown(self):
        if self._sectional_breakdown_cache is not None:
            return self._sectional_breakdown_cache
        entries = self._official_entries()
        latest_entry = entries[0] if entries else {}
        latest_place = parse_placing(latest_entry.get("placing")) if latest_entry else None
        recent_top4 = sum(1 for entry in entries[:3] if (parse_placing(entry.get("placing")) or 99) <= 4)
        forgiveness_count = self._forgiveness_count()

        w = SECTIONAL_MICRO_WEIGHTS
        # ⚠️ 呢個 leaf 係**純加分累加器**：base 60 + 只有正項，所以最低就係 60。
        # 咁樣「有 PI 數據但段速平平」同「完全冇 PI 數據」攞一模一樣嘅分 ——
        # 睇落似個要修嘅單邊尺。**試過三次，三次都輸。唔好試第四次。**
        #
        # 713 場場內量度（已修正馬群大細，數字＝相對該批期望前三率嘅超額）：
        #     恰好 60（冇 PI 數據）   n=2877   −1.4
        #     有 PI，60–65           n= 607   **−2.4**   ← 差過「冇數據」
        #     有 PI，65–70           n=1121   −1.0
        #     有 PI，70–80 / 80–90   n=2624   +1.2 / +1.7
        #     有 PI，90–100          n= 318   **+6.9**
        # 排序的確倒轉咗，但幅度得 1.0pp（對比 `jockey_horse_fit` 當初嗰個
        # 6.6pp 就改得成）。實測代價大過收益：
        #   2026-08-01（另一線）「有 PI 但零增益」扣 −4 / −8 → holdout ndcg
        #     −0.34 / −0.46、crec −0.58 / −0.73，兩檔 REJECT。
        #   2026-08-02（本線）整批有數據嘅起點下移 3 / 6 / 9 分再按比例放大加分
        #     （頂位仍然剛好 100）→ holdout champ −0.93 / −0.93 / **−1.87**、
        #     mrr −0.67 / −0.67 / −1.14、ndcg −0.29 / −0.45 / −0.54。**單調越改越差。**
        #
        # 點解會咁：PI 係「追前幅度」，同跑法糾纏 —— 領放到底嘅馬天生冇追前幅度
        # 可言，罰低 PI 等於罰前領型馬，而前領型馬贏開。所以 champ 同 mrr 首當其衝。
        # 要真係救呢 1pp，要先令段速量度**與跑法無關**（例如同位置對應嘅期望
        # 收放比），唔係喺分數層搬點位。
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
        # 競爭力封頂（2026-07-31，用戶提出）：原本逐場收 PI 然後平均，完全唔理嗰場
        # 跑成點。Benbulben 拿 +20「位置增益優秀」，而嗰個 +5 係定位第 11、終點第 6、
        # 輸 9.05L、賽事節奏 V Slow 嘅一場 —— Racenet 自己評語係
        # "Passed a few plodders late."。喺爬行賽事由最後追過幾隻慢馬唔係後勁證據。
        #
        # 做法：非競爭場次嘅正 PI 封到 0，但**仍然計入分母** —— 早期版本直接剔走整場，
        # 結果連負 PI（失位）嘅弱勢證據都被抹走，有啲馬平均 PI 反而升，係設計錯誤。
        #
        # A/B（713 場）：holdout 冇任何指標變差，winT3 +0.94、t3prec +0.63、
        # compet +0.94；dev 基本平（Gold −1）。受影響 7.0% 馬匹，平均 −13.17 分。
        pi_from_entries = []
        capped_runs = 0
        proxy_runs = 0
        for entry in entries:
            pi_val = parse_float(entry.get("pi"))
            if pi_val is None:
                # 覆蓋解鎖（2026-09-01）：`pi` 欄空唔代表冇走位資料。Sportsbet 只喺
                # 41.6% 往績印 `Settled`，但 800m 檢查點有 71.6%，而佢做代理
                # 偏差 +0.044 / ρ 0.9688。詳見 `pi_from_trajectory`。
                pi_val, mark = pi_from_trajectory(entry.get("trajectory"))
                if pi_val is None:
                    continue
                if mark == "800m":
                    proxy_runs += 1
            if pi_val > 0 and not self._run_was_competitive(entry):
                pi_val = 0.0
                capped_runs += 1
            pi_from_entries.append(pi_val)

        if not pi_from_entries:
            # 2026-07-10：無 PI 時嘅試閘時間補償 REMOVED — 舊 bonus 非單調（最快 +0、
            # 較慢 +3.97，ML search 殘骸），三個修法 A/B「完全移除」最好（GGP +2）。
            # 試閘證據由試閘分（同維度 leaf）獨力承擔。
            add(0.0, "位置增益（PI）", "缺 L400 PI 數據 — 呢匹馬近仗冇官方 PI 紀錄")
            add(0.0, "末段速度（L600）", "缺 PI 時不參與評分")
            add(0.0, "增益兌現", "不適用（無 PI 數據）")
            notes.append("缺 L400 PI 數據，段速證據薄，維持基礎分")
        else:
            avg_pi = sum(pi_from_entries) / len(pi_from_entries)
            n_pi = len(pi_from_entries)
            capped_note = (f"（其中 {capped_runs} 場大敗/居後，追前不予計功）"
                           if capped_runs else "")

            if avg_pi >= 4.0:
                add(w.get("pi_extreme_bonus", 25.0), "位置增益（PI）極佳",
                    f"近{n_pi}仗末段平均追前 {avg_pi:.1f} 個位（≥4 屬頂級後勁）{capped_note}")
            elif avg_pi >= 2.0:
                add(w.get("pi_excellent_bonus", 15.0), "位置增益（PI）優秀",
                    f"近{n_pi}仗末段平均追前 {avg_pi:.1f} 個位{capped_note}")
            elif avg_pi >= 0.0:
                add(w.get("pi_pass_bonus", 5.0), "位置增益（PI）達標",
                    f"近{n_pi}仗末段平均 {avg_pi:+.1f} 個位（冇失地）{capped_note}")
            else:
                add(0.0, "位置增益（PI）",
                    f"近{n_pi}仗末段平均俾人過 {abs(avg_pi):.1f} 個位——缺乏後勁{capped_note}")

            # 2. Distance-Adjusted L600
            # 口徑修正（2026-07-31）：原本用 `timing_600m_best_speed` —— 即係**生涯
            # 最大值** —— 去同今仗路程嘅場地標準比。一次快段速就變成永久資歷，
            # 而唔係「而家有幾快」。實測 best/avg 中位數 1.035、P99 1.101，
            # 26.7% 嘅馬 best 高出自己平均 ≥5%（Benbulben 1.110，P99 以上）。
            #
            # 693 場逐場排名對實際名次嘅 Spearman ρ（唔需要場地標準，直接比口徑）：
            #   L600 平均            ρ 0.057  Q1−Q5 7.8pp
            #   L600 最近            ρ 0.045  Q1−Q5 5.5pp
            #   L600 最快封頂 avg×1.05 ρ 0.035  Q1−Q5 5.8pp
            #   L600 生涯最快（原本）  ρ 0.023  Q1−Q5 4.8pp  ← 四個之中最差
            # 平均值嘅預測力係生涯最快嘅 2.5 倍，所以改用平均。
            # Rollback: 將 `timing_600m_avg_speed` 換返 `timing_600m_best_speed`。
            tw_typical = self.data.get("timing_600m_avg_speed")
            if tw_typical and tw_typical > 0:
                typical_l600 = 600.0 / tw_typical
                # 防禦（2026-07-11）：可信 L600 帶 31-42s（舊 writer 分佈 31.4-41.9）。
                # 帶外＝上游污染（曾出過「快過標準 9 秒」假象），唔採用。
                if not (31.0 <= typical_l600 <= 42.0):
                    add(0.0, "末段速度（L600）",
                        f"時間數據異常（{typical_l600:.2f}s 超出可信範圍），唔採用")
                    race_dist = None
                else:
                    race_dist = self._distance_from_text(self.race_context.get("distance", ""))
                if race_dist and race_dist >= 600:
                    std_l600 = _lookup_standard_l600(self._current_venue_name(), race_dist)
                    if std_l600 and std_l600 > 0:
                        delta = typical_l600 - std_l600
                        if delta <= -0.6:
                            add(w.get("l600_extreme_bonus", 15.0), "末段速度（L600）破標準",
                                f"平均 {typical_l600:.2f}s，快過場地標準 {std_l600:.2f}s 成 {abs(delta):.2f}s")
                        elif delta <= -0.3:
                            add(w.get("l600_excellent_bonus", 5.0), "末段速度（L600）優秀",
                                f"平均 {typical_l600:.2f}s，快過場地標準 {abs(delta):.2f}s")
                        else:
                            add(0.0, "末段速度（L600）",
                                f"平均 {typical_l600:.2f}s，未快過場地標準（{std_l600:.2f}s）")
                    else:
                        add(0.0, "末段速度（L600）", "此場地/路程無標準時間可比")
            else:
                add(0.0, "末段速度（L600）", "缺 L600 時間數據")

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
            "label": "中性 60 + PI/L600 累加",
        }
        return self._sectional_breakdown_cache
    def _sectional_score(self):
        target_line = str(self.data.get("target_distance_line") or "")
        entries = self._official_entries()
        latest_entry = entries[0] if entries else {}
        latest_place = parse_placing(latest_entry.get("placing")) if latest_entry else None
        latest_flags = self._entry_note_flags(latest_entry) if latest_entry else {"positive": [], "negative": []}
        race_bucket = self._race_class_bucket()
        wet_state = self._wet_state()
        recent_top3 = sum(1 for entry in entries[:3] if (parse_placing(entry.get("placing")) or 99) <= 3)
        breakdown = self._sectional_breakdown()
        score = breakdown["score"]
        notes = []
        # 短判語行先（逐項計法喺 pace_perf_detail 攤開，唔使喺度重覆）
        # 2026-08-01：base 移到中性 60 之後，「冇證據」同「有證據但唔靚」必須分開講。
        # 舊寫法 score>=60 → 「證據正面」，而中性化後 60 正正就係「查唔到」，會講反。
        if not breakdown.get("has_pi"):
            notes.append("缺 L400 PI 數據，段速分維持中性")
        elif score >= 75:
            notes.append("PI 位置增益證據正面")
        elif score > 60.5:
            notes.append("PI 證據一般")
        else:
            notes.append("有 PI 紀錄但未見末段增益")
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
        """檔位分 = 60 + 大場次檔位分（`draw.py`，同入綜合分嗰個 `draw_feature` 一樣）。

        呢個 leaf 唔入維度權重（`race_shape` 係數 None），只係令報告「檔位形勢」顯示真正入分嗰個數。
        舊逐場地檔位矩陣（`au_draw_bias_matrix.json`）已剷走：EXP-20260821-04／20260901-03 證實佢訊號太細，
        EXP-20261102-07 嘅簡單場內檔位排名先有方向一致嘅正數（EXP-20261102-09）。
        """
        e = _draw.explain(self.horse_data.get("barrier"), self._field_summary().get("barriers"),
                          self._straight_course())
        score = 60.0 + e["adj"]
        if e["applies"]:
            line = (f"檔位 {self.horse_data.get('barrier')}：{e['n']} 匹入面第 {e['rank']} 內（場內 z {e['z']:+.2f}）"
                    f"→ 檔位分 {e['adj']:+.2f}（直接加落綜合分）")
        else:
            line = f"檔位 {self.horse_data.get('barrier') or '-'}：{e['reason']}"
        self.pace_map_detail = {"base": 60.0, "lines": [line], "final": round(clip_score(score), 2)}
        note = (f"{e['n']} 匹入面第 {e['rank']} 內，檔位分 {e['adj']:+.2f}。" if e["applies"]
                else f"{e['reason']}，檔位分中性。")
        return score, note, "barrier_rank_big_field"

    def _race_date(self) -> str:
        """賽事日期（YYYY-MM-DD）；攞唔到回 ""（= 當 live，唔改行為）。"""
        for value in (self._meeting_intelligence().get("date"), self.race_context.get("date")):
            text = str(value or "").strip()[:10]
            if _pit.is_iso_date(text):
                return text
        if self.facts_path is not None:
            match = re.search(r"(\d{4}-\d{2}-\d{2})", _meeting_dir(self.facts_path).name)
            if match:
                return match.group(1)
        return ""

    def _rating_known_at_race(self, rating):
        """騎練 tier 表冇版本：歷史場次只准用 `as_of < 賽事日期` 嘅行
        （EXP-20261015-04，L1 leak 7）。live（今日或之後）行為不變。"""
        if not rating:
            return None
        race_date = self._race_date()
        if not _pit.is_historical(race_date):
            return rating
        as_of = str(rating.get("as_of") or "")
        return rating if _pit.is_iso_date(as_of) and as_of < race_date else None

    def _jockey_rating_profile(self, jockey: str):
        if not jockey:
            return None
        jockey_cache, _ = _load_named_rating_stats()
        return self._rating_known_at_race(jockey_cache.get(_normalize_rating_identity(jockey)))

    def _trainer_rating_profile(self, trainer: str):
        if not trainer:
            return None
        _, trainer_cache = _load_named_rating_stats()
        return self._rating_known_at_race(trainer_cache.get(_normalize_rating_identity(trainer)))

    def _jockey_score(self):
        """騎師分：見 `jockey_trainer`。呢度只砌說明。"""
        jockey = self._clean_identity(self.horse_data.get("jockey"))
        ly = self.data.get("jockey_ly") or {}
        detail = {"lines": [], "source": ""}
        self.jockey_detail = detail
        unified = _jt.rate_score("jockey", ly)
        if unified is not None:
            score, evidence = unified
            detail["source"] = "unified_place_rate"
            detail["lines"] = [evidence, f"高過基準加分、低過扣分 → {clip_score(score):.1f} 分（60 為中性）"]
            return score, f"{jockey} {evidence}，騎師分 {clip_score(score):.1f}。", "unified_place_rate"
        rating = self._jockey_rating_profile(jockey)
        if rating:
            score = rating["base_score"]
            tier = _jt.tier_text(rating.get("tier"), "jockey")
            note = f"{jockey} · {tier}" + ("（暫定補名）" if rating.get("confidence") == "provisional" else "")
            detail["source"] = "db"
            detail["lines"] = [f"{tier} → {clip_score(score):.0f} 分"]
            runs, wins, places = _jt.ly_record(ly)
            if runs:
                detail["lines"].append(f"去年官方：{int(runs)} 騎、{int(wins or 0)} 冠 {int(places)} 上名"
                                       f"（勝率 {(wins or 0) / runs * 100:.0f}%、上名率 {places / runs * 100:.0f}%）")
            return score, f"{note}，騎師分 {clip_score(score):.1f}。", "jockey_rating_db"
        # LY 少過 10 場同練馬師一樣當中性（EXP-20261103-06）：以前用另一把尺（prior 0.365、spread 100），
        # 例如 John Velazquez 去年澳洲 1 騎 0 上名 → 58.3。
        runs, _wins, places = _jt.ly_record(ly)
        detail["source"] = "neutral"
        detail["lines"] = [f"去年官方僅 {int(runs)} 騎、上名 {int(places)} 次，未達 {_jt.MIN_RUNS} 場可信門檻 → 中性 60 分" if runs
                           else "資料庫／官方統計均無記錄 → 中性 60 分"]
        return 60, f"{jockey or '騎師資料'} 屬中性配置，騎師分 60.0。", "jockey_missing_neutral"

    def _trainer_score(self):
        """練馬師分：見 `jockey_trainer`。場館往績只做報告（delta 0）。"""
        trainer = self._clean_identity(self.horse_data.get("trainer"))
        ly = self.data.get("trainer_ly") or {}
        unified = _jt.rate_score("trainer", ly)
        rating = None if unified is not None else self._trainer_rating_profile(trainer)
        runs, wins, places = _jt.ly_record(ly)
        if unified is not None:
            score, base_evidence = unified
            base_label = "統一上名率"
        elif rating:
            score, base_evidence = rating["base_score"], ""
            base_label = _jt.tier_text(rating.get("tier"), "trainer")
        else:
            score, base_evidence = 60, ""
            base_label = (f"去年官方僅 {int(runs)} 場、{int(wins or 0)} 冠 {int(places)} 上名，"
                          f"未達 {_jt.MIN_RUNS} 場可信門檻，按中性處理" if runs
                          else "Sportsbet 官方統計未有可用記錄，中性起步")
        detail = {"base": round(float(score), 1), "base_label": base_label, "adjustments": [],
                  "source": "unified" if unified is not None else "db" if rating else "neutral",
                  "final": round(clip_score(score), 2), "base_evidence": base_evidence,
                  "ly_line": (f"去年官方：{int(runs)} 場、{int(wins or 0)} 冠 {int(places)} 上名"
                              f"（勝率 {(wins or 0) / runs * 100:.0f}%、上名率 {places / runs * 100:.0f}%）" if runs else "")}
        self.trainer_detail = detail
        notes = []
        if rating:
            notes.append(base_label + ("（暫定補名）" if rating.get("confidence") == "provisional" else ""))
        venue = _jt.venue_note(self._trainer_track_stats())
        if venue:
            detail["adjustments"].append({"delta": 0.0, "factor": venue[0], "evidence": venue[1]})
            notes.append(venue[0])
        thin = base_label if unified is None and rating is None and runs else ""
        head = f"{trainer} {base_evidence}" if (trainer and base_evidence) else \
            (base_evidence or (f"{trainer} {thin}" if trainer and thin else "") or "；".join(notes) or
             f"{trainer or '練馬師資料'} Sportsbet 官方統計未有可用記錄")
        if base_evidence and notes:
            head += "；" + "；".join(notes)
        return score, f"{head}，練馬師分 {clip_score(score):.1f}。", "trainer_name+trainer_track_stats"

    def _preparation_score(self):
        """試閘備戰分 = 60 + 試閘密度兩項（由 `jockey_trainer.fit_parts` 出，喺人馬配搭分度分開）。"""
        selected = self.preparation_parts
        score = 60.0 + sum(a["delta"] for a in selected)
        if selected:
            self.preparation_detail = {"base": 60.0, "adjustments": selected, "final": clip_score(score)}
        note = "；".join(a.get("evidence") or a["factor"] for a in selected)
        return score, note or "未有額外試閘備戰證據", "trial_preparation"

    def _formguide_trial_counts(self):
        """(試閘課數, 前列課數)：前列 = 試閘場內百分位 ≤ 40%；冇馬匹數就照舊絕對 ≤ 3（EXP-20261016-75 P2）。"""
        trials = self.data.get("fg_trials") or []
        good = 0
        for t in trials:
            f, n = t.get("finish_pos"), t.get("starters")
            if f and n and int(n) >= 2:
                good += (int(f) - 1) / (int(n) - 1) <= 0.4
            elif f:
                good += int(f) <= 3
        return len(trials), good

    def _jockey_horse_fit_score(self):
        """人馬配搭分：入分項見 `jockey_trainer.fit_parts`；呢度砌數字同唔入分嘅敘述。"""
        jockey = self._clean_identity(self.horse_data.get("jockey"))
        trainer = self._clean_identity(self.horse_data.get("trainer"))
        trial_count = int(parse_float(self.data.get("trial_count")) or len(self._trial_places()))
        trial_top3 = int(parse_float(self.data.get("trial_top3_count"))
                         or sum(1 for place in self._trial_places() if place <= 3))
        # EXP-20261016-75 P2（§7）：試閘「入前三」按試閘場內百分位（前 40%）。
        if self.data.get("fg_trials") is not None:
            trial_count, trial_top3 = self._formguide_trial_counts()
        signal = self._jockey_change_signal() or ""
        rides, places = self._current_jockey_formal_rides(), self._current_jockey_formal_places()
        parts = _jt.fit_parts({
            "jockey": jockey, "trial_count": trial_count, "trial_top3": trial_top3,
            "top_jt": self._is_top_jockey(jockey) or self._is_top_trainer(trainer),
            "current_rides": rides, "current_places": places, "current_wins": self._current_jockey_formal_wins(),
            "current_trial_rides": self._current_jockey_trial_rides(),
            "current_trial_top3": self._current_jockey_trial_top3(), "change_signal": signal,
        })
        signal_factors = ("沿用歷來最佳人馬配搭", "試閘手接手，備戰線完整")
        prep = [p for p in parts if p[1] in _jt.PREPARATION_FACTORS]
        parts = [p for p in parts if p[1] not in _jt.PREPARATION_FACTORS]
        self.preparation_parts = [{"factor": f, "delta": round(float(d), 2), "evidence": str(e or "").strip()}
                                  for d, f, e in prep if d]
        notes = [factor for _, factor, _ in parts if factor not in signal_factors]

        # 唔入分嘅敘述（次序同報告一樣）。
        if self._best_formal_jockey() and self._best_formal_jockey_rides() > 0:
            vs_best = self._current_vs_best_jockey_brief()
            if vs_best:
                notes.append(vs_best)
        latest = self._latest_official_jockey()
        latest_rides = self._latest_official_jockey_formal_rides()
        latest_rate = safe_ratio(self._latest_official_jockey_formal_places(), latest_rides)
        if latest and latest != jockey and latest_rides > 0:
            if rides == 0 and latest_rate >= 0.50:
                notes.append(f"今場離開上仗已證明配搭（上仗{latest}對此駒上名率"
                             f"{latest_rate * 100:.0f}%，實測此群反而超額 +4.1pp，不入分）")
            elif rides > 0 and latest_rate > safe_ratio(places, rides) + 0.20:
                notes.append(f"今場騎師對此駒往績未及上仗騎師（今場上名率{safe_ratio(places, rides) * 100:.0f}%"
                             f" vs 上仗{latest} {latest_rate * 100:.0f}%，不入分）")
        combo = self._current_track_combo_stats()
        if combo.get("runs", 0) >= 5:
            combo_evidence = (f"{jockey}×{trainer}同場館{int(combo.get('runs', 0))}次，"
                              f"上名率{combo.get('place_rate', 0.0) * 100:.0f}%、勝率{combo.get('win_rate', 0.0) * 100:.0f}%")
            if combo.get("place_rate", 0.0) >= 0.45:
                notes.append(f"今場場館騎練組合已有穩定上名輸出（{combo_evidence}，不入分）")
            elif combo.get("place_rate", 0.0) < 0.15:
                notes.append(f"今場場館騎練組合過往交代偏淡（{combo_evidence}，不入分）")
        if signal:
            if "沿用歷來最佳配搭" in signal or ("試閘手接手" in signal and not any(
                    k in signal for k in ("較強騎師", "換下較高級騎師", "沿用上仗騎師"))):
                notes += [factor for _, factor, _ in parts if factor in signal_factors]
            elif "較強騎師" in signal or "換下較高級騎師" in signal:
                notes.append(f"{signal}（評級變化只作背景，不入分）")
            elif "沿用上仗騎師" in signal:
                notes.append(f"{signal}（實測此群低於同層 3.7–6.7pp，不入分）")
            elif "回配" in signal:
                notes.append(f"{signal}（實測此群反而低於同層 1.2–7.5pp，不入分）")
        status_cycle = self._status_cycle_text()
        stage_stats = self._stage_stats()
        if status_cycle in {"First-up", "久休復出"} and stage_stats["first_up"]["places"] > 0:
            notes.append(f"過往首仗上陣有基本交代（{stage_stats['first_up'].get('runs', '')}次"
                         f"{stage_stats['first_up']['places']}上名，不入分）")
        if status_cycle in {"Second-up", "二出"} and stage_stats["second_up"]["places"] > 0:
            notes.append(f"二出歷史有承接（{stage_stats['second_up'].get('runs', '')}次"
                         f"{stage_stats['second_up']['places']}上名，不入分）")
        claim = -float(self.horse_data.get("jockey_allowance_kg") or 0.0)
        weight = parse_float(self.horse_data.get("weight"))
        if claim > 0 and weight:
            notes.append(f"見習減磅 {claim:g}kg（分配 {weight:.1f}kg → 實負 {weight - claim:.1f}kg，不入分）")
        if trainer in {"", "Unknown"}:
            notes.append("馬房資料不完整")

        adjustments = [{"factor": factor, "delta": round(float(delta), 2), "evidence": str(evidence or "").strip()}
                       for delta, factor, evidence in parts if delta]
        score = 60.0
        for delta, _, _ in parts:
            score += float(delta)
        if not adjustments and not self.preparation_parts:
            score = _jt.FIT_NO_EVIDENCE
            notes.append("並無任何人馬配搭紀錄（新配搭／輕出賽馬），按實測低於中性處理")
        self.jt_fit_detail = {"base": 60.0, "final": round(clip_score(score), 2), "adjustments": adjustments}
        note = "；".join(notes) if notes else "未見特別人馬部署訊號"
        return score, f"{note}。人馬配搭分 {clip_score(score):.1f}。", \
            "jockey_trainer_fit+stage_stats+trial_continuity+formguide_jockey_history+track_combo_stats"

    def _matrix_reasoning(self, matrix_scores, feature_scores, feature_notes):
        return {
            spec.key: self._reason_bundle(
                spec.key,
                (matrix_scores.get(spec.key, spec.reasoning_score_default)
                 if spec.reasoning_score_default is not None else matrix_scores[spec.key]),
                feature_scores,
                feature_notes,
                *(spec.reasoning_components or tuple(key for key, _ in spec.leaves)),
            )
            for spec in DIMENSION_SPECS if spec.shown_in_report
        }

    def _reason_bundle(self, key, score, feature_scores, feature_notes, *component_keys):
        label = self._matrix_label(key)
        # 有啲 component 係純 context（矩陣公式內權重 = 0）—— 例如 級數分（2026-07-29
        # 退出）同 負磅分（2026-08-01 退出）。之前佢哋同真·計分項排一齊、格式一模
        # 一樣，讀者見到「級數分 60、負磅分 60」就自然當成「呢個維度全部都係 60，
        # 純噪音」。標明出嚼，維度分數點嚟先睇得明。
        scoring_leaves = {
            name for name, _weight in MATRIX_FORMULAS.get(canonical_matrix_key(key), ())
        }
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
                    "in_ranking": component_key in scoring_leaves,
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
        """Source-aware L600 evidence plus runner-level PI interpretation."""
        pace = feature_scores.get("pace_figure_score", 60)
        sec = feature_scores.get("sectional_score", 60)
        pd = getattr(self, "pace_figure_detail", {}) or {}
        pf_source = str(pd.get("source") or "unknown")
        individual_pf = pf_source.startswith("racenet_")
        has_pf = pd.get("state") == "ok"
        has_pi = bool(self._sectional_breakdown().get("has_pi"))

        if has_pf and individual_pf and pace >= 72:
            verdict = "逐駒 L600 benchmark 快過場均，個體速度證據偏強。"
        elif has_pf and individual_pf and pace <= 48:
            verdict = "逐駒 L600 benchmark 明顯慢過場均，個體速度證據偏弱。"
        elif has_pf and individual_pf:
            verdict = "逐駒 L600 benchmark 接近場均，個體速度證據中性。"
        elif has_pf and pace >= 72:
            verdict = "往績所處賽事末段環境快過場均——反映過往速度考驗，唔等於本駒個體末段。"
        elif has_pf and pace <= 48:
            verdict = "往績賽事末段環境明顯慢過場均，速度考驗旁證偏弱。"
        elif has_pf and pace <= 56:
            verdict = "往績賽事末段環境略慢過場均，速度考驗旁證冇著數。"
        elif has_pf:
            verdict = "往績賽事末段環境貼近場均，呢項旁證中性。"
        elif has_pi:
            verdict = "冇 L600 環境數據，只有 PI 位置增益作旁證，呢一格參考價值有限。"
        else:
            verdict = "段速證據不足，呢一格唔好過份解讀。"

        # 門檻對應段速分階梯（60 = 冇增益證據、75 = PI 優秀、81 = PI 極佳），
        # 2026-08-01 中性化之後重新對位（舊尺 45/55/60 喺新尺永遠唔會觸發）。
        cross = ""
        if has_pf and has_pi:
            if individual_pf and pace >= 68 and sec >= 75:
                cross = "逐駒 benchmark 同 PI 升位方向一致，個體速度證據較完整。"
            elif individual_pf and pace >= 68:
                cross = "逐駒 benchmark 偏快但 PI 平平，速度有數據、兌現度仍要保守。"
            elif individual_pf and sec >= 75:
                cross = "PI 升位靚但逐駒 benchmark 未見優勢，後勁證據未完全一致。"
            elif pace >= 68 and sec >= 75:
                cross = "快末段賽事背景下仍有 PI 升位，個體後勁旁證較完整。"
            elif pace >= 68 and sec <= 63:
                cross = "只係往績賽事末段快、PI 升位平平，唔可以當成本駒自己快。"
            elif pace < 56 and sec >= 75:
                cross = "PI 升位靚但往績賽事末段環境偏慢，位置增益要保守解讀。"

        evidence_name = "逐駒 benchmark" if individual_pf else "L600 環境"
        conf = (f"強（{evidence_name} {int(pd.get('runs') or 0)} 場）" if has_pf
                else "中（只有 PI 位置增益）" if has_pi
                else "弱（只餘試閘／無數據）")
        return " ".join(x for x in (verdict, cross, f"速度背景證據信心：{conf}。") if x)

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
            
        quality_score = feature_scores.get(
            "performance_quality_score",
            feature_scores.get("consistency_score", 60),
        )
        if feature_scores["form_score"] >= 72 and quality_score >= 68:
            assessment = "連仗交出接近表現證明戰鬥力企穩，唔係單靠一場偶發水準撐起，具備堅實嘅爭勝底氣。"
        elif feature_scores["form_score"] <= 58 or quality_score <= 58:
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
        """一句檔位（同入綜合分嘅大場次檔位分一致）＋預期跑法。"""
        style = self._running_style()
        style_parts = [p.strip() for p in str(style).split("/")]
        if len(style_parts) > 1 and len(set(style_parts)) == 1:
            style = style_parts[0]
        barrier = self.horse_data.get("barrier")
        e = _draw.explain(barrier, self._field_summary().get("barriers"), self._straight_course())
        if not e["applies"]:
            draw_v = f"排 {barrier} 檔（{e['reason']}）"
        elif e["adj"] >= 0.5:
            draw_v = f"排 {barrier} 檔，{e['n']} 匹入面屬內檔，有利（{e['adj']:+.1f}）"
        elif e["adj"] <= -0.5:
            draw_v = f"排 {barrier} 檔，{e['n']} 匹入面屬外檔，蝕位（{e['adj']:+.1f}）"
        else:
            draw_v = f"排 {barrier} 檔，{e['n']} 匹入面屬中間（{e['adj']:+.1f}）"
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
        """一句今場班次／負磅 → 一句能力對位結論。逐項計法喺評分構成 detail 攤開。"""
        class_move = self._class_move_display()
        weight = parse_float(self.horse_data.get("weight"))
        cs = feature_scores["class_score"]
        rs = feature_scores["rating_score"]

        head = f"今仗 {self._race_class_text()}"
        if weight is not None:
            head += f"，負 {weight:.1f}kg{self._weight_allowance_suffix()}"
        if "降班" in class_move:
            head += "，今場班次較上仗低"
        elif "升班" in class_move:
            head += "，今場班次較上仗高"
        head += "。"

        # 維度 = 0.70 評分分 + 0.15 級數分（class_rating）；負磅分只做顯示。
        if rs >= 66:
            verdict = "官方讓磅分對位高過場均，能力面有實質支持。"
        elif rs <= 54:
            verdict = "官方讓磅分對位低過場均，能力面要靠其他維度補。"
        else:
            verdict = "能力對位貼近場均，未見明顯阻力亦未見甜頭。"
        if cs <= 56:
            verdict += f" 級數分 {cs:.0f} 偏低。"
        elif cs >= 65:
            verdict += f" 級數分 {cs:.0f} 偏高。"
        return head + " " + verdict

    def _describe_track_matrix(self, score, feature_scores):
        """短而狠：場地/地狀適應一句定調 ＋（濕地）風險一句。逐項計法喺評分構成攤開。"""
        ts = feature_scores["track_score"]
        wet_state = self._wet_state()
        if ts >= 70:
            verdict = "同場/今日地狀有實績支持，場地唔會成為絆腳石。"
        elif ts <= 54:
            verdict = "場地/地狀往績未見支持，發揮要打折睇。"
        elif not any(_track.track_score(self._track_records(), self._today_going())[1:]):
            verdict = "冇同場／今日地況往績，場地分維持中性。"
        else:
            verdict = "場地適應有基礎，應付到今日地狀。"
        if wet_state in {"soft7plus", "heavy"} and not self._has_verified_wet_place():
            verdict += " 爛地實績未經驗證（唔扣分：未跑過濕地嘅馬實測只差 −1.2pp）。"
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
                m = RE_OPP_FOLLOWUP.search(nr)
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

    def _speed_evidence_brief(self):
        """L600 環境分每一仗用咗乜（speed.evidence）：賽事 L600 對基準、輸距、本駒估算、權重。"""
        metrics = self._pf_metrics() or {}
        source = str((metrics.get("pf_aggregates") or {}).get("source") or "")
        parts = []
        for run in _speed.evidence(metrics.get("pf_runs") or [], source):
            where = " ".join(str(x) for x in (run["date"], run.get("venue"),
                                               f"{run['distance']}m" if run.get("distance") else None) if x)
            if run["own"] is not None:
                body = f"賽事 {run['race']:+.2f}s、輸 {float(run['margin']):.1f}L → 本駒 {run['own']:+.2f}s"
            else:
                body = f"賽事 {run['race']:+.2f}s"
            parts.append(f"{where}：{body}（×{run['weight']:.2f}）")
        return "；".join(parts)

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
            # 逐項計法已喺評分構成 detail 攤開，錨點只留原始證據
            return self._anchor_lines(
                ("逐仗證據（新→舊，負數＝快過基準）", self._speed_evidence_brief()),
                ("近段 PI 走勢", self._sectional_trend_brief()),
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
        from .dimensions import MATRIX_LABELS
        if key in MATRIX_LABELS:
            return MATRIX_LABELS[key]
        return {
            "stability": "狀態與穩定性",
            "pace_perf": "速度考驗背景",
            # 舊 key 保留畀歷史 Logic 檔顯示
            "sectional": "段速與引擎",
            "pace_figure": "往績賽事 L600 環境",
            "race_shape": "檔位形勢",
            "jockey_trainer": "騎練訊號",
            "class_level": "級數門檻",
            "weight_pressure": "負磅壓力",
            "class_weight": "官方評分對位",
            "track": "場地與地況適性",
            "form_line": "賽績線",
            "preparation": "試閘備戰",
        }.get(key, key)

    def _feature_label(self, key):
        return {
            "form_score": "近績分",
            "trial_score": "試閘分",
            "sectional_score": "段速分",
            "pace_figure_score": "L600 環境分",
            "pace_map_score": "檔位分",
            "jockey_score": "騎師分",
            "trainer_score": "練馬師分",
            "jockey_horse_fit_score": "人馬配搭分",
            "class_score": "級數分",
            "rating_score": "Rating 分",
            "weight_score": "負磅分",
            "distance_score": "路程分",
            "track_score": "同場／地況往績分",
            "formline_score": "賽績線分",
            "consistency_score": "穩定性分",
            "performance_quality_score": "表現質素分",
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

    def _au_grade_computation_transparency(self, matrix_scores, matrix_bands, feature_scores,
                                           base_7d_score, ability_score, grade,
                                           feature_notes=None, wet_form_feature=0.0,
                                           class_proof_feature=0.0, full_time_speed_feature=0.0,
                                           draw_feature=0.0):
        """Generate the six-dimension ranking walkthrough.

        ``base_7d_score`` is retained as a legacy archive field name.  The live
        ranking registry has six dimensions; ``form_line`` is report-only.
        """
        # 舊「核心/半核心/輔助」角色標籤已死（同實際權重脫節，輸出表亦唔再印）；
        # 直接用 _matrix_label ＋ 實際權重，權重百分比先係唯一真相。
        dims = [(key, self._matrix_label(key), float(MATRIX_WEIGHTS.get(key, 0.0))) for key in MATRIX_WEIGHTS]
        rows = []
        lines = []
        weighted_sum = 0.0
        for key, label, weight in dims:
            raw_score = float(matrix_scores.get(key, 60))
            band = matrix_bands.get(key, "➖")
            contribution = round((raw_score - 60.0) * weight, 2)
            weighted_sum += contribution
            rows.append({"key": key, "label": label, "score": round(raw_score, 2),
                         "weight": weight, "contribution": contribution, "band": band})
            # 拿走 [核心/半核心/輔助] 標籤：權重百分比已經表達咗重要性，標籤多餘。
            lines.append(f"| {label} | {raw_score:.1f} | {weight:.4f} | {contribution:+.2f} | {band} |")
        table = "\n".join([
            "| 維度 | 得分 | 合成係數 | 相對60分的貢獻 | 判定 |",
            "|:---|---:|---:|---:|:---:|",
            *lines,
        ])
        summary = (
            f"{table}\n\n"
            f"**→ 60 ＋ 各項貢獻 = {base_7d_score:.2f} 分；"
            f"濕地往績調整 {float(wet_form_feature):+.2f}；"
            f"高班實績證明 {float(class_proof_feature):+.2f}；"
            f"逐駒全程速度 {float(full_time_speed_feature):+.4f}；"
            f"大場次檔位 {float(draw_feature):+.2f}；"
            f"綜合戰力分 = {ability_score:.2f} 分 → Grade = [{grade}]**"
        )
        # 有計但唔直接入六維公式嘅分數 — 一併展示，唔收埋
        ref_bits = []
        for ref_key, ref_label in (("distance_score", "路程分"), ("confidence_score", "信心分")):
            val = feature_scores.get(ref_key)
            if isinstance(val, (int, float)):
                ref_bits.append(f"{ref_label} {float(val):.1f}")

        # 備戰完整度分 2026-08-21 實測（300 場）：場內 SD **0.89**，19% 嘅馬恰好 60.0。
        # 佢自己每項調整只有 ±0.3..±2.0 分，而 band 界線喺 55 / 70 —— 即係呢個數字
        # 數學上永遠出唔到 ➖ 以外，印出嚟等於冇資訊。但佢個 note（「近績有獸醫/
        # 健康疑點」「久休 N 日而缺少試閘時間支撐」）係真有料嘅。
        # 所以：唔再印個無意義嘅數，改為只喺真有訊號觸發時出佢講咗咩。
        health = feature_scores.get("health_score")
        if isinstance(health, (int, float)) and abs(float(health) - 60.0) >= 1.0:
            note = str((feature_notes or {}).get("health_score") or "").strip()
            # note 形如「近績有獸醫/健康疑點；久休 120 日…。健康/備戰分 56.0。」
            # 只要最前面嗰段講原因嘅字，唔要尾巴嗰個分數。
            reason = note.split("。")[0].strip(" ；")
            skip = ("未見明確健康或備戰扣分訊號", "")
            if reason and reason not in skip:
                direction = "⚠️" if float(health) < 60.0 else "＋"
                ref_bits.append(f"備戰 {direction}{reason}")
        if ref_bits:
            from .dimensions import ranking_dimension_numeral
            summary += f"\n**📎 參考分（不直接入{ranking_dimension_numeral(MATRIX_WEIGHTS)}維公式）：** " + "、".join(ref_bits)
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
            "trial_no_recent_top3": "近三課有名次嘅試閘全部未入前三，備戰交代偏弱",
            "surface_transfer_unverified": "近仗包含另一種跑道；草地與合成跑道成績不能直接等同",
        }
        return mapping.get(flag, flag)

    def _clean_identity(self, value):
        return _clean_identity(value)

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
        inferred = self._preparation_cycle().get('label')
        if inferred:
            return inferred
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
    #
    # 2026-09-05 收尾：**token fallback 全部剷走**。2026-07-11 已經宣佈咗「DB 係唯一
    # 真相」，但兩張姓氏 token 名單留咗喺度，而佢哋係 substring 比對。實測 836 場
    # 8,047 個騎手位（`docs/audits/AU_TRACK_JHF_DATA_QUALITY_2026-09-05.md`）：
    #
    #   * DB 只有 59 個騎師 / 56 個練馬師，配對率 20.6% / 16.3% ——
    #     即係「fallback」先係主路徑（79.4% / 83.7%）。
    #   * 190 個位由 token 判 T1，**189 個係錯**：
    #       `Sheridan Clarke` 中 `Clark`（連姓都唔同）、`Shane Bottomley` 中 `Bott`、
    #       `Brad`/`Campbell Rawiller`（真嗰個係 Nash）、`Lachlan`/`Brooke King`、
    #       `Margaret Collett`（真嗰個係 Jason）、`Peter`/`Declan Maher`（真嗰個係 Ciaron）、
    #       `Mitchell Freedman`、`Keith Dryden & Libby Snowden`。
    #   * 而九個 token 入面，三個（McDonald/Rawiller/Berry）本身就同 DB 嘅 T1 重複，
    #     另外六個（Clark/Hyeronimus/Schiller/Lloyd/King/Collett）指向嘅人 **DB 明文
    #     評 T2** —— token 名單係喺度**推翻**佢自己聲明嘅真相來源。練馬師同款。
    #   * 剩返嗰一個真 case（`Paul Snowden`，4 個位）係 DB 別名缺口，已經喺
    #     `AU_Trainer_Ratings.csv` 補一行 alias → `Peter & Paul Snowden`（T1）。
    #
    # 呢個係評估合約第 7 節「正確性修正」：就算績效數字係相反方向，
    # `Sheridan Clarke` 都唔應該因為個姓包住 `Clark` 而變頂級騎師。
    # 唔喺 DB = 唔係 T1；要加人就加落 CSV（有 `canonical_name` 別名機制）。
    def _is_top_jockey(self, jockey: str) -> bool:
        rating = self._jockey_rating_profile(jockey)
        return bool(rating) and str(rating.get("tier")) == "T1"

    def _is_top_trainer(self, trainer: str) -> bool:
        rating = self._trainer_rating_profile(trainer)
        return bool(rating) and str(rating.get("tier")) == "T1"

    # 跑法只有**一個**來源：Sportsbet 逐仗 video/settled 走位證據，經
    # `weighted_au_running_style()` 加權，寫入 `running_style_line`。
    # 2026-09-02 剷走另外三條路，因為佢哋都唔係觀察返嚟嘅跑法：
    #   `race_shape_summary`     —— 舊 Racenet 場面摘要（Racenet 本身已剷走）
    #   `facts_section` token 掃描 —— 由敘述文字撈字，會撈到對手嘅跑法
    #   `tactical_plan.expected_position` —— 我哋自己**推**出嚟嘅（仲溝埋檔位）
    # 多個來源嘅代價唔係「多啲覆蓋」，係「量嘅時候唔知量緊邊個」。
    UNMEASURED_STYLES = ("未知", "多變")

    def _running_style(self):
        text = str(self.data.get("running_style_line") or "").strip()
        if not text or any(token in text for token in self.UNMEASURED_STYLES):
            return ""
        return text

    def _predicted_style(self):
        """Tactical position read (前置／守好位／守中／後上) + the WHY, for the 數據判讀.
        Reference only — never enters the rating matrix. Uses the pre-computed
        running_style_line / tactical_plan; WHY comes from the race scenario."""
        raw = self._running_style()
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
        rows = _record_rows(self.facts_section)
        abroad = _overseas.horse_has_overseas([_overseas.venue_name(cols[3]) for cols in rows])
        for cols in rows:
            entries.append({
                "kind": cols[1],
                # New Facts use HCnn.  Legacy BMnn is deliberately not coerced:
                # handwritten/older rows can genuinely mean a BM race class, so
                # guessing would recreate the same semantic contamination.
                "historical_rating": parse_float(
                    re.sub(r"^HC", "", cols[1], flags=re.I)
                ) if re.fullmatch(r"HC\d+(?:\.\d+)?", cols[1], re.I) else None,
                "date": cols[2],
                "venue": cols[3],
                "distance": cols[4],
                "going": cols[5],
                "barrier": cols[6],
                "placing": cols[7],
                "result_status": "NON_STANDARD" if cols[7] == "非標準賽果" else "",
                "class_move": cols[8],
                "trajectory": cols[9],
                "pi": cols[10] if len(cols) > 10 else "",
                "sectional_quality": cols[11] if len(cols) > 11 else "",
                # `early_pace`（Facts `cols[12]` = 早段步速）2026-09-07 剷走：
                # 嗰欄 73,452 行 0.0% 有值（PF payload 換咗，`Early Runner Pace`
                # 冇咗），而且**零 consumer** —— 全 repo 冇一處讀過呢個 key。
                # 欄位本身留喺 Facts 表，因為下游係位置解析。
                "l600_rt": cols[13] if len(cols) > 13 else "",
                "run_style": cols[14] if len(cols) > 14 else "",
                "consumption": cols[15] if len(cols) > 15 else "",
                "notes": cols[16] if len(cols) > 16 else "",
                "forgiveness": cols[17] if len(cols) > 17 else "",
                "is_trial": "試閘" in cols[1],
                # 馬群大細（2026-07-31）：名次格由 `4 (-12.0L)` 變 `4/6 (-12.0L)`。
                # 舊 meeting 冇 `/N`，`field_size` 就係 None，行為完全不變。
                "field_size": _parse_field_size(cols[7]),
                # 獎金（2026-07-31）：追加喺最後一欄，舊 Facts 冇 → None。
                "prize": _parse_prize(cols[18]) if len(cols) > 18 else None,
                # Sportsbet 原始往績班次（2026-08-25）：保留 raw label；正式排名
                # 只經 locked `proven_class` field-relative overlay 使用，絕不駁入
                # 舊 `entry['class']` multiplier，避免同獎金 proxy 重複計票。
                # EXP-20261102-11：英愛港法 `CLn` 係「1 最高」，先換成澳洲對等標籤。
                "source_race_class": _overseas.normalise_class(
                    cols[19], _overseas.venue_name(cols[3]), abroad) if len(cols) > 19 and cols[19] != "-" else "",
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
        if _surname_token_match(name, ("McEvoy", "Layt", "Bayliss", "Moore", "Roper",
                                       "Costin", "Parr", "Dolan", "Schiller")):
            return 2
        if "(a)" in name or _surname_token_match(name, ("Fitzgerald", "Panya")):
            return 1
        return 0

    def _jockey_change_signal(self):
        signal = str(self.data.get("jockey_change_signal") or "").strip()
        # Facts builder can only compare this horse's historical combinations;
        # its generic "由 X 轉配 Y" / "回配 Y" text does not know the global
        # jockey tiers.  Returning it immediately made the tier upgrade and
        # downgrade branches below unreachable across the 710-race archive.
        # Keep genuinely specific facts, but enrich generic changes here where
        # the ratings DB is available.
        specific_markers = (
            "沿用歷來最佳配搭",
            "沿用上仗騎師",
            "試閘手接手",
            "較合拍騎師",
            "離開已證明配搭",
        )
        if signal and any(marker in signal for marker in specific_markers):
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
            return signal or f"由 {latest_official} 轉配 {current}"
        return signal

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

    def _track_records(self):
        return _track.records(self.data.get("track_stats_line"), self.data.get("going_stats_line"))

    def _meeting_intelligence(self):
        data = self.race_context.get("meeting_intelligence")
        return data if isinstance(data, dict) else {}

    def _track_profile(self):
        data = self.race_context.get("track_profile")
        return data if isinstance(data, dict) else {}

    def _straight_course(self):
        venue = self._meeting_intelligence().get("venue") or self._track_profile().get("venue") or ""
        return _draw.is_straight(venue, self._distance_from_text(self.race_context.get("distance")))

    def _today_going(self):
        going = str(
            self._meeting_intelligence().get("going")
            or self._speed_map_field("going", "track_condition")
            or self.race_context.get("going")
            or ""
        ).strip()
        venue = (self._meeting_intelligence().get("venue")
                 or self._track_profile().get("venue") or "")
        return normalise_synthetic_going(venue, going)

    def _wet_state(self):
        return _track.wet_state(self._today_going())

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
            # ⚠️ 呢個係**全份 profile 文件**嘅 substring 掃描，而場地偏差表係
            # **按 rail position 分行**嘅。Randwick 個表：
            #     True            中性偏公平（前領 ~31%、後追 ~29%）
            #     Rail Out +3~+5  偏利前置
            #     Rail Out +6m+   強烈利前置
            # 引擎唔知今日 rail 喺邊，但掃到 Rail Out 幾行嘅「前置」就把
            # front_bias 設成 True，於是**無論 rail 位置**都報「偏前置場地輪廓」——
            # 同同一份檔案嘅幾何描述（「The Rise 上坡段…強後追型馬受益」）並存，
            # 讀者會見到自相矛盾。2026-08-24 用戶喺 Randwick R1 直接踩到。
            #
            # 收窄做「只認明確講**成個場地**偏前置」嘅講法，並排除條件式行
            # （含 "rail out" / "rail position" 嘅行）同否定式講法。
            # ⚠️ 純顯示：`front_bias` 只餵 `_track_fit_brief`，唔入任何評分。
            "front_bias": _profile_front_bias(bias_text),
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
        if len(parts) <= 1:
            # 淨係得場地名 = 呢個場地冇任何幾何資料。報一個孤零零嘅名等於話
            # 「有資料」，所以直接唔出呢行（`_anchor_lines` 會 drop 空字串）。
            return ""
        return " | ".join(parts)

    def _track_distance_note_brief(self):
        return str(self._track_context().get("distance_note") or "").strip()

    def _track_fit_brief(self):
        context = self._track_context()
        style = self._running_style()
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
        return _track.has_wet_place(self._track_records())

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
            label = self._running_style().strip()
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

    def _preparation_cycle(self):
        cached = getattr(self, '_preparation_cycle_cache', None)
        if cached is None:
            meeting = (self._meeting_intelligence().get('date')
                       or self.race_context.get('date') or '')
            cached = preparation_cycle(self._official_entries(), meeting,
                                       career_starts=self.horse_data.get('career_race_starts'))
            self._preparation_cycle_cache = cached
        return cached

    def _trial_summary_text(self):
        trial_count = int(parse_float(self.data.get("trial_count")) or len(self._trial_places()))
        trial_top3 = int(parse_float(self.data.get("trial_top3_count")) or sum(1 for place in self._trial_places() if place <= 3))
        if trial_count <= 0:
            return ""
        return f"共 {trial_count} 次試閘，其中 {trial_top3} 次跑入前三"

    def _class_move_today(self):
        """上一仗 → **今場** 嘅班次變動；今場或者上一仗冇獎金就係 ""（未知）。

        ⚠️ 唔可以讀 `horse_data["class_move"]`：Facts 賽績表「班次」欄量嘅係
        「上上仗 → 該仗」，`_extract_latest_class_move` 攞最新一行，即係
        「上上仗 → 上一仗」—— 錯位一場。2026-09-09→10-08 實測 1,870 匹（15%）
        因此被寫成「降班」（例：Sir Rupert Clarke Stakes（一級賽）入面上仗跑
        Memsie 嘅馬），其中冇官方評分嗰 366 匹經 rating proxy 食咗 +6。
        今場獎金由 Racecard 標題行（`| $28,000`）嚟；任何一邊冇就係未知 —— 寧願講唔知，都唔好講錯。
        """
        entries = self._official_entries()
        latest_prize = entries[0].get("prize") if entries else None
        return today_class_move(self.race_context.get("prize"), latest_prize)

    def _class_move_display(self):
        class_move = self._class_move_today()
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
        # ⚠️ 入分（跑法穩定性「重複交代獎勵」+2）。「同場同程: 1:」只認啱啱 1 戰、唔理有冇上名 ——
        # 已知怪，但改佢係模型改動，要另行 A/B（EXP-20261103-02 記錄）。
        track_line = str(self.data.get("track_record_line") or "")
        if "同場同程: 1:" in track_line:
            return "同場同程已有直接對位"
        track_stats = self._track_records()["同場"]
        if not track_stats["complete"]:
            return ""  # 截斷紀錄（2026-08 舊 Facts）：同舊 parser 一樣當冇紀錄
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
            # `to_top` keeps the field-minus-horse convention because its label
            # spells the direction out ("較頂磅**輕** X kg").
            "to_top": (max_weight - weight) if max_weight is not None else None,
            # `to_avg` was ALSO field-minus-horse, but it is rendered with a bare
            # signed label ("較場均 +X kg") which reads as the horse's deviation —
            # so every sign was printed backwards.  2026-08-22 Randwick R1 made it
            # self-contradictory on one row: Call Me Sassy carried 52.0kg in a field
            # averaging 56.41kg and topped at 60.0kg, and the report said
            # "較頂磅輕 8.0kg；較場均 **+4.4kg**" — 8kg below the top weight yet
            # somehow 4.4kg above the average.  Gunroom (59.0kg) printed "-2.6kg"
            # when it was carrying 2.59kg MORE than the field.
            # Horse-minus-field, matching `_field_rating_delta` directly below and
            # `to_bottom` in this same dict.  Display-only: the sole consumer is
            # `_field_weight_brief`, and `weight_score` left the ranking matrix on
            # 2026-07-30, so no score moves.
            "to_avg": (weight - avg_weight) if avg_weight is not None else None,
            "to_bottom": (weight - min_weight) if min_weight is not None else None,
        }

    def _weight_allowance_suffix(self):
        """`（見習減 1.5kg，實負 59.5kg）`／`（超磅 0.5kg，實負 53.5kg）`；冇調整回空字串。"""
        allowance = parse_float(self.horse_data.get("jockey_allowance_kg")) or 0.0
        carried = parse_float(self.horse_data.get("carried_weight"))
        if not allowance or carried is None:
            return ""
        label = "見習減" if allowance < 0 else "超磅"
        return f"（{label} {abs(allowance):g}kg，實負 {carried:.1f}kg）"

    def _weight_text(self):
        # `weight` = 分配負磅；騎師調整只喺後綴顯示。
        weight = parse_float(self.horse_data.get("weight"))
        if weight is None:
            return ""
        return f"{weight:.1f}kg{self._weight_allowance_suffix()}"

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
            match = RE_OPP_FOLLOWUP.search(result)
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

    def _latest_run_good(self):
        """上仗跑入場內頭 25%（EXP-20261016-18 R4x）；冇馬匹數就用絕對名次 ≤3。冇上仗 → False。"""
        entries = self._official_entries()
        if not entries:
            return False
        place = parse_placing((entries[0] or {}).get("placing"))
        field = (entries[0] or {}).get("field_size")
        if place is not None and field and field >= 2 and place <= field:
            return (place - 1) / (field - 1) <= 0.25
        return place is not None and place <= 3

    def _proven_z(self):
        summary = self.race_context.get("field_summary") or {}
        return _class.proven_class_z(parse_float(self.data.get("proven_class_raw")),
                                     int(summary.get("proven_class_field_count") or 0),
                                     parse_float(summary.get("proven_class_field_mean")),
                                     parse_float(summary.get("proven_class_field_stdev")))

    def _class_score(self):
        score, adjustments = _class.class_score(
            self._career_starts(), self._latest_run_good(), "降班" in self._class_move_today())
        notes = [factor for _, factor in adjustments]
        self.class_detail = {"base": 60.0, "notes": list(notes),
                             "adjustments": [{"delta": round(d, 2), "factor": f} for d, f in adjustments],
                             "final": round(score, 2)}
        note_text = "；".join(notes) if notes else "班次資料未見鮮明傾向"
        return score, f"{note_text}，級數分 {score:.1f}。", "class_move+record_table+formline_followups"

    def _rating_score(self):
        rating = self._horse_rating()
        field = self._field_summary()
        rated_count = int(field.get("rated_count") or 0)
        rdetail = {"lines": [], "source": ""}
        self.rating_detail = rdetail
        if rating is not None and rated_count >= 2:
            avg_rating = parse_float(field.get("avg_rating"))
            score, adjustment, z_value = _class.official_rating_score(
                rating, avg_rating, parse_float(field.get("rating_stdev")) or 0.0)
            notes = [f"今場官方 rating 為 {rating:.1f}"]
            if avg_rating is not None:
                if z_value is not None:
                    notes.append("高於場均逾一個標準差" if z_value >= 1.0 else "高於場均" if z_value >= 0.4
                                 else "低於場均逾一個標準差" if z_value <= -1.0 else "低於場均" if z_value <= -0.4
                                 else "與場均接近")
                else:
                    delta = rating - avg_rating
                    notes.append("高於場均" if delta > 0.8 else "低於場均" if delta < -0.8 else "與場均接近")
            top3_cutoff = parse_float(field.get("top3_rating_cutoff"))
            if top3_cutoff is not None and rating >= top3_cutoff:
                notes.append("rating 已達場內前三門檻")
            vs = "高過場均" if adjustment > 0.5 else "低過場均" if adjustment < -0.5 else "同場均接近"
            rdetail["source"] = "official"
            rdetail["lines"] = [
                f"官方讓磅分 {rating:.1f}" + (f"，場均 {avg_rating:.1f}" if avg_rating is not None else ""),
                f"{vs} → 對位修正 {adjustment:+.1f} 分（60 為中性）",
            ]
            return score, f"{'；'.join(notes)}，Rating 分 {score:.1f}。", "racecard_rating+field_relative"

        # 冇評分（處女／進口馬），或者場內少過 2 匹有：唔死當中性，用代理（見 class_rating）。
        class_proxy = clip_score(self._class_score()[0])
        weight_proxy, weight_line = self._handicap_weight_proxy()
        mixed = rating is None and rated_count >= 2
        score, kind = _class.proxy_rating_score(class_proxy, weight_proxy, mixed)
        if kind == "weight_only":
            rdetail["source"] = "proxy_weight_only"
            rdetail["lines"] = ["今場其他馬有官方讓磅分，本駒冇", weight_line,
                                f"用負磅代理（同評分同一把尺）{score:.1f}（60 為中性）"]
            return score, f"本駒未有官方讓磅分，改用場內負磅代理 {score:.1f}（同場評分馬同一把尺）。", "weight_proxy_mixed_field"
        if kind == "class_only":
            rdetail["source"] = "proxy"
            if mixed:
                # 定磅／齡磅大賽冇負磅代理，冇評分嗰一兩匹（多數係進口馬）落到呢度（2026-11-02）。
                why = ("場內負磅差太細／資料唔夠，借唔到負磅代理" if self._is_handicap_race()
                       else "定磅／齡磅賽負磅唔反映能力，冇得借負磅代理")
                rdetail["lines"] = [f"今場 {rated_count} 匹有官方讓磅分，本駒冇（多見於進口馬／首戰）", why,
                                    f"改以級數分 {class_proxy:.1f} 作能力代理（唔死當中性）"]
                return score, (f"本駒未有官方讓磅分（同場 {rated_count} 匹有），{why}，"
                               f"改以級數分 {class_proxy:.1f} 作能力代理。"), "class_proxy"
            rdetail["lines"] = ["呢場多數馬未有官方讓磅分（處女／未評分賽事常見）",
                                f"改以級數分 {class_proxy:.1f} 作能力代理（唔死當中性）"]
            return score, f"未有足夠官方讓磅分（多見於處女賽），改以級數分 {class_proxy:.1f} 作能力代理。", "class_proxy"
        rdetail["source"] = "proxy_class_weight"
        rdetail["lines"] = ["呢場多數馬未有官方讓磅分（處女／未評分賽事常見）", f"級數分代理 {class_proxy:.1f}",
                            weight_line, f"兩者各半合成能力代理 {score:.1f}（60 為中性）"]
        return score, (f"未有足夠官方讓磅分（多見於處女賽），改以級數分 {class_proxy:.1f} ＋ 場內負磅代理 "
                       f"{weight_proxy:.1f} 各半合成 {score:.1f}。"), "class_weight_proxy"

    def _handicap_weight_proxy(self):
        """(分數, 說明) 或 (None, "")：讓磅賽先有（負磅由能力定），見 class_rating.weight_proxy。"""
        weight = parse_float(self.horse_data.get("weight"))
        field = self._field_summary()
        avg_weight = parse_float(field.get("avg_weight"))
        score = _class.weight_proxy(self._is_handicap_race(), weight, avg_weight,
                                    parse_float(field.get("weight_stdev")) or 0.0, int(field.get("weighted_count") or 0))
        if score is None:
            return None, ""
        direction = "重過" if weight > avg_weight else "輕過"
        line = (f"場內負磅代理 {score:.1f}：負 {weight:.1f}kg，{direction}場均 "
                f"{abs(weight - avg_weight):.1f}kg（讓磅賽由能力定磅，"
                f"頂磅＝讓磅官評為能力最高）")
        return score, line

    def _pace_figure_score(self):
        """L600 context: field-relative historical-race L600-vs-benchmark.

        Sportsbet values are race-level and identical for runners from the same
        historical race. They describe speed tests faced, not the horse's own
        individual sectional.
        Lower l600_delta (faster than the race benchmark) → higher score. Neutral
        60 when the runner has no PF data or the field has <3 with data (→ this
        component is rank-neutral on no-PF races). scale 20 reproduces the
        validated backtest config. See scoring.MATRIX_WEIGHTS note."""
        pf_agg = (self._pf_metrics() or {}).get("pf_aggregates") or {}
        source = str(pf_agg.get("source") or "unknown")
        detail = {"value": None, "mean": None, "stdev": None, "z": None,
                  "runs": int(pf_agg.get("pf_run_count") or 0), "final": 60.0, "state": ""}
        detail["source"] = source
        detail["trial_runs"] = int(pf_agg.get("trial_run_count") or 0)
        detail["formal_runs"] = int(pf_agg.get("formal_run_count") or 0)
        detail["run_dates"] = list(pf_agg.get("run_dates") or [])
        self.pace_figure_detail = detail
        field = self._field_summary()
        # 優先用個體化 L600（race-level L600 + 本駒喺嗰場輸咗幾多秒）。
        # 場均／場內標準差**一定要**同分子攞同一個量，否則個 z 冇意義。
        # 兩者都齊先用，唔係就原封不動退返 race-level —— 舊 formguide
        # 冇 `margin:` 嘅 2.2% 往績行由呢條路走。
        picked = _speed.choose(
            finite_pf_number(pf_agg.get("own_l600_delta_avg"), "own_l600_delta_avg"),
            int(field.get("own_l600_delta_field_count") or 0),
            finite_pf_number(pf_agg.get("l600_delta_avg"), "l600_delta_avg"),
            int(field.get("l600_delta_field_count") or 0),
        )
        detail["basis"] = picked[0] if picked else "race"
        if picked is None:
            detail["state"] = "no_pf"
            return 60, "無往績賽事 L600 環境數據，L600 環境分中性 60。", "missing_neutral"
        basis, value = picked
        prefix = "own_l600_delta" if basis == "own" else "l600_delta"
        mean = finite_pf_number(field.get(f"{prefix}_field_mean"), f"{prefix}_field_mean")
        stdev = finite_pf_number(field.get(f"{prefix}_field_stdev"), f"{prefix}_field_stdev") or 0.0
        if mean is None or stdev <= 0.0:
            detail["state"] = "no_spread"
            return 60, "同場 L600 環境數據無有效分散，L600 環境分中性處理。", "no_spread"
        z = (float(value) - mean) / stdev
        score = _speed.score(float(value), mean, stdev)
        detail.update({"value": round(float(value), 2), "mean": round(mean, 2),
                       "stdev": round(stdev, 2), "z": round(z, 2),
                       "final": round(score, 1), "state": "ok"})
        # ⚠️ 個分係 **場內相對**（60 − z×20，z 對全場平均），但舊 note 只講絕對值
        # 「快過賽事基準 X 秒」，於是會出現「快過基準 0.94 秒 → 45.4 分」呢種
        # 睇落自相矛盾嘅句子（2026-08-01 Rosehill R5 Horizons 實例）。分數係啱嘅
        # ——嗰場全場都快，佢排第 7 —— 錯嘅係冇講埋同場點比。所以 note 要寫埋
        # 場均同差距，否則一個正確嘅數字會令人以為引擎壞咗。
        direction = "快過" if float(value) < 0 else "慢過"
        field_dir = "快過" if mean < 0 else "慢過"
        gap = float(value) - mean          # >0 = 慢過場均（l600_delta 越細越快）
        rel = "慢過" if gap > 0 else "快過"
        if source == "sportsbet_race_context" and basis == "own":
            # own = 賽事 L600 對基準 + 本駒輸距 × 0.17 秒（speed.run_values）；即係「嗰場跑得幾快」
            # 加「本駒輸幾多」。唔係本駒實測末段 —— 實測末段越準預測越差（EXP-20261101-40／42）。
            note = (f"近{detail['runs']}場本駒末段估算（近期加權）{direction}基準 "
                    f"{abs(float(value)):.2f} 秒；同場平均{field_dir}基準 {abs(mean):.2f} 秒，"
                    f"即係{rel}今場馬匹平均 {abs(gap):.2f} 秒（估算＝賽事 L600 對基準＋輸距×0.17 秒）；"
                    f"L600 環境分 {score:.1f}。")
        elif source == "sportsbet_race_context":
            note = (f"近{detail['runs']}場所在賽事 L600（近期加權）{direction}基準 "
                    f"{abs(float(value)):.2f} 秒；同場平均{field_dir}基準 {abs(mean):.2f} 秒，"
                    f"即係其往績速度環境{rel}今場馬匹平均 {abs(gap):.2f} 秒；"
                    "同場有輸距嘅馬少過三匹，用 race-level 賽事數（唔係本駒個體），"
                    f"L600 環境分 {score:.1f}。")
        elif source.startswith("racenet_"):
            note = (f"近{detail['runs']}場逐駒 L600 benchmark 近期加權平均{direction}基準 "
                    f"{abs(float(value)):.2f} 秒；同場平均{field_dir}基準 {abs(mean):.2f} 秒，"
                    f"即係本駒個體 benchmark {rel}場均 {abs(gap):.2f} 秒；"
                    f"L600 環境分 {score:.1f}。")
        else:
            note = (f"近{detail['runs']}場 L600 近期加權平均{direction}基準 {abs(float(value)):.2f} 秒；"
                    f"來源語意未明，唔當作逐駒實測；L600 環境分 {score:.1f}。")
        if detail["trial_runs"]:
            note += (f" 來源含 {detail['trial_runs']} 課試閘、{detail['formal_runs']} 場正式賽；"
                     f"PF 日期：{', '.join(detail['run_dates'])}。")
        if detail["runs"] < 3:
            note += " 少於三次 PF 證據，單次數值不代表穩定速度。"
        return score, note, "pf_l600_delta_field_relative"

    def _is_handicap_race(self):
        """賽事名明確係讓磅賽先返 True（EXP-20261028-12，§7 正確性修正）。

        負磅只有喺讓磅賽先係「讓磅官按能力派磅」。舊版反過嚟只認定磅字眼
        （`maiden plate`／`wfa`／`sw`），淨係寫 PLATE／QUALITY／STAKES／MAIDEN 嘅場
        全部漏網，照用負磅代理同寫「頂磅＝讓磅官評為能力最高」—— 但嗰啲場嘅負磅
        係年齡同性別定，唔係能力（語料 1,265 匹中招，負磅代理喺嗰批場 AUC 0.511）。
        而家正面認讓磅；認唔到（包括賽事名空白）一律唔當讓磅。賽事名約 45 字截斷
        （「MAIDEN HANDI」「CG&E MAIDEN HA」），尾字係 handicap 前綴都算。
        """
        return _is_handicap_title(self._race_class_text())

    def _weight_score(self):
        """顯示用（2026-07-30 退出排名；評分已經包含負磅嘅能力訊號，2026-11-02 第三次重測確認）。"""
        weight = parse_float(self.horse_data.get("weight"))
        move = self._class_move_display()
        score, notes = _class.weight_score(weight, self._is_handicap_race(), "降班" in move, "升班" in move)
        self.weight_detail = {"base": 60.0, "weight": round(float(weight), 1) if weight is not None else None,
                              "notes": list(notes), "final": round(score, 2)}
        if weight is None:
            return score, "負磅資料不足，負磅分中性處理。", "missing_neutral"
        if weight >= 60.0 and self._is_handicap_race():
            self.risk_flags.append("top_weight")
        note_text = "；".join(notes) if notes else f"今場負磅 {weight:.1f}kg"
        return score, f"{note_text}，負磅分 {score:.1f}。", "weight+wet_track+class_move"

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
            placing = parse_placing(entry.get("placing"))
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
        """場地分：見 `track_going`。呢度只砌說明。"""
        recs = self._track_records()
        score, same_parts, going_parts = _track.track_score(recs, self._today_going())
        notes = [text for _, text in same_parts]
        tdetail = {"base": _track.NEUTRAL, "final": round(score, 2)}
        if going_parts:
            total = sum(d for d, _ in going_parts)
            sign = "＋" if total >= 0 else "−"
            notes.append(f"地況適應：{'、'.join(text for _, text in going_parts)}（合計 {sign}{abs(total):.1f}）")
            tdetail["going_adjustment"] = round(total, 2)
        # 往績記錄行先：一眼睇到同場、好/軟/重地實績
        rec_bits = [f"{label} {r['starts']}:{r['wins']}-{r['seconds']}-{r['thirds']}"
                    for label, r in recs.items() if r["starts"] and r["complete"]]
        tdetail["notes"] = ([f"往績 {' / '.join(rec_bits)}"] if rec_bits else []) + notes
        self.track_detail = tdetail
        prefix = "；".join(rec_bits) + "；" if rec_bits else ""
        body = f"{prefix}{'；'.join(notes) if notes else '場地資料未見鮮明優劣'}"
        return score, f"{body}。場地分 {score:.1f}。", "track_stats+going_stats+wet_track"

    def _formline_future_wins(self):
        rows = self._formline_rows()
        return sum(
            1 for row in rows
            if (m := RE_OPP_FOLLOWUP.search(row.get("next_result", "")))
            and int(m.group(1)) > 0
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
        # ── 2026-08-02 重建：冇對手線就唔好扮有 ────────────────────────────
        # 舊行為：`_formline_signal()` 喺**冇任何對手線**嘅時候，會去 parse
        # `formline_line` 個文字標題（「強」「極強」…）當作級別。實測 713 場：
        #     valid=0（冇任何對手強度證據）  6,682 匹 **88.5%**
        #         分數 平均 75.76 中位 78.0 範圍 57.0–89.5
        #         場內超額前三率 **+0.0** ← 完全等於隨機
        #     valid>=1（有對手線）             865 匹  11.5%  範圍 53.0–100.0
        # 即係八成半嘅馬帶住一個 32 分闊嘅**純噪音**分佈，而且 79.9% 全樣本
        # 「冇證據但攞到 >70 分」。個 leaf 場內 ρ 得 0.011（12 個 leaf 最差）
        # 就係咁嚟 —— 唔係缺數據，係冇數據嗰批被派咗高分，蓋過咗有數據嗰批。
        #
        # ⚠️ 呢個唔止影響排名（form_line 權重本身係 0）。報告會照樣同用戶講
        # 「賽績線強」，而背後乜證據都冇 —— 就算永遠唔畀權重都要修。
        #
        # 新行為：冇對手強度證據 → 直接坐 60（該批實測超額 +0.0，中性就係啱），
        # 唔再讀文字標題。有證據先至用級別表。下面嘅 bonus 項本身都係證據性嘅
        # （對手其後贏出／升班／頭馬交手），所以照計，令「得少少證據」嘅馬
        # 仍然可以離開 60。
        _support, valid_rows = self._formline_support_summary()
        if valid_rows <= 0:
            signal = "unknown"
            score = 60.0
        else:
            signal = self._formline_signal()
            mapping = {
                "elite": 82.5,
                "strong": 72.0,
                "medium_strong": 66.0,
                "medium": 62.0,
                "medium_weak": 57.0,
                "weak": 53.0,
                "neutral": 58.0,
                "unknown": 60.0,
            }
            score = mapping.get(signal, 60.0)

        future_win_hits = self._formline_future_wins()
        strong_hits = self._formline_strong_opponents()
        followups = self._formline_followup_counts()
        headwinner = self._formline_headwinner()

        if future_win_hits:
            score += min(6, future_win_hits * 5.9)
        if strong_hits:
            score += min(4, strong_hits * 3.3)
        if followups["higher"] > 0:
            score += min(4, followups["higher"] * 2.4)
        if followups["same"] >= 2:
            score += 1.2
        if followups["lower"] >= 3 and followups["higher"] == 0:
            score += -3.6
        if headwinner and any(token in headwinner for token in ("頭馬", "亞軍")):
            score += 1.8

        row_strength_text = " ".join(str(row.get("strength") or "") for row in self._formline_rows())
        has_strong_row = any(token in row_strength_text for token in ("強組", "超強組", "極強組"))
        has_medium_row = "中組" in row_strength_text
        has_weak_row = "弱組" in row_strength_text
        text = str(self.data.get("formline_line") or "")
        if has_strong_row:
            score = max(score, 66.0)
        elif has_weak_row and not has_medium_row:
            score = min(score, 57.0 - 2.0)
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

        recent_text = self.data.get("recent_form")
        recent_format = self.data.get("recent_form_format", "auto")
        if recent_format == "auto":
            decoded = _capture(
                self.facts_section or self.data.get("facts_section", ""),
                r"近績序列解讀: `?([^`\n]+)`?",
            )
            if decoded and decoded.strip() == str(recent_text or "").strip():
                recent_format = "positions"
        recent = parse_recent_finishes(recent_text, source_format=recent_format)
        official = self._official_entries()
        if (official and len(official) >= self._career_starts()
                and all(entry.get("result_status") for entry in official)):
            # Last10 '0' also represents disqualification; it is not proof of
            # tenth place or a large beaten margin when all starts have status.
            recent = None
            detail["recent_result_status"] = "non_standard_only"
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
            if improvement >= 2.0:
                add(w.get("margin_trend_up_bonus", 3.0), "輸距趨勢改善",
                    f"近2仗平均輸距較之前收窄 {improvement:.1f}L")
                notes.append("輸距趨勢改善")
            elif improvement <= -2.0:
                add(w.get("margin_trend_down_pen", -3.0), "輸距趨勢惡化",
                    f"近2仗平均輸距較之前擴大 {abs(improvement):.1f}L")
                notes.append("輸距趨勢惡化")

        # 「跑法連貫獎勵」（2026-07-10 加，w=5.2）2026-09-02 剷走：**佢由來冇 fire 過**。
        # 佢讀 Facts 往績表嘅「走位跑法」欄，而嗰欄嘅來源係逐仗**賽評文字**
        # (`extract_run_profile_from_video`)。Racenet 落畫、轉去 Sportsbet 之後,
        # sportsbetform 嘅表格頁根本冇賽評 —— 抽取層寫死 `Video: / Note: / Stewards:`
        # 三個空欄（實測 60 個 cache 頁 0 個有 stewards/comment 字眼，唔係抽取漏,
        # 係來源冇）。語料庫實測：**26,381 條往績行，走位跑法欄 100% 係 `-`**。
        # 即係話呢個 +5.2 分嘅條件永遠 False。留住佢淨係令人以為「跑法有入分」。
        # 真正嘅走位證據而家喺「跑位軌跡」欄嘅 `S<n>` 起步位（正式賽 56.5% 有），
        # 由 `weighted_au_running_style()` 用；但佢做排名特徵已經過唔到閘
        # （EXP-20260902-02：六個 k 冇一個 5/5 fold）。

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

    def _form_quality_score(self):
        """Dispatcher placeholder: the real leaf needs the final form / PQ leaves,
        so `analyze_horse` overwrites it via `_merged_form_quality`."""
        return 60.0, "近績質素分喺其他 leaf 完成後先計。", "derived_after_context"

    def _trial_speed_score(self):
        """Dispatcher 佔位（真計法喺 `_merged_trial_speed`，要等 field summary）。"""
        return 60.0, "", "trial_speed_placeholder"

    def _merged_trial_speed(self):
        """EXP-20261016-77：試閘個體 L600 場內 z → 60 − 20z；場內有值少過 3 匹或者冇值 → 60。→ (score, note)"""
        raw = trial_speed_raw(self.horse_data)
        field = self._field_summary()
        count = int(field.get("trial_speed_field_count") or 0)
        mean = parse_float(field.get("trial_speed_field_mean"))
        stdev = parse_float(field.get("trial_speed_field_stdev")) or 0.0
        detail = {"raw": None if raw is None else round(raw, 2), "field_count": count,
                  "mean": None if mean is None else round(mean, 2), "stdev": round(stdev, 2),
                  "applies": trial_performance_applies(self.horse_data), "final": 60.0}
        self.trial_speed_detail = detail
        if not detail["applies"]:
            return 60.0, "正式賽已有 6 場或以上，試閘速度唔計（中性 60）。"
        if raw is None or count < 3 or mean is None or stdev <= 0:
            return 60.0, "冇足夠試閘 L600 數據（本駒冇或者同場少過 3 匹），試閘 L600 分中性 60。"
        score = clip_score(60.0 - 20.0 * (raw - mean) / stdev)
        detail.update(z=round((raw - mean) / stdev, 2), final=round(score, 1))
        rel = "快過" if raw < mean else "慢過"
        return score, f"試閘個體 L600 {raw:+.2f} 秒，{rel}同場試閘均值 {mean:+.2f} 秒，試閘 L600 分 {score:.1f}。"

    def _trip_change_adjustment(self, fq, fq_note):
        """大幅增程／縮程 → 近績質素分 −5（`stability.trip_change`）。"""
        trip_runs = self.data.get("form_quality_runs") or []
        last_trip = parse_float(trip_runs[0].get("distance")) if trip_runs else None
        today_trip = self._distance_m()
        delta, change = _stab.trip_change(today_trip, last_trip)
        if not delta:
            return fq, fq_note
        detail = getattr(self, "form_quality_detail", None)
        if isinstance(detail, dict):
            detail["trip_change"] = {"today": today_trip, "last": last_trip, "delta": delta}
        return clip_score(fq + delta), (
            f"{fq_note}今場 {today_trip}m 對上仗 {last_trip:.0f}m 大幅{change}"
            f"（≥{_stab.TRIP_CHANGE_M:.0f}m），近績參考價值打折 {delta:+.0f}。")

    def _overseas_form_quality_proxy(self):
        """英愛法往績為主 → 近績質素分改由官方讓磅分推算（`overseas.py`）；唔適用 → None。"""
        venues = [_overseas.venue_name(e.get("venue")) for e in self._official_entries()[:6]]
        if not _overseas.mostly_europe(venues):
            return None
        rating = self._horse_rating()
        field = self._field_summary()
        avg = parse_float(field.get("avg_rating"))
        sd = parse_float(field.get("rating_stdev")) or 0.0
        if rating is None or int(field.get("rated_count") or 0) < 3 or avg is None or sd < 0.5:
            return None
        z = _overseas.RATING_TO_FORM_QUALITY * (rating - avg) / sd
        score = clip_score(60.0 + 20.0 * z)
        self.form_quality_detail.update(z=round(z, 4), final=round(score, 2), overseas_rating_proxy=True)
        return score, (f"最近往績以英愛法為主（獎金同班次標籤冇得同澳洲比），近績質素改由官方讓磅分 {rating:.0f}"
                       f"（場均 {avg:.1f}）推算：0.43 × 場內評分 z → {score:.1f}。"), "form_quality_overseas_rating_proxy"

    def _merged_form_quality(self, feature_scores):
        """近績質素分：名次同賽事質素合併（EXP-20261016-06）。

        冇最少兩場完整往績、或者全場少過 3 匹有值 → 用返舊 stability 組合
        （0.6 × 近績分 + 0.4 × 表現質素分），排名同上線前一樣。
        """
        form = clip_score(feature_scores.get("form_score", 60))
        quality = clip_score(feature_scores.get("performance_quality_score", 60))
        composite = _stab.composite(form, quality)
        raw = parse_float(self.data.get("form_quality_raw"))
        runs = int(parse_float(self.data.get("form_quality_run_count")) or 0)
        summary = self.race_context.get("field_summary") or {}
        count = int(parse_float(summary.get("form_quality_field_count")) or 0)
        mean = parse_float(summary.get("form_quality_field_mean"))
        stdev = parse_float(summary.get("form_quality_field_stdev")) or 0.0
        self.form_quality_detail = {"raw": raw, "run_count": runs, "field_count": count,
                                    "field_mean": mean, "field_stdev": stdev,
                                    "runs": self.data.get("form_quality_runs") or []}
        proxy = self._overseas_form_quality_proxy()
        if proxy is not None:
            return proxy
        z = _stab.field_z(raw, runs, count, mean, stdev)
        if z is None:
            self.form_quality_detail.update(final=round(composite, 2), fallback="form_and_quality_composite")
            return composite, (f"未有最少兩場完整往績（名次、出馬數、獎金），沿用近績分 {form:.1f} 同"
                               f"表現質素分 {quality:.1f} 嘅組合 {composite:.1f}。"), "form_quality_fallback_composite"
        score = clip_score(60.0 + 20.0 * z)
        self.form_quality_detail.update(z=round(z, 4), final=round(score, 2))
        return score, (f"近 {runs} 場按名次（場內百分位）同賽事獎金級別合併，"
                       f"場內標準分 {score:.1f}。"), "form_quality_field_relative"

    def _performance_quality_score(self):
        raw = parse_float(self.data.get("performance_quality_raw"))
        recovered_score = parse_float(
            self.data.get("sportsbet_performance_quality_score")
        )
        if raw is None and recovered_score is not None:
            run_count = int(parse_float(
                self.data.get("sportsbet_performance_quality_run_count")
            ) or 0)
            runs = self.data.get("sportsbet_performance_quality_runs")
            runs = runs if isinstance(runs, list) else []
            self.performance_quality_detail = {
                "raw": parse_float(
                    self.data.get("sportsbet_performance_quality_raw")
                ),
                "run_count": run_count,
                "runs": runs,
                "source": "sportsbet_complete_form_archive_recovery",
                "field_relative_recovered_score": round(recovered_score, 2),
                "final": round(recovered_score, 2),
            }
            if run_count >= 2:
                return (
                    clip_score(recovered_score),
                    f"舊檔由嚴格早於賽事日嘅 Sportsbet 完整往績恢復，"
                    f"場內標準分 {clip_score(recovered_score):.1f}。",
                    "sportsbet_complete_form_archive_recovery",
                )
        summary = self.race_context.get("field_summary") or {}
        count = int(parse_float(summary.get("performance_quality_field_count")) or 0)
        field_mean = parse_float(summary.get("performance_quality_field_mean"))
        field_stdev = parse_float(summary.get("performance_quality_field_stdev"))
        run_count = int(parse_float(self.data.get("performance_quality_run_count")) or 0)
        run_evidence = self.data.get("performance_quality_runs")
        run_evidence = run_evidence if isinstance(run_evidence, list) else []
        self.performance_quality_detail = {
            "raw": raw,
            "run_count": run_count,
            "runs": run_evidence,
            "field_count": count,
            "field_mean": field_mean,
            "field_stdev": field_stdev,
            "final": None,
        }
        if (
            raw is None
            or run_count < 2
            or count < 3
            or field_mean is None
            or field_stdev is None
            or field_stdev <= 0
        ):
            return 60.0, "完整表現質素樣本不足，稍後沿用跑法穩定性分。", "consistency_fallback"
        z_score = (raw - field_mean) / field_stdev
        score = clip_score(60.0 + 20.0 * z_score)
        self.performance_quality_detail.update(
            {"z_score": round(z_score, 4), "final": round(score, 2)}
        )
        return (
            score,
            f"近 {run_count} 場按輸距及賽事獎金級別校正，場內標準分 {score:.1f}。",
            "class_adjusted_margin_field_relative",
        )

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
            self._current_jockey_history_brief(),
        ):
            if value and str(value).strip() not in {"N/A", "Unknown"}:
                anchors += 1
        # 2026-09-07：錨點由 14 個減到 13 —— `_latest_l600_rt_brief()` 剷走。
        # 佢讀 Facts 往績表嘅 `L600/RT` 欄，而嗰欄喺 **73,452 行入面 0.0% 有值**
        # （836 份 Facts，2026-08-13→09-04）。即係呢個錨點永遠計唔到，
        # 令分母 14 由頭到尾達唔到。同一個 helper 喺下面 `+1` 都係同樣情況。
        # 見 `docs/experiments/EXP-20260907-03-au-confidence-dead-branches.md`。
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
        # `_latest_l600_rt_brief() +1` 同 `_has_last10_warning() -4` 一齊剷走 ——
        # 兩個都**由來冇 fire 過**（`L600/RT` 欄 0.0%、`warning_line` 個 key
        # 由來唔存在），所以呢個改動係**零分數變化**。
        #
        # ⚠️ 下面 `unresolved_forgiveness -1` **冇動，但佢係壞嘅**：Facts 嘅
        # 「寬恕認定」欄 **73,452 行 100% 都係 `[需判定]`**，所以呢個「條件式」
        # 扣分其實**每匹馬都中** —— 即係一個常數 −1，冇任何區分力。
        # 冇喺呢度剷係因為剷走會令**每個顯示嘅信心分 +1**（用戶可見），
        # 而正確做法多數係令「寬恕認定」真係會被判定，唔係刪個罰分。
        # 要獨立一個改動處理。
        # `unresolved_forgiveness -1` 2026-09-08 剷走。「寬恕認定」欄之前
        # **73,452 行 100% 都係 `[需判定]`**（writer 硬寫死），所以呢個「條件式」
        # 扣分每匹馬都中 = 常數 −1、零區分力。Writer 已改寫 `[-]`，而寬恕本身
        # 判唔到（EXP-20260908-01：三個由走位推導嘅規則方向全部相反）。
        # 呢個改動令每個顯示嘅信心分 +1 —— 係常數偏移，唔改相對次序。
        return score, f"可用分析錨點 {anchors}/13，並按 style confidence、正式樣本、jockey history 同 source 校正後，信心分 {clip_score(score):.1f}。", "data_coverage+style_meta+formline+jockey_history"

    def _health_score(self):
        # ⚠️ **呢個 leaf 唯一活住嘅輸入係「距上仗日數」。** 個名同標籤講「健康」，
        # 但 2026-09-07 實測 8,224 匹：分數只有 59 / 60 / 61 三個值，而每一個
        # 都嚟自下面嗰個 spell 分支 —— 冇一個健康分支中過。原因唔係我哋解析失敗，
        # 係**來源根本冇呢啲資料**（`docs/experiments/EXP-20260907-02-...`）：
        #
        #   * `Stewards:` / `Note:` / `Video:` 三個欄各 **21,127 行，0.0% 有內容**
        #     —— Sportsbet 出標籤但唔出內文。
        #   * `warning_line` 個 key **由來唔存在**於 `_data`。
        #   * 獸醫字眼掃描：全語料每一個命中都係**假陽性** —— 馬名同父母名，
        #     例如 `Heart Of Vienna`、`Heartoni`、`Vetoed`、母系 `Cardiac`、
        #     `Lamerican`。真正嘅獸醫記錄係 **0** 條。
        #   * `timing_trial_600m_avg_speed` 100% 有 key、**0% 有值**；Formguide
        #     入面 5,513 條試閘行**冇一條**有 L600/RT 數字。
        #
        # 所以三個警告／獸醫分支同「久休但有試閘時間」嗰條 rescue **全部剷走**：
        # 佢哋由來冇 fire 過，剷走係**零分數變化**（golden bit-identical）。
        #
        # 而且唔剷有實質風險：`warning_text` 原本包住 `gear_line`，而配備抽取
        # 2026-09-07 啱啱由 0% 修到 22.3%（590 種唔同文字）。今日冇一個撞到
        # 獸醫 token（實測 2,351 匹全部乾淨），但將來一個配備名含 `vet` 或
        # `heart` 就會靜靜扣 1.5–2.0 分 —— substring 比對加上活數據 = 地雷。
        #
        # 要重新做一個真嘅健康分，前提係**先有健康數據來源**，唔係改公式。
        score = 60.0
        notes = []

        spell = self._spell_days()
        if 14 <= spell <= 45:
            score += 1.0
            cycle = self._preparation_cycle()
            notes.append(cycle['summary'] if cycle['stage'] in {'second_up', 'third_up'}
                         else f"距上仗 {spell} 日；單憑出賽間隔不能判定復出狀態")
        elif spell > 90:
            score -= 1.0
            notes.append(f"久休 {spell} 日")

        # 2026-09-07：**配備變更唔入分**，兩個分支剷走。
        #
        # 佢哋由來冇 fire 過（`gear_line` 因為 regex 落差全語料 0% 有值，
        # 而 `Blinkers: Yes` 呢個格式根本唔存在），所以剷走係**零分數變化**。
        # 而家 regex 修好咗，如果留住佢哋就會由「一直死」突然變成「配備入分」——
        # 而 EXP-20260826-07 已經明確 REJECT 咗配備做評分輸入：訊號真
        # （除下配備 −3.86pp [−6.94, −0.75]）但同 `form_score` 重複
        # （有變更嘅馬 form 平均 59.83 vs 62.10），四個扣分幅度冇一個過閘。
        #
        # 配備而家淨係出報告（見 renderer 嘅「配備變更」行）。
        # 講返佢真正量嘅嘢 —— 唔好再暗示我哋查過健康。
        note = "；".join(notes) if notes else "出賽間隔喺常規範圍"
        return score, f"{note}。出賽間隔分 {clip_score(score):.1f}。", "spell_only"

    def _advantages(self, feature_scores, matrix_scores):
        # 2026-08-01：門檻統一到 MATRIX_ADVANTAGE_CUTOFF。維度尺正規化之前，
        # 每個維度嘅 spread 差幾倍，所以呢啲 magic number 各自係對住唔同尺磨出嚟
        # ——`jockey_trainer >= 72`（舊上限 73.8）同 `class_weight >= 68`（舊上限
        # 69.5）實際上幾乎永遠唔會 fire。而家七個維度同一把尺，一個門檻就夠。
        cut = MATRIX_ADVANTAGE_CUTOFF
        items = []
        if matrix_scores.get("pace_perf", 60) >= cut:
            if feature_scores["distance_score"] >= 72:
                items.append("曾應付較快末段賽事環境，路程配套亦有支持")
            else:
                items.append("往績速度考驗背景唔差，但唔當成本駒個體末段實測")
        if matrix_scores["jockey_trainer"] >= cut:
            trainer = self._clean_identity(self.horse_data.get("trainer")) or "馬房"
            items.append(f"{trainer} 呢邊嘅部署訊號偏正面，人馬配搭有基本支持")
        if matrix_scores["track"] >= cut:
            items.append("場地或場館適性有實際證據，唔係紙上談兵")
        if matrix_scores["stability"] >= cut:
            items.append("近期交代密度夠，狀態線唔算飄")
        if matrix_scores.get("race_shape", 60) >= cut:
            items.append("檔位同步速形勢配腳，走位有本錢")
        if matrix_scores.get("class_weight", 60) >= cut:
            items.append("班次同負磅未見吃力，發揮門檻唔高")
        if self._forgiveness_count() >= 2:
            items.append("近仗至少有一兩場蝕位或受阻，紙面名次可能低估真身")
        if self._formline_followup_counts()["higher"] > 0:
            items.append("對手後續升班仲交到貨，賽績線唔薄")
        return items[:3] or ["整體結構平均，未見特別爆點，但亦唔算有明顯穿崩位"]

    def _disadvantages(self, feature_scores, matrix_scores):
        # 門檻同 _advantages 一樣統一（見該處註釋）。
        cut = MATRIX_DISADVANTAGE_CUTOFF
        items = []
        if matrix_scores["race_shape"] <= cut:
            items.append("步速配腳未算理想，走位成本可能會先食蝕")
        if matrix_scores.get("class_weight", 60) <= cut:
            items.append("班次或負磅面前仍有壓力，容錯空間唔大")
        if matrix_scores["track"] <= cut:
            items.append("場地適性仍未有清楚支持，轉場條件未必幫到手")
        if matrix_scores.get("pace_perf", 60) <= cut:
            items.append("段速實證偏弱，靠速度取勝嘅路唔通")
        if matrix_scores["stability"] <= cut:
            items.append("近況同穩定性都唔靚，狀態線飄")
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
        cm = self._class_move_today()
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
        """Data-grounded verdict: six ranking dimensions, then actual
        strengths and concerns (reusing the already-specific advantages/disadvantages).
        Drops the generic '做主軸 / 保留型 / 走勢未算鮮明' filler."""
        name = self.horse_data.get("horse_name", "此駒")
        # ``matrix_scores`` also carries report-only ``form_line`` for archive and
        # renderer compatibility.  It must never be described as the strongest or
        # weakest *ranking* dimension now that the live registry is six-dimensional.
        ordered = sorted(
            ((key, matrix_scores.get(key, 60.0)) for key in MATRIX_WEIGHTS),
            key=lambda kv: kv[1],
            reverse=True,
        )
        top_dim = self._matrix_label(ordered[0][0])
        low_dim = self._matrix_label(ordered[-1][0])
        from .dimensions import ranking_dimension_numeral
        sents = [f"{name}今場{ranking_dimension_numeral(MATRIX_WEIGHTS)}個排名維度以{top_dim}（{ordered[0][1]:.0f}）最強、{low_dim}（{ordered[-1][1]:.0f}）最弱。"]
        real_adv = [a for a in (advantages or []) if "整體結構平均" not in a]
        real_dis = [d for d in (disadvantages or []) if "主要變數仍然係臨場步速" not in d]
        if real_adv:
            sents.append("優勢在於" + "；".join(real_adv[:3]) + "。")
        if real_dis:
            sents.append("要留意" + "；".join(real_dis[:3]) + "。")
        if "surface_transfer_unverified" in self.risk_flags:
            sents.append(self.form_detail.get("surface_transfer_note", ""))
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








































































































































































































































# ── Barrier bias lookup tables ──
# Derived from AU_Racing_Historical_Stats.md venue-level barrier analysis.
# Values represent ability_score adjustment: positive = advantage, negative = disadvantage.
