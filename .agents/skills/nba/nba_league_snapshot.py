"""Last-known-good copies of the stats.nba.com league tables (2026-10-30).

Team stats, player advanced (USG...), key defenders and team defence-vs-position
exist only on stats.nba.com. When it blocks us (12+ hours on 10-29/30) every
table came back empty and no game could be analysed. Each successful fetch is
now saved here, and a failed fetch -- a network failure, not a legitimately
empty feed -- reads back the newest copy instead.

Point-in-time rule: a copy is only usable when the date window it was fetched
with ends ON OR BEFORE the window being asked for (``date_to``), so a later
copy can never leak into an earlier analysis. It must also be at most
``MAX_AGE_DAYS`` older than that window; past that, empty is more honest.
Every use is recorded in the package's ``data_sources`` (``snapshot``), so a
stale table is never silent.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

# One day: a block that outlasts the next slate fails closed rather than
# analysing on tables that are two or more match-days behind.
MAX_AGE_DAYS = 1
CONTRACT = "nba-league-snapshot/v1"


def snapshot_root() -> Path:
    override = os.environ.get("WC_NBA_LEAGUE_SNAPSHOT_DIR")
    if override:
        return Path(override)
    return Path.home() / "WongChoiData" / "NBA" / "league_snapshots"


def _window_day(date_to: str | None) -> date | None:
    """nba_api ``date_to_nullable`` ('MM/DD/YYYY') -> date."""
    if not date_to:
        return None
    try:
        return datetime.strptime(str(date_to), "%m/%d/%Y").date()
    except ValueError:
        return None


def _path(label: str, season: str, day: date) -> Path:
    return snapshot_root() / label / str(season) / f"{day.isoformat()}.json"


def _restore_key(key: str):
    # Player-keyed tables use int NBA PLAYER_IDs; JSON turned them into str.
    return int(key) if key.lstrip("-").isdigit() else key


def save(label: str, season: str, date_to: str | None, data) -> Path | None:
    """Persist one successful fetch. Never raises: a cache must not break a run."""
    day = _window_day(date_to)
    if day is None or not data:
        return None
    path = _path(label, season, day)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {"contract": CONTRACT, "label": label, "season": season,
                "date_to": date_to, "saved_at": datetime.now().isoformat(timespec="seconds"),
                "rows": len(data),
                "data": {str(key): value for key, value in data.items()}}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, default=float), encoding="utf-8")
        os.replace(tmp, path)
        return path
    except (OSError, TypeError, ValueError):
        return None


def load(label: str, season: str, date_to: str | None, max_age_days: int = MAX_AGE_DAYS):
    """Newest usable copy as ``(data, info)``, or ``(None, None)``."""
    wanted = _window_day(date_to)
    folder = snapshot_root() / label / str(season)
    if wanted is None or not folder.is_dir():
        return None, None
    candidates = []
    for path in folder.glob("*.json"):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day <= wanted and (wanted - day).days <= max_age_days:
            candidates.append((day, path))
    for day, path in sorted(candidates, reverse=True):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        data = {_restore_key(key): value for key, value in (body.get("data") or {}).items()}
        if data:
            return data, {"snapshot_date_to": body.get("date_to"),
                          "snapshot_age_days": (wanted - day).days,
                          "snapshot_saved_at": body.get("saved_at"),
                          "snapshot_rows": len(data)}
    return None, None


def _entry_path(label: str, season: str, day: date, key) -> Path:
    # One file per player: the orchestrator runs games in parallel processes,
    # so a shared per-day file would lose entries to read-modify-write races.
    return snapshot_root() / label / str(season) / day.isoformat() / f"{key}.json"


def save_entry(label: str, season: str, date_to: str | None, key, value) -> None:
    """Persist one per-player result (e.g. splits). Never raises."""
    day = _window_day(date_to)
    if day is None or not value:
        return
    path = _entry_path(label, season, day, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"date_to": date_to, "value": value},
                                  ensure_ascii=False, default=float), encoding="utf-8")
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError):
        pass


def load_entry(label: str, season: str, date_to: str | None, key,
               max_age_days: int = MAX_AGE_DAYS):
    """Newest usable per-player copy as ``(value, age_days)``, same
    point-in-time and age rules as ``load``."""
    wanted = _window_day(date_to)
    folder = snapshot_root() / label / str(season)
    if wanted is None or not folder.is_dir():
        return None, None
    days = []
    for child in folder.iterdir():
        try:
            day = date.fromisoformat(child.name)
        except ValueError:
            continue
        if day <= wanted and (wanted - day).days <= max_age_days:
            days.append(day)
    for day in sorted(days, reverse=True):
        try:
            body = json.loads(_entry_path(label, season, day, key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if body.get("value"):
            return body["value"], (wanted - day).days
    return None, None


def backed(fetch_fn, label: str, failures, date_to_for):
    """Wrap ``fetch_fn(season, as_of)`` so it saves on success and, when the
    call failed on the network (``failures()`` went up) and came back empty,
    falls back to the newest usable copy. ``date_to_for(as_of)`` is the
    extractor's own window (``history_date_to``). ``wrapped.used`` lists every
    snapshot read, for ``data_sources``."""

    def wrapped(season, as_of=None):
        date_to = date_to_for(as_of)
        before = failures()
        data = fetch_fn(season, as_of)
        if data:
            save(label, season, date_to, data)
            return data
        if failures() == before:
            return data          # a genuinely empty feed, not an outage
        cached, info = load(label, season, date_to)
        if cached:
            print(f"  ♻️ {label}: stats.nba.com 唔通，用 {info['snapshot_date_to']} 嘅快照"
                  f"（舊 {info['snapshot_age_days']} 日，{info['snapshot_rows']} 行）")
            wrapped.used.append({"season": season, **info})
            return cached
        print(f"  ⛔ {label}: stats.nba.com 唔通，而 {MAX_AGE_DAYS} 日內冇可用快照")
        return data

    wrapped.used = []
    return wrapped
