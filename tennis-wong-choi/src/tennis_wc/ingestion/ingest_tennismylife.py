from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from io import StringIO
from urllib.request import Request, urlopen

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now
from tennis_wc.ingestion.name_matching import match_pair_score, same_player_name


PROVIDER_NAME = "tennismylife"
MANIFEST_URL = "https://stats.tennismylife.org/api/data-files"


def ingest_tennismylife_results(start_date: str, end_date: str | None = None) -> dict:
    end_date = end_date or start_date
    wanted_dates = _date_range(start_date, end_date)
    manifest = _download_json(MANIFEST_URL)
    files = _candidate_files(manifest.get("files", []), wanted_dates)
    summary = {"files": 0, "rows_seen": 0, "results_imported": 0, "unmatched_rows": 0, "errors": []}
    for file_info in files:
        try:
            rows = _download_csv(file_info["url"])
        except Exception as exc:
            summary["errors"].append({"file": file_info.get("name"), "error": str(exc)})
            continue
        imported, unmatched, seen, adjacent_seen = _store_rows(rows, wanted_dates)
        summary["files"] += 1
        summary["rows_seen"] += seen
        summary["lookup_rows_seen"] = summary.get("lookup_rows_seen", 0) + seen + adjacent_seen
        summary["adjacent_rows_seen"] = summary.get("adjacent_rows_seen", 0) + adjacent_seen
        summary["results_imported"] += imported
        summary["unmatched_rows"] += unmatched
    return summary


def _download_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "TennisWongChoi/0.1"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_csv(url: str) -> list[dict]:
    request = Request(url, headers={"User-Agent": "TennisWongChoi/0.1"})
    with urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8-sig")
    return list(csv.DictReader(StringIO(text)))


def _candidate_files(files: list[dict], wanted_dates: set[str]) -> list[dict]:
    years = {item[:4] for item in wanted_dates}
    candidates = []
    for file_info in files:
        name = str(file_info.get("name") or "")
        if _is_live_candidate(name) or any(_is_year_candidate(name, year) for year in years):
            candidates.append(file_info)
    return candidates


def _is_live_candidate(name: str) -> bool:
    lower = name.lower()
    # wta_ongoing_tourneys.csv was published all along and simply never read,
    # so in-progress WTA tournaments had no live result feed at all -- the
    # yearly WTA file only lands once an event is over.  Nothing errored; the
    # rows just never arrived.
    return lower in {
        "ongoing_tourneys.csv",
        "challenger_ongoing_tourneys.csv",
        "wta_ongoing_tourneys.csv",
    }


def _is_year_candidate(name: str, year: str) -> bool:
    lower = name.lower()
    return (
        lower == f"{year}.csv"
        or lower == f"{year}_challenger.csv"
        or lower.endswith(f"{year}_atp_quali.csv")
        or lower.endswith(f"{year}_wta_quali.csv")
        or lower.endswith(f"{year}_wta.csv")
        or lower.endswith(f"{year}_itf.csv")
    )


def _store_rows(rows: list[dict], wanted_dates: set[str]) -> tuple[int, int, int, int]:
    now = utc_now()
    imported = 0
    unmatched = 0
    seen = 0
    adjacent_seen = 0
    with get_connection() as conn:
        _ensure_score_column(conn)
        fixtures = _fixtures_for_dates(conn, wanted_dates)
        for row in rows:
            csv_match_date = _csv_date(row.get("tourney_date"))
            if not _in_tournament_window(csv_match_date, wanted_dates):
                continue
            if csv_match_date in wanted_dates:
                seen += 1
            else:
                adjacent_seen += 1
            match = _match_by_names_for_dates(
                conn, wanted_dates, row.get("winner_name"), row.get("loser_name"),
                fixtures=fixtures,
            )
            if not match:
                unmatched += 1
                continue
            winner_player_id = match["player_a_id"] if same_player_name(row.get("winner_name"), match["player_a_name"]) else match["player_b_id"]
            score_json = json.dumps(_score_payload(row, match), sort_keys=True)
            conn.execute(
                """
                INSERT INTO match_results (match_id, winner_player_id, score_json, source_provider, raw_response_id, created_at)
                VALUES (?, ?, ?, ?, NULL, ?)
                ON CONFLICT(match_id, source_provider) DO UPDATE SET
                    winner_player_id = excluded.winner_player_id,
                    score_json = excluded.score_json,
                    created_at = excluded.created_at
                """,
                (match["id"], winner_player_id, score_json, PROVIDER_NAME, now),
            )
            imported += 1
    return imported, unmatched, seen, adjacent_seen


# The CSV keys every row by the TOURNAMENT START date, not the date the match
# was played, so a one-day window only ever admits the opening rounds. Of 18
# pending ace fixtures found in 2026_wta.csv on 2026-08-09, exactly 2 fell
# inside the old +/-1 day window; the rest sat 2 to 10 days into their event
# and were silently skipped, which is why player_aces had 65 outcomes after
# months of running. Grand slams run 14 days, so allow a fortnight and a bit.
TOURNAMENT_WINDOW_DAYS = 20


def _in_tournament_window(csv_date: str | None, wanted_dates: set[str]) -> bool:
    """True when a match on one of ``wanted_dates`` could belong to this event."""
    if not csv_date:
        return False
    try:
        start = date.fromisoformat(csv_date)
    except ValueError:
        return False
    for item in wanted_dates:
        try:
            offset = (date.fromisoformat(item) - start).days
        except ValueError:
            continue
        # One day before covers a fixture dated in a timezone ahead of the feed.
        if -1 <= offset <= TOURNAMENT_WINDOW_DAYS:
            return True
    return False


def _score_payload(row: dict, match: dict) -> dict:
    winner_is_a = same_player_name(row.get("winner_name"), match["player_a_name"])
    loser_is_a = same_player_name(row.get("loser_name"), match["player_a_name"])
    sets = _sets(row.get("score"), winner_is_a)
    payload = _score_summary(sets)
    payload.update(
        {
            "player_a_aces": _int_or_none(row.get("w_ace" if winner_is_a else "l_ace" if loser_is_a else "")),
            "player_b_aces": _int_or_none(row.get("l_ace" if winner_is_a else "w_ace" if loser_is_a else "")),
            "player_a_double_faults": _int_or_none(row.get("w_df" if winner_is_a else "l_df" if loser_is_a else "")),
            "player_b_double_faults": _int_or_none(row.get("l_df" if winner_is_a else "w_df" if loser_is_a else "")),
            "player_a_bp_saved": _int_or_none(row.get("w_bpSaved" if winner_is_a else "l_bpSaved" if loser_is_a else "")),
            "player_b_bp_saved": _int_or_none(row.get("l_bpSaved" if winner_is_a else "w_bpSaved" if loser_is_a else "")),
            "player_a_bp_faced": _int_or_none(row.get("w_bpFaced" if winner_is_a else "l_bpFaced" if loser_is_a else "")),
            "player_b_bp_faced": _int_or_none(row.get("l_bpFaced" if winner_is_a else "w_bpFaced" if loser_is_a else "")),
            # `or` and not a plain assignment: `_score_summary` has already
            # set this True for a scoreline that cannot have happened (a
            # completed match cannot end level on sets), and an unconditional
            # overwrite here silently undid that guard two lines after it was
            # written. Four rows reached the database reading sets 0-0 with
            # `retired: false`, which is the exact state the summary exists to
            # prevent -- they tripped the critical `impossible_scoreline` check
            # and were saved from grading real bets only by the separate
            # `incomplete_scoreline` flag, which happens not to be in this dict.
            "retired": _is_retired_score(row.get("score")) or bool(payload.get("retired")),
            "source": PROVIDER_NAME,
        }
    )
    return payload


def _score_summary(sets: list[dict]) -> dict:
    a_sets = sum(1 for item in sets if item["player_a_games"] > item["player_b_games"])
    b_sets = sum(1 for item in sets if item["player_b_games"] > item["player_a_games"])
    summary = {
        "player_a_sets": a_sets,
        "player_b_sets": b_sets,
        "total_sets": len(sets),
        "player_a_games": sum(item["player_a_games"] for item in sets),
        "player_b_games": sum(item["player_b_games"] for item in sets),
        "sets": sets,
    }
    # A completed match cannot end level on sets. An unparseable score string
    # produced 0-0, and a walkover or mid-match retirement produced 1-1 or 0-0,
    # and all of them were stored as finished: 9 such results existed and 22
    # props had been graded against them -- a prop settled on a scoreline that
    # never happened is worse than one left pending. Flag them so settlement
    # voids rather than grades.
    if a_sets == b_sets:
        summary["retired"] = True
        summary["incomplete_scoreline"] = True
    return summary


def _sets(score: str | None, winner_is_player_a: bool) -> list[dict]:
    if not score:
        return []
    parsed = []
    for token in str(score).split():
        if token.upper() in {"RET", "W/O", "DEF"}:
            continue
        parts = token.split("(")[0].split("-")
        if len(parts) != 2:
            continue
        try:
            winner_games = int(parts[0])
            loser_games = int(parts[1])
        except ValueError:
            continue
        parsed.append(
            {
                "player_a_games": winner_games if winner_is_player_a else loser_games,
                "player_b_games": loser_games if winner_is_player_a else winner_games,
            }
        )
    return parsed


def _is_retired_score(score: str | None) -> bool:
    return "RET" in str(score or "").upper().split()


def _match_by_names(conn, match_date: str, player_name: str | None, opponent_name: str | None):
    return _match_by_names_for_dates(conn, {match_date}, player_name, opponent_name)


def _fixtures_for_dates(conn, match_dates: set[str]) -> list:
    """Fixtures on the wanted dates, fetched once per import.

    The tournament window admits far more CSV rows than the old one-day filter,
    and re-running this query per row made the import quadratic enough to time
    out on a season backfill.
    """
    return _match_by_names_for_dates(conn, match_dates, None, None, fixtures_only=True)


def _match_by_names_for_dates(conn, match_dates: set[str], player_name: str | None,
                              opponent_name: str | None, fixtures_only: bool = False,
                              fixtures: list | None = None):
    if fixtures is not None:
        rows = fixtures
    else:
        placeholders = ",".join("?" for _ in match_dates)
        rows = conn.execute(
            f"""
        SELECT m.id, m.player_a_id, m.player_b_id, pa.name AS player_a_name, pb.name AS player_b_name
        FROM matches m
        JOIN players pa ON pa.id = m.player_a_id
        JOIN players pb ON pb.id = m.player_b_id
        WHERE m.match_date IN ({placeholders})
        """,
            tuple(sorted(match_dates)),
        ).fetchall()
    if fixtures_only:
        return rows
    best_row = None
    best_score = 0.0
    runner_up = 0.0
    for row in rows:
        score, _direction = match_pair_score(player_name, opponent_name, row["player_a_name"], row["player_b_name"])
        if score > best_score:
            runner_up = best_score
            best_row = row
            best_score = score
        elif score > runner_up:
            runner_up = score
    # The tournament window admits several days of fixtures at once, so a pair
    # that meets twice inside it would otherwise be resolved by "best score
    # wins" -- and the loser of that comparison gets settled against the wrong
    # match. Refuse instead.
    if best_score - runner_up < 0.02:
        return None
    return best_row


def _date_range(start_date: str, end_date: str) -> set[str]:
    current = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    values = set()
    while current <= end:
        values.add(current.isoformat())
        current += timedelta(days=1)
    return values


def _csv_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value)
    if len(raw) != 8:
        return None
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _same_name(left: str | None, right: str | None) -> bool:
    return same_player_name(left, right)


def _int_or_none(value: str | None) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _ensure_score_column(conn) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(match_results)").fetchall()}
    if "score_json" not in columns:
        conn.execute("ALTER TABLE match_results ADD COLUMN score_json TEXT")
