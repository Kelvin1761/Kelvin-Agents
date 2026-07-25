#!/usr/bin/env python3
"""Generate an idempotent D1 import from the legacy WC_STATE KV ledgers.

The script never talks to Cloudflare directly.  It converts two explicitly
exported JSON files into a reviewable SQL transaction which can be tested
locally and then applied with ``wrangler d1 execute``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple


def _number(value: Any, default: float = 0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sql(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bet_upsert(values: Dict[str, Any]) -> str:
    columns = [
        "id", "sport", "source_id", "event_date", "event_name", "market",
        "selection", "bet_type", "odds", "settlement_odds", "stake", "status",
        "payout", "profit", "bookmaker", "note", "analysis_snapshot",
        "settlement_source", "settlement_ref", "settlement_reason",
        "idempotency_key", "version", "created_at", "updated_at", "settled_at",
        "deleted_at",
    ]
    update_columns = [
        column for column in columns
        if column not in {"id", "created_at"}
    ]
    return (
        f"INSERT INTO bets ({', '.join(columns)}) VALUES "
        f"({', '.join(_sql(values.get(column)) for column in columns)}) "
        "ON CONFLICT(id) DO UPDATE SET "
        + ", ".join(f"{column}=excluded.{column}" for column in update_columns)
        + ";"
    )


def _horse_bet(key: str, record: Dict[str, Any]) -> Dict[str, Any]:
    deleted_at = _integer(record.get("deleted_at"), 0) or None
    updated_at = _integer(record.get("_updated_at"), 0) or deleted_at or 0
    status = str(record.get("status") or "pending").lower()
    if status not in {"pending", "won", "lost", "void"}:
        status = "pending"
    venue = str(record.get("venue") or "")
    race_number = _integer(record.get("race_number"))
    horse_number = _integer(record.get("horse_number"))
    horse_name = str(record.get("horse_name") or "")
    snapshot = {
        "region": str(record.get("region") or ""),
        "venue": venue,
        "race_number": race_number,
        "horse_number": horse_number,
        "horse_name": horse_name,
        "result_position": record.get("result_position"),
    }
    odds = max(0, _number(record.get("odds")))
    stake = max(0.01, _number(record.get("stake"), 1))
    if status == "won":
        payout = _number(record.get("payout"), stake * odds)
        profit = payout - stake
    elif status == "lost":
        payout = 0
        profit = -stake
    elif status == "void":
        payout = stake
        profit = 0
    else:
        payout = 0
        profit = 0
    return {
        "id": f"horse:{key}",
        "sport": "horses",
        "source_id": key,
        "event_date": str(record.get("date") or key.split("|", 1)[0]),
        "event_name": f"{venue} R{race_number}",
        "market": "Place",
        "selection": f"#{horse_number} {horse_name}".strip(),
        "bet_type": "single",
        "odds": odds,
        "settlement_odds": odds if status == "won" else None,
        "stake": stake,
        "status": status,
        "payout": round(payout, 6),
        "profit": round(profit, 6),
        "bookmaker": "Horse Racing",
        "note": "",
        "analysis_snapshot": _json(snapshot),
        "settlement_source": "horse-result" if status != "pending" else None,
        "settlement_ref": f"{record.get('date') or ''}|{venue}|R{race_number}",
        "settlement_reason": None,
        "idempotency_key": f"migration:{key}",
        "version": 1,
        "created_at": updated_at,
        "updated_at": updated_at,
        "settled_at": updated_at if status != "pending" else None,
        "deleted_at": deleted_at,
    }


def _sports_bet(key: str, record: Dict[str, Any]) -> Dict[str, Any]:
    deleted_at = _integer(record.get("deleted_at"), 0) or None
    created_at = _integer(record.get("created_at"), 0)
    updated_at = _integer(record.get("updated_at"), created_at) or deleted_at or 0
    status = str(record.get("status") or "pending").lower()
    if status not in {"pending", "won", "lost", "void"}:
        status = "pending"
    sport = str(record.get("sport") or "tennis").lower()
    if sport not in {"nba", "tennis"}:
        sport = "tennis"
    odds = max(0, _number(record.get("odds")))
    return {
        "id": str(record.get("id") or key),
        "sport": sport,
        "source_id": str(record.get("source_id") or ""),
        "event_date": str(record.get("event_date") or ""),
        "event_name": str(record.get("event_name") or ""),
        "market": str(record.get("market") or ""),
        "selection": str(record.get("selection") or ""),
        "bet_type": str(record.get("bet_type") or "single"),
        "odds": odds,
        "settlement_odds": record.get("settlement_odds"),
        "stake": max(0.01, _number(record.get("stake"), 1)),
        "status": status,
        "payout": _number(record.get("payout")),
        "profit": _number(record.get("profit")),
        "bookmaker": str(record.get("bookmaker") or ""),
        "note": str(record.get("note") or ""),
        "analysis_snapshot": _json(record.get("analysis_snapshot") or {}),
        "settlement_source": record.get("settlement_source") or None,
        "settlement_ref": record.get("settlement_ref") or None,
        "settlement_reason": record.get("settlement_reason") or None,
        "idempotency_key": str(record.get("idempotency_key") or f"migration:{key}"),
        "version": max(1, _integer(record.get("version"), 1)),
        "created_at": created_at,
        "updated_at": updated_at,
        "settled_at": record.get("settled_at"),
        "deleted_at": deleted_at,
    }


def _leg_inserts(bet_id: str, legs: Iterable[Dict[str, Any]]) -> Tuple[list[str], int]:
    statements = [f"DELETE FROM bet_legs WHERE bet_id = {_sql(bet_id)};"]
    count = 0
    for index, leg in enumerate(legs):
        if not isinstance(leg, dict) or not str(leg.get("selection") or "").strip():
            continue
        status = str(leg.get("status") or "pending").lower()
        if status not in {"pending", "won", "lost", "void"}:
            status = "pending"
        values = [
            bet_id,
            index,
            leg.get("event_name"),
            leg.get("market"),
            str(leg.get("selection") or ""),
            leg.get("line"),
            leg.get("odds"),
            status,
            leg.get("result_value"),
            leg.get("settlement_source"),
            leg.get("settlement_ref"),
            leg.get("settled_at"),
        ]
        statements.append(
            "INSERT INTO bet_legs ("
            "bet_id, leg_index, event_name, market, selection, line, odds, status, "
            "result_value, settlement_source, settlement_ref, settled_at"
            f") VALUES ({', '.join(_sql(value) for value in values)});"
        )
        count += 1
    return statements, count


def build_migration_sql(
    roi_ledger: Dict[str, Any],
    sports_ledger: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    roi = roi_ledger if isinstance(roi_ledger, dict) else {}
    sports = sports_ledger if isinstance(sports_ledger, dict) else {}
    canonical = _json({"roi": roi, "sports": sports})
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    migration_key = f"kv-to-d1-v1:{checksum[:16]}"
    # Wrangler D1 remote imports provide their own atomic rollback and reject
    # explicit BEGIN/COMMIT statements.  Every row is also an idempotent
    # upsert, so the same generated file is safe to retry.
    statements: list[str] = []
    horse_rows = 0
    sports_rows = 0
    leg_rows = 0

    for key, raw in sorted(roi.items()):
        if not isinstance(raw, dict):
            continue
        bet = _horse_bet(str(key), raw)
        statements.append(_bet_upsert(bet))
        horse_rows += 1

    for key, raw in sorted(sports.items()):
        if not isinstance(raw, dict):
            continue
        bet = _sports_bet(str(key), raw)
        statements.append(_bet_upsert(bet))
        leg_sql, count = _leg_inserts(bet["id"], raw.get("legs") or [])
        statements.extend(leg_sql)
        sports_rows += 1
        leg_rows += count

    source_count = horse_rows + sports_rows
    completed_at = max(
        [_integer(item.get("_updated_at") or item.get("updated_at") or item.get("deleted_at"), 0)
         for item in list(roi.values()) + list(sports.values()) if isinstance(item, dict)]
        or [0]
    )
    statements.append(
        "INSERT INTO migration_state "
        "(migration_key, source_count, imported_count, checksum, completed_at) VALUES "
        f"({_sql(migration_key)}, {source_count}, {source_count}, {_sql(checksum)}, {completed_at}) "
        "ON CONFLICT(migration_key) DO UPDATE SET "
        "source_count=excluded.source_count, imported_count=excluded.imported_count, "
        "checksum=excluded.checksum, completed_at=excluded.completed_at;"
    )
    summary = {
        "migration_key": migration_key,
        "checksum": checksum,
        "horse_rows": horse_rows,
        "sports_rows": sports_rows,
        "leg_rows": leg_rows,
        "source_count": source_count,
    }
    return "\n".join(statements) + "\n", summary


def _read_object(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate idempotent KV-to-D1 ledger SQL.")
    parser.add_argument("--roi-json", required=True, type=Path)
    parser.add_argument("--sports-json", required=True, type=Path)
    parser.add_argument("--output-sql", required=True, type=Path)
    parser.add_argument("--summary-json", type=Path)
    args = parser.parse_args()

    sql, summary = build_migration_sql(
        _read_object(args.roi_json),
        _read_object(args.sports_json),
    )
    args.output_sql.write_text(sql, encoding="utf-8")
    if args.summary_json:
        args.summary_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
