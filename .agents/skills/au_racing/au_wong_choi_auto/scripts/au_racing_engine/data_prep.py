"""AU 數據準備：讀 Facts／Formguide／Racecard、補欄位、`refresh_*`／`backfill_*`（由 `engine_core.py` 搬出，EXP-20261103-14）。

冇評分邏輯；`engine_core` re-export 晒舊名，舊 import 照用。
"""
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



TRACK_RESOURCE_DIR = Path(__file__).resolve().parents[3] / "au_horse_analyst" / "resources"


TRACK_PROFILE_CACHE: dict[tuple[str, int], dict] = {}


# Historical PF sectionals live beside the archive, newest cache first.
PF_BACKFILL_FILENAMES = ("AU_PF_Historical_Backfill_Cache_2026-07-13.json",)


_PF_BACKFILL_CACHE: dict | None = None


PROVINCIAL_TRACK_FILE = "04b_track_provincial.md"


# 賽道幾何（周長 / 直路 / 方向）由 `fetch_au_track_geometry.py` 生成，兩個來源交叉核對。
# 以前呢啲數喺 `04b_track_*.md` 人手寫，實測 2026-09-02：85 個場地印緊合集檔第一節
# 嘅數，而手寫嗰批本身都有錯（Morphettville 2000/350 → 真值 2339/334）。
# markdown 而家淨係負責文字特性（key_traits / distance_note / going_note）。
TRACK_GEOMETRY_PATH = Path(__file__).resolve().parents[2] / "resources" / "au_track_geometry.json"


TRACK_GEOMETRY_CACHE: dict[str, dict] = {}


# 場地名 → 幾何檔 key。**只准逐字對或者明寫 alias** —— 唔准「斬走尾巴再試」，
# 咁做會令 `Ballarat Synthetic` 攞到草地跑道嘅數，即係我哋啱啱修好嗰種 bug。
TRACK_GEOMETRY_ALIASES = {
    "rosehill": "rosehill-gardens",
    "canterbury-park": "canterbury",
    "newcastle-broadmeadow": "newcastle",
    "broadmeadow": "newcastle",
    "sandown-hillside": "sandown",
    "wagga-wagga": "wagga",
    "belmont-park": "belmont",
    "mount-isa": "mt-isa",
    "mt-gambier": "mount-gambier",
    "devonport-synthetic": "devonport",
    "murray-bdge": "murray-bridge",
    "pioneer-park": "alice-springs",
    # 同一條跑道改咗名／Sportsbet 用另一個名（2026-10-09 月度檢討：呢三個令
    # 32 場冇場地級別）。Kembla Grange 2024 年改名 Illawarra Grange。
    "illawarra-grange": "kembla-grange",
    "randwick-kensington": "kensington",
    "wagga-riverside": "wagga",
}


# 副跑道（合成跑道／內場跑道）幾何同主場唔同，所以**唔可以**做 alias 借幾何；
# 但同一個會場，賽事級別（Metropolitan / Provincial / Country）係同一個。
CLASSIFICATION_PARENT = {
    "ballarat-synthetic": "ballarat",
    "pakenham-synthetic": "pakenham",
    "caulfield-heath": "caulfield",
    "sandown-lakeside": "sandown",
}


def _track_geometry_key(venue: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(venue or "").lower()).strip("-")
    return TRACK_GEOMETRY_ALIASES.get(slug, slug)


def _load_track_geometry(venue: str) -> dict:
    if not TRACK_GEOMETRY_CACHE:
        try:
            payload = json.loads(TRACK_GEOMETRY_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # 讀唔到就當冇幾何。呢度**唔准**靜靜 fall back 去 markdown 嘅數 ——
            # 果批數就係我哋要換走嘅嘢。
            TRACK_GEOMETRY_CACHE["__loaded__"] = {}
            return {}
        TRACK_GEOMETRY_CACHE.update(payload.get("venues") or {})
        TRACK_GEOMETRY_CACHE["__loaded__"] = {}
    row = TRACK_GEOMETRY_CACHE.get(_track_geometry_key(venue)) or {}
    return row if row.get("circumference_m") else {}


VENUE_TRACK_MAP = {
    "randwick": "04b_track_randwick.md",
    "rosehill": "04b_track_rosehill.md",
    "flemington": "04b_track_flemington.md",
    "caulfield": "04b_track_caulfield.md",
    "moonee valley": "04b_track_moonee_valley.md",
    "eagle farm": "04b_track_eagle_farm.md",
    "doomben": "04b_track_doomben.md",
    "warwick farm": "04b_track_warwick_farm.md",
}


HORSE_BLOCK_RE = HORSE_HEADER_RE


_PF_TOKEN_RE = re.compile(r"PF\[(.+?)\]")


_FG_HORSE_HDR_RE = re.compile(
    r"^\[(\d+)\]\s+(.+?)\s+\((\d+)\)\s*$",
    re.M,
)


_FG_JT_LY_RE = re.compile(
    r"(?:^|\|)\s*(T|J):\s*([^(|\n]+?)\s*"
    r"\(LY:\s*(\d+):(\d+)-(\d+)-(\d+)\)",
    re.M,
)


def _pf_num(pattern: str, text: str):
    match = re.search(pattern, text)
    try:
        return float(match.group(1)) if match else None
    except (TypeError, ValueError):
        return None


def _pf_str(pattern: str, text: str):
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def _parse_pf_token(token: str) -> dict:
    return {
        "source": _pf_str(r"Source:\s*([A-Za-z0-9_-]+)", token),
        # Historical field name kept for cache compatibility.  Racenet PF
        # `Last600` is elapsed time at the 600m-to-go marker, not the final
        # 600m split; final split = Runner Time - Last600.
        "l600_time": _pf_num(r"Last600:\s*([-\d.]+)", token),
        "runner_time": _pf_num(r"Runner Time:\s*([-\d.]+)", token),
        "race_time_diff": _pf_num(r"Race Time:\s*([-\d.]+)", token),
        "l800_delta": _pf_num(r"L800 Delta:\s*([-\d.]+)", token),
        "l600_delta": _pf_num(r"L600 Delta:\s*([-\d.]+)", token),
        "l400_delta": _pf_num(r"L400 Delta:\s*([-\d.]+)", token),
        "l200_delta": _pf_num(r"L200 Delta:\s*([-\d.]+)", token),
        "tempo_qrank": _pf_num(r"Tempo QRank:\s*([-\d.]+)", token),
        "rt_rating": _pf_num(r"RT Rating:\s*([-\d.]+)", token),
        "early_runner_pace": _pf_str(
            r"Early Runner Pace:\s*([^.]+)\.",
            token,
        ),
        "early_race_pace": _pf_str(
            r"Early Race Pace:\s*([^.]+)\.",
            token,
        ),
    }


def _formguide_text(facts_path: Path) -> str:
    formguide = facts_path.with_name(
        facts_path.name.replace("Facts", "Formguide")
    )
    if not formguide.exists():
        return ""
    try:
        return formguide.read_text(encoding="utf-8")
    except OSError:
        return ""


# 速度分用嘅兩個逐仗量。`_parse_pf_token` 仲識讀 Racenet 年代其餘十個欄位（舊歸檔），但 2026-08 起
# 0% 有值、冇分數讀佢哋，所以唔再聚合（EXP-20260831-03；速度重建 2026-11-01）。
_PF_SPLIT_KEYS = ("l600_delta", "own_l600_delta")


# 常數住喺 speed.py；呢度保留名俾舊 import 用。
_SEC_PER_LENGTH = _speed.SEC_PER_LENGTH


L600_RECENCY_DECAY = _speed.RECENCY_DECAY


def _pf_aggregates(runs: list[dict], source: str) -> dict:
    """Field-relative PF/L600 inputs. One code path for every PF source
    (live formguide tokens and the historical backfill) so a re-scored archive
    race and a live race are scored by the same arithmetic."""
    if not runs:
        return {}

    # 速度分嘅逐仗值同近期加權全部喺 `speed.py`（唯一計算位置）。own_l600_delta 寫返落每仗
    # 俾顯示用；Racenet `Last600` 唔係末段 split，所以只有 Sportsbet 來源先有 own（見 speed.run_values）。
    for run in runs:
        own, _race = _speed.run_values(run, source)
        if own is not None:
            run["own_l600_delta"] = own

    def values(key):
        return [run[key] for run in runs if run.get(key) is not None]

    aggregates: dict = {}
    # 近期加權平均（EXP-20261101-30 R）；場均／場內 SD 經 field summary 讀同一個值。
    horse = _speed.horse_speed(runs, source)
    if horse.own is not None:
        aggregates["own_l600_delta_avg"] = horse.own
    if horse.race is not None:
        aggregates["l600_delta_avg"] = horse.race
    aggregates["pf_run_count"] = len(runs)
    aggregates["trial_run_count"] = sum(run.get("run_kind") == "trial" for run in runs)
    aggregates["formal_run_count"] = sum(run.get("run_kind") == "formal" for run in runs)
    aggregates["run_dates"] = [run["run_date"] for run in runs if run.get("run_date")]

    aggregates["source"] = source
    aggregates["value_counts"] = {
        key: len(values(key)) for key in _PF_SPLIT_KEYS
    }
    return aggregates


_RUN_POSITION_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)@(800m|400m|Settled)\b")


_RUN_FINISH_RE = re.compile(r"\bfinish:(\d{1,2})/(\d{1,2})\b")


_RUN_WINNING_TIME_RE = re.compile(r"\bWinningTime:(?:(\d+):)?(\d{1,3}(?:\.\d+)?)\b")


_RUN_RACE_L600_RE = re.compile(r"\bRaceL600:(\d{2}(?:\.\d+)?)\b")


_RUN_VENUE_RE = re.compile(r"^\s*(?:[-*]\s*)?(.+?)\s+R\d{1,2}\s+\d{4}-\d{2}-\d{2}\b")


def _formguide_run_context(line: str) -> dict:
    """Ordinal positions, finish/starters, winner's time, race L600 seconds and venue on one form line.

    Recorded on each PF run as data only — no score reads them yet. They are
    what a field-size-aware or speed-aware L600 needs, and positions are ordinal:
    a place at 800m is not a number of lengths behind.
    """
    out: dict = {}
    for place, mark in _RUN_POSITION_RE.findall(line):
        key = {"800m": "pos_800", "400m": "pos_400", "Settled": "pos_settled"}[mark]
        out[key] = int(place)
    finish = _RUN_FINISH_RE.search(line)
    if finish:
        out["finish"], out["starters"] = int(finish.group(1)), int(finish.group(2))
    winning = _RUN_WINNING_TIME_RE.search(line)
    if winning:
        minutes = int(winning.group(1) or 0)
        out["winning_time"] = round(minutes * 60 + float(winning.group(2)), 3)
    race_l600 = _RUN_RACE_L600_RE.search(line)
    if race_l600:
        out["race_l600"] = float(race_l600.group(1))
    venue = _RUN_VENUE_RE.match(line)
    if venue:
        out["venue"] = venue.group(1).strip()
    return out


def _parse_formguide_pf_metrics(
    facts_path: Path,
    *,
    formguide_text: str | None = None,
    target_date: str = "",
) -> dict:
    text = _formguide_text(facts_path) if formguide_text is None else formguide_text
    if not text:
        return {}
    if not target_date:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", _meeting_dir(facts_path).name)
        target_date = date_match.group(1) if date_match else ""
    output: dict = {}
    headers = list(_FG_HORSE_HDR_RE.finditer(text))
    for index, header in enumerate(headers):
        body = text[
            header.end():
            headers[index + 1].start() if index + 1 < len(headers) else len(text)
        ]
        runs = []
        for line in body.splitlines():
            if "ResultStatus:NON_STANDARD" in line:
                continue
            # ⚠️ 試閘 PF **刻意保留**。EXP-20261012-31：剔走試閘（全部，或者只剔走冇正式
            # PF 嘅馬）喺 2,436 場重建語料 Gold −0.37pp／−0.29pp —— 試閘嘅速度環境平均
            # 有預測力，Platinum Card（單場試閘 → 84.1）係個別例外，唔係規律。
            run_date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", line)
            run_date = run_date_match.group(1) if run_date_match else ""
            distance_match = re.search(r"\b(\d{3,4})m\b", line, re.I)
            run_distance = int(distance_match.group(1)) if distance_match else None
            # With a known meeting date, undated PF evidence cannot prove it is
            # pre-race and therefore stays out of ranking.
            if target_date and (not run_date or run_date >= target_date):
                continue
            # 本駒喺嗰場輸幾多馬位。同一條 form line 上面，覆蓋 97.8%
            # （85,939 條 PF 往績行嘅 84,008 條，全語料 1,891 場）。
            # 攞佢係為咗將 race-level 嘅 L600 個體化 —— 見 `_pf_aggregates`。
            # ⚠️ 兩種格式並存，個 `L` 唔可以當必需：
            #   Sportsbet（現行）  `margin:1.14L`
            #   Racenet（≤2026-07）`margin:10.4`     ← 冇 L
            # 硬要 `L` 會靜靜漏走成個 Racenet 年代（2026-05..07 共 326 場，
            # 實測嗰三個月 A/B 全部 +0.0000 就係咁嚟）。單位一樣，都係馬位。
            margin_match = re.search(r"margin:\s*(-?[\d.]+)\s*L?\b", line)
            run_margin = None
            if margin_match:
                try:
                    run_margin = float(margin_match.group(1))
                except ValueError:
                    run_margin = None
            for token in _PF_TOKEN_RE.findall(line):
                parsed = _parse_pf_token(token)
                parsed["run_kind"] = "trial" if ("**(TRIAL)**" in line or re.search(r"\$0(?:\s|$)", line) or re.search(r"Barrier\s*Trial|Jump\s*Out", line, re.I)) else "formal"
                if run_date:
                    parsed["run_date"] = run_date
                if run_distance:
                    parsed["distance"] = run_distance
                if run_margin is not None:
                    parsed["margin"] = run_margin
                parsed.update(_formguide_run_context(line))
                runs.append(parsed)
        marked_sources = {
            str(run.get("source"))
            for run in runs
            if run.get("source")
        }
        if marked_sources == {"sportsbet_race_context"}:
            source = "sportsbet_race_context"
        elif marked_sources:
            source = "mixed_formguide_pf"
        elif "WinOdds:" in text:
            # Compatibility for Sportsbet Formguides written before the
            # explicit PF token source marker was introduced.
            source = "sportsbet_race_context"
        else:
            source = "racenet_formguide_cfb"
        output[header.group(1)] = {
            "pf_runs": runs,
            "pf_aggregates": _pf_aggregates(runs, source),
        }
    return output


def _validate_formguide_horse_alignment(
    text: str,
    horses: dict,
    *,
    source: str,
) -> None:
    """Refuse cross-race/cross-horse Formguide payloads before enrichment.

    Extra Formguide runners are allowed (late scratchings can remove a runner
    from Logic), but every Logic runner must have the same number/name pair.
    """
    headers = list(_FG_HORSE_HDR_RE.finditer(text or ""))
    if not headers:
        return
    by_number: dict[str, str] = {}
    duplicate_numbers = []
    for header in headers:
        number = header.group(1)
        if number in by_number:
            duplicate_numbers.append(number)
        by_number[number] = header.group(2).strip()
    errors = []
    if duplicate_numbers:
        errors.append(f"duplicate Formguide horse numbers {sorted(set(duplicate_numbers))}")
    for number, horse in horses.items():
        key = str(number)
        if key not in by_number:
            errors.append(f"Logic runner #{key} absent from Formguide")
            continue
        logic_name = _normalize_horse_name((horse or {}).get("horse_name"))
        formguide_name = _normalize_horse_name(by_number[key])
        if logic_name != formguide_name:
            errors.append(
                f"#{key} Logic={logic_name or '?'} Formguide={formguide_name or '?'}"
            )
    if errors:
        raise ValueError(
            f"FORMGUIDE ALIGNMENT FAILED in {source}: " + "; ".join(errors)
        )


def _load_pf_backfill(archive_root: Path) -> dict:
    """Historical racenet PuntingForm sectionals for archive meetings.

    Live meetings carry PF inside their own Formguide (`PF[...]` tokens), but
    the scraper only started emitting them around 2026-05 — every earlier
    Formguide has none. The legacy `pace_figure_score` L600 signal was a useful
    leaf (within-race AUC 0.596 where covered, vs 0.615 for the best comparator)
    yet it fell back to a neutral 60 on 67% of archive
    runners, so two thirds of every backtest scored the pace dimension blind.

    The backfill cache closes that: 82 meetings / 728 races / 7,738 runners,
    built pre-race-only with zero leakage rejections. Runs are re-filtered
    against the meeting date on read anyway — a cache is not a licence to skip
    the point-in-time check.
    """
    global _PF_BACKFILL_CACHE
    if _PF_BACKFILL_CACHE is not None:
        return _PF_BACKFILL_CACHE
    _PF_BACKFILL_CACHE = {}
    for name in PF_BACKFILL_FILENAMES:
        path = archive_root / name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        meetings = payload.get("meetings")
        if isinstance(meetings, dict):
            _PF_BACKFILL_CACHE = meetings
            break
    return _PF_BACKFILL_CACHE


def _pf_backfill_for_race(facts_path: Path, race_number: int | None) -> dict:
    """{horse_number: {"pf_runs": [...], "pf_aggregates": {...}}} for one race."""
    meeting_dir = _meeting_dir(facts_path)
    meetings = _load_pf_backfill(meeting_dir.parent)
    meeting = meetings.get(meeting_dir.name)
    if not isinstance(meeting, dict) or not race_number:
        return {}
    races = meeting.get("races")
    race = races.get(str(race_number)) if isinstance(races, dict) else None
    if not isinstance(race, dict):
        return {}
    target_date = str(meeting.get("target_date") or "")
    output: dict = {}
    for horse_number, entry in race.items():
        if not isinstance(entry, dict):
            continue
        runs = [
            run
            for run in (entry.get("runs") or [])
            if isinstance(run, dict)
            # point-in-time: a run on or after race day cannot inform it
            and (not target_date or str(run.get("run_date") or "") < target_date)
        ]
        if not runs:
            continue
        output[str(horse_number)] = {
            "pf_runs": runs,
            "pf_aggregates": _pf_aggregates(runs, "racenet_pf_historical_backfill"),
        }
    return output


def _merge_pf_sources(formguide_pf: dict, backfill_pf: dict) -> dict:
    """Formguide PF wins; backfill only fills runners it left empty."""
    if not backfill_pf:
        return formguide_pf
    merged = dict(formguide_pf)
    for horse_number, entry in backfill_pf.items():
        existing = merged.get(horse_number) or {}
        if not (existing.get("pf_aggregates") or {}).get("pf_run_count"):
            merged[horse_number] = entry
    return merged


PRIZE_COLUMN = 18


_PRIZE_MIN_COLUMNS = 20


_FORMGUIDE_HORSE_HEADER = re.compile(r"^\[(\d+)\]\s+(.+?)\s*\((\d+)\)\s*$", re.M)


def _prize_map_from_formguide(text: str, meeting_date: str) -> dict[str, dict]:
    """{runner number: {(run date, distance m): prize}} for one Formguide file.

    Runs dated on or after the meeting are dropped. 62 rows in the corpus are
    post-race contamination from an archive re-scrape, and a class proxy built
    on those would be reading the future.
    """
    out: dict[str, dict] = {}
    heads = list(_FORMGUIDE_HORSE_HEADER.finditer(text))
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        prizes: dict[tuple[str, int], int] = {}
        for entry in _parse_formguide_entries(text[head.end():end], head.group(2)):
            if entry["is_trial"] or not entry["prize"]:
                continue
            if not entry["date"] or (meeting_date and entry["date"] >= meeting_date):
                continue
            prizes[(entry["date"], int(entry["distance"]))] = int(entry["prize"])
        out[head.group(1)] = prizes
    return out


def _fill_prize_column(facts: str, prizes: dict) -> tuple[str, int]:
    if not prizes:
        return facts, 0
    filled = 0
    lines = []
    for line in facts.splitlines():
        text = line.strip()
        if not text.startswith("|") or "|---" in text:
            lines.append(line)
            continue
        cols = [col.strip() for col in text.strip("|").split("|")]
        if len(cols) < 10 or cols[0] == "#" or "試閘" in cols[1]:
            lines.append(line)
            continue
        distance = re.match(r"(\d+)", cols[4] or "")
        prize = prizes.get((cols[2], int(distance.group(1)))) if distance else None
        if prize is None:
            lines.append(line)
            continue
        while len(cols) < _PRIZE_MIN_COLUMNS:
            cols.append("-")
        if not cols[PRIZE_COLUMN] or cols[PRIZE_COLUMN] == "-":
            cols[PRIZE_COLUMN] = str(prize)
            filled += 1
        lines.append("| " + " | ".join(cols) + " |")
    return "\n".join(lines), filled


def backfill_prize_column(logic_data: dict, meeting_dir: Path | None,
                          race_number, meeting_date: str) -> int:
    """Restore the Facts prize column from the meeting's own Formguide.

    `horse_prize_level()` -- the 班次水平調整 -- reads Facts column 18, which the
    fact writer only started emitting on 2026-07-31. Live meetings have it
    (2026-09 measured 90-95%), but 12 of the corpus's 14 months do not, so any
    harness that replays stored Logic scores the dev window with the adjustment
    silently switched off while production runs with it on. That is a corpus
    gap, not a data gap: the Formguide the Facts were generated from still
    carries a per-run prize for 100% of rows in every month.

    MUST run before the race's `field_summary` is built: the adjustment is own
    level minus the field median, so both sides have to come from the same
    measurement. Returns the number of Facts rows filled; a meeting whose Facts
    already carry the column is left untouched.
    """
    if meeting_dir is None:
        return 0
    # ⚠️ 一定要**逐字**對死場次號。有啲 meeting 除咗逐場檔仲有一個合併檔
    # （`03-28 Race 1-10 Formguide.md`），而 `Race\s*(\d+)` 喺佢度會攞到 `1`。
    # 合併檔入面每一場嘅 `[N]` 編號都由 1 開始重新數，所以撞正揀咗佢，
    # 第 1 場嘅 3 號馬就會靜靜攞到第 2 場 3 號馬嘅獎金。實測 3 場中招。
    guide = None
    for path in sorted(Path(meeting_dir).glob("*Formguide*.md")):
        found = re.search(r"\bRace\s*(\d+)\s+Formguide\b", path.name)
        if found and str(race_number) == found.group(1):
            guide = path
            break
    if guide is None:
        return 0
    try:
        prize_maps = _prize_map_from_formguide(
            guide.read_text(encoding="utf-8", errors="replace"), str(meeting_date or ""))
    except OSError:
        return 0
    filled = 0
    for number, horse in (logic_data.get("horses") or {}).items():
        if not isinstance(horse, dict):
            continue
        data = horse.get("_data")
        if not isinstance(data, dict) or not data.get("facts_section"):
            continue
        updated, count = _fill_prize_column(
            data["facts_section"], prize_maps.get(str(number), {}))
        if count:
            data["facts_section"] = updated
            filled += count
    return filled


def backfill_pf_metrics(logic_data: dict, facts_path: Path | None) -> int:
    """Fill `_data["pf_metrics"]` from the historical PF cache where it is absent.

    MUST run before the race's `field_summary` is built: the L600 signal is a
    field-relative z-score, so a runner's own PF runs are useless unless the
    rest of the field was loaded from the same source. Returns the number of
    runners filled. No-op for live meetings, whose Formguide already carries PF.

    OFF BY DEFAULT — opt in with WC_PF_BACKFILL=1. 2026-08-01, 710 races:
    the backfill lifts PF coverage 32.8% → 94.3% and the backfilled data is
    genuinely predictive (within-race AUC 0.572 on pre-2026-05 meetings vs
    0.599 on live-Formguide meetings, both above every leaf except 近績/穩定),
    yet switching it on makes the model WORSE at the shipped weights:
    gold 37→34, champ −1.55, t3prec −0.94, mrr −0.93, ndcg −0.83
    (good_pos +0.71, winT3 +0.42, blowout −0.98 the only gains).
    A pace_perf matrix-weight sweep under full coverage (0.06/0.09/0.12/0.15/
    0.24/0.30 vs the shipped 0.18831) does not recover it — every level loses
    gold, best case 0.15 is gold −1 with t3prec −0.19 — and neither does
    dropping the text-PI leaf so 段速表現 is pure PF (gold =, good_pos −1.27).
    Read: 0.18831 was fitted while this leaf sat inert on two thirds of
    runners, so un-blinding it over-weights pace against better-calibrated
    signals. Unlocking the coverage needs a full matrix re-fit under full
    coverage, not a coverage flip. Kept wired (not deleted) because the cache
    had already sat unread on disk for three weeks once.

    ── 2026-08-01（同日稍後）喺合併後配置下覆核：**維持 OFF。** ──
    合併咗另一條線嘅改動（馬群大細百分位 base、PI 競爭力封頂、L600 改用平均、
    獎金班次調整、統一上名率取代 jockey/trainer 分）之後重測。

    中途一度以為結論反轉（量到 dev gold 25→28、good_pos +2.97），**嗰個係錯嘅**：
    量度時自己用 `MATRIX_FORMULAS` 砌維度再乘 `MATRIX_WEIGHTS`，**漏咗
    `MATRIX_DISPLAY_GAINS`**。權重數字 2026-08-01 改過，但 w×gain 相對舊權重
    係同一個常數 1.4225（即係排名影響力冇變）—— 唔套 gain 就等於用緊一組
    根本唔存在嘅權重。一定要行 `map_features_to_matrix_scores`。

    改正後（713 場，dev 606 / 未碰過 holdout 107）：
      dev      gold +1、good_pos +0.66、winT3 +0.50、blowout −0.99、compet +0.66
               但 **champ −1.65、good_any2 −0.82**、t3prec −0.22、mrr/ndcg −0.01
      holdout  全部 0.00（嗰批 meeting 本身已有 live PF，backfill 無作用）
      只計生效嘅 466 場：champ −2.15、any2 −1.08、t3prec −0.28
    即係上面原本嘅判斷喺 leaf 重新居中 + 顯示尺正規化之後**仍然成立**。

    亦喺全覆蓋下做過七維權重重新配權（5-fold 閘，候選要每個 fold 都唔差過現狀）：
    搵唔到任何改進。冇 fold 閘嘅純 dev 擬合會俾出 dev +3.28 / holdout −2.04
    （good_any2 −6.54）—— 典型過擬合，唔可信。
    """
    if not facts_path or os.environ.get("WC_PF_BACKFILL", "0") != "1":
        return 0
    horses = logic_data.get("horses")
    if not isinstance(horses, dict):
        return 0
    missing = [
        number
        for number, horse in horses.items()
        if isinstance(horse, dict)
        and not (
            ((horse.get("_data") or {}).get("pf_metrics") or {}).get("pf_aggregates") or {}
        ).get("pf_run_count")
    ]
    if not missing:
        return 0
    race_number = _extract_first_int(
        str((logic_data.get("race_analysis") or {}).get("race_number") or ""),
        r"(\d+)",
    ) or _extract_first_int(Path(facts_path).name, r"Race[_ ]*(\d+)")
    backfill = _pf_backfill_for_race(Path(facts_path), race_number)
    if not backfill:
        return 0
    filled = 0
    for number in missing:
        entry = backfill.get(str(number))
        if not entry:
            continue
        horses[number].setdefault("_data", {})["pf_metrics"] = entry
        filled += 1
    return filled


def refresh_pf_own_l600(logic_data: dict, facts_path: Path | None) -> int:
    """由 Formguide 重新 parse，補返 `own_l600_delta`（cache 版本升級）。→ 補咗幾多匹。

    點解需要：已評分嘅 `Race_*_Logic.json` 入面 `_data["pf_metrics"]` 係**當時**
    嘅 parse 結果，只存咗 race-level `l600_delta`；`margin` 從來冇存過。
    `backfill_pf_metrics` 只填**完全冇** PF 嘅 runner（而且預設 OFF），所以佢
    唔會刷新已有嘅 entry。冇呢個函數，任何讀舊 Logic 嘅 harness
    （`au_dump_engine_leaves` 就係）都攞唔到新欄位，A/B 會同 baseline 一模一樣
    ——「一模一樣」係**冇接通**嘅徵狀，唔係「冇效果」（見 AGENTS.md 第 2 條）。

    有匹配 Formguide 就原子刷新，包括排除試閘後嘅空 payload。
    冇匹配來源先保留舊資料，避免將其他馬嘅數據混入。
    """
    if not facts_path:
        return 0
    horses = logic_data.get("horses")
    if not isinstance(horses, dict):
        return 0
    # Reparse matched runners atomically, including an empty formal PF payload.
    # A cached own delta is not evidence that its source was a formal race.
    parsed = _parse_formguide_pf_metrics(Path(facts_path))
    filled = 0
    for number, horse in horses.items():
        if not isinstance(horse, dict):
            continue
        entry = parsed.get(str(number))
        if entry is None:
            continue
        data = horse.setdefault("_data", {})
        if data.get("pf_metrics") != entry:
            data["pf_metrics"] = entry
            filled += 1
    return filled


def _parse_formguide_jt_ly(
    facts_path: Path,
    *,
    formguide_text: str | None = None,
) -> dict:
    text = _formguide_text(facts_path) if formguide_text is None else formguide_text
    if not text:
        return {}
    output: dict = {}
    headers = list(_FG_HORSE_HDR_RE.finditer(text))
    for index, header in enumerate(headers):
        body = text[
            header.end():
            headers[index + 1].start() if index + 1 < len(headers) else len(text)
        ]
        record: dict = {}
        for match in _FG_JT_LY_RE.finditer(body):
            kind = "trainer_ly" if match.group(1) == "T" else "jockey_ly"
            if kind in record:
                continue
            wins = int(match.group(4))
            seconds = int(match.group(5))
            thirds = int(match.group(6))
            record[kind] = {
                "name": match.group(2).strip(),
                "rides": int(match.group(3)),
                "wins": wins,
                "places": wins + seconds + thirds,
            }
        if record:
            output[header.group(1)] = record
    return output


def _extract_race_number(filename: str, text: str) -> int:
    match = re.search(r"Race[ _](\d+)", filename)
    if match:
        return int(match.group(1))
    match = re.search(r"# .*Race\s+(\d+)", text)
    return int(match.group(1)) if match else 1


def _extract_race_meta(
    facts_path: Path,
    text: str,
) -> tuple[str, str, int]:
    race_number = _extract_race_number(facts_path.name, text)
    distance_match = re.search(r"今仗距離:\s*([0-9]+m)", text)
    distance = distance_match.group(1) if distance_match else ""
    racecards = race_source_candidates(
        facts_path.parent,
        race_number,
        "Racecard",
    )
    race_class = ""
    prize = 0
    if racecards:
        lines = racecards[0].read_text(encoding="utf-8").splitlines()
        if not lines:
            raise ValueError(
                f"Race {race_number} Racecard is empty: {racecards[0].name}"
            )
        header = lines[0]
        class_match = re.search(
            r"\d+m\s*\|\s*([^|$]+?)(?:\s*\||\s*$)",
            header,
        )
        if class_match:
            race_class = class_match.group(1).strip()
        prize_match = re.search(r"\$\s*([0-9,]+)", header)
        if prize_match:
            prize = int(prize_match.group(1).replace(",", ""))
        if not distance:
            distance_match = re.search(r"[—–-]\s*(\d{3,5}m)", header)
            if distance_match:
                distance = distance_match.group(1)
    return race_class, distance, prize


def _extract_career_starts(block: str) -> int:
    line = _capture(block, r"生涯: ([^\n]+)")
    # Sportsbet Racecard writes ``Career: 45 : 5-7-7``.  The old Racecard
    # parser captured only the first token (``45``), while this parser required
    # a colon immediately after it.  That made established horses DEBUT even
    # though the same Facts block contained many official runs.
    match = re.match(r"\s*(\d+)\s*(?::|$)", line or "")
    return int(match.group(1)) if match else 0


def _extract_career_tag(block: str) -> str:
    starts = _extract_career_starts(block)
    if starts == 0:
        return "DEBUT"
    if starts <= 5:
        return "EARLY_CAREER"
    return "ESTABLISHED"


def build_logic_from_facts(facts_path: Path) -> dict:
    """Build one canonical Logic object through the enrichment parser."""
    text = facts_path.read_text(encoding="utf-8")
    race_number = _extract_race_number(facts_path.name, text)
    race_class, distance, prize = _extract_race_meta(facts_path, text)
    matches = validate_facts_horse_alignment(
        text,
        source=facts_path.name,
    )
    logic = {
        "race_analysis": {
            "race_number": race_number,
            "race_class": race_class,
            "distance": distance,
            "prize": prize,
        },
        "horses": {},
    }
    for match in matches:
        horse_number = match.group(1)
        logic["horses"][horse_number] = {
            "horse_name": _clean_identity(match.group(2)),
            "barrier": int(match.group(3)),
            "jockey": _clean_identity(match.group(4)),
            "trainer": _clean_identity(match.group(5)),
            "weight": parse_float(match.group(6)),
            "_data": {},
        }
    return enrich_logic_from_facts(
        logic,
        facts_path,
        facts_text=text,
    )


def enrich_logic_from_facts(
    logic_data: dict,
    facts_path: Path,
    *,
    facts_text: str | None = None,
) -> dict:
    text = (
        facts_path.read_text(encoding="utf-8")
        if facts_text is None
        else facts_text
    )
    race_analysis = logic_data.setdefault("race_analysis", {})
    speed_map = race_analysis.setdefault("speed_map", {})
    auto_speed_map = _parse_speed_map(text)
    race_number = _extract_first_int(str(race_analysis.get("race_number") or facts_path.name), r"(\d+)")
    racecard_profiles = _load_racecard_profiles(facts_path, race_number)
    formguide_text = _formguide_text(facts_path)
    _validate_formguide_horse_alignment(
        formguide_text,
        logic_data.get("horses") or {},
        source=facts_path.name.replace("Facts", "Formguide"),
    )
    formguide_digests = _load_formguide_digests(facts_path, race_number)
    pf_by_horse = _merge_pf_sources(
        _parse_formguide_pf_metrics(
            facts_path,
            formguide_text=formguide_text,
        ),
        _pf_backfill_for_race(facts_path, race_number),
    )
    jt_ly_by_horse = _parse_formguide_jt_ly(
        facts_path,
        formguide_text=formguide_text,
    )
    existing_meeting = race_analysis.get("meeting_intelligence")
    existing_meeting = existing_meeting if isinstance(existing_meeting, dict) else {}
    fresh_meeting = _load_meeting_intelligence(facts_path, race_number)
    # Facts/extractor context is fresher, but may be deliberately run from a
    # temporary work directory whose name is not a meeting identity. Preserve
    # existing non-empty context when the fresh source cannot prove a value.
    meeting_intelligence = dict(existing_meeting)
    for key, value in fresh_meeting.items():
        if value:
            meeting_intelligence[key] = value
    meeting_intelligence["source"] = _merge_sources(
        existing_meeting.get("source"),
        fresh_meeting.get("source"),
    )
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

    validate_facts_horse_alignment(
        text,
        logic_horse_keys=logic_data.get("horses", {}).keys(),
        source=facts_path.name,
    )
    sections = _parse_horse_sections(text)
    for horse_num, horse in logic_data.get("horses", {}).items():
        section = sections.get(str(horse_num), {})
        racecard_profile = racecard_profiles.get(
            _normalize_horse_name(section.get("horse_name") or horse.get("horse_name"))
        ) or {}
        formguide = formguide_digests.get(str(horse_num), {})
        jt_ly = jt_ly_by_horse.get(str(horse_num), {})
        facts_section = section.get("raw_text", "")
        data = horse.setdefault("_data", {})
        data.pop("eem_summary", None)
        data.pop("eem_style", None)
        # A matching Formguide section is an atomic, horse-number keyed source
        # of truth.  Old Logic snapshots were produced before the multi-race
        # scraper identity fix and can contain another race's sire, jockey
        # history, splits and running-position digest under this horse number.
        # Fill-if-missing preserved that cross-horse payload forever.  Replace
        # every digest key together (including meaningful zero/False/empty
        # values); preserve the old payload only when no matching section was
        # parsed at all.
        if formguide:
            data.update(formguide)
        for key in ("jockey_ly", "trainer_ly"):
            if key in jt_ly:
                data[key] = jt_ly[key]
        _merge_prefer_clean(horse, "horse_name", section.get("horse_name"))
        _merge_prefer_clean(horse, "jockey", section.get("jockey"))
        _merge_prefer_clean(horse, "trainer", section.get("trainer"))
        # Early Sportsbet-migration Facts headers did not yet carry trainer or
        # jockey even though the matching Racecard did.  Leaving the stale
        # Logic blanks in place made the score consume correctly linked LY
        # statistics while the analysis displayed ``騎師: - / 練馬師: -`` and
        # disabled name-dependent J/H checks.  Racecard identity is keyed by
        # horse name and is therefore the safe fallback for those archives.
        # 配備變更：純顯示，唔會餵入任何 leaf。見 `_load_racecard_profiles` 註。
        #
        # 2026-09-07：**Formguide 行先，Racecard 做 fallback。** 兩個來源逐匹對過
        # （2,366 個 runner 位，2026-09-01→09-04）：
        #     兩邊都有 434｜只有 Formguide **94**｜只有 Racecard **0**｜都冇 1,838
        # 即係 Racecard 係 Formguide 嘅子集，而且喺兩邊都有嗰 434 匹入面
        # **140 匹（32%）Racecard 截短咗**，只印第一項：
        #     Racecard  `Blinkers FIRST TIME`
        #     Formguide `Blinkers FIRST TIME, Cross-over Nose Band FIRST TIME`
        # 揀長嗰個唔安全（文字長度唔等於完整），所以直接定優先次序：
        # Formguide 有就用 Formguide。報告覆蓋 18.3% → 22.3%。
        _fg_gear = str((horse.get("_data") or {}).get("gear_line") or "").strip()
        if _fg_gear:
            horse["gear_change"] = _fg_gear
        elif racecard_profile.get("gear_change"):
            horse["gear_change"] = racecard_profile["gear_change"]
        _merge_prefer_clean(horse, "jockey", racecard_profile.get("jockey"))
        _merge_prefer_clean(horse, "trainer", racecard_profile.get("trainer"))
        if racecard_profile.get("horse_rating") is not None:
            horse["rating"] = racecard_profile["horse_rating"]
        if section.get("weight") is not None:
            horse["weight"] = section["weight"]
        # `weight` 係**分配負磅**（讓磅官派嘅），讓磅代理同場內負磅統計要嘅就係佢；
        # 實負磅只係報告用。EXP-20261014-02。
        allowance = float(racecard_profile.get("jockey_allowance_kg") or 0.0)
        horse["jockey_allowance_kg"] = allowance
        weight_now = parse_float(horse.get("weight"))
        horse["carried_weight"] = (
            round(weight_now + allowance, 2) if weight_now is not None else None
        )
        if section.get("barrier") is not None:
            horse["barrier"] = section["barrier"]
        horse["tactical_plan"] = _build_tactical_plan(
            int(section.get("barrier") or horse.get("barrier") or 0),
            facts_section,
        )
        if racecard_profile.get("horse_rating") is not None:
            data["horse_rating"] = racecard_profile["horse_rating"]
        # PF is derived from the matching Formguide (or the point-in-time
        # historical cache), so it must be refreshed as one atomic payload.
        # Older Logic snapshots already contain the pre-source/pre-split PF
        # schema; a generic fill-if-missing merge kept that stale payload and
        # silently ignored newly parsed splits on every archive re-score.
        # Preserve the existing value only when neither current source has a
        # matching runner.
        fresh_pf = pf_by_horse.get(str(horse_num))
        if fresh_pf:
            data["pf_metrics"] = fresh_pf
        # A matched Facts horse block is authoritative, just like the matched
        # Formguide digest above.  Fill-if-missing left stale non-empty scalars
        # from an older (and occasionally cross-horse) Logic snapshot while
        # ``facts_section`` itself was refreshed.  Replace only values the
        # current Facts block explicitly proves; preserve legacy values when a
        # field is absent from that historical Facts format.
        _replace_data_value(data, "last10_raw", section.get("last10_raw"))
        _replace_data_value(data, "recent_form", section.get("recent_form"))
        if section.get("recent_form"):
            data["recent_form_format"] = "positions"
        _replace_data_value(data, "career_record_line", section.get("career_line"))
        _replace_data_value(data, "engine_line", section.get("engine_line"))
        _replace_data_value(data, "formline_line", section.get("formline_line"))
        _replace_data_value(data, "consumption_summary", section.get("consumption_summary"))
        _replace_data_value(data, "sectional_trend_line", section.get("sectional_trend_line"))
        _replace_data_value(data, "running_style_line", section.get("running_style_line"))
        _replace_data_value(data, "style_confidence_line", section.get("style_confidence_line"))
        _replace_data_value(data, "engine_type_line", section.get("engine_type_line"))
        _replace_data_value(data, "engine_confidence_line", section.get("engine_confidence_line"))
        _replace_data_value(data, "distance_profile_line", section.get("distance_profile_line"))
        _replace_data_value(data, "target_distance_line", section.get("target_distance_line"))
        _replace_data_value(data, "class_move", section.get("class_move"))
        _replace_data_value(data, "formal_count", section.get("formal_count"))
        _replace_data_value(data, "trial_count", section.get("trial_count"))
        _replace_data_value(data, "trial_top3_count", section.get("trial_top3_count"))
        _replace_data_value(data, "track_record_line", section.get("track_line"))
        _replace_data_value(data, "track_stats_line", section.get("track_stats_line"))
        _replace_data_value(data, "going_stats_line", section.get("going_stats_line"))
        _replace_data_value(data, "stage_stats_line", section.get("stage_stats_line"))
        # The Facts file is the source of truth for the per-horse facts_section.
        # Older Logic files carry a stale pre-realignment blob that the modern
        # feature parsers (賽績線 / 試閘 / L400 / 近況) cannot read, so a
        # fill-if-missing merge would leave form/trial/health blind forever.
        if facts_section:
            data["facts_section"] = facts_section
            horse["career_race_starts"] = _extract_career_starts(
                facts_section
            )
            horse["career_tag"] = _extract_career_tag(facts_section)
        else:
            _merge_data_value(data, "facts_section", facts_section)
        _replace_data_value(data, "last_finish_line", section.get("last_finish_line"))
        _replace_data_value(data, "warning_line", section.get("warning_line"))
        if not str(data.get("current_jockey_history_line") or "").strip():
            current_jockey = _clean_identity(horse.get("jockey"))
            best_jockey = _clean_identity(data.get("best_formal_jockey"))
            if current_jockey:
                if best_jockey and best_jockey != current_jockey:
                    data["current_jockey_history_line"] = f"{current_jockey} 暫未見正式賽或試閘合作紀錄"
                else:
                    data["current_jockey_history_line"] = f"{current_jockey} 暫未見正式賽合作紀錄"
    # 逐匹 loop 之後才做：實際出閘檔位要睇齊成個出賽名單（見
    # `normalise_field_barriers` 嘅實測理由）。戰術敘述由佢一齊重建。
    normalise_field_barriers(logic_data)
    return logic_data


def normalise_field_barriers(logic_data: dict) -> int:
    """把檔位由「原始抽籤號」改成「實際出閘檔位」。

    退出馬之後閘位會重編：實際檔位 = 原始抽籤喺**實際出賽馬**之中嘅密集排位。
    2026-08-31 實測（1,782 場語料 + 261 場 `Race_Results_*.json` 真值）：

      * 現行存檔嘅檔位對真值只有 **47.4%**（2,840 條記錄）
      * 密集排位對真值 **99.3%**
      * **62.1%** 場次有馬嘅原始抽籤號大過今日馬匹數 —— 唔需要真值都證明有退出馬
      * 分桶（`≤4` / `≤8` / `≤12`）錯 **18.0%** 行、影響 **56.5%** 場次，
        而且**單向**：wide→mid 1,359、very_wide→wide 959、mid→inner 798。
        即係引擎系統性地當馬排得比實際更外。

    無條件密集排位係安全嘅（實測性質）：
      * 冇退出馬嘅 676 場（max 檔位 == 馬匹數）—— 密集排位 **100% 係 no-op**
      * 有退出馬嘅 1,106 場 —— 密集排位 **100% 有修正**

    ⚠️ 呢個係場內**保序**變換，所以任何 rank-based 指標（場內 AUC 之類）一定
    一模一樣。佢只經**絕對值**影響嘢：`_pace_map_score` 嘅分桶查表、逐場地檔位
    偏差基準表、`_expected_position_label`（`≤3`）同用戶睇到嘅戰術敘述。
    唔好因為「AUC 一樣」就以為冇接通。

    檔位缺失或者有重複就唔動（冇辦法安全重編）。回傳改咗嘅馬匹數。
    """
    horses = logic_data.get("horses")
    if not isinstance(horses, dict) or len(horses) < 2:
        return 0
    pairs = []
    for num, horse in horses.items():
        if not isinstance(horse, dict):
            return 0
        b = parse_float(horse.get("barrier"))
        if b is None or b <= 0:
            return 0
        pairs.append((num, b))
    if len({b for _, b in pairs}) != len(pairs):
        return 0
    changed = 0
    for rank, (num, _) in enumerate(sorted(pairs, key=lambda t: t[1]), start=1):
        horse = horses[num]
        if parse_float(horse.get("barrier")) == float(rank):
            continue
        horse["barrier"] = rank
        changed += 1
        data = horse.get("_data")
        block = data.get("facts_section", "") if isinstance(data, dict) else ""
        horse["tactical_plan"] = _build_tactical_plan(rank, block)
    return changed


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


def _replace_data_value(target, key, value):
    """Refresh a scalar only when the current source explicitly provides it."""
    if value in (None, ""):
        return
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
        "expected_pace": field("expected_pace") or field("predicted_pace"),
        "pace_confidence": field("pace_confidence"),
        "style_confidence": field("style_confidence"),
        "leaders": _parse_num_list(field("leaders")),
        "pressers": _parse_num_list(field("pressers")),
        "on_pace": _parse_num_list(field("on_pace")),
        "mid_pack": _parse_num_list(field("mid_pack")),
        "closers": _parse_num_list(field("closers")),
        "unclassified": _parse_num_list(field("unclassified")),
        # 三條並排嘅預測起步位（`[馬號:值, ...]`）。EXP-20260902-03：官方 Speedmap
        # 同我哋自己個圖 ρ 只有 +0.005，30/70 混合喺 holdout 贏 +0.063 ✅。
        "official_settle": _parse_num_map(field("official_settle")),
        "our_settle": _parse_num_map(field("our_settle"), as_float=True),
        "blended_settle": _parse_num_map(field("blended_settle")),
        "style_evidence": field("style_evidence"),
        "track_bias": _normalize_speed_map_text(field("track_bias")),
        "tactical_nodes": _normalize_speed_map_text(field("tactical_nodes")),
        "collapse_point": _normalize_speed_map_text(field("collapse_point")),
        "going": field("going"),
        "source": field("source"),
    }


def _parse_num_list(text):
    return [int(x) for x in re.findall(r"\d+", str(text or ""))]


def _parse_num_map(text, as_float=False):
    """`[2:4, 4:1, 7:6.5]` → {2: 4, 4: 1, 7: 6.5}。"""
    out = {}
    for key, value in re.findall(r"(\d+)\s*:\s*([0-9.]+)", str(text or "")):
        out[int(key)] = float(value) if as_float else int(float(value))
    return out


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
            # 2026-09-07：配備變更由 Facts 帶落嚟（`inject_fact_anchors` 由
            # Formguide 嘅 `SportsbetGear:` 行抽）。**純報告欄位，唔入評分** ——
            # EXP-20260826-07 測過同 `form_score` 重複，四個幅度冇一個過閘。
            "gear_changes": _capture(block, r"配備變更: ([^\n]+)"),
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
        if not text.startswith("|") or "|---" in text:
            continue
        cols = [col.strip() for col in text.strip("|").split("|")]
        # Header wording can evolve (e.g. 類型 → 類型／歷史HC); identify it by
        # the stable ordinal marker instead of matching a translated label.
        if not cols or cols[0] == "#":
            continue
        if len(cols) >= 10:
            rows.append(cols)
    return rows


def _parse_field_size(placing_cell) -> int | None:
    """賽績表「名次」格嘅馬群大細：`4/6 (-12.0L)` → 6；`4 (-12.0L)` → None。

    2026-07-31 起 crawler 寫 ` starters:N`，fact-anchor writer 就會嵌成 `名次/馬群`。
    舊 meeting 冇 `/N` → 回 None，所有用到嘅地方都要當「唔知」處理而唔係當 0。
    """
    match = re.match(r"^\s*(\d+)\s*/\s*(\d+)", str(placing_cell or ""))
    if not match:
        return None
    place, field = int(match.group(1)), int(match.group(2))
    # 名次 0 或大過馬群 = 上游污染。名次 0 特別危險：百分位會變負數，
    # 令一匹馬拿到「頭馬」base 100。一律唔採用。
    if field < 2 or place < 1 or place > field:
        return None
    return field


def _parse_prize(cell) -> int | None:
    """賽績表「獎金」格 → 整數（`$40,000` / `40000` → 40000）。冇值 → None。"""
    digits = re.sub(r"[^\d]", "", str(cell or ""))
    if not digits:
        return None
    value = int(digits)
    # 帶外＝上游污染。AU 最細鄉下賽約 $8k，最大 Group 1 約 $10M。
    return value if 1000 <= value <= 20_000_000 else None


def today_class_move(race_prize, latest_run_prize) -> str:
    """上一仗 → 今場 班次變動，同 `inject_fact_anchors.compute_class_change` 同一把尺。

    任何一邊冇獎金 → ""（未知），唔估。
    """
    today = _parse_prize(race_prize)
    last = _parse_prize(latest_run_prize)
    if not today or not last:
        return ""
    ratio = today / last
    if ratio >= 2.5:
        return "↑↑大幅升班"
    if ratio >= 1.3:
        return "↑升班"
    if ratio <= 0.4:
        return "↓↓大幅降班"
    if ratio <= 0.7:
        return "↓降班"
    return "="


def exact_race_class_level(label) -> float | None:
    """Ordered strength for exact Sportsbet historical race-class labels.

    Maiden must be checked before generic handicap: ``MDN HCP`` is still a
    maiden.  The numeric origin is immaterial because the final signal is
    standardised within today's field; the ordering is locked to
    EXP-20260825-03 and must not be retuned against its opened holdout.
    """
    text = re.sub(r"\s+", " ", str(label or "").upper()).strip()
    if not text or any(token in text for token in ("BARRIER TRIAL", "JUMP OUT", "-BT")):
        return None
    if re.search(r"\b(?:GROUP\s*1|G1)\b", text):
        return 100.0
    if re.search(r"\b(?:GROUP\s*2|G2)\b", text):
        return 92.0
    if re.search(r"\b(?:GROUP\s*3|G3)\b", text):
        return 86.0
    if re.search(r"\b(?:LISTED|LR)\b", text):
        return 82.0
    if "MAIDEN" in text or re.search(r"\bMDN\b", text):
        return 56.0
    benchmark = re.search(r"\bBM\s*(\d{2,3})\b", text)
    if benchmark:
        return float(benchmark.group(1))
    class_number = re.search(r"\b(?:CLASS|CL|C)\s*([1-6])\b", text)
    if class_number:
        return 60.0 + 2.0 * int(class_number.group(1))
    if "OPEN" in text:
        return 78.0
    if "HCP" in text or "HANDICAP" in text:
        return 72.0
    return None


def horse_proven_class_level(facts_section) -> float | None:
    """Last-four exact-class strength weighted by achieved finish quality.

    A high-class label is not rewarded by itself: it contributes only in
    proportion to the horse's field-relative finish in that historical run.
    Missing class, placing, or field size stays unknown rather than becoming a
    low score.  This reproduces the locked research ``proven_class`` feature.
    """
    recent = []
    rows = _record_rows(facts_section or "")
    abroad = _overseas.horse_has_overseas([_overseas.venue_name(cols[3]) for cols in rows])
    for cols in rows:
        if "試閘" in cols[1]:
            continue
        source_class = (_overseas.normalise_class(cols[19], _overseas.venue_name(cols[3]), abroad)
                        if len(cols) > 19 and cols[19] != "-" else "")
        level = exact_race_class_level(source_class)
        if level is None:
            continue
        placing = parse_placing(cols[7])
        field_size = _parse_field_size(cols[7])
        quality = None
        if placing is not None and field_size is not None:
            quality = 1.0 - (placing - 1.0) / (field_size - 1.0)
        recent.append((level, quality))
        if len(recent) >= 4:
            break
    if not recent:
        return None
    num = den = 0.0
    for (level, quality), weight in zip(recent, PROVEN_CLASS_DECAY):
        if quality is None:
            continue
        num += weight * (level - 56.0) * quality
        den += weight
    return (num / den) if den else None


# 班次代理：獎金。`_form_score` 個 class_mult 一直係全場統一常數
# （`entry["class"]` 呢個 key 由來冇存在過），即係近績分完全冇班次調整 ——
# 一匹馬喺 $27k 鄉下 Maiden 入前列同另一匹喺 $500k 都會賽入前列，同分。
# 賽績表個「班次」欄 85% 係 fallback "Maiden/SW"（`hc` 缺失）用唔到，
# 但獎金 85,010 個 run 100% 密度，單獨場內 ρ = 0.105、Q1−Q5 10.1pp。
CLASS_PRIZE_DECAY = (1.0, 0.8, 0.6, 0.4)   # 同 _form_score 嘅 decay 一致


# K：每 1.0 log10(獎金) 偏離場內中位數換幾多近績分。A/B（713 場）K=10：
# dev 全部指標變好或平（Gold +2、good_pos +1.32、winT3 +1.65、blowout −1.32）；
# holdout 冇任何指標變差（Gold +1、any2 +0.94、t3prec +0.63、blowout −1.87）。
# K=30 dev 更好（Gold +4）但 holdout champ −1.87 / winT3 −0.93 → 唔採用。
CLASS_PRIZE_K = 10.0


def horse_prize_level(facts_section) -> float | None:
    """decay 加權嘅 log10(近 4 場正式仗獎金)。冇獎金數據 → None。

    Module-level 係為咗令 orchestrator 嘅 `_build_field_summary` 可以喺唔重複
    parse 賽績表嘅情況下算場內中位數（同 pace_figure 拿 l600_delta_field_mean
    同一個 pattern）。
    """
    levels = []
    for cols in _record_rows(facts_section or ""):
        if "試閘" in cols[1]:
            continue
        prize = _parse_prize(cols[18]) if len(cols) > 18 else None
        if prize:
            levels.append(prize)
    if not levels:
        return None
    num = den = 0.0
    for prize, weight in zip(levels[:4], CLASS_PRIZE_DECAY):
        num += math.log10(prize) * weight
        den += weight
    return (num / den) if den else None


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
    """一律回 ""：賽績表「班次」欄係「上上仗 → 該仗」，最新一行即係
    「上上仗 → 上一仗」，唔係今場嘅升降班（錯位一場）。今場班次變動由引擎
    `RacingEngine._class_move_today()` 用今場獎金 vs 上一仗獎金計。
    保留個 key 只係為咗舊 reader 唔炸。"""
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
    latest_consumption = latest_official[15].strip() if latest_official and len(latest_official) > 15 else ""
    latest_notes = latest_official[16].strip() if latest_official and len(latest_official) > 16 else ""
    expected_position = _expected_position_label(style)
    race_scenario = _tactical_scenario_text(expected_position, barrier, latest_consumption, latest_notes)
    return {
        "expected_position": expected_position,
        "race_scenario": race_scenario,
    }


def _expected_position_label(style: str) -> str:
    """由 Sportsbet 加權跑法直接對照。**唔准**自己造一個。

    舊版收三個輸入（加權跑法 + 上仗跑法 + 檔位），冇跑法證據時就按檔位
    寫「守中 / 內欄」或者「守中 / 居中」—— 即係由**檔位**編一個從來冇觀察過嘅
    跑法出嚟，而呢個 label 之後又餵返落 `_running_style()` 做 fallback，
    形成一個自己餵自己嘅圈。2026-09-02 拆咗：一個來源，冇證據就留空。
    """
    text = str(style or "")
    if any(token in text for token in ("前置", "跟前", "居中前", "前領", "領放")):
        return "前置 / 跟前"
    if any(token in text for token in ("後上", "中後", "後追")):
        return "中後 / 後上"
    if "守中" in text:
        return "守中"
    return ""


def _tactical_scenario_text(expected_position: str, barrier: int, consumption: str, notes: str) -> str:
    if not expected_position:
        # 冇跑法證據 —— 只可以講檔位，唔可以講「預計點跑」。
        if barrier <= 3:
            return f"冇走位證據，跑法未定；{barrier}檔起碼有貼欄慳位嘅選擇。"
        if barrier <= 8:
            return "冇走位證據，跑法未定；中檔進退有位，睇出閘先定走位。"
        return "冇走位證據，跑法未定；外檔出閘後要即刻定走位，否則走位成本會較高。"
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


def _meeting_dir(facts_path: Path) -> Path:
    """The folder whose name carries the meeting date and venue.

    Files are always read next to the Facts file, but the meeting's identity is
    its folder name. A pre-race snapshot lives at
    `<meeting>/_prediction_snapshots/<20261014T004339…>/`, whose own name has no
    date — replaying it in place used to blank the meeting date, so
    `refresh_form_quality` dropped every run (0/376 runners on 2026-10-14) and
    the date-gated Formguide / PF parsers lost their cut-off.
    """
    parent = Path(facts_path).parent
    if parent.parent.name == "_prediction_snapshots":
        return parent.parent.parent
    return parent


def _formguide_path_for_facts(facts_path: Path, race_number: int = 0) -> Path | None:
    race_number = race_number or _extract_race_number_from_text_or_name(facts_path.read_text(encoding="utf-8"), facts_path.name)
    matches = sorted(facts_path.parent.glob(f"*Race {race_number} Formguide.md"))
    return matches[0] if matches else None


def _load_formguide_digests(facts_path: Path, race_number: int = 0) -> dict[str, dict]:
    formguide_path = _formguide_path_for_facts(facts_path, race_number)
    if not formguide_path or not formguide_path.exists():
        return {}
    text = formguide_path.read_text(encoding="utf-8")
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", _meeting_dir(facts_path).name)
    meeting_date = date_match.group(1) if date_match else ""
    sections = list(re.finditer(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", text, re.M))
    output: dict[str, dict] = {}
    for idx, match in enumerate(sections):
        start = match.start()
        end = sections[idx + 1].start() if idx + 1 < len(sections) else len(text)
        section = text[start:end]
        digest = _summarize_formguide_section(
            section,
            match.group(2).strip(),
            meeting_date=meeting_date,
        )
        # ── 市場盤（2026-08-26）────────────────────────────────────────────
        # Formguide 每匹馬個 stats 區塊有 `WinOdds:` / `PlcOdds:`（91.6% 覆蓋），
        # 係抓取嗰刻嘅賽前固定盤。以前只當佢做「呢個 Formguide 係 Sportsbet 出品」
        # 嘅來源標記，個**數值**由頭到尾冇用過。
        #
        # ⚠️ **純顯示，唔入排名。** 2026-08-26 實測（EXP-20260826-08）：
        # 賽前 WinOdds 場內 AUC 0.7332，高過現行模型 0.6665；加落 ability
        # 六個 k 全部過閘。但掃混合比重之後最佳 w = **0.0（純市場）** ——
        # 加任何模型比重都令 AUC 單調下跌，即係市場已經完全包含我哋啲訊號。
        # 排名一旦等於市場排名就冇 edge，而 SP 抽水 19.8%。
        # `AGENTS.md` 亦寫住市場價唔准做隱藏 proxy。所以抽咗淨係用嚟：
        #   1) 報告顯示市場點睇
        #   2) dashboard 預填位賠，落注時唔使逐匹打
        for key, field in (("WinOdds", "win_odds"), ("PlcOdds", "place_odds")):
            om = re.search(rf"\b{key}:\s*([\d.]+)", section)
            if om:
                try:
                    value = float(om.group(1))
                except ValueError:
                    continue
                if 1.0 < value < 1000.0:
                    digest[field] = value
        output[match.group(1)] = digest
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


def _summarize_formguide_section(
    section: str,
    horse_name: str,
    *,
    meeting_date: str = "",
) -> dict:
    current_jockey = _capture(section, r"\|\s*J:\s*([^(\n|]+)")
    sire_line = _capture(section, r"Sire:\s*([^|]+)")
    current_market_line = _capture(section, r"^Flucs:\s*(.+)$")
    current_market_values = _parse_fluc_values(current_market_line)
    # 2026-09-07 修：`^Gear:` 由來對唔上。`claw_sportsbet_form` 寫落 Formguide
    # 嘅係 **`SportsbetGear: Changes: ...`**，而 `^` 錨定行頭，所以
    # `SportsbetGear:` 永遠唔會 match `^Gear:` —— `gear_line` 全語料 **0% 有值**
    # （8,224 匹，key 100% 存在）。存檔實測：85.9% Formguide 有呢一行、
    # 21.5% runner 有變更文字，即係數據一直喺度，只係一個 token 落差食咗佢。
    # 見 `docs/audits/AU_TRACK_JHF_DATA_QUALITY_2026-09-05.md`。
    #
    # 兩種前綴都收：Racecard 寫 `Gear:`、Formguide 寫 `SportsbetGear:`。
    gear_line = _capture(section, r"^(?:Sportsbet)?Gear:\s*(?:Changes:)?\s*(.+)$")
    gear_changes = _capture(gear_line, r"Changes:\s*(.+)$") or gear_line
    entries = _parse_formguide_entries(section, horse_name)
    # Apply one point-in-time boundary to every digest consumer. Previously
    # only Performance Quality censored post-target rows, while jockey history,
    # recent shape and timing summaries could ingest a refreshed target result.
    if meeting_date:
        entries = [
            entry for entry in entries
            if str(entry.get("date") or "") < meeting_date
        ]
    official_entries = [entry for entry in entries if not entry["is_trial"]]
    trial_entries = [entry for entry in entries if entry["is_trial"]]
    latest_official = official_entries[0] if official_entries else {}
    latest_trial = trial_entries[0] if trial_entries else {}
    timing_summary = _build_timing_summary(official_entries, trial_entries)
    trial_video_signals = _parse_trial_video_signals(trial_entries)
    recent_shape = _summarize_recent_shape(official_entries)
    performance_quality = _performance_quality_digest(
        official_entries,
        meeting_date=meeting_date,
    )

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
        # 2026-09-07 修：`Blinkers: Yes` 呢個格式**全語料唔存在**。真實文字係
        # `Blinkers FIRST TIME` / `Blinkers AGAIN` / `Blinkers OFF`。
        # 「而家戴住」＝ 有 Blinkers 而且唔係 OFF。
        "has_blinkers": bool(
            re.search(r"\bBlinkers\b(?!\s+OFF)", gear_line, re.IGNORECASE)
        ),
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
        # ⚠️ 2026-10-13：`timing_*` 全部由 Racenet 嘅 `600m / MM:SS.mmm` 分段砌。
        # Sportsbet Formguide 一行都冇呢個格式 → **live 永遠係 None**，所以
        # 用佢嘅三個加分（maiden 試閘 proxy +5、trial_score 快試閘 +4/+2、
        # spell +0.5）live 永遠唔觸發。但 ≤2026-08-01 嘅 68 個舊賽日
        # Formguide 仍有 105,927 條，回放舊語料會觸發 —— 剷走會改舊場次分數，
        # 所以留住。要復活就要新來源（例如 Racing Queensland 逐駒段速）。
        "timing_trial_600m_avg_speed": timing_summary.get("trial_600m_avg_speed"),
        "performance_quality_raw": performance_quality.get("raw"),
        "performance_quality_run_count": performance_quality.get("run_count", 0),
        "performance_quality_source": performance_quality.get("source", ""),
        # Research/audit evidence only.  Persist the exact point-in-time rows
        # behind the digest so future forward tests do not have to reconstruct
        # finish position or margin semantics from refreshed archive pages.
        "performance_quality_runs": performance_quality.get("runs", []),
    }


_PERFORMANCE_QUALITY_RECENCY_WEIGHTS = (1.0, 0.8, 0.6, 0.4)


_PERFORMANCE_QUALITY_CLASS_CREDIT = 4.0


_PERFORMANCE_QUALITY_REFERENCE_PRIZE = 50000.0


def _form_quality_digest(official_entries: list[dict], *, meeting_date: str = "", legacy: bool = False) -> dict:
    """近績質素 raw（`stability.digest`）；往績揀選同表現質素分一樣。"""
    return _stab.digest(_performance_quality_digest(
        official_entries, meeting_date=meeting_date, max_runs=len(_stab.RECENCY_WEIGHTS)).get("runs", []),
        legacy=legacy)


def refresh_trial_runs(logic_data: dict, facts_path: Path | None) -> int:
    """由 Formguide 寫 `fg_trials`（日期、名次、試閘馬匹數）同 `fg_last_formal_date`（EXP-20261016-75 P2）。

    Facts 往績表冇試閘馬匹數，所以要由 Formguide 讀。一定要喺評分之前叫（同 `refresh_form_quality` 一齊）；
    冇對應 Formguide 段落嘅馬寫 None，引擎就跌返 Facts 嘅舊計法。
    """
    horses = logic_data.get("horses") if isinstance(logic_data, dict) else None
    if not isinstance(horses, dict) or not facts_path:
        return 0
    race_number = (logic_data.get("race_analysis") or {}).get("race_number") or 0
    try:
        formguide = _formguide_path_for_facts(Path(facts_path), int(race_number or 0))
    except (OSError, ValueError):
        formguide = None
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", _meeting_dir(Path(facts_path)).name)
    meeting_date = date_match.group(1) if date_match else ""
    found = {}
    if formguide and formguide.exists():
        text = formguide.read_text(encoding="utf-8")
        heads = list(re.finditer(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", text, re.M))
        for i, head in enumerate(heads):
            section = text[head.start(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            entries = [e for e in _parse_formguide_entries(section, head.group(2).strip())
                       if str(e.get("date") or "") < meeting_date]
            found[head.group(1)] = (
                [{"date": e.get("date"), "finish_pos": e.get("finish_pos"), "starters": e.get("starters")}
                 for e in entries if e["is_trial"]],
                max((str(e.get("date") or "") for e in entries if not e["is_trial"]), default=""))
    refreshed = 0
    for number, horse in horses.items():
        if not isinstance(horse, dict):
            continue
        data = horse.setdefault("_data", {})
        trials, last_formal = found.get(str(number), (None, ""))
        data["fg_trials"] = trials
        data["fg_last_formal_date"] = last_formal
        refreshed += trials is not None
    return refreshed


def refresh_form_quality(logic_data: dict, facts_path: Path | None) -> int:
    """Re-derive 近績質素 from the race Formguide for every runner. → runners refreshed.

    Same pattern as `refresh_pf_own_l600`: stored Logic files predate this leaf,
    so live scoring and every replay recompute it from the Formguide. Must run
    before `_build_field_summary` (the leaf is field-relative). Runners with no
    matching Formguide section get the field cleared, never a stale value.
    """
    horses = logic_data.get("horses") if isinstance(logic_data, dict) else None
    if not isinstance(horses, dict) or not facts_path:
        return 0
    race_number = (logic_data.get("race_analysis") or {}).get("race_number") or 0
    try:
        formguide = _formguide_path_for_facts(Path(facts_path), int(race_number or 0))
    except (OSError, ValueError):
        formguide = None
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", _meeting_dir(Path(facts_path)).name)
    meeting_date = date_match.group(1) if date_match else ""
    race_info = logic_data.get("race_analysis") or {}
    mi = race_info.get("meeting_intelligence") if isinstance(race_info.get("meeting_intelligence"), dict) else {}
    sm = race_info.get("speed_map") if isinstance(race_info.get("speed_map"), dict) else {}
    today_going = mi.get("going") or sm.get("going") or sm.get("track_condition") or race_info.get("going") or ""
    legacy = _stab.HEAVY_MODE == "H2" and _stab.is_heavy_going(today_going)  # EXP-20261105-06 研究開關
    digests = {}
    if formguide and formguide.exists():
        text = formguide.read_text(encoding="utf-8")
        heads = list(re.finditer(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", text, re.M))
        for i, head in enumerate(heads):
            section = text[head.start(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            entries = [e for e in _parse_formguide_entries(section, head.group(2).strip())
                       if str(e.get("date") or "") < meeting_date and not e["is_trial"]]
            digests[head.group(1)] = _form_quality_digest(entries, meeting_date=meeting_date, legacy=legacy)
    refreshed = 0
    for number, horse in horses.items():
        if not isinstance(horse, dict):
            continue
        data = horse.setdefault("_data", {})
        digest = digests.get(str(number)) or {}
        data["form_quality_raw"] = digest.get("raw")
        data["form_quality_run_count"] = digest.get("run_count", 0)
        data["form_quality_runs"] = digest.get("runs", [])
        refreshed += digest.get("raw") is not None
    return refreshed


def _performance_quality_digest(
    official_entries: list[dict],
    *,
    meeting_date: str = "",
    max_runs: int | None = None,
) -> dict:
    """Summarize demonstrated performance against race strength.

    The source gate is deliberately structural rather than date-based: a run
    must carry beaten margin, purse and starter count.  That is the complete
    current Sportsbet schema; partial legacy rows cannot silently enter the
    ranking.  At least two comparable runs are required.  Archived pages may
    be refreshed after racing, so same-day/future rows are censored too.
    """
    evidence = []
    for entry in official_entries:
        run_date = str(entry.get("date") or "")
        if meeting_date and (not run_date or run_date >= meeting_date):
            continue
        if entry.get("result_status"):
            continue
        margin = parse_float(entry.get("margin"))
        prize = parse_float(entry.get("prize"))
        starters = parse_float(entry.get("starters"))
        if (
            margin is None
            or entry.get("margin_source") != "header"
            or prize is None
            or prize <= 0
            or not starters
        ):
            continue
        quality = (
            -min(20.0, abs(margin))
            + _PERFORMANCE_QUALITY_CLASS_CREDIT
            * math.log10(prize / _PERFORMANCE_QUALITY_REFERENCE_PRIZE)
        )
        evidence.append({
            "date": run_date,
            "finish_pos": entry.get("finish_pos"),
            "margin": round(float(margin), 4),
            "prize": round(float(prize), 2),
            "starters": int(starters),
            "distance": entry.get("distance"),
            "going": entry.get("going", ""),
            "race_class": entry.get("race_class", ""),
            "venue": entry.get("venue", ""),
            "quality": round(quality, 6),
        })
        if len(evidence) == (max_runs or len(_PERFORMANCE_QUALITY_RECENCY_WEIGHTS)):
            break
    if len(evidence) < 2:
        return {}
    if max_runs:
        # Callers asking for a longer window only want the selected rows.
        return {"runs": evidence}
    weights = _PERFORMANCE_QUALITY_RECENCY_WEIGHTS[: len(evidence)]
    raw = sum(row["quality"] * weight for row, weight in zip(evidence, weights)) / sum(weights)
    return {
        "raw": round(raw, 6),
        "run_count": len(evidence),
        "source": "class_adjusted_margin_complete_formguide",
        "runs": evidence,
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
    # 賽馬時間大部分係 `1:09.230`；舊 regex 硬要兩位分鐘，
    # 只會識 `01:09.230`，令 Sportsbet `Winning Time 1:52.590`、亦即
    # 幾乎所有正式賽事時間都靜靜地變 None。
    match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})\.(\d{3})(?!\d)", text)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2)) + int(match.group(3)) / 1000.0


# `WinningTime:58.420`（<60 秒，冇 `M:`）同 `WinningTime:1:39.310` 兩種寫法。
# 2026-10-13：claw 嘅 `RE_WINNING_TIME` 08-31 已修，但引擎呢邊仍然用
# `_parse_time_to_seconds`（硬要 `M:SS.mmm`），語料 201,421 個 token 有
# 37,902 個（18.8%，全部短途）讀唔到。暫時冇 consumer，所以排名不變。
_WINNING_TIME_TOKEN = re.compile(r"\bWinningTime:(?:(\d{1,2}):)?(\d{1,2})\.(\d{2,3})(?!\d)")


def _parse_winning_time(header: str) -> float | None:
    match = _WINNING_TIME_TOKEN.search(header or "")
    if not match:
        return _parse_time_to_seconds(header)
    minutes = int(match.group(1) or 0)
    frac = match.group(3)
    return minutes * 60 + int(match.group(2)) + int(frac) / (10 ** len(frac))


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
        prize = int(prize_str)
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
        margin_source = ""
        result_status = "NON_STANDARD" if "ResultStatus:NON_STANDARD" in header else ""
        explicit_finish = re.search(r"\bfinish:(\d+)\s*/\s*(\d+)\b", header, re.I)
        if explicit_finish:
            parsed_finish = int(explicit_finish.group(1))
            parsed_field = int(explicit_finish.group(2))
            if parsed_field >= 2 and 1 <= parsed_finish <= parsed_field:
                finish_pos = parsed_finish
        header_margin = re.search(r"\bmargin:([-+]?\d+(?:\.\d+)?)L?\b", header, re.I)
        if header_margin:
            margin = float(header_margin.group(1))
            margin_source = "header"
        if result_line and hn_clean:
            for pos_m in re.finditer(r"(\d+)-([^(]+)\s*\(([^)]+)\)(?:\s+(\d+\.?\d*)L)?", result_line):
                name_in_result = pos_m.group(2).strip().lower()
                if hn_clean[:6] in name_in_result or name_in_result[:6] in hn_clean:
                    result_finish = int(pos_m.group(1))
                    if finish_pos is None:
                        finish_pos = result_finish
                    if margin is None and pos_m.group(4):
                        margin = float(pos_m.group(4))
                        margin_source = "result_line"
                    break
        if result_status:
            finish_pos = margin = None
            margin_source = ""
        # Defensive compatibility for archived Formguides produced before the
        # extractor fix: a positive number beside the winner is winning margin,
        # never the winner's beaten margin.
        if finish_pos == 1 and margin is not None:
            margin = 0.0
        note = _capture(block, r"^Note:\s*(.+)$")
        stewards = _capture(block, r"^Stewards:\s*(.+)$")
        video = _capture(block, r"^Video:\s*(.+)$")
        winner_time = _parse_winning_time(header)
        l600_split = None
        l600_match = re.search(r"\(?600m\s*/\s*(\d{2}:\d{2}\.\d{3})\)?", header)
        if l600_match:
            l600_split = _parse_time_to_seconds(l600_match.group(1))
        entries.append({
            "date": match.group(3),
            "venue": match.group(1),
            "going": match.group(5),
            "race_class": _capture(header, r"(?i)\bRaceClass:\[([^\]]+)\]"),
            "distance": int(match.group(4)[:-1]),
            "is_trial": is_trial,
            "prize": prize,
            "starters": int(starters_match.group(1)) if (
                starters_match := re.search(r"\bstarters:(\d+)\b", header, re.I)
            ) else None,
            "jockey": jockey,
            "flucs": flucs,
            "last_flucs": fluc_values[-1] if fluc_values else "",
            "finish_pos": finish_pos,
            "result_status": result_status,
            "margin": margin,
            "margin_source": margin_source,
            "settled_pos": _parse_running_position(header, "Settled"),
            "pos_1200": _parse_running_position(header, "1200m"),
            "pos_400": _parse_running_position(header, "400m"),
            "pos_800": _parse_running_position(header, "800m"),
            "winner_time_seconds": winner_time,
            "l600_split_seconds": l600_split,
            "note": note,
            "stewards": stewards,
            "video": video,
        })
    return entries


_TRAJ_SETTLED_RE = re.compile(r"^S(\d+)$", re.I)


_TRAJ_FINISH_RE = re.compile(r"^F(\d+)$", re.I)


_TRAJ_MARK_RE = re.compile(r"^(\d+)(?:st|nd|rd|th)(\d+)$")


def parse_trajectory(text) -> dict:
    """`S5→8th5→4th4→F2` → `{"S": 5, 8: 5, 4: 4, "F": 2}`。

    數字前綴係**標記點**（`8th5` = 800m 第 5 位），唔係序數詞。
    """
    out = {}
    for part in str(text or "").split("→"):
        part = part.strip()
        match = _TRAJ_SETTLED_RE.match(part)
        if match:
            out["S"] = int(match.group(1))
            continue
        match = _TRAJ_FINISH_RE.match(part)
        if match:
            out["F"] = int(match.group(1))
            continue
        match = _TRAJ_MARK_RE.match(part)
        if match:
            out[int(match.group(1))] = int(match.group(2))
    return out


def pi_from_trajectory(text) -> tuple[float | None, str]:
    """由走位軌跡算 PI（位置增益），回傳 (值, 用咗邊個標記點)。

    2026-09-01 實測（5,240 條正式往績 + 4,129 條有齊兩個標記點嘅記錄）：

    * `entry["pi"]` 就係 **落後位置 − 終點位置**，8,852 條 **100.0%** 吻合。
      唔係名字暗示嘅 L400（`400m − F` 只對 42.5%）。
    * 覆蓋瓶頸**唔係抽取層**：Sportsbet 頁面只喺 **41.6%** 往績印 `Settled`，
      而我哋抽咗 5,142/5,152（缺口 10 條）。呢個係對方嘅結構限制。
    * 但 `In running` 嘅 **800m** 檢查點覆蓋 71.6%，而佢做 `S` 嘅代理近乎完美：
      偏差平均 **+0.044**（PI 本身 SD 3.751，即 1.2%）、中位 **0.0**、
      **ρ = +0.9688**。所以唔做偏差修正 —— 校一個 0.044 嘅偏移係 fit 噪音。
    * 400m 唔用：偏差 +0.277、SD 1.684，明顯差過 800m。

    效果：正式往績 PI 覆蓋 **47.5% → 61.5%**（補 735 / 5,240 條）。
    """
    marks = parse_trajectory(text)
    finish = marks.get("F")
    if finish is None:
        return None, ""
    if "S" in marks:
        return float(marks["S"] - finish), "settled"
    if 8 in marks:
        return float(marks[8] - finish), "800m"
    return None, ""


def _surface_kind(value):
    value = str(value or "").lower()
    if any(token in value for token in ("synthetic", "polytrack", "tapeta")):
        return "synthetic"
    if any(token in value for token in ("good", "soft", "heavy", "firm", "turf")):
        return "turf"
    return ""


def _parse_running_position(header: str, marker: str) -> int | None:
    """`Nth@400m` 式走位 token。

    歷史：2026-08-31 實測四個 marker 全部 0% 命中（Formguide 當時冇
    `Nth@400m` 寫法）。之後 claw 已經寫出呢個格式 —— 2026-10-13 重量（Ascot
    10-14，539 條非試閘往績）：`pos_800` / `pos_400` **99.8%**、`settled_pos` 70.1%。

    後果**目前限於顯示層**：唯一消費者係 `_entry_shape_bucket` 同
    `_summarize_recent_shape`，而 `_entry_shape_bucket` 有散文關鍵詞 fallback
    （「led」/「midfield」/「rear」），所以 `recent_shape_*` 仍然有 ~70% 有值 ——
    只不過係**關鍵詞推出嚟**，唔係數字位置。再往下只去到
    `_matrix_anchor_lines`（報告）同 `_predicted_style`（餵零權重嘅
    `_pace_map_score`），所以**排名冇受影響**。

    要修就要令 Formguide 帶走位數字。但先睇 EXP-20260822-02：800m→終點嘅
    末段跌位訊號（同一份資訊）已經量過同 REJECT，而 PI 本身係由 `entry["pi"]`
    另一條路嚟（64.5% 覆蓋），唔靠呢四個欄位。即係填返佢哋**唔會**自動變成
    排名收益。見 [[au-written-field-is-not-a-filled-field]]。
    """
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
        intelligence = _parse_meeting_intelligence(
            meeting_path.read_text(encoding="utf-8"),
            _venue_from_folder_name(_meeting_dir(facts_path).name),
        )
    else:
        intelligence = {}
    fallback = _meeting_context_from_extractor_files(facts_path, race_number)
    # Extractor/Racecard context is the later official snapshot.  A MIP may
    # have been generated the evening before (for example Randwick was Soft 6
    # in the package but Soft 7 in the racecard).  Prefer every meaningful
    # current value; keep MIP data only where the extractor says Unknown/blank.
    for key, value in fallback.items():
        if key == "source":
            continue
        clean = str(value or "").strip()
        if clean and clean.lower() not in {"unknown", "n/a", "none", "-"}:
            intelligence[key] = value
    if fallback:
        intelligence["source"] = _merge_sources(intelligence.get("source"), fallback.get("source"))
    if intelligence.get("going"):
        intelligence["going"] = normalize_going(intelligence["going"])
    return intelligence


def _meeting_context_from_extractor_files(facts_path: Path, race_number: int = 0) -> dict:
    folder = facts_path.parent
    context = {
        "venue": _venue_from_folder_name(_meeting_dir(facts_path).name),
        "date": _capture(_meeting_dir(facts_path).name, r"(\d{4}-\d{2}-\d{2})"),
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
    racecards = race_source_candidates(folder, race_number, "Racecard")
    if racecards:
        racecard = racecards[0].read_text(encoding="utf-8")
        meta_line = _first_line_matching(racecard, r"^Track:")
        if meta_line:
            context["going"] = _first_clean(_capture(meta_line, r"Track:\s*([^|]+)"), context["going"])
            context["weather_summary"] = _first_clean(_capture(meta_line, r"Weather:\s*([^|]+)"), context["weather_summary"])
            context["rail_position"] = _first_clean(_capture(meta_line, r"Rail:\s*([^|]+)"), context["rail_position"])
            sources.append(racecards[0].name)

    if context["going"]:
        context["going"] = normalize_going(context["going"])
        context["track_summary"] = context["going"]
    context["source"] = " + ".join(dict.fromkeys(sources + (["folder_name"] if context["venue"] else [])))
    return {key: value for key, value in context.items() if value}


def _venue_from_folder_name(name: str) -> str:
    # Folder-name fallback is only trustworthy when it carries the documented
    # YYYY-MM-DD meeting prefix. Arbitrary temp names such as "local" must not
    # silently become a venue and overwrite a valid Logic context.
    if not re.match(r"^\d{4}-\d{2}-\d{2}(?:[_\s-]|$)", str(name or "")):
        return ""
    return venue_from_meeting_name(name)


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


def _mip_plain_text(text: str) -> str:
    """Remove Markdown decoration without changing section/line structure."""
    return str(text or "").replace("**", "").replace("`", "")


def _mip_field(text: str, *labels: str) -> str:
    """Read a colon field from a line or an inline ``Date | Venue`` header."""
    plain = _mip_plain_text(text)
    for label in labels:
        match = re.search(
            rf"(?mi)(?:^|\|)\s*[-*>]?\s*(?:{label})\s*[:：]\s*([^|\n]+)",
            plain,
        )
        if match:
            return match.group(1).strip().strip(" -*_|")
    return ""


def _mip_section_value(text: str, heading: str) -> str:
    """Return the first content line under a matching Markdown H2 heading."""
    plain = _mip_plain_text(text)
    match = re.search(
        rf"(?ims)^##[^\n]*(?:{heading})[^\n]*\n(.*?)(?=^##|\Z)",
        plain,
    )
    if not match:
        return ""
    for raw in match.group(1).splitlines():
        value = raw.strip().strip(" -*_|")
        if not value:
            continue
        value = re.sub(r"^\[[A-Z_ ]+\]\s*", "", value)
        return value.strip()
    return ""


def _parse_meeting_intelligence(text: str, fallback_venue: str = "") -> dict:
    """Parse every Meeting Intelligence Package format used in the archive.

    The archive contains three real schemas: the original English bilingual
    sections, an inline bold ``Date | Venue`` header with Chinese sections,
    and the current bullet-list generator.  The old parser only understood the
    first one, so Markdown ``**`` leaked into venue identity and 33 races lost
    a known going to ``Unknown`` during runtime refresh.
    """
    plain = _mip_plain_text(text)
    venue = _mip_field(
        plain,
        r"Venue",
        r"賽場",
        r"賽道\s*\(Track\)",
    ) or str(fallback_venue or "").strip()
    date = _mip_field(plain, r"Date", r"日期")
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", date or plain)
    date = date_match.group(0) if date_match else ""

    weather_block = _section_text(
        plain, "## Weather / 天氣狀況", "## Track Condition / 場地狀況"
    )
    track_block = _section_text(
        plain, "## Track Condition / 場地狀況", "## Track Bias / 賽道偏差預測"
    )
    bias_block = _section_text(
        plain, "## Track Bias / 賽道偏差預測", "## Sources / 資料來源"
    )
    source_block = _section_text(plain, "## Sources / 資料來源")

    going = _mip_field(
        plain,
        r"場地狀況\s*\(Track Condition\)",
        r"跑道狀況\s*\(Track Condition\)",
        r"Condition\s*\(跑道\)",
        r"場地",
    )
    if not going:
        going_match = re.search(r"(?mi)^Track condition extracted:\s*([^\n.]+)", plain)
        going = going_match.group(1).strip() if going_match else ""
    if not going:
        going = _mip_section_value(plain, r"官方掛牌\s*\(Official Going\)")
    if not going:
        going = _mip_section_value(plain, r"預測掛牌\s*\(Predicted Going\)")
    english_going = re.search(
        r"\b(Firm|Good|Soft|Heavy|Synthetic|Slow)\s*\d*",
        going,
        re.I,
    )
    if english_going:
        going = english_going.group(0).strip()

    rail = _mip_field(
        plain,
        r"移欄\s*\(Rail\)",
        r"移欄\s*\(Rail Position\)",
        r"Rails?\s*\(欄位\)",
    )
    if not rail:
        rail_match = re.search(r"(?mi)^Rail position .*?:\s*([^\n.]+)", plain)
        rail = rail_match.group(1).strip() if rail_match else ""
    if not rail:
        rail = _mip_section_value(plain, r"欄位\s*\(Rail Position\)")

    weather = _mip_field(plain, r"天氣\s*\(Weather\)", r"Weather")
    if not weather:
        weather = _mip_section_value(plain, r"天氣\s*\(Weather\)")
    if not weather:
        weather = _compact_text(weather_block)

    bias = _mip_field(plain, r"Bias")
    if not bias:
        bias = _mip_field(plain, r"偏差")
    if not bias:
        bias = _mip_section_value(
            plain,
            r"跑道偏差\s*\(Track Bias\)|Track Bias.*偏差",
        )
    if not bias:
        bias = _compact_text(bias_block)

    return {
        "venue": venue,
        "date": date,
        "weather_summary": weather,
        "track_summary": _compact_text(track_block) or going,
        "going": going,
        "rail_position": rail,
        "bias_summary": bias,
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
    dedicated = track_file is not None and track_file.exists()
    if not dedicated:
        fallback = TRACK_RESOURCE_DIR / PROVINCIAL_TRACK_FILE
        track_file = fallback if fallback.exists() else None
    if not track_file or not track_file.exists():
        return {}
    text = track_file.read_text(encoding="utf-8")
    if dedicated:
        # 單場地檔：成份檔案就係嗰個場地，唔好再切 section。個幾何表喺一級標題
        # (`# Randwick 場地特性`) 之下、第一個 `##` 之上，切 section 就會漏咗成個表。
        section = text
    else:
        # 合集檔（provincial）：一定要對到該場地嘅 `## <venue>` 段落先攞得幾何。
        # 對唔到就唔好 fall back 去成份檔 —— 舊版咁做，令 85 個場地靜靜印住
        # 合集第一個場地（Canterbury）嘅 1570m / 280m。冇數據要報冇數據。
        section = _track_venue_section(text, venue)
        if not section:
            # 冇文字特性唔代表冇幾何 —— 84 個場地就係得幾何冇 markdown。
            profile = {
                "venue": venue,
                "key_traits": [],
                "distance_note": "",
                "going_note": "",
                "source_file": "",
            }
            profile.update(_geometry_fields(venue))
            TRACK_PROFILE_CACHE[cache_key] = profile
            return profile
    going_heading = "## 🌧️ 天氣與場地互動 (Track Condition Bias)"
    profile = {
        "venue": venue,
        "key_traits": _extract_track_traits(section),
        "distance_note": _compact_text(_track_distance_note(section, distance_m)),
        "going_note": _compact_text(_section_text(section, going_heading)),
        "source_file": track_file.name,
    }
    profile.update(_geometry_fields(venue))
    TRACK_PROFILE_CACHE[cache_key] = profile
    return profile


def _geometry_fields(venue: str) -> dict:
    """周長 / 直路 / 方向 一律由生成嘅幾何檔嚟，唔再由 markdown 讀。"""
    geometry = _load_track_geometry(venue)
    return {
        "circumference_m": int(geometry.get("circumference_m") or 0),
        "straight_m": int(geometry.get("straight_m") or 0),
        "direction": str(geometry.get("direction") or ""),
        "classification": _track_classification(venue),
        "track_note": str(geometry.get("note") or ""),
        "geometry_sources": list(geometry.get("sources") or []),
    }


# 全場只有合成跑道嘅場地（名入面冇寫 Synthetic 嘅要明列）。Devonport 係 Tapeta。
SYNTHETIC_ONLY_VENUES = {"devonport", "devonport-synthetic"}


def normalise_synthetic_going(venue, going) -> str:
    """合成跑道賽事唔准報草地掛牌。

    Sportsbet 對 Devonport／Pakenham Synthetic 寫 `Track: Good 3`，賽果寫 `Synthetic`
    （2026-09-09→10-08：18 場）。後果係報告「今場掛牌 Good 3」、`_surface_kind` 當草地，
    跨跑道風險標記貼錯馬。只改 Good/Firm/空白：濕地判斷（soft/heavy）同評分完全唔變。
    """
    text = str(going or "").strip()
    slug = re.sub(r"[^a-z0-9]+", "-", str(venue or "").lower()).strip("-")
    synthetic = (any(t in slug for t in ("synthetic", "tapeta", "polytrack"))
                 or slug in SYNTHETIC_ONLY_VENUES)
    if not synthetic or _surface_kind(text) == "synthetic":
        return text
    if text and not re.match(r"(?i)(good|firm)\b", text):
        return text
    return "Synthetic"


def _track_classification(venue: str) -> str:
    """場地級別。唔要求有周長（Caulfield Heath 冇幾何但級別確定），副跑道承繼主場。"""
    _load_track_geometry(venue)  # 確保 cache 已載入
    key = _track_geometry_key(venue)
    for candidate in (key, CLASSIFICATION_PARENT.get(key)):
        row = TRACK_GEOMETRY_CACHE.get(candidate or "") or {}
        if row.get("classification"):
            return str(row["classification"])
    return ""


def _track_venue_section(text: str, venue: str) -> str:
    venue_words = [re.escape(part) for part in re.split(r"\s+", str(venue or "").strip()) if part]
    if not venue_words:
        return ""
    venue_pattern = r"\s+".join(venue_words)
    # 標題行唔可以跨行 —— 舊版用咗 re.S，令 `^##\s+.*<venue>` 個 `.*` 由檔案第一個
    # `##` 一路食落去先撞到場地名，於是每個場地都攞返合集第一節嘅表。
    match = re.search(
        rf"(^\#{{1,3}}[ \t]+[^\n]*{venue_pattern}[^\n]*\n)(.*?)(?=^\#{{1,3}}[ \t]+|\Z)",
        text,
        re.I | re.M | re.S,
    )
    return (match.group(1) + match.group(2)).strip() if match else ""


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


def _distance_to_int(distance: str) -> int:
    match = re.search(r"(\d+)", str(distance or ""))
    return int(match.group(1)) if match else 0


def _extract_first_int(text: str, pattern: str) -> int:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _load_racecard_profiles(facts_path: Path, race_number: int) -> dict[str, dict]:
    if race_number <= 0:
        return {}
    candidates = race_source_candidates(facts_path.parent, race_number, "Racecard")
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
                "horse_rating": (
                    float(meta_match.group("rating"))
                    if meta_match.group("rating") else None
                ),
                "declared_weight": float(meta_match.group("weight")),
                # 騎師負磅調整（有符號：見習減磅負、超磅正）。冇括號 = 0.0 ——
                # 2026-10-14 之前抽嘅 Racecard 一律冇，所以舊檔讀成 0 係**未知**
                # 而唔係「證實冇減磅」。只供顯示；讓磅代理照用分配負磅（見
                # `_handicap_weight_proxy`、EXP-20261014-02）。
                "jockey_allowance_kg": (
                    (-1.0 if meta_match.group("allowance_label") == "Claim" else 1.0)
                    * float(meta_match.group("allowance_kg"))
                    if meta_match.group("allowance_kg") else 0.0
                ),
                "jockey": _clean_identity(meta_match.group("jockey")),
                "trainer": _clean_identity(meta_match.group("trainer")),
            }
            # 配備變更（2026-08-26）：由馬名行向下掃到下一匹馬為止。
            # 只出報告，**唔入排名** —— 實測加落 ability 四個 k 全部跨 0，
            # 而且同 `form_score` 重複（有配備變更嘅馬 form 平均 59.83 vs 62.10）。
            # 但佢本身係顯著訊號（除下 OFF FIRST TIME −3.86pp [−6.94,−0.75]），
            # 用戶睇分析嗰陣想知，所以照顯示。見 EXP-20260826-07。
            look = index + 2
            while look < len(lines) and not RACECARD_HORSE_RE.match(lines[look].strip()):
                gm = re.match(r"Gear:\s*(.+)$", lines[look].strip())
                if gm:
                    profiles[_normalize_horse_name(horse_name)]["gear_change"] = gm.group(1).strip()
                    break
                look += 1
        index += 2
    return profiles
