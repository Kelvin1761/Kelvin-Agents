"""Unit tests for the Sackmann/TML history ingestion helpers (pure functions)."""


def test_normalise_level_maps_low_tier_codes():
    from tennis_wc.ingestion.ingest_sackmann import _normalise_level

    assert _normalise_level("ATP", "C") == "CHALLENGER"
    assert _normalise_level("ATP", "250") == "ATP_250"
    assert _normalise_level("WTA", "500") == "WTA_500"
    assert _normalise_level("ATP", "G") == "GRAND_SLAM"
    assert _normalise_level("ATP", "M") == "ATP_1000"
    assert _normalise_level("WTA", "M") == "WTA_1000"
    assert _normalise_level("ATP", "A") == "UNKNOWN"


def test_numeric_parsers_tolerate_dirty_tml_cells():
    from tennis_wc.ingestion.ingest_sackmann import _float_or_none, _int_or_none

    # TML season files contain malformed stat cells (e.g. "2s") — these must
    # read as missing, not abort the whole file.
    assert _float_or_none("2s") is None
    assert _int_or_none("2s") is None
    assert _float_or_none("12") == 12.0
    assert _int_or_none("12.0") == 12
    assert _float_or_none("") is None
    assert _int_or_none(None) is None


def test_low_tier_history_skips_rows_with_missing_provider_identity():
    from tennis_wc.ingestion.ingest_sackmann import _has_valid_player_identities, _ingest_rows

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
    from tennis_wc.ingestion.ingest_sackmann import HISTORY_PROVIDERS

    assert "jeff_sackmann" in HISTORY_PROVIDERS
    assert "tennismylife_history" in HISTORY_PROVIDERS
