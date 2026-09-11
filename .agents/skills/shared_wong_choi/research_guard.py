"""Fail-closed execution guard backed by the existing pinned HOT review cursor.

An allowed check permits research computation only, never model promotion. There
is deliberately no reset/unfreeze API. Changing a ruler needs independent human
review; a new spec, delivered digest or advanced cursor cannot restart its age.
Explicit production-metadata reviews can latch incidents independently. Verified
sample and daily-closure producers remain separate, unfinished integrations.
"""
from __future__ import annotations

import sqlite3
import os
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from .contracts import Domain
from .research_evaluation import _strict_json
from .research_index import _at, _safe, _Reader, _hash, _encoded
from .research_registry import ExperimentRegistry
from .research_runner import ResearchRuntime

INCIDENT_SCHEMA = 'wong-choi-production-incident-freeze/v1'


def _incident_context(runtime: ResearchRuntime, registry: ExperimentRegistry, domain: Domain) -> dict:
    return {'domain': domain.value, 'registry': str(_safe(registry.root)),
            'warm_root': str(_safe(runtime.review_warm_root or runtime.warm_root))}


def _incident_path(runtime: ResearchRuntime, domain: Domain) -> Path:
    state = _safe(runtime.state_root)
    if state.is_relative_to(_safe(runtime.review_warm_root or runtime.warm_root)):
        raise ValueError('HOT incident state must be outside WARM')
    return _safe(state / 'research-incident-freezes' / (domain.value + '.json'))


def _load_production_incident(runtime: ResearchRuntime, registry: ExperimentRegistry, domain: Domain) -> dict | None:
    from .research_index import _hashed
    from .research_production_incidents import verify_production_incidents
    path = _incident_path(runtime, domain)
    if not path.exists():
        return None
    value, _ = _Reader(lambda: None, max_record_bytes=65536, max_total_bytes=65536).read(path)
    _hashed(value, INCIDENT_SCHEMA)
    if (set(value) != {'schema_version', 'domain', 'registry', 'warm_root', 'source_root', 'observed_at',
                      'report', 'reason', 'model_promotion_allowed', 'content_hash'}
            or any(value[key] != item for key, item in _incident_context(runtime, registry, domain).items())
            or value['model_promotion_allowed'] is not False):
        raise ValueError('incident freeze scope mismatch')
    root, observed = _safe(value['source_root']), _at(value['observed_at'])
    if value['report'] is None:
        if value['reason'] != 'source_unverified':
            raise ValueError('invalid unverified source freeze')
    else:
        verify_production_incidents(value['report'], root=root, domain=domain, as_of=observed)
        if not value['report']['events'] or value['reason'] != 'metadata_incidents':
            raise ValueError('freeze needs positive incident evidence')
    return value


def production_incident_status(runtime: ResearchRuntime, registry: ExperimentRegistry, domain: Domain) -> str | None:
    """Read the first durable source incident; no implicit acknowledgement/reset."""
    try:
        return 'research_frozen_production_evidence' if _load_production_incident(runtime, registry, domain) else None
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError):
        return 'research_review_unavailable'


def production_incident_projection(runtime: ResearchRuntime, registry: ExperimentRegistry, domain: Domain) -> dict | None:
    """Compact immutable-latch proof for truthful subsequent review summaries."""
    value = _load_production_incident(runtime, registry, domain)
    if value is None:
        return None
    events = value['report']['events'] if value['report'] is not None else [
        {'kind': 'incident', 'event_id': 'production-unverified:' + value['content_hash'],
         'occurred_at': value['observed_at'], 'evidence_digest': value['content_hash']}]
    return {key: value[key] for key in ('content_hash', 'observed_at', 'source_root', 'reason')} | {'events': events}


def persist_production_incident(runtime: ResearchRuntime, registry: ExperimentRegistry, domain: Domain,
                                *, source_root: Path, observed_at: datetime, report: dict | None) -> Path:
    """Latch before review receipts/acknowledgement; preserve the first observation."""
    from .research_review_cursor import _fsync_directory
    from .research_production_incidents import verify_production_incidents
    source_root, observed = _safe(source_root), _at(observed_at)
    if report is not None:
        verify_production_incidents(report, root=source_root, domain=domain, as_of=observed)
        if not report['events']:
            raise ValueError('no production incident to persist')
    path = _incident_path(runtime, domain)
    if not path.parent.parent.is_dir():
        raise ValueError('existing HOT state root required')
    prior = production_incident_status(runtime, registry, domain)
    if prior is not None:
        if prior != 'research_frozen_production_evidence':
            raise ValueError('existing incident latch is unverified')
        return path
    payload = {'schema_version': INCIDENT_SCHEMA, **_incident_context(runtime, registry, domain),
               'source_root': str(source_root), 'observed_at': observed.isoformat(), 'report': report,
               'reason': 'metadata_incidents' if report is not None else 'source_unverified',
               'model_promotion_allowed': False}
    payload['content_hash'] = _hash(payload)
    encoded = _encoded(payload)
    if len(encoded) > 65536:
        raise ValueError('incident latch exceeds metadata bound')
    path.parent.mkdir(mode=0o700, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        if production_incident_status(runtime, registry, domain) != 'research_frozen_production_evidence':
            raise ValueError('racing incident write unverified')
        return path
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)
    _fsync_directory(path.parent.parent)
    return path


def _ruler_freeze(path: Path, config: dict, *, persist: bool = False) -> bool:
    """Create-only HOT latch; an uncertain or malformed write never allows work."""
    from .research_review_cursor import _fsync_directory
    target = _safe(path.with_suffix('.freeze.json'))
    payload = {'schema_version': 'wong-choi-research-ruler-freeze/v1',
               'config': config, 'reason': 'research_frozen_ruler_90_day',
               'due_at': (_at(config['ruler_released_at']) + timedelta(days=90)).isoformat(),
               'model_promotion_allowed': False, 'automatic_unfreeze_allowed': False}
    sealed = {**payload, 'content_hash': _hash(payload)}
    if target.exists():
        stored, _ = _Reader(lambda: None, max_record_bytes=65536, max_total_bytes=65536).read(target)
        if stored != sealed:
            raise ValueError('freeze scope or payload mismatch')
        return True
    if persist:
        # The cursor directory already exists; never create a new state root.
        if not target.parent.is_dir():
            raise ValueError('existing cursor directory required for freeze')
        encoded = _encoded(sealed)
        if len(encoded) > 65536:
            raise ValueError('freeze metadata too large')
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            # A racing writer may still be partial: bounded verification either
            # proves its identical latch or blocks, never replaces it.
            if not _ruler_freeze(path, config):
                raise ValueError('competing freeze disappeared before verification')
            return True
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(target.parent)
        return True
    return False


def research_gate_status(runtime: ResearchRuntime, registry: ExperimentRegistry,
                         domain: Domain, ruler_digest: str, *, queue_root: Path | None = None) -> str | None:
    """Revalidate bounded, read-only cursor/proof and latch expired UTC clocks.

    Missing/locked/corrupt state is not an implicit opt-out. Review, delivery,
    source inventory and reconciliation must not call this computation guard:
    they remain available to investigate a freeze under normal resource limits.
    """
    from .research_review_cursor import ResearchReviewCursorRunner, MAX_STATE_BYTES
    context = replace(runtime, warm_root=runtime.review_warm_root or runtime.warm_root)
    cursor = ResearchReviewCursorRunner(context, registry)
    try:
        incident = production_incident_status(context, registry, domain)
        if incident:
            return incident
        path = cursor._path(domain)
        with closing(sqlite3.connect(f'file:{quote(str(path))}?mode=ro', uri=True,
                                     timeout=0, isolation_level=None)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            size = db.execute('SELECT length(CAST(payload AS BLOB)) FROM cursor_state WHERE id=1').fetchone()
            if size is None or not 0 < size[0] <= MAX_STATE_BYTES:
                raise ValueError('invalid cursor size')
            raw = _strict_json(db.execute('SELECT payload FROM cursor_state WHERE id=1').fetchone()[0])
            config = raw['config']
            configured_queue = Path(config['queue_root']) if config['queue_root'] is not None else None
            if queue_root is not None and configured_queue != queue_root.expanduser().absolute():
                raise ValueError('queue not bound to review cursor')
            saved = cursor._read_state(db, domain, ruler_digest, config['ruler_released_at'],
                                       configured_queue, lambda: None, config.get('production_evidence_root'))
            if config.get('production_evidence_root') is not None and saved['generation'] == 0:
                return 'research_source_review_required'
            now = _at(runtime.clock())
            if now < _at(saved['last_as_of']):
                raise ValueError('clock before verified review progress')
            expired = now >= _at(saved['config']['ruler_released_at']) + timedelta(days=90)
            if _ruler_freeze(path, saved['config'], persist=expired):
                return 'research_frozen_ruler_90_day'
            return None
    except (OSError, RuntimeError, sqlite3.Error, ValueError, KeyError, TypeError, AttributeError):
        return 'research_review_unavailable'
