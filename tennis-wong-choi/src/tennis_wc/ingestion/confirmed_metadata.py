from __future__ import annotations

import re
from dataclasses import dataclass

from tennis_wc.database.db import get_connection
from tennis_wc.ingestion.raw_response_store import store_raw_response, utc_now


CONFIRMED_METADATA_PROVIDER = "curated_tournament_metadata"


@dataclass(frozen=True)
class ConfirmedTournamentMeta:
    tour: str
    tournament_name: str
    level: str
    surface: str | None
    indoor_outdoor: str | None
    source_url: str
    source_note: str
    aliases: tuple[str, ...]


CONFIRMED_TOURNAMENTS: tuple[ConfirmedTournamentMeta, ...] = (
    ConfirmedTournamentMeta(
        tour="ATP",
        tournament_name="ATP Halle",
        level="ATP_500",
        surface="Grass",
        indoor_outdoor="outdoor",
        source_url="https://www.atptour.com/en/tournaments/halle/500/overview",
        source_note="ATP Tour tournament overview",
        aliases=("ATP Halle", "Halle", "Terra Wortmann Open", "Halle Open"),
    ),
    ConfirmedTournamentMeta(
        tour="WTA",
        tournament_name="WTA Berlin",
        level="WTA_500",
        surface="Grass",
        indoor_outdoor="outdoor",
        source_url="https://www.wtatennis.com/tournament/2012/berlin",
        source_note="WTA tournament overview",
        aliases=("WTA Berlin", "Berlin Tennis Open", "Berlin Open", "German Open"),
    ),
    ConfirmedTournamentMeta(
        tour="WTA",
        tournament_name="WTA Nottingham",
        level="WTA_250",
        surface="Grass",
        indoor_outdoor="outdoor",
        source_url="https://www.wtatennis.com/tournament/1080/nottingham",
        source_note="WTA tournament overview",
        aliases=("WTA Nottingham", "Nottingham Open", "Lexus Nottingham Open"),
    ),
    ConfirmedTournamentMeta(
        tour="ATP",
        tournament_name="ATP Nottingham Challenger",
        level="Challenger",
        surface="Grass",
        indoor_outdoor="outdoor",
        source_url="https://www.atptour.com/en/tournaments/nottingham-3/3007/overview",
        source_note="ATP Challenger tournament overview",
        aliases=("ATP Nottingham Challenger", "Nottingham Challenger", "Nottingham Open"),
    ),
    ConfirmedTournamentMeta(
        tour="ATP",
        tournament_name="ATP Parma Challenger",
        level="Challenger",
        surface="Clay",
        indoor_outdoor="outdoor",
        source_url="https://www.atptour.com/en/tournaments/parma/9510/overview",
        source_note="ATP Challenger tournament overview",
        aliases=("ATP Parma Challenger", "Parma Challenger", "Emilia-Romagna Open"),
    ),
    ConfirmedTournamentMeta(
        tour="ATP",
        tournament_name="ATP Poznan Challenger",
        level="Challenger",
        surface="Clay",
        indoor_outdoor="outdoor",
        source_url="https://www.atptour.com/en/tournaments/poznan/786/overview",
        source_note="ATP Challenger tournament overview",
        aliases=("ATP Poznan Challenger", "Poznan Challenger", "Poznań Open", "Poznan Open"),
    ),
    # --- Grass swing (June, Wimbledon warm-up). Verified levels/surfaces. ---
    ConfirmedTournamentMeta(
        tour="ATP",
        tournament_name="ATP Queen's Club (HSBC Championships)",
        level="ATP_500",
        surface="Grass",
        indoor_outdoor="outdoor",
        source_url="https://en.wikipedia.org/wiki/2025_Queen%27s_Club_Championships",
        source_note="ATP 500 grass, Queen's Club London (HSBC Championships)",
        aliases=("HSBC Championships", "Queen's Club Championships", "Queens Club Championships", "Cinch Championships", "Queens Club", "Queen's Club"),
    ),
    ConfirmedTournamentMeta(
        tour="ATP",
        tournament_name="ATP Mallorca Championships",
        level="ATP_250",
        surface="Grass",
        indoor_outdoor="outdoor",
        source_url="https://www.atptour.com/en/tournaments/mallorca/9163/overview",
        source_note="ATP 250 grass, Mallorca",
        aliases=("Mallorca Championships", "Mallorca Open", "ATP Mallorca"),
    ),
    ConfirmedTournamentMeta(
        tour="ATP",
        tournament_name="ATP Eastbourne",
        level="ATP_250",
        surface="Grass",
        indoor_outdoor="outdoor",
        source_url="https://en.wikipedia.org/wiki/2025_Eastbourne_Open",
        source_note="ATP 250 grass, Eastbourne (men)",
        aliases=("Eastbourne International", "Rothesay International", "Eastbourne Open", "ATP Eastbourne"),
    ),
    ConfirmedTournamentMeta(
        tour="WTA",
        tournament_name="WTA Eastbourne",
        level="WTA_500",
        surface="Grass",
        indoor_outdoor="outdoor",
        source_url="https://en.wikipedia.org/wiki/2025_Eastbourne_Open",
        source_note="WTA 500 grass, Eastbourne (women)",
        aliases=("Eastbourne International", "Rothesay International", "Eastbourne Open", "WTA Eastbourne"),
    ),
    ConfirmedTournamentMeta(
        tour="WTA",
        tournament_name="WTA Bad Homburg",
        level="WTA_500",
        surface="Grass",
        indoor_outdoor="outdoor",
        source_url="https://en.wikipedia.org/wiki/Bad_Homburg_Open",
        source_note="WTA 500 grass, Bad Homburg",
        aliases=("Bad Homburg Open", "Bad Homburg", "WTA Bad Homburg"),
    ),
)


def confirmed_competition_meta(competition: str | None, tour: str | None = None) -> ConfirmedTournamentMeta | None:
    key = _metadata_key(competition)
    if not key:
        return None
    comp_tokens = set(_tokens(competition))
    exact: list[ConfirmedTournamentMeta] = []
    fuzzy: list[ConfirmedTournamentMeta] = []
    for meta in CONFIRMED_TOURNAMENTS:
        if key in {_metadata_key(alias) for alias in meta.aliases}:
            exact.append(meta)
            continue
        # Token-subset: every token of a multi-word alias appears as a token in
        # the competition name. Catches sponsor-prefixed feeds, e.g. "VANDA
        # Pharmaceuticals Berlin Tennis Open" -> alias "Berlin Tennis Open".
        # Multi-word only (>=2 tokens) so a single generic token can't false-match
        # (e.g. "Halle" must not match inside "Challenger").
        if any(len(at := set(_tokens(alias))) >= 2 and at <= comp_tokens for alias in meta.aliases):
            fuzzy.append(meta)
    tour_norm = (tour or "").upper() or None
    for bucket in (exact, fuzzy):
        if not bucket:
            continue
        if tour_norm:
            # A tour was requested: only accept a same-tour entry. Some venues run
            # an ATP and a WTA event under one name (e.g. Eastbourne ATP 250 /
            # WTA 500); never apply the wrong tour's level — prefer UNKNOWN.
            same_tour = [meta for meta in bucket if meta.tour.upper() == tour_norm]
            if same_tour:
                return same_tour[0]
            continue
        return bucket[0]
    return None


def backfill_confirmed_metadata_for_date(match_date: str) -> dict:
    raw_id = store_raw_response(
        CONFIRMED_METADATA_PROVIDER,
        "/curated/tournament-metadata",
        {"date": match_date},
        [meta.__dict__ for meta in CONFIRMED_TOURNAMENTS],
        200,
        "tournament_metadata",
        match_date,
    )
    now = utc_now()
    applied = []
    with get_connection() as conn:
        tournament_rows = conn.execute(
            """
            SELECT DISTINCT t.id AS tournament_id, t.name AS tournament_name, m.tour AS match_tour
            FROM matches m
            JOIN tournaments t ON t.id = m.tournament_id
            WHERE m.match_date = ?
            ORDER BY t.name
            """,
            (match_date,),
        ).fetchall()
        for row in tournament_rows:
            meta = confirmed_competition_meta(row["tournament_name"], row["match_tour"])
            if meta is None:
                continue
            conn.execute(
                """
                INSERT INTO tournament_levels (
                    tournament_id, tour, level, surface, indoor_outdoor,
                    source_provider, raw_response_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tournament_id, tour, source_provider) DO UPDATE SET
                    level = excluded.level,
                    surface = excluded.surface,
                    indoor_outdoor = excluded.indoor_outdoor,
                    raw_response_id = excluded.raw_response_id,
                    updated_at = excluded.updated_at
                """,
                (
                    int(row["tournament_id"]),
                    meta.tour,
                    meta.level,
                    meta.surface,
                    meta.indoor_outdoor,
                    CONFIRMED_METADATA_PROVIDER,
                    raw_id,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE matches
                SET tour = ?, updated_at = ?
                WHERE match_date = ?
                  AND tournament_id = ?
                  AND (tour IS NULL OR tour = '' OR tour = 'UNKNOWN')
                """,
                (meta.tour, now, match_date, int(row["tournament_id"])),
            )
            applied.append(
                {
                    "tournament": row["tournament_name"],
                    "tour": meta.tour,
                    "level": meta.level,
                    "surface": meta.surface,
                    "source_url": meta.source_url,
                }
            )

        qualifier_rows = conn.execute(
            """
            SELECT m.id, t.name AS tournament_name
            FROM matches m
            JOIN tournaments t ON t.id = m.tournament_id
            WHERE m.match_date = ?
              AND (m.round IS NULL OR m.round = '' OR m.round = 'UNKNOWN')
              AND lower(t.name) LIKE '%qualifier%'
            """,
            (match_date,),
        ).fetchall()
        for row in qualifier_rows:
            conn.execute("UPDATE matches SET round = 'QUALIFYING' WHERE id = ?", (int(row["id"]),))

    audit = metadata_audit_for_date(match_date)
    return {
        "date": match_date,
        "applied": applied,
        "raw_response_id": raw_id,
        "remaining_gaps": audit["summary"],
        "rounds_from_qualifier_label": len(qualifier_rows) if "qualifier_rows" in locals() else 0,
    }


def metadata_audit_for_date(match_date: str) -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            """
            WITH BestLevels AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY tournament_id, tour
                           ORDER BY
                               (source_provider = ?) DESC,
                               (level IS NOT NULL AND level != '' AND level != 'UNKNOWN' AND level != '未確認') DESC,
                               (surface IS NOT NULL AND surface != '') DESC,
                               id DESC
                       ) AS rn
                FROM tournament_levels
            )
            SELECT
                m.id AS match_id,
                t.name AS tournament,
                p1.name || ' vs ' || p2.name AS match,
                m.round,
                m.tour,
                tl.level,
                tl.surface,
                tl.source_provider AS metadata_source
            FROM matches m
            JOIN tournaments t ON t.id = m.tournament_id
            JOIN players p1 ON p1.id = m.player_a_id
            JOIN players p2 ON p2.id = m.player_b_id
            LEFT JOIN BestLevels tl ON tl.tournament_id = m.tournament_id AND tl.tour = m.tour AND tl.rn = 1
            WHERE m.match_date = ?
            ORDER BY t.name, p1.name, p2.name
            """,
            (CONFIRMED_METADATA_PROVIDER, match_date),
        ).fetchall()
    gaps = []
    summary = {"matches": len(rows), "missing_level": 0, "missing_surface": 0, "missing_round": 0}
    for row in rows:
        missing = []
        reliable_tournament_metadata = row["metadata_source"] == CONFIRMED_METADATA_PROVIDER
        if not reliable_tournament_metadata or not _is_filled(row["level"]):
            missing.append("level")
            summary["missing_level"] += 1
        if not reliable_tournament_metadata or not _is_filled(row["surface"]):
            missing.append("surface")
            summary["missing_surface"] += 1
        if not _is_filled(row["round"]):
            missing.append("round")
            summary["missing_round"] += 1
        if missing:
            gaps.append(
                {
                    "match_id": row["match_id"],
                    "tournament": row["tournament"],
                    "match": row["match"],
                    "missing": missing,
                    "level": row["level"],
                    "surface": row["surface"],
                    "round": row["round"],
                    "metadata_source": row["metadata_source"],
                }
            )
    return {"date": match_date, "summary": summary, "gaps": gaps}


def _metadata_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _tokens(value: str | None) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", str(value or "").lower()) if token]


def _is_filled(value: object) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.upper() not in {"UNKNOWN", "N/A"} and text != "未確認"
