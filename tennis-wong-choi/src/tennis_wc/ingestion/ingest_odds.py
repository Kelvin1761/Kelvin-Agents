from __future__ import annotations

from datetime import date as date_type, datetime, timezone, timedelta
import re
from zoneinfo import ZoneInfo

from tennis_wc.database.db import get_connection
from tennis_wc.ingestion.entity_mapping import get_or_create_player, upsert_tournament
from tennis_wc.ingestion.raw_response_store import store_raw_response, utc_now
from tennis_wc.ingestion.sportsbet_fixture_mapping import sportsbet_competition_meta, sportsbet_round_label, sportsbet_slug
from tennis_wc.providers import get_odds_provider


def ingest_odds(date: str) -> int:
    provider = get_odds_provider()
    if hasattr(provider, "fetch_upcoming_odds_for_date"):
        rows = provider.fetch_upcoming_odds_for_date(date)
    else:
        rows = provider.fetch_upcoming_odds("tennis", ["us"], ["match_winner"])
    raw_id = store_raw_response(
        provider.provider_name,
        "/mock/odds",
        {"date": date, "sport": "tennis", "regions": ["us"], "markets": ["match_winner"]},
        rows,
        200,
        "odds",
        date,
    )
    now = utc_now()
    count = 0
    rows = [row for row in rows if _row_matches_requested_date(row, date)]
    _prune_stale_sportsbet_odds_for_date(provider.provider_name, date, {str(row.get("event_id")) for row in rows if row.get("event_id")})
    for row in rows:
        if provider.provider_name == "mock":
            row = row | {"event_id": f"mock-event-{date}-1"}
        with get_connection() as conn:
            match = conn.execute(
                "SELECT id FROM matches WHERE market_event_id = ?",
                (row["event_id"],),
            ).fetchone()
            match_id = int(match["id"]) if match else _find_match_id_for_odds(conn, date, row)
        
        # Always ensure tournament metadata for sportsbet matches
        _ensure_provisional_tournament_for_odds(provider.provider_name, date, row, raw_id)
        
        if match_id is None:
            match_id = _create_provisional_match_for_odds(provider.provider_name, date, row, raw_id)
        else:
            # An EXISTING fixture never learned its start time. Only the
            # create path carried `_row_start_time_utc`, so a match first seen
            # by the composite fixture provider -- which does not send one --
            # stayed NULL forever even while Sportsbet odds carrying the start
            # were being attached to it every run. Measured 2026-08-16 on
            # match_date 2026-08-17: source_provider='sportsbet' rows were
            # 100% populated and 'composite' rows 0%, which is what held the
            # column at 27-63% overall and left the card unable to tell
            # whether a match had already begun.
            _backfill_match_start_time(match_id, row)
        with get_connection() as conn:
            a_odds, b_odds, a_open, b_open = _oriented_positional_odds(
                conn, match_id, row)
            conn.execute(
                """
                INSERT INTO odds_snapshots (
                    event_id, match_id, bookmaker, market, player_a_odds, player_b_odds,
                    player_a_open_odds, player_b_open_odds, source_provider, raw_response_id,
                    fetched_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["event_id"],
                    match_id,
                    row["bookmaker"],
                    row["market"],
                    a_odds,
                    b_odds,
                    a_open,
                    b_open,
                    provider.provider_name,
                    raw_id,
                    row.get("timestamp", now),
                    now,
                ),
            )
            _insert_market_odds(conn, row, match_id, provider.provider_name, raw_id, now)
            # The fixture's players can have been rewritten by the upsert above
            # since these sides were last written; re-derive rather than trust.
            if match_id is not None:
                resync_selection_sides(conn, match_id)
        count += 1
    return count


def _insert_market_odds(conn, row: dict, match_id: int | None, provider_name: str, raw_id: int, now: str) -> None:
    # selection_side must be oriented to the LINKED match row's player order:
    # the scrape can list players in the opposite order to the fixture-created
    # match, and a flipped side mirror-flips every downstream factor readout.
    side_row = row
    if match_id is not None:
        match_players = conn.execute(
            """
            SELECT pa.name AS player_a_name, pb.name AS player_b_name
            FROM matches m
            JOIN players pa ON pa.id = m.player_a_id
            JOIN players pb ON pb.id = m.player_b_id
            WHERE m.id = ?
            """,
            (match_id,),
        ).fetchone()
        if match_players and match_players["player_a_name"] and match_players["player_b_name"]:
            side_row = {
                "player_a_name": match_players["player_a_name"],
                "player_b_name": match_players["player_b_name"],
            }
    markets = row.get("markets") or [
        {
            "market_key": row.get("market", "match_winner"),
            "market_name": "Match Betting",
            "selections": [
                {"selection_name": row.get("player_a_name"), "odds": row.get("player_a_odds")},
                {"selection_name": row.get("player_b_name"), "odds": row.get("player_b_odds")},
            ],
        }
    ]
    for market in markets:
        for selection in market.get("selections", []):
            odds = selection.get("odds")
            selection_name = selection.get("selection_name")
            if odds is None or not selection_name:
                continue
            conn.execute(
                """
                INSERT INTO market_odds_snapshots (
                    event_id, match_id, bookmaker, market_key, market_name,
                    selection_name, selection_side, line, odds, source_provider,
                    raw_response_id, fetched_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["event_id"],
                    match_id,
                    row["bookmaker"],
                    market.get("market_key") or row.get("market", "unknown"),
                    market.get("market_name") or market.get("market_key") or "Unknown",
                    selection_name,
                    _selection_side(side_row, selection_name),
                    selection.get("line"),
                    float(odds),
                    provider_name,
                    raw_id,
                    row.get("timestamp", now),
                    now,
                ),
            )


def _prune_stale_sportsbet_odds_for_date(provider_name: str, match_date: str, active_event_ids: set[str]) -> None:
    if provider_name not in {"sportsbet", "sportsbet_scrape"} or not active_event_ids:
        return
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM matches
            WHERE match_date = ?
              AND source_provider IN ('sportsbet', 'sportsbet_scrape')
              AND market_event_id IS NOT NULL
            """,
            (match_date,),
        ).fetchall()
        stale_ids = []
        for row in rows:
            match = conn.execute("SELECT market_event_id FROM matches WHERE id = ?", (row["id"],)).fetchone()
            if match and str(match["market_event_id"]) not in active_event_ids:
                stale_ids.append(int(row["id"]))
        if not stale_ids:
            return
        placeholders = ",".join("?" for _ in stale_ids)
        conn.execute(f"DELETE FROM odds_snapshots WHERE match_id IN ({placeholders}) AND source_provider IN ('sportsbet', 'sportsbet_scrape')", stale_ids)
        conn.execute(f"DELETE FROM market_odds_snapshots WHERE match_id IN ({placeholders}) AND source_provider IN ('sportsbet', 'sportsbet_scrape')", stale_ids)
        conn.execute(f"DELETE FROM market_predictions WHERE match_id IN ({placeholders})", stale_ids)


_NAME_NOISE = re.compile(r"-\s*(rain delay|walkover|retired|suspended)\b")


def _name_tokens(value: str | None) -> frozenset[str]:
    """The surname-ish tokens of a player or selection name.

    Substring containment was the previous rule and it failed in three shapes
    that are all common in this feed: the doubles pair `Nuno Borges/Francisco
    Cabral` is offered as `Borges / Cabral`, `Felix Auger-Aliassime` is offered
    without the hyphen, and a fixture name can carry a `- Rain Delay` suffix.
    Each of those returned None, and a side of None makes the price invisible to
    every reader rather than merely unordered.
    """
    text = _NAME_NOISE.sub(" ", str(value or "").lower())
    text = re.sub(r"[^a-z/ ]+", " ", text)
    return frozenset(part for part in re.split(r"[/\s]+", text) if len(part) > 2)


def selection_side_for(
    player_a_name: str | None,
    player_b_name: str | None,
    selection_name: str | None,
) -> str | None:
    """Which side of THIS match a selection name refers to, defined once.

    Both writers used to answer this question their own way -- the market table
    reoriented against the linked fixture and the positional columns did not --
    and the two disagreed on 10.8% of stored rows.  This is the single
    definition; every caller goes through it.

    A name that matches both players, or neither, returns None on purpose. A
    guess here mirror-flips the price, which is worse than declining to say.
    """
    selection = _name_tokens(selection_name)
    if not selection:
        return None
    normalised = _normalise_name(selection_name)
    if normalised in {"over", "under"}:
        return normalised
    matches_a = bool(selection & _name_tokens(player_a_name))
    matches_b = bool(selection & _name_tokens(player_b_name))
    if matches_a and not matches_b:
        return "player_a"
    if matches_b and not matches_a:
        return "player_b"
    return None


def _selection_side(row: dict, selection_name: str) -> str | None:
    return selection_side_for(
        row.get("player_a_name"), row.get("player_b_name"), selection_name
    )


def _oriented_positional_odds(conn, match_id: int | None, row: dict) -> tuple:
    """`(a, b, a_open, b_open)` ordered to the LINKED fixture's players.

    Every provider fills `player_a_odds` from its OWN first listed player, and
    `_find_match_id_for_odds` deliberately links a fixture whose players are in
    either order.  The market table has reoriented since; these four columns
    never did, so 48.6% of composite-fixture rows held the opponent's price.
    Only one reader remains -- feature_builder's positional fallback, which
    fires on 1 match of 2,046 -- but a wrong number stored is a wrong number
    someone eventually reads.
    """
    a = row.get("player_a_odds")
    b = row.get("player_b_odds")
    a_open = row.get("player_a_open_odds")
    b_open = row.get("player_b_open_odds")
    if match_id is None:
        return a, b, a_open, b_open
    players = conn.execute(
        """
        SELECT pa.name AS player_a_name, pb.name AS player_b_name
        FROM matches m
        JOIN players pa ON pa.id = m.player_a_id
        JOIN players pb ON pb.id = m.player_b_id
        WHERE m.id = ?
        """,
        (match_id,),
    ).fetchone()
    if not players:
        return a, b, a_open, b_open
    # The provider's own first player decides the flip; if it cannot be placed
    # on either side of the fixture, leave the order alone rather than guess.
    side = selection_side_for(
        players["player_a_name"], players["player_b_name"], row.get("player_a_name")
    )
    if side == "player_b":
        return b, a, b_open, a_open
    return a, b, a_open, b_open


def resync_selection_sides(conn, match_id: int) -> int:
    """Re-derive stored sides for one match from its CURRENT player names.

    The matches upsert sets `player_a_id = excluded.player_a_id`, so a provider
    that reuses a provider_match_id for a different pairing silently invalidates
    every side already stored against that row -- 29.1% of graded TOUR
    selections and 54.2% of UNKNOWN ones were mismatched this way, and nothing
    reported it.  Called after the upsert so the stored side always describes
    the row it hangs off.
    """
    players = conn.execute(
        """
        SELECT pa.name AS player_a_name, pb.name AS player_b_name
        FROM matches m
        JOIN players pa ON pa.id = m.player_a_id
        JOIN players pb ON pb.id = m.player_b_id
        WHERE m.id = ?
        """,
        (match_id,),
    ).fetchone()
    if not players:
        return 0
    rows = conn.execute(
        """
        SELECT id, selection_name, selection_side
        FROM market_odds_snapshots WHERE match_id = ?
        """,
        (match_id,),
    ).fetchall()
    changed = 0
    for row in rows:
        side = selection_side_for(
            players["player_a_name"], players["player_b_name"], row["selection_name"]
        )
        # Over/under sides carry no player, so leave them exactly as stored.
        if side is None and row["selection_side"] in {"over", "under"}:
            continue
        if side != row["selection_side"]:
            conn.execute(
                "UPDATE market_odds_snapshots SET selection_side = ? WHERE id = ?",
                (side, row["id"]),
            )
            changed += 1
    return changed


def _ensure_provisional_tournament_for_odds(provider_name: str, match_date: str, row: dict, raw_id: int) -> int | None:
    if provider_name != "sportsbet":
        return None
    meta = sportsbet_competition_meta(row.get("competition"), match_date)
    return upsert_tournament(
        provider_name,
        f"competition-{sportsbet_slug(row.get('competition') or meta.tournament_name)}",
        meta.tournament_name,
        meta.tour,
        raw_id,
        meta.level,
        meta.surface,
        meta.indoor_outdoor,
    )


def _create_provisional_match_for_odds(provider_name: str, match_date: str, row: dict, raw_id: int) -> int | None:
    if provider_name != "sportsbet":
        return None
    meta = sportsbet_competition_meta(row.get("competition"), match_date)
    if not row.get("player_a_name") or not row.get("player_b_name"):
        return None

    provider_match_id = f"sportsbet-{row['event_id']}"
    player_a_id = get_or_create_player(
        provider_name,
        f"player-{sportsbet_slug(row['player_a_name'])}",
        row["player_a_name"],
        meta.tour,
        raw_id,
    )
    player_b_id = get_or_create_player(
        provider_name,
        f"player-{sportsbet_slug(row['player_b_name'])}",
        row["player_b_name"],
        meta.tour,
        raw_id,
    )
    tournament_id = _ensure_provisional_tournament_for_odds(provider_name, match_date, row, raw_id)
    now = utc_now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO matches (
                provider_match_id, market_event_id, tour, match_date, tournament_id,
                player_a_id, player_b_id, round, source_provider, raw_response_id,
                created_at, updated_at, start_time_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_provider, provider_match_id) DO UPDATE SET
                market_event_id = excluded.market_event_id,
                match_date = excluded.match_date,
                tournament_id = excluded.tournament_id,
                player_a_id = excluded.player_a_id,
                player_b_id = excluded.player_b_id,
                round = CASE
                    WHEN matches.round IS NULL OR matches.round = 'UNKNOWN' THEN excluded.round
                    ELSE matches.round
                END,
                raw_response_id = excluded.raw_response_id,
                updated_at = excluded.updated_at,
                -- Never overwrite a known start time with nothing: the close
                -- cannot be identified without it.
                start_time_utc = COALESCE(excluded.start_time_utc,
                                          matches.start_time_utc)
            RETURNING id
            """,
            (
                provider_match_id,
                row["event_id"],
                meta.tour,
                match_date,
                tournament_id,
                player_a_id,
                player_b_id,
                sportsbet_round_label(row.get("round"), row.get("event_name"), row.get("name"), row.get("event_url"), row.get("competition")),
                provider_name,
                raw_id,
                now,
                now,
                _row_start_time_utc(row),
            ),
        )
        return int(cursor.fetchone()["id"])



def _row_start_time_utc(row: dict) -> str | None:
    """The fixture's start, normalised to UTC ISO-8601, or None.

    The provider sends it and nothing stored it, so there was no way to say
    which odds snapshot is the CLOSE -- 2.4% of snapshots were fetched after the
    match date and 1.2% of selections swing more than threefold inside their own
    history (1.19 -> 67.00), which is in-running, not drift. A "closing" price
    taken as simply the newest snapshot is sometimes a price from the middle of
    the second set.
    """
    for key in ("start_time_utc", "start_time", "startTime",
                "commence_time", "commenceTime"):
        parsed = _parse_datetime(row.get(key))
        if parsed:
            return parsed.astimezone(timezone.utc).isoformat(
                timespec="seconds").replace("+00:00", "Z")
    raw = row.get("raw")
    if isinstance(raw, dict):
        for source_key in ("event", "fixture"):
            source = raw.get(source_key)
            if not isinstance(source, dict):
                continue
            for key in ("start_time_utc", "start_time", "startTime",
                        "commence_time", "commenceTime"):
                parsed = _parse_datetime(source.get(key))
                if parsed:
                    return parsed.astimezone(timezone.utc).isoformat(
                        timespec="seconds").replace("+00:00", "Z")
    return None


def _backfill_match_start_time(match_id: int, row: dict) -> bool:
    """Fill a missing start time from the odds row. Never overwrite one.

    Fills only NULLs on purpose: the fixture provider is the authority on when
    a match starts, and a bookmaker's advertised time drifts. This is about the
    column being empty, not about it being wrong.
    """
    start = _row_start_time_utc(row)
    if not start:
        return False
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE matches SET start_time_utc = ? "
            "WHERE id = ? AND start_time_utc IS NULL",
            (start, int(match_id)),
        )
        conn.commit()
    return cursor.rowcount > 0


def _find_match_id_for_odds(conn, match_date: str, row: dict) -> int | None:
    player_a = _normalise_name(row.get("player_a_name"))
    player_b = _normalise_name(row.get("player_b_name"))
    if not player_a or not player_b:
        return None

    dates = _nearby_dates(match_date)
    placeholders = ",".join("?" for _ in dates)
    rows = conn.execute(
        f"""
        SELECT m.id, p1.name AS player_a_name, p2.name AS player_b_name
        FROM matches m
        JOIN players p1 ON p1.id = m.player_a_id
        JOIN players p2 ON p2.id = m.player_b_id
        WHERE m.match_date IN ({placeholders})
        """,
        dates,
    ).fetchall()
    for match in rows:
        match_a = _normalise_name(match["player_a_name"])
        match_b = _normalise_name(match["player_b_name"])
        if (match_a == player_a and match_b == player_b) or (match_a == player_b and match_b == player_a):
            return int(match["id"])
    return None


def _nearby_dates(match_date: str) -> list[str]:
    base = date_type.fromisoformat(match_date)
    return [(base + timedelta(days=offset)).isoformat() for offset in (0, -1, 1)]


def _row_matches_requested_date(row: dict, requested_date: str) -> bool:
    local_date = row.get("local_date")
    if local_date:
        return str(local_date) == requested_date
    for key in ("match_date", "date"):
        value = row.get(key)
        if isinstance(value, str) and len(value) >= 10 and value[:10].count("-") == 2:
            return value[:10] == requested_date
    parsed = _row_local_date(row)
    return parsed is None or parsed == requested_date


def _row_local_date(row: dict) -> str | None:
    for key in ("start_time_utc", "start_time", "startTime", "commence_time", "commenceTime", "match_date", "date"):
        parsed = _parse_datetime(row.get(key))
        if parsed:
            return parsed.astimezone(ZoneInfo("Australia/Sydney")).date().isoformat()
    raw = row.get("raw")
    if isinstance(raw, dict):
        event = raw.get("event") if isinstance(raw.get("event"), dict) else {}
        fixture = raw.get("fixture") if isinstance(raw.get("fixture"), dict) else {}
        for source in (event, fixture):
            for key in ("start_time", "startTime", "commence_time", "commenceTime", "game_time", "date", "match_date"):
                parsed = _parse_datetime(source.get(key))
                if parsed:
                    return parsed.astimezone(ZoneInfo("Australia/Sydney")).date().isoformat()
    return None


def _parse_datetime(value) -> datetime | None:
    # Before the membership test below, which is a set lookup and therefore
    # raises TypeError on the very shape this branch exists to handle.
    #
    # Sportsbet sends the start as an OBJECT -- {"milliseconds": 1786892400000}
    # -- not a scalar. Without this branch `str(dict)` fell through to the ISO
    # and %Y-%m-%d attempts, both failed on "{'millise", and None was returned
    # for every Sportsbet fixture: source coverage was 100% while the column
    # sat at 27-63%, filled only by the composite provider's string form. The
    # loss was invisible because "no start time" is a legal value.
    if isinstance(value, dict):
        for key in ("milliseconds", "millis", "ms"):
            if isinstance(value.get(key), (int, float)):
                return datetime.fromtimestamp(
                    float(value[key]) / 1000, tz=timezone.utc
                )
        for key in ("seconds", "epoch", "iso", "utc", "value"):
            if value.get(key) not in (None, ""):
                return _parse_datetime(value[key])
        return None
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalise_name(value: str | None) -> str:
    return " ".join(str(value or "").lower().strip().split())


def ingest_event_odds(event_id: str, match_id: int | None = None) -> int:
    provider = get_odds_provider()
    row = provider.fetch_event_odds(event_id, ["match_winner"])
    raw_id = store_raw_response(
        provider.provider_name,
        "/event-odds",
        {"event_id": event_id, "markets": ["match_winner"]},
        row,
        200,
        "odds",
        event_id,
    )
    now = utc_now()
    with get_connection() as conn:
        if match_id is None:
            match = conn.execute(
                "SELECT id FROM matches WHERE market_event_id = ?",
                (row["event_id"],),
            ).fetchone()
            match_id = int(match["id"]) if match else None
        a_odds, b_odds, a_open, b_open = _oriented_positional_odds(conn, match_id, row)
        conn.execute(
            """
            INSERT INTO odds_snapshots (
                event_id, match_id, bookmaker, market, player_a_odds, player_b_odds,
                player_a_open_odds, player_b_open_odds, source_provider, raw_response_id,
                fetched_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["event_id"],
                match_id,
                row["bookmaker"],
                row["market"],
                a_odds,
                b_odds,
                a_open,
                b_open,
                provider.provider_name,
                raw_id,
                row.get("timestamp") or now,
                now,
            ),
        )
        _insert_market_odds(conn, row, match_id, provider.provider_name, raw_id, now)
        if match_id is not None:
            resync_selection_sides(conn, match_id)
    return 1


def enrich_sportsbet_event_markets(match_date: str) -> dict:
    provider = get_odds_provider()
    if not hasattr(provider, "fetch_event_odds"):
        return {"date": match_date, "events": 0, "enriched": 0, "errors": ["provider_missing_fetch_event_odds"]}
    with get_connection() as conn:
        latest_raw = conn.execute(
            """
            SELECT id
            FROM raw_api_responses
            WHERE provider_name = 'sportsbet'
              AND entity_type = 'odds'
              AND entity_external_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (match_date,),
        ).fetchone()
        if latest_raw is None:
            return {"date": match_date, "events": 0, "enriched": 0, "errors": ["missing_latest_sportsbet_odds_raw_snapshot"]}

        rows = conn.execute(
            """
            SELECT o.event_id, MAX(o.match_id) AS match_id, json_extract(value, '$.event_url') AS event_url
            FROM odds_snapshots o
            JOIN raw_api_responses r ON r.id = o.raw_response_id
            JOIN json_each(r.response_json)
            WHERE r.id = ?
              AND json_extract(value, '$.event_id') = o.event_id
              AND o.source_provider = 'sportsbet'
            GROUP BY o.event_id, event_url
            """,
            (int(latest_raw["id"]),),
        ).fetchall()
    enriched = 0
    failed: list[dict] = []
    for row in rows:
        event_ref = row["event_url"] or row["event_id"]
        try:
            ingest_event_odds(event_ref, int(row["match_id"]) if row["match_id"] is not None else None)
            enriched += 1
        except Exception as exc:  # noqa: BLE001
            failed.append({"row": row, "event_id": row["event_id"], "event_url": row["event_url"], "error": _classify_sportsbet_probe_error(str(exc))})

    # Retry transient per-event failures (network blips) up to 2 extra passes so a
    # day reliably ends up with ALL markets, not just the headline match-winner.
    for _attempt in range(2):
        if not failed:
            break
        still: list[dict] = []
        for item in failed:
            row = item["row"]
            event_ref = row["event_url"] or row["event_id"]
            try:
                ingest_event_odds(event_ref, int(row["match_id"]) if row["match_id"] is not None else None)
                enriched += 1
            except Exception as exc:  # noqa: BLE001
                still.append({"row": row, "event_id": row["event_id"], "event_url": row["event_url"], "error": _classify_sportsbet_probe_error(str(exc))})
        failed = still

    errors = [{"event_id": item["event_id"], "event_url": item["event_url"], "error": item["error"]} for item in failed]
    return {
        "date": match_date,
        "events": len(rows),
        "enriched": enriched,
        "failed": len(errors),
        "coverage": round(enriched / len(rows), 3) if rows else 0.0,
        "errors": errors,
    }


def probe_sportsbet_event_markets(match_date: str, limit: int | None = None) -> dict:
    provider = get_odds_provider()
    if not hasattr(provider, "fetch_event_odds"):
        return {"date": match_date, "events": 0, "probed": 0, "errors": ["provider_missing_fetch_event_odds"], "market_counts": {}}

    event_rows = _latest_sportsbet_event_refs(match_date)
    if limit is not None:
        event_rows = event_rows[:limit]

    probed = 0
    market_counts: dict[str, int] = {}
    event_summaries = []
    errors = []
    for row in event_rows:
        event_ref = row["event_url"] or row["event_id"]
        try:
            event = provider.fetch_event_odds(event_ref, ["all"])
            raw_id = store_raw_response(
                provider.provider_name,
                "/event-market-probe",
                {"event_id": row["event_id"], "event_url": row["event_url"], "markets": ["all"]},
                event,
                200,
                "event_market_probe",
                str(row["event_id"]),
            )
            markets = event.get("markets") or []
            for market in markets:
                key = market.get("market_key") or "unknown"
                market_counts[key] = market_counts.get(key, 0) + 1
            event_summaries.append(
                {
                    "event_id": row["event_id"],
                    "match_id": row["match_id"],
                    "event_url": row["event_url"],
                    "market_count": len(markets),
                    "market_keys": sorted({market.get("market_key") or "unknown" for market in markets}),
                    "raw_response_id": raw_id,
                }
            )
            probed += 1
        except Exception as exc:
            errors.append({"event_id": row["event_id"], "event_url": row["event_url"], "error": _classify_sportsbet_probe_error(str(exc))})
    return {
        "date": match_date,
        "events": len(event_rows),
        "probed": probed,
        "market_counts": dict(sorted(market_counts.items(), key=lambda item: (-item[1], item[0]))),
        "event_summaries": event_summaries,
        "errors": errors,
    }


def _classify_sportsbet_probe_error(message: str) -> str:
    lowered = message.lower()
    if "could not resolve host" in lowered or "nodename nor servname provided" in lowered:
        return "dns_resolution_failed_for_sportsbet_domain"
    if "403" in lowered or "forbidden" in lowered:
        return "sportsbet_blocked_or_forbidden"
    if "preloaded state" in lowered:
        return "sportsbet_preloaded_state_not_found"
    return message


def _latest_sportsbet_event_refs(match_date: str) -> list[dict]:
    with get_connection() as conn:
        latest_raw = conn.execute(
            """
            SELECT id
            FROM raw_api_responses
            WHERE provider_name = 'sportsbet'
              AND entity_type = 'odds'
              AND entity_external_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (match_date,),
        ).fetchone()
        if latest_raw is None:
            return []
        rows = conn.execute(
            """
            SELECT o.event_id, MAX(o.match_id) AS match_id, json_extract(value, '$.event_url') AS event_url
            FROM odds_snapshots o
            JOIN raw_api_responses r ON r.id = o.raw_response_id
            JOIN json_each(r.response_json)
            WHERE r.id = ?
              AND json_extract(value, '$.event_id') = o.event_id
              AND o.source_provider = 'sportsbet'
            GROUP BY o.event_id, event_url
            ORDER BY o.event_id
            """,
            (int(latest_raw["id"]),),
        ).fetchall()
    return [dict(row) for row in rows]
