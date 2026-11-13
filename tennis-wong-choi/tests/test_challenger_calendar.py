"""Challenger court from the season calendar (EXP-20261113-30)."""
from __future__ import annotations

from datetime import date

import pytest

from conftest import configure_test_db
from tennis_wc.sources.challenger_calendar import parse_calendar, resolve

WIKI = """=== November ===
{| class="wikitable"
|-valign=top
|rowspan=12|November 2||rowspan=2|[[2026 Costa do Sauípe Open|Costa do Sauípe Open]]<br/>[[Sauipe]], Brazil <br/> Clay – Challenger 125 – 32S/24Q/16D<br/>[[x|Singles]] || winners
|-valign=top
|rowspan=2|[[2026 Slovak Open|Slovak Open]]<br/>[[Bratislava]], Slovakia <br/> Hard (i) – Challenger 100 – 32S/24Q/16D<br/>[[x|Singles]] || winners
|-valign=top
|rowspan=2|[[2026 Crete Challenger|Crete Challenger]]<br/>[[Hersonissos]], Greece <br/> Hard – Challenger 50 – 32S<br/> || w
|-valign=top
|rowspan=12|November 9||rowspan=2|[[2026 Crete Challenger III|Crete Challenger III]]<br/>[[Hersonissos]], Greece <br/> Clay – Challenger 50 – 32S<br/> || w
|-valign=top
|rowspan=2|[[2026 Santa Cruz|Santa Cruz Challenger]]<br/>[[Santa Cruz de la Sierra]], Bolivia <br/> Clay – Challenger 75 – 32S<br/> || w
"""


def events():
    return parse_calendar(WIKI, 2026)


def test_parse_reads_week_city_court_and_indoor():
    got = {(e.week_start, e.city, e.surface, e.indoor, e.category) for e in events()}
    assert (date(2026, 11, 2), "Bratislava", "Hard", True, "100") in got
    assert (date(2026, 11, 2), "Sauipe", "Clay", False, "125") in got
    assert (date(2026, 11, 9), "Santa Cruz de la Sierra", "Clay", False, "75") in got


@pytest.mark.parametrize("name,day,surface", [
    ("ATP Challenger 100 Bratislava", "2026-11-05", "Hard"),
    ("ATP Challenger 100 Bratislava Q", "2026-10-31", "Hard"),      # qualifying weekend
    ("ATP Challenger 125 Costa Do Sauipe", "2026-11-09", "Clay"),   # Sunday final, Monday in Sydney
    ("ATP Challenger 75 Santa Cruz", "2026-11-12", "Clay"),         # Sportsbet shortens the city
    ("ATP Challenger 50 Hersonissos", "2026-11-04", "Hard"),        # same city, two weeks:
    ("ATP Challenger 50 Hersonissos", "2026-11-12", "Clay"),        # the date picks the edition
])
def test_resolve(name, day, surface):
    assert resolve(events(), name, day).surface == surface


@pytest.mark.parametrize("name,day", [
    ("ATP Challenger 100 Bratislava", "2026-10-20"),          # outside the week
    ("ATP Challenger 75 Bratislava", "2026-11-05"),           # wrong category
    ("ATP Challenger 100 Bratislava Doubles", "2026-11-05"),  # doubles never enter singles
    ("ATP Challenger 100 Prague", "2026-11-05"),              # not in the calendar
    ("ATP Bratislava", "2026-11-05"),                         # not named a Challenger
    ("ATP Challenger 50 Hersonissos", "2026-11-09"),          # both Hersonissos weeks, courts differ
])
def test_resolve_refuses_to_guess(name, day):
    assert resolve(events(), name, day) is None


def _db(tmp_path, monkeypatch, name="ATP Challenger 100 Bratislava", day="2026-11-05"):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.store.db import get_connection
    from tennis_wc.store.migrations import init_db

    init_db()
    with get_connection() as conn:
        conn.execute("INSERT INTO tournaments (id, name, tour, external_id, source_provider, created_at, updated_at) "
                     "VALUES (1, ?, 'ATP', 'sb-1', 'sportsbet', 'now', 'now')", (name,))
        for pid in (1, 2):
            conn.execute("INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
                         "VALUES (?, ?, 'ATP', 'test', 'now', 'now')", (pid, f"P{pid}"))
        conn.execute("INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id, player_a_id, "
                     "player_b_id, round, source_provider, created_at, updated_at) "
                     "VALUES (1, 'm1', 'ATP', ?, 1, 1, 2, 'UNKNOWN', 'sportsbet', 'now', 'now')", (day,))
    return get_connection


def _use_calendar(monkeypatch, fetch):
    from tennis_wc.sources import confirmed_metadata
    from tennis_wc.sources.challenger_calendar import load_events

    monkeypatch.setattr(confirmed_metadata, "_CALENDAR_CACHE", {})
    monkeypatch.setattr(confirmed_metadata, "_challenger_events", lambda year: load_events(year, fetch=fetch))


def test_backfill_writes_the_court_and_features_read_it(tmp_path, monkeypatch):
    connect = _db(tmp_path, monkeypatch)
    _use_calendar(monkeypatch, lambda year: WIKI)
    from tennis_wc.sources.confirmed_metadata import backfill_confirmed_metadata_for_date, metadata_audit_for_date

    out = backfill_confirmed_metadata_for_date("2026-11-05")
    assert out["challenger_calendar"]["events"] == 5
    with connect() as conn:
        row = conn.execute("SELECT * FROM tournament_levels WHERE source_provider = "
                           "'wikipedia_atp_challenger_calendar'").fetchone()
        assert (row["level"], row["surface"], row["indoor_outdoor"]) == ("CHALLENGER", "Hard", "indoor")
        best = conn.execute(
            """SELECT surface FROM tournament_levels WHERE tournament_id = 1 AND tour = 'ATP' ORDER BY
               (source_provider = 'curated_tournament_metadata') DESC,
               (level != 'UNKNOWN' AND level != '未確認') DESC, (surface IS NOT NULL) DESC, id DESC LIMIT 1"""
        ).fetchone()
        assert best["surface"] == "Hard"
    assert metadata_audit_for_date("2026-11-05")["summary"]["missing_surface"] == 0


def test_a_week_that_no_longer_resolves_clears_the_old_court(tmp_path, monkeypatch):
    connect = _db(tmp_path, monkeypatch)
    _use_calendar(monkeypatch, lambda year: WIKI)
    from tennis_wc.sources.confirmed_metadata import backfill_confirmed_metadata_for_date

    backfill_confirmed_metadata_for_date("2026-11-05")
    with connect() as conn:
        conn.execute("UPDATE matches SET match_date = '2026-12-20'")
    backfill_confirmed_metadata_for_date("2026-12-20")
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tournament_levels WHERE source_provider = "
                            "'wikipedia_atp_challenger_calendar'").fetchone()[0] == 0


def test_fetch_failure_uses_the_stored_copy_then_nothing(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    from tennis_wc.sources.challenger_calendar import load_events

    def boom(year):
        raise OSError("offline")

    events_, raw_id, error = load_events(2026, fetch=boom)
    assert events_ == [] and raw_id is None and "offline" in error
    load_events(2026, fetch=lambda year: WIKI)          # stores a good copy
    events_, raw_id, error = load_events(2026, fetch=boom)
    assert len(events_) == 5 and raw_id is not None and "offline" in error


def test_tests_never_fetch_by_default(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    from tennis_wc.sources.challenger_calendar import load_events

    events_, raw_id, error = load_events(2026)
    assert events_ == [] and "OFFLINE" in error
