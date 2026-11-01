"""Exhaustive historical rule plumbing audit; no outcome fitting or live writes."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import platform
import re
import sys

from tennis_wc.research_kernel.rule_kernel import SetRule, match_win_probability
from tennis_wc.research_kernel.rule_resolver import DRAW, UnsupportedRules, resolve_slam_rules

EVENTS = ["ausopen", "frenchopen", "wimbledon", "usopen"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_rule(event, year):
    # Independent statement of the source transitions, not a registry lookup.
    if event == "ausopen":
        return SetRule(None, None) if year < 2019 else SetRule(6, 10)
    if event == "frenchopen":
        return SetRule(None, None) if year < 2022 else SetRule(6, 10)
    if event == "wimbledon":
        return SetRule(None, None) if year < 2019 else (SetRule(12, 7) if year < 2022 else SetRule(6, 10))
    return SetRule(6, 7) if year < 2022 else SetRule(6, 10)


def audit_archive(source_manifest, matches, output):
    """Check metadata-to-resolver routing, not point replay or training eligibility."""
    capture = json.loads(source_manifest.read_text())
    receipts = [r for r in capture["files"] if r["path"].endswith("-matches.csv")]
    if len(capture["files"]) != 98 or len(receipts) != 49:
        raise ValueError("the complete pinned 49-event capture is required")
    frozen = json.loads(matches.with_name("artifact_manifest.json").read_text())
    if sha(matches) != frozen[matches.name]:
        raise ValueError("frozen archive audit fingerprint mismatch")
    tables = {}
    for receipt in receipts:
        path = Path(receipt["local_path"])
        if sha(path) != receipt["sha256"]:
            raise ValueError("captured metadata fingerprint mismatch")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            tables[str(path)] = list(csv.DictReader(stream))
    counts = Counter()
    with matches.open() as stream, (output/"archive-routing.jsonl").open("w") as target:
        for line in stream:
            row = json.loads(line)
            result = dict(match_id=row.get("match_id"), original_reason=row.get("reason"),
                          original_training_eligible=row.get("training_eligible"), training_eligibility_changed=False)
            try:
                locator = row["metadata_locator"]
                offset = locator["csv_line"] - 2
                if type(offset) is not int or offset < 0:
                    raise ValueError("invalid metadata line locator")
                metadata = tables[locator["file"]][offset]
                year, event = row["year"], row["event"]
                code = metadata.get("match_num", "")
                match = re.fullmatch(r"(1|2|MS|WS)([1-7])\d{2}", code)
                if not match:
                    raise ValueError("unknown main-draw singles code")
                if (metadata.get("year") != str(year) or metadata.get("slam") != event
                        or metadata.get("match_id") != row["match_id"]
                        or row["match_id"] != f"{year}-{event}-{code}"):
                    raise ValueError("metadata identity conflict")
                tour = "ATP" if match[1] in {"1", "MS"} else "WTA"
                declared = metadata.get("event_name", "").casefold()
                allowed = {"men's singles", "event_ms"} if tour == "ATP" else {"women's singles", "event_ws"}
                if declared and declared not in allowed:
                    raise ValueError("metadata draw conflict")
                rules = resolve_slam_rules(event=event, year=year, tour=tour, draw=DRAW)
                assert rules.best_of == (5 if tour == "ATP" else 3)
                assert rules.deciding == expected_rule(event, year)
                result.update(status="ROUTED_RULES_ONLY", rule_id=rules.rule_id, tour=tour,
                              format_evidence="explicit_metadata" if declared else "match_code_only")
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                result.update(status="HELD", error=str(exc))
            counts[result["status"]] += 1
            target.write(json.dumps(result)+"\n")
    return dict(counts=counts, source_manifest_sha256=sha(source_manifest),
                frozen_matches_sha256=sha(matches), verified_metadata_files=49,
                point_files_replayed=False, training_eligibility_changed=False,
                qualification="RULE_ROUTING_ONLY_NOT_FIXTURE_OR_TRAINING_CERTIFICATION")


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--archive-matches", type=Path)
    args = parser.parse_args()
    if bool(args.source_manifest) != bool(args.archive_matches):
        parser.error("both archive inputs must be supplied together")
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    source_paths = [Path(__file__).resolve(), root/"pyproject.toml",
                    *sorted((root/"src/tennis_wc/research_kernel").glob("*.py")),
                    root/"src/tennis_wc/research_kernel/slam_rules.json"]
    sources = {str(p.relative_to(root)): sha(p) for p in source_paths}
    metadata = dict(started_utc=datetime.now(timezone.utc).isoformat(), argv=sys.argv,
                    python=sys.version, platform=platform.platform(), source_sha256=sources,
                    protocol_sha256="7a3eae421474e4a04deaf80706580efe0f87183f49af3552afd8d32faeb2d9e2")
    (args.output/"metadata.json").write_text(json.dumps(metadata, indent=2)+"\n")
    contexts, comparisons = [], []
    for event, year, tour in itertools.product(EVENTS, range(2011, 2025), ["ATP", "WTA"]):
        context = dict(event=event, year=year, tour=tour)
        if event == "wimbledon" and year == 2020:
            try:
                resolve_slam_rules(**context, draw=DRAW)
            except UnsupportedRules as exc:
                contexts.append(dict(**context, status="CANCELLED", error=str(exc)))
                continue
            raise AssertionError("cancelled event accepted")
        rules = resolve_slam_rules(**context, draw=DRAW)
        best = 5 if tour == "ATP" else 3
        expected = expected_rule(event, year)
        assert rules.deciding == expected and rules.ordinary == SetRule(6, 7) and rules.best_of == best
        contexts.append(dict(**context, status="SUPPORTED", resolved=asdict(rules)))
        for a, b, first in itertools.product([.45, .60, .75], [.45, .60, .75], [True, False]):
            actual = rules.match_probability(a, b, first_a=first)
            direct = match_win_probability(a, b, first_a=first, best_of=best,
                                           ordinary_rule=SetRule(6, 7), deciding_rule=expected)
            error = abs(actual-direct)
            assert error <= 1e-8
            comparisons.append(dict(**context, p_a=a, p_b=b, first_a=first,
                                    resolved_probability=actual, direct_probability=direct, abs_error=error))
    assert len(contexts) == 112 and len(comparisons) == 1980
    report = dict(contexts=contexts, comparisons=comparisons, supported=110, cancelled=2,
                  max_abs_error=max(r["abs_error"] for r in comparisons),
                  qualification="RESOLVER_PLUMBING_ONLY", production_changed=False)
    if args.archive_matches:
        report["archive"] = audit_archive(args.source_manifest, args.archive_matches, args.output)
    report["source_unchanged"] = all(sha(p) == sources[str(p.relative_to(root))] for p in source_paths)
    assert report["source_unchanged"]
    (args.output/"result.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"contexts", "comparisons"}}, indent=2))


if __name__ == "__main__":
    main()
