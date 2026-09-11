"""Transactional HOT calendar cursor around the existing supervised review API.

Explicit local initialization is required. This module installs no scheduler and
never treats a reviewed window as notification delivery, model or ruler approval.
Large registry/receipt work stays in the existing supervised worker.
"""
from __future__ import annotations

import math
import os
import sqlite3
import stat
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from .contracts import Domain
from .research_evaluation import EvaluationError, _strict_json
from .research_index import ResearchIndexError, _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_registry import ExperimentRegistry
from .research_resources import ResourceInterrupted, _resource_status
from .research_review_clock import plan_reviews
from .research_review_runtime import ResearchReviewResult, ResearchReviewRunner, verify_review_summary
from .research_runner import ResearchDisposition, ResearchRuntime

SCHEMA = 'wong-choi-review-cursor/v1'
SAMPLE_SCHEMA = 'wong-choi-review-sample-cursor/v1'
STORAGE_SCHEMA = 'wong-choi-review-storage-cursor/v1'
LIVENESS_SCHEMA = 'wong-choi-review-liveness-cursor/v1'
MAX_STATE_BYTES = 65536
MAX_DB_BYTES = 1024 * 1024


@dataclass(frozen=True)
class CursorReviewResult:
    disposition: ResearchDisposition
    status: str
    cursor_path: Path | None = None
    generation: int | None = None
    advanced: bool = False
    review: ResearchReviewResult | None = None
    telegram_delivery_confirmed: bool = False


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _seal(value: dict) -> dict:
    result = {key: item for key, item in value.items() if key != 'content_hash'}
    result['content_hash'] = _hash(result)
    if len(_encoded(result)) > MAX_STATE_BYTES:
        raise ValueError('review cursor metadata too large')
    return result


class ResearchReviewCursorRunner:
    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def _path(self, domain: Domain, *, existing: bool = True) -> Path:
        if not isinstance(domain, Domain):
            raise ValueError('known domain required')
        root = _safe(self.runtime.state_root / 'research-review-cursors')
        if not root.is_dir() or root.is_relative_to(_safe(self.runtime.warm_root)):
            raise ValueError('existing HOT cursor root outside WARM required')
        path = _safe(root / (domain.value + '.sqlite3'))
        for suffix in ('', '-journal', '-wal', '-shm'):
            item = _safe(Path(str(path) + suffix))
            if item.exists():
                info = item.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DB_BYTES:
                    raise ValueError('invalid or oversized cursor file')
        if existing and not path.is_file():
            raise ValueError('cursor initialization or restore required')
        return path

    def _config(self, domain: Domain, initial_window_start: datetime, ruler_digest: str,
                ruler_released_at: datetime, queue_root: Path | None,
                production_evidence_root: Path | None = None) -> dict:
        start, release = _at(initial_window_start), _at(ruler_released_at)
        plan_reviews(domain=domain, window_start=start, now=start, ruler_digest=ruler_digest,
                     ruler_released_at=release)
        config = {'domain': domain.value, 'registry': str(_safe(self.registry.root)),
                'warm_root': str(_safe(self.runtime.warm_root)), 'initial_window_start': start.isoformat(),
                'ruler_digest': ruler_digest, 'ruler_released_at': release.isoformat(),
                'queue_root': str(_safe(queue_root)) if queue_root is not None else None}
        if production_evidence_root is not None:
            config['production_evidence_root'] = str(_safe(production_evidence_root))
        return config

    def initialize(self, *, domain: Domain, initial_window_start: datetime, ruler_digest: str,
                   ruler_released_at: datetime, queue_root: Path | None = None,
                   production_evidence_root: Path | None = None) -> Path:
        """Create one new cursor only; never repair/reset an existing state file."""
        config = self._config(domain, initial_window_start, ruler_digest, ruler_released_at, queue_root, production_evidence_root)
        path = self._path(domain, existing=False)
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        value = _seal({'schema_version': SCHEMA, 'config': config, 'generation': 0,
                       'window_start': config['initial_window_start'], 'last_as_of': config['initial_window_start'],
                       'last_review': None, 'model_promotion_allowed': False, 'telegram_delivery_confirmed': False})
        # On setup failure the partial file is retained, never silently reset.
        with closing(sqlite3.connect(path, timeout=0, isolation_level=None)) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE cursor_state (id INTEGER PRIMARY KEY CHECK (id=1), payload TEXT NOT NULL)')
            db.execute('INSERT INTO cursor_state VALUES (1, ?)', (_encoded(value).decode(),))
            db.execute('COMMIT')
        _fsync_directory(path.parent)
        return path

    def initialize_racing_samples(
            self, *, domain: Domain, evidence_root: Path,
            relocation_roots: tuple[Path, ...] = ()) -> Path:
        """Attach a new AU/HKJC sample watermark; never infer or overwrite one."""
        if domain not in {Domain.AU, Domain.HKJC}:
            raise ValueError('AU/HKJC domain required')
        return self.initialize_monitoring_samples(
            domain=domain, evidence_root=evidence_root,
            relocation_roots=relocation_roots,
        )

    def initialize_monitoring_samples(
            self, *, domain: Domain, evidence_root: Path,
            relocation_roots: tuple[Path, ...] = ()) -> Path:
        """Attach one create-only domain sample watermark; never infer/reset it."""
        if not isinstance(domain, Domain) or not isinstance(relocation_roots, tuple):
            raise ValueError('known domain and tuple relocation roots required')
        path = self._path(domain)
        config = {
            'domain': domain.value,
            'evidence_root': str(_safe(evidence_root)),
            'relocation_roots': [str(_safe(item)) for item in relocation_roots],
        }
        value = _seal({
            'schema_version': SAMPLE_SCHEMA,
            'config': config,
            'generation': 0,
            'last_report': None,
            'model_promotion_allowed': False,
            'reevaluate_promotion_allowed': False,
        })
        with closing(sqlite3.connect(path, timeout=0, isolation_level=None)) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            cursor_payload = _strict_json(
                db.execute('SELECT payload FROM cursor_state WHERE id=1').fetchone()[0]
            )
            _hashed(cursor_payload, SCHEMA)
            if cursor_payload['config']['domain'] != domain.value:
                raise ValueError('sample watermark domain differs from calendar cursor')
            db.execute(
                'CREATE TABLE racing_sample_state '
                '(id INTEGER PRIMARY KEY CHECK (id=1), payload TEXT NOT NULL)'
            )
            db.execute(
                'INSERT INTO racing_sample_state VALUES (1, ?)',
                (_encoded(value).decode(),),
            )
            db.execute('COMMIT')
        _fsync_directory(path.parent)
        return path

    def initialize_storage_evidence(
            self, *, domain: Domain, repo_root: Path,
            storage_state_root: Path) -> Path:
        """Attach create-only storage source config; never infer or overwrite it."""
        if not isinstance(domain, Domain):
            raise ValueError('known domain required')
        path = self._path(domain)
        config = {
            'domain': domain.value,
            'repo_root': str(_safe(repo_root)),
            'storage_state_root': str(_safe(storage_state_root)),
        }
        value = _seal({
            'schema_version': STORAGE_SCHEMA,
            'config': config,
            'generation': 0,
            'last_report': None,
            'model_promotion_allowed': False,
            'process_liveness_verified': False,
            'live_drift_verified': False,
        })
        with closing(sqlite3.connect(path, timeout=0, isolation_level=None)) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            cursor_payload = _strict_json(
                db.execute('SELECT payload FROM cursor_state WHERE id=1').fetchone()[0]
            )
            _hashed(cursor_payload, SCHEMA)
            if cursor_payload['config']['domain'] != domain.value:
                raise ValueError('storage evidence domain differs from calendar cursor')
            db.execute(
                'CREATE TABLE storage_evidence_state '
                '(id INTEGER PRIMARY KEY CHECK (id=1), payload TEXT NOT NULL)'
            )
            db.execute(
                'INSERT INTO storage_evidence_state VALUES (1, ?)',
                (_encoded(value).decode(),),
            )
            db.execute('COMMIT')
        _fsync_directory(path.parent)
        return path

    def initialize_liveness_evidence(
            self, *, domain: Domain, queue_root: Path,
            lease_root: Path) -> Path:
        """Attach create-only queue/lease config; never infer current liveness."""
        if not isinstance(domain, Domain):
            raise ValueError('known domain required')
        path = self._path(domain)
        config = {
            'domain': domain.value,
            'queue_root': str(_safe(queue_root)),
            'lease_root': str(_safe(lease_root)),
        }
        value = _seal({
            'schema_version': LIVENESS_SCHEMA,
            'config': config,
            'generation': 0,
            'last_report': None,
            'model_promotion_allowed': False,
            'queue_mutation_allowed': False,
        })
        with closing(sqlite3.connect(path, timeout=0, isolation_level=None)) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            cursor_payload = _strict_json(
                db.execute('SELECT payload FROM cursor_state WHERE id=1').fetchone()[0]
            )
            _hashed(cursor_payload, SCHEMA)
            if (cursor_payload['config']['domain'] != domain.value
                    or cursor_payload['config']['queue_root'] != config['queue_root']):
                raise ValueError('liveness source differs from calendar queue')
            db.execute(
                'CREATE TABLE liveness_evidence_state '
                '(id INTEGER PRIMARY KEY CHECK (id=1), payload TEXT NOT NULL)'
            )
            db.execute(
                'INSERT INTO liveness_evidence_state VALUES (1, ?)',
                (_encoded(value).decode(),),
            )
            db.execute('COMMIT')
        _fsync_directory(path.parent)
        return path

    def _sample_report(self, reference: dict, domain: Domain, config: dict,
                       checkpoint) -> dict:
        legacy_fields = {
            'path', 'content_hash', 'observed_at', 'sample_count',
            'source_coverage_complete',
        }
        current_fields = {
            'path', 'content_hash', 'observed_at', 'scope_counts',
            'source_coverage_complete',
        }
        if (not isinstance(reference, dict)
                or frozenset(reference) not in {frozenset(legacy_fields),
                                                frozenset(current_fields)}):
            raise ValueError('invalid monitoring sample report reference')
        path = _safe(Path(reference['path']))
        phase_root = _safe(self.runtime.warm_root / 'research-phases' / domain.value)
        prefixes = {
            Domain.AU: 'racing-monitoring-samples-',
            Domain.HKJC: 'racing-monitoring-samples-',
            Domain.NBA: 'nba-monitoring-samples-',
            Domain.TENNIS: 'tennis-monitoring-samples-',
        }
        if (not path.is_file() or path.is_symlink() or not path.is_relative_to(phase_root)
                or path.stat().st_size > 1048576
                or not path.parent.parent.name.startswith(prefixes[domain])):
            raise ValueError('monitoring sample report is outside owned phase root')
        from .research_monitoring_samples import (
            monitoring_report_reference,
            monitoring_sample_snapshots,
        )
        report = _strict_json(path.read_text())
        samples = monitoring_sample_snapshots(report)
        expected_reference = monitoring_report_reference(path, report)
        if set(reference) == legacy_fields:
            if len(samples) != 1:
                raise ValueError('legacy sample reference requires one scope')
            expected_reference = {
                'path': str(path), 'content_hash': report['content_hash'],
                'observed_at': samples[0].observed_at.isoformat(),
                'sample_count': len(samples[0].unit_ids),
                'source_coverage_complete': report['source_coverage_complete'],
            }
        if (reference != expected_reference
                or any(sample.domain is not domain for sample in samples)
                or report['root'] != config['evidence_root']
                or report['relocation_roots'] != config['relocation_roots']):
            raise ValueError('monitoring sample report does not match pinned source')
        checkpoint()
        return report

    def _read_sample_state(self, db, domain: Domain, checkpoint) -> dict | None:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='racing_sample_state'"
        ).fetchone()
        if exists is None:
            return None
        row = db.execute(
            'SELECT length(CAST(payload AS BLOB)) FROM racing_sample_state WHERE id=1'
        ).fetchone()
        if row is None or not 0 < row[0] <= MAX_STATE_BYTES:
            raise ValueError('missing or oversized racing sample state')
        value = _strict_json(
            db.execute('SELECT payload FROM racing_sample_state WHERE id=1').fetchone()[0]
        )
        _hashed(value, SAMPLE_SCHEMA)
        expected = {
            'schema_version', 'config', 'generation', 'last_report',
            'model_promotion_allowed', 'reevaluate_promotion_allowed', 'content_hash',
        }
        if (set(value) != expected or type(value['generation']) is not int
                or value['generation'] < 0
                or value['model_promotion_allowed'] is not False
                or value['reevaluate_promotion_allowed'] is not False):
            raise ValueError('invalid racing sample cursor authority')
        config = value['config']
        if (not isinstance(config, dict)
                or set(config) != {'domain', 'evidence_root', 'relocation_roots'}
                or config['domain'] != domain.value
                or config['evidence_root'] != str(_safe(Path(config['evidence_root'])))
                or not isinstance(config['relocation_roots'], list)
                or config['relocation_roots'] != [
                    str(_safe(Path(item))) for item in config['relocation_roots']
                ]):
            raise ValueError('invalid racing sample cursor source config')
        if value['generation'] == 0:
            if value['last_report'] is not None:
                raise ValueError('initial racing sample cursor has a watermark')
        else:
            if value['last_report'] is None:
                raise ValueError('advanced racing sample cursor lost its watermark')
            report = self._sample_report(
                value['last_report'], domain, config, checkpoint,
            )
            if 'sample_count' in value['last_report']:
                # Normalize the old single-scope reference in memory. It is
                # written back only if the new review and the joint transaction
                # succeed, so a failed migration leaves durable state untouched.
                from .research_monitoring_samples import monitoring_report_reference
                value = {
                    **value,
                    'last_report': monitoring_report_reference(
                        Path(value['last_report']['path']), report,
                    ),
                }
        return value

    def _storage_report(self, reference: dict, domain: Domain, config: dict,
                        checkpoint) -> dict:
        expected_fields = {
            'path', 'content_hash', 'observed_at', 'storage_health',
        }
        if not isinstance(reference, dict) or set(reference) != expected_fields:
            raise ValueError('invalid storage evidence report reference')
        path = _safe(Path(reference['path']))
        phase_root = _safe(self.runtime.warm_root / 'research-phases' / domain.value)
        if (not path.is_file() or path.is_symlink()
                or not path.is_relative_to(phase_root)
                or path.stat().st_size > 32768
                or not path.parent.parent.name.startswith(
                    'research-storage-evidence-'
                )):
            raise ValueError('storage evidence report is outside owned phase root')
        from .research_storage_evidence import (
            storage_report_reference,
            verify_research_storage_evidence,
        )
        report = _strict_json(path.read_text())
        verify_research_storage_evidence(
            report,
            repo_root=Path(config['repo_root']),
            state_root=Path(config['storage_state_root']),
            domain=domain, as_of=reference['observed_at'],
            reverify_source=False,
        )
        if reference != storage_report_reference(path, report):
            raise ValueError('storage evidence report does not match watermark')
        checkpoint()
        return report

    def _read_storage_state(self, db, domain: Domain, checkpoint) -> dict | None:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='storage_evidence_state'"
        ).fetchone()
        if exists is None:
            return None
        row = db.execute(
            'SELECT length(CAST(payload AS BLOB)) '
            'FROM storage_evidence_state WHERE id=1'
        ).fetchone()
        if row is None or not 0 < row[0] <= MAX_STATE_BYTES:
            raise ValueError('missing or oversized storage evidence state')
        value = _strict_json(
            db.execute(
                'SELECT payload FROM storage_evidence_state WHERE id=1'
            ).fetchone()[0]
        )
        _hashed(value, STORAGE_SCHEMA)
        expected = {
            'schema_version', 'config', 'generation', 'last_report',
            'model_promotion_allowed', 'process_liveness_verified',
            'live_drift_verified', 'content_hash',
        }
        if (set(value) != expected or type(value['generation']) is not int
                or value['generation'] < 0
                or any(value[key] is not False for key in (
                    'model_promotion_allowed', 'process_liveness_verified',
                    'live_drift_verified',
                ))):
            raise ValueError('invalid storage evidence cursor authority')
        config = value['config']
        if (not isinstance(config, dict)
                or set(config) != {
                    'domain', 'repo_root', 'storage_state_root',
                }
                or config['domain'] != domain.value
                or config['repo_root'] != str(_safe(Path(config['repo_root'])))
                or config['storage_state_root']
                != str(_safe(Path(config['storage_state_root'])))):
            raise ValueError('invalid storage evidence cursor source config')
        if value['generation'] == 0:
            if value['last_report'] is not None:
                raise ValueError('initial storage evidence cursor has a watermark')
        else:
            if value['last_report'] is None:
                raise ValueError('advanced storage evidence cursor lost its watermark')
            self._storage_report(value['last_report'], domain, config, checkpoint)
        return value

    def _liveness_report(self, reference: dict, domain: Domain, config: dict,
                         checkpoint) -> dict:
        expected_fields = {
            'path', 'content_hash', 'observed_at',
            'queue_index_hash', 'all_claimed_processes_verified', 'counts',
        }
        if not isinstance(reference, dict) or set(reference) != expected_fields:
            raise ValueError('invalid liveness evidence report reference')
        path = _safe(Path(reference['path']))
        phase_root = _safe(self.runtime.warm_root / 'research-phases' / domain.value)
        if (not path.is_file() or path.is_symlink()
                or not path.is_relative_to(phase_root)
                or path.stat().st_size > 1048576
                or not path.parent.parent.name.startswith(
                    'research-liveness-evidence-'
                )):
            raise ValueError('liveness evidence report is outside owned phase root')
        from .research_liveness import (
            liveness_report_reference,
            verify_research_liveness_evidence,
        )
        report = _strict_json(path.read_text())
        verify_research_liveness_evidence(
            report,
            registry_root=self.registry.root,
            queue_root=Path(config['queue_root']),
            lease_root=Path(config['lease_root']),
            domain=domain, as_of=reference['observed_at'],
            reverify_source=False,
        )
        if reference != liveness_report_reference(path, report):
            raise ValueError('liveness evidence report does not match watermark')
        checkpoint()
        return report

    def _read_liveness_state(self, db, domain: Domain, checkpoint) -> dict | None:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='liveness_evidence_state'"
        ).fetchone()
        if exists is None:
            return None
        row = db.execute(
            'SELECT length(CAST(payload AS BLOB)) '
            'FROM liveness_evidence_state WHERE id=1'
        ).fetchone()
        if row is None or not 0 < row[0] <= MAX_STATE_BYTES:
            raise ValueError('missing or oversized liveness evidence state')
        value = _strict_json(
            db.execute(
                'SELECT payload FROM liveness_evidence_state WHERE id=1'
            ).fetchone()[0]
        )
        _hashed(value, LIVENESS_SCHEMA)
        expected = {
            'schema_version', 'config', 'generation', 'last_report',
            'model_promotion_allowed', 'queue_mutation_allowed', 'content_hash',
        }
        if (set(value) != expected or type(value['generation']) is not int
                or value['generation'] < 0
                or value['model_promotion_allowed'] is not False
                or value['queue_mutation_allowed'] is not False):
            raise ValueError('invalid liveness evidence cursor authority')
        config = value['config']
        if (not isinstance(config, dict)
                or set(config) != {'domain', 'queue_root', 'lease_root'}
                or config['domain'] != domain.value
                or config['queue_root'] != str(_safe(Path(config['queue_root'])))
                or config['lease_root'] != str(_safe(Path(config['lease_root'])))):
            raise ValueError('invalid liveness evidence cursor source config')
        if value['generation'] == 0:
            if value['last_report'] is not None:
                raise ValueError('initial liveness evidence cursor has a watermark')
        else:
            if value['last_report'] is None:
                raise ValueError('advanced liveness evidence cursor lost its watermark')
            self._liveness_report(value['last_report'], domain, config, checkpoint)
        return value

    def _proof(self, reference: dict, domain: Domain, checkpoint) -> dict:
        if set(reference) != {'attempt_path', 'request_hash', 'content_hash'}:
            raise ValueError('invalid review proof reference')
        attempt = _safe(reference['attempt_path'])
        parent = _safe(self.runtime.warm_root / 'research-phases' / domain.value)
        if attempt.parent != parent or not attempt.name.startswith('review-'):
            raise ValueError('review proof is outside owned phase root')
        reader = _Reader(checkpoint, max_record_bytes=MAX_STATE_BYTES, max_total_bytes=3 * MAX_STATE_BYTES)
        request, _ = reader.read(attempt / 'request.json')
        completed, _ = reader.read(attempt / 'completed.json')
        path = attempt / 'work/review-summary.json'
        summary, _ = reader.read(path)
        if (request['action'] != 'review' or request['registry'] != str(self.registry.root)
                or request['warm_root'] != str(self.runtime.warm_root) or request['state_root'] != str(self.runtime.state_root)
                or request['payload']['domain'] != domain.value or _hash(request) != reference['request_hash']
                or summary['content_hash'] != reference['content_hash']):
            raise ValueError('review proof scope mismatch')
        verify_review_summary(request=request, runtime=self.runtime, report_path=path, receipt=completed)
        reader.recheck()
        checkpoint()
        return summary

    def _read_state(self, db, domain, ruler_digest, ruler_released_at, queue_root, checkpoint, production_evidence_root=None):
        row = db.execute('SELECT length(CAST(payload AS BLOB)) FROM cursor_state WHERE id=1').fetchone()
        if row is None or not 0 < row[0] <= MAX_STATE_BYTES:
            raise ValueError('missing or oversized cursor state')
        value = _strict_json(db.execute('SELECT payload FROM cursor_state WHERE id=1').fetchone()[0])
        _hashed(value, SCHEMA)
        if (set(value) != {'schema_version', 'config', 'generation', 'window_start', 'last_as_of', 'last_review',
                          'model_promotion_allowed', 'telegram_delivery_confirmed', 'content_hash'}
                or type(value['generation']) is not int or value['generation'] < 0
                or value['model_promotion_allowed'] is not False or value['telegram_delivery_confirmed'] is not False):
            raise ValueError('invalid cursor schema or authority')
        config = self._config(domain, value['config']['initial_window_start'], ruler_digest, ruler_released_at, queue_root, production_evidence_root)
        if value['config'] != config:
            raise ValueError('cursor configuration changed; independent review required')
        if value['generation'] == 0:
            if value['last_review'] is not None or value['window_start'] != config['initial_window_start'] or value['last_as_of'] != value['window_start']:
                raise ValueError('invalid initial cursor')
        else:
            summary = self._proof(value['last_review'], domain, checkpoint)
            if (value['window_start'] != summary['next_window_start'] or value['last_as_of'] != summary['as_of']
                    or summary['ruler_digest'] != ruler_digest or summary['ruler_released_at'] != config['ruler_released_at']
                    or _at(summary['window_start']) < _at(config['initial_window_start'])):
                raise ValueError('cursor does not match verified review progress')
            if summary.get('production_incidents', {}).get('root') != config.get('production_evidence_root'):
                raise ValueError('review proof does not cover pinned production source')
        return value

    def run(self, *, domain: Domain, now: datetime, ruler_digest: str, ruler_released_at: datetime,
            estimated_bytes: int, timeout_seconds: float, queue_root: Path | None = None,
            report_paths: dict | None = None, max_reviews: int = 50,
            production_evidence_root: Path | None = None) -> CursorReviewResult:
        """Run one bounded review pass, committing progress only after verification.

        Failures before commit leave the prior cursor intact. After a lost commit
        acknowledgement, reopen the store: recovery may reveal old or fully new
        state. ``advanced`` confirms an observed window advance, not its absence
        after an uncertain failure. Replay rechecks receipts, never scoring/bets.
        """
        if type(estimated_bytes) is not int or estimated_bytes <= 0 or type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError('positive capacity and finite timeout required')
        deadline = time.monotonic() + timeout_seconds
        def checkpoint():
            if time.monotonic() >= deadline:
                raise ResourceInterrupted('phase_timeout')
            reason = _resource_status(self.runtime, self.registry, estimated_bytes)
            if reason:
                raise ResourceInterrupted(reason)
        path = None
        review = None
        try:
            reason = _resource_status(self.runtime, self.registry, estimated_bytes)
            if reason:
                return CursorReviewResult(ResearchDisposition.DEFERRED, reason)
            path = self._path(domain)
            with closing(sqlite3.connect(f'file:{quote(str(path))}?mode=rw', uri=True, timeout=0, isolation_level=None)) as db:
                db.execute('PRAGMA synchronous=FULL')
                # One metadata-only transaction owns this domain across the
                # supervised pass. A second caller immediately defers, not waits.
                db.execute('BEGIN IMMEDIATE')
                saved = self._read_state(db, domain, ruler_digest, ruler_released_at, queue_root, checkpoint, production_evidence_root)
                sample_saved = self._read_sample_state(db, domain, checkpoint)
                storage_saved = self._read_storage_state(db, domain, checkpoint)
                liveness_saved = self._read_liveness_state(db, domain, checkpoint)
                if _at(now) < _at(saved['last_as_of']):
                    raise ValueError('review clock moved backwards')
                checkpoint()
                sample_result = None
                sample_config = sample_saved['config'] if sample_saved is not None else None
                if sample_config is not None:
                    from .research_supervision import (
                        NbaMonitoringSampleInspectionRunner,
                        RacingMonitoringSampleInspectionRunner,
                        TennisMonitoringSampleInspectionRunner,
                    )
                    common = {
                        'evidence_root': Path(sample_config['evidence_root']),
                        'as_of': _at(now),
                        'relocation_roots': tuple(
                            Path(item) for item in sample_config['relocation_roots']
                        ),
                        'estimated_bytes': estimated_bytes,
                        'timeout_seconds': deadline-time.monotonic(),
                    }
                    if domain in {Domain.AU, Domain.HKJC}:
                        sample_result = RacingMonitoringSampleInspectionRunner(
                            self.runtime, self.registry
                        ).run(domain=domain, **common)
                    elif domain is Domain.NBA:
                        sample_result = NbaMonitoringSampleInspectionRunner(
                            self.runtime, self.registry
                        ).run(**common)
                    else:
                        sample_result = TennisMonitoringSampleInspectionRunner(
                            self.runtime, self.registry
                        ).run(**common)
                    if sample_result.disposition is not ResearchDisposition.SUCCEEDED:
                        return CursorReviewResult(
                            sample_result.disposition, sample_result.status, path,
                            saved['generation'],
                        )
                    if sample_result.report_path is None:
                        raise ValueError('successful sample phase omitted its report')
                    checkpoint()
                storage_result = None
                storage_config = (
                    storage_saved['config'] if storage_saved is not None else None
                )
                if storage_config is not None:
                    from .research_supervision import (
                        ResearchStorageEvidenceInspectionRunner,
                    )
                    storage_result = ResearchStorageEvidenceInspectionRunner(
                        self.runtime, self.registry
                    ).run(
                        domain=domain,
                        repo_root=Path(storage_config['repo_root']),
                        storage_state_root=Path(
                            storage_config['storage_state_root']
                        ),
                        as_of=_at(now), estimated_bytes=estimated_bytes,
                        timeout_seconds=deadline-time.monotonic(),
                    )
                    if storage_result.disposition is not ResearchDisposition.SUCCEEDED:
                        return CursorReviewResult(
                            storage_result.disposition, storage_result.status, path,
                            saved['generation'],
                        )
                    if storage_result.report_path is None:
                        raise ValueError('successful storage phase omitted its report')
                    checkpoint()
                liveness_result = None
                liveness_config = (
                    liveness_saved['config'] if liveness_saved is not None else None
                )
                if liveness_config is not None:
                    from .research_supervision import ResearchLivenessInspectionRunner
                    if liveness_config['queue_root'] != str(_safe(queue_root)):
                        raise ValueError('liveness cursor queue differs from review queue')
                    liveness_result = ResearchLivenessInspectionRunner(
                        self.runtime, self.registry
                    ).run(
                        domain=domain,
                        queue_root=Path(liveness_config['queue_root']),
                        lease_root=Path(liveness_config['lease_root']),
                        as_of=_at(now), estimated_bytes=estimated_bytes,
                        timeout_seconds=deadline-time.monotonic(),
                    )
                    if liveness_result.disposition is not ResearchDisposition.SUCCEEDED:
                        return CursorReviewResult(
                            liveness_result.disposition, liveness_result.status, path,
                            saved['generation'],
                        )
                    if liveness_result.report_path is None:
                        raise ValueError('successful liveness phase omitted its report')
                    checkpoint()
                review = ResearchReviewRunner(self.runtime, self.registry).run(
                    domain=domain, window_start=_at(saved['window_start']), now=_at(now), ruler_digest=ruler_digest,
                    ruler_released_at=_at(ruler_released_at), estimated_bytes=estimated_bytes,
                    timeout_seconds=deadline-time.monotonic(), queue_root=queue_root, report_paths=report_paths, max_reviews=max_reviews,
                    production_evidence_root=production_evidence_root,
                    racing_sample_report=(
                        sample_result.report_path if sample_result is not None else None
                    ),
                    previous_racing_sample_report=(
                        Path(sample_saved['last_report']['path'])
                        if sample_saved is not None
                        and sample_saved['last_report'] is not None else None
                    ),
                    racing_sample_evidence_root=(
                        Path(sample_config['evidence_root'])
                        if sample_config is not None else None
                    ),
                    racing_sample_relocation_roots=(
                        tuple(Path(item) for item in sample_config['relocation_roots'])
                        if sample_config is not None else ()
                    ),
                    storage_report=(
                        storage_result.report_path
                        if storage_result is not None else None
                    ),
                    storage_repo_root=(
                        Path(storage_config['repo_root'])
                        if storage_config is not None else None
                    ),
                    storage_state_root=(
                        Path(storage_config['storage_state_root'])
                        if storage_config is not None else None
                    ),
                    liveness_report=(
                        liveness_result.report_path
                        if liveness_result is not None else None
                    ),
                    liveness_lease_root=(
                        Path(liveness_config['lease_root'])
                        if liveness_config is not None else None
                    ))
                if review.disposition is not ResearchDisposition.SUCCEEDED:
                    return CursorReviewResult(review.disposition, review.status, path, saved['generation'], review=review)
                request, _ = _Reader(checkpoint, max_record_bytes=MAX_STATE_BYTES).read(review.attempt_path / 'request.json')
                reference = {'attempt_path': str(review.attempt_path), 'request_hash': _hash(request), 'content_hash': review.content_hash}
                summary = self._proof(reference, domain, checkpoint)
                if summary['window_start'] != saved['window_start'] or summary['as_of'] != _at(now).isoformat():
                    raise ValueError('review does not continue current cursor')
                sample_updated = None
                if sample_saved is not None:
                    if (summary.get('racing_sample_current', {}).get('path')
                            != str(sample_result.report_path)
                            or summary.get('racing_sample_previous')
                            != sample_saved['last_report']):
                        raise ValueError('review does not continue racing sample cursor')
                    # A bounded pass may leave the threshold-triggered request
                    # unprocessed. Keep the old watermark in that case so replay
                    # cannot silently lose the pending sample-growth review.
                    if summary['remaining_requests'] == 0:
                        sample_updated = _seal({
                            **sample_saved,
                            'generation': sample_saved['generation'] + 1,
                            'last_report': summary['racing_sample_current'],
                        })
                storage_updated = None
                if storage_saved is not None:
                    if (summary.get('storage_evidence', {}).get('path')
                            != str(storage_result.report_path)):
                        raise ValueError('review does not continue storage evidence cursor')
                    storage_updated = _seal({
                        **storage_saved,
                        'generation': storage_saved['generation'] + 1,
                        'last_report': summary['storage_evidence'],
                    })
                liveness_updated = None
                if liveness_saved is not None:
                    if (summary.get('process_liveness', {}).get('path')
                            != str(liveness_result.report_path)):
                        raise ValueError('review does not continue liveness evidence cursor')
                    liveness_updated = _seal({
                        **liveness_saved,
                        'generation': liveness_saved['generation'] + 1,
                        'last_report': summary['process_liveness'],
                    })
                if _at(summary['as_of']) >= _at(summary['ruler_released_at']) + timedelta(days=90):
                    # Source incidents have their own worker-persisted latch.
                    # Persist before cursor progress; lost COMMIT acknowledgement
                    # must not discard a freeze already observed by this review.
                    from .research_guard import _ruler_freeze
                    _ruler_freeze(path, saved['config'], persist=True)
                # Persist the WARM proof directory entries before HOT progress.
                if sample_result is not None:
                    _fsync_directory(sample_result.report_path.parent)
                    _fsync_directory(sample_result.attempt_path)
                if storage_result is not None:
                    _fsync_directory(storage_result.report_path.parent)
                    _fsync_directory(storage_result.attempt_path)
                if liveness_result is not None:
                    _fsync_directory(liveness_result.report_path.parent)
                    _fsync_directory(liveness_result.attempt_path)
                _fsync_directory(review.report_path.parent)
                _fsync_directory(review.attempt_path)
                checkpoint()
                self._path(domain)
                updated = _seal({**saved, 'generation': saved['generation']+1, 'window_start': summary['next_window_start'],
                                 'last_as_of': summary['as_of'], 'last_review': reference})
                db.execute('UPDATE cursor_state SET payload=? WHERE id=1', (_encoded(updated).decode(),))
                if sample_updated is not None:
                    db.execute(
                        'UPDATE racing_sample_state SET payload=? WHERE id=1',
                        (_encoded(sample_updated).decode(),),
                    )
                if storage_updated is not None:
                    db.execute(
                        'UPDATE storage_evidence_state SET payload=? WHERE id=1',
                        (_encoded(storage_updated).decode(),),
                    )
                if liveness_updated is not None:
                    db.execute(
                        'UPDATE liveness_evidence_state SET payload=? WHERE id=1',
                        (_encoded(liveness_updated).decode(),),
                    )
                checkpoint()
                db.execute('COMMIT')
                return CursorReviewResult(review.disposition, review.status, path, updated['generation'],
                                          updated['window_start'] != saved['window_start'], review)
        except ResourceInterrupted as exc:
            disposition = ResearchDisposition.TIMED_OUT if str(exc) == 'phase_timeout' else ResearchDisposition.PREEMPTED
            return CursorReviewResult(disposition, str(exc), path, review=review)
        except sqlite3.OperationalError as exc:
            if 'locked' in str(exc) or 'busy' in str(exc):
                return CursorReviewResult(ResearchDisposition.DEFERRED, 'review_cursor_busy', path)
            return CursorReviewResult(ResearchDisposition.BLOCKED, 'review_cursor_store_unavailable', path, review=review)
        except (OSError, ValueError, KeyError, TypeError, ResearchIndexError, EvaluationError, sqlite3.DatabaseError):
            return CursorReviewResult(ResearchDisposition.BLOCKED, 'review_cursor_verification_failed', path, review=review)
