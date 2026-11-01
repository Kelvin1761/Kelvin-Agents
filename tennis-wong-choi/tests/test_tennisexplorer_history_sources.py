"""Raw source capture precedes parsing, without inventing old source evidence."""
from dataclasses import replace
import hashlib
import json

import pytest

from test_tennisexplorer_history import _Stub, _result, _setup
from tennis_wc.ingestion import ingest_tennisexplorer_history as corpus
from tennis_wc.database.db import get_connection
from tennis_wc.providers.tennisexplorer_provider import TennisExplorerResultsProvider,parse_results_page


def _stub():
    return _Stub({'2026-03-01':[_result('ITF M15 Monastir','Ivan One','Petr Two')],
                  '2026-03-02':[_result('ITF W35 Southaven','Piper Charney','Jia-Jing Lu')]})


def _raws():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM raw_api_responses WHERE provider_name='tennisexplorer' ORDER BY id")]


def test_each_day_preserves_html_hash_url_clock_and_history_link(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch)
    stub=_stub(); pages={d:stub.fetch_results_page_for_date(d) for d in stub.by_date}
    monkeypatch.setattr(stub,'fetch_results_page_for_date',lambda d:pages[d])
    summary=corpus.ingest_tennisexplorer_history('2026-03-01','2026-03-02',provider=stub)
    assert not summary['errors'] and summary['matches']==2
    raws=_raws();assert len(raws)==2
    with get_connection() as conn:
        for raw in raws:
            payload=json.loads(raw['response_json']);page=pages[payload['match_date']]
            assert payload['format']=='tennisexplorer-results-html-v1'
            assert payload['html']==page.html
            assert payload['decoded_html_sha256']==hashlib.sha256(page.html.encode()).hexdigest()
            assert payload['requested_url']==page.requested_url
            assert payload['fetched_at']==page.fetched_at
            assert '原文' in payload['html']
            assert json.loads(raw['request_params_json'])['match_date']==page.match_date
            linked=list(conn.execute('SELECT match_date FROM player_match_history WHERE raw_response_id=?',(raw['id'],)))
            assert len(linked)==2 and {r[0] for r in linked}=={page.match_date}


def test_parse_failure_preserves_response_and_next_day_continues(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch)
    real=corpus.parse_results_page
    def parser(html):
        if 'Ivan One' in html:raise ValueError('simulated parser failure')
        return real(html)
    monkeypatch.setattr(corpus,'parse_results_page',parser)
    summary=corpus.ingest_tennisexplorer_history('2026-03-01','2026-03-02',provider=_stub())
    assert summary['dates']==1 and summary['matches']==1
    error=summary['errors'][0];assert error['phase']=='parse' and error['raw_response_id'] is not None
    raws=_raws();assert len(raws)==2
    assert 'Ivan One' in json.loads(raws[0]['response_json'])['html']
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM player_match_history WHERE match_date='2026-03-01'").fetchone()[0]==0


def test_store_failure_prevents_parse_or_history(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch)
    def fail(*args,**kwargs):raise RuntimeError('source store failed')
    def forbidden(*args):raise AssertionError('parser must not run')
    monkeypatch.setattr(corpus,'store_raw_response',fail)
    monkeypatch.setattr(corpus,'parse_results_page',forbidden)
    summary=corpus.ingest_tennisexplorer_history('2026-03-01',provider=_stub())
    assert summary['errors'][0]['phase']=='source_store'
    with get_connection() as conn:assert conn.execute('SELECT COUNT(*) FROM player_match_history').fetchone()[0]==0


@pytest.mark.parametrize('change',['wrong_date','wrong_url','naive_clock','future_clock','empty_html'])
def test_invalid_source_preserved_but_not_ingested(tmp_path,monkeypatch,change):
    _setup(tmp_path,monkeypatch);stub=_stub();page=stub.fetch_results_page_for_date('2026-03-01')
    updates={'wrong_date':dict(match_date='2026-03-02'),'wrong_url':dict(requested_url='https://example.invalid/'),
             'naive_clock':dict(fetched_at='2026-03-01T00:00:00'),
             'future_clock':dict(fetched_at='2999-01-01T00:00:00Z'),'empty_html':dict(html='')}
    page=replace(page,**updates[change]);monkeypatch.setattr(stub,'fetch_results_page_for_date',lambda d:page)
    summary=corpus.ingest_tennisexplorer_history('2026-03-01',provider=stub)
    assert summary['dates']==0 and summary['errors'][0]['phase']=='source_validation'
    assert len(_raws())==1
    with get_connection() as conn:assert conn.execute('SELECT COUNT(*) FROM player_match_history').fetchone()[0]==0


def test_results_only_custom_provider_cannot_fake_raw_source(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch)
    class Legacy:
        def fetch_results_for_date(self,day):return _stub().fetch_results_for_date(day)
    summary=corpus.ingest_tennisexplorer_history('2026-03-01',provider=Legacy())
    assert summary['dates']==0 and summary['errors'][0]['phase']=='fetch'
    assert not _raws()


def test_empty_day_keeps_original_page_without_history(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch)
    summary=corpus.ingest_tennisexplorer_history('2026-03-03',provider=_stub())
    assert summary['dates']==1 and summary['matches']==0 and not summary['errors']
    assert json.loads(_raws()[0]['response_json'])['html'].startswith('<table>')


def test_rerun_does_not_relabel_old_summary_as_verified_source(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch);stub=_stub()
    raw_id=corpus.store_raw_response('tennisexplorer','tennisexplorer/results',{}, {'summary':'legacy'},200)
    with get_connection() as conn:
        corpus.player_identity.ensure_identity_schema(conn)
        corpus._store_history(conn,'2026-03-01',stub.fetch_results_for_date('2026-03-01')[0],raw_id)
        before=[dict(r) for r in conn.execute('SELECT * FROM player_match_history ORDER BY id')]
    summary=corpus.ingest_tennisexplorer_history('2026-03-01',provider=stub)
    assert not summary['errors']
    with get_connection() as conn:assert [dict(r) for r in conn.execute('SELECT * FROM player_match_history ORDER BY id')]==before
    assert len(_raws())==2 and json.loads(_raws()[0]['response_json'])=={'summary':'legacy'}


def test_provider_results_api_keeps_same_parser_output(monkeypatch):
    page=_stub().fetch_results_page_for_date('2026-03-01')
    provider=TennisExplorerResultsProvider();seen=[]
    def fetch(url):seen.append(url);return page.html
    monkeypatch.setattr(provider,'_fetch_html',fetch)
    assert provider.fetch_results_for_date('2026-03-01')==parse_results_page(page.html)
    fetched=provider.fetch_results_page_for_date('2026-03-01')
    assert seen==[page.requested_url,page.requested_url]
    assert fetched.html==page.html and fetched.match_date=='2026-03-01'


def test_history_failure_keeps_source_committed(tmp_path,monkeypatch):
    _setup(tmp_path,monkeypatch)
    def fail(*args):raise RuntimeError('simulated history write failure')
    monkeypatch.setattr(corpus,'_store_history',fail)
    with pytest.raises(RuntimeError,match='history write failure'):
        corpus.ingest_tennisexplorer_history('2026-03-01',provider=_stub())
    assert len(_raws())==1
    assert 'Ivan One' in json.loads(_raws()[0]['response_json'])['html']


def test_source_survives_lossless_retention(tmp_path,monkeypatch):
    from tennis_wc.database.payload_archive import compact_payloads,read_payload
    _setup(tmp_path,monkeypatch)
    corpus.ingest_tennisexplorer_history('2026-03-01',provider=_stub())
    original=_raws()[0]
    with get_connection() as conn:
        compact_payloads(conn,'raw_response','id=?',(original['id'],))
        stored=conn.execute('SELECT response_json FROM raw_api_responses WHERE id=?',(original['id'],)).fetchone()[0]
        assert stored==''
        assert read_payload(conn,'raw_response',original['id'],stored)==original['response_json']


def test_same_source_preserves_numeric_history_and_elo(tmp_path,monkeypatch):
    from tennis_wc.modelling.elo_builder import build_sackmann_elo
    stub=_stub();outputs=[]
    for mode in ['baseline','candidate']:
        _setup(tmp_path/mode,monkeypatch)
        if mode=='baseline':
            raw_id=corpus.store_raw_response('tennisexplorer','tennisexplorer/results',{}, {'summary':'old'},200)
            with get_connection() as conn:
                corpus.player_identity.ensure_identity_schema(conn)
                for day in ['2026-03-01','2026-03-02']:
                    corpus._store_history(conn,day,parse_results_page(stub.fetch_results_page_for_date(day).html)[0],raw_id)
        else:corpus.ingest_tennisexplorer_history('2026-03-01','2026-03-02',provider=stub)
        build_sackmann_elo()
        with get_connection() as conn:
            outputs.append(dict(history=[tuple(r) for r in conn.execute('SELECT player_id,opponent_id,match_date,won,tour,tournament_level FROM player_match_history ORDER BY id')],
                                players=[tuple(r) for r in conn.execute('SELECT id,name,tour,overall_elo,surface_elo_json FROM players ORDER BY id')],
                                elo_v2=[tuple(r) for r in conn.execute('SELECT * FROM player_elo_history_v2 ORDER BY player_id,as_of_date,surface')]))
    assert outputs[0]==outputs[1]
