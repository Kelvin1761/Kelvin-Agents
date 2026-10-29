from __future__ import annotations

import json

import pytest

from conftest import configure_test_db
from tennis_wc.ingestion.confirmed_metadata import (
    CONFIRMED_METADATA_PROVIDER,
    backfill_confirmed_metadata_for_date,
    confirmed_competition_meta,
    metadata_audit_for_date,
)
from tennis_wc.ingestion.sportsbet_fixture_mapping import sportsbet_competition_meta


NAME = "Toray Pan Pacific Open Tennis"


@pytest.mark.parametrize("stamp", ["2026-10-26", "2026-10-29", "2026-11-01"])
@pytest.mark.parametrize("name", [NAME, NAME + " Tournament", "Toray Pan Pacific Open"])
def test_toray_official_edition_dates(stamp, name):
    meta = confirmed_competition_meta(name, "WTA", match_date=stamp)
    assert (meta.tour, meta.level, meta.surface, meta.indoor_outdoor) == (
        "WTA", "WTA_500", "Hard", "outdoor",
    )
    assert meta.source_url == "https://www.wtatennis.com/tournaments/1056/tokyo/2026"
    mapped = sportsbet_competition_meta(name, stamp)
    assert mapped.is_mvp_supported and mapped.tour == "WTA" and mapped.surface == "Hard"


@pytest.mark.parametrize("stamp", [None, "", "bad", "2026-02-30", "2026-10-25", "2026-11-02", "2025-10-29", "2027-10-29"])
def test_toray_does_not_infer_other_dates(stamp):
    assert confirmed_competition_meta(NAME, "WTA", match_date=stamp) is None
    assert not sportsbet_competition_meta(NAME, stamp).is_mvp_supported


@pytest.mark.parametrize("name,tour", [
    (NAME, "ATP"), ("Tokyo", "WTA"), ("Japan Open", "ATP"),
    (NAME + " Doubles", "WTA"), (NAME + " Qualifiers", "WTA"),
])
def test_toray_does_not_match_other_events(name, tour):
    assert confirmed_competition_meta(name, tour, match_date="2026-10-29") is None


def test_toray_backfill_keeps_source_and_bounds_persisted_context(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.features.feature_builder import _match_context

    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO tournaments (id, name, tour, external_id, source_provider, created_at, updated_at) "
            "VALUES (1, ?, 'WTA', '264-2026', 'test', 'now', 'now')", (NAME,),
        )
        for pid in (1, 2):
            conn.execute(
                "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
                "VALUES (?, ?, 'WTA', 'test', 'now', 'now')", (pid, f"Player {pid}"),
            )
        conn.execute(
            "INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id, player_a_id, "
            "player_b_id, round, source_provider, created_at, updated_at) "
            "VALUES (1, '185660', 'WTA', '2026-10-29', 1, 1, 2, 'R16', 'test', 'now', 'now')",
        )
        conn.execute(
            "INSERT INTO tournament_levels (tournament_id, tour, level, surface, source_provider, "
            "raw_response_id, created_at, updated_at) VALUES (1, 'WTA', 'UNKNOWN', NULL, 'composite', 0, 'now', 'now')",
        )

    result = backfill_confirmed_metadata_for_date("2026-10-29")
    assert len(result["applied"]) == 1
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM tournament_levels ORDER BY id").fetchall()
        assert len(rows) == 2
        assert rows[0]["surface"] is None and rows[0]["level"] == "UNKNOWN"
        curated = dict(rows[1])
        assert curated["source_provider"] == CONFIRMED_METADATA_PROVIDER
        raw = conn.execute("SELECT * FROM raw_api_responses WHERE id=?", (curated["raw_response_id"],)).fetchone()
        assert json.loads(raw["request_params_json"]) == {"date": "2026-10-29"}
        edition = next(m for m in json.loads(raw["response_json"]) if m["tournament_name"] == NAME)
        assert edition["valid_from"] == "2026-10-26" and edition["valid_until"] == "2026-11-01"
        match = dict(conn.execute("SELECT * FROM matches WHERE id=1").fetchone())
    context = _match_context(match, {"name": NAME}, curated)
    assert context["surface"]["value"] == "Hard" and context["level"]["value"] == "WTA_500"
    assert context["surface"]["provenance"]["raw_response_id"] == raw["id"]
    # The table is keyed by tournament, not date: verify a later reuse cannot
    # silently turn an unverified edition into hard/WTA500.
    for stamp in ("2025-10-29", "2026-11-02", "2027-10-29"):
        context = _match_context({**match, "match_date": stamp}, {"name": NAME}, curated)
        assert context["surface"]["value"] is None and context["level"]["value"] == "UNKNOWN"
        assert "tournament_metadata_outside_confirmed_dates" in context["surface"]["provenance"]["warnings"]
    with get_connection() as conn:
        conn.execute("UPDATE matches SET match_date='2027-10-29' WHERE id=1")
    audit = metadata_audit_for_date("2027-10-29")
    assert audit["summary"]["missing_surface"] == 1 and audit["summary"]["missing_level"] == 1
    assert not backfill_confirmed_metadata_for_date("2027-10-29")["applied"]


def test_undated_existing_metadata_is_unchanged():
    before = confirmed_competition_meta("ATP Halle", "ATP")
    assert confirmed_competition_meta("ATP Halle", "ATP", match_date="2027-06-01") == before
    assert before.level == "ATP_500" and before.surface == "Grass"
