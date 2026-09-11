"""Read-only Tennis availability inventory, NOT a PIT dataset or safety grant.

Only archived inputs are read; no labels, current feature builder, prediction,
settlement or model code. MIN(id) means earliest *remaining* database price,
not proof of complete market history. Per-field provenance timing is checked,
but derivations still need independent historical verification. Operational
callers must supervise this bounded reader under the shared research lock.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .research_safety import ResearchSafetyError, _json


_MATCH_COLUMNS = "id,market_event_id,match_date,player_a_id,player_b_id,start_time_utc"
_RAW_COLUMNS = "id,provider_name,endpoint,response_json,fetched_at,created_at"
_PRICE_COLUMNS = "id,event_id,match_id,bookmaker,market_key,market_name,selection_name,selection_side,line,odds,source_provider,raw_response_id,fetched_at,created_at"
_FEATURE_COLUMNS = (
    "id,match_id,player_id,feature_set_version,features_json,provenance_json,data_quality_score,created_at"
)


class SourceExcluded(ValueError):
    """A specific match cannot be verified without repairing/cherry-picking."""


class SourceLimitExceeded(RuntimeError):
    """The whole inspection is incomplete; never return a truncated cohort."""


def _time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as exc:
        raise SourceExcluded("invalid_or_naive_timestamp") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceExcluded("missing_player_name")
    # Deliberately no fuzzy alias matching, reversal, transliteration or repair.
    return " ".join(value.casefold().split())


def _numeric(value: Any) -> bool:
    return type(value) in (float, int) and math.isfinite(value)


@dataclass(frozen=True)
class TennisSourcePolicy:
    date_from: str
    date_to: str
    as_of: str
    feature_fields: tuple[str, ...]
    feature_max_age_seconds: float
    price_max_age_seconds: float
    source_provider: str = "sportsbet"
    bookmaker: str = "Sportsbet"
    feature_set_version: str = "stage3.v1"
    max_matches: int = 500
    max_rows_per_match: int = 2000
    max_json_bytes: int = 4_000_000
    timeout_seconds: float = 10
    max_raw_rows: int = 10000
    max_raw_bytes: int = 64_000_000

    def validate(self) -> None:
        if (
            date.fromisoformat(self.date_from).isoformat() != self.date_from
            or date.fromisoformat(self.date_to).isoformat() != self.date_to
            or self.date_from > self.date_to
        ):
            raise ValueError("invalid date window")
        _time(self.as_of)
        if (
            not isinstance(self.feature_fields, tuple)
            or not self.feature_fields
            or any(
                not isinstance(field, str) or not field or any(not part for part in field.split("."))
                for field in self.feature_fields
            )
            or len(set(self.feature_fields)) != len(self.feature_fields)
        ):
            raise ValueError("explicit unique feature fields required")
        for value in (self.feature_max_age_seconds, self.price_max_age_seconds, self.timeout_seconds):
            if not _numeric(value) or value <= 0:
                raise ValueError("finite positive time limits required")
        for value in (
            self.max_matches,
            self.max_rows_per_match,
            self.max_json_bytes,
            self.max_raw_rows,
            self.max_raw_bytes,
        ):
            if type(value) is not int or value <= 0:
                raise ValueError("positive integer limits required")
        if self.source_provider != "sportsbet" or self.bookmaker != "Sportsbet" or not self.feature_set_version:
            raise ValueError("this source inspector only supports Sportsbet")


@dataclass(frozen=True)
class TennisSourceReport:
    policy: TennisSourcePolicy
    rows: tuple[dict, ...]
    exclusions: tuple[dict, ...]
    query_evidence_sha256: str
    exporter_sha256: str
    market_reconciliation: dict
    rating_lineage: dict

    def to_payload(self) -> dict:
        payload = {
            "schema_version": "wong-choi-tennis-source-inventory/v2",
            "policy": asdict(self.policy),
            "scope": "match_winner_availability_only",
            "proposal_ready": False,
            "pit_dataset_ready": False,
            "labels_read": False,
            "query_evidence_sha256": self.query_evidence_sha256,
            "exporter_sha256": self.exporter_sha256,
            "market_reconciliation": self.market_reconciliation,
            "rating_lineage": self.rating_lineage,
            "unresolved": [
                "historical_feature_derivation",
                "complete_earliest_market_history",
                "immutable_schedule_identity",
                "cohort_provenance",
                "labels_and_family_coverage",
            ],
            "rows": list(self.rows),
            "exclusions": list(self.exclusions),
        }
        return {**payload, "content_hash": _digest(payload)}


class _Reader:
    def __init__(self, conn, policy, checkpoint):
        self.conn, self.policy, self.checkpoint = conn, policy, checkpoint
        self.evidence = hashlib.sha256()

    def query(self, sql, args=(), *, limit=None):
        self.checkpoint()
        limit = self.policy.max_rows_per_match if limit is None else limit
        rows = self.conn.execute(sql, args).fetchmany(limit + 1)
        self.checkpoint()
        if len(rows) > limit:
            raise SourceLimitExceeded("row limit exceeded; use a smaller explicit window")
        result = [dict(row) for row in rows]
        # Bind inspected bad/missing inputs as well as successful rows. This is
        # a digest of the exact queried projection, not a whole-DB backup hash.
        self.evidence.update(_digest({"query": sql, "args": args, "rows": result}).encode())
        return result

    def parse(self, raw):
        if not isinstance(raw, str) or not raw.strip():
            raise SourceExcluded("empty_json")
        if len(raw.encode()) > self.policy.max_json_bytes:
            raise SourceLimitExceeded("source JSON exceeds inspection budget")
        try:
            result = _json(raw.encode())
        except (ResearchSafetyError, RecursionError) as exc:
            raise SourceExcluded("invalid_json") from exc
        self.checkpoint()
        return result

    def raw(self, raw_id):
        if type(raw_id) is not int or raw_id <= 0:
            raise SourceExcluded("invalid_raw_reference")
        rows = self.query(f"SELECT {_RAW_COLUMNS} FROM raw_api_responses WHERE id=?", (raw_id,))
        if len(rows) != 1:
            raise SourceExcluded("missing_raw_response")
        row = rows[0]
        if not row["provider_name"] or "mock" in row["provider_name"].casefold():
            raise SourceExcluded("mock_or_unknown_provider")
        return row

    def match(self, match):
        event_id = match["market_event_id"]
        if not event_id or self.query(
            "SELECT id FROM matches WHERE market_event_id=? ORDER BY id LIMIT 2", (event_id,), limit=2
        ) != [{"id": match["id"]}]:
            raise SourceExcluded("duplicate_or_missing_event_identity")
        start = _time(match["start_time_utc"])
        people = [match["player_a_id"], match["player_b_id"]]
        if len(set(people)) != 2 or any(type(person) is not int for person in people):
            raise SourceExcluded("ambiguous_participants")
        names = []
        for person in people:
            rows = self.query("SELECT name FROM players WHERE id=?", (person,))
            if len(rows) != 1:
                raise SourceExcluded("missing_player")
            names.append(_name(rows[0]["name"]))
        if names[0] == names[1]:
            raise SourceExcluded("ambiguous_player_names")
        quotes = self.query(
            f"""SELECT {_PRICE_COLUMNS} FROM market_odds_snapshots WHERE id IN (
            SELECT MIN(id) FROM market_odds_snapshots
            WHERE match_id=? AND event_id=? AND source_provider=? AND bookmaker=?
              AND market_key='match_winner'
            GROUP BY selection_name,line) ORDER BY id""",
            (match["id"], event_id, self.policy.source_provider, self.policy.bookmaker),
        )
        if len(quotes) != 2 or {_name(q["selection_name"]) for q in quotes} != set(names):
            raise SourceExcluded("incomplete_or_ambiguous_first_market")
        quotes.sort(key=lambda q: names.index(_name(q["selection_name"])))
        verified_quotes = [self.quote(q, match, names, start) for q in quotes]
        price_available = max(_time(q["available_at"]) for q in verified_quotes)
        snapshots = self.query(
            f"SELECT {_FEATURE_COLUMNS} FROM feature_snapshots WHERE match_id=? ORDER BY id", (match["id"],)
        )
        groups: dict[datetime, list[dict]] = {}
        for snapshot in snapshots:
            created = _time(snapshot["created_at"])
            if created >= price_available:
                groups.setdefault(created, []).append(snapshot)
        coherent = [moment for moment, group in groups.items() if set(s["player_id"] for s in group) == set(people)]
        if not coherent:
            raise SourceExcluded("no_coherent_feature_pair_after_first_price")
        decision = min(coherent)
        selected = groups[decision]
        if len(selected) != 2 or any(s["feature_set_version"] != self.policy.feature_set_version for s in selected):
            raise SourceExcluded("ambiguous_or_wrong_feature_version")
        if decision >= start or decision > _time(self.policy.as_of):
            raise SourceExcluded("decision_not_pre_start_or_after_cutoff")
        if any(
            (decision - _time(q["observed_at"])).total_seconds() > self.policy.price_max_age_seconds
            for q in verified_quotes
        ):
            raise SourceExcluded("stale_first_price")
        selected.sort(key=lambda s: people.index(s["player_id"]))
        features = [self.features(s, names[i], decision) for i, s in enumerate(selected)]
        return {
            "match_id": match["id"],
            "event_id": event_id,
            "stored_match_date": match["match_date"],
            "event_at": start.isoformat(),
            "decision_at": decision.isoformat(),
            "quotes": verified_quotes,
            "features": features,
            "match_metadata_sha256": _digest(match),
        }

    def quote(self, quote, match, names, start):
        if quote["line"] is not None or not _numeric(quote["odds"]) or quote["odds"] <= 1:
            raise SourceExcluded("invalid_two_way_price")
        raw = self.raw(quote["raw_response_id"])
        if raw["provider_name"] != self.policy.source_provider:
            raise SourceExcluded("price_provider_mismatch")
        parsed = self.parse(raw["response_json"])
        # /mock/odds is also a real ingestion endpoint label. Provider and exact
        # normalized event content decide identity, not that misleading label.
        events = parsed if isinstance(parsed, list) else [parsed]
        matches = [e for e in events if isinstance(e, dict) and str(e.get("event_id")) == match["market_event_id"]]
        if len(matches) != 1:
            raise SourceExcluded("raw_event_identity_mismatch")
        event = matches[0]
        if (
            event.get("bookmaker") != self.policy.bookmaker
            or [_name(event.get("player_a_name")), _name(event.get("player_b_name"))] != names
        ):
            raise SourceExcluded("raw_participant_or_bookmaker_mismatch")
        if _time(event.get("start_time_utc")) != start:
            raise SourceExcluded("raw_schedule_mismatch")
        if any(key in event and event[key] is not False for key in ("in_play", "is_live")):
            raise SourceExcluded("live_or_ambiguous_market_state")
        if "status" in event and str(event["status"]).casefold() not in ("scheduled", "prematch", "pre_match"):
            raise SourceExcluded("live_or_ambiguous_market_status")
        markets = event.get("markets")
        if not isinstance(markets, list):
            raise SourceExcluded("missing_raw_markets")
        markets = [m for m in markets if isinstance(m, dict) and m.get("market_key") == "match_winner"]
        if len(markets) != 1 or not isinstance(markets[0].get("selections"), list):
            raise SourceExcluded("ambiguous_raw_market")
        selections = markets[0]["selections"]
        if (
            len(selections) != 2
            or any(not isinstance(s, dict) for s in selections)
            or {_name(s.get("selection_name")) for s in selections} != set(names)
        ):
            raise SourceExcluded("raw_selection_identity_mismatch")
        selection = next(s for s in selections if _name(s["selection_name"]) == _name(quote["selection_name"]))
        if (
            selection.get("line") is not None
            or not _numeric(selection.get("odds"))
            or selection["odds"] != quote["odds"]
        ):
            raise SourceExcluded("raw_price_mismatch")
        observed, raw_observed = _time(quote["fetched_at"]), _time(raw["fetched_at"])
        available = max(observed, raw_observed, _time(quote["created_at"]), _time(raw["created_at"]))
        if raw_observed > observed or available >= start or available > _time(self.policy.as_of):
            raise SourceExcluded("price_not_verifiably_pre_start")
        return {
            "snapshot_id": quote["id"],
            "selection_name": quote["selection_name"],
            "odds": quote["odds"],
            "observed_at": observed.isoformat(),
            "available_at": available.isoformat(),
            "raw_response_id": raw["id"],
            "raw_sha256": _digest(raw),
            "snapshot_sha256": _digest(quote),
        }

    def features(self, snapshot, name, decision):
        parsed = self.parse(snapshot["features_json"])
        if (
            not isinstance(parsed, dict)
            or not isinstance(parsed.get("id"), dict)
            or parsed["id"].get("value") != snapshot["player_id"]
            or _name(parsed.get("name")) != name
        ):
            raise SourceExcluded("feature_player_identity_mismatch")
        output = {}
        for field in self.policy.feature_fields:
            point = parsed
            for part in field.split("."):
                point = point.get(part) if isinstance(point, dict) else None
            if (
                not isinstance(point, dict)
                or not _numeric(point.get("value"))
                or not isinstance(point.get("provenance"), dict)
            ):
                raise SourceExcluded("missing_numeric_feature_or_provenance:" + field)
            prov = point["provenance"]
            if prov.get("warnings") != []:
                raise SourceExcluded("feature_provenance_warning:" + field)
            raw = self.raw(prov.get("raw_response_id"))
            if prov.get("source_provider") != raw["provider_name"] or prov.get("source_endpoint") != raw["endpoint"]:
                raise SourceExcluded("feature_source_mismatch:" + field)
            self.parse(raw["response_json"])
            seen, calculated = _time(prov.get("source_timestamp")), _time(prov.get("calculated_at"))
            fetched, created = _time(raw["fetched_at"]), _time(raw["created_at"])
            if seen != fetched or max(seen, fetched, created) > calculated or calculated > decision:
                raise SourceExcluded("future_or_mismatched_feature_source:" + field)
            if (decision - seen).total_seconds() > self.policy.feature_max_age_seconds:
                raise SourceExcluded("stale_feature_source:" + field)
            output[field] = {"value": point["value"], "provenance": prov, "raw_sha256": _digest(raw)}
        return {
            "snapshot_id": snapshot["id"],
            "player_id": snapshot["player_id"],
            "fields": output,
            "snapshot_sha256": _digest(snapshot),
            "derivation_verified": False,
        }


def _raw_events(parsed):
    events = parsed if isinstance(parsed, list) else [parsed]
    if any(not isinstance(event, dict) or not event.get("event_id") for event in events):
        raise SourceExcluded("unrecognized_raw_event_shape")
    return events


def _has_match_winner(event, row):
    """Recognize both archived normalized shapes without inventing prices."""
    markets = event.get("markets")
    if not markets and event.get("market") == "match_winner":
        markets = [
            {
                "market_key": "match_winner",
                "selections": [
                    {"selection_name": event.get("player_a_name"), "odds": event.get("player_a_odds")},
                    {"selection_name": event.get("player_b_name"), "odds": event.get("player_b_odds")},
                ],
            }
        ]
    if not isinstance(markets, list):
        raise SourceExcluded("unrecognized_raw_market_shape")
    if any(not isinstance(market, dict) or not market.get("market_key") for market in markets):
        raise SourceExcluded("unrecognized_raw_market_shape")
    markets = [market for market in markets if market["market_key"] == "match_winner"]
    if not markets:
        return False
    if len(markets) != 1 or not isinstance(markets[0].get("selections"), list):
        raise SourceExcluded("ambiguous_raw_first_market")
    selections = markets[0]["selections"]
    names = {_name(quote["selection_name"]) for quote in row["quotes"]}
    if (
        len(selections) != 2
        or any(not isinstance(selection, dict) for selection in selections)
        or {_name(selection.get("selection_name")) for selection in selections} != names
        or any(
            selection.get("line") is not None or not _numeric(selection.get("odds")) or selection["odds"] <= 1
            for selection in selections
        )
    ):
        raise SourceExcluded("ambiguous_raw_first_selection")
    return True


def _reconcile_raw_markets(reader, rows):
    """Cross-check *retained* normalized raws; never assert archival completeness.

    Scan metadata first, enforce the aggregate byte budget before reading JSON,
    then fetch/parse one raw at a time. No literal-ID substring filtering that
    could miss escaped JSON IDs, and no quality-based skipping of earlier raws.
    """
    report = {
        "scope": "retained_provider_raws",
        "complete_archive_verified": False,
        "scanned_raws": 0,
        "scanned_bytes": 0,
        "unresolved_raws": [],
        "events": [],
    }
    if not rows:
        return report
    by_event = {row["event_id"]: row for row in rows}
    latest_decision = max(_time(row["decision_at"]) for row in rows)
    metadata = reader.query(
        "SELECT id,endpoint,fetched_at,created_at,length(CAST(response_json AS BLOB)) AS byte_length "
        "FROM raw_api_responses WHERE provider_name=? ORDER BY id",
        (reader.policy.source_provider,),
        limit=reader.policy.max_raw_rows,
    )
    eligible = []
    for meta in metadata:
        try:
            available = max(_time(meta["fetched_at"]), _time(meta["created_at"]))
        except SourceExcluded:
            report["unresolved_raws"].append(
                {"raw_response_id": meta["id"], "reason": "invalid_raw_time", "available_at": None}
            )
            continue
        if available <= latest_decision:
            if type(meta["byte_length"]) is not int or meta["byte_length"] < 0:
                raise SourceLimitExceeded("raw byte length unavailable")
            report["scanned_bytes"] += meta["byte_length"]
            eligible.append((meta, available))
    if report["scanned_bytes"] > reader.policy.max_raw_bytes:
        raise SourceLimitExceeded("raw archive exceeds aggregate byte budget")
    findings = {event_id: {"earlier": set(), "unresolved": []} for event_id in by_event}
    for meta, available in eligible:
        raw = reader.raw(meta["id"])
        report["scanned_raws"] += 1
        try:
            if meta["endpoint"] not in {"/mock/odds", "/event-odds", "/event-market-probe"}:
                raise SourceExcluded("unrecognized_provider_endpoint")
            events = _raw_events(reader.parse(raw["response_json"]))
        except SourceExcluded as exc:
            report["unresolved_raws"].append(
                {"raw_response_id": meta["id"], "reason": str(exc), "available_at": available.isoformat()}
            )
            continue
        seen = set()
        for event in events:
            event_id = str(event["event_id"])
            if event_id not in by_event:
                continue
            row = by_event[event_id]
            if available > _time(row["decision_at"]):
                continue
            finding = findings[event_id]
            try:
                if event_id in seen:
                    raise SourceExcluded("duplicate_raw_event")
                seen.add(event_id)
                if event.get("bookmaker") != reader.policy.bookmaker:
                    raise SourceExcluded("raw_bookmaker_ambiguous")
                if not _has_match_winner(event, row):
                    continue
                for quote in row["quotes"]:
                    if raw["id"] != quote["raw_response_id"] and (
                        raw["id"] < quote["raw_response_id"]
                        or available < _time(quote["available_at"])
                        or _time(raw["fetched_at"]) < _time(quote["observed_at"])
                    ):
                        finding["earlier"].add(raw["id"])
            except SourceExcluded as exc:
                finding["unresolved"].append({"raw_response_id": raw["id"], "reason": str(exc)})
    for row in rows:
        finding = findings[row["event_id"]]
        unresolved = finding["unresolved"] + [
            item
            for item in report["unresolved_raws"]
            if item["available_at"] is None or _time(item["available_at"]) <= _time(row["decision_at"])
        ]
        status = (
            "earlier_archived_capture"
            if finding["earlier"]
            else "raw_history_unverifiable"
            if unresolved
            else "earliest_in_retained_raws"
        )
        report["events"].append(
            {
                "match_id": row["match_id"],
                "event_id": row["event_id"],
                "status": status,
                "earlier_raw_ids": sorted(finding["earlier"]),
                "unresolved": unresolved,
            }
        )
    return report


def _rating_lineage(reader, rows):
    """Diagnostic comparison only. Current historical values are NEVER inputs."""
    report = {"status": "unverified", "missing_proof": ["ingested_at", "build_version", "input_manifest"], "rows": []}
    if not reader.query("SELECT name FROM sqlite_master WHERE type='table' AND name='player_elo_history'"):
        report["status"] = "history_table_missing"
        return report
    columns = {item["name"] for item in reader.query("PRAGMA table_info(player_elo_history)")}
    report["missing_proof"] = [column for column in report["missing_proof"] if column not in columns]
    for row in rows:
        for player in row["features"]:
            if "overall_elo" not in player["fields"]:
                continue
            value = player["fields"]["overall_elo"]["value"]
            history = reader.query(
                "SELECT player_id,as_of_date,surface,rating,matches_played FROM player_elo_history "
                "WHERE player_id=? AND surface='' AND as_of_date < ? ORDER BY as_of_date DESC LIMIT 1",
                (player["player_id"], row["stored_match_date"]),
            )
            report["rows"].append(
                {
                    "match_id": row["match_id"],
                    "player_id": player["player_id"],
                    "snapshot_id": player["snapshot_id"],
                    "snapshot_value": value,
                    "current_lookup": history[0] if history else None,
                    "current_lookup_matches_snapshot": bool(history and history[0]["rating"] == value),
                    "derivation_verified": False,
                }
            )
    return report


def inspect_tennis_sources(
    db_path: Path, policy: TennisSourcePolicy, *, checkpoint: Callable[[], None] | None = None
) -> TennisSourceReport:
    """Read one consistent, bounded snapshot; raise rather than truncate on limits.

    The progress handler bounds SQL CPU, not blocked OS I/O: live callers still
    require the external process supervisor. No database is created or modified.
    """
    policy.validate()
    exporter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    path = Path(db_path).expanduser().absolute()
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("source must be an existing regular non-symlink database")
    deadline = time.monotonic() + policy.timeout_seconds

    def check():
        if time.monotonic() >= deadline:
            raise SourceLimitExceeded("source inspection timeout")
        if checkpoint is not None:
            checkpoint()

    callback_error = None

    def progress():
        nonlocal callback_error
        try:
            check()
            return 0
        except Exception as exc:
            # sqlite3 otherwise replaces the original resource exception with
            # an opaque OperationalError('interrupted'). Preserve its reason.
            callback_error = exc
            return 1

    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=min(0.1, policy.timeout_seconds))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA trusted_schema=OFF")
        conn.set_progress_handler(progress, 1000)
        conn.execute("BEGIN")
        reader = _Reader(conn, policy, check)
        matches = reader.query(
            f"SELECT {_MATCH_COLUMNS} FROM matches WHERE match_date>=? AND match_date<=? ORDER BY match_date,id",
            (policy.date_from, policy.date_to),
            limit=policy.max_matches,
        )
        rows, exclusions = [], []
        for match in matches:
            check()
            try:
                rows.append(reader.match(match))
            except SourceExcluded as exc:
                exclusions.append(
                    {
                        "match_id": match["id"],
                        "event_id": match["market_event_id"],
                        "match_metadata_sha256": _digest(match),
                        "reasons": [str(exc)],
                    }
                )
        rating_lineage = _rating_lineage(reader, rows)
        reconciliation = _reconcile_raw_markets(reader, rows)
        statuses = {event["event_id"]: event["status"] for event in reconciliation["events"]}
        retained = []
        for row in rows:
            if statuses[row["event_id"]] == "earliest_in_retained_raws":
                retained.append(row)
            else:
                exclusions.append(
                    {
                        "match_id": row["match_id"],
                        "event_id": row["event_id"],
                        "match_metadata_sha256": row["match_metadata_sha256"],
                        "reasons": [statuses[row["event_id"]]],
                    }
                )
        exclusions.sort(key=lambda item: item["match_id"])
        check()
        if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != exporter_sha256:
            raise SourceLimitExceeded("exporter source changed during inspection")
        return TennisSourceReport(
            policy,
            tuple(retained),
            tuple(exclusions),
            reader.evidence.hexdigest(),
            exporter_sha256,
            reconciliation,
            rating_lineage,
        )
    except sqlite3.OperationalError as exc:
        if callback_error is not None:
            raise callback_error from exc
        raise
    finally:
        conn.close()
