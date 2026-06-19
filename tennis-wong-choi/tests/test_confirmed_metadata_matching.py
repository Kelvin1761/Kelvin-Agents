from __future__ import annotations

from tennis_wc.ingestion.confirmed_metadata import (
    confirmed_competition_meta,
    tennisdata_competition_meta,
)


def test_tennisdata_index_resolves_long_tail_tour_events():
    # Tour events not in the hand-curated list should still resolve level+surface
    # from the historical tennis-data index.
    m = tennisdata_competition_meta("Mallorca Championships", "ATP")
    assert m == {"tour": "ATP", "level": "ATP_250", "surface": "Grass"}


def test_tennisdata_index_is_tour_aware():
    atp = tennisdata_competition_meta("Adelaide International", "ATP")
    wta = tennisdata_competition_meta("Adelaide International", "WTA")
    assert atp["surface"] == "Hard" and atp["level"] == "ATP_250"
    assert wta["level"] == "WTA_500"


def test_tennisdata_index_excludes_non_tour_events():
    for name in ("ITF China Futures", "Mens UTR Pro Series, Australia", "Some Random Cup"):
        assert tennisdata_competition_meta(name, "ATP") is None


def test_tennisdata_index_requires_a_tour():
    assert tennisdata_competition_meta("Mallorca Championships", None) is None
    assert tennisdata_competition_meta("Mallorca Championships", "UNKNOWN") is None


def test_exact_alias_still_matches():
    m = confirmed_competition_meta("ATP Halle", "ATP")
    assert m is not None and m.level == "ATP_500" and m.surface == "Grass"


def test_sponsor_prefixed_name_recovered_by_token_subset():
    # "VANDA Pharmaceuticals Berlin Tennis Open" must resolve to WTA Berlin 500
    # even though the sponsor prefix breaks an exact-name match.
    m = confirmed_competition_meta("VANDA Pharmaceuticals Berlin Tennis Open", "WTA")
    assert m is not None and m.tour == "WTA" and m.level == "WTA_500" and m.surface == "Grass"


def test_queens_hsbc_championships_resolved():
    m = confirmed_competition_meta("HSBC Championships", "ATP")
    assert m is not None and m.level == "ATP_500" and m.surface == "Grass"


def test_eastbourne_disambiguates_by_tour():
    atp = confirmed_competition_meta("Eastbourne International", "ATP")
    wta = confirmed_competition_meta("Eastbourne International", "WTA")
    assert atp is not None and atp.level == "ATP_250"
    assert wta is not None and wta.level == "WTA_500"


def test_wrong_tour_returns_none_not_wrong_level():
    # Queen's men's event is ATP 500; asking for WTA must NOT mislabel it.
    assert confirmed_competition_meta("HSBC Championships", "WTA") is None


def test_single_token_does_not_false_match_inside_word():
    # "Halle" must not match inside "Challenger" (substring) — token-based only.
    assert confirmed_competition_meta("ATP Challenger Genova", "ATP") is None


def test_itf_and_utf_junk_excluded():
    for name in ("ITF Doubles", "ITF China Futures", "Mens UTR Pro Series, Australia", "UTR Singles"):
        assert confirmed_competition_meta(name, "ATP") is None
