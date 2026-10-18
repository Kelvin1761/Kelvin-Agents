"""Domain router for source-reverified Stage 5 monitoring sample reports."""
from __future__ import annotations

from pathlib import Path

from .contracts import Domain
from .research_index import _Reader, _at, _hashed, _safe


def _paged_consumer_input(path, runtime, checkpoint):
    from .research_racing_monitoring_pages import COVERAGE_SCHEMA

    path = _safe(Path(path))
    if (path.name != "racing-monitoring-coverage.json"
            or not path.is_relative_to(_safe(runtime.warm_root / "research-phases"))
            or not path.parent.parent.name.startswith(("racing-monitoring-corpus-",
                                                       "racing-monitoring-corpus-reconcile-"))):
        raise ValueError("paged monitoring report is outside owned corpus phase")
    reader = _Reader(checkpoint, max_record_bytes=1048576)
    report, report_digest = reader.read(path)
    _hashed(report, COVERAGE_SCHEMA)
    domain = Domain(report["domain"])
    phase_root = _safe(runtime.warm_root / "research-phases" / domain.value)
    if (domain not in {Domain.AU, Domain.HKJC}
            or path.name != "racing-monitoring-coverage.json"
            or not path.is_relative_to(phase_root)
            or not path.parent.parent.name.startswith(("racing-monitoring-corpus-",
                                                       "racing-monitoring-corpus-reconcile-"))):
        raise ValueError("paged monitoring report is outside owned corpus phase")
    payload = {"domain": domain.value, "evidence_root": report["root"],
               "as_of": report["as_of"], "relocation_roots": report["relocation_roots"],
               "max_refs": report["max_refs"], "max_records": report["max_records"]}
    return path, report, report_digest, payload, reader


def _paged_sample_snapshot(report):
    from .research_review_clock import SampleSnapshot
    return (SampleSnapshot(domain=Domain(report["domain"]), scope="all", basis="settled_races",
                           observed_at=_at(report["as_of"]),
                           evidence_digest=report["content_hash"],
                           unit_ids=frozenset(item["unit_id"] for item in report["units"])),)


def source_reverified_paged_monitoring_samples(*, path: Path, runtime, checkpoint):
    """Child-only: caller holds supervisor heavy lease; replay every source.

    Not a parent receipt verifier, nor retry or promotion authority.
    """
    from .research_racing_monitoring_page_runtime import (
        _MONITORING_WITNESSES, reconcile_racing_monitoring_corpus,
    )
    path, report, report_digest, payload, reader = _paged_consumer_input(path, runtime, checkpoint)
    metadata = _Reader(checkpoint, max_record_bytes=4194304)
    witnesses = {}
    for key, name in _MONITORING_WITNESSES.items():
        if name == path.name:
            witnesses[key] = report_digest
        else:
            _, witnesses[key] = metadata.read(path.parent / name)
    verified = reconcile_racing_monitoring_corpus(
        payload=payload, runtime=runtime, workspace=path.parent,
        checkpoint=checkpoint, **witnesses)
    if (verified["content_hash"] != report["content_hash"]
            or verified["verified_monitoring_samples"] != len(report["units"])):
        raise ValueError("replayed monitoring report count or hash differs")
    reader.recheck()
    metadata.recheck()
    checkpoint()
    return _paged_sample_snapshot(report)


def bounded_paged_monitoring_samples(*, path: Path, runtime, checkpoint):
    """Parent companion verification, not independent native source acceptance.

    The review worker must separately replay source under its heavy lease.
    """
    from .research_racing_monitoring_page_runtime import verify_racing_monitoring_corpus_receipt
    path, report, _, payload, reader = _paged_consumer_input(path, runtime, checkpoint)
    verify_racing_monitoring_corpus_receipt(
        payload=payload, runtime=runtime, report_path=path,
        receipt={"content_hash": report["content_hash"],
                 "verified_monitoring_samples": report["verified_monitoring_samples"]})
    reader.recheck()
    checkpoint()
    return _paged_sample_snapshot(report)


def monitoring_sample_snapshots(report: dict):
    """Rebuild one domain report and return its immutable sample scopes."""
    domain = Domain(report.get("domain"))
    if domain in {Domain.AU, Domain.HKJC}:
        from .research_racing_monitoring_samples import monitoring_sample_snapshot
        return (monitoring_sample_snapshot(report),)
    if domain is Domain.NBA:
        from .research_nba_monitoring_samples import monitoring_sample_snapshot
        return (monitoring_sample_snapshot(report),)
    if domain is Domain.TENNIS:
        from .research_tennis_monitoring_samples import monitoring_sample_snapshots
        return monitoring_sample_snapshots(report)
    raise ValueError("unsupported monitoring sample domain")


def monitoring_report_reference(path: Path, report: dict) -> dict:
    samples = monitoring_sample_snapshots(report)
    return _reference_from_samples(path, report, samples)


def _reference_from_samples(path, report, samples):
    if any(item.domain is not Domain(report["domain"])
           or item.evidence_digest != report["content_hash"] for item in samples):
        raise ValueError("monitoring sample scopes disagree on source report")
    observed = {_at(item.observed_at) for item in samples}
    report_at = _at(report["as_of"])
    if observed and observed != {report_at}:
        raise ValueError("monitoring sample scopes disagree on observed time")
    counts = {item.scope: len(item.unit_ids) for item in samples}
    if len(counts) != len(samples):
        raise ValueError("duplicate monitoring sample scope")
    return {
        "path": str(path),
        "content_hash": report["content_hash"],
        "observed_at": report_at.isoformat(),
        "scope_counts": {key: counts[key] for key in sorted(counts)},
        "source_coverage_complete": report["source_coverage_complete"],
    }


def review_child_monitoring_samples(*, path, report, runtime, checkpoint):
    """Dispatch inside the review worker's existing heavy lease."""
    from .research_racing_monitoring_pages import COVERAGE_SCHEMA
    if report.get("schema_version") == COVERAGE_SCHEMA:
        _hashed(report, COVERAGE_SCHEMA)
        samples = source_reverified_paged_monitoring_samples(path=path, runtime=runtime, checkpoint=checkpoint)
    else:
        samples = monitoring_sample_snapshots(report)
    return samples, _reference_from_samples(path, report, samples)


def review_parent_monitoring_samples(*, path, report, runtime, checkpoint):
    """Bounded new-corpus proofs; legacy domain behavior remains unchanged."""
    from .research_racing_monitoring_pages import COVERAGE_SCHEMA
    if report.get("schema_version") == COVERAGE_SCHEMA:
        _hashed(report, COVERAGE_SCHEMA)
        samples = bounded_paged_monitoring_samples(path=path, runtime=runtime, checkpoint=checkpoint)
    else:
        samples = monitoring_sample_snapshots(report)
    return samples, _reference_from_samples(path, report, samples)
