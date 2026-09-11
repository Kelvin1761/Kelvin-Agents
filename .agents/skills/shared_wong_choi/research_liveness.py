"""Fail-closed process-liveness evidence for claimed Stage 5 research jobs.

A queue claim proves ownership, not that its worker still exists.  This module
binds a create-only lease to the immutable claim and checks both PID existence
and process start identity, so PID reuse cannot turn a stale claim green.
"""
from __future__ import annotations

import ctypes
import platform
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from .contracts import Domain
from .research_index import (
    _Reader,
    _at,
    _encoded,
    _hash,
    _hashed,
    _safe,
    build_research_index,
)
from .research_runner import (
    QUEUE_CLAIM_SCHEMA_VERSION,
    QueueClaim,
    _load_hashed_json,
    _write_exclusive_json,
)


LEASE_SCHEMA = "wong-choi-research-liveness-lease/v1"
REPORT_SCHEMA = "wong-choi-research-liveness-evidence/v1"
_STATUSES = {
    "queued", "claimed_liveness_unverified", "running_verified",
    "claimed_not_alive", "terminal",
}


def liveness_report_reference(path: Path, report: dict) -> dict:
    """Return the bounded identity retained by review summaries/cursors."""
    _hashed(report, REPORT_SCHEMA)
    verify_research_liveness_evidence(
        report,
        registry_root=Path(report["registry_root"]),
        queue_root=Path(report["queue_root"]),
        lease_root=Path(report["lease_root"]),
        domain=Domain(report["domain"]), as_of=report["as_of"],
    )
    return {
        "path": str(path),
        "content_hash": report["content_hash"],
        "observed_at": _at(report["as_of"]).isoformat(),
        "queue_index_hash": report["queue_index_hash"],
        "all_claimed_processes_verified": report["all_claimed_processes_verified"],
        "counts": report["counts"],
    }


def probe_process_start_token(pid: int) -> str | None:
    """Return a stable process-start identity, or None when PID is not live."""
    if type(pid) is not int or pid <= 0:
        return None
    if platform.system() == "Darwin":
        class _ProcBsdInfo(ctypes.Structure):
            _fields_ = [
                ("pbi_flags", ctypes.c_uint32), ("pbi_status", ctypes.c_uint32),
                ("pbi_xstatus", ctypes.c_uint32), ("pbi_pid", ctypes.c_uint32),
                ("pbi_ppid", ctypes.c_uint32), ("pbi_uid", ctypes.c_uint32),
                ("pbi_gid", ctypes.c_uint32), ("pbi_ruid", ctypes.c_uint32),
                ("pbi_rgid", ctypes.c_uint32), ("pbi_svuid", ctypes.c_uint32),
                ("pbi_svgid", ctypes.c_uint32), ("rfu_1", ctypes.c_uint32),
                ("pbi_comm", ctypes.c_char * 16), ("pbi_name", ctypes.c_char * 32),
                ("pbi_nfiles", ctypes.c_uint32), ("pbi_pgid", ctypes.c_uint32),
                ("pbi_pjobc", ctypes.c_uint32), ("e_tdev", ctypes.c_uint32),
                ("e_tpgid", ctypes.c_uint32), ("pbi_nice", ctypes.c_int32),
                ("pbi_start_tvsec", ctypes.c_uint64),
                ("pbi_start_tvusec", ctypes.c_uint64),
            ]
        try:
            library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            info = _ProcBsdInfo()
            size = library.proc_pidinfo(
                pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info),
            )
            if size == ctypes.sizeof(info) and info.pbi_pid == pid:
                return f"darwin:{info.pbi_start_tvsec}:{info.pbi_start_tvusec}"
            return None
        except (OSError, AttributeError):
            return None
    if platform.system() == "Linux":
        try:
            # Field 22 is starttime.  Split after the final ')' because comm
            # may itself contain spaces or parentheses.
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            return f"linux:{fields[19]}" if len(fields) > 19 else None
        except (OSError, IndexError):
            return None
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            check=False, capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    token = " ".join(result.stdout.split())
    return token if result.returncode == 0 and 0 < len(token) <= 128 else None


def _lease_name(job_id: str) -> str:
    return quote(job_id, safe="._-") + ".json"


def _token(value) -> str:
    if not isinstance(value, str):
        raise ValueError("process start token required")
    normalized = " ".join(value.split())
    if normalized != value or not 0 < len(value) <= 128:
        raise ValueError("invalid process start token")
    return value


def record_research_liveness_lease(
        *, lease_root: Path, claim: QueueClaim, pid: int,
        process_start_token: str, observed_at: datetime,
        valid_until: datetime) -> Path:
    """Create one immutable lease bound to a canonical queue claim."""
    root = _safe(Path(lease_root).expanduser().absolute())
    if not root.is_dir():
        raise ValueError("existing liveness lease root required")
    if type(pid) is not int or pid <= 0:
        raise ValueError("positive worker pid required")
    token = _token(process_start_token)
    observed, deadline = _at(observed_at), _at(valid_until)
    if not observed < deadline:
        raise ValueError("liveness lease deadline must follow observation")
    claim_path = _safe(claim.path.expanduser().absolute())
    claim_payload = _load_hashed_json(
        claim_path, schema_version=QUEUE_CLAIM_SCHEMA_VERSION,
    )
    if (claim_payload["job_id"] != claim.job.job_id
            or claim_payload["worker_id"] != claim.worker_id
            or claim_payload["job_content_hash"]
            != claim.job.to_payload()["content_hash"]
            or _at(claim_payload["claimed_at"]) > observed
            or deadline > observed + timedelta(seconds=claim.job.timeout_seconds)):
        raise ValueError("liveness lease claim binding or duration mismatch")
    payload = {
        "schema_version": LEASE_SCHEMA,
        "append_only": True,
        "job_id": claim.job.job_id,
        "worker_id": claim.worker_id,
        "claim_content_hash": claim_payload["content_hash"],
        "pid": pid,
        "process_start_token": token,
        "observed_at": observed.isoformat(),
        "valid_until": deadline.isoformat(),
    }
    path = root / _lease_name(claim.job.job_id)
    _write_exclusive_json(path, payload)
    return path


def _load_leases(root: Path, *, checkpoint, max_jobs: int) -> dict[str, dict]:
    reader = _Reader(
        checkpoint, max_records=max_jobs, max_record_bytes=8192,
        max_total_bytes=max_jobs * 8192,
    )
    leases = {}
    for path in reader.listing(root):
        payload, _ = reader.read(path)
        _hashed(payload, LEASE_SCHEMA)
        identity = payload.get("job_id")
        if (not isinstance(identity, str) or not identity
                or path.name != _lease_name(identity) or identity in leases):
            raise ValueError("liveness lease identity mismatch")
        leases[identity] = payload
    reader.recheck()
    return leases


def _validate_lease(lease: dict, item: dict, end: datetime) -> tuple[datetime, datetime]:
    expected = {
        "schema_version", "append_only", "job_id", "worker_id",
        "claim_content_hash", "pid", "process_start_token", "observed_at",
        "valid_until", "content_hash",
    }
    claim = item.get("claim")
    job = item["job"]
    if (set(lease) != expected or lease["append_only"] is not True
            or claim is None or lease["job_id"] != item["job_id"]
            or lease["worker_id"] != claim["worker_id"]
            or lease["claim_content_hash"] != claim["content_hash"]):
        raise ValueError("liveness lease claim binding mismatch")
    if type(lease["pid"]) is not int or lease["pid"] <= 0:
        raise ValueError("invalid liveness lease pid")
    _token(lease["process_start_token"])
    observed, deadline = _at(lease["observed_at"]), _at(lease["valid_until"])
    if (not _at(claim["claimed_at"]) <= observed <= end
            or not observed < deadline
            or deadline > observed + timedelta(seconds=job["timeout_seconds"])):
        raise ValueError("liveness lease time binding mismatch")
    return observed, deadline


def _projection(index: dict, leases: dict[str, dict], domain: Domain,
                end: datetime, process_probe: Callable[[int], str | None]) -> list[dict]:
    selected = [item for item in index["queue"] if item["domain"] == domain.value]
    indexed = {item["job_id"]: item for item in index["queue"]}
    known = set(indexed)
    if set(leases) - known:
        raise ValueError("orphan liveness lease")
    for identity, lease in leases.items():
        if indexed[identity]["claim"] is None:
            raise ValueError("liveness lease has no claim binding")
        _validate_lease(lease, indexed[identity], end)
    output = []
    for item in selected:
        claim, outcome, lease = item["claim"], item["outcome"], leases.get(item["job_id"])
        projected = {
            "job_id": item["job_id"], "domain": item["domain"],
            "worker_id": claim["worker_id"] if claim else None,
            "claim_content_hash": claim["content_hash"] if claim else None,
            "lease_content_hash": lease["content_hash"] if lease else None,
            "pid": lease["pid"] if lease else None,
            "status": "queued", "process_alive": None,
            "reason": "not_claimed",
        }
        if outcome is not None:
            if lease is not None:
                _validate_lease(lease, item, end)
            projected.update(status="terminal", reason=item["status"])
        elif claim is None:
            if lease is not None:
                raise ValueError("liveness lease has no claim binding")
        elif lease is None:
            projected.update(
                status="claimed_liveness_unverified", reason="lease_missing",
            )
        else:
            _, deadline = _validate_lease(lease, item, end)
            if end > deadline:
                projected.update(
                    status="claimed_not_alive", process_alive=False,
                    reason="lease_expired",
                )
            else:
                current = process_probe(lease["pid"])
                alive = current == lease["process_start_token"]
                projected.update(
                    status="running_verified" if alive else "claimed_not_alive",
                    process_alive=alive,
                    reason="process_identity_matched" if alive else "process_identity_missing_or_changed",
                )
        output.append(projected)
    return output


def collect_research_liveness_evidence(
        *, registry_root: Path, queue_root: Path, lease_root: Path,
        domain: Domain, as_of: datetime,
        process_probe: Callable[[int], str | None] = probe_process_start_token,
        checkpoint: Callable[[], None] = lambda: None,
        max_jobs: int = 1000) -> dict:
    """Build a bounded liveness view; never changes queue or model state."""
    if (not isinstance(domain, Domain) or type(max_jobs) is not int
            or not 0 < max_jobs <= 1000):
        raise ValueError("known domain and positive liveness bound required")
    registry = _safe(Path(registry_root).expanduser().absolute())
    queue = _safe(Path(queue_root).expanduser().absolute())
    leases_root = _safe(Path(lease_root).expanduser().absolute())
    if not leases_root.is_dir():
        raise ValueError("configured liveness lease root missing")
    end = _at(as_of)
    index = build_research_index(
        registry_root=registry, queue_root=queue, as_of=end,
        checkpoint=checkpoint, max_records=10000,
    )
    if len(index["queue"]) > max_jobs:
        raise ValueError("liveness queue bound exceeded")
    leases = _load_leases(leases_root, checkpoint=checkpoint, max_jobs=max_jobs)
    queue_view = _projection(index, leases, domain, end, process_probe)
    counts = Counter(item["status"] for item in queue_view)
    report = {
        "schema_version": REPORT_SCHEMA,
        "domain": domain.value,
        "registry_root": str(registry),
        "queue_root": str(queue),
        "lease_root": str(leases_root),
        "as_of": end.isoformat(),
        "queue_index_hash": index["content_hash"],
        "queue": queue_view,
        "counts": {status: counts[status] for status in sorted(_STATUSES)},
        "source_snapshot_verified": True,
        "process_liveness_verified": True,
        "all_claimed_processes_verified": all(
            item["status"] != "claimed_liveness_unverified" for item in queue_view
        ),
        "model_promotion_allowed": False,
        "queue_mutation_allowed": False,
    }
    report["content_hash"] = _hash(report)
    verify_research_liveness_evidence(
        report, registry_root=registry, queue_root=queue,
        lease_root=leases_root, domain=domain, as_of=end,
        process_probe=process_probe,
    )
    return report


def verify_research_liveness_evidence(
        report: dict, *, registry_root: Path, queue_root: Path,
        lease_root: Path, domain: Domain, as_of: datetime,
        process_probe: Callable[[int], str | None] = probe_process_start_token,
        reverify_source: bool = False,
        checkpoint: Callable[[], None] = lambda: None) -> None:
    """Validate the report and optionally rebuild current source evidence."""
    _hashed(report, REPORT_SCHEMA)
    expected = {
        "schema_version", "domain", "registry_root", "queue_root",
        "lease_root", "as_of", "queue_index_hash", "queue", "counts",
        "source_snapshot_verified", "process_liveness_verified",
        "all_claimed_processes_verified", "model_promotion_allowed",
        "queue_mutation_allowed", "content_hash",
    }
    registry = _safe(Path(registry_root).expanduser().absolute())
    queue = _safe(Path(queue_root).expanduser().absolute())
    leases = _safe(Path(lease_root).expanduser().absolute())
    end = _at(as_of)
    if (set(report) != expected or report["domain"] != domain.value
            or report["registry_root"] != str(registry)
            or report["queue_root"] != str(queue)
            or report["lease_root"] != str(leases)
            or report["as_of"] != end.isoformat()
            or not re.fullmatch("[0-9a-f]{64}", report.get("queue_index_hash", ""))
            or len(_encoded(report)) > 1048576):
        raise ValueError("liveness evidence scope or size mismatch")
    if (report["source_snapshot_verified"] is not True
            or report["process_liveness_verified"] is not True
            or type(report["all_claimed_processes_verified"]) is not bool
            or report["model_promotion_allowed"] is not False
            or report["queue_mutation_allowed"] is not False):
        raise ValueError("liveness evidence cannot grant unrelated authority")
    if (not isinstance(report["queue"], list)
            or [item.get("job_id") for item in report["queue"]
                if isinstance(item, dict)]
            != sorted(item.get("job_id") for item in report["queue"]
                      if isinstance(item, dict))):
        raise ValueError("invalid liveness queue projection")
    counts, identities = Counter(), set()
    for item in report["queue"]:
        if (not isinstance(item, dict)
                or set(item) != {
                    "job_id", "domain", "worker_id", "claim_content_hash",
                    "lease_content_hash", "pid", "status", "process_alive",
                    "reason",
                }
                or item["domain"] != domain.value or item["status"] not in _STATUSES
                or not isinstance(item["job_id"], str) or not item["job_id"]
                or item["job_id"] in identities
                or item["process_alive"] is not None
                    and type(item["process_alive"]) is not bool
                or item["worker_id"] is not None
                    and (not isinstance(item["worker_id"], str) or not item["worker_id"])
                or item["pid"] is not None
                    and (type(item["pid"]) is not int or item["pid"] <= 0)
                or any(value is not None and not re.fullmatch("[0-9a-f]{64}", value)
                       for value in (item["claim_content_hash"], item["lease_content_hash"]))
                or not isinstance(item["reason"], str) or not item["reason"]):
            raise ValueError("invalid liveness queue projection")
        identities.add(item["job_id"])
        if item["status"] == "queued":
            valid = (item["worker_id"], item["claim_content_hash"],
                     item["lease_content_hash"], item["pid"],
                     item["process_alive"], item["reason"]) == (
                         None, None, None, None, None, "not_claimed",
                     )
        elif item["status"] == "claimed_liveness_unverified":
            valid = (item["worker_id"] is not None
                     and item["claim_content_hash"] is not None
                     and item["lease_content_hash"] is None
                     and item["pid"] is None and item["process_alive"] is None
                     and item["reason"] == "lease_missing")
        elif item["status"] == "running_verified":
            valid = (all(item[key] is not None for key in (
                        "worker_id", "claim_content_hash", "lease_content_hash", "pid"))
                     and item["process_alive"] is True
                     and item["reason"] == "process_identity_matched")
        elif item["status"] == "claimed_not_alive":
            valid = (all(item[key] is not None for key in (
                        "worker_id", "claim_content_hash", "lease_content_hash", "pid"))
                     and item["process_alive"] is False
                     and item["reason"] in {
                         "lease_expired", "process_identity_missing_or_changed",
                     })
        else:
            valid = (item["worker_id"] is not None
                     and item["claim_content_hash"] is not None
                     and item["process_alive"] is None
                     and item["reason"] in {
                         "succeeded", "failed", "blocked", "deferred",
                         "timed_out", "preempted",
                     })
        if not valid:
            raise ValueError("inconsistent liveness queue projection")
        counts[item["status"]] += 1
    expected_counts = {status: counts[status] for status in sorted(_STATUSES)}
    if (report["counts"] != expected_counts
            or report["all_claimed_processes_verified"] != (
                expected_counts["claimed_liveness_unverified"] == 0
            )):
        raise ValueError("liveness evidence counts mismatch")
    if reverify_source:
        rebuilt = collect_research_liveness_evidence(
            registry_root=registry, queue_root=queue, lease_root=leases,
            domain=domain, as_of=end, process_probe=process_probe,
            checkpoint=checkpoint,
        )
        if _encoded(rebuilt) != _encoded(report):
            raise ValueError("liveness source changed during verification")
