from __future__ import annotations

from datetime import date as date_type, datetime, timezone, timedelta
import re
import logging
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from tennis_wc.database.db import get_connection
from tennis_wc.ingestion.entity_mapping import get_or_create_player, upsert_tournament
from tennis_wc.ingestion.fixture_versions import (
    upsert_fixture, ensure_fixture_schema, active_fixture_clause, quarantine_fixture,
)
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
    _prune_stale_sportsbet_odds_for_date(provider.provider_name, date, {str(row.get("event_id")) for row in rows if row.get("event_id")}, raw_id=raw_id)
    for row in rows:
        if provider.provider_name == "mock":
            row = row | {"event_id": f"mock-event-{date}-1"}
        # Refresh this provider's own provisional generation before resolving its event key.
        if provider.provider_name == "sportsbet":
            with get_connection() as conn:
                own=conn.execute("SELECT id FROM matches WHERE source_provider='sportsbet' AND provider_match_id=?",
                                 (f"sportsbet-{row['event_id']}",)).fetchone()
            if own:
                _create_provisional_match_for_odds(provider.provider_name,date,row,raw_id)
        with get_connection() as conn:
            match_id,blocked=_resolve_odds_fixture(conn,row,date,provider_name=provider.provider_name)
        if blocked:
            logging.getLogger(__name__).warning("odds identity rejected: %s/%s",provider.provider_name,row.get('event_id'))
            continue

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
            if a_odds is not None and b_odds is not None:
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
        count += 1
    return count


def _insert_market_odds(conn, row: dict, match_id: int | None, provider_name: str, raw_id: int, now: str,
                        *, table: str = "market_odds_snapshots", fetched_at: str | None = None) -> None:
    from tennis_wc.database.market_captures import record_market_capture

    record_market_capture(conn,match_id,row,provider_name,raw_id,now,table)
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
                f"""
                INSERT INTO {table} (
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
                    fetched_at or row.get("timestamp", now),
                    now,
                ),
            )


def _prune_stale_sportsbet_odds_for_date(provider_name: str, match_date: str,
                                         active_event_ids: set[str], *, raw_id: int | None = None) -> None:
    if provider_name not in {"sportsbet", "sportsbet_scrape"}:
        return
    from tennis_wc.database.market_captures import bookmaker_event_for_match,record_market_capture
    from tennis_wc.ingestion.fixture_versions import _observe
    with get_connection() as conn:
        ensure_fixture_schema(conn)
        rows = conn.execute("""SELECT m.* FROM matches m WHERE m.match_date=? AND (
            m.source_provider IN ('sportsbet','sportsbet_scrape')
            OR EXISTS(SELECT 1 FROM odds_snapshots o WHERE o.match_id=m.id AND o.source_provider=?)
            OR EXISTS(SELECT 1 FROM market_odds_snapshots o WHERE o.match_id=m.id AND o.source_provider=?))""",
            (match_date,provider_name,provider_name)).fetchall()
        for row in rows:
            event_id=bookmaker_event_for_match(conn,int(row['id']),provider_name)
            if not event_id or event_id in active_event_ids:
                continue
            if raw_id is not None:
                books={r[0] for r in conn.execute("""SELECT bookmaker FROM odds_snapshots WHERE match_id=? AND source_provider=?
                    UNION SELECT bookmaker FROM market_odds_snapshots WHERE match_id=? AND source_provider=?""",
                    (row['id'],provider_name,row['id'],provider_name))}
                for book in books or {provider_name}:
                    record_market_capture(conn,int(row['id']),{'event_id':event_id,'bookmaker':book,'listed':False},
                                          provider_name,raw_id,utc_now(),'market_odds_snapshots')
            # Availability belongs to the book; another fixture feed may still
            # list the event. Retain every old quote and forecast in both cases.
            if row['source_provider'] in {'sportsbet','sportsbet_scrape'} and row['fixture_status']=='ACTIVE':
                _observe(conn,int(row['id']),dict(row),'NOT_LISTED',utc_now())
                conn.execute("UPDATE matches SET fixture_status='NOT_LISTED' WHERE id=?",(row['id'],))


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
    from tennis_wc.ingestion.name_matching import normalise_player_name

    exact=normalise_player_name(selection_name)
    a,b=normalise_player_name(player_a_name),normalise_player_name(player_b_name)
    if exact and a!=b:
        if exact==a:
            return 'player_a'
        if exact==b:
            return 'player_b'
    selection = _name_tokens(selection_name)
    if not selection:
        return None
    normalised = _normalise_name(selection_name)
    if normalised in {"over", "under"}:
        return normalised
    names_a, names_b = _name_tokens(player_a_name), _name_tokens(player_b_name)
    matches_a = bool(names_a and (selection <= names_a or names_a <= selection))
    matches_b = bool(names_b and (selection <= names_b or names_b <= selection))
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
        return upsert_fixture(conn, {
            "provider_match_id": provider_match_id, "market_event_id": str(row["event_id"]),
            "tour": meta.tour, "match_date": match_date, "tournament_id": tournament_id,
            "player_a_id": player_a_id, "player_b_id": player_b_id,
            "round": sportsbet_round_label(row.get("round"),row.get("event_name"),row.get("name"),row.get("event_url"),row.get("competition")),
            "source_provider": provider_name, "raw_response_id": raw_id,
            "start_time_utc": _row_start_time_utc(row),
        }, now)



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
        f"""SELECT m.id,p1.name AS player_a_name,p2.name AS player_b_name FROM matches m
        JOIN players p1 ON p1.id=m.player_a_id JOIN players p2 ON p2.id=m.player_b_id
        WHERE m.match_date IN ({placeholders}) AND {active_fixture_clause(conn)}""",dates).fetchall()
    matches=[int(m['id']) for m in rows if _pair_matches(m,row)]
    if len(matches)>1:
        raise ValueError('ambiguous odds fixture pair')
    return matches[0] if matches else None


def _pair_matches(match, row: dict) -> bool:
    from tennis_wc.ingestion.name_matching import normalise_player_name
    a,b=(normalise_player_name(row.get(k)) for k in ('player_a_name','player_b_name'))
    x,y=(normalise_player_name(match[k]) for k in ('player_a_name','player_b_name'))
    return bool(a and b and a!=b and ((a==x and b==y) or (a==y and b==x)))


def _resolve_odds_fixture(conn, row: dict, match_date: str | None = None, *,
                          explicit_id: int | None = None, provider_name: str = '') -> tuple[int | None,bool]:
    ensure_fixture_schema(conn)
    where,params=('m.id=?',(explicit_id,)) if explicit_id is not None else ('m.market_event_id=?',(str(row.get('event_id')),))
    rows=conn.execute(f"""SELECT m.*,pa.name AS player_a_name,pb.name AS player_b_name FROM matches m
        JOIN players pa ON pa.id=m.player_a_id JOIN players pb ON pb.id=m.player_b_id WHERE {where}""",params).fetchall()
    if not row.get('player_a_name') or not row.get('player_b_name'):
        # Static mock rows carry a trusted explicit fixture key; live rows need both names.
        return (int(rows[0]['id']),False) if provider_name=='mock' and len(rows)==1 else (None,True)
    matched=[r for r in rows if _pair_matches(r,row) and r['fixture_status'] in {'ACTIVE','NOT_LISTED'}]
    if len(matched)==1:
        return int(matched[0]['id']),False
    if rows:
        # Conflicting event identifiers must not attach a new pair's prices to old forecasts.
        for r in rows:
            if not _pair_matches(r,row) and r['fixture_status'] in {'ACTIVE','NOT_LISTED'}:
                quarantine_fixture(conn,int(r['id']),row,utc_now())
        return None,True
    if explicit_id is not None:
        return None,True
    if match_date:
        try:
            match_id=_find_match_id_for_odds(conn,match_date,row)
        except ValueError:
            return None,True
        return match_id,False
    return None,False


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


def ingest_event_odds(event_id: str, match_id: int | None = None, *, preclose: bool = False) -> int:
    """Fetch one event page and store every market on it.

    `preclose=True` (2026-10-14) writes to `preclose_odds_snapshots` /
    `preclose_market_odds_snapshots` instead of the two live tables. Those
    hold ONLY the scheduled near-start capture, and only the CLOSE readers
    (`fetch_closing_odds_for_date`, `_tracker_close`, `_log_prop_prices`) read
    them. About fifty other queries read the live tables -- the card prices
    from the newest snapshot and every replay from the earliest -- so a late
    capture landing there could change a selection, or seed a replay with a
    price that was never on offer at card time. Kept apart, it cannot.
    """
    provider = get_odds_provider()
    row = provider.fetch_event_odds(event_id, ["match_winner"])
    raw_id = store_raw_response(
        provider.provider_name,
        "/event-odds-preclose" if preclose else "/event-odds",
        {"event_id": event_id, "markets": ["match_winner"], "preclose": preclose},
        row,
        200,
        "odds_preclose" if preclose else "odds",
        event_id,
    )
    _validate_sportsbet_event_response(provider.provider_name, event_id, row)
    if preclose:
        return _store_preclose_event(row, match_id, provider.provider_name, raw_id)
    now = utc_now()
    with get_connection() as conn:
        match_id,blocked=_resolve_odds_fixture(conn,row,explicit_id=match_id,provider_name=provider.provider_name)
        if blocked:
            return 0
        a_odds, b_odds, a_open, b_open = _oriented_positional_odds(conn, match_id, row)
        if a_odds is not None and b_odds is not None:
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
    return 1


def _validate_sportsbet_event_response(provider_name: str, event_ref: str, row: dict) -> None:
    """A direct Sportsbet URL identifies the requested event, not a redirect's event."""
    if provider_name != "sportsbet":
        return
    parsed = urlparse(str(event_ref))
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"sportsbet.com.au", "www.sportsbet.com.au"}:
        return
    requested = re.search(r"-(\d+)$", parsed.path.rstrip("/"))
    if not requested:
        return
    received = str(row.get("event_id") or "").strip() if isinstance(row, dict) else ""
    if received != requested.group(1):
        raise ValueError(f"sportsbet_event_response_mismatch: requested={requested.group(1)} received={received or 'missing'}")


def _store_preclose_event(row: dict, match_id: int | None, provider_name: str, raw_id: int) -> int:
    now = utc_now()
    # The capture time: a close is defined against the start by WHEN we saw it.
    fetched_at = row.get("timestamp") or now
    with get_connection() as conn:
        match_id,blocked=_resolve_odds_fixture(conn,row,explicit_id=match_id,provider_name=provider_name)
        if blocked:
            return 0
        a_odds, b_odds, a_open, b_open = _oriented_positional_odds(conn, match_id, row)
        if a_odds is not None and b_odds is not None:
            conn.execute(
                """
                INSERT INTO preclose_odds_snapshots (
                    event_id, match_id, bookmaker, market, player_a_odds, player_b_odds,
                    player_a_open_odds, player_b_open_odds, source_provider, raw_response_id,
                    fetched_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row["event_id"], match_id, row.get("bookmaker") or provider_name,
                 row.get("market") or "match_winner", a_odds, b_odds,
                 a_open, b_open, provider_name, raw_id, fetched_at, now),
            )
        _insert_market_odds(conn, row | {"bookmaker": row.get("bookmaker") or provider_name},
                            match_id, provider_name, raw_id, now,
                            table="preclose_market_odds_snapshots", fetched_at=fetched_at)
    return 1


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def refresh_pre_start_markets(
    match_date: str,
    *,
    now: datetime | None = None,
    lead_min_minutes: int = 15,
    lead_max_minutes: int = 75,
    max_events: int = 30,
    pause_seconds: float = 3.0,
    fetcher=None,
    sleeper=None,
) -> dict:
    """Second pre-start capture for the matches we evaluated on `match_date`.

    Why (measured read-only 2026-10-14 on props since 2026-09-01 with a feed
    identity and a start time): 2,839 of the 2,882 props with any pre-start
    snapshot had EXACTLY ONE (98.5%), median 3.8h before the start. The close
    WAS the price we evaluated at, so prop CLV was zero by construction.

    Which matches: start in (now + lead_min, now + lead_max], at least one
    prop_tracker or clv_tracker row (the model looked at it), and no preclose
    capture yet inside [start - lead_max, start). The scheduler ticks every 30
    minutes against a 60-minute window, so every start falls inside at least
    one tick and the "already captured" guard drops the second.

    Rate: one event page per match per day, `pause_seconds` apart, at most
    `max_events` a tick -- ~45 pages spread over a day, against the ~60 the
    09:00 card fetches back to back.

    Writes only the preclose tables (see `ingest_event_odds`); nothing that
    selects or stakes a bet reads them.
    """
    import time as _time

    fetch = fetcher or (lambda ref, mid: ingest_event_odds(ref, mid, preclose=True))
    sleep = sleeper or _time.sleep
    now_dt = now or datetime.now(timezone.utc)
    lower = _iso_z(now_dt + timedelta(minutes=lead_min_minutes))
    upper = _iso_z(now_dt + timedelta(minutes=lead_max_minutes))
    with get_connection() as conn:
        candidates = conn.execute(
            """
            SELECT m.id, m.start_time_utc
            FROM matches m
            WHERE m.match_date = ?
              AND m.start_time_utc IS NOT NULL AND m.start_time_utc != ''
              AND m.start_time_utc > ? AND m.start_time_utc <= ?
              AND (
                EXISTS (SELECT 1 FROM prop_tracker p WHERE p.match_id = m.id)
                OR EXISTS (SELECT 1 FROM clv_tracker t WHERE t.match_id = m.id)
              )
            ORDER BY m.start_time_utc, m.id
            """,
            (match_date, lower, upper),
        ).fetchall()
        todo = []
        already = 0
        for match in candidates:
            window_open = _iso_z(_parse_utc(match["start_time_utc"])
                                 - timedelta(minutes=lead_max_minutes))
            seen = conn.execute(
                """
                SELECT 1 FROM preclose_market_odds_snapshots
                WHERE match_id = ? AND fetched_at >= ? AND fetched_at < ?
                LIMIT 1
                """,
                (match["id"], window_open, match["start_time_utc"]),
            ).fetchone()
            if seen:
                already += 1
            else:
                todo.append(dict(match))
    refs = {}
    if todo:
        refs = {int(r["match_id"]): r for r in _latest_sportsbet_event_refs(match_date)
                if r.get("match_id") is not None}
    refreshed = 0
    errors: list[dict] = []
    no_ref = 0
    fetched_any = False
    for match in todo[:max_events]:
        ref = refs.get(int(match["id"])) or {}
        event_ref = ref.get("event_url") or ref.get("event_id")
        if not event_ref:
            no_ref += 1
            errors.append({"match_id": match["id"], "error": "no_event_ref_in_latest_listing"})
            continue
        if fetched_any:
            sleep(pause_seconds)
        fetched_any = True
        try:
            if fetch(event_ref, int(match["id"])) == 0:
                raise ValueError("event_identity_rejected")
            refreshed += 1
        except Exception as exc:  # noqa: BLE001 -- one bad page must not stop the tick
            errors.append({"match_id": match["id"],
                           "error": _classify_sportsbet_probe_error(str(exc))})
    return {
        "date": match_date,
        "window_utc": [lower, upper],
        "candidates": len(candidates),
        "already_captured": already,
        "refreshed": refreshed,
        "no_event_ref": no_ref,
        "failed": len(errors) - no_ref,
        "deferred_by_cap": max(0, len(todo) - max_events),
        "errors": errors,
    }


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
            if ingest_event_odds(event_ref, int(row["match_id"]) if row["match_id"] is not None else None) == 0:
                raise ValueError("event_identity_rejected")
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
                if ingest_event_odds(event_ref, int(row["match_id"]) if row["match_id"] is not None else None) == 0:
                    raise ValueError("event_identity_rejected")
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
