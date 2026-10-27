"""Read-only, uncapped Tennis model tracking; never promotes a recommendation.

One record per saved source row. CLV mirrors of props are deduplicated by
source identity. Untimed/late/disputed entries remain visible but cannot enter
point-in-time model ROI. Actual D1 wagers remain a separate authority.
"""

from datetime import datetime, timezone
import json
import math
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
                for name in (
                    "prop_tracker",
                    "combo_tracker",
                    "clv_tracker",
                    "predictions",
                    "market_predictions",
                    "prop_live_bets",
                )
            }
            result["warnings"] = [f"missing_tracking_source:{name}" for name, rows in sources.items() if rows is None]
            records = []

            def make(row, identity, kind, match=None, legs=None):
                m = match or matches.get(row.get("match_id"), {})
                recorded = _time(row.get("recorded_at") or row.get("created_at"))
                starts = [_time(m.get("start_time_utc"))]
                if legs is not None:
                    starts = [_time(matches.get(l.get("match_id"), {}).get("start_time_utc")) for l in legs]
                timed = bool(recorded and starts and all(t and recorded < t for t in starts))
                explicit = row.get("is_point_in_time")
                if explicit == 0:
                    timed = False
                elif explicit == 1 and not all(starts):
                    timed = True
                disputed = (
                    m.get("fixture_status") == "DISPUTED"
                    or m.get("source_provider") == "mock"
                    or any(matches.get(l.get("match_id"), {}).get("fixture_status") == "DISPUTED" for l in (legs or []))
                )
                if disputed:
                    timed = False
                start = (
                    (min(starts) if starts and all(starts) else None)
                    if legs is not None
                    else _time(m.get("start_time_utc"))
                )
                day = (
                    start.astimezone(ZoneInfo("Australia/Sydney")).date().isoformat()
                    if start
                    else row.get("match_date") or m.get("match_date") or ""
                )
                odds = _number(
                    row.get(
                        "decimal_odds",
                        row.get("combo_odds", row.get("odds_taken", row.get("current_market_odds", row.get("odds")))),
                    )
                )
                state = _state(row.get("result_status"))
                if disputed:
                    state = "unverified"
                unit = None
                if odds is not None and odds > 1 and state in ("won", "lost", "void"):
                    stake, pnl = _number(row.get("stake_units")), _number(row.get("profit_loss_units"))
                    if stake and stake > 0 and pnl is not None:
                        unit = pnl / stake
                    elif kind != "combo":
                        unit = odds - 1 if state == "won" else -1 if state == "lost" else 0
                    elif state == "void":
                        unit = 0
                event = f"{players.get(m.get('player_a_id')) or '?'} vs {players.get(m.get('player_b_id')) or '?'}"
                if not m:
                    event = row.get("match_label") or "賽事待核實"
                clean_legs = [
                    {
                        "selection": l.get("selection") or l.get("selection_name") or "",
                        "market": l.get("market_key") or l.get("market") or "",
                        "match_id": l.get("match_id"),
                        "state": _state(l.get("result_status") or l.get("status")),
                        "event_name": " vs ".join(
                            players.get(matches.get(l.get("match_id"), {}).get(key)) or "?"
                            for key in ("player_a_id", "player_b_id")
                        ),
                    }
                    for l in (legs or [])
                    if isinstance(l, dict)
                ]
                return {
                    "id": identity,
                    "day": day,
                    "event_name": event,
                    "start_time_utc": start.isoformat() if start else None,
                    "kind": kind,
                    "tier": row.get("tier") or "模型候選",
                    "tour": m.get("tour") or "",
                    "selection": row.get("selection")
                    or row.get("selection_name")
                    or " + ".join(l["selection"] for l in clean_legs)
                    or "選項待核實",
                    "market": row.get("market_key")
                    or row.get("market_name")
                    or ("跨場組合" if kind == "combo" else "Match Winner"),
                    "odds": odds,
                    "state": state,
                    "unit_profit": unit,
                    "point_in_time": timed,
                    "recorded_at": row.get("recorded_at") or row.get("created_at"),
                    "model_probability": _number(row.get("blended_prob", row.get("model_probability"))),
                    "legs": clean_legs,
                    "evidence_note": "賽事身份待核實"
                    if disputed
                    else "賽前時間已核實"
                    if timed
                    else "未有可核實賽前時間",
                }

            prop_ids = set()
            for r in sources["prop_tracker"] or []:
                if r.get("is_value") != 1:
                    continue
                prop_ids.add(r["id"])
                records.append(make(r, f"tennis:prop:{r['id']}", "prop"))
            clv_pred = set()
            clv_market = set()
            for r in sources["clv_tracker"] or []:
                typ = r.get("recommendation_type")
                if typ == "PROP_RECOMMENDATION" and r.get("source_id") in prop_ids:
                    continue
                if typ == "MATCH_PREDICTION":
                    clv_pred.add(r.get("source_id"))
                if typ == "MARKET_LEG":
                    clv_market.add(r.get("source_id"))
                records.append(
                    make(r, f"tennis:tracking:clv:{r['id']}", "match" if typ == "MATCH_PREDICTION" else "market")
                )
            for r in sources["combo_tracker"] or []:
                raw_legs = _json(r.get("legs_json"))
                legs = [l for l in raw_legs if isinstance(l, dict)]
                record = make(r, f"tennis:combo:{r.get('combo_key') or r['id']}", "combo", legs=legs)
                record["event_name"] = r.get("match_label") or "跨場組合"
                if not legs or len(legs) != len(raw_legs):
                    record["point_in_time"] = False
                    record["evidence_note"] = "組合腳資料待核實"
                records.append(record)
            for r in sources["market_predictions"] or []:
                if r.get("decision") == "BET" and r["id"] not in clv_market:
                    records.append(make(r, f"tennis:tracking:market:{r['id']}", "market"))
            latest = {}
            for r in sources["predictions"] or []:
                if r["id"] > latest.get(r.get("match_id"), {}).get("id", -1):
                    latest[r.get("match_id")] = r
            for r in latest.values():
                if r.get("decision") == "BET" and r["id"] not in clv_pred:
                    records.append(make(r, f"tennis:reference:{r['id']}", "match"))
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
