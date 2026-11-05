"""Read-only, uncapped Tennis model tracking; never promotes a recommendation.

One record per saved source row. CLV mirrors of props are deduplicated by
source identity. Untimed/late/disputed entries remain visible but cannot enter
point-in-time model ROI. Actual D1 wagers remain a separate authority.
"""

from datetime import datetime, timezone
import json
import math
import re
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _time(value):
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo is not None and d.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def _rows(c, table, where=""):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        return None
    return [dict(r) for r in c.execute("SELECT * FROM " + table + where)]


def _json(value):
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _state(value):
    return {"WON": "won", "LOST": "lost", "VOID": "void", "PUSH": "void", "PENDING": "pending"}.get(
        str(value or "PENDING").upper(), "unverified"
    )


def _subject(row, match, players):
    """Resolve only explicit subject identity belonging to this exact fixture."""
    raw = row.get("subject_player_id")
    if raw is None:
        encoded = re.fullmatch(r"player_win_a_set_(\d+)", str(row.get("market_key") or ""))
        raw = encoded.group(1) if encoded else None
    identity = int(str(raw)) if str(raw).isdigit() else None
    if identity not in (match.get("player_a_id"), match.get("player_b_id")):
        identity = None
    name = players.get(identity) if identity is not None else None
    return {"subject_player_id": identity if name else None, "subject_player_name": name or None}


def export_tennis_tracking(db_path):
    result = {
        "status": "unavailable",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": [],
        "actual_bets": [],
        "covered_dates": [],
        "source_counts": {},
        "warnings": [],
    }
    if not db_path or not Path(db_path).is_file():
        result["warnings"] = ["tennis_tracking_database_unavailable"]
        return result
    try:
        with sqlite3.connect("file:" + str(Path(db_path).resolve()) + "?mode=ro", uri=True) as c:
            c.row_factory = sqlite3.Row
            # One read transaction: counts, results and identities share a view.
            c.execute("BEGIN")
            matches = {r["id"]: r for r in (_rows(c, "matches") or [])}
            players = {r["id"]: r.get("name", "") for r in (_rows(c, "players") or [])}
            sources = {
                name: _rows(c, name)
                # One ledger (2026-11-06 rebuild): props, 精選, and real bets.
                # Older match/market/combo paper rows stay in the database as
                # history but are no longer shown.
                for name in ("prop_tracker", "prop_live_bets")
            }
            result["warnings"] = [f"missing_tracking_source:{name}" for name, rows in sources.items() if rows is None]
            records = []

            def make(row, identity, kind):
                m = matches.get(row.get("match_id"), {})
                recorded = _time(row.get("recorded_at") or row.get("created_at"))
                start = _time(m.get("start_time_utc"))
                timed = bool(recorded and start and recorded < start)
                explicit = row.get("is_point_in_time")
                if explicit == 0:
                    timed = False
                elif explicit == 1 and not start:
                    timed = True
                disputed = m.get("fixture_status") == "DISPUTED" or m.get("source_provider") == "mock"
                if disputed:
                    timed = False
                day = (start.astimezone(ZoneInfo("Australia/Sydney")).date().isoformat() if start
                       else row.get("match_date") or m.get("match_date") or "")
                odds = _number(row.get("decimal_odds", row.get("odds_taken", row.get("odds"))))
                state = "unverified" if disputed else _state(row.get("result_status"))
                unit = None
                if odds is not None and odds > 1 and state in ("won", "lost", "void"):
                    stake, pnl = _number(row.get("stake_units")), _number(row.get("profit_loss_units"))
                    if stake and stake > 0 and pnl is not None:
                        unit = pnl / stake
                    else:
                        unit = odds - 1 if state == "won" else -1 if state == "lost" else 0
                event = f"{players.get(m.get('player_a_id')) or '?'} vs {players.get(m.get('player_b_id')) or '?'}"
                if not m:
                    event = row.get("match_label") or "賽事待核實"
                return {
                    "id": identity,
                    **_subject(row, m, players),
                    "day": day,
                    "event_name": event,
                    "start_time_utc": start.isoformat() if start else None,
                    "kind": kind,
                    "tier": row.get("tier") or "模型候選",
                    "tour": m.get("tour") or "",
                    "selection": row.get("selection") or "選項待核實",
                    "market": row.get("market_key") or "",
                    "odds": odds,
                    "state": state,
                    "unit_profit": unit,
                    "point_in_time": timed,
                    "recorded_at": row.get("recorded_at") or row.get("created_at"),
                    "model_probability": _number(row.get("blended_prob")),
                    "legs": [],
                    "evidence_note": "賽事身份待核實" if disputed
                    else "賽前時間已核實" if timed else "未有可核實賽前時間",
                }

            prop_ids = set()
            for r in sources["prop_tracker"] or []:
                if r.get("is_value") != 1:
                    continue
                prop_ids.add(r["id"])
                record = make(r, f"tennis:prop:{r['id']}", "prop")
                # Sportsbet's own English market and selection, so a bet can be
                # found on the site as written (Kelvin 2026-11-06).
                record["sportsbet_market"] = r.get("feed_market_name") or None
                if r.get("feed_selection_name"):
                    record["selection"] = r["feed_selection_name"]
                records.append(record)
            # 精選 (2026-11-05): frozen at the price each pick was sent at; the
            # result comes from prop_tracker, the single settlement source.
            # Read separately so a database without the table adds no warning.
            prop_by_id = {r["id"]: r for r in sources["prop_tracker"] or []}
            for f in _rows(c, "featured_picks") or []:
                base = prop_by_id.get(f.get("prop_id"), {})
                status = str(base.get("result_status") or "PENDING").upper()
                frozen = _number(f.get("odds"))
                pnl = None
                if frozen and frozen > 1:
                    pnl = {"WON": frozen - 1, "LOST": -1.0, "VOID": 0.0}.get(status)
                row = {
                    **base,
                    "match_id": f.get("match_id"),
                    "market_key": f.get("market_key"),
                    "selection": f.get("feed_selection_name") or f.get("selection"),
                    "decimal_odds": frozen,
                    "result_status": status,
                    "recorded_at": f.get("featured_at"),
                    "is_point_in_time": None,
                    "stake_units": 1.0 if pnl is not None else None,
                    "profit_loss_units": pnl,
                    "tier": f"精選 #{f.get('rank')}",
                }
                record = make(row, f"tennis:featured:{f.get('prop_id')}", "featured")
                record.update(
                    featured=True,
                    featured_rank=f.get("rank"),
                    sportsbet_market=f.get("feed_market_name") or None,
                )
                records.append(record)
            props = {r["id"]: r for r in sources["prop_tracker"] or []}
            for r in sources["prop_live_bets"] or []:
                prop = props.get(r.get("prop_id"), {})
                actual = make(dict(prop, recorded_at=r.get("placed_at")), f"tennis:live:{r['id']}", "actual")
                # This is a real placement with its own taken price/stake.
                # Never expose the model's normalized $1 P/L as actual profit.
                actual.pop("unit_profit", None)
                actual.update(
                    odds=_number(r.get("odds_taken")),
                    stake_aud=_number(r.get("stake_aud")),
                    currency=r.get("currency") or "AUD",
                    placed_at=r.get("placed_at"),
                )
                result["actual_bets"].append(actual)
            ids = [r["id"] for r in records]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate_tennis_tracking_identity")
            result.update(
                status="valid" if any(v is not None for v in sources.values()) else "unavailable",
                records=records,
                covered_dates=sorted({r["day"] for r in records if r["day"]}),
                source_counts={name: len(rows) for name, rows in sources.items() if rows is not None},
            )
    except (sqlite3.Error, ValueError, KeyError) as exc:
        result.update(status="unavailable", records=[], actual_bets=[], warnings=[f"tennis_tracking_error:{exc}"])
    return result
