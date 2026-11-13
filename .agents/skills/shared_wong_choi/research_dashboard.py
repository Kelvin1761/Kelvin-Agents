"""Explicit publication of verified research projections to the private Dashboard.

The remote KV is a disposable display cache, never canonical research evidence.
No scheduler, credential setup, D1 write, scoring or promotion is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from .research_presentation import prepare_review_presentation
from .research_index import ResearchIndexError
from .research_safety import _json, ResearchSafetyError


MAX_BYTES = 256 * 1024


def prepare_publication(receipt_path, *, review_summary_path=None):
    projection = prepare_review_presentation(
        receipt_path, review_summary_path=review_summary_path,
    )['projection']
    publication = {
        'schema_version': 'wong-choi-private-research-feed/v1',
        'domain': projection['domain'], 'as_of': projection['as_of'],
        'projection': projection, 'model_promotion_allowed': False,
        'current_state_verified': False,
    }
    _encoded(publication)
    return publication


def _encoded(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(raw) > MAX_BYTES:
        raise ValueError('research projection exceeds private cache size bound')
    return raw


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('private publication redirects forbidden')


def publish_publication(receipt_path, *, endpoint, token, review_summary_path=None, opener=None):
    """One HTTPS POST, no retries, to an explicitly configured Dashboard endpoint."""
    target = urllib.parse.urlsplit(endpoint)
    if (target.scheme != 'https' or not target.hostname or target.username is not None
            or target.password is not None or target.query or target.fragment
            or target.path != '/api/research' or target.port not in (None, 443)):
        raise ValueError('explicit HTTPS private research endpoint required')
    if not isinstance(token, str) or not token.strip() or '\r' in token or '\n' in token:
        raise ValueError('existing Dashboard authorization required')
    publication = prepare_publication(receipt_path, review_summary_path=review_summary_path)
    raw = _encoded(publication)
    expected = hashlib.sha256(raw).hexdigest()
    request = urllib.request.Request(endpoint, data=raw, method='POST', headers={
        'Content-Type': 'application/json; charset=utf-8', 'Authorization': 'Bearer ' + token,
    })
    transport = opener or urllib.request.build_opener(_NoRedirect())
    try:
        with transport.open(request, timeout=30) as response:
            if response.status != 200:
                raise ValueError('private publication not acknowledged')
            response_bytes = response.read(65537)
            if len(response_bytes) > 65536:
                raise ValueError('oversized acknowledgement')
            reply = _json(response_bytes)
            if (not isinstance(reply, dict) or set(reply) != {'status', 'domain', 'sha256', 'model_promotion_allowed'}
                    or reply['status'] not in {'stored', 'already_stored'}
                    or reply['domain'] != publication['domain'] or reply['sha256'] != expected
                    or reply['model_promotion_allowed'] is not False):
                raise ValueError('private publication acknowledgement mismatch')
    except (OSError, ValueError, urllib.error.URLError, ResearchSafetyError):
        # Never expose HTTP error bodies/URLs/headers, which may contain secrets.
        raise ValueError('private publication unconfirmed; inspect cache before retry') from None
    return {**reply, 'current_state_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--review-summary', type=Path)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--endpoint')
    args = parser.parse_args()
    if bool(args.endpoint) != args.publish:
        parser.error('--endpoint and --publish must be selected together')
    try:
        result = (publish_publication(args.receipt, review_summary_path=args.review_summary,
                                     endpoint=args.endpoint, token=os.environ.get('WC_SYNC_TOKEN', ''))
                  if args.publish else prepare_publication(args.receipt, review_summary_path=args.review_summary))
    except (ValueError, OSError, ResearchIndexError, ResearchSafetyError):
        print(json.dumps({'status': 'blocked_or_unconfirmed', 'model_promotion_allowed': False}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
