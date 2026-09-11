"""Read-only Central research projection and create-only local review receipts.

Registry/report integrity is not fresh model-safety verification. Queue claims
are not process liveness. Receipt completion is neither delivery nor approval.
Callers doing unattended I/O must run this under the research supervisor; the
checkpoint hook alone is not a hard timeout for an unavailable filesystem.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote
from uuid import uuid4

from .contracts import Domain
from .research_registry import ExperimentRegistry, ResearchKind, ResearchConflictError, MissingResearchParentError, _record_from_payload
from .research_review_clock import plan_reviews, SampleSnapshot, ReviewEvent
from .research_runner import ResearchJob, ResearchDisposition, QueueConflictError
from .research_safety import _json, ResearchSafetyError


INDEX_SCHEMA = "wong-choi-research-index/v1"
RECEIPT_SCHEMA = "wong-choi-research-review-receipt/v1"
_EVIDENCE_ERRORS = (OSError, ValueError, KeyError, TypeError, ResearchConflictError, MissingResearchParentError, QueueConflictError, ResearchSafetyError)


class ResearchIndexError(RuntimeError):
    pass


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _hash(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _hashed(value, schema):
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        raise ResearchIndexError("unsupported index evidence schema")
    if value.get("content_hash") != _hash({key: item for key, item in value.items() if key != "content_hash"}):
        raise ResearchIndexError("index evidence hash mismatch")
    return value


def _at(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ResearchIndexError("aware timestamp required")
    return value.astimezone(timezone.utc)


def _safe(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or any(item.is_symlink() for item in (path, *path.parents)):
        raise ResearchIndexError("absolute non-symlink evidence path required")
    return path


class _Reader:
    def __init__(self, checkpoint, *, max_records=10000, max_record_bytes=1048576, max_total_bytes=33554432):
        if any(type(value) is not int or value <= 0 for value in (max_records, max_record_bytes, max_total_bytes)):
            raise ResearchIndexError("positive evidence read bounds required")
        self.checkpoint = checkpoint
        self.max_records, self.max_record_bytes, self.max_total_bytes = max_records, max_record_bytes, max_total_bytes
        self.files, self.directories, self.bytes_read = {}, {}, 0

    def listing(self, folder):
        self.checkpoint()
        folder = _safe(folder)
        if not folder.exists():
            result = ()
        else:
            if not folder.is_dir():
                raise ResearchIndexError("evidence collection must be a directory")
            names = []
            with os.scandir(folder) as entries:
                for entry_count, entry in enumerate(entries):
                    if entry_count >= self.max_records:
                        raise ResearchIndexError("evidence entry limit exceeded")
                    if entry.is_symlink():
                        raise ResearchIndexError("symlink evidence entry")
                    # Registry's atomic-link staging files are not committed records.
                    if entry.name.startswith(".") and entry.name.endswith(".tmp"):
                        continue
                    names.append(entry.name)
            result = tuple(sorted(names))
        if folder in self.directories and self.directories[folder] != result:
            raise ResearchIndexError("evidence directory changed during read")
        self.directories[folder] = result
        return tuple(folder / name for name in result)

    def read(self, path):
        self.checkpoint()
        path = _safe(path)
        if not stat.S_ISREG(path.stat().st_mode):
            raise ResearchIndexError("evidence must be a regular file")
        if path not in self.files and len(self.files) >= self.max_records:
            raise ResearchIndexError("evidence record limit exceeded")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > self.max_record_bytes:
                raise ResearchIndexError("evidence file type or size limit")
            chunks, length = [], 0
            while True:
                self.checkpoint()
                chunk = os.read(descriptor, min(65536, self.max_record_bytes - length + 1))
                if not chunk:
                    break
                length += len(chunk)
                self.bytes_read += len(chunk)
                if length > self.max_record_bytes or self.bytes_read > self.max_total_bytes:
                    raise ResearchIndexError("evidence byte budget exceeded")
                chunks.append(chunk)
        finally:
            os.close(descriptor)
        raw = b"".join(chunks)
        digest = hashlib.sha256(raw).hexdigest()
        if path in self.files and self.files[path] != digest:
            raise ResearchIndexError("evidence bytes changed during read")
        self.files[path] = digest
        return _json(raw), digest

    def recheck(self):
        for path in tuple(self.files):
            self.read(path)
        for folder in tuple(self.directories):
            self.listing(folder)
        self.checkpoint()


class _FrozenRegistry(ExperimentRegistry):
    def __init__(self, records):
        self.records = records

    def _parent(self, child, link_name, parent_id, expected_kind):
        parent = self.records.get(parent_id)
        if not parent or parent["kind"] != expected_kind.value or parent["domain"] != child.domain.value:
            raise ResearchIndexError("missing, wrong-kind or cross-domain parent")
        return parent


def _registry(reader, root, as_of):
    root = _safe(root)
    if not root.is_dir():
        raise ResearchIndexError("registry root missing; not an empty healthy registry")
    records = {}
    known = {kind.value for kind in ResearchKind}
    for folder in reader.listing(root / "records"):
        if folder.name not in known or not folder.is_dir():
            raise ResearchIndexError("unknown registry collection")
        for path in reader.listing(folder):
            payload, _ = reader.read(path)
            _hashed(payload, "wong-choi-research-record/v1")
            record = _record_from_payload(payload)
            if _encoded(record.to_payload()) != _encoded(payload):
                raise ResearchIndexError("noncanonical registry record")
            if path.name != quote(record.record_id, safe="._-") + ".json" or folder.name != record.kind.value:
                raise ResearchIndexError("registry filename/identity mismatch")
            if record.record_id in records or _at(record.created_at) > as_of:
                raise ResearchIndexError("duplicate or future registry record")
            records[record.record_id] = payload
    _validate_records(records, as_of)
    return records


def _validate_records(records, as_of):
    for identity, payload in records.items():
        _hashed(payload, "wong-choi-research-record/v1")
        record = _record_from_payload(payload)
        if (record.record_id != identity or _encoded(record.to_payload()) != _encoded(payload)
                or _at(record.created_at) > as_of):
            raise ResearchIndexError("noncanonical or future record in snapshot")
    frozen = _FrozenRegistry(records)
    for payload in records.values():
        frozen._validate_links(_record_from_payload(payload))
    finished = set()
    for identity in records:
        trail, current = set(), identity
        while current and current not in finished:
            if current in trail:
                raise ResearchIndexError("cyclic parent experiment lineage")
            trail.add(current)
            current = records[current]["links"].get("parent_spec_id")
        finished.update(trail)


def _queue(reader, root, records, as_of):
    if root is None:
        return []
    root = _safe(root)
    if not root.is_dir():
        raise ResearchIndexError("configured queue root missing")
    groups = {}
    for collection in ("jobs", "claims", "outcomes"):
        groups[collection] = {}
        for path in reader.listing(root / collection):
            payload, _ = reader.read(path)
            schema = {"jobs": "job", "claims": "claim", "outcomes": "outcome"}[collection]
            _hashed(payload, f"wong-choi-research-{schema}/v1")
            identity = payload["job_id"]
            if path.name != quote(identity, safe="._-") + ".json" or payload.get("append_only") is not True:
                raise ResearchIndexError("queue identity mismatch")
            groups[collection][identity] = payload
    return _project_queue(groups, records, as_of)


def _project_queue(groups, records, as_of):
    if (set(groups["claims"]) | set(groups["outcomes"])) - set(groups["jobs"]):
        raise ResearchIndexError("orphan queue claim or outcome")
    output = []
    for identity, payload in sorted(groups["jobs"].items()):
        job = ResearchJob.from_payload(payload)
        if job.job_id != identity or _encoded(job.to_payload()) != _encoded(payload):
            raise ResearchIndexError("noncanonical queue job")
        spec = records.get(job.spec_id)
        if not spec or spec["kind"] != "experiment_spec" or spec["domain"] != job.domain.value:
            raise ResearchIndexError("queue job requires registered domain spec")
        claim, outcome = groups["claims"].get(identity), groups["outcomes"].get(identity)
        status = "queued"
        if claim:
            _hashed(claim, "wong-choi-research-claim/v1")
            if (set(claim) != {"schema_version", "append_only", "job_id", "worker_id", "claimed_at", "job_content_hash", "content_hash"}
                    or claim["job_id"] != identity or claim["append_only"] is not True
                    or claim["job_content_hash"] != payload["content_hash"] or not isinstance(claim["worker_id"], str) or not claim["worker_id"].strip()
                    or _at(claim["claimed_at"]) > as_of):
                raise ResearchIndexError("queue claim provenance mismatch")
            status = "claimed_liveness_unverified"
        if outcome:
            _hashed(outcome, "wong-choi-research-outcome/v1")
            expected = {"schema_version", "append_only", "job_id", "worker_id", "disposition", "status",
                        "experiment_run_id", "artifact_path", "reproducibility_digest", "completed_at", "content_hash"}
            if (set(outcome) != expected or outcome["job_id"] != identity or outcome["append_only"] is not True
                    or not claim or outcome["worker_id"] != claim["worker_id"]
                    or not _at(claim["claimed_at"]) <= _at(outcome["completed_at"]) <= as_of):
                raise ResearchIndexError("queue outcome provenance mismatch")
            status = ResearchDisposition(outcome["disposition"]).value
            if outcome["experiment_run_id"]:
                run = records.get(outcome["experiment_run_id"])
                if not run or run["kind"] != "experiment_run" or run["links"]["spec_id"] != job.spec_id:
                    raise ResearchIndexError("queue outcome run mismatch")
                run_suffix = _hash({"job_id": identity, "started_at": run["started_at"], "artifact_digest": run["artifact_digest"]})[:24]
                if (run["record_id"] != f"wc:{job.domain.value}:experiment-run:{run_suffix}"
                        or not _at(claim["claimed_at"]) <= _at(run["started_at"]) <= _at(run["completed_at"]) <= _at(outcome["completed_at"])):
                    raise ResearchIndexError("queue outcome is not the claimed job's run")
                if (status == "succeeded") != (run["state"] == "succeeded"):
                    raise ResearchIndexError("queue outcome success mismatch")
            elif status == "succeeded":
                raise ResearchIndexError("successful queue outcome lacks registered run")
        output.append({"job_id": identity, "domain": job.domain.value, "spec_id": job.spec_id,
                       "status": status, "process_alive": None, "job": payload, "claim": claim, "outcome": outcome})
    return output


def _report(reader, path, decision, records):
    payload, byte_hash = reader.read(path)
    return _verify_report(payload, byte_hash, decision, records)


def _verify_report(payload, byte_hash, decision, records):
    from .research_evaluation import EvaluationVerdict, _decision_for_evaluation
    _hashed(payload, "wong-choi-research-evaluation/v2")
    run = records[decision["links"]["run_id"]]
    spec = records[run["links"]["spec_id"]]
    expected = {"schema_version", "append_only", "domain", "spec_id", "dataset_manifest_id", "ruler_id", "ruler_digest",
                "input_metrics_digest", "verdict", "reason", "promotion_proposal_allowed", "safety_passed", "scopes", "safety_report", "content_hash"}
    if (set(payload) != expected or payload["append_only"] is not True or byte_hash != decision["artifact_digest"]
            or payload["domain"] != decision["domain"] or payload["spec_id"] != spec["record_id"]
            or payload["dataset_manifest_id"] != run["links"]["dataset_manifest_id"]
            or payload["ruler_id"] != spec["evaluation_ruler_id"] or payload["ruler_digest"] != spec["evaluation_ruler_digest"]
            or not isinstance(payload["scopes"], list)):
        raise ResearchIndexError("report hash or lineage mismatch")
    wrapper = SimpleNamespace(to_payload=lambda: payload, domain=Domain(payload["domain"]),
                              verdict=EvaluationVerdict(payload["verdict"]), reason=payload["reason"],
                              input_metrics_digest=payload["input_metrics_digest"])
    expected_decision = _decision_for_evaluation(wrapper, run["record_id"], byte_hash, decision["decided_at"])
    if _encoded(expected_decision.to_payload()) != _encoded(decision):
        raise ResearchIndexError("report does not match registered decision")
    return payload


def _project_experiments(records, report_loader):
    children, decisions_by_run = defaultdict(list), defaultdict(list)
    ordered = sorted(records.values(), key=lambda value: value["record_id"])
    for item in ordered:
        if "spec_id" in item["links"]:
            children[item["links"]["spec_id"]].append(item)
        if item["kind"] == "experiment_decision":
            decisions_by_run[item["links"]["run_id"]].append(item)
    experiments = []
    for spec in ordered:
        if spec["kind"] != "experiment_spec":
            continue
        datasets, runs = [], []
        for item in children[spec["record_id"]]:
            if item["kind"] == "dataset_manifest":
                datasets.append({"record_id": item["record_id"], "manifest_rows": item["row_count"],
                                 "sample_hash": item["sample_hash"], "splits": item["splits"]})
            elif item["kind"] == "experiment_run":
                decisions = []
                for choice in decisions_by_run[item["record_id"]]:
                    proposal = choice["state"] == "shadow_review_proposal"
                    if proposal and item["state"] != "succeeded":
                        raise ResearchIndexError("failed run cannot support a registered shadow proposal")
                    report = report_loader(choice)
                    decisions.append({"record_id": choice["record_id"], "state": choice["state"], "rationale": choice["rationale"],
                                      "report_verification": "hash_and_lineage_verified_not_recomputed" if report else "not_supplied",
                                      "report": report, "next_human_action": "verify_evidence_then_shadow_review" if proposal else None})
                runs.append({"record_id": item["record_id"], "execution_state": item["state"],
                             "registered_decisions": decisions, "completed_at": item["completed_at"]})
        experiments.append({"spec_id": spec["record_id"], "domain": spec["domain"], "hypothesis": spec["hypothesis"],
                            "ruler_id": spec["evaluation_ruler_id"], "ruler_digest": spec["evaluation_ruler_digest"],
                            "baseline_commit": spec["baseline_commit"], "candidate_commit": spec["candidate_commit"],
                            "datasets": datasets, "runs": runs})
    return experiments


def build_research_index(*, registry_root, as_of, queue_root=None, report_paths=None,
                         checkpoint=lambda: None, max_records=10000, max_record_bytes=1048576, max_total_bytes=33554432):
    try:
        now = _at(as_of)
        reader = _Reader(checkpoint, max_records=max_records, max_record_bytes=max_record_bytes, max_total_bytes=max_total_bytes)
        records = _registry(reader, registry_root, now)
        queue = _queue(reader, queue_root, records, now)
        reports = report_paths or {}
        if any(key not in records or records[key]["kind"] != "experiment_decision" for key in reports):
            raise ResearchIndexError("report reference lacks registered decision")
        experiments = _project_experiments(records, lambda choice: _report(reader, reports[choice["record_id"]], choice, records)
                                            if choice["record_id"] in reports else None)
        reader.recheck()
        counts = Counter(item["kind"] for item in records.values())
        payload = {"schema_version": INDEX_SCHEMA, "as_of": now.isoformat(), "registry_root": str(registry_root),
                   "records": [records[key] for key in sorted(records)], "experiments": experiments, "queue": queue,
                   "counts": {kind.value: counts[kind.value] for kind in ResearchKind},
                   "evidence": [{"path": str(path), "sha256": digest} for path, digest in sorted(reader.files.items())],
                   "verified_monitoring_samples": None, "safety_recomputed": False, "process_liveness_verified": False,
                   "model_promotion_allowed": False, "rerun_scoring_allowed": False}
        payload["content_hash"] = _hash(payload)
        return payload
    except (InterruptedError, ResearchIndexError):
        raise
    except _EVIDENCE_ERRORS as exc:
        raise ResearchIndexError(f"research index rejected: {exc}") from exc


def _verify_index_snapshot(index):
    _hashed(index, INDEX_SCHEMA)
    expected = {"schema_version", "as_of", "registry_root", "records", "experiments", "queue", "counts", "evidence",
                "verified_monitoring_samples", "safety_recomputed", "process_liveness_verified", "model_promotion_allowed",
                "rerun_scoring_allowed", "content_hash"}
    if (set(index) != expected or index["verified_monitoring_samples"] is not None
            or any(index[key] is not False for key in ("safety_recomputed", "process_liveness_verified", "model_promotion_allowed", "rerun_scoring_allowed"))):
        raise ResearchIndexError("index cannot grant execution or safety authority")
    records = {item["record_id"]: item for item in index["records"]}
    if len(records) != len(index["records"]):
        raise ResearchIndexError("duplicate snapshot record")
    _validate_records(records, _at(index["as_of"]))
    counts = Counter(item["kind"] for item in records.values())
    if index["counts"] != {kind.value: counts[kind.value] for kind in ResearchKind}:
        raise ResearchIndexError("index count projection mismatch")
    reports = {}
    for experiment in index["experiments"]:
        for run in experiment["runs"]:
            for choice in run["registered_decisions"]:
                if choice["report"] is not None:
                    body = (json.dumps(choice["report"], ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
                    reports[choice["record_id"]] = _verify_report(choice["report"], hashlib.sha256(body).hexdigest(), records[choice["record_id"]], records)
    projected = _project_experiments(records, lambda choice: reports.get(choice["record_id"]))
    if _encoded(projected) != _encoded(index["experiments"]):
        raise ResearchIndexError("index experiment projection mismatch")
    groups = {key: {} for key in ("jobs", "claims", "outcomes")}
    for item in index["queue"]:
        identity = item["job_id"]
        if identity in groups["jobs"]:
            raise ResearchIndexError("duplicate snapshot queue job")
        for collection, key in (("jobs", "job"), ("claims", "claim"), ("outcomes", "outcome")):
            if item[key] is not None:
                groups[collection][identity] = item[key]
    if _encoded(_project_queue(groups, records, _at(index["as_of"]))) != _encoded(index["queue"]):
        raise ResearchIndexError("index queue projection mismatch")


def _clock_payload(options):
    payload = {key: options[key] for key in ("domain", "window_start", "now", "ruler_digest", "ruler_released_at")}
    payload["domain"] = payload["domain"].value
    for key in ("window_start", "now", "ruler_released_at"):
        payload[key] = _at(payload[key]).isoformat()
    for name in ("samples", "previous_samples"):
        payload[name] = sorted(({"domain": item.domain.value, "scope": item.scope, "basis": item.basis,
                                "observed_at": _at(item.observed_at).isoformat(), "evidence_digest": item.evidence_digest,
                                "unit_ids": sorted(item.unit_ids)} for item in options.get(name, ())), key=lambda item: item["scope"])
    payload["events"] = sorted(({"kind": item.kind, "event_id": item.event_id, "occurred_at": _at(item.occurred_at).isoformat(),
                                  "evidence_digest": item.evidence_digest,
                                  **({"production_day": item.production_day.isoformat()} if item.production_day is not None else {})}
                                 for item in options.get("events", ())), key=lambda item: (item["kind"], item["event_id"]))
    payload["completed_request_ids"] = sorted(options.get("completed_request_ids", ()))
    return payload


def _clock_options(payload):
    options = {**payload, "domain": Domain(payload["domain"])}
    for key in ("window_start", "now", "ruler_released_at"):
        options[key] = _at(payload[key])
    for name in ("samples", "previous_samples"):
        options[name] = tuple(SampleSnapshot(**{**item, "domain": Domain(item["domain"]),
                                              "observed_at": _at(item["observed_at"]), "unit_ids": frozenset(item["unit_ids"])}) for item in payload[name])
    options["events"] = tuple(ReviewEvent(**{**item, "occurred_at": _at(item["occurred_at"]),
                                             **({"production_day": date.fromisoformat(item["production_day"])} if "production_day" in item else {})})
                               for item in payload["events"])
    options["completed_request_ids"] = frozenset(payload["completed_request_ids"])
    return options


def _load_review_receipt(path, reader):
    try:
        payload, _ = reader.read(path)
        _hashed(payload, RECEIPT_SCHEMA)
        expected = {"schema_version", "domain", "request_id", "recorded_at", "clock_inputs", "plan", "index",
                    "telegram_delivery_confirmed", "model_promotion_allowed", "content_hash"}
        if set(payload) != expected or payload["telegram_delivery_confirmed"] is not False or payload["model_promotion_allowed"] is not False:
            raise ResearchIndexError("review receipt is not approval or delivery evidence")
        plan, index = payload["plan"], payload["index"]
        _verify_index_snapshot(index)
        options = _clock_options(payload["clock_inputs"])
        if _encoded(_clock_payload(options)) != _encoded(payload["clock_inputs"]) or plan_reviews(**options) != plan:
            raise ResearchIndexError("review clock receipt replay mismatch")
        if (payload["domain"] != plan["domain"] or payload["recorded_at"] != plan["as_of"] or index["as_of"] != plan["as_of"]
                or sum(item["request_id"] == payload["request_id"] for item in plan["requests"]) != 1
                or Path(path).name != payload["request_id"] + ".json" or Path(path).parent.name != payload["domain"]):
            raise ResearchIndexError("review receipt identity mismatch")
        return payload
    except (ResearchIndexError, InterruptedError):
        raise
    except _EVIDENCE_ERRORS as exc:
        raise ResearchIndexError(f"invalid review receipt: {exc}") from exc


def load_review_receipt(path):
    return _load_review_receipt(path, _Reader(lambda: None, max_record_bytes=16777216))


def record_review(*, root, registry_root, clock_inputs, request_id, queue_root=None, report_paths=None, checkpoint=lambda: None):
    plan = plan_reviews(**clock_inputs)
    if sum(item["request_id"] == request_id for item in plan["requests"]) != 1:
        raise ResearchIndexError("requested review is not due")
    index = build_research_index(registry_root=registry_root, as_of=clock_inputs["now"], queue_root=queue_root,
                                 report_paths=report_paths, checkpoint=checkpoint)
    payload = {"schema_version": RECEIPT_SCHEMA, "domain": plan["domain"], "request_id": request_id,
               "recorded_at": plan["as_of"], "clock_inputs": _clock_payload(clock_inputs), "plan": plan, "index": index,
               "telegram_delivery_confirmed": False, "model_promotion_allowed": False}
    payload["content_hash"] = _hash(payload)
    raw = _encoded(payload)
    if len(raw) > 16777216:
        raise ResearchIndexError("review receipt exceeds bounded metadata size")
    path = _safe(Path(root) / plan["domain"] / (request_id + ".json"))
    checkpoint()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        checkpoint()
        try:
            os.link(temporary, path)
            status = "created"
        except FileExistsError:
            if load_review_receipt(path) != payload:
                raise ResearchIndexError("immutable review receipt conflict")
            status = "duplicate"
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)
    return {"status": status, "path": path, "receipt_id": payload["content_hash"]}


def completed_review_request_ids(root, domain, *, checkpoint=lambda: None, registry_root=None):
    if not isinstance(domain, Domain):
        raise ResearchIndexError("known review domain required")
    reader = _Reader(checkpoint, max_record_bytes=16777216)
    expected_registry = _safe(registry_root) if registry_root is not None else None
    ids = set()
    for path in reader.listing(_safe(Path(root) / domain.value)):
        receipt = _load_review_receipt(path, reader)
        if expected_registry is not None and Path(receipt["index"]["registry_root"]) != expected_registry:
            raise ResearchIndexError("review completion belongs to another registry")
        ids.add(receipt["request_id"])
    result = frozenset(ids)
    reader.recheck()
    return result
