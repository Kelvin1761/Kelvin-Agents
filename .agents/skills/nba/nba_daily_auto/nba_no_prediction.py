#!/usr/bin/env python3
"""Auditable "no prediction" marker for an NBA analysis date or game.

Why this exists
---------------
2026-10-10/11/12 (preseason) were blocked by the FW-04 decimal sentence-split
bug (fixed in 7c5df1b0).  Reports were written but no immutable
``_prediction_snapshots`` was ever frozen, so postgame raised
``live_analysis_has_no_prediction_snapshot`` and health reported
``missing_prediction`` forever.  Kelvin decided (2026-10-15) **not** to create
post-hoc snapshots: a snapshot written days later is not point-in-time
evidence.  These days are archived as "no prediction" instead.

Marker
------
``<date folder>/_no_prediction.json`` (travels with the folder when postgame
moves it into the archive)::

    {
      "schema_version": 1, "sport": "nba", "domain": "nba",
      "kind": "no_prediction", "event_id": D, "target_date": D,
      "append_only": true,
      "entries": [
        {"scope": "date" | "games", "game_tags": [...], "reason": "...",
         "marked_by": "...", "marked_at": "<Sydney ISO>",
         "model_commit": "<sha>",
         "files_present_at_mark": [{"name", "sha256", "bytes"}]}
      ]
    }

``files_present_at_mark`` is an audit trail of what existed when the day was
written off.  It is *not* a prediction snapshot and nothing evaluates it.

Entries are only ever appended.  Re-marking the same scope is a no-op.  A date
or game that already has a frozen prediction snapshot cannot be marked: the
marker exists to explain an absence, never to hide a prediction.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


MARKER_NAME = "_no_prediction.json"
SCHEMA_VERSION = 1


class NoPredictionError(ValueError):
    """The requested mark is not allowed (bad input or a snapshot exists)."""


@dataclass(frozen=True)
class NoPredictionScope:
    whole_date: bool = False
    game_tags: frozenset[str] = field(default_factory=frozenset)
    entries: tuple[dict[str, Any], ...] = ()

    @property
    def marked(self) -> bool:
        return self.whole_date or bool(self.game_tags)

    def covers(self, tags: Iterable[str]) -> bool:
        """True when every tag given is written off (an empty set never is)."""
        wanted = set(tags)
        if self.whole_date:
            return True
        return bool(wanted) and wanted <= self.game_tags

    def summary(self) -> dict[str, Any]:
        latest = self.entries[-1] if self.entries else {}
        return {
            "scope": "date" if self.whole_date else "games",
            "game_tags": sorted(
                self.game_tags
                | {
                    str(tag)
                    for entry in self.entries
                    if entry.get("scope") == "date"
                    for tag in entry.get("game_tags") or []
                }
            ),
            "reason": latest.get("reason"),
            "marked_by": latest.get("marked_by"),
            "marked_at": latest.get("marked_at"),
        }


def marker_path(folder: Path) -> Path:
    return Path(folder) / MARKER_NAME


def read_marker(folder: Path) -> dict[str, Any] | None:
    path = marker_path(folder)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # A corrupt marker must never silently become "no marker" (that would
        # re-raise the original alert) nor "everything marked".
        raise NoPredictionError(f"unreadable_no_prediction_marker:{path}:{exc}") from exc
    if not isinstance(payload, dict) or payload.get("kind") != "no_prediction":
        raise NoPredictionError(f"invalid_no_prediction_marker:{path}")
    return payload


def scope(folder: Path | None) -> NoPredictionScope:
    if folder is None or not Path(folder).is_dir():
        return NoPredictionScope()
    payload = read_marker(folder)
    if not payload:
        return NoPredictionScope()
    entries = tuple(entry for entry in payload.get("entries") or [] if isinstance(entry, dict))
    whole = any(entry.get("scope") == "date" for entry in entries)
    tags = frozenset(
        str(tag)
        for entry in entries
        if entry.get("scope") == "games"
        for tag in entry.get("game_tags") or []
    )
    return NoPredictionScope(whole_date=whole, game_tags=tags, entries=entries)


def folder_game_tags(folder: Path) -> set[str]:
    """Game tags with any analysis artifact in the folder."""
    tags: set[str] = set()
    for pattern, prefix, suffix in (
        ("Sportsbet_Odds_*.json", "Sportsbet_Odds_", ".json"),
        ("Game_*_Full_Analysis.md", "Game_", "_Full_Analysis.md"),
    ):
        for path in Path(folder).glob(pattern):
            tags.add(path.name.removeprefix(prefix).removesuffix(suffix))
    return tags


def covers_date(folder: Path) -> bool:
    """True when the whole date (every game in the folder) is written off."""
    current = scope(folder)
    return current.whole_date or current.covers(folder_game_tags(folder))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshotted_tags(folder: Path) -> tuple[bool, set[str]]:
    root = Path(folder) / "_prediction_snapshots"
    any_snapshot = False
    tags: set[str] = set()
    for manifest in sorted(root.glob("*/manifest.json")) if root.is_dir() else []:
        any_snapshot = True
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tags.update(str(tag) for tag in payload.get("game_tags") or [])
    return any_snapshot, tags


def mark(
    folder: Path,
    target_date: str,
    *,
    reason: str,
    marked_by: str,
    now: datetime,
    game_tags: Iterable[str] | None = None,
    model_commit: str = "unknown",
) -> dict[str, Any]:
    """Append one no-prediction entry; returns ``{"status", "entry", "path"}``."""
    folder = Path(folder)
    reason = (reason or "").strip()
    marked_by = (marked_by or "").strip()
    if not reason:
        raise NoPredictionError("reason_required")
    if not marked_by:
        raise NoPredictionError("marked_by_required")
    if not folder.is_dir():
        raise NoPredictionError(f"analysis_folder_missing:{folder}")
    if not folder.name.startswith(f"{target_date} NBA Analysis"):
        raise NoPredictionError(f"folder_date_mismatch:{folder.name}")

    tags = sorted({str(tag).strip() for tag in game_tags or [] if str(tag).strip()})
    present = folder_game_tags(folder)
    any_snapshot, snapshotted = _snapshotted_tags(folder)
    if tags:
        unknown = [tag for tag in tags if tag not in present]
        if unknown:
            raise NoPredictionError("unknown_game_tags:" + ",".join(unknown))
        frozen = [tag for tag in tags if tag in snapshotted]
        if frozen:
            raise NoPredictionError("game_has_prediction_snapshot:" + ",".join(frozen))
        entry_scope = "games"
    else:
        if any_snapshot:
            raise NoPredictionError("date_has_prediction_snapshot:use --game for unsnapshotted games")
        entry_scope = "date"

    current = scope(folder)
    if entry_scope == "date" and current.whole_date:
        return {"status": "already_marked", "path": str(marker_path(folder)), "entry": current.summary()}
    if entry_scope == "games" and current.covers(tags):
        return {"status": "already_marked", "path": str(marker_path(folder)), "entry": current.summary()}

    files = []
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.name != MARKER_NAME and not path.name.startswith("."):
            files.append({"name": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size})
    entry = {
        "scope": entry_scope,
        "game_tags": tags if tags else sorted(present),
        "reason": reason,
        "marked_by": marked_by,
        "marked_at": now.isoformat(),
        "model_commit": model_commit,
        "files_present_at_mark": files,
    }
    payload = read_marker(folder) or {
        "schema_version": SCHEMA_VERSION,
        "sport": "nba",
        "domain": "nba",
        "kind": "no_prediction",
        "event_id": target_date,
        "target_date": target_date,
        "append_only": True,
        "note": (
            "Written off as no prediction: no immutable prediction snapshot was "
            "frozen before tip-off. Excluded from prediction health, settlement "
            "evidence, the market ledger and reflector training."
        ),
        "entries": [],
    }
    payload["entries"] = list(payload.get("entries") or []) + [entry]
    path = marker_path(folder)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)
    return {"status": "marked", "path": str(path), "entry": {k: v for k, v in entry.items() if k != "files_present_at_mark"}}
