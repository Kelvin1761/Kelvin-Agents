"""Complete dated ATP publication: preserve ties, reject loss or another product."""
from copy import deepcopy
import pytest

from tennis_wc.providers.official_ranking_provider import (
    OfficialRankingFetchError, OfficialRankingProvider, _parse_atp_numeric_pdf_pages,
)


def pages():
    return [
        "Rankings Date: Oct 26, 2026 Total Grand Slam Masters Other Tourns. Points Next\n"
        "Rank # Player Natl. Points Points 1000 Points Points Played Dropping Best\n"
        "1 Sinner, Jannik (ITA) 10450 2850 6000 1600 16 1000 0\n"
        "Page 1 of 2 Rankings/ Numerical Order/ Complete/ Singles Report as of Oct 25, 2026",
        "Rankings Date: Oct 26, 2026\n"
        "2T Rublev, Andrey 4 1 2 1 7 0 0\n"
        "2T van de Zandschulp, Botic (NED) 4 1 2 1 7 0 0\n"
        "Page 2 of 2 Rankings/ Numerical Order/ Complete/ Singles Report as of Oct 25, 2026",
    ]


def test_complete_source_keeps_published_ties_missing_country_and_effective_date():
    rows = _parse_atp_numeric_pdf_pages(pages(), "2026-10-30")
    assert len(rows) == 3 and [r["rank"] for r in rows] == [1, 2, 2]
    assert {r["ranking_date"] for r in rows} == {"2026-10-26"}
    assert rows[0]["ranking_points"] == 10450
    assert rows[1]["player_name"] == "Andrey Rublev" and rows[1]["raw"]["nationality"] is None
    assert rows[2]["player_name"] == "Botic Van De Zandschulp"
    assert rows[1]["raw"]["tied"] is True


@pytest.mark.parametrize("fault", ["missing_page", "reordered", "mixed_dates", "missing_date", "wrong_product",
                                   "bad_row", "missing_row", "points_columns", "empty_page"])
def test_partial_or_ambiguous_publications_reject_whole_batch(fault):
    text = deepcopy(pages())
    if fault == "missing_page": text = text[:1]
    if fault == "reordered": text.reverse()
    if fault == "mixed_dates": text[1] = text[1].replace("Oct 26", "Oct 19")
    if fault == "missing_date": text[1] = text[1].replace("Rankings Date:", "Not a source date:")
    if fault == "wrong_product": text[1] = text[1].replace("Singles", "Doubles")
    if fault == "bad_row": text[1] = text[1].replace("4 1 2 1 7 0 0", "4 unreadable 7 0 0", 1)
    if fault == "missing_row": text[0] = text[0].replace("1 Sinner, Jannik (ITA) 10450 2850 6000 1600 16 1000 0", "")
    if fault == "points_columns": text[0] = text[0].replace("10450 2850", "10451 2850")
    if fault == "empty_page": text[1] = "\n".join(x for x in text[1].splitlines() if not x.startswith("2T"))
    with pytest.raises(OfficialRankingFetchError):
        _parse_atp_numeric_pdf_pages(text, "2026-10-30")


def test_future_publication_cannot_be_used_for_an_earlier_date():
    with pytest.raises(OfficialRankingFetchError, match="after requested"):
        _parse_atp_numeric_pdf_pages(pages(), "2026-10-25")


def test_official_pdf_is_preferred_over_dated_uts(monkeypatch):
    provider = OfficialRankingProvider()
    rows = _parse_atp_numeric_pdf_pages(pages(), "2026-10-29")
    monkeypatch.setattr(provider, "_fetch_atp_numeric_pdf", lambda *a: rows)
    monkeypatch.setattr(provider, "_fetch_atp_uts", lambda *a: pytest.fail("fresh complete official PDF must be preferred"))
    assert provider.fetch_rankings("ATP", "2026-10-29") == rows


def test_a_stale_pdf_falls_back_but_retains_the_rejected_source(monkeypatch):
    provider = OfficialRankingProvider()
    stale = _parse_atp_numeric_pdf_pages([s.replace("Oct 26, 2026", "Dec 30, 2024") for s in pages()])
    monkeypatch.setattr(provider, "_fetch_atp_numeric_pdf", lambda *a: stale)
    fresh = [{"player_id": "uts:1", "ranking_date": "2026-10-26", "raw": {
        "source": "ultimate_tennis_statistics", "source_ranking_date": "2026-10-26",
        "source_date_url": provider.ATP_UTS_DATE_URL, "source_date_sha256": "a"*64}}]
    monkeypatch.setattr(provider, "_fetch_atp_uts", lambda *a: fresh)
    assert provider.fetch_rankings("ATP", "2026-10-29") == fresh
    assert provider.ranking_source_failures[0]["rows"] == stale
    assert "stale source ranking date" in provider.ranking_source_failures[0]["error"]


def test_missing_dependency_is_an_explicit_source_failure(monkeypatch):
    import builtins
    provider = OfficialRankingProvider()
    original = builtins.__import__
    def no_pdf(name, *args, **kwargs):
        if name == "pdfplumber": raise ImportError("not installed")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_pdf)
    with pytest.raises(OfficialRankingFetchError, match="pdfplumber is required"):
        provider._fetch_atp_numeric_pdf("2026-10-29")


def test_native_schema_can_lookup_new_source_names_without_a_player_table_scan(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    init_db()
    with get_connection() as conn:
        plan = conn.execute("EXPLAIN QUERY PLAN SELECT id FROM players WHERE lower(trim(name))=lower(trim(?)) AND tour=?",
                            ("Jannik Sinner", "ATP")).fetchall()
        assert any("idx_players_lower_name_tour" in r[3] for r in plan)
