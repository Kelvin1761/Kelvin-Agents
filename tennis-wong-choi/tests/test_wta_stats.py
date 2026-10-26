"""Official WTA per-match serve stats (2026-10-14). Temp DB, no network."""
from __future__ import annotations

import pytest

# Real shape, trimmed: api.wtatennis.com Adana 125 2026, match RS010.
MATCH = {
    "DrawLevelType": "Q", "DrawMatchType": "S", "EventID": "1179", "EventYear": 2026,
    "MatchID": "RS010", "MatchState": "F", "MatchTimeStamp": "2026-09-26T07:17:43.26+00:00",
    "PlayerIDA": "322277", "PlayerIDB": "322016",
    "PlayerNameFirstA": "Viktoria", "PlayerNameLastA": "Hruncakova",
    "PlayerNameFirstB": "Jaeda", "PlayerNameLastB": "Daniel",
    "ResultString": "[2]V. Hruncakova d J. Daniel 6-4,6-3", "RoundID": "1",
    "ScoreSet1A": "6", "ScoreSet1B": "4", "ScoreSet2A": "6", "ScoreSet2B": "3",
    "ScoreString": "6-4,6-3", "Winner": "2",
}
TOTAL = {
    "setnum": 0, "acesa": 4, "acesb": 2, "dblflta": 6, "dblfltb": 3,
    "ptswon1stserva": 26, "ptswon1stservb": 21, "ptsplayed1stserva": 39,
    "ptsplayed1stservb": 34, "ptstotwonserva": 46, "ptstotwonservb": 30,
    "totservplayeda": 72, "totservplayedb": 49, "breakptsconva": 3, "breakptsconvb": 1,
    "breakptsplayeda": 3, "breakptsplayedb": 7, "servgamesplayeda": 10, "servgamesplayedb": 9,
}
TOURNAMENTS = {"content": [
    {"tournamentGroup": {"id": 1179, "level": "WTA 125"}, "year": 2026,
     "title": "Adana Open", "startDate": "2026-09-28", "surface": "Hard"},
    {"tournamentGroup": {"id": 4498, "level": "ITF"}, "year": 2026,
     "title": "W15 Monastir", "startDate": "2026-09-28", "surface": "Hard"},
]}


class FakeGetter:
    def __init__(self, with_stats=True):
        self.calls: list[str] = []
        self.with_stats = with_stats

    def __call__(self, url, params=None):
        self.calls.append(url)
        if url.endswith("/tournaments/"):
            return TOURNAMENTS
        if url.endswith("/stats"):
            return [TOTAL, {**TOTAL, "setnum": 1}] if self.with_stats else []
        if url.endswith("/matches"):
            doubles = {**MATCH, "MatchID": "RD001", "DrawMatchType": "D"}
            live = {**MATCH, "MatchID": "RS020", "MatchState": "P"}
            return {"matches": [MATCH, doubles, live]}
        raise AssertionError(url)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db

    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO players (id, name, tour, source_provider, created_at, updated_at)
           VALUES (11,'Viktoria Hruncakova','WTA','test','now','now')"""
    )
    conn.commit()
    return conn


def _ingest(getter):
    from tennis_wc.ingestion.ingest_wta_stats import ingest_wta_match_stats
    from tennis_wc.providers.wta_stats_provider import WtaStatsProvider

    return ingest_wta_match_stats(
        "2026-09-20", "2026-10-14", provider=WtaStatsProvider(getter), sleeper=lambda s: None)


def test_ingests_singles_with_sackmann_equivalent_columns(db):
    from tennis_wc.database.db import get_connection

    getter = FakeGetter()
    summary = _ingest(getter)
    assert summary["tournaments"] == 1 and summary["tournaments_skipped_itf"] == 1
    assert not any("/4498/" in url for url in getter.calls), "ITF match feeds are empty; skip"
    assert summary["matches_with_stats"] == 1, "doubles and unfinished matches excluded"
    rows = {r["side"]: r for r in get_connection().execute("SELECT * FROM wta_match_stats")}
    a, b = rows["A"], rows["B"]
    assert a["player_id"] == 11 and b["player_id"] is None   # resolution is exact-name only
    assert a["won"] == 1 and b["won"] == 0, "the Winner field ('2') is not a side flag"
    assert a["match_date"] == "2026-09-26"
    assert (a["ace_count"], a["double_fault_count"], a["serve_points"]) == (4, 6, 72)
    assert a["second_serve_points_won"] == 20          # 46 won on serve - 26 on first
    assert a["first_serve_points_won_pct"] == pytest.approx(26 / 39)
    # A faced 7 break points on serve and lost 1 -> held 9 of 10.
    assert (a["break_points_faced"], a["break_points_saved"]) == (7, 6)
    assert a["hold_rate"] == pytest.approx(0.9)
    # Games reconcile: A won 12 = 9 holds + 3 breaks; B won 7 = 6 holds + 1 break.
    assert b["hold_rate"] == pytest.approx(6 / 9)
    assert a["break_rate"] == pytest.approx(3 / 9)
    assert a["return_points_won_pct"] == pytest.approx((49 - 30) / 49)
    assert a["stats_status"] == "OK" and a["raw_response_id"] > 0


def test_rerun_skips_stored_matches_and_no_stats_is_retried(db):
    from tennis_wc.database.db import get_connection

    empty = FakeGetter(with_stats=False)
    first = _ingest(empty)
    assert first["matches_without_stats"] == 1
    status = get_connection().execute(
        "SELECT DISTINCT stats_status FROM wta_match_stats").fetchall()
    assert [r[0] for r in status] == ["NO_STATS"]

    full = FakeGetter()
    second = _ingest(full)
    assert second["matches_with_stats"] == 1, "a NO_STATS row is fetched again"
    third_getter = FakeGetter()
    third = _ingest(third_getter)
    assert third["already_stored"] == 1
    assert not any(url.endswith("/stats") for url in third_getter.calls)
    assert get_connection().execute("SELECT COUNT(*) FROM wta_match_stats").fetchone()[0] == 2


def test_health_separates_what_models_read_from_what_feed_holds(db):
    from tennis_wc.database.db import get_connection
    from tennis_wc.ingestion.ingest_wta_stats import wta_serve_stats_health

    _ingest(FakeGetter())
    health = wta_serve_stats_health(get_connection(), "2026-10-14")
    assert health["model_serve_latest"] is None, "serve models still read player_match_history"
    assert health["feed_latest"] == "2026-09-26" and health["feed_age_days"] == 18


def test_list_failure_is_reported_not_raised(db):
    def broken(url, params=None):
        raise RuntimeError("HTTP 503")

    summary = _ingest(broken)
    assert summary["errors"][0]["stage"] == "list_tournaments"


@pytest.mark.parametrize('changes,reason',[
    ({'servgamesplayeda':5,'servgamesplayedb':4},'inconsistent_service_exposure'),
    ({'ptswon1stserva':99},'invalid_count'),
    ({'ptsplayed1stserva':99},'invalid_point_counts'),
    ({'acesa':100},'invalid_point_counts'),
])
def test_invalid_totals_are_preserved_but_not_marked_usable(db,changes,reason):
    from tennis_wc.ingestion.ingest_wta_stats import wta_serve_stats_health

    class InvalidGetter(FakeGetter):
        def __call__(self,url,params=None):
            if url.endswith('/stats'):
                return [{**TOTAL,**changes}]
            return super().__call__(url,params)

    result=_ingest(InvalidGetter())
    assert result['matches_with_stats']==1, 'availability is distinct from validity'
    assert result['matches_invalid_stats']==1
    assert result['matches_with_valid_stats']==0
    assert result['quality_issues'][reason]==1
    assert [r[0] for r in db.execute('SELECT DISTINCT stats_status FROM wta_match_stats')]==['INVALID_STATS']
    assert db.execute('SELECT MIN(raw_response_id) FROM wta_match_stats').fetchone()[0]>0
    health=wta_serve_stats_health(db,'2026-10-14')
    assert health['feed_latest'] is None
    assert health['feed_status_counts']=={'INVALID_STATS':2}
    retried=_ingest(FakeGetter())
    assert retried['matches_with_valid_stats']==1, 'invalid totals must be retried, not cached forever'
    assert [r[0] for r in db.execute('SELECT DISTINCT stats_status FROM wta_match_stats')]==['OK']


def test_legacy_ok_label_with_invalid_raw_is_revalidated_and_retried(db):
    class LegacyGetter(FakeGetter):
        def __call__(self,url,params=None):
            if url.endswith('/stats'):
                return [{**TOTAL,'servgamesplayeda':5,'servgamesplayedb':4}]
            return super().__call__(url,params)

    _ingest(LegacyGetter())
    db.execute("UPDATE wta_match_stats SET stats_status='OK'")
    db.commit()
    getter=FakeGetter()
    result=_ingest(getter)
    assert result['cached_invalid_retried']==1
    assert result['matches_with_valid_stats']==1
    assert any(url.endswith('/stats') for url in getter.calls)


def test_complete_historical_advantage_set_is_valid(db):
    class AdvantageGetter(FakeGetter):
        def __call__(self,url,params=None):
            body=super().__call__(url,params)
            if url.endswith('/stats'):
                return [{**TOTAL,'servgamesplayeda':13,'servgamesplayedb':13,'totservplayedb':70}]
            if url.endswith('/matches'):
                body['matches'][0]={**MATCH,'ScoreSet2A':'9','ScoreSet2B':'7','ScoreString':'6-4,9-7'}
            return body

    result=_ingest(AdvantageGetter())
    assert result['matches_with_valid_stats']==1
    assert not result['quality_issues']


def test_failed_refresh_preserves_values_when_old_raw_evidence_is_missing(db):
    _ingest(FakeGetter())
    db.execute('UPDATE wta_match_stats SET raw_response_id=0')
    db.commit()
    before={r['side']:dict(r) for r in db.execute('SELECT * FROM wta_match_stats')}
    result=_ingest(FakeGetter(with_stats=False))
    assert result['existing_values_preserved']==1
    after={r['side']:dict(r) for r in db.execute('SELECT * FROM wta_match_stats')}
    for side,old in before.items():
        assert after[side]=={**old,'stats_status':'UNVERIFIED_STATS'}
    recovered=_ingest(FakeGetter())
    assert recovered['matches_with_valid_stats']==1
    assert [r[0] for r in db.execute('SELECT DISTINCT stats_status FROM wta_match_stats')]==['OK']


def test_retired_match_is_partial_even_when_statistics_are_available(db):
    class RetiredGetter(FakeGetter):
        def __call__(self,url,params=None):
            body=super().__call__(url,params)
            if url.endswith('/matches'):
                body['matches'][0]={**MATCH,'ScoreString':"6-4,1-0 Ret'd"}
            return body

    result=_ingest(RetiredGetter())
    assert result['matches_partial_stats']==1
    assert result['matches_with_valid_stats']==0
    assert [r[0] for r in db.execute('SELECT DISTINCT stats_status FROM wta_match_stats')]==['PARTIAL_MATCH']
