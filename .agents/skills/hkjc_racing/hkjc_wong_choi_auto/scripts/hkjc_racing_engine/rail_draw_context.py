"""Point-in-time rail-relative draw context for the prospective HKJC shadow."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

import numpy as np
import pandas as pd

from wongchoi_paths import HK_RACING, is_materialized_file


DATASET = (
    HK_RACING
    / "HKJC_Race_Results_Database"
    / "comprehensive_stats"
    / "rail_draw_results.csv"
)
SHRINK_RUNNERS = 60.0
MIN_RUNNERS = 100
MIN_RACES = 20
ADJUSTMENT_CAP = 4.0
_RAILS = {"A", "A+3", "B", "B+2", "C", "C+3"}


def _integer(value) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def _venue(value) -> str:
    text = str(value or "").replace(" ", "")
    low = text.casefold()
    if "跑馬地" in text or "happyvalley" in low or text.upper() == "HV":
        return "跑馬地"
    if "沙田" in text or "shatin" in low or text.upper() == "ST":
        return "沙田"
    return ""


def _draw_group(value) -> str:
    draw = _integer(value)
    if 1 <= draw <= 4:
        return "inner"
    if 5 <= draw <= 8:
        return "middle"
    if draw >= 9:
        return "outer"
    return "unknown"


def _distance_band(value) -> str:
    distance = _integer(value)
    if 1 <= distance <= 1200:
        return "sprint"
    if distance <= 1650:
        return "middle"
    if distance > 1650:
        return "route"
    return "unknown"


@lru_cache(maxsize=4)
def _read_dataset(path_text: str, modified_ns: int, size: int) -> pd.DataFrame:
    del modified_ns, size
    frame = pd.read_csv(path_text)
    required = {
        "Date", "RaceNo", "Venue", "Track", "Distance", "Rail",
        "FieldSize", "Draw", "Place",
    }
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    frame = frame[frame["Track"].astype(str).eq("Turf")].copy()
    frame["Date"] = frame["Date"].astype(str).str[:10]
    frame["VenueNorm"] = frame["Venue"].map(_venue)
    frame["RailNorm"] = frame["Rail"].astype(str).str.replace(" ", "", regex=False).str.upper()
    frame["DrawGroup"] = frame["Draw"].map(_draw_group)
    frame["DistanceBand"] = frame["Distance"].map(_distance_band)
    field = pd.to_numeric(frame["FieldSize"], errors="coerce").clip(lower=1)
    frame["Residual"] = (
        pd.to_numeric(frame["Place"], errors="coerce").fillna(0.0)
        - np.minimum(3.0, field) / field
    )
    frame["RaceId"] = (
        frame["Date"] + "|" + frame["VenueNorm"] + "|" + frame["RaceNo"].astype(str)
    )
    return frame


def _dataset(path: Path) -> pd.DataFrame:
    if not is_materialized_file(path):
        return pd.DataFrame()
    try:
        info = path.stat()
        return _read_dataset(str(path), info.st_mtime_ns, info.st_size)
    except (OSError, UnicodeError, pd.errors.ParserError):
        return pd.DataFrame()


def rail_draw_context_adjustment(
    race_context: dict,
    barrier,
    *,
    dataset_path: Path | None = None,
) -> dict:
    """Return a bounded pre-race adjustment relative to the generic draw prior."""
    venue = _venue(race_context.get("venue") or race_context.get("racecourse"))
    track_text = " ".join(
        str(race_context.get(key) or "")
        for key in ("track", "surface", "track_type", "venue")
    ).upper()
    rail = str(
        race_context.get("rail")
        or race_context.get("course_rail")
        or race_context.get("course_config")
        or race_context.get("course")
        or ""
    ).replace(" ", "").upper()
    band = _distance_band(race_context.get("distance"))
    group = _draw_group(barrier)
    cutoff = str(race_context.get("race_date") or "")[:10]
    base = {
        "applied": False,
        "adjustment": 0.0,
        "venue": venue,
        "rail": rail,
        "distance_band": band,
        "draw_group": group,
        "cell_runners": 0,
        "cell_races": 0,
        "parent_runners": 0,
        "cutoff": cutoff,
        "formula": "rail excess minus venue-distance parent; shrink=60; cap=±4",
    }
    if (
        not venue or rail not in _RAILS or band == "unknown" or group == "unknown"
        or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", cutoff)
        or any(token in track_text for token in ("AWT", "ALL WEATHER", "全天候", "泥地"))
    ):
        base["reason"] = "missing_or_ineligible_context"
        return base
    history = _dataset(dataset_path or DATASET)
    if history.empty:
        base["reason"] = "rail_history_unavailable"
        return base
    history = history[history["Date"] < cutoff]
    cell = history[
        history["VenueNorm"].eq(venue)
        & history["RailNorm"].eq(rail)
        & history["DistanceBand"].eq(band)
        & history["DrawGroup"].eq(group)
    ]
    parent = history[
        history["VenueNorm"].eq(venue)
        & history["DistanceBand"].eq(band)
        & history["DrawGroup"].eq(group)
    ]
    cell_races = int(cell["RaceId"].nunique())
    base.update(
        cell_runners=int(len(cell)),
        cell_races=cell_races,
        parent_runners=int(len(parent)),
    )
    if len(cell) < MIN_RUNNERS or cell_races < MIN_RACES or len(parent) < MIN_RUNNERS:
        base["reason"] = "insufficient_point_in_time_sample"
        return base
    cell_excess = float(cell["Residual"].sum()) / (len(cell) + SHRINK_RUNNERS)
    parent_excess = float(parent["Residual"].sum()) / (len(parent) + SHRINK_RUNNERS)
    adjustment = float(np.clip(100.0 * (cell_excess - parent_excess), -ADJUSTMENT_CAP, ADJUSTMENT_CAP))
    base.update(
        applied=abs(adjustment) >= 0.01,
        adjustment=round(adjustment, 4),
        cell_shrunk_excess=round(cell_excess, 6),
        parent_shrunk_excess=round(parent_excess, 6),
        reason="stable_point_in_time_rail_cell",
    )
    return base
