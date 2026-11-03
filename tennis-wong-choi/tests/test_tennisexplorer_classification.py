"""Source draw/tour guards must preserve results and stop unsafe history writes."""
from dataclasses import replace
import pytest
from test_tennisexplorer_history import _Stub, _result, _setup
from tennis_wc.database.db import get_connection
from tennis_wc.database.history_observations import upsert_history_observation
from tennis_wc.ingestion import ingest_tennisexplorer_history as corpus
from tennis_wc.providers.tennisexplorer_provider import parse_results_page


def _page(*, header='/templeton-itf/2026/wta-women/', a='/player/one/',
          b='/player/two/', between='', match_id='100'):
    title = '<a href="' + header + '">Templeton ITF</a>' if header else 'Templeton ITF'
    return ('<table><tr class="head flags"><td class="t-name">' + title + '</td></tr>'
            '<tr id="r10"><td class="t-name"><a href="' + a + '">Source One</a></td>'
            '<td class="result">2</td><td class="score">6</td><td class="score">6</td>'
            + (f'<td><a href="/match-detail/?id={match_id}">Detail</a></td>' if match_id is not None else '') + '</tr>'
            + between +
            '<tr id="r10b"><td class="t-name"><a href="' + b + '">Source Two</a></td>'
            '<td class="result">0</td><td class="score">2</td><td class="score">3</td></tr></table>')


def _run_html(tmp_path, monkeypatch, html):
    _setup(tmp_path, monkeypatch)
    stub = _Stub({})
    page = stub.fetch_results_page_for_date('2026-03-01')
    monkeypatch.setattr(stub, 'fetch_results_page_for_date', lambda _: replace(page, html=html))
    return corpus.ingest_tennisexplorer_history('2026-03-01', provider=stub)


@pytest.mark.parametrize('tour,path', [('ATP', 'atp-men'), ('WTA', 'wta-women')])
def test_tour_comes_from_source_not_city_name(tour, path):
    results, skipped = parse_results_page(_page(header=f'/templeton-itf/2026/{path}/'))
    assert skipped == 0 and len(results) == 1
    row = results[0]
    assert row.tour == tour and row.draw_kind == 'SINGLES'
    assert row.classification_warnings == ()
    assert row.player_a_source_ref == 'https://www.tennisexplorer.com/player/one/'
    assert row.winner_name == 'Source One'
    assert row.score_payload()['player_a_games'] == 12


def test_city_only_womens_event_is_stored_as_wta(tmp_path, monkeypatch):
    summary = _run_html(tmp_path, monkeypatch, _page())
    assert summary['matches'] == 1 and summary['rows'] == 2
    assert summary['held_reasons'] == {}
    with get_connection() as conn:
        assert {r[0] for r in conn.execute('SELECT tour FROM player_match_history')} == {'WTA'}


@pytest.mark.parametrize('path', ['atp-men', 'wta-women'])
def test_doubles_kept_for_results_not_individual_history(tmp_path, monkeypatch, path):
    html = _page(header=f'/fixture/2026/{path}/?type=double',
                 a='/doubles-team/one/two/', b='/doubles-team/three/four/')
    row = parse_results_page(html)[0][0]
    assert row.draw_kind == 'DOUBLES' and row.classification_warnings == ()
    assert row.score_payload()['player_a_sets'] == 2
    summary = _run_html(tmp_path, monkeypatch, html)
    assert summary['matches'] == summary['rows'] == summary['players_created'] == 0
    assert summary['held_reasons'] == {'doubles_not_individual_history': 1}
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM players').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM player_match_history').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM raw_api_responses').fetchone()[0] == 1


@pytest.mark.parametrize('updates', [
    {'header': None},
    {'header': '/unclassified/2026/unknown/'},
    {'header': '/fixture/2026/wta-women/?type=unknown'},
    {'header': 'https://example.invalid/fixture/2026/wta-women/'},
    {'header': 'https://[invalid/'},
    {'a': '/doubles-team/one/two/'},
    {'a': '/player/two/'},
    {'between': '<tr class="head flags"><td class="t-name">Other event</td></tr>'},
])
def test_unresolved_source_keeps_facts_without_history(tmp_path, monkeypatch, updates):
    html = _page(**updates)
    results, skipped = parse_results_page(html)
    assert skipped == 0 and results[0].winner_name == 'Source One'
    assert results[0].classification_warnings
    summary = _run_html(tmp_path, monkeypatch, html)
    assert summary['skipped'] == 1 and summary['rows'] == 0
    assert summary['held_sources'][0]['raw_response_id'] is not None
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM players').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM raw_api_responses').fetchone()[0] == 1


def _seed_player(conn, player_id, name, tour):
    conn.execute('INSERT INTO players(id,name,tour,source_provider,created_at,updated_at) '
                 'VALUES(?,?,?,\'fixture\',\'now\',\'now\')', (player_id, name, tour))


@pytest.mark.parametrize('tour,reason', [('ATP', 'target_tour_conflict'),
                                        ('UNKNOWN', 'unknown_target_tour')])
def test_target_tour_hold_rolls_back_opponent_and_alias(tmp_path, monkeypatch, tour, reason):
    conn = _setup(tmp_path, monkeypatch)
    _seed_player(conn, 1, 'Source Two', tour)
    conn.commit()
    stub = _Stub({'2026-03-01': [_result('ITF W35 Fixture', 'Source One', 'Source Two')]})
    summary = corpus.ingest_tennisexplorer_history('2026-03-01', provider=stub)
    assert summary['held_reasons'] == {reason: 1}
    assert summary['players_created'] == 0
    with get_connection() as conn:
        assert [r[0] for r in conn.execute('SELECT name FROM players')] == ['Source Two']
        assert conn.execute('SELECT COUNT(*) FROM player_aliases').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM player_match_history').fetchone()[0] == 0


def test_second_perspective_failure_leaves_no_half_match(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    real = corpus.upsert_history_observation
    calls = []

    def fail_second(conn, data, **kwargs):
        calls.append(data['won'])
        if len(calls) == 2:
            raise RuntimeError('loser-side write failed')
        return real(conn, data, **kwargs)

    monkeypatch.setattr(corpus, 'upsert_history_observation', fail_second)
    with pytest.raises(RuntimeError, match='loser-side write failed'):
        corpus.ingest_tennisexplorer_history('2026-03-01', provider=_Stub({
            '2026-03-01': [_result('ITF M15 Fixture', 'Source One', 'Source Two')]}))
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM players').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM player_match_history').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM history_observations').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM raw_api_responses').fetchone()[0] == 1


@pytest.mark.parametrize('old_tour,retired,reason', [
    ('ATP', False, 'existing_history_facts_conflict'),
    ('WTA', True, 'legacy_history_requires_review'),
])
def test_new_classification_does_not_duplicate_or_resurrect_history(
        tmp_path, monkeypatch, old_tour, retired, reason):
    conn = _setup(tmp_path, monkeypatch)
    _seed_player(conn, 1, 'Source One', 'WTA')
    _seed_player(conn, 2, 'Source Two', 'WTA')
    conn.commit()
    raw = corpus.store_raw_response('tennisexplorer', 'tennisexplorer/results', {},
                                    {'summary': 'old source'}, 200)
    for pid, opponent, won, suffix in [(1, 2, 1, 'winner'), (2, 1, 0, 'loser')]:
        upsert_history_observation(conn, dict(
            provider_match_id='te-2026-03-01-sourceone-sourcetwo-' + suffix,
            player_id=pid, opponent_id=opponent, tour=old_tour, match_date='2026-03-01',
            tournament_external_id='Templeton ITF', tournament_level='ITF', round='R',
            format='BO3', won=won, source_provider='tennisexplorer', raw_response_id=raw,
            created_at='old', surface=None), observed_at='old')
    if retired:
        conn.execute("UPDATE player_match_history SET history_status='SUPERSEDED'")
    conn.commit()
    before = [dict(r) for r in conn.execute('SELECT * FROM player_match_history ORDER BY id')]
    observations = conn.execute('SELECT COUNT(*) FROM history_observations').fetchone()[0]
    stub = _Stub({})
    page = stub.fetch_results_page_for_date('2026-03-01')
    monkeypatch.setattr(stub, 'fetch_results_page_for_date', lambda _: replace(page, html=_page()))
    summary = corpus.ingest_tennisexplorer_history('2026-03-01', provider=stub)
    assert summary['rows'] == 0 and summary['held_reasons'] == {reason: 1}
    with get_connection() as conn:
        assert [dict(r) for r in conn.execute('SELECT * FROM player_match_history ORDER BY id')] == before
        assert conn.execute('SELECT COUNT(*) FROM history_observations').fetchone()[0] == observations
        assert conn.execute('SELECT COUNT(*) FROM raw_api_responses').fetchone()[0] == 2


def test_contradictory_source_versions_are_all_held(tmp_path, monkeypatch):
    first = _result('ITF W35 Fixture', 'Source One', 'Source Two')
    second = replace(first, player_a_sets=0, player_b_sets=2,
                     sets=[{'player_a_games': 2, 'player_b_games': 6},
                           {'player_a_games': 3, 'player_b_games': 6}])
    _setup(tmp_path, monkeypatch)
    summary = corpus.ingest_tennisexplorer_history('2026-03-01', provider=_Stub({
        '2026-03-01': [first, second]}))
    assert summary['held_reasons'] == {'conflicting_source_scores': 2}
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM players').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM player_match_history').fetchone()[0] == 0


def _generic(icon, *, doubles=False):
    a = '/doubles-team/one/two/' if doubles else '/player/one/'
    b = '/doubles-team/three/four/' if doubles else '/player/two/'
    html = _page(header=None, a=a, b=b)
    return html.replace('>Templeton ITF</td>',
                        f'><span class="{icon}">&nbsp;</span>Futures 2026</td>', 1)


@pytest.mark.parametrize('icon,tour', [('type-men2', 'ATP'), ('type-men4', 'ATP'),
                                      ('type-women2', 'WTA'), ('type-women4', 'WTA')])
@pytest.mark.parametrize('doubles', [False, True])
def test_current_generic_header_has_own_icon_source(icon, tour, doubles):
    row = parse_results_page(_generic(icon, doubles=doubles))[0][0]
    assert row.tour == tour
    assert row.draw_kind == ('DOUBLES' if doubles else 'SINGLES')
    assert row.tour_source_kind == 'header_icon'
    assert row.tournament_source_url is None
    assert row.tournament_name == row.tournament_source_label == 'Futures 2026'
    assert row.classification_warnings == ()


def test_new_generic_header_never_inherits_previous_wta_url():
    first = _page().replace('</table>', '')
    second = _generic('type-men2').replace('<table>', '').replace('r10', 'r20')
    rows, skipped = parse_results_page(first + second)
    assert skipped == 0 and len(rows) == 2
    assert rows[0].tour == 'WTA'
    assert rows[1].tour == 'ATP' and rows[1].tour_source_kind == 'header_icon'
    assert rows[1].tournament_source_url is None


@pytest.mark.parametrize('icon', ['type-men2', 'type-unknown'])
def test_url_icon_disagreement_is_held(tmp_path, monkeypatch, icon):
    html = _page().replace('>Templeton ITF</a>',
                           f'><span class="{icon}">&nbsp;</span>Templeton ITF</a>', 1)
    row = parse_results_page(html)[0][0]
    assert row.classification_warnings
    summary = _run_html(tmp_path, monkeypatch, html)
    assert summary['rows'] == 0 and summary['players_created'] == 0


def test_blank_current_label_is_not_filled_from_previous_event():
    first = _page().replace('</table>', '')
    second = _generic('type-men2').replace('<table>', '').replace('r10', 'r20')
    second = second.replace('Futures 2026', '')
    rows, _ = parse_results_page(first + second)
    assert len(rows) == 2
    # Preserve the legacy result API, but forbid its stale label in history.
    assert rows[1].tournament_name == 'Templeton ITF'
    assert rows[1].tournament_source_label is None
    assert 'missing_current_tournament_label' in rows[1].classification_warnings


@pytest.mark.parametrize('icon,tour', [('type-men2', 'ATP'), ('type-women2', 'WTA')])
def test_generic_source_can_store_fresh_individual_history(tmp_path, monkeypatch, icon, tour):
    summary = _run_html(tmp_path, monkeypatch, _generic(icon))
    assert summary['matches'] == 1 and summary['rows'] == 2
    with get_connection() as conn:
        rows = list(conn.execute('SELECT tour,tournament_external_id,tournament_level '
                                 'FROM player_match_history'))
        assert len(rows) == 2
        assert {tuple(r) for r in rows} == {(tour, 'Futures 2026', 'ITF')}


def test_ambiguous_existing_people_do_not_create_a_new_spelling(tmp_path, monkeypatch):
    conn = _setup(tmp_path, monkeypatch)
    _seed_player(conn, 1, 'Sarah Smith', 'WTA')
    _seed_player(conn, 2, 'Susan Smith', 'WTA')
    conn.commit()
    summary = corpus.ingest_tennisexplorer_history('2026-03-01', provider=_Stub({
        '2026-03-01': [_result('ITF W35 Fixture', 'Source One', 'Smith S.')]}))
    assert summary['held_reasons'] == {'unresolved_existing_player': 1}
    assert summary['players_created'] == 0
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM players').fetchone()[0] == 2
        assert conn.execute('SELECT COUNT(*) FROM player_aliases').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM player_match_history').fetchone()[0] == 0


def test_empty_normalized_name_is_held_without_aborting_source(tmp_path, monkeypatch):
    html = _page().replace('>Source One</a>', '>---</a>')
    summary = _run_html(tmp_path, monkeypatch, html)
    assert summary['held_reasons'] == {'invalid_player_name': 1}
    assert summary['players_created'] == 0


@pytest.mark.parametrize("same_id", [False, True])
def test_ambiguous_primary_fixture_holds_all_versions(tmp_path, monkeypatch, same_id):
    second = _page(match_id="100" if same_id else "101",
                   a="/player/three/" if same_id else "/player/one/")
    summary = _run_html(tmp_path, monkeypatch, _page() + second)
    assert summary["held_reasons"] == {"ambiguous_source_fixture": 2}
    assert summary["rows"] == summary["players_created"] == 0


def test_identical_primary_fixture_is_idempotent(tmp_path, monkeypatch):
    summary = _run_html(tmp_path, monkeypatch, _page() + _page())
    assert summary["matches"] == 2 and summary["held_reasons"] == {}
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM player_match_history").fetchone()[0] == 2


def test_missing_primary_fixture_is_held(tmp_path, monkeypatch):
    summary = _run_html(tmp_path, monkeypatch, _page(match_id=None))
    assert summary["held_reasons"] == {"unknown_source_fixture": 1}


@pytest.mark.parametrize("match_id", ["0", "-1", "abc", "1&id=2"])
def test_invalid_primary_fixture_keeps_score_but_warns(match_id):
    row = parse_results_page(_page(match_id=match_id))[0][0]
    assert row.player_a_sets == 2
    assert "invalid_match_source" in row.classification_warnings
