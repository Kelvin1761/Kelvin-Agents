"""Unit tests for the Sackmann/TML history ingestion helpers (pure functions)."""


def test_normalise_level_maps_low_tier_codes():
    from tennis_wc.sources.ingest_sackmann import _normalise_level

    assert _normalise_level("ATP", "C") == "CHALLENGER"
    assert _normalise_level("ATP", "250") == "ATP_250"
    assert _normalise_level("WTA", "500") == "WTA_500"
    assert _normalise_level("ATP", "G") == "GRAND_SLAM"
    assert _normalise_level("ATP", "M") == "ATP_1000"
    assert _normalise_level("WTA", "M") == "WTA_1000"
    assert _normalise_level("ATP", "A") == "UNKNOWN"


def test_numeric_parsers_tolerate_dirty_tml_cells():
    from tennis_wc.sources.ingest_sackmann import _float_or_none, _int_or_none

    # TML season files contain malformed stat cells (e.g. "2s") — these must
    # read as missing, not abort the whole file.
    assert _float_or_none("2s") is None
    assert _int_or_none("2s") is None
    assert _float_or_none("12") == 12.0
    assert _int_or_none("12.0") == 12
    assert _float_or_none("") is None
    assert _int_or_none(None) is None


def test_low_tier_history_skips_rows_with_missing_provider_identity():
    from tennis_wc.sources.ingest_sackmann import _has_valid_player_identities, _ingest_rows

    invalid_row = {
        "winner_id": "",
        "winner_name": "Jordan Lee",
        "loser_id": "12345",
        "loser_name": "Valid Player",
    }
    assert not _has_valid_player_identities(invalid_row)
    assert _ingest_rows("ATP", [invalid_row], raw_id=1) == {
        "matches": 0,
        "player_rows": 0,
        "ranking_rows": 0,
        "skipped_duplicates": 0,
        "skipped_invalid_identities": 1,
        "held_identity_conflicts": 0,
        "held": [],
    }
    assert _has_valid_player_identities(
        {
            "winner_id": "67890",
            "winner_name": "Jordan Lee",
            "loser_id": "12345",
            "loser_name": "Valid Player",
        }
    )


def test_elo_builder_consumes_both_history_providers():
    from tennis_wc.sources.ingest_sackmann import HISTORY_PROVIDERS

    assert "jeff_sackmann" in HISTORY_PROVIDERS
    assert "tennismylife_history" in HISTORY_PROVIDERS


def test_one_identity_conflict_holds_that_match_and_keeps_the_rest(monkeypatch):
    """2026-10-28..11-26: TML KE64 'Toby Samuel' -> 'Stefan Kozlov' aborted the whole season file
    on every run, so no Challenger / ATP history arrived for a month. Hold the row, keep the rest."""
    from tennis_wc.sources import ingest_sackmann as s
    from tennis_wc.sources.entity_mapping import PlayerIdentityConflict

    rows = [{"winner_id": str(w), "winner_name": f"P{w}", "loser_id": str(w + 100), "loser_name": f"Q{w}",
             "tourney_id": "2026-9999", "tourney_date": "20261116", "tourney_name": "X"} for w in (1, 2, 3)]
    inserted = []

    def fake_player(provider, pid, name, tour, raw_id, current_rank=None):
        if pid == "2":
            raise PlayerIdentityConflict("provider player identity changed: tennismylife_history/2: 'A' -> 'B'")
        return int(pid)

    monkeypatch.setattr(s, "upsert_tournament", lambda *a, **k: 1)
    monkeypatch.setattr(s, "get_or_create_player", fake_player)
    monkeypatch.setattr(s, "_upsert_rank", lambda *a, **k: 0)
    monkeypatch.setattr(s, "_insert_history_pair", lambda tour, row, *a, **k: inserted.append(row["winner_id"]))
    stats = s._ingest_rows("ATP", rows, raw_id=1, provider=s.TML_PROVIDER_NAME)
    assert inserted == ["1", "3"]
    assert stats["matches"] == 2 and stats["held_identity_conflicts"] == 1
    assert stats["held"][0]["winner_id"] == "2" and "identity changed" in stats["held"][0]["detail"]
