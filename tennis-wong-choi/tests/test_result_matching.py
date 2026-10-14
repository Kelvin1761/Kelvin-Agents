from __future__ import annotations


def test_name_matching_handles_accents_initials_and_last_first():
    from tennis_wc.ingestion.name_matching import match_pair_score, same_player_name

    assert same_player_name("M. Arnaldi", "Matteo Arnaldi")
    assert same_player_name("Jodar, Rafael", "Rafael Jodar")
    assert same_player_name("Tallon Griekspoor", "Tallon Griekspoor")
    assert same_player_name("Eero Vasa", "Eero Vasa")

    score, direction = match_pair_score("Arnaldi, Matteo", "R. Jodar", "Matteo Arnaldi", "Rafael Jodar")
    assert score >= 1.84
    assert direction == "direct"


def test_tennismylife_candidate_files_include_quali_and_future_wta_itf():
    from tennis_wc.ingestion.ingest_tennismylife import _candidate_files

    files = [
        {"name": "2026.csv", "url": "main"},
        {"name": "2026_challenger.csv", "url": "challenger"},
        {"name": "atp_quali/2026_atp_quali.csv", "url": "atp_quali"},
        {"name": "wta_quali/2026_wta_quali.csv", "url": "wta_quali"},
        {"name": "itf/2026_itf.csv", "url": "itf"},
        {"name": "ongoing_tourneys.csv", "url": "ongoing"},
        {"name": "challenger_ongoing_tourneys.csv", "url": "challenger_ongoing"},
        {"name": "2025.csv", "url": "old"},
    ]

    selected = _candidate_files(files, {"2026-05-10"})
    assert [item["url"] for item in selected] == [
        "main",
        "challenger",
        "atp_quali",
        "wta_quali",
        "itf",
        "ongoing",
        "challenger_ongoing",
    ]


def test_bsd_score_payload_extracts_aces_and_double_faults():
    from tennis_wc.betting.ledger import _score_from_bsd_raw

    payload = _score_from_bsd_raw(
        {
            "sets_detail": [{"p1": 6, "p2": 4}, {"p1": 7, "p2": 5}],
            "p1_aces": 9,
            "p2_aces": 4,
            "p1_df": 2,
            "p2_df": 5,
        }
    )

    assert payload["player_a_aces"] == 9
    assert payload["player_b_aces"] == 4
    assert payload["player_a_double_faults"] == 2
    assert payload["player_b_double_faults"] == 5


def test_result_lookup_dates_include_adjacent_days():
    from tennis_wc.betting.ledger import _result_lookup_dates

    assert _result_lookup_dates("2026-05-11") == ["2026-05-11", "2026-05-10", "2026-05-12"]


def test_tennismylife_rows_are_matched_on_the_tournament_week():
    """The CSV keys rows by tournament START date, not by match date.

    A one-day window therefore only ever admitted the opening rounds: of 18
    pending ace fixtures present in 2026_wta.csv on 2026-08-09, two fell inside
    it, and the rest -- 2 to 10 days into their event -- were skipped without a
    word. That is why player_aces still had 65 outcomes after months of runs.
    """
    from datetime import date, timedelta

    from tennis_wc.ingestion.ingest_tennismylife import (
        TOURNAMENT_WINDOW_DAYS,
        _in_tournament_window,
    )

    wanted = {"2026-06-17"}
    # Berlin starts 2026-06-15; a round-of-16 match two days in must be kept.
    assert _in_tournament_window("2026-06-15", wanted)
    assert _in_tournament_window("2026-06-17", wanted)
    # A day either side covers timezone drift between feed and fixture.
    assert _in_tournament_window("2026-06-18", wanted)
    # A tournament that finished long before is not a candidate.
    assert not _in_tournament_window("2026-05-01", wanted)
    assert not _in_tournament_window("2026-06-19", wanted)
    boundary = date.fromisoformat("2026-06-17") - timedelta(days=TOURNAMENT_WINDOW_DAYS)
    assert _in_tournament_window(boundary.isoformat(), wanted)
    assert not _in_tournament_window((boundary - timedelta(days=1)).isoformat(), wanted)
    assert not _in_tournament_window(None, wanted)


def test_tennismylife_retains_the_exact_considered_rows_as_result_provenance(
    monkeypatch,
):
    from tennis_wc.ingestion import ingest_tennismylife as module

    row = {
        "tourney_date": "20260905",
        "winner_name": "Player A",
        "loser_name": "Player B",
    }
    monkeypatch.setattr(
        module,
        "_download_json",
        lambda _url: {"files": [{"name": "2026.csv", "url": "https://source/2026.csv"}]},
    )
    monkeypatch.setattr(module, "_download_csv", lambda _url: [row])
    observed = {}

    def fake_raw(provider, endpoint, params, response, status, **kwargs):
        observed["raw"] = (provider, endpoint, params, response, status, kwargs)
        return 77

    def fake_store(rows, wanted_dates, *, raw_response_id=None):
        observed["store"] = (rows, wanted_dates, raw_response_id)
        return 1, 0, 1, 0

    monkeypatch.setattr(module, "store_raw_response", fake_raw, raising=False)
    monkeypatch.setattr(module, "_store_rows", fake_store)

    summary = module.ingest_tennismylife_results("2026-09-05")

    assert summary["results_imported"] == 1
    assert observed["raw"] == (
        "tennismylife",
        "results/2026.csv",
        {"file": "2026.csv", "wanted_dates": ["2026-09-05"]},
        [row],
        200,
        {"entity_type": "match_results", "entity_external_id": "2026-09-05"},
    )
    assert observed["store"] == ([row], {"2026-09-05"}, 77)


def test_primary_result_provider_retains_rows_and_threads_raw_id_to_resolvers(
    monkeypatch,
):
    from tennis_wc.betting import ledger
    from tennis_wc.ingestion import ingest_tennisexplorer, ingest_tennismylife

    rows = [
        {
            "id": "m1",
            "match_date": lookup_date,
            "player_name": "Player A",
            "opponent_name": "Player B",
            "won": True,
        }
        for lookup_date in ("2026-09-05", "2026-09-04", "2026-09-06")
    ]

    class Provider:
        provider_name = "composite"

        def fetch_historical_matches(self, start, _end):
            return [row for row in rows if row["match_date"] == start]

    observed = {}
    monkeypatch.setattr(ledger, "_ensure_tracking_schema", lambda: None)
    monkeypatch.setattr(ledger, "get_tennis_provider", lambda: Provider())
    monkeypatch.setattr(
        ledger,
        "store_raw_response",
        lambda provider, endpoint, params, response, status, **kwargs: (
            observed.setdefault(
                "raw", (provider, endpoint, params, response, status, kwargs)
            )
            and 88
        ),
        raising=False,
    )
    monkeypatch.setattr(
        ledger,
        "_store_result_rows",
        lambda date, found, provider, raw_response_id=None: observed.setdefault(
            "store", (date, found, provider, raw_response_id)
        )
        and 3,
    )
    monkeypatch.setattr(
        ledger,
        "_resolve_pending_match_results",
        lambda date, found, provider, raw_response_id=None: observed.setdefault(
            "resolver", (date, found, provider, raw_response_id)
        )
        and {
            "event_id_tracked": 0,
            "event_result_imported": 0,
            "event_result_errors": [],
            "provider_rows_imported": 0,
            "local_history_imported": 0,
        },
    )
    monkeypatch.setattr(
        ingest_tennismylife, "ingest_tennismylife_results", lambda _date: {}
    )
    monkeypatch.setattr(
        ingest_tennisexplorer, "ingest_tennisexplorer_results", lambda _date: {}
    )

    result = ledger.fetch_results_for_date("2026-09-05")

    assert result["imported"] == 3
    assert observed["raw"] == (
        "composite",
        "historical_matches/2026-09-05",
        {"lookup_dates": ["2026-09-05", "2026-09-04", "2026-09-06"]},
        rows,
        200,
        {"entity_type": "match_results", "entity_external_id": "2026-09-05"},
    )
    assert observed["store"][3] == 88
    assert observed["resolver"][3] == 88


def test_event_result_provider_retains_exact_response_and_threads_raw_id(
    monkeypatch,
):
    from tennis_wc.betting import ledger
    from tennis_wc import providers

    match = {
        "id": 1,
        "market_event_id": "event-123",
        "player_a_id": 10,
        "player_b_id": 20,
        "player_a_name": "Player A",
        "player_b_name": "Player B",
    }
    result = {
        "winner_name": "Player A",
        "loser_name": "Player B",
        "status": "complete",
    }

    class Provider:
        provider_name = "sportsbet"

        def fetch_event_result(self, event_id):
            assert event_id == "event-123"
            return result

    observed = {}
    monkeypatch.setattr(ledger, "_pending_result_matches", lambda _date: [match])
    monkeypatch.setattr(providers, "get_odds_provider", lambda: Provider())
    monkeypatch.setattr(
        ledger,
        "store_raw_response",
        lambda provider, endpoint, params, response, status, **kwargs: (
            observed.setdefault(
                "raw", (provider, endpoint, params, response, status, kwargs)
            )
            and 99
        ),
    )
    monkeypatch.setattr(
        ledger,
        "_insert_resolved_result_from_names",
        lambda *args, **kwargs: observed.setdefault("insert", (args, kwargs)) and 1,
    )

    summary = ledger._resolve_pending_from_event_provider("2026-09-05")

    assert summary == {
        "event_id_tracked": 1,
        "event_result_imported": 1,
        "event_result_errors": [],
    }
    assert observed["raw"] == (
        "sportsbet",
        "event_result/event-123",
        {"event_id": "event-123", "match_date": "2026-09-05"},
        result,
        200,
        {"entity_type": "match_result", "entity_external_id": "event-123"},
    )
    assert observed["insert"][1]["raw_response_id"] == 99
