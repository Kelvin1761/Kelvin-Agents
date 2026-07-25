"""Results-backed NBA and Tennis settlement proposals.

This module never writes a ledger.  It emits idempotent proposals only when
every required result can be tied to an official pipeline artifact.  The
Cloudflare settlement endpoint remains responsible for applying proposals to
the user's actual odds and stake while preserving an audit trail.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .multisport_exporter import export_nba_snapshot


SETTLED_MAP = {
    "WON": "won",
    "WIN": "won",
    "LOST": "lost",
    "LOSS": "lost",
    "VOID": "void",
    "PUSH": "void",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
    )


def _settled_status(value: Any) -> Optional[str]:
    return SETTLED_MAP.get(str(value or "").strip().upper())


def _derive_combo_status(legs: Iterable[Dict[str, Any]]) -> str:
    statuses = [str(leg.get("status") or "pending") for leg in legs]
    if "lost" in statuses:
        return "lost"
    if "pending" in statuses:
        return "pending"
    if statuses and all(status == "void" for status in statuses):
        return "void"
    return "won" if statuses else "pending"


def _latest_match_result(connection: sqlite3.Connection, match_id: int) -> Optional[sqlite3.Row]:
    return connection.execute(
        """
        SELECT r.winner_player_id, r.source_provider, r.score_json,
               m.player_a_id, m.player_b_id
        FROM matches m
        LEFT JOIN match_results r ON r.id = (
            SELECT r2.id FROM match_results r2
            WHERE r2.match_id = m.id
            ORDER BY r2.id DESC LIMIT 1
        )
        WHERE m.id = ?
        """,
        (match_id,),
    ).fetchone()


def _settle_tennis_leg(connection: sqlite3.Connection, leg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    match_id = leg.get("match_id")
    if match_id is None:
        return None
    result = _latest_match_result(connection, int(match_id))
    if not result or result["winner_player_id"] is None:
        return None
    market_key = str(leg.get("market_key") or "")
    if market_key != "match_winner":
        # The native tennis settlement engine handles the broader prop surface.
        # Dashboard auto-settlement remains strict until the tracker preserves a
        # per-leg result payload for those markets.
        return None
    winner_side = (
        "player_a"
        if int(result["winner_player_id"]) == int(result["player_a_id"])
        else "player_b"
    )
    status = "won" if str(leg.get("selection_side") or "") == winner_side else "lost"
    return {
        "selection": str(leg.get("selection_name") or ""),
        "market": str(leg.get("market_name") or market_key),
        "line": leg.get("line"),
        "odds": leg.get("odds"),
        "status": status,
        "settlement_source": "tennis_wc.db",
        "settlement_ref": f"match_results:{match_id}:{result['source_provider']}",
    }


def export_tennis_settlements(db_path: Path, target_date: Optional[str] = None) -> Dict[str, Any]:
    db_path = Path(db_path)
    if not db_path.is_file():
        return {
            "sport": "tennis",
            "generated_at": _utc_now(),
            "validation_status": "unavailable",
            "settlements": [],
            "warnings": ["tennis_database_not_found"],
        }
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    required = ["matches", "match_results", "clv_tracker", "combo_tracker"]
    missing = [name for name in required if not _table_exists(connection, name)]
    if missing:
        connection.close()
        return {
            "sport": "tennis",
            "generated_at": _utc_now(),
            "validation_status": "blocked",
            "settlements": [],
            "warnings": [f"missing_tennis_table:{name}" for name in missing],
        }

    date_clause = " AND match_date = ?" if target_date else ""
    params: tuple[Any, ...] = (target_date,) if target_date else ()
    singles = connection.execute(
        f"""
        SELECT id, source_id, match_id, match_date, result_status,
               profit_loss_units, updated_at
        FROM clv_tracker
        WHERE recommendation_type = 'MARKET_LEG'
          AND result_status IN ('WON', 'LOST', 'VOID', 'PUSH')
          {date_clause}
        ORDER BY updated_at, id
        """,
        params,
    ).fetchall()
    combos = connection.execute(
        f"""
        SELECT id, combo_key, match_date, legs_json, combo_odds,
               result_status, profit_loss_units, settled_at, updated_at
        FROM combo_tracker
        WHERE result_status IN ('WON', 'LOST', 'VOID', 'PUSH')
          {date_clause}
        ORDER BY updated_at, id
        """,
        params,
    ).fetchall()

    settlements: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for row in singles:
        status = _settled_status(row["result_status"])
        if not status:
            continue
        settlements.append(
            {
                "source_id": f"tennis:market:{row['source_id']}",
                "sport": "tennis",
                "status": status,
                "source": "tennis_wc.db",
                "source_ref": f"clv_tracker#{row['id']}",
                "reason": "Tennis native CLV tracker settlement",
                "settled_at": row["updated_at"],
                "idempotency_key": f"tennis:clv:{row['id']}:{row['updated_at']}:{status}",
            }
        )

    for row in combos:
        try:
            raw_legs = json.loads(row["legs_json"] or "[]")
        except (TypeError, ValueError):
            raw_legs = []
        resolved_legs = [
            _settle_tennis_leg(connection, leg)
            for leg in raw_legs
            if isinstance(leg, dict)
        ]
        if not raw_legs or any(leg is None for leg in resolved_legs):
            warnings.append(f"tennis_combo_leg_unresolved:{row['combo_key']}")
            continue
        legs = [leg for leg in resolved_legs if leg is not None]
        status = _derive_combo_status(legs)
        tracker_status = _settled_status(row["result_status"])
        if tracker_status and tracker_status != status:
            warnings.append(f"tennis_combo_tracker_disagreement:{row['combo_key']}")
        settlements.append(
            {
                "source_id": f"tennis:combo:{row['combo_key']}",
                "sport": "tennis",
                "status": status,
                "legs": legs,
                "source": "tennis_wc.db",
                "source_ref": f"combo_tracker#{row['id']}",
                "reason": "Independently resolved each combo leg from match_results",
                "settled_at": row["settled_at"] or row["updated_at"],
                "idempotency_key": (
                    f"tennis:combo:{row['id']}:{row['updated_at']}:{status}"
                ),
            }
        )
    connection.close()
    return {
        "sport": "tennis",
        "generated_at": _utc_now(),
        "validation_status": "valid" if settlements else "unavailable",
        "settlements": settlements,
        "warnings": warnings,
    }


def _normalise_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _nba_stat(player: Dict[str, Any], stat: str) -> Optional[float]:
    direct = {
        "PTS": "pts",
        "REB": "reb",
        "AST": "ast",
        "3PM": "fg3m",
        "STL": "stl",
        "BLK": "blk",
        "TOV": "tov",
    }
    stat = str(stat or "").upper()
    if stat in direct:
        value = player.get(direct[stat])
    else:
        parts = {
            "PRA": ("pts", "reb", "ast"),
            "PR": ("pts", "reb"),
            "PA": ("pts", "ast"),
            "RA": ("reb", "ast"),
        }.get(stat)
        if not parts:
            return None
        values = [player.get(part) for part in parts]
        if any(value is None for value in values):
            return None
        value = sum(float(item) for item in values)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_nba_game(results: Dict[str, Any], event_name: str) -> Optional[Dict[str, Any]]:
    teams = [part.strip().upper() for part in str(event_name).split("@")]
    for game in results.get("games") or []:
        away = str((game.get("away") or {}).get("team") or "").upper()
        home = str((game.get("home") or {}).get("team") or "").upper()
        if len(teams) == 2 and teams == [away, home]:
            return game
    return None


def _settle_nba_leg(game: Dict[str, Any], leg: Dict[str, Any], results_name: str) -> Optional[Dict[str, Any]]:
    player_name = str(leg.get("player") or "")
    stat = str(leg.get("stat") or "")
    line = leg.get("line")
    if not player_name or not stat or line is None:
        return None
    player = next(
        (
            item for item in (game.get("players") or [])
            if _normalise_name(item.get("name")) == _normalise_name(player_name)
        ),
        None,
    )
    if not player:
        return None
    actual = _nba_stat(player, stat)
    if actual is None:
        return None
    return {
        "selection": leg.get("selection") or "",
        "market": leg.get("market") or f"Player {stat}",
        "line": float(line),
        "odds": leg.get("odds"),
        "status": "won" if actual >= float(line) else "lost",
        "result_value": actual,
        "settlement_source": "nba_reflector",
        "settlement_ref": results_name,
    }


def export_nba_settlements(analysis_dir: Path) -> Dict[str, Any]:
    analysis_dir = Path(analysis_dir)
    date_match = re.match(r"(\d{4}-\d{2}-\d{2}) NBA Analysis$", analysis_dir.name)
    if not analysis_dir.is_dir() or not date_match:
        return {
            "sport": "nba",
            "generated_at": _utc_now(),
            "validation_status": "unavailable",
            "settlements": [],
            "warnings": ["nba_analysis_directory_not_found"],
        }
    result_paths = sorted(analysis_dir.glob("Results_Brief_*.json"))
    if not result_paths:
        return {
            "sport": "nba",
            "generated_at": _utc_now(),
            "validation_status": "unavailable",
            "settlements": [],
            "warnings": ["nba_results_brief_not_found"],
        }
    result_path = result_paths[-1]
    try:
        results = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        results = {}
    snapshot = export_nba_snapshot(analysis_dir.parent, target_date=date_match.group(1))
    settlements: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for recommendation in snapshot.get("recommendations") or []:
        game = _find_nba_game(results, recommendation.get("event_name") or "")
        if not game:
            warnings.append(f"nba_result_game_unmatched:{recommendation.get('id')}")
            continue
        if recommendation.get("bet_type") == "combo":
            resolved = [
                _settle_nba_leg(game, leg, result_path.name)
                for leg in recommendation.get("legs") or []
            ]
            if not resolved or any(leg is None for leg in resolved):
                warnings.append(f"nba_combo_leg_unresolved:{recommendation.get('id')}")
                continue
            legs = [leg for leg in resolved if leg is not None]
            status = _derive_combo_status(legs)
        else:
            contract = recommendation.get("settlement_contract") or {}
            leg = _settle_nba_leg(
                game,
                {
                    **contract,
                    "selection": recommendation.get("selection"),
                    "market": recommendation.get("market"),
                    "odds": recommendation.get("odds"),
                },
                result_path.name,
            )
            if not leg:
                warnings.append(f"nba_single_unresolved:{recommendation.get('id')}")
                continue
            legs = []
            status = leg["status"]
        settlements.append(
            {
                "source_id": recommendation["id"],
                "sport": "nba",
                "status": status,
                "legs": legs,
                "source": "nba_reflector",
                "source_ref": result_path.name,
                "reason": "NBA Results Brief box-score settlement",
                "settled_at": _utc_now(),
                "idempotency_key": (
                    f"nba:{date_match.group(1)}:{recommendation['id']}:{status}"
                ),
            }
        )
    return {
        "sport": "nba",
        "generated_at": _utc_now(),
        "validation_status": "valid" if settlements else "unavailable",
        "settlements": settlements,
        "warnings": warnings,
        "source_files": [result_path.name],
    }
