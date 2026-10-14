"""Local-only Stage 5 review projection; never part of the public sports feed.

Callers select explicit receipts. This exporter verifies their snapshot lineage,
not current source truth, and grants no authority to mutate models or ledgers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

_DASHBOARD = Path(__file__).resolve().parents[2]
_REPO_SKILLS = str(_DASHBOARD.parent / ".agents/skills")
if _REPO_SKILLS not in sys.path:
    # Respect an explicitly supplied approved runtime (for example Release A
    # during pre-merge integration) instead of shadowing it with this checkout.
    sys.path.append(_REPO_SKILLS)

from shared_wong_choi.research_index import load_review_receipt
from shared_wong_choi.research_presentation import prepare_review_presentation

SCHEMA = "wong-choi-research-dashboard/v1"
MAX_FEED_BYTES = 2 * 1024 * 1024
_VIEW_FIELDS = (
    "domain", "as_of", "request_id", "receipt_hash", "index_hash", "review_ruler_digest",
    "counts", "queue", "other_ruler_experiment_ids", "freeze_reasons", "findings",
    "freeze_research_required", "human_review_required", "progress_only",
    "verified_monitoring_samples", "production_day_evidence_status",
    "storage_health", "live_drift_evidence_status", "live_drift",
    "queue_completeness_verified", "process_liveness_verified", "evidence_scope",
    "safety_recomputed", "model_promotion_allowed", "rerun_scoring_allowed",
    "reevaluate_promotion_allowed",
)
_OPTIONAL_VIEW_FIELDS = (
    "storage_evidence", "process_liveness", "production_day_evidence",
)


def _pick(value, fields):
    return {key: value[key] for key in fields}


def _experiment(item):
    result = _pick(item, ("spec_id", "domain", "hypothesis", "ruler_id", "ruler_digest",
                          "baseline_commit", "candidate_commit", "datasets"))
    result["runs"] = []
    for run in item["runs"]:
        projected = _pick(run, ("record_id", "execution_state", "completed_at"))
        projected["registered_decisions"] = []
        for choice in run["registered_decisions"]:
            decision = _pick(choice, ("record_id", "state", "rationale", "report_verification", "next_human_action"))
            report = choice["report"]
            # Raw safety artifacts include source paths and are deliberately not
            # copied. Metric/CI scopes remain original report data, not rejudged.
            decision["report"] = _pick(report, ("content_hash", "scopes")) if report else None
            projected["registered_decisions"].append(decision)
        result["runs"].append(projected)
    return result


def build_research_feed(receipt_paths, *, registry_root, review_summary_paths=None):
    """Bounded, deterministic selection: at most one verified receipt per domain."""
    registry = Path(registry_root)
    if not registry.is_absolute() or registry.resolve() != registry or not registry.is_dir():
        raise ValueError("expected an existing absolute non-symlink registry")
    summaries = dict(review_summary_paths or {})
    if (len(summaries) > 4 or any(
            key not in {"au", "hkjc", "tennis", "nba"}
            or not isinstance(value, Path)
            for key, value in summaries.items())):
        raise ValueError("review summaries require an explicit domain-to-Path mapping")
    domains = {}
    for count, path in enumerate(receipt_paths, start=1):
        if count > 4:
            raise ValueError("at most four review receipts may be selected")
        receipt = load_review_receipt(path)
        if receipt["index"]["registry_root"] != str(registry):
            raise ValueError("review receipt registry mismatch")
        projection = prepare_review_presentation(
            path, review_summary_path=summaries.get(receipt["domain"]),
        )["projection"]
        if projection["receipt_hash"] != receipt["content_hash"]:
            raise ValueError("review receipt changed during projection")
        domain = projection["domain"]
        if domain in domains:
            raise ValueError("ambiguous review selection for domain")
        view = _pick(projection, _VIEW_FIELDS)
        for field in _OPTIONAL_VIEW_FIELDS:
            if field in projection:
                view[field] = projection[field]
        view["experiments"] = [_experiment(item) for item in projection["experiments"]]
        view["source_projection_hash"] = projection["content_hash"]
        domains[domain] = view
    if set(summaries) - set(domains):
        raise ValueError("review summary has no selected domain receipt")
    result = {"schema_version": SCHEMA, "visibility": "local_review_only", "read_only": True,
              "domains": dict(sorted(domains.items()))}
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > MAX_FEED_BYTES:
        raise ValueError("research feed exceeds local display budget; select smaller receipts")
    result["content_hash"] = hashlib.sha256(encoded).hexdigest()
    return result


def _script_json(value):
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    for character, escaped in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                               ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        text = text.replace(character, escaped)
    return text


def generate_local_research_html(
        receipt_paths, *, registry_root, review_summary_paths=None):
    """Return a local inspection artifact without reading live sports or writing files.

    This is not a deployment entry point. Hypotheses and metric labels are private
    free text; local-only does not mean anonymised or safe for public publication.
    """
    feed = build_research_feed(
        receipt_paths, registry_root=registry_root,
        review_summary_paths=review_summary_paths,
    )
    template = (_DASHBOARD / "static_template.html").read_text(encoding="utf-8")
    css = (_DASHBOARD / "frontend/src/index.css").read_text(encoding="utf-8")
    empty = {"meetings": [], "races": {}, "consensus": {}, "roi": {}, "sports_history": {}}
    return (template.replace("/* __CSS_PLACEHOLDER__ */", css)
            .replace("__GENERATED_TIME__", "本機研究快照 · 非公開部署")
            .replace('"__DATA_PLACEHOLDER__"', _script_json(empty))
            .replace('"__DEFAULT_WORKSPACE_PLACEHOLDER__"', '"research"')
            .replace('"__RESEARCH_PLACEHOLDER__"', _script_json(feed)))


def _absolute_path(value: str, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    return path


def _summary_paths(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        domain, separator, raw_path = value.partition("=")
        if (
            separator != "="
            or domain not in {"au", "hkjc", "tennis", "nba"}
            or domain in result
        ):
            raise ValueError("review summary must be one unique DOMAIN=/absolute/path")
        result[domain] = _absolute_path(raw_path, "review summary")
    return result


def write_local_research_html(output_path: Path, html: str) -> None:
    """Create one owner-only local artifact; never overwrite an existing review."""
    path = Path(output_path)
    if not path.is_absolute():
        raise ValueError("output must be an absolute path")
    parent = path.parent
    if not parent.is_dir():
        raise ValueError("output parent must already exist")
    if any(item.is_symlink() for item in (parent, *parent.parents)):
        raise ValueError("symlinked output parent is forbidden")
    raw = html.encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    try:
        offset = 0
        while offset < len(raw):
            offset += os.write(descriptor, raw[offset:])
        os.fsync(descriptor)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("local research output is not a regular file")
    finally:
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create one private, read-only local Wong Choi research Dashboard",
    )
    parser.add_argument("--registry-root", required=True)
    parser.add_argument("--receipt", action="append", required=True)
    parser.add_argument(
        "--review-summary",
        action="append",
        default=[],
        metavar="DOMAIN=/ABSOLUTE/PATH",
    )
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args(argv)
    registry_root = _absolute_path(arguments.registry_root, "registry root")
    receipts = [_absolute_path(value, "receipt") for value in arguments.receipt]
    output = _absolute_path(arguments.output, "output")
    html = generate_local_research_html(
        receipts,
        registry_root=registry_root,
        review_summary_paths=_summary_paths(arguments.review_summary),
    )
    write_local_research_html(output, html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
