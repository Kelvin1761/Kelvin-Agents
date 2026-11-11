"""One event with an unprovable player identity must not take the whole odds source down.

2026-11-11: a WTA doubles pair (Sportsbet "Siniakova/Townsend") resolved through a
merge onto a record tagged ATP. The identity guard rightly refused it, but the
exception escaped ``ingest_odds`` and the 09:00 and 10:30 cards failed for every
other match too.
"""
from __future__ import annotations

from types import SimpleNamespace

from conftest import configure_test_db
from tennis_wc import run
from tennis_wc.sources import ingest_odds
from tennis_wc.sources.entity_mapping import PlayerIdentityConflict
from tennis_wc.store.migrations import init_db


def _rows():
    return [dict(event_id=event, local_date="2026-06-01", bookmaker="Sportsbet",
                 player_a_name="A", player_b_name="B", player_a_odds=1.9, player_b_odds=1.9)
            for event in ("good-1", "bad", "good-2")]


def _patch(monkeypatch, tmp_path, seen):
    configure_test_db(tmp_path, monkeypatch)
    init_db()
    provider = SimpleNamespace(provider_name="test", fetch_upcoming_odds_for_date=lambda day: _rows())
    monkeypatch.setattr(ingest_odds, "get_odds_provider", lambda: provider)

    def fake_row(provider_name, date, row, raw_id, now):
        seen.append(row["event_id"])
        if row["event_id"] == "bad":
            raise PlayerIdentityConflict("canonical player identity changed: 21766 -> 8262")
        return True

    monkeypatch.setattr(ingest_odds, "_ingest_odds_row", fake_row)


def test_identity_conflict_skips_only_that_event(tmp_path, monkeypatch):
    seen: list[str] = []
    _patch(monkeypatch, tmp_path, seen)
    rejected: list[dict] = []
    assert ingest_odds.ingest_odds("2026-06-01", rejected=rejected) == 2
    assert seen == ["good-1", "bad", "good-2"]
    assert [r["event_id"] for r in rejected] == ["bad"]
    assert rejected[0]["error"].startswith("player_identity_conflict:")


def test_skipped_event_is_reported_as_a_degraded_odds_source(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, [])
    stages = run.Stages()
    result = stages.run("odds", lambda: run._ingest_odds_reporting(ingest_odds.ingest_odds, "2026-06-01"))
    assert result["rows"] == 2
    assert stages.errors == []
    assert [(w["source"], w["event_id"]) for w in stages.warnings] == [("odds", "bad")]
    assert stages.warnings[0]["warning"].startswith("player_identity_conflict:")


def test_other_errors_still_fail_the_source(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, [])

    def broken(provider_name, date, row, raw_id, now):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(ingest_odds, "_ingest_odds_row", broken)
    stages = run.Stages()
    assert stages.run("odds", lambda: run._ingest_odds_reporting(ingest_odds.ingest_odds, "2026-06-01")) is None
    assert stages.errors and stages.errors[0]["source"] == "odds"
