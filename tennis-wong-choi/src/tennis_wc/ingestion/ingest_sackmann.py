from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tennis_wc.database.db import get_connection
from tennis_wc.ingestion.entity_mapping import get_or_create_player, upsert_tournament
from tennis_wc.ingestion.raw_response_store import store_raw_response, utc_now


PROVIDER_NAME = "jeff_sackmann"
BASE_URLS = {
    "ATP": "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_{year}.csv",
    "WTA": "https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/wta_matches_{year}.csv",
}

# TennisMyLife serves live-updated ATP Challenger and tour-qualifying season
# files in the exact Sackmann column layout (incl. serve stats), so the same
# ingestion path applies. This is the low-tier history source that lets the
# model price Challenger players (Phase 2b; Sackmann's own qual_chall files
# were unreachable). ATP only — TML carries no WTA/ITF data.
TML_PROVIDER_NAME = "tennismylife_history"
TML_LOW_TIER_URLS = {
    "CHALLENGER": "https://stats.tennismylife.org/data/{year}_challenger.csv",
    "ATP_QUALI": "https://stats.tennismylife.org/data/atp_quali/{year}_atp_quali.csv",
    # ATP tour-level main draws. OVERLAPS the Sackmann backbone, so these rows
    # are inserted only when no jeff_sackmann row exists for the same player
    # pair on the same tourney_date (cross-provider dedup) — this keeps tour
    # history FRESH after the last Sackmann pull (frozen 2026-06-02; github
    # unreachable) without double-counting matches in Elo/feature stats.
    "ATP_MAIN": "https://stats.tennismylife.org/data/{year}.csv",
}
# Elo must consume both history backbones; elo_builder imports this.
HISTORY_PROVIDERS = (PROVIDER_NAME, TML_PROVIDER_NAME)


def ingest_sackmann_history(start_year: int, end_year: int, tours: list[str] | None = None) -> dict:
    """
    Import Jeff Sackmann match CSVs into local historical snapshots.

    The CSV files are treated as external data snapshots. We store the raw rows,
    map players by provider ID and name, insert historical ranks from winner_rank
    / loser_rank at tourney_date, and insert one player_match_history row per
    player per match.
    """
    wanted_tours = tours or ["ATP", "WTA"]
    imported = {"files": 0, "matches": 0, "player_rows": 0, "ranking_rows": 0, "errors": []}
    for tour in wanted_tours:
        for year in range(start_year, end_year + 1):
            url = BASE_URLS[tour].format(year=year)
            try:
                rows = _download_csv(url)
            except HTTPError as exc:
                if exc.code == 404:
                    imported["errors"].append({"tour": tour, "year": year, "error": "csv_not_found"})
                    continue
                raise
            raw_id = store_raw_response(
                PROVIDER_NAME,
                url,
                {"tour": tour, "year": year},
                rows,
                200,
                "match_history",
                f"{tour}-{year}",
            )
            stats = _ingest_rows(tour, rows, raw_id)
            imported["files"] += 1
            imported["matches"] += stats["matches"]
            imported["player_rows"] += stats["player_rows"]
            imported["ranking_rows"] += stats["ranking_rows"]
    return imported


def _download_csv(url: str) -> list[dict]:
    request = Request(url, headers={"User-Agent": "TennisWongChoi/0.1"})
    with urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8-sig")
    return list(csv.DictReader(StringIO(text)))


def ingest_tml_low_tier_history(start_year: int, end_year: int, include_quali: bool = True) -> dict:
    """Import TennisMyLife ATP Challenger (and tour-qualifying) season CSVs.

    Same column layout as Sackmann, stored under provider
    'tennismylife_history' so provenance stays honest. Disjoint from the
    Sackmann backbone (that covers tour-level main draws only), so no
    double-counted matches enter the Elo pool.
    """
    kinds = ["CHALLENGER"] + (["ATP_QUALI"] if include_quali else []) + ["ATP_MAIN"]
    imported = {"files": 0, "matches": 0, "player_rows": 0, "ranking_rows": 0, "skipped_duplicates": 0, "errors": []}
    for kind in kinds:
        for year in range(start_year, end_year + 1):
            url = TML_LOW_TIER_URLS[kind].format(year=year)
            try:
                rows = _download_csv(url)
            except HTTPError as exc:
                if exc.code == 404:
                    imported["errors"].append({"kind": kind, "year": year, "error": "csv_not_found"})
                    continue
                raise
            raw_id = store_raw_response(
                TML_PROVIDER_NAME,
                url,
                {"kind": kind, "year": year},
                rows,
                200,
                "match_history",
                f"{kind}-{year}",
            )
            stats = _ingest_rows(
                "ATP",
                rows,
                raw_id,
                provider=TML_PROVIDER_NAME,
                dedup_against_provider=PROVIDER_NAME if kind == "ATP_MAIN" else None,
            )
            imported["files"] += 1
            imported["matches"] += stats["matches"]
            imported["player_rows"] += stats["player_rows"]
            imported["ranking_rows"] += stats["ranking_rows"]
            imported["skipped_duplicates"] += stats.get("skipped_duplicates", 0)
    return imported


def _ingest_rows(
    tour: str,
    rows: list[dict],
    raw_id: int,
    provider: str = PROVIDER_NAME,
    dedup_against_provider: str | None = None,
) -> dict[str, int]:
    now = utc_now()
    stats = {"matches": 0, "player_rows": 0, "ranking_rows": 0, "skipped_duplicates": 0}
    for row in rows:
        match_date = _parse_tourney_date(row.get("tourney_date"))
        if not match_date:
            continue
        tournament_id = upsert_tournament(
            provider,
            row["tourney_id"],
            row.get("tourney_name") or row["tourney_id"],
            tour,
            raw_id,
            _normalise_level(tour, row.get("tourney_level")),
            _normalise_surface(row.get("surface")),
            None,
        )
        winner_id = get_or_create_player(
            provider,
            str(row["winner_id"]),
            row.get("winner_name") or f"Player {row['winner_id']}",
            tour,
            raw_id,
            current_rank=_int_or_none(row.get("winner_rank")),
        )
        loser_id = get_or_create_player(
            provider,
            str(row["loser_id"]),
            row.get("loser_name") or f"Player {row['loser_id']}",
            tour,
            raw_id,
            current_rank=_int_or_none(row.get("loser_rank")),
        )
        stats["ranking_rows"] += _upsert_rank(winner_id, match_date, tour, row.get("winner_rank"), row.get("winner_rank_points"), raw_id, now, provider)
        stats["ranking_rows"] += _upsert_rank(loser_id, match_date, tour, row.get("loser_rank"), row.get("loser_rank_points"), raw_id, now, provider)
        if dedup_against_provider and _history_pair_exists(dedup_against_provider, winner_id, loser_id, match_date):
            stats["skipped_duplicates"] += 1
            continue
        _insert_history_pair(tour, row, raw_id, winner_id, loser_id, match_date, now, provider)
        stats["matches"] += 1
        stats["player_rows"] += 2
    return stats


def _history_pair_exists(provider: str, winner_id: int, loser_id: int, match_date: str) -> bool:
    """True when another provider already recorded this player pair NEARBY —
    cross-provider dedup so overlapping season files never double-count a
    match in Elo/feature stats. The window is ±10 days (not exact-date)
    because the two sources use different date conventions: Sackmann stamps
    every match with the tournament START date, TML main files carry the
    actual per-day match date (verified: AO 2026 = 13 distinct TML dates vs 1
    Sackmann date; exact-date dedup let 1,027 tour matches through twice).
    A genuinely repeated pairing within 10 days is far rarer than the
    double-count this prevents."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM player_match_history
            WHERE source_provider = ? AND player_id = ? AND opponent_id = ?
              AND match_date BETWEEN date(?, '-10 days') AND date(?, '+10 days')
            LIMIT 1
            """,
            (provider, winner_id, loser_id, match_date, match_date),
        ).fetchone()
    return row is not None


def _insert_history_pair(tour: str, row: dict, raw_id: int, winner_id: int, loser_id: int, match_date: str, now: str, provider: str = PROVIDER_NAME) -> None:
    tournament_level = _normalise_level(tour, row.get("tourney_level"))
    surface = _normalise_surface(row.get("surface"))
    match_format = f"BO{row.get('best_of') or 3}"
    base_match_id = f"{tour}-{row.get('tourney_id')}-{row.get('match_num')}"
    winner_metrics = _metrics(row, "w", "l")
    loser_metrics = _metrics(row, "l", "w")
    winner_deciding = _deciding_set_won(row.get("score"), won=True)
    loser_deciding = _deciding_set_won(row.get("score"), won=False)
    loser_lost_first = _lost_first_set(row.get("score"), won=False)
    winner_lost_first = _lost_first_set(row.get("score"), won=True)
    with get_connection() as conn:
        for payload in (
            {
                "provider_match_id": f"{base_match_id}-winner",
                "player_id": winner_id,
                "opponent_id": loser_id,
                "won": 1,
                "tiebreak_won": _tiebreak_won(row.get("score"), won=True),
                "deciding_set_won": winner_deciding,
                "lost_first_set": winner_lost_first,
                "comeback_after_losing_first_set": bool(winner_lost_first),
                **winner_metrics,
            },
            {
                "provider_match_id": f"{base_match_id}-loser",
                "player_id": loser_id,
                "opponent_id": winner_id,
                "won": 0,
                "tiebreak_won": _tiebreak_won(row.get("score"), won=False),
                "deciding_set_won": loser_deciding,
                "lost_first_set": loser_lost_first,
                "comeback_after_losing_first_set": False,
                **loser_metrics,
            },
        ):
            conn.execute(
                """
                INSERT INTO player_match_history (
                    provider_match_id, player_id, opponent_id, tour, match_date, surface,
                    tournament_external_id, tournament_level, round, format, won,
                    opponent_elo, hold_rate, break_rate, ace_count, double_fault_count,
                    break_points_saved, break_points_faced, break_points_converted,
                    break_points_chances, first_serve_points_won_pct,
                    second_serve_points_won_pct, return_points_won_pct, tiebreak_won,
                    deciding_set_won, lost_first_set, comeback_after_losing_first_set,
                    source_provider, raw_response_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_provider, provider_match_id, player_id) DO UPDATE SET
                    won = excluded.won,
                    hold_rate = excluded.hold_rate,
                    break_rate = excluded.break_rate,
                    ace_count = excluded.ace_count,
                    double_fault_count = excluded.double_fault_count,
                    break_points_saved = excluded.break_points_saved,
                    break_points_faced = excluded.break_points_faced,
                    break_points_converted = excluded.break_points_converted,
                    break_points_chances = excluded.break_points_chances,
                    first_serve_points_won_pct = excluded.first_serve_points_won_pct,
                    second_serve_points_won_pct = excluded.second_serve_points_won_pct,
                    return_points_won_pct = excluded.return_points_won_pct,
                    raw_response_id = excluded.raw_response_id
                """,
                (
                    payload["provider_match_id"],
                    payload["player_id"],
                    payload["opponent_id"],
                    tour,
                    match_date,
                    surface,
                    row["tourney_id"],
                    tournament_level,
                    row.get("round") or "UNKNOWN",
                    match_format,
                    payload["won"],
                    None,
                    payload["hold_rate"],
                    payload["break_rate"],
                    payload["ace_count"],
                    payload["double_fault_count"],
                    payload["break_points_saved"],
                    payload["break_points_faced"],
                    payload["break_points_converted"],
                    payload["break_points_chances"],
                    payload["first_serve_points_won_pct"],
                    payload["second_serve_points_won_pct"],
                    payload["return_points_won_pct"],
                    _bool_to_int(payload["tiebreak_won"]),
                    _bool_to_int(payload["deciding_set_won"]),
                    _bool_to_int(payload["lost_first_set"]),
                    _bool_to_int(payload["comeback_after_losing_first_set"]),
                    provider,
                    raw_id,
                    now,
                ),
            )


def _upsert_rank(player_id: int, ranking_date: str, tour: str, rank: str | None, points: str | None, raw_id: int, now: str, provider: str = PROVIDER_NAME) -> int:
    parsed_rank = _int_or_none(rank)
    if parsed_rank is None:
        return 0
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO rankings_history (
                player_id, ranking_date, tour, rank, ranking_points,
                source_provider, raw_response_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, ranking_date, tour, source_provider) DO UPDATE SET
                rank = excluded.rank,
                ranking_points = excluded.ranking_points,
                raw_response_id = excluded.raw_response_id
            """,
            (player_id, ranking_date, tour, parsed_rank, _int_or_none(points), provider, raw_id, now),
        )
    return 1


def _metrics(row: dict, own_prefix: str, opp_prefix: str) -> dict[str, float | None]:
    svpt = _float_or_none(row.get(f"{own_prefix}_svpt"))
    first_in = _float_or_none(row.get(f"{own_prefix}_1stIn"))
    first_won = _float_or_none(row.get(f"{own_prefix}_1stWon"))
    second_won = _float_or_none(row.get(f"{own_prefix}_2ndWon"))
    sv_gms = _float_or_none(row.get(f"{own_prefix}_SvGms"))
    bp_saved = _float_or_none(row.get(f"{own_prefix}_bpSaved"))
    bp_faced = _float_or_none(row.get(f"{own_prefix}_bpFaced"))
    aces = _float_or_none(row.get(f"{own_prefix}_ace"))
    double_faults = _float_or_none(row.get(f"{own_prefix}_df"))
    opp_svpt = _float_or_none(row.get(f"{opp_prefix}_svpt"))
    opp_first_won = _float_or_none(row.get(f"{opp_prefix}_1stWon"))
    opp_second_won = _float_or_none(row.get(f"{opp_prefix}_2ndWon"))
    opp_sv_gms = _float_or_none(row.get(f"{opp_prefix}_SvGms"))
    opp_bp_saved = _float_or_none(row.get(f"{opp_prefix}_bpSaved"))
    opp_bp_faced = _float_or_none(row.get(f"{opp_prefix}_bpFaced"))
    return {
        "hold_rate": _safe_rate(sv_gms - (bp_faced - bp_saved), sv_gms) if None not in (sv_gms, bp_faced, bp_saved) else None,
        "break_rate": _safe_rate(opp_bp_faced - opp_bp_saved, opp_sv_gms) if None not in (opp_bp_faced, opp_bp_saved, opp_sv_gms) else None,
        "ace_count": aces,
        "double_fault_count": double_faults,
        "break_points_saved": bp_saved,
        "break_points_faced": bp_faced,
        "break_points_converted": opp_bp_faced - opp_bp_saved if None not in (opp_bp_faced, opp_bp_saved) else None,
        "break_points_chances": opp_bp_faced,
        "first_serve_points_won_pct": _safe_rate(first_won, first_in),
        "second_serve_points_won_pct": _safe_rate(second_won, svpt - first_in) if None not in (svpt, first_in, second_won) else None,
        "return_points_won_pct": _safe_rate(opp_svpt - opp_first_won - opp_second_won, opp_svpt) if None not in (opp_svpt, opp_first_won, opp_second_won) else None,
    }


def _parse_tourney_date(value: str | None) -> str | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y%m%d").date().isoformat()


def _normalise_surface(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower()


def _normalise_level(tour: str, value: str | None) -> str:
    raw = str(value or "").upper()
    if raw == "G":
        return "GRAND_SLAM"
    if raw == "F":
        return f"{tour}_FINALS"
    if raw == "M":
        return "ATP_1000" if tour == "ATP" else "WTA_1000"
    if raw == "C":
        # Challenger circuit (TML low-tier files; matches the level the
        # competition-name heuristic resolves for live Sportsbet fixtures).
        return "CHALLENGER"
    if raw in {"250", "500", "1000"}:
        # TML qualifying files carry the parent tour event's numeric level.
        return f"{tour}_{raw}"
    return "UNKNOWN"


def _int_or_none(value: str | None) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        # Dirty cells appear in the TML files (e.g. "2s" in a stat column) —
        # treat as missing rather than aborting the whole season file.
        return None


def _float_or_none(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_rate(numerator: float | None, denominator: float | None) -> float | None:
    if denominator in {None, 0} or numerator is None:
        return None
    return float(numerator) / float(denominator)


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _sets(score: str | None) -> list[tuple[int, int]]:
    if not score:
        return []
    parsed = []
    for token in score.split():
        if token.upper() in {"RET", "W/O", "DEF"}:
            continue
        left_right = token.split("(")[0].split("-")
        if len(left_right) != 2:
            continue
        try:
            parsed.append((int(left_right[0]), int(left_right[1])))
        except ValueError:
            continue
    return parsed


def _lost_first_set(score: str | None, won: bool) -> bool | None:
    sets = _sets(score)
    if not sets:
        return None
    first = sets[0]
    return first[0] < first[1] if won else first[1] < first[0]


def _deciding_set_won(score: str | None, won: bool) -> bool | None:
    sets = _sets(score)
    if len(sets) < 3:
        return None
    last = sets[-1]
    return last[0] > last[1] if won else last[1] > last[0]


def _tiebreak_won(score: str | None, won: bool) -> bool | None:
    sets = _sets(score)
    if not sets:
        return None
    saw = False
    for left, right in sets:
        if max(left, right) >= 7 and abs(left - right) <= 2:
            saw = True
            if won and left > right:
                return True
            if not won and right > left:
                return True
    return False if saw else None
