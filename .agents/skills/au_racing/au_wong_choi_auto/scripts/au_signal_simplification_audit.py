#!/usr/bin/env python3
"""Canonical AU matrix/leaf simplification audit.

This is deliberately a thin companion to :mod:`au_eval`.  It generates
ablation hypotheses, but it does not own a second split, metric contract or
promotion rule.  The input is the current-runtime JSON snapshot produced by
``au_runtime_failure_audit.py --dataset-json``.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_eval import (  # noqa: E402
    baseline_report,
    compare,
    configured_scorer,
    default_scorer,
    load_races,
    verdict_dict,
)
from io_utils import write_json_atomic, write_text_atomic  # noqa: E402
from matrix_mapper import MATRIX_FORMULAS, map_features_to_matrix_scores  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402


ACTIVE_MATRICES = tuple(
    key for key, weight in MATRIX_WEIGHTS.items() if float(weight) > 0
)
ACTIVE_LEAVES = tuple(dict.fromkeys(
    leaf
    for matrix in ACTIVE_MATRICES
    for leaf, _weight in MATRIX_FORMULAS[matrix]
))
GROUPS = {
    "performance_core": (
        "form_score", "performance_quality_score", "pace_figure_score",
    ),
    "people": (
        "jockey_score", "trainer_score", "jockey_horse_fit_score",
    ),
    "race_context": ("pace_map_score", "track_score"),
}


def neutral_matrix_scorer(matrix_key: str):
    """Set one final matrix dimension to neutral while preserving all else."""
    def scorer(row):
        matrices = map_features_to_matrix_scores(row["features"])
        matrices[matrix_key] = 60.0
        return sum(
            matrices.get(key, 60.0) * weight
            for key, weight in MATRIX_WEIGHTS.items()
        ) + float(row["wet"] or 0.0)
    return scorer


def build_audit(races, holdout=0.15):
    variants = []
    for key in ACTIVE_MATRICES:
        variants.append((f"drop_matrix:{key}", neutral_matrix_scorer(key)))
    for leaf in ACTIVE_LEAVES:
        variants.append((
            f"drop_leaf:{leaf}",
            configured_scorer(leaf_overrides={leaf: 60.0}),
        ))
    for name, leaves in GROUPS.items():
        active = {leaf: 60.0 for leaf in leaves if leaf in ACTIVE_LEAVES}
        if active:
            variants.append((
                f"drop_group:{name}",
                configured_scorer(leaf_overrides=active),
            ))

    verdicts = []
    for label, scorer in variants:
        verdict = compare(
            races,
            default_scorer,
            scorer,
            label=label,
            holdout=holdout,
        )
        verdicts.append(verdict_dict(verdict))
        print(verdict)
        print()
    return {
        "baseline": baseline_report(races, holdout),
        "design": {
            "active_matrices": list(ACTIVE_MATRICES),
            "active_leaves": list(ACTIVE_LEAVES),
            "interpretation": (
                "Positive delta means neutralising the signal improved ranking. "
                "Only au_eval's whole-date terminal bootstrap can promote removal."
            ),
        },
        "verdicts": verdicts,
    }


def render_markdown(report: dict) -> str:
    design = report["baseline"]["design"]
    lines = [
        "# AU Signal Simplification Audit",
        "",
        f"- Archive / development / terminal: {design['races']} / "
        f"{design['development_races']} / {design['terminal_holdout_races']}",
        "- Split unit: complete race date; one date is never divided.",
        "- Removal ships only when development Top-5 AUC is non-negative and "
        "the terminal paired-bootstrap 95% interval is wholly positive.",
        "- Gold / Good / Pass remain reported context, never an alternate gate.",
        "",
        "| Variant | Dev Top5 AUC Δ | Terminal Δ | 95% CI | Ship | Reason |",
        "|---|---:|---:|---:|:---:|---|",
    ]
    for row in report["verdicts"]:
        lo, hi = row["top_hold_ci"]
        lines.append(
            f"| {row['label']} | {row['top_dev']:+.4f} | "
            f"{row['top_hold']:+.4f} | [{lo:+.4f}, {hi:+.4f}] | "
            f"{'YES' if row['ship'] else 'NO'} | {row['reason']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-json", "--dataset", dest="dataset_json",
        type=Path, required=True,
        help="Current-runtime JSON dataset (legacy flat CSV is intentionally unsupported).",
    )
    parser.add_argument(
        "--output-json", type=Path,
        default=Path("/private/tmp/au_signal_simplification_audit.json"),
    )
    parser.add_argument(
        "--output-md", type=Path,
        default=Path("/private/tmp/au_signal_simplification_audit.md"),
    )
    parser.add_argument("--holdout-fraction", type=float, default=0.15)
    args = parser.parse_args()

    races = load_races(args.dataset_json)
    if not races:
        raise SystemExit("No aligned runtime races in dataset.")
    report = build_audit(races, args.holdout_fraction)
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render_markdown(report))
    print(f"Races: {len(races)}")
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
