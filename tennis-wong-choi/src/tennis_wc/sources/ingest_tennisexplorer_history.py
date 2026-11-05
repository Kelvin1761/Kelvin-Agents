"""Build a lower-tier match corpus from the TennisExplorer scoreboard.

``ingest_tennisexplorer`` settles fixtures we already hold.  This writes the
history the models learn from, including matches between players we have never
priced -- which is the whole point.  Elo is built from ``player_match_history``,
that table is fed by the Sackmann/TennisMyLife files, and those publish ATP,
ATP quali, Challenger and WTA and **no ITF at all** (checked against the live
manifest: 171 files, zero matching itf or futures).  So Elo covers 75.9% of
tour fixtures and 1.2% of ITF ones while ITF is ~85% of the board we price.

Every player is resolved through :mod:`tennis_wc.sources.identity`
before anything is created, because creating a player per spelling is exactly
how 864 duplicate identities happened the first time.
"""
from __future__ import annotations

from tennis_wc.store.history_observations import ensure_history_schema, upsert_history_observation

from datetime import date, datetime, timedelta, timezone
from dataclasses import asdict

from tennis_wc.store.db import get_connection
from tennis_wc.model.features.common import utc_now
from tennis_wc.sources import identity as player_identity
from tennis_wc.sources.name_matching import normalise_player_name, player_name_score
from tennis_wc.sources.raw_response_store import store_raw_response
from tennis_wc.sources.providers.tennisexplorer_provider import (
    ParsedResult,
    ResultsPage,
    RESULTS_URL,
    TennisExplorerResultsProvider,
    parse_results_page,
)

PROVIDER_NAME = "tennisexplorer"


def _tier_of(tournament_name: str | None) -> str:
    name = str(tournament_name or "").upper()
    if "ITF" in name or "FUTURES" in name:
        return "ITF"
    if "UTR" in name:
        return "UTR"
    if "CHALLENGER" in name:
        return "CHALLENGER"
    return "TOUR"


def _date_range(start_date: str, end_date: str) -> list[str]:
    first = date.fromisoformat(start_date)
    last = date.fromisoformat(end_date)
    if last < first:
        first, last = last, first
    return [
        (first + timedelta(days=offset)).isoformat()
        for offset in range((last - first).days + 1)
    ]


class _HistoryHold(ValueError):
    """Keep an unresolved source match out of the individual history graph."""


class _ExistingHistory:
    """A changed tour/identity must not create a second ACTIVE historical match."""

    def __init__(self, conn, match_date: str):
        self.by_ref = {}
        self.by_pair = {}
        for row in conn.execute(
            "SELECT * FROM player_match_history WHERE source_provider=? AND match_date=?",
            (PROVIDER_NAME, match_date),
        ):
            self.remember(dict(row))

    def remember(self, row: dict) -> None:
        pair = tuple(sorted((row["player_id"], row["opponent_id"])))
        self.by_pair.setdefault(pair, {})[row["id"]] = row
        for ref in (row["source_match_ref"], row["provider_match_id"]):
            if ref:
                self.by_ref.setdefault(ref, {})[row["id"]] = row

    def check(self, proposed: list[dict]) -> None:
        pair = tuple(sorted((proposed[0]["player_id"], proposed[0]["opponent_id"])))
        old = dict(self.by_pair.get(pair, {}))
        expected = {}
        for row in proposed:
            ref = row["provider_match_id"]
            old.update(self.by_ref.get(ref, {}))
            expected[(ref, row["player_id"])] = row
        if not old:
            return
        if len(old) != 2:
            raise _HistoryHold("existing_history_pair_collision")
        for row in old.values():
            if row["history_status"] != "ACTIVE" or not row["canonical_event_key"]:
                raise _HistoryHold("legacy_history_requires_review")
            ref = row["source_match_ref"] or row["provider_match_id"]
            new = expected.get((ref, row["player_id"]))
            if new is None or any(
                row.get(key) != value for key, value in new.items()
                if key not in {"provider_match_id", "raw_response_id", "created_at"}
            ):
                raise _HistoryHold("existing_history_facts_conflict")


def _get_or_create_player(conn, name: str, tour: str, created: list) -> int:
    """Canonical id for ``name``, creating a player only as a last resort."""
    if not name or player_identity.is_placeholder(name):
        raise _HistoryHold("placeholder_player")
    tokens = normalise_player_name(name).split()
    if not tokens:
        raise _HistoryHold("invalid_player_name")
    existing = player_identity.resolve_player_id(conn, name, tour)
    if existing is not None:
        row = conn.execute("SELECT tour FROM players WHERE id=?", (existing,)).fetchone()
        existing_tour = str(row[0] or "").upper() if row else ""
        if existing_tour not in {"ATP", "WTA"}:
            raise _HistoryHold("unknown_target_tour")
        if existing_tour != tour:
            raise _HistoryHold("target_tour_conflict")
        return existing
    # None can mean ambiguous, not unseen. Do not mint another spelling to
    # bypass a resolver that deliberately refused to choose between people.
    surname = tokens[-1]
    candidates = conn.execute(
        "SELECT name FROM players WHERE LOWER(name) LIKE ? OR LOWER(name) LIKE ?",
        (f"%{surname}%", f"%{surname[:4]}%"),
    )
    if any(player_name_score(name, row[0]) >= 0.92 for row in candidates):
        raise _HistoryHold("unresolved_existing_player")
    now = utc_now()
    cursor = conn.execute(
        "INSERT INTO players (name, tour, source_provider, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, tour, PROVIDER_NAME, now, now),
    )
    player_id = int(cursor.lastrowid)
    conn.execute(
        "INSERT OR IGNORE INTO player_aliases "
        "(alias_norm, canonical_player_id, source, created_at) VALUES (?, ?, ?, ?)",
        (normalise_player_name(name), player_id, PROVIDER_NAME, now),
    )
    created.append(player_id)
    return player_id


def _store_history(conn, match_date: str, results: list[ParsedResult], raw_id: int) -> dict:
    counts = {"matches": 0, "rows": 0, "players_created": 0, "skipped": 0,
              "held_reasons": {}}
    created: list[int] = []
    now = utc_now()
    source_scores = {}
    conflicting = set()
    fixture_refs = {}
    fixture_actors = {}

    def source_key(result):
        return (result.tournament_source_url or result.tournament_source_label,
                tuple(sorted((result.player_a_source_ref, result.player_b_source_ref))))

    for result in results:
        if (result.draw_kind != "SINGLES" or result.classification_warnings
                or not result.player_a_source_ref or not result.player_b_source_ref):
            continue
        key = source_key(result)
        if result.match_source_ref:
            fixture_refs.setdefault(key, set()).add(result.match_source_ref)
            fixture_actors.setdefault(result.match_source_ref, set()).add(
                (result.tour, result.draw_kind, key[1]))
        facts = (tuple(sorted((
            (result.player_a_source_ref, result.player_a_sets,
             tuple(s["player_a_games"] for s in result.sets)),
            (result.player_b_source_ref, result.player_b_sets,
             tuple(s["player_b_games"] for s in result.sets)),
        ))), result.retired)
        if key in source_scores and source_scores[key] != facts:
            conflicting.add(key)
        source_scores[key] = facts

    def hold(reason: str) -> None:
        counts["skipped"] += 1
        counts["held_reasons"][reason] = counts["held_reasons"].get(reason, 0) + 1

    # Nested match savepoints must not commit an otherwise empty date transaction.
    if results and not conn.in_transaction:
        conn.execute("BEGIN")
    if results:
        ensure_history_schema(conn)
    existing = _ExistingHistory(conn, match_date) if results else None
    for result in results:
        if result.classification_warnings:
            hold("invalid_source_classification")
            continue
        if result.draw_kind == "DOUBLES":
            hold("doubles_not_individual_history")
            continue
        if (result.draw_kind != "SINGLES" or result.tour not in {"ATP", "WTA"}
                or not result.player_a_source_ref or not result.player_b_source_ref
                or result.tour_source_kind not in {"tournament_url", "header_icon",
                                                    "tournament_url+header_icon"}
                or not result.tournament_source_label
                or result.tournament_source_label != result.tournament_name):
            hold("unknown_source_classification")
            continue
        if source_key(result) in conflicting:
            hold("conflicting_source_scores")
            continue
        if not result.match_source_ref:
            hold("unknown_source_fixture")
            continue
        if (len(fixture_refs.get(source_key(result), ())) > 1
                or len(fixture_actors.get(result.match_source_ref, ())) > 1):
            hold("ambiguous_source_fixture")
            continue
        winner_name = result.winner_name
        loser_name = (
            result.player_b_name if winner_name == result.player_a_name
            else result.player_a_name
        )
        tour = result.tour
        created_before = len(created)
        conn.execute("SAVEPOINT te_history_match")
        try:
            winner_id = _get_or_create_player(conn, winner_name, tour, created)
            loser_id = _get_or_create_player(conn, loser_name, tour, created)
            if winner_id == loser_id:
                raise _HistoryHold("same_resolved_player")
            base = (
                f"te-{match_date}-"
                f"{normalise_player_name(winner_name).replace(' ', '')}-"
                f"{normalise_player_name(loser_name).replace(' ', '')}"
            )
            proposed = []
            for provider_match_id, player_id, opponent_id, won in (
                (f"{base}-winner", winner_id, loser_id, 1),
                (f"{base}-loser", loser_id, winner_id, 0),
            ):
                proposed.append({
                        'provider_match_id': provider_match_id,
                        'player_id': player_id,
                        'opponent_id': opponent_id,
                        'tour': tour,
                        'match_date': match_date,
                        'tournament_external_id': result.tournament_name,
                        'tournament_level': _tier_of(result.tournament_name),
                        'round': "R",
                        'format': "BO3",
                        'won': won,
                        'source_provider': PROVIDER_NAME,
                        'raw_response_id': raw_id,
                        'created_at': now,
                        'surface': None,
                    })
            existing.check(proposed)
            stored_ids = [upsert_history_observation(conn, row, observed_at=now)
                          for row in proposed]
        except Exception as exc:
            conn.execute("ROLLBACK TO te_history_match")
            conn.execute("RELEASE te_history_match")
            del created[created_before:]
            if isinstance(exc, _HistoryHold):
                hold(str(exc))
                continue
            raise
        else:
            conn.execute("RELEASE te_history_match")
            for history_id in stored_ids:
                row = conn.execute("SELECT * FROM player_match_history WHERE id=?",
                                   (history_id,)).fetchone()
                existing.remember(dict(row))
            counts["rows"] += 2
            counts["matches"] += 1
    counts["players_created"] = len(set(created))
    return counts


def ingest_tennisexplorer_history(
    start_date: str, end_date: str | None = None, provider=None, log=None
) -> dict:
    """Walk the scoreboard day by day and store both sides of every match."""
    provider = provider or TennisExplorerResultsProvider()
    summary = {
        "dates": 0, "matches": 0, "rows": 0, "players_created": 0,
        "skipped": 0, "parse_skipped": 0, "held_reasons": {}, "held_sources": [],
        "errors": [],
    }
    with get_connection() as conn:
        player_identity.ensure_identity_schema(conn)
        # Release any bootstrap schema transaction before the source store's
        # own connection commits its receipt. A failed parse must not erase it.
        conn.commit()
        for match_date in _date_range(start_date, end_date or start_date):
            raw_id = None
            phase = 'fetch'
            try:
                page = provider.fetch_results_page_for_date(match_date)
                if not isinstance(page, ResultsPage) or not isinstance(page.html, str):
                    raise ValueError('TennisExplorer history requires a ResultsPage with original decoded HTML')
                phase = 'source_store'
                raw_id = store_raw_response(
                    PROVIDER_NAME, 'tennisexplorer/results',
                    {'match_date': match_date, 'requested_url': page.requested_url},
                    {'format': 'tennisexplorer-results-html-v1', **asdict(page),
                     'decoded_html_sha256': page.decoded_html_sha256},
                    200, 'match_history', match_date,
                )
                # Preserve even a rejected response before validating/ parsing.
                phase = 'source_validation'
                day = date.fromisoformat(match_date)
                expected_url = RESULTS_URL.format(year=day.year, month=day.month, day=day.day)
                fetched_at = datetime.fromisoformat(page.fetched_at.replace('Z', '+00:00'))
                if (page.match_date != match_date or page.requested_url != expected_url
                        or not page.html.strip() or fetched_at.tzinfo is None
                        or fetched_at > datetime.now(timezone.utc)):
                    raise ValueError('TennisExplorer source date/URL/clock/content is invalid')
                phase = 'parse'
                results, parse_skipped = parse_results_page(page.html)
            except Exception as exc:  # one bad day must not end the corpus build
                summary["errors"].append({'date': match_date, 'phase': phase,
                                          'raw_response_id': raw_id, 'error': str(exc)})
                continue
            counts = _store_history(conn, match_date, results, raw_id)
            conn.commit()
            summary["dates"] += 1
            summary["parse_skipped"] += parse_skipped
            for key in ("matches", "rows", "players_created", "skipped"):
                summary[key] += counts[key]
            for reason, count in counts["held_reasons"].items():
                summary["held_reasons"][reason] = summary["held_reasons"].get(reason, 0) + count
            if counts["held_reasons"]:
                summary["held_sources"].append({"date": match_date, "raw_response_id": raw_id,
                                                "reasons": counts["held_reasons"]})
            if log:
                log(f"{match_date}: {counts['matches']} matches, "
                    f"{counts['players_created']} new players, "
                    f"{counts['skipped']} held {counts['held_reasons']}")
    return summary
