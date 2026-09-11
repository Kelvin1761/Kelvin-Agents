"""Read-only Stage 4 metadata contradictions; never qualify settled samples.

Artifact references and 'settled' labels are claims, not result verification.
Only objectively inconsistent metadata becomes an incident here. No findings is
not full producer/source coverage, PIT readiness, or model acceptance.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

from .contracts import Domain
from .evidence import ArtifactRef, EvidenceRecord, RecordKind
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe

SCHEMA = 'wong-choi-production-metadata-incidents/v1'
CODES = frozenset({'settlement_event_after_settled_at', 'settlement_outcome_artifacts_missing',
                   'settlement_before_decision', 'settlement_event_mismatch', 'settlement_time_after_record'})


def _events(root: str, findings: list[dict]) -> list[dict]:
    return [{'kind': 'incident',
             'event_id': 'production-metadata:' + _hash({'root': root, 'record_id': item['record_id'], 'codes': item['codes']}),
             'occurred_at': item['created_at'], 'evidence_digest': item['content_hash']}
            for item in findings]


def collect_production_incidents(*, root: Path, domain: Domain, as_of: datetime,
                                 checkpoint: Callable[[], None] = lambda: None) -> dict:
    """Bounded, stable snapshot of one domain's existing append-only metadata."""
    if not isinstance(domain, Domain):
        raise ValueError('known domain required')
    root, end = _safe(root), _at(as_of)
    if not root.is_dir() or not (root / 'records').is_dir():
        raise ValueError('production evidence store unavailable, not an empty healthy source')
    reader = _Reader(checkpoint)
    records = {}
    prefix = quote(f'wc:{domain.value}:', safe='._-')
    for kind in RecordKind:
        for path in reader.listing(root / 'records' / kind.value):
            identity = unquote(path.stem)
            parts = identity.split(':')
            if (path.name != quote(identity, safe='._-') + '.json' or len(parts) < 3
                    or parts[0] != 'wc' or parts[1] not in {item.value for item in Domain}):
                raise ValueError('noncanonical evidence filename cannot be silently omitted')
            if not path.name.startswith(prefix):
                continue
            raw, _ = reader.read(path)
            record = EvidenceRecord(raw['record_id'], RecordKind(raw['kind']), Domain(raw['domain']),
                                    raw['created_at'], raw['body'], raw['links'],
                                    tuple(ArtifactRef(**item) for item in raw['artifacts']))
            if (record.to_dict() != raw or record.kind != kind or record.domain != domain
                    or path.name != quote(record.record_id, safe='._-') + '.json'):
                raise ValueError('noncanonical or corrupt production evidence')
            if _at(record.created_at) <= end:
                if record.record_id in records:
                    raise ValueError('duplicate production evidence identity across kinds')
                records[record.record_id] = raw
    required = {RecordKind.PREDICTION.value: ('model_release_id', RecordKind.MODEL_RELEASE.value),
                RecordKind.DECISION.value: ('prediction_id', RecordKind.PREDICTION.value),
                RecordKind.SETTLEMENT.value: ('decision_id', RecordKind.DECISION.value)}
    for raw in records.values():
        if raw['kind'] in required:
            link, kind = required[raw['kind']]
            parent = records.get(raw['links'][link])
            if not parent or parent['kind'] != kind or parent['domain'] != domain.value:
                raise ValueError('missing, future, wrong-kind or cross-domain evidence parent')
    findings = []
    for identity, raw in sorted(records.items()):
        if raw['kind'] != RecordKind.SETTLEMENT.value:
            continue
        body = raw['body']
        if body['settlement_state'] not in {'settled', 'hit', 'miss'}:
            continue
        decision = records[raw['links']['decision_id']]
        prediction = records[decision['links']['prediction_id']]
        settled = _at(body['settled_at'])
        codes = set()
        if not raw['artifacts']:
            codes.add('settlement_outcome_artifacts_missing')
        if settled > _at(raw['created_at']):
            codes.add('settlement_time_after_record')
        if settled < max(_at(decision['created_at']), _at(prediction['created_at'])):
            codes.add('settlement_before_decision')
        if body.get('event_id') != prediction['body']['event_id']:
            codes.add('settlement_event_mismatch')
        event = body.get('event_id', '')
        try:
            # Existing domain writers use a date alone or date + venue suffix.
            # Do not reinterpret opaque IDs or timestamp timezones as dates.
            event_date = date.fromisoformat(event[:10]) if len(event) == 10 or event[10:11] in {' ', '|', '_'} else None
        except (ValueError, TypeError):
            event_date = None  # Unknown identifiers cannot qualify samples.
        if event_date is not None and event_date > settled.astimezone(ZoneInfo('Australia/Sydney')).date():
            codes.add('settlement_event_after_settled_at')
        if codes:
            findings.append({'record_id': identity, 'created_at': raw['created_at'],
                             'content_hash': raw['content_hash'], 'codes': sorted(codes)})
    reader.recheck()
    report = {'schema_version': SCHEMA, 'domain': domain.value, 'root': str(root), 'as_of': end.isoformat(),
              'records_seen': len(records), 'findings': findings, 'events': _events(str(root), findings),
              'artifact_contents_verified': False, 'source_coverage_complete': False,
              'verified_monitoring_samples': None, 'model_promotion_allowed': False}
    report['content_hash'] = _hash(report)
    verify_production_incidents(report, root=root, domain=domain, as_of=end)
    return report


def verify_production_incidents(report: dict, *, root: Path, domain: Domain, as_of: datetime) -> None:
    """Bounded parent proof validation; bulk source reads stay in the worker."""
    _hashed(report, SCHEMA)
    expected = {'schema_version', 'domain', 'root', 'as_of', 'records_seen', 'findings', 'events',
                'artifact_contents_verified', 'source_coverage_complete', 'verified_monitoring_samples',
                'model_promotion_allowed', 'content_hash'}
    if (set(report) != expected or report['domain'] != domain.value or report['root'] != str(_safe(root))
            or report['as_of'] != _at(as_of).isoformat() or len(_encoded(report)) > 32768):
        raise ValueError('production incident proof scope or size mismatch')
    if (any(report[key] is not False for key in ('artifact_contents_verified', 'source_coverage_complete', 'model_promotion_allowed'))
            or report['verified_monitoring_samples'] is not None):
        raise ValueError('metadata cannot grant sample or model authority')
    if type(report['records_seen']) is not int or not 0 <= report['records_seen'] <= 10000:
        raise ValueError('invalid source metadata count')
    if not isinstance(report['findings'], list) or len(report['findings']) > report['records_seen']:
        raise ValueError('invalid incident finding count')
    ids = set()
    from .research_review_clock import _digest
    for item in report['findings']:
        if (set(item) != {'record_id', 'created_at', 'content_hash', 'codes'} or item['record_id'] in ids
                or not item['record_id'].startswith(f'wc:{domain.value}:') or _at(item['created_at']) > _at(as_of)
                or not item['codes'] or item['codes'] != sorted(set(item['codes'])) or not set(item['codes']) <= CODES):
            raise ValueError('invalid production incident finding')
        _digest(item['content_hash'])
        ids.add(item['record_id'])
    if report['events'] != _events(str(root), report['findings']):
        raise ValueError('production incident event/proof mismatch')
