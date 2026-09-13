"""Build compact Stage 5 NBA evidence without changing prediction logic.

The feature producer observes already-created pregame source files at one aware
cutoff and returns canonical bytes.  The settlement helper selects and validates
the existing reflector chain.  Neither function writes, publishes or promotes.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence


FEATURE_SCHEMA = "wong-choi-nba-feature-evidence/v1"
FEATURE_CONTRACT = "nba-pregame-feature-v1"
GAME_TAG = re.compile(r"[A-Z0-9]{2,4}_[A-Z0-9]{2,4}")


def _encoded(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _at(value: object) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid NBA evidence timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("NBA evidence timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _object(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"invalid NBA {label} JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"NBA {label} must be an object")
    return value


def _read(folder: Path, name: str) -> tuple[Path, bytes, dict]:
    path = folder / name
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"missing NBA source artifact: {name}") from exc
    if not raw:
        raise ValueError(f"empty NBA source artifact: {name}")
    return path, raw, _object(raw, name)


def _source(path: Path, raw: bytes, cutoff: datetime, field: str) -> dict:
    return {
        "artifact": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "available_at": cutoff.isoformat(),
        "field": field,
    }


def _nonempty_nested(value: object) -> bool:
    return isinstance(value, dict) and any(bool(item) for item in value.values())


def build_feature_projection(
    *,
    folder: Path,
    event_id: str,
    game_tags: Sequence[str],
    source_cutoff_at: datetime,
) -> bytes:
    """Return a central-contract NBA feature projection without file writes."""
    try:
        date.fromisoformat(event_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical NBA event date required") from exc
    root, cutoff = Path(folder).expanduser().resolve(), _at(source_cutoff_at)
    if not root.is_dir() or not root.name.startswith(f"{event_id} NBA Analysis"):
        raise ValueError("NBA evidence folder/event mismatch")
    if (
        not isinstance(game_tags, Sequence)
        or isinstance(game_tags, (str, bytes))
        or not game_tags
        or any(not isinstance(tag, str) or not GAME_TAG.fullmatch(tag) for tag in game_tags)
        or len(game_tags) != len(set(game_tags))
    ):
        raise ValueError("canonical unique NBA game tags required")

    rows = []
    for tag in sorted(game_tags):
        odds_path, odds_raw, odds = _read(root, f"Sportsbet_Odds_{tag}.json")
        game_path, game_raw, game = _read(root, f"nba_game_data_{tag}.json")
        if (
            str(odds.get("source") or "").casefold()
            not in {"sportsbet", "sportsbet_extractor"}
            or odds.get("target_analysis_date") != event_id
        ):
            raise ValueError("NBA odds event mismatch")
        market_fields = [
            name for name in ("game_lines", "player_props")
            if isinstance(odds.get(name), dict) and odds[name]
        ]
        if not market_fields:
            raise ValueError("NBA market source has no market data")

        meta = game.get("meta")
        if (
            not isinstance(meta, dict)
            or not isinstance(meta.get("game"), str) or not meta["game"].strip()
            or not isinstance(meta.get("date"), str) or not meta["date"].strip()
            or not isinstance(meta.get("season_phase"), str)
            or not isinstance(meta.get("away"), dict)
            or not isinstance(meta.get("home"), dict)
            or not all(str(meta[side].get("name") or "").strip() for side in ("away", "home"))
        ):
            raise ValueError("NBA schedule-context source is incomplete")
        players = game.get("players")
        if (
            not isinstance(players, dict)
            or not players
            or not any(isinstance(items, list) and items for items in players.values())
        ):
            raise ValueError("NBA player-form source is empty")
        team_fields = [
            name for name in ("team_stats", "team_dvp")
            if _nonempty_nested(game.get(name))
        ]
        if not team_fields:
            raise ValueError("NBA team-context source is empty")

        families = {
            "market": {
                "status": "available",
                "derivation": "sportsbet.pregame_market/v1",
                "sources": [
                    _source(odds_path, odds_raw, cutoff, name)
                    for name in market_fields
                ],
            },
            "player_form": {
                "status": "available",
                "derivation": "nba.player_form/v1",
                "sources": [_source(game_path, game_raw, cutoff, "players")],
            },
            "team_context": {
                "status": "available",
                "derivation": "nba.team_context/v1",
                "sources": [
                    _source(game_path, game_raw, cutoff, name)
                    for name in team_fields
                ],
            },
            "schedule_context": {
                "status": "available",
                "derivation": "nba.schedule_context/v1",
                "sources": [_source(game_path, game_raw, cutoff, "meta")],
            },
        }
        injuries = game.get("injuries")
        if isinstance(injuries, dict) and injuries:
            families["injury_context"] = {
                "status": "available",
                "derivation": "nba.injury_context/v1",
                "sources": [_source(game_path, game_raw, cutoff, "injuries")],
            }
        else:
            families["injury_context"] = {
                "status": "unavailable",
                "reason": "source_not_present" if injuries is None else "source_empty",
                "sources": [],
            }
        rows.append({
            "game_tag": tag,
            "feature_contract_id": FEATURE_CONTRACT,
            "families": families,
        })
    return _encoded({
        "schema_version": FEATURE_SCHEMA,
        "event_id": event_id,
        "generated_at": cutoff.isoformat(),
        "rows": rows,
    }) + b"\n"


def _number(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(float(value))


def _verification_complete(value: dict) -> bool:
    summary, legs = value.get("summary"), value.get("legs")
    fields = ("total_legs", "hits", "misses", "voids", "unverified")
    if (
        value.get("_version") != "PROPS_VERIFICATION_V1"
        or not isinstance(summary, dict)
        or any(type(summary.get(name)) is not int or summary[name] < 0 for name in fields)
        or not isinstance(legs, list)
        or summary["total_legs"] <= 0
        or summary["unverified"] != 0
        or len(legs) != summary["total_legs"]
    ):
        return False
    hits = misses = voids = 0
    for leg in legs:
        if not isinstance(leg, dict):
            return False
        if leg.get("outcome") == "void":
            if leg.get("cleared") is not None:
                return False
            voids += 1
            continue
        if (
            type(leg.get("cleared")) is not bool
            or not _number(leg.get("actual"))
            or not _number(leg.get("line"))
            or leg["cleared"] != (float(leg["actual"]) >= float(leg["line"]))
        ):
            return False
        hits += int(leg["cleared"])
        misses += int(not leg["cleared"])
    return (
        hits == summary["hits"]
        and misses == summary["misses"]
        and voids == summary["voids"]
        and hits + misses + voids == summary["total_legs"]
    )


def settlement_artifacts(*, folder: Path, event_id: str) -> tuple[Path, ...]:
    """Select the exact complete NBA reflector chain; never mutate the archive."""
    try:
        analysis_date = date.fromisoformat(event_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical NBA settlement event date required") from exc
    root = Path(folder).expanduser().resolve()
    if not root.is_dir() or not root.name.startswith(f"{event_id} NBA Analysis"):
        raise ValueError("NBA settlement folder/event mismatch")
    us_date = (analysis_date - timedelta(days=1)).isoformat()
    names = (
        f"Reflector_Run_Summary_{event_id}.json",
        f"Results_Brief_{us_date}.json",
        f"Props_Verification_{us_date}.json",
    )
    loaded = {}
    paths = []
    for name in names:
        path, raw, value = _read(root, name)
        paths.append(path)
        loaded[name] = value
    summary, results, verification = (loaded[name] for name in names)
    if (
        summary.get("analysis_date") != event_id
        or summary.get("us_game_date") != us_date
        or Path(str(summary.get("results_path") or "")).name != names[1]
        or Path(str(summary.get("verification_path") or "")).name != names[2]
        or type(summary.get("rows_recorded")) is not int
        or summary["rows_recorded"] <= 0
        or results.get("_version") != "RESULTS_BRIEF_V1"
        or results.get("date") != us_date
        or type(results.get("total_games")) is not int
        or results["total_games"] <= 0
        or not isinstance(results.get("games"), list)
        or len(results["games"]) != results["total_games"]
        or not _verification_complete(verification)
    ):
        raise ValueError("incomplete NBA settlement result chain")
    return tuple(sorted(paths, key=lambda path: path.name))
