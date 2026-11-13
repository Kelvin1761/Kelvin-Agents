from __future__ import annotations

import json
import hashlib
import io
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.research_dashboard import prepare_publication, publish_publication
from test_research_presentation import receipt


def test_real_verified_receipt_projects_without_changing_source(tmp_path):
    path = receipt(tmp_path)
    original = path.read_bytes()
    publication = prepare_publication(path)
    assert publication['projection']['receipt_hash'] == json.loads(original)['content_hash']
    assert publication['projection']['counts']['experiments'] == 1
    assert publication['model_promotion_allowed'] is False
    assert publication['current_state_verified'] is False
    assert path.read_bytes() == original


@pytest.mark.parametrize('endpoint', ['http://example.com/api/research',
    'https://user:pass@example.com/api/research', 'https://example.com/api/sync',
    'https://example.com/api/research?token=secret'])
def test_publisher_rejects_wrong_endpoint_before_network(tmp_path, endpoint):
    with pytest.raises(ValueError):
        publish_publication(receipt(tmp_path), endpoint=endpoint, token='test')


class Reply(io.BytesIO):
    status = 200


def test_actual_python_publisher_through_node_api_and_private_read(tmp_path):
    path = receipt(tmp_path)
    calls = []
    repo = Path(__file__).resolve().parents[4]
    handler = (repo / 'Horse_Racing_Dashboard/functions/api/research.js').as_uri()

    class NodeEndpoint:
        def open(self, request, timeout):
            calls.append(request)
            assert timeout == 30
            # Execute the actual Pages handler, not a parallel Python mock.
            code = '''
import {webcrypto} from 'node:crypto';
import fs from 'node:fs';
globalThis.crypto ||= webcrypto;
const handler = await import(process.argv[1]);
const body = fs.readFileSync(0, 'utf8'), values = new Map();
const env = {WC_SYNC_TOKEN:'test-private', WC_STATE:{
  get:async k=>values.get(k)??null, put:async(k,v)=>values.set(k,v)}};
const headers = {'Authorization':'Bearer test-private','Content-Type':'application/json'};
const post = await handler.onRequestPost({env,request:new Request('https://dashboard.example/api/research',{method:'POST',headers,body})});
const ack = await post.json();
const get = await handler.onRequestGet({env,request:new Request('https://dashboard.example/api/research',{headers})});
const feed = await get.json();
if(post.status!==200||get.status!==200||feed.snapshots[0].sha256!==ack.sha256) throw Error('integration failed');
if(JSON.stringify(feed.snapshots[0].publication)!==JSON.stringify(JSON.parse(body))) throw Error('changed projection');
if([...values.keys()].some(k=>!k.startsWith('STAGE5_RESEARCH_V1:'))) throw Error('wrong store');
process.stdout.write(JSON.stringify(ack));
'''
            result = subprocess.run(['node', '--input-type=module', '-e', code, handler],
                                    input=request.data, capture_output=True, check=True)
            return Reply(result.stdout)

    before = {p: p.read_bytes() for p in tmp_path.rglob('*.json')}
    result = publish_publication(path, endpoint='https://dashboard.example/api/research',
                                 token='test-private', opener=NodeEndpoint())
    assert result['status'] == 'stored' and result['current_state_verified'] is False
    assert result['sha256'] == hashlib.sha256(calls[0].data).hexdigest()
    assert before == {p: p.read_bytes() for p in before}
    assert len(calls) == 1


@pytest.mark.parametrize('fault', ['bad_hash', 'authority', 'oversize', 'lost_reply', 'bad_json'])
def test_unconfirmed_publication_does_not_retry_or_expose_secrets(tmp_path, fault):
    calls = []
    class Endpoint:
        def open(self, request, **kwargs):
            calls.append(request)
            if fault == 'lost_reply':
                raise OSError('test-private must not leak')
            reply = {'status': 'stored', 'domain': 'au', 'sha256': hashlib.sha256(request.data).hexdigest(),
                     'model_promotion_allowed': False}
            if fault == 'bad_hash': reply['sha256'] = 'f' * 64
            if fault == 'authority': reply['model_promotion_allowed'] = True
            raw = json.dumps(reply).encode()
            if fault == 'oversize': raw += b' ' * 65536
            if fault == 'bad_json': raw = b'{"test-private":'
            return Reply(raw)
    with pytest.raises(ValueError) as error:
        publish_publication(receipt(tmp_path), endpoint='https://dashboard.example/api/research',
                            token='test-private', opener=Endpoint())
    assert 'test-private' not in str(error.value)
    assert error.value.__suppress_context__ is True
    assert len(calls) == 1


def test_changed_receipt_cannot_publish(tmp_path):
    path = receipt(tmp_path)
    raw = json.loads(path.read_text()); raw['content_hash'] = 'f' * 64
    path.write_text(json.dumps(raw))
    from shared_wong_choi.research_index import ResearchIndexError
    with pytest.raises(ResearchIndexError):
        prepare_publication(path)
