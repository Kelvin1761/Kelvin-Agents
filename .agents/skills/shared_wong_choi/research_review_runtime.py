"""Supervised, record-only review passes; no scheduler/model/delivery authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .contracts import Domain
from .research_index import (
    _at, _encoded, _hash, _hashed, _safe, _Reader,
    _clock_payload, _clock_options, build_research_index,
    completed_review_request_ids, record_review,
    ResearchIndexError,
)
from .research_review_clock import plan_reviews, ReviewEvent
from .research_runner import ResearchDisposition
from .research_evaluation import _strict_json, _write_report, EvaluationError


SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v1"
INCIDENT_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v2"
SAMPLE_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v3"
INCIDENT_SAMPLE_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v4"
STORAGE_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v5"
INCIDENT_STORAGE_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v6"
SAMPLE_STORAGE_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v7"
INCIDENT_SAMPLE_STORAGE_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v8"
LIVENESS_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v9"
INCIDENT_LIVENESS_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v10"
SAMPLE_LIVENESS_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v11"
INCIDENT_SAMPLE_LIVENESS_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v12"
STORAGE_LIVENESS_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v13"
INCIDENT_STORAGE_LIVENESS_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v14"
SAMPLE_STORAGE_LIVENESS_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v15"
INCIDENT_SAMPLE_STORAGE_LIVENESS_SUMMARY_SCHEMA = "wong-choi-supervised-review-summary/v16"


def _summary_schema(*, incident: bool, sample: bool, storage: bool = False,
                    liveness: bool = False, production_day: bool = False,
                    drift: bool = False) -> str:
    version = 1 + sum((
        int(incident), 2 * int(sample), 4 * int(storage),
        8 * int(liveness), 16 * int(production_day), 32 * int(drift),
    ))
    return f"wong-choi-supervised-review-summary/v{version}"


@dataclass(frozen=True)
class ResearchReviewResult:
    disposition: ResearchDisposition
    status: str
    attempt_path: Path | None = None
    report_path: Path | None = None
    content_hash: str | None = None


class ResearchReviewRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain: Domain, window_start, now, ruler_digest, ruler_released_at,
            estimated_bytes, timeout_seconds, queue_root=None, report_paths=None, max_reviews=50,
            production_evidence_root: Path | None = None,
            racing_sample_report: Path | None = None,
            previous_racing_sample_report: Path | None = None,
            racing_sample_evidence_root: Path | None = None,
            racing_sample_relocation_roots: tuple[Path, ...] = (),
            storage_report: Path | None = None,
            storage_repo_root: Path | None = None,
            storage_state_root: Path | None = None,
            liveness_report: Path | None = None,
            liveness_lease_root: Path | None = None,
            production_day_report: Path | None = None,
            production_day_run_root: Path | None = None,
            production_day_attestation_path: Path | None = None,
            production_day: date | None = None,
            drift_report: Path | None = None,
            drift_evidence_root: Path | None = None,
            drift_baseline_as_of=None,
            drift_relocation_roots: tuple[Path, ...] = ()):
        from .research_supervision import _phase
        clock = dict(domain=domain, window_start=window_start, now=now, ruler_digest=ruler_digest,
                     ruler_released_at=ruler_released_at)
        plan_reviews(**clock)  # Validate bounded clocks before allocating a worker.
        if type(max_reviews) is not int or not 1 <= max_reviews <= 50:
            raise ValueError("review batch must contain 1 to 50 requests")
        payload = {"domain": domain.value, "clock_inputs": _clock_payload(clock),
                   "queue_root": str(_safe(queue_root)) if queue_root is not None else None,
                   "report_paths": {key: str(_safe(path)) for key, path in (report_paths or {}).items()},
                   "max_reviews": max_reviews}
        if production_evidence_root is not None:
            payload['production_evidence_root'] = str(_safe(production_evidence_root))
        sample_requested = any(item is not None for item in (
            racing_sample_report, previous_racing_sample_report,
            racing_sample_evidence_root,
        )) or bool(racing_sample_relocation_roots)
        if sample_requested:
            if (not isinstance(domain, Domain) or racing_sample_report is None
                    or racing_sample_evidence_root is None
                    or not isinstance(racing_sample_relocation_roots, tuple)):
                raise ValueError("complete domain monitoring sample evidence required")
            payload['racing_sample_report'] = str(_safe(racing_sample_report))
            payload['previous_racing_sample_report'] = (
                str(_safe(previous_racing_sample_report))
                if previous_racing_sample_report is not None else None
            )
            payload['racing_sample_evidence_root'] = str(
                _safe(racing_sample_evidence_root)
            )
            payload['racing_sample_relocation_roots'] = [
                str(_safe(path)) for path in racing_sample_relocation_roots
            ]
        storage_requested = any(item is not None for item in (
            storage_report, storage_repo_root, storage_state_root,
        ))
        if storage_requested:
            if (storage_report is None or storage_repo_root is None
                    or storage_state_root is None):
                raise ValueError("complete storage evidence required")
            payload['storage_report'] = str(_safe(storage_report))
            payload['storage_repo_root'] = str(_safe(storage_repo_root))
            payload['storage_state_root'] = str(_safe(storage_state_root))
        liveness_requested = any(item is not None for item in (
            liveness_report, liveness_lease_root,
        ))
        if liveness_requested:
            if (liveness_report is None or liveness_lease_root is None
                    or queue_root is None):
                raise ValueError("complete queue liveness evidence required")
            payload['liveness_report'] = str(_safe(liveness_report))
            payload['liveness_lease_root'] = str(_safe(liveness_lease_root))
        production_day_requested = any(item is not None for item in (
            production_day_report, production_day_run_root,
            production_day_attestation_path, production_day,
        ))
        if production_day_requested:
            if (production_day_report is None or production_day_run_root is None
                    or type(production_day) is not date):
                raise ValueError("complete production-day evidence required")
            payload['production_day_report'] = str(_safe(production_day_report))
            payload['production_day_run_root'] = str(_safe(production_day_run_root))
            payload['production_day_attestation_path'] = (
                str(_safe(production_day_attestation_path))
                if production_day_attestation_path is not None else None
            )
            payload['production_day'] = production_day.isoformat()
        drift_requested = any(item is not None for item in (
            drift_report, drift_evidence_root, drift_baseline_as_of,
        )) or bool(drift_relocation_roots)
        if drift_requested:
            if (drift_report is None or drift_evidence_root is None
                    or drift_baseline_as_of is None
                    or not isinstance(drift_relocation_roots, tuple)):
                raise ValueError("complete live drift evidence required")
            payload['drift_report'] = str(_safe(drift_report))
            payload['drift_evidence_root'] = str(_safe(drift_evidence_root))
            payload['drift_baseline_as_of'] = _at(drift_baseline_as_of).isoformat()
            payload['drift_relocation_roots'] = [
                str(_safe(path)) for path in drift_relocation_roots
            ]
        if len(_encoded(payload)) > 32768:
            raise ValueError("review request metadata exceeds bounded size")
        disposition, status, attempt, completed = _phase(
            self.runtime, self.registry, None, action="review", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = completed if disposition is ResearchDisposition.SUCCEEDED else {}
        return ResearchReviewResult(disposition, status, attempt,
                                    Path(valid["report_path"]) if valid.get("report_path") else None,
                                    valid.get("content_hash"))


def run_review_request(request, *, registry, runtime, workspace, checkpoint):
    payload = request["payload"]
    source_root = payload.get('production_evidence_root')
    sample_path = payload.get('racing_sample_report')
    storage_path = payload.get('storage_report')
    liveness_path = payload.get('liveness_report')
    production_day_path = payload.get('production_day_report')
    drift_path = payload.get('drift_report')
    expected_payload = {"domain", "clock_inputs", "queue_root", "report_paths", "max_reviews"}
    if source_root is not None:
        expected_payload.add('production_evidence_root')
    if sample_path is not None:
        expected_payload.update({
            'racing_sample_report', 'previous_racing_sample_report',
            'racing_sample_evidence_root', 'racing_sample_relocation_roots',
        })
    if storage_path is not None:
        expected_payload.update({
            'storage_report', 'storage_repo_root', 'storage_state_root',
        })
    if liveness_path is not None:
        expected_payload.update({'liveness_report', 'liveness_lease_root'})
    if production_day_path is not None:
        expected_payload.update({
            'production_day_report', 'production_day_run_root',
            'production_day_attestation_path', 'production_day',
        })
    if drift_path is not None:
        expected_payload.update({
            'drift_report', 'drift_evidence_root', 'drift_baseline_as_of',
            'drift_relocation_roots',
        })
    if set(payload) != expected_payload:
        raise ValueError("unsupported review request fields")
    clock = _clock_options(payload["clock_inputs"])
    if (clock["domain"].value != payload["domain"] or clock["samples"] or clock["previous_samples"]
            or clock["events"] or clock["completed_request_ids"]):
        raise ValueError("external sample/event/completion claims are not accepted")
    if type(payload["max_reviews"]) is not int or not 1 <= payload["max_reviews"] <= 50:
        raise ValueError("invalid review batch bound")
    root = _safe(runtime.warm_root / "research-reviews")
    checkpoint()
    acknowledged = completed_review_request_ids(root, clock["domain"], checkpoint=checkpoint, registry_root=registry.root)
    index_args = {"registry_root": registry.root, "queue_root": Path(payload["queue_root"]) if payload["queue_root"] else None,
                  "report_paths": {key: Path(path) for key, path in payload["report_paths"].items()}, "checkpoint": checkpoint}
    index = build_research_index(as_of=clock["now"], **index_args)
    # Only registered terminal run records become completion events. No guessed
    # process liveness, raw dataset counts, or production-day closure is inferred.
    events = tuple(ReviewEvent("run_postflight", item["record_id"], _at(item["created_at"]), item["content_hash"])
                   for item in index["records"] if item["kind"] == "experiment_run" and item["domain"] == payload["domain"])
    run_completion_count = len(events)
    source_report = None
    source_freeze = None
    if source_root is not None:
        from .research_production_incidents import collect_production_incidents
        from .research_guard import persist_production_incident, production_incident_projection
        try:
            source_report = collect_production_incidents(root=Path(source_root), domain=clock['domain'],
                                                         as_of=clock['now'], checkpoint=checkpoint)
        except (OSError, ValueError, KeyError, TypeError, ResearchIndexError, EvaluationError):
            # A failed source scan cannot become a clean review. Resource
            # preemption/timeouts are deliberately NOT reclassified as incidents.
            persist_production_incident(runtime, registry, clock['domain'], source_root=Path(source_root),
                                        observed_at=clock['now'], report=None)
            raise
        if source_report['events']:
            persist_production_incident(runtime, registry, clock['domain'], source_root=Path(source_root),
                                        observed_at=clock['now'], report=source_report)
        source_freeze = production_incident_projection(runtime, registry, clock['domain'])
        if source_freeze is not None and source_freeze['source_root'] != source_root:
            raise ValueError('incident latch belongs to another source root')
        events += tuple(ReviewEvent(item['kind'], item['event_id'], _at(item['occurred_at']), item['evidence_digest'])
                        for item in source_report['events'] + (source_freeze['events'] if source_freeze else []))
    sample_current = ()
    sample_previous = ()
    sample_current_ref = None
    sample_previous_ref = None
    sample_status = 'not_integrated'
    if sample_path is not None:
        from .research_monitoring_samples import (
            monitoring_report_reference,
            monitoring_sample_snapshots,
        )

        def load_sample(path_value):
            path = _safe(Path(path_value))
            phase_root = _safe(runtime.warm_root / 'research-phases' / clock['domain'].value)
            if (not path.is_file() or path.is_symlink() or not path.is_relative_to(phase_root)
                    or path.stat().st_size > 1048576):
                raise ValueError('racing sample report is outside supervised WARM evidence')
            report = _strict_json(path.read_text())
            samples = monitoring_sample_snapshots(report)
            roots = [str(_safe(Path(item))) for item in payload['racing_sample_relocation_roots']]
            if (any(sample.domain is not clock['domain'] for sample in samples)
                    or report['root'] != str(_safe(Path(payload['racing_sample_evidence_root'])))
                    or report['relocation_roots'] != roots):
                raise ValueError('monitoring sample report scope mismatch')
            return report, samples, monitoring_report_reference(path, report)

        current_report, sample_current, sample_current_ref = load_sample(sample_path)
        if _at(sample_current_ref['observed_at']) != _at(clock['now']):
            raise ValueError('current monitoring sample must match review as-of')
        previous_path = payload['previous_racing_sample_report']
        if previous_path is not None:
            _previous_report, sample_previous, sample_previous_ref = load_sample(previous_path)
            if _at(sample_previous_ref['observed_at']) > _at(sample_current_ref['observed_at']):
                raise ValueError('previous monitoring sample is newer than current sample')
        sample_status = (
            'verified_complete' if current_report['source_coverage_complete']
            else 'verified_incomplete' if current_report['candidate_settlements']
            else 'verified_empty'
        )
    storage_report = None
    storage_ref = None
    storage_status = 'not_integrated'
    if storage_path is not None:
        from .research_storage_evidence import (
            storage_report_reference,
            verify_research_storage_evidence,
        )
        path = _safe(Path(storage_path))
        phase_root = _safe(
            runtime.warm_root / 'research-phases' / clock['domain'].value
        )
        if (not path.is_file() or path.is_symlink()
                or not path.is_relative_to(phase_root)
                or path.stat().st_size > 32768
                or not path.parent.parent.name.startswith(
                    'research-storage-evidence-'
                )):
            raise ValueError('storage report is outside supervised WARM evidence')
        storage_report = _strict_json(path.read_text())
        verify_research_storage_evidence(
            storage_report,
            repo_root=Path(payload['storage_repo_root']),
            state_root=Path(payload['storage_state_root']),
            domain=clock['domain'], as_of=clock['now'],
            reverify_source=True, checkpoint=checkpoint,
        )
        storage_ref = storage_report_reference(path, storage_report)
        storage_status = 'verified_' + storage_report['storage_health']
    liveness_report = None
    liveness_ref = None
    liveness_status = 'not_integrated'
    if liveness_path is not None:
        from .research_liveness import (
            liveness_report_reference,
            verify_research_liveness_evidence,
        )
        path = _safe(Path(liveness_path))
        phase_root = _safe(
            runtime.warm_root / 'research-phases' / clock['domain'].value
        )
        if (not path.is_file() or path.is_symlink()
                or not path.is_relative_to(phase_root)
                or path.stat().st_size > 1048576
                or not path.parent.parent.name.startswith(
                    'research-liveness-evidence-'
                )):
            raise ValueError('liveness report is outside supervised WARM evidence')
        liveness_report = _strict_json(path.read_text())
        verify_research_liveness_evidence(
            liveness_report,
            registry_root=registry.root,
            queue_root=Path(payload['queue_root']),
            lease_root=Path(payload['liveness_lease_root']),
            domain=clock['domain'], as_of=clock['now'],
            reverify_source=True, checkpoint=checkpoint,
        )
        if liveness_report['queue_index_hash'] != index['content_hash']:
            raise ValueError('liveness evidence belongs to another queue index')
        liveness_ref = liveness_report_reference(path, liveness_report)
        liveness_status = (
            'verified_complete'
            if liveness_report['all_claimed_processes_verified']
            else 'verified_incomplete'
        )
    drift_report = None
    drift_ref = None
    drift_status = 'not_integrated'
    if drift_path is not None:
        from .research_live_drift import (
            live_drift_report_reference,
            verify_live_feature_drift_report,
        )
        path = _safe(Path(drift_path))
        phase_root = _safe(
            runtime.warm_root / 'research-phases' / clock['domain'].value
        )
        if (not path.is_file() or path.is_symlink()
                or not path.is_relative_to(phase_root)
                or path.stat().st_size > 32768
                or not path.parent.parent.name.startswith(
                    'research-live-drift-'
                )):
            raise ValueError('live drift report is outside supervised WARM evidence')
        drift_report = _strict_json(path.read_text())
        verify_live_feature_drift_report(
            drift_report,
            root=Path(payload['drift_evidence_root']),
            domain=clock['domain'],
            baseline_as_of=payload['drift_baseline_as_of'],
            as_of=clock['now'],
            relocation_roots=tuple(
                Path(item) for item in payload['drift_relocation_roots']
            ),
            reverify_source=True,
            checkpoint=checkpoint,
        )
        drift_ref = live_drift_report_reference(path, drift_report)
        drift_status = (
            'verified_descriptive'
            if drift_report['status'] == 'verified_descriptive'
            else 'verified_' + drift_report['status']
        )
    production_day_report = None
    production_day_ref = None
    production_day_status = 'not_integrated'
    if production_day_path is not None:
        from .research_production_day import (
            production_day_report_reference,
            production_day_review_event,
            verify_production_day_evidence,
        )
        path = _safe(Path(production_day_path))
        phase_root = _safe(
            runtime.warm_root / 'research-phases' / clock['domain'].value
        )
        if (not path.is_file() or path.is_symlink()
                or not path.is_relative_to(phase_root)
                or path.stat().st_size > 1048576
                or not path.parent.parent.name.startswith(
                    'research-production-day-evidence-'
                )):
            raise ValueError('production-day report is outside supervised WARM evidence')
        production_day_report = _strict_json(path.read_text())
        verify_production_day_evidence(
            production_day_report,
            run_root=Path(payload['production_day_run_root']),
            attestation_path=(
                Path(payload['production_day_attestation_path'])
                if payload['production_day_attestation_path'] is not None else None
            ),
            domain=clock['domain'],
            production_day=date.fromisoformat(payload['production_day']),
            as_of=clock['now'], reverify_source=True, checkpoint=checkpoint,
        )
        production_day_ref = production_day_report_reference(
            path, production_day_report,
        )
        if production_day_report['production_day_closed']:
            events += (production_day_review_event(production_day_report),)
            production_day_status = 'verified_closed'
        else:
            production_day_status = 'verified_incomplete'
    clock.update(
        events=events,
        completed_request_ids=acknowledged,
        samples=sample_current,
        previous_samples=sample_previous,
    )
    plan = plan_reviews(**clock)
    processed = []
    for review in plan["requests"][:payload["max_reviews"]]:
        checkpoint()
        result = record_review(root=root, clock_inputs=clock, request_id=review["request_id"], **index_args)
        processed.append({"request_id": review["request_id"], "receipt_id": result["receipt_id"],
                          "status": result["status"], "path": str(result["path"])})
    checkpoint()
    remaining = len(plan["requests"]) - len(processed)
    status = "review_backlog" if remaining else ("reviewed_freeze_required" if plan["freeze_research_required"] else "reviews_recorded")
    summary = {"schema_version": _summary_schema(
                    incident=source_report is not None,
                    sample=sample_path is not None,
                    storage=storage_path is not None,
                    liveness=liveness_path is not None,
                    production_day=production_day_path is not None,
                    drift=drift_path is not None),
               "domain": payload["domain"], "request_hash": _hash(request),
               "window_start": plan["window_start"], "as_of": plan["as_of"], "ruler_digest": plan["ruler_digest"],
               "ruler_released_at": plan["ruler_released_at"], "index_hash": index["content_hash"],
               "status": status, "due_requests": len(plan["requests"]), "created_reviews": sum(item["status"] == "created" for item in processed),
               "already_recorded_reviews": len(acknowledged), "processed": processed, "remaining_requests": remaining,
               "next_window_start": plan["as_of"] if not remaining else plan["window_start"],
               "run_completion_events": run_completion_count, "freeze_research_required": plan["freeze_research_required"],
               "sample_evidence_status": sample_status,
               "production_day_evidence_status": production_day_status,
               "incident_evidence_status": "not_integrated", "telegram_delivery_confirmed": False,
               "model_promotion_allowed": False, "rerun_scoring_allowed": False, "reevaluate_promotion_allowed": False}
    if source_report is not None:
        summary['production_incidents'] = source_report
        summary['production_freeze'] = source_freeze
        summary['incident_evidence_status'] = 'metadata_issues' if source_report['events'] else 'metadata_only'
    if sample_path is not None:
        summary['racing_sample_current'] = sample_current_ref
        summary['racing_sample_previous'] = sample_previous_ref
        summary['sample_growth_observed'] = plan['sample_growth_observed']
        summary['progress_only'] = plan['progress_only']
    if storage_path is not None:
        summary['storage_evidence_status'] = storage_status
        summary['storage_evidence'] = storage_ref
        summary['process_liveness_verified'] = False
        summary['live_drift_verified'] = False
    if liveness_path is not None:
        summary['process_liveness_evidence_status'] = liveness_status
        summary['process_liveness'] = liveness_ref
        summary['process_liveness_verified'] = True
        summary['live_drift_verified'] = False
    if drift_path is not None:
        summary['live_drift_evidence_status'] = drift_status
        summary['live_drift'] = drift_ref
        summary['live_drift_verified'] = drift_report['live_drift_verified']
    if production_day_path is not None:
        summary['production_day_evidence'] = production_day_ref
    summary["content_hash"] = _hash(summary)
    if len(_encoded(summary)) > 65536:
        raise ValueError("review summary exceeds bounded metadata size")
    path = workspace / "review-summary.json"
    _write_report(path, summary, resource_checkpoint=checkpoint, create_parents=False)
    return {"disposition": "succeeded", "status": status, "report_path": str(path),
            "content_hash": summary["content_hash"], "request_hash": summary["request_hash"],
            "model_promotion_allowed": False, "telegram_delivery_confirmed": False}


def verify_review_summary(*, request, runtime, report_path, receipt,
                          require_current_freeze=False,
                          require_current_storage=False,
                          require_current_liveness=False,
                          require_current_production_day=False,
                          require_current_drift=False):
    """Bounded parent cross-check; full registry/receipt reads stay in worker."""
    payload = request["payload"]
    source_root = payload.get('production_evidence_root')
    sample_path = payload.get('racing_sample_report')
    storage_path = payload.get('storage_report')
    liveness_path = payload.get('liveness_report')
    production_day_path = payload.get('production_day_report')
    drift_path = payload.get('drift_report')
    reader = _Reader(lambda: None, max_record_bytes=65536, max_total_bytes=65536)
    summary, _ = reader.read(report_path)
    _hashed(summary, _summary_schema(
        incident=source_root is not None, sample=sample_path is not None,
        storage=storage_path is not None,
        liveness=liveness_path is not None,
        production_day=production_day_path is not None,
        drift=drift_path is not None))
    expected = {"schema_version", "domain", "request_hash", "window_start", "as_of", "ruler_digest", "ruler_released_at", "index_hash",
                "status", "due_requests", "created_reviews", "already_recorded_reviews", "processed", "remaining_requests", "next_window_start",
                "run_completion_events", "freeze_research_required", "sample_evidence_status", "production_day_evidence_status", "incident_evidence_status",
                "telegram_delivery_confirmed", "model_promotion_allowed", "rerun_scoring_allowed", "reevaluate_promotion_allowed", "content_hash"}
    if source_root is not None:
        expected.update(('production_incidents', 'production_freeze'))
    if sample_path is not None:
        expected.update((
            'racing_sample_current', 'racing_sample_previous',
            'sample_growth_observed', 'progress_only',
        ))
    if storage_path is not None:
        expected.update((
            'storage_evidence_status', 'storage_evidence',
            'process_liveness_verified', 'live_drift_verified',
        ))
    if liveness_path is not None:
        expected.update((
            'process_liveness_evidence_status', 'process_liveness',
            'process_liveness_verified', 'live_drift_verified',
        ))
    if production_day_path is not None:
        expected.add('production_day_evidence')
    if drift_path is not None:
        expected.update((
            'live_drift_evidence_status', 'live_drift',
            'live_drift_verified',
        ))
    if set(summary) != expected or summary["content_hash"] != receipt.get("content_hash") or summary["request_hash"] != _hash(request):
        raise ValueError("review summary identity mismatch")
    clock = payload["clock_inputs"]
    if (summary["domain"] != payload["domain"] or summary["as_of"] != clock["now"]
            or summary["window_start"] != clock["window_start"] or summary["ruler_digest"] != clock["ruler_digest"]
            or summary["ruler_released_at"] != clock["ruler_released_at"]):
        raise ValueError("review summary clock mismatch")
    for key in ("model_promotion_allowed", "telegram_delivery_confirmed", "rerun_scoring_allowed", "reevaluate_promotion_allowed"):
        if summary[key] is not False:
            raise ValueError("review summary cannot grant authority")
    if (production_day_path is None
            and summary["production_day_evidence_status"] != "not_integrated"):
        raise ValueError("review summary cannot invent source evidence")
    if sample_path is None and summary['sample_evidence_status'] != 'not_integrated':
        raise ValueError('review summary cannot invent sample evidence')
    if storage_path is not None:
        from .research_storage_evidence import (
            storage_report_reference,
            verify_research_storage_evidence,
        )
        path = _safe(Path(storage_path))
        phase_root = _safe(runtime.warm_root / 'research-phases' / payload['domain'])
        if (not path.is_file() or path.is_symlink()
                or not path.is_relative_to(phase_root)
                or path.stat().st_size > 32768
                or not path.parent.parent.name.startswith(
                    'research-storage-evidence-'
                )):
            raise ValueError('invalid supervised storage evidence path')
        storage_report = _strict_json(path.read_text())
        verify_research_storage_evidence(
            storage_report,
            repo_root=Path(payload['storage_repo_root']),
            state_root=Path(payload['storage_state_root']),
            domain=Domain(payload['domain']), as_of=_at(clock['now']),
            reverify_source=require_current_storage,
        )
        if (summary['storage_evidence']
                != storage_report_reference(path, storage_report)
                or summary['storage_evidence_status']
                != 'verified_' + storage_report['storage_health']
                or summary['process_liveness_verified']
                is not (liveness_path is not None)):
            raise ValueError('storage review evidence mismatch')
    if liveness_path is not None:
        from .research_liveness import (
            liveness_report_reference,
            verify_research_liveness_evidence,
        )
        path = _safe(Path(liveness_path))
        phase_root = _safe(runtime.warm_root / 'research-phases' / payload['domain'])
        if (not path.is_file() or path.is_symlink()
                or not path.is_relative_to(phase_root)
                or path.stat().st_size > 1048576
                or not path.parent.parent.name.startswith(
                    'research-liveness-evidence-'
                )):
            raise ValueError('invalid supervised liveness evidence path')
        report = _strict_json(path.read_text())
        verify_research_liveness_evidence(
            report,
            registry_root=Path(request['registry']),
            queue_root=Path(payload['queue_root']),
            lease_root=Path(payload['liveness_lease_root']),
            domain=Domain(payload['domain']), as_of=_at(clock['now']),
            reverify_source=require_current_liveness,
        )
        expected_status = (
            'verified_complete' if report['all_claimed_processes_verified']
            else 'verified_incomplete'
        )
        if (summary['process_liveness']
                != liveness_report_reference(path, report)
                or report['queue_index_hash'] != summary['index_hash']
                or summary['process_liveness_evidence_status'] != expected_status
                or summary['process_liveness_verified'] is not True):
            raise ValueError('liveness review evidence mismatch')
    if drift_path is not None:
        from .research_live_drift import (
            live_drift_report_reference,
            verify_live_feature_drift_report,
        )
        path = _safe(Path(drift_path))
        phase_root = _safe(runtime.warm_root / 'research-phases' / payload['domain'])
        if (not path.is_file() or path.is_symlink()
                or not path.is_relative_to(phase_root)
                or path.stat().st_size > 32768
                or not path.parent.parent.name.startswith('research-live-drift-')):
            raise ValueError('invalid supervised live drift evidence path')
        report = _strict_json(path.read_text())
        verify_live_feature_drift_report(
            report,
            root=Path(payload['drift_evidence_root']),
            domain=Domain(payload['domain']),
            baseline_as_of=payload['drift_baseline_as_of'],
            as_of=_at(clock['now']),
            relocation_roots=tuple(
                Path(item) for item in payload['drift_relocation_roots']
            ),
            reverify_source=require_current_drift,
        )
        expected_status = (
            'verified_descriptive'
            if report['status'] == 'verified_descriptive'
            else 'verified_' + report['status']
        )
        if (summary['live_drift'] != live_drift_report_reference(path, report)
                or summary['live_drift_evidence_status'] != expected_status
                or summary['live_drift_verified']
                is not report['live_drift_verified']):
            raise ValueError('live drift review evidence mismatch')
    elif (storage_path is not None or liveness_path is not None) and (
            summary['live_drift_verified'] is not False):
        raise ValueError('review summary cannot invent live drift evidence')
    if production_day_path is not None:
        from .research_production_day import (
            production_day_report_reference,
            verify_production_day_evidence,
        )
        path = _safe(Path(production_day_path))
        phase_root = _safe(
            runtime.warm_root / 'research-phases' / payload['domain']
        )
        if (not path.is_file() or path.is_symlink()
                or not path.is_relative_to(phase_root)
                or path.stat().st_size > 1048576
                or not path.parent.parent.name.startswith(
                    'research-production-day-evidence-'
                )):
            raise ValueError('invalid supervised production-day evidence path')
        report = _strict_json(path.read_text())
        verify_production_day_evidence(
            report,
            run_root=Path(payload['production_day_run_root']),
            attestation_path=(
                Path(payload['production_day_attestation_path'])
                if payload['production_day_attestation_path'] is not None else None
            ),
            domain=Domain(payload['domain']),
            production_day=date.fromisoformat(payload['production_day']),
            as_of=_at(clock['now']),
            reverify_source=require_current_production_day,
        )
        expected_status = (
            'verified_closed' if report['production_day_closed']
            else 'verified_incomplete'
        )
        if (summary['production_day_evidence']
                != production_day_report_reference(path, report)
                or summary['production_day_evidence_status'] != expected_status):
            raise ValueError('production-day review evidence mismatch')
    sample_current = ()
    sample_previous = ()
    sample_freeze = False
    if sample_path is not None:
        from .research_monitoring_samples import (
            monitoring_report_reference,
            monitoring_sample_snapshots,
        )

        def verify_sample_ref(path_value, reference):
            path = _safe(Path(path_value))
            phase_root = _safe(runtime.warm_root / 'research-phases' / payload['domain'])
            if (not path.is_file() or path.is_symlink() or not path.is_relative_to(phase_root)
                    or path.stat().st_size > 1048576):
                raise ValueError('invalid supervised racing sample path')
            report = _strict_json(path.read_text())
            samples = monitoring_sample_snapshots(report)
            expected_reference = monitoring_report_reference(path, report)
            roots = [str(_safe(Path(item))) for item in payload['racing_sample_relocation_roots']]
            if (reference != expected_reference
                    or report['root'] != str(_safe(Path(payload['racing_sample_evidence_root'])))
                    or report['relocation_roots'] != roots
                    or any(sample.domain is not Domain(payload['domain'])
                           for sample in samples)):
                raise ValueError('monitoring sample summary reference mismatch')
            return report, samples

        current_report, sample_current = verify_sample_ref(
            sample_path, summary['racing_sample_current'])
        previous_path = payload['previous_racing_sample_report']
        if previous_path is None:
            if summary['racing_sample_previous'] is not None:
                raise ValueError('unexpected previous racing sample')
        else:
            _previous_report, sample_previous = verify_sample_ref(
                previous_path, summary['racing_sample_previous'])
        if _at(summary['racing_sample_current']['observed_at']) != _at(clock['now']):
            raise ValueError('monitoring sample as-of mismatch')
        expected_sample_status = (
            'verified_complete' if current_report['source_coverage_complete']
            else 'verified_incomplete' if current_report['candidate_settlements']
            else 'verified_empty'
        )
        current_scopes = {item.scope: item for item in sample_current}
        previous_scopes = {item.scope: item for item in sample_previous}
        growth = False
        for scope in set(current_scopes) | set(previous_scopes):
            current_item = current_scopes.get(scope)
            previous_item = previous_scopes.get(scope)
            if current_item is None:
                sample_freeze = True
            elif previous_item is not None:
                if not previous_item.unit_ids.issubset(current_item.unit_ids):
                    sample_freeze = True
                elif len(current_item.unit_ids) > len(previous_item.unit_ids):
                    growth = True
        if (summary['sample_evidence_status'] != expected_sample_status
                or summary['sample_growth_observed'] is not growth
                or summary['progress_only'] is not (not growth)):
            raise ValueError('racing sample review semantics mismatch')
    has_incidents = False
    incident_status = 'not_integrated'
    if source_root is not None:
        from .research_production_incidents import verify_production_incidents
        source_report = summary['production_incidents']
        verify_production_incidents(source_report, root=Path(source_root), domain=Domain(payload['domain']), as_of=_at(clock['now']))
        has_incidents = bool(source_report['events'])
        incident_status = 'metadata_issues' if has_incidents else 'metadata_only'
        from .research_guard import production_incident_projection
        from .research_registry import ExperimentRegistry
        freeze = production_incident_projection(runtime, ExperimentRegistry(Path(request['registry'])), Domain(payload['domain']))
        # Historical clean proofs remain valid after a later incident. A fresh
        # worker acknowledgement must nevertheless match current durable state.
        saved_freeze = summary['production_freeze']
        if ((require_current_freeze or saved_freeze is not None) and saved_freeze != freeze
                or saved_freeze is not None and saved_freeze['source_root'] != source_root):
            raise ValueError('review does not match durable production freeze')
        has_incidents = has_incidents or saved_freeze is not None
    if summary['incident_evidence_status'] != incident_status:
        raise ValueError('review incident coverage mismatch')
    for key in ("due_requests", "created_reviews", "already_recorded_reviews", "remaining_requests", "run_completion_events"):
        if type(summary[key]) is not int or not 0 <= summary[key] <= 10000:
            raise ValueError("invalid review summary count")
    processed = summary["processed"]
    if not isinstance(processed, list) or len(processed) > payload["max_reviews"]:
        raise ValueError("invalid processed review list")
    from .research_review_clock import _digest
    _digest(summary["index_hash"])
    ids = set()
    for item in processed:
        if set(item) != {"request_id", "receipt_id", "status", "path"} or item["status"] not in {"created", "duplicate"}:
            raise ValueError("invalid processed review receipt")
        _digest(item["request_id"])
        _digest(item["receipt_id"])
        expected_path = runtime.warm_root.expanduser().absolute() / "research-reviews" / payload["domain"] / (item["request_id"] + ".json")
        if item["request_id"] in ids or Path(item["path"]) != expected_path:
            raise ValueError("review receipt path or identity mismatch")
        ids.add(item["request_id"])
    remaining = summary["due_requests"] - len(processed)
    if (summary["created_reviews"] != sum(item["status"] == "created" for item in processed)
            or summary["remaining_requests"] != remaining
            or summary["next_window_start"] != (summary["as_of"] if remaining == 0 else summary["window_start"])):
        raise ValueError("review summary counts or replay cursor mismatch")
    freeze = (has_incidents or sample_freeze
              or _at(clock["now"]) >= _at(clock["ruler_released_at"]) + timedelta(days=90))
    status = "review_backlog" if remaining else ("reviewed_freeze_required" if freeze else "reviews_recorded")
    if summary["freeze_research_required"] is not freeze or summary["status"] != status:
        raise ValueError("review summary freeze status mismatch")
    expected_receipt = {"disposition": "succeeded", "status": status, "report_path": str(report_path),
                        "content_hash": summary["content_hash"], "request_hash": _hash(request),
                        "model_promotion_allowed": False, "telegram_delivery_confirmed": False}
    if receipt != expected_receipt:
        raise ValueError("review completion receipt mismatch")
