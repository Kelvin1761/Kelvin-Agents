#!/usr/bin/env python3
"""Canonical test of whether a rebuilt AU 賽績線 deserves ranking weight.

This is deliberately a matrix-level ability test, not a rank-3/rank-4 rerank.
Every candidate competes against the live six-dimension score on the same
whole-date development/terminal split used by :mod:`au_eval`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_eval import compare, default_scorer, load_races, verdict_dict  # noqa: E402
from io_utils import write_json_atomic, write_text_atomic  # noqa: E402
from matrix_mapper import map_features_to_matrix_scores  # noqa: E402


SHARES = (0.01, 0.02, 0.05, 0.10)


def _line_score(row: dict, variant: str) -> float:
    features = row["features"]
    if variant == "opponent_followup":
        # Existing Sportsbet opponent-follow-up implementation.  It is kept
        # report-only today, so this is the clean test of restoring weight.
        return float(map_features_to_matrix_scores(features)["form_line"])
    if variant == "normalised_recent_quality":
        # Reconstructed line: recent finishing consistency plus margin/prize-
        # strength performance quality and a small class-context component.
        # All three inputs are strictly pre-race and already normalised to the
        # engine's 0-100 scale.  This avoids treating a raw string such as
        # ``3-7-2-5`` as comparable across different races.
        return (
            0.45 * float(features.get("form_score", 60.0))
            + 0.40 * float(features.get("performance_quality_score", 60.0))
            + 0.15 * float(features.get("class_score", 60.0))
        )
    raise ValueError(f"Unknown formline variant: {variant}")


def formline_scorer(variant: str, share: float):
    """Blend one formline definition into the overall ability matrix."""
    if not 0.0 < share < 1.0:
        raise ValueError("share must be between zero and one")

    def scorer(row: dict) -> float:
        wet = float(row.get("wet") or 0.0)
        current_ability = default_scorer(row) - wet
        return (1.0 - share) * current_ability + share * _line_score(row, variant) + wet

    return scorer


def render_markdown(report: dict) -> str:
    lines = [
        "# AU 賽績線 Recovery Audit",
        "",
        "呢個 audit 測試整體 scoring matrix；冇鎖 Top 2，亦冇只 rerank 第 3/4 位。",
        "",
        "- `opponent_followup`: 現有 Sportsbet 對手後續賽績線。",
        "- `normalised_recent_quality`: 45% 近績 + 40% margin/prize-strength 表現質素 + 15% 級數背景。",
        "- 所有候選只可用 whole-date development/terminal canonical gate 升級。",
        "",
        "| Variant | Share | Dev Top-5 AUC Δ | Terminal Δ | 95% CI | 場數指標摘要 | Ship |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for item in report["candidates"]:
        verdict = item["verdict"]
        counts = verdict.get("counts") or {}
        context = ", ".join(
            f"{key} {value:+.2f}pp"
            for key, value in counts.items()
            if key in {"gold", "good_positional", "pass", "champion", "winner_in_top3"}
        )
        ci = verdict["top_hold_ci"]
        lines.append(
            f"| {item['variant']} | {item['share']:.0%} | "
            f"{verdict['top_dev']:+.5f} | {verdict['top_hold']:+.5f} | "
            f"[{ci[0]:+.5f}, {ci[1]:+.5f}] | {context} | "
            f"{'YES' if verdict['ship'] else 'NO'} |"
        )
    lines.extend([
        "",
        "## 判決",
        "",
        report["conclusion"],
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-json", type=Path, required=True)
    parser.add_argument(
        "--output-json", type=Path,
        default=Path("/private/tmp/au_formline_recovery.json"),
    )
    parser.add_argument(
        "--output-md", type=Path,
        default=Path("/private/tmp/au_formline_recovery.md"),
    )
    args = parser.parse_args()

    races = load_races(args.dataset_json)
    candidates = []
    for variant in ("opponent_followup", "normalised_recent_quality"):
        for share in SHARES:
            verdict = compare(
                races,
                default_scorer,
                formline_scorer(variant, share),
                label=f"{variant} @ {share:.0%}",
            )
            candidates.append({
                "variant": variant,
                "share": share,
                "verdict": verdict_dict(verdict),
            })

    shipped = [item for item in candidates if item["verdict"]["ship"]]
    conclusion = (
        "有候選通過 canonical gate；仍需檢查 leakage／cohort stability 先可採用。"
        if shipped else
        "冇候選同時做到 development 非負及 terminal 95% CI 全正；賽績線維持 report-only，"
        "唔將重複或不穩定訊號加入排名。"
    )
    report = {
        "design": {
            "races": len(races),
            "dataset": str(args.dataset_json),
            "scope": "whole scoring matrix; no slot-specific rerank",
            "shares": list(SHARES),
        },
        "candidates": candidates,
        "conclusion": conclusion,
    }
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render_markdown(report))
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
