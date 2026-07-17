#!/usr/bin/env python3
"""Step-6 fixed-candidate shadow test for the HKJC rating matrix.

The candidates are deliberately few and fixed before measurement.  They use
the speed-only proxy instead of the stored sectional score, keep the existing
race-shape weight frozen, preserve the current debut formula, and do not use
rank_score, micro tie-breaks, blind swaps, odds, market data or pace.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from hkjc_rating_matrix_audit import (
    DEFAULT_ARCHIVE,
    DEFAULT_MANIFEST,
    DEBUT_MATRIX_WEIGHTS,
    MATRIX_WEIGHTS,
    build_horse_rows,
    group_races,
)


ROOT = Path(__file__).resolve().parents[1]


CANDIDATES: dict[str, dict[str, Any]] = {
    "baseline_pure_matrix": {
        "label": "現行純矩陣基準",
        "sectional_source": "sectional",
        "weights": dict(MATRIX_WEIGHTS),
        "note": "只作比較；stored sectional含going。",
    },
    "speed_only_substitution": {
        "label": "純段速直接替換",
        "sectional_source": "speed_only",
        "weights": dict(MATRIX_WEIGHTS),
        "note": "只將sectional輸入改為speed-only，其餘權重不變。",
    },
    "speed_stability_shift": {
        "label": "純段速＋穩定性小幅增權",
        "sectional_source": "speed_only",
        "weights": {
            "sectional": 0.1849,
            "trainer_signal": 0.2209,
            "stability": 0.1447,
            "race_shape": 0.2560,
            "class_advantage": 0.1335,
            "horse_health": 0.0100,
            "form_line": 0.0499,
        },
        "note": "由弱健康及弱賽績線合共轉5.28%去穩定性；race-shape權重凍結。",
    },
    "speed_balanced_context": {
        "label": "純段速＋穩定性／級數平衡",
        "sectional_source": "speed_only",
        "weights": {
            "sectional": 0.1849,
            "trainer_signal": 0.2209,
            "stability": 0.1200,
            "race_shape": 0.2560,
            "class_advantage": 0.1581,
            "horse_health": 0.0100,
            "form_line": 0.0500,
        },
        "note": "由健康／賽績線轉5.27%，分配去穩定性及級數；race-shape權重凍結。",
    },
    "speed_distance_5pct": {
        "label": "純段速＋5%路程context",
        "sectional_source": "speed_only",
        "weights": {
            "sectional": 0.1849,
            "trainer_signal": 0.2209,
            "stability": 0.0919,
            "race_shape": 0.2560,
            "class_advantage": 0.1335,
            "horse_health": 0.0100,
            "form_line": 0.0527,
            "distance_context": 0.0500,
        },
        "note": "由健康／賽績線轉5%去路程context；race-shape權重凍結。",
    },
}


def validate_candidates() -> None:
    for name, candidate in CANDIDATES.items():
        total = sum(candidate["weights"].values())
        if not math.isclose(total, sum(MATRIX_WEIGHTS.values()), abs_tol=1e-9):
            raise ValueError(f"{name} weights total {total:.8f}, expected {sum(MATRIX_WEIGHTS.values()):.8f}")


def score_row(row: dict[str, Any], candidate: dict[str, Any]) -> float:
    # Step 6 explicitly preserves the live debut formula; it is not part of
    # this shadow experiment.
    if row["is_debut"]:
        return round(
            sum(float(row[key]) * weight for key, weight in DEBUT_MATRIX_WEIGHTS.items()),
            4,
        )
    total = 0.0
    for dimension, weight in candidate["weights"].items():
        source = candidate["sectional_source"] if dimension == "sectional" else dimension
        total += float(row[source]) * weight
    return round(total, 4)


def add_scores(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        for name, candidate in CANDIDATES.items():
            row[name] = score_row(row, candidate)
        if abs(row["baseline_pure_matrix"] - row["pure_matrix_total"]) > 1e-6:
            raise ValueError(
                f"baseline mismatch {row['meeting']} R{row['race_number']} H{row['horse_number']}: "
                f"{row['baseline_pure_matrix']} != {row['pure_matrix_total']}"
            )


def temporal_subsets(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    archive_meetings = sorted({row["meeting"] for row in rows if row["dataset"] == "archive"})
    cut = math.floor(len(archive_meetings) * 0.70)
    development = set(archive_meetings[:cut])
    temporal = set(archive_meetings[cut:])
    return {
        "all": rows,
        "archive_development": [
            row for row in rows if row["dataset"] == "archive" and row["meeting"] in development
        ],
        "archive_temporal_holdout": [
            row for row in rows if row["dataset"] == "archive" and row["meeting"] in temporal
        ],
        "independent_recent": [row for row in rows if row["dataset"] == "independent_recent"],
        "external_2026_07_15": [row for row in rows if row["dataset"] == "external_2026_07_15"],
    }


def within_race_auc(races: dict[tuple[str, str, int], list[dict[str, Any]]], score_key: str) -> float:
    wins = 0.0
    pairs = 0
    for race_rows in races.values():
        positives = [row for row in race_rows if row["is_top3"]]
        negatives = [row for row in race_rows if not row["is_top3"]]
        for positive in positives:
            for negative in negatives:
                pairs += 1
                if positive[score_key] > negative[score_key]:
                    wins += 1.0
                elif positive[score_key] == negative[score_key]:
                    wins += 0.5
    return round(wins / pairs, 4) if pairs else 0.5


def selections(
    races: dict[tuple[str, str, int], list[dict[str, Any]]], score_key: str
) -> dict[tuple[str, str, int], dict[str, Any]]:
    output = {}
    for key, race_rows in races.items():
        ranked = sorted(race_rows, key=lambda row: (-row[score_key], row["horse_number"]))
        top2 = ranked[:2]
        output[key] = {
            "top2": [row["horse_number"] for row in top2],
            "top2_names": [row["horse_name"] for row in top2],
            "hits": sum(row["is_top3"] for row in top2),
            "winner": int(any(row["is_winner"] for row in top2)),
        }
    return output


def candidate_metrics(
    races: dict[tuple[str, str, int], list[dict[str, Any]]],
    score_key: str,
    baseline: dict[tuple[str, str, int], dict[str, Any]],
) -> dict[str, Any]:
    chosen = selections(races, score_key)
    distribution = Counter(item["hits"] for item in chosen.values())
    total_hits = sum(item["hits"] for item in chosen.values())
    winners = sum(item["winner"] for item in chosen.values())
    total = len(chosen)
    changed = [key for key in chosen if set(chosen[key]["top2"]) != set(baseline[key]["top2"])]
    return {
        "races": total,
        "top3_auc": within_race_auc(races, score_key),
        "top2_hit_distribution": {str(hit): distribution.get(hit, 0) for hit in (0, 1, 2)},
        "total_top2_hits": total_hits,
        "hits_per_race": round(total_hits / total, 4) if total else 0.0,
        "winner_top2": winners,
        "winner_top2_rate": round(winners / total * 100, 1) if total else 0.0,
        "top2_set_changes": len(changed),
        "hit_helped": sum(chosen[key]["hits"] > baseline[key]["hits"] for key in changed),
        "hit_harmed": sum(chosen[key]["hits"] < baseline[key]["hits"] for key in changed),
        "winner_helped": sum(chosen[key]["winner"] > baseline[key]["winner"] for key in changed),
        "winner_harmed": sum(chosen[key]["winner"] < baseline[key]["winner"] for key in changed),
        "zero_to_positive": sum(
            baseline[key]["hits"] == 0 and chosen[key]["hits"] > 0 for key in chosen
        ),
        "one_to_two": sum(baseline[key]["hits"] == 1 and chosen[key]["hits"] == 2 for key in chosen),
        "one_to_zero": sum(baseline[key]["hits"] == 1 and chosen[key]["hits"] == 0 for key in chosen),
        "two_to_lower": sum(baseline[key]["hits"] == 2 and chosen[key]["hits"] < 2 for key in chosen),
    }


def build_results(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    subsets = temporal_subsets(rows)
    results: dict[str, Any] = {}
    changes: list[dict[str, Any]] = []
    for subset, subset_rows in subsets.items():
        races = group_races(subset_rows)
        baseline = selections(races, "baseline_pure_matrix")
        results[subset] = {}
        for name in CANDIDATES:
            results[subset][name] = candidate_metrics(races, name, baseline)
        if subset != "all":
            continue
        for name in CANDIDATES:
            if name == "baseline_pure_matrix":
                continue
            chosen = selections(races, name)
            for key in sorted(races):
                if set(chosen[key]["top2"]) == set(baseline[key]["top2"]):
                    continue
                changes.append(
                    {
                        "candidate": name,
                        "dataset": key[0],
                        "meeting": key[1],
                        "race_number": key[2],
                        "baseline_top2": "-".join(map(str, baseline[key]["top2"])),
                        "candidate_top2": "-".join(map(str, chosen[key]["top2"])),
                        "baseline_hits": baseline[key]["hits"],
                        "candidate_hits": chosen[key]["hits"],
                        "baseline_winner": baseline[key]["winner"],
                        "candidate_winner": chosen[key]["winner"],
                    }
                )
    return results, changes


def advancement_gate(results: dict[str, Any], candidate: str) -> dict[str, Any]:
    checks = {}
    positive = False
    for subset in ("archive_development", "archive_temporal_holdout", "independent_recent"):
        base = results[subset]["baseline_pure_matrix"]
        row = results[subset][candidate]
        hit_delta = row["total_top2_hits"] - base["total_top2_hits"]
        winner_delta = row["winner_top2"] - base["winner_top2"]
        zero_delta = row["top2_hit_distribution"]["0"] - base["top2_hit_distribution"]["0"]
        checks[subset] = {
            "top2_hit_delta": hit_delta,
            "winner_top2_delta": winner_delta,
            "zero_hit_delta": zero_delta,
            "non_negative": hit_delta >= 0 and winner_delta >= 0 and zero_delta <= 0,
        }
        positive = positive or hit_delta > 0 or winner_delta > 0 or zero_delta < 0
    advances = all(row["non_negative"] for row in checks.values()) and positive
    return {"advances_to_step7": advances, "checks": checks}


def write_outputs(
    results: dict[str, Any],
    changes: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    output_prefix: Path,
) -> None:
    gates = {
        name: advancement_gate(results, name)
        for name in CANDIDATES
        if name != "baseline_pure_matrix"
    }
    payload = {
        "method": {
            "fixed_candidates_no_grid_search": True,
            "preserves_debut_formula": True,
            "uses_rank_score": False,
            "uses_micro_tiebreak": False,
            "uses_blind_swap": False,
            "uses_odds_market_pace": False,
            "candidate_sectional_source": "speed_only",
            "race_shape_weight": "frozen at baseline; not optimized in Step 6",
            "archive_split": "first 70% meetings development; last 30% temporal holdout",
        },
        "candidates": CANDIDATES,
        "results": results,
        "advancement_gate": gates,
        "errors": errors,
    }
    json_path = output_prefix.with_suffix(".json")
    csv_path = output_prefix.with_suffix(".csv")
    changes_path = output_prefix.with_name(output_prefix.name + "_changes").with_suffix(".csv")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    metric_fields = [
        "subset", "candidate", "races", "top3_auc", "zero_hit", "one_hit", "two_hit",
        "total_top2_hits", "hits_per_race", "winner_top2", "winner_top2_rate",
        "top2_set_changes", "hit_helped", "hit_harmed", "winner_helped", "winner_harmed",
        "zero_to_positive", "one_to_two", "one_to_zero", "two_to_lower",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=metric_fields)
        writer.writeheader()
        for subset, candidates in results.items():
            for name, row in candidates.items():
                distribution = row["top2_hit_distribution"]
                writer.writerow(
                    {
                        "subset": subset,
                        "candidate": name,
                        **{key: value for key, value in row.items() if key != "top2_hit_distribution"},
                        "zero_hit": distribution["0"],
                        "one_hit": distribution["1"],
                        "two_hit": distribution["2"],
                    }
                )
    change_fields = [
        "candidate", "dataset", "meeting", "race_number", "baseline_top2", "candidate_top2",
        "baseline_hits", "candidate_hits", "baseline_winner", "candidate_winner",
    ]
    with changes_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=change_fields)
        writer.writeheader()
        writer.writerows(changes)

    lines = [
        "# HKJC Wong Choi Step 6 — Rating Matrix固定候選Shadow",
        "",
        "## 方法鎖定",
        "",
        "- 四個候選在睇結果前固定，無grid search、無逐場調權重。",
        "- 候選全部用speed-only取代含going嘅stored sectional；初出馬沿用現有debut公式。",
        "- race-shape權重凍結，不按其含draw訊號作調權；本步只重配健康／賽績線至穩定性、級數或路程context。",
        "- 無rank_score、micro tie-break、第二／第三選盲換、賠率、市場或pace。",
        "- Archive按賽日先後70／30切development與時間留後；近期獨立集及2026-07-15另列。",
        "",
        "## 候選定義",
        "",
        "| 候選 | 說明 | 權重總和 |",
        "|---|---|---:|",
    ]
    for name, candidate in CANDIDATES.items():
        lines.append(
            f"| {name} | {candidate['note']} | {sum(candidate['weights'].values()):.4f} |"
        )
    for subset in (
        "archive_development",
        "archive_temporal_holdout",
        "independent_recent",
        "external_2026_07_15",
        "all",
    ):
        lines.extend(
            [
                "",
                f"## {subset}",
                "",
                "| 候選 | 場數 | 0／1／2 hit | Top2總hits | Δhits | 頭馬Top2 | Δ頭馬 | AUC | 名單變動 | 救0-hit | 1→2 | 1→0 |",
                "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        base = results[subset]["baseline_pure_matrix"]
        for name, row in results[subset].items():
            dist = row["top2_hit_distribution"]
            lines.append(
                f"| {name} | {row['races']} | {dist['0']}/{dist['1']}/{dist['2']} | "
                f"{row['total_top2_hits']} | {row['total_top2_hits'] - base['total_top2_hits']:+d} | "
                f"{row['winner_top2']} | {row['winner_top2'] - base['winner_top2']:+d} | "
                f"{row['top3_auc']:.3f} | {row['top2_set_changes']} | {row['zero_to_positive']} | "
                f"{row['one_to_two']} | {row['one_to_zero']} |"
            )
    lines.extend(
        [
            "",
            "## Step 7入閘條件",
            "",
            "候選要在development、archive時間留後及近期獨立集同時滿足：Top2總hits不跌、頭馬Top2不跌、0-hit不增；三段之中至少一項有改善。07-15只有9場，只作外部方向檢查，不作硬閘。",
            "",
            "| 候選 | Development Δhits/Δ頭馬/Δ0-hit | Holdout | 近期獨立 | 入Step 7 |",
            "|---|---|---|---|---|",
        ]
    )
    for name, gate in gates.items():
        cells = []
        for subset in ("archive_development", "archive_temporal_holdout", "independent_recent"):
            row = gate["checks"][subset]
            cells.append(
                f"{row['top2_hit_delta']:+d}/{row['winner_top2_delta']:+d}/{row['zero_hit_delta']:+d}"
            )
        lines.append(
            f"| {name} | {cells[0]} | {cells[1]} | {cells[2]} | "
            f"{'是' if gate['advances_to_step7'] else '否'} |"
        )
    advancing = [name for name, gate in gates.items() if gate["advances_to_step7"]]
    lines.extend(
        [
            "",
            "## Step 6結論",
            "",
            f"- 可進入Step 7候選：{', '.join(advancing) if advancing else '無'}",
            f"- 全體Top2名單變動明細：{len(changes)}行（不同候選可重複同一場）。",
            f"- 資料錯誤：{len(errors)}。",
            "- 本步只係shadow診斷，無修改正式HKJC scoring engine。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "json": str(json_path),
                "csv": str(csv_path),
                "changes": str(changes_path),
                "report": str(report_path),
                "advancing": advancing,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=ROOT / "scratch" / "hkjc_matrix_shadow_candidates",
    )
    args = parser.parse_args()
    validate_candidates()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows, errors = build_horse_rows(manifest, args.archive)
    add_scores(rows)
    results, changes = build_results(rows)
    write_outputs(results, changes, errors, args.output_prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
