#!/usr/bin/env python3
"""Audit Sportsbet source linkage and neutral/fallback coverage for AU scores."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from racing_engine.io_utils import write_json_atomic, write_text_atomic


def people_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def name_match(current: object, linked: object) -> bool:
    left, right = people_key(current), people_key(linked)
    return bool(left and right and (left == right or left.startswith(right) or right.startswith(left)))


def sample_bucket(value: object) -> str:
    try:
        rides = int(value or 0)
    except (TypeError, ValueError):
        rides = 0
    if rides >= 10:
        return "usable_10plus"
    if rides > 0:
        return "thin_1_9"
    return "absent"


def rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def class_family(value: object) -> str:
    text = str(value or "").upper()
    if "MAIDEN" in text or "MDN" in text:
        return "Maiden"
    if "BM" in text or "BENCHMARK" in text:
        return "Benchmark"
    if "GROUP" in text or "LISTED" in text or re.search(r"\bG[123]\b", text):
        return "Stakes/Listed"
    if "CLASS" in text or re.search(r"\bCL\s*\d", text):
        return "Class"
    return "Other"


def build_report(dataset: dict, feature_audit: dict | None = None) -> dict:
    races = dataset["races"]
    rows = [row for race in races for row in race["rows"]]
    total = len(rows)
    people = {}
    for kind in ("jockey", "trainer"):
        samples = Counter()
        linked = matched = 0
        model_sources = Counter()
        exact_60 = band = 0
        for row in rows:
            raw = row.get("raw_pre_race") or {}
            ly = raw.get(f"{kind}_ly") or {}
            samples[sample_bucket(ly.get("rides"))] += 1
            if ly:
                linked += 1
                matched += int(name_match(raw.get(kind), ly.get("name")))
            score = float((row.get("feature_scores") or {}).get(f"{kind}_score", 60.0))
            exact_60 += abs(score - 60.0) < 1e-9
            band += 58.0 <= score <= 62.0
            model_sources[(row.get("score_provenance") or {}).get(f"{kind}_score", "unknown")] += 1
        people[kind] = {
            "official_sample_counts": dict(samples),
            "official_sample_rates": {key: rate(value, total) for key, value in samples.items()},
            "linked_stat_rows": linked,
            "linked_name_match_rate": rate(matched, linked),
            "model_source_counts": dict(model_sources),
            "exact_60_rate": rate(exact_60, total),
            "band_58_62_rate": rate(band, total),
        }

    rating_sources = Counter()
    rating_by_class = defaultdict(Counter)
    for race in races:
        family = class_family((race.get("metadata") or {}).get("race_class"))
        for row in race["rows"]:
            source = (row.get("score_provenance") or {}).get("rating_score", "unknown")
            rating_sources[source] += 1
            rating_by_class[family][source] += 1

    jh_sources = Counter()
    jh_formal_rides = Counter()
    for row in rows:
        raw = row.get("raw_pre_race") or {}
        score = float((row.get("feature_scores") or {}).get("jockey_horse_fit_score", 60.0))
        jh_sources[(row.get("score_provenance") or {}).get("jockey_horse_fit_score", "unknown")] += 1
        if int(raw.get("current_jockey_formal_rides") or 0) > 0:
            jh_formal_rides["same_horse_formal_history"] += 1
        elif abs(score - 58.0) < 1e-9:
            jh_formal_rides["no_scoring_evidence_58"] += 1
        else:
            jh_formal_rides["other_contextual_evidence"] += 1

    track = Counter()
    for row in rows:
        raw = row.get("raw_pre_race") or {}
        track["track_record_present"] += bool(str(raw.get("track_stats_line") or "").strip())
        track["going_record_present"] += bool(str(raw.get("going_stats_line") or "").strip())
        state = (row.get("feature_evidence_state") or {}).get("track_score", "unknown")
        track[f"state_{state}"] += 1

    output = {
        "design": {
            "races": len(races),
            "horses": total,
            "sportsbet_people_minimum_sample": 10,
            "matching_contract": "punctuation-insensitive exact or unique prefix",
        },
        "people": people,
        "rating": {
            "source_counts": dict(rating_sources),
            "source_rates": {key: rate(value, total) for key, value in rating_sources.items()},
            "by_race_class": {key: dict(value) for key, value in sorted(rating_by_class.items())},
        },
        "jockey_horse_fit": {
            "source_counts": dict(jh_sources),
            "evidence_counts": dict(jh_formal_rides),
            "evidence_rates": {key: rate(value, total) for key, value in jh_formal_rides.items()},
        },
        "track": {
            "counts": dict(track),
            "rates": {key: rate(value, total) for key, value in track.items()},
        },
    }
    if feature_audit:
        output["neutral_value_summary"] = {
            key: {
                name: feature_audit["features"][key].get(name)
                for name in (
                    "mean", "median", "stddev", "min", "max", "exact_60_rate",
                    "band_58_62_rate", "missing_or_fallback_rate",
                    "within_race_auc_all", "within_race_auc_terminal", "role", "status",
                )
            }
            for key in (
                "jockey_score", "trainer_score", "jockey_horse_fit_score",
                "rating_score", "track_score", "class_score", "weight_score",
                "formline_score",
            )
        }
    return output


def render_markdown(report: dict) -> str:
    total = report["design"]["horses"]
    lines = [
        "# AU Sportsbet Source Coverage Audit",
        "",
        f"Corpus: {report['design']['races']} races / {total:,} horses.",
        "",
        "## Trainer / jockey linkage",
        "",
        "| Person | usable ≥10 | thin 1–9 | absent | linked-name match | exact 60 | 58–62 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for kind, label in (("jockey", "Jockey"), ("trainer", "Trainer")):
        item = report["people"][kind]
        rates = item["official_sample_rates"]
        lines.append(
            f"| {label} | {pct(rates.get('usable_10plus', 0))} | "
            f"{pct(rates.get('thin_1_9', 0))} | {pct(rates.get('absent', 0))} | "
            f"{pct(item['linked_name_match_rate'])} | {pct(item['exact_60_rate'])} | "
            f"{pct(item['band_58_62_rate'])} |"
        )
    lines.extend(["", "Model provenance:"])
    for kind in ("jockey", "trainer"):
        values = report["people"][kind]["model_source_counts"]
        lines.append(f"- {kind}: " + ", ".join(f"{key}={value}" for key, value in values.items()))

    lines.extend([
        "",
        "## Rating source",
        "",
        "| Source | Horses | Rate |",
        "|---|---:|---:|",
    ])
    for key, value in report["rating"]["source_counts"].items():
        lines.append(f"| {key} | {value:,} | {pct(value / total)} |")
    lines.extend([
        "",
        "Official ratings are field-relative. Missing-rating races use the validated "
        "class proxy, optionally blended with a handicap-only field-relative weight proxy; "
        "WFA/set-weight races refuse that proxy.",
        "",
        "## Jockey/horse-fit evidence",
        "",
    ])
    for key, value in report["jockey_horse_fit"]["evidence_counts"].items():
        lines.append(f"- {key}: {value:,} ({pct(value / total)})")
    lines.extend([
        "",
        "## Track / going evidence",
        "",
        f"- Same-track record present: {pct(report['track']['rates'].get('track_record_present', 0))}",
        f"- Going record present: {pct(report['track']['rates'].get('going_record_present', 0))}",
        "- `track_score` is one leaf combining same-track and today's going history; "
        "the matrix label is its transformed parent, not a second vote.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-json", type=Path, required=True)
    parser.add_argument("--feature-audit-json", type=Path)
    parser.add_argument("--output-json", type=Path, default=Path("/private/tmp/au_source_coverage.json"))
    parser.add_argument("--output-md", type=Path, default=Path("/private/tmp/au_source_coverage.md"))
    args = parser.parse_args()
    dataset = json.loads(args.dataset_json.read_text(encoding="utf-8"))
    feature = json.loads(args.feature_audit_json.read_text(encoding="utf-8")) if args.feature_audit_json else None
    report = build_report(dataset, feature)
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render_markdown(report))
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
