"""Domain router for source-reverified Stage 5 monitoring sample reports."""
from __future__ import annotations

from pathlib import Path

from .contracts import Domain
from .research_index import _at


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
