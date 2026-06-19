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
    from tennis_wc.ingestion.ingest_tennismylife import _expanded_dates

    assert _result_lookup_dates("2026-05-11") == ["2026-05-11", "2026-05-10", "2026-05-12"]
    assert _expanded_dates({"2026-05-11"}) == {"2026-05-10", "2026-05-11", "2026-05-12"}
