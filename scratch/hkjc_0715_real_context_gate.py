#!/usr/bin/env python3
"""Gate real-context normalized sectional history on the 2026-07-15 snapshot."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ENGINE = (
    ROOT / ".agents" / "skills" / "hkjc_racing"
    / "hkjc_wong_choi_auto" / "scripts" / "racing_engine"
)
SHARED = ROOT / ".agents" / "skills" / "shared_racing"
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(SHARED))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402


DATASET = ROOT / "scratch" / "hkjc_ranking_dataset_2026_07_15_current.csv"
FEATURES = ROOT / "scratch" / "hkjc_0715_normalized_features.json"
JSON_OUT = ROOT / "scratch" / "hkjc_0715_real_context_gate.json"
REPORT_OUT = ROOT / "scratch" / "hkjc_0715_real_context_gate_report.md"


def relative(values: dict[int, float | None], lower_is_better: bool = True) -> dict[int, float]:
    valid = {horse: value for horse, value in values.items() if value is not None}
    output = {}
    for horse, value in values.items():
        if value is None or len(valid) < 2:
            output[horse] = 60.0
            continue
        others = [other for other_horse, other in valid.items() if other_horse != horse]
        worse = sum((other > value) if lower_is_better else (other < value) for other in others)
        ties = sum(other == value for other in others)
        output[horse] = 45.0 + 30.0 * (worse + 0.5 * ties) / len(others)
    return output


def rank_race(rows: pd.DataFrame, signal: str, alpha: float) -> list[dict]:
    l400 = {
        int(row.horse_number): (
            None if pd.isna(row.sectional_normalized_l400_delta)
            else float(row.sectional_normalized_l400_delta)
        )
        for row in rows.itertuples()
    }
    total = {
        int(row.horse_number): (
            None if pd.isna(row.sectional_normalized_total_delta)
            else float(row.sectional_normalized_total_delta)
        )
        for row in rows.itertuples()
    }
    l400_rel, total_rel = relative(l400), relative(total)
    evidence = {}
    for row in rows.itertuples():
        horse = int(row.horse_number)
        if signal == "l400":
            raw = l400_rel[horse]
        elif signal == "total":
            raw = total_rel[horse]
        else:
            raw = 0.6 * l400_rel[horse] + 0.4 * total_rel[horse]
        samples = float(row.sectional_normalized_samples or 0)
        reliability = samples / (samples + 2.0)
        evidence[horse] = 60.0 + reliability * (raw - 60.0)

    ranked = []
    for record in rows.to_dict("records"):
        horse = int(record["horse_number"])
        matrices = {
            name: float(record.get(f"matrix_{name}", 60.0) or 60.0)
            for name in MATRIX_WEIGHTS
        }
        matrices["sectional"] = (
            (1.0 - alpha) * matrices["sectional"] + alpha * evidence[horse]
        )
        ability = sum(matrices[name] * weight for name, weight in MATRIX_WEIGHTS.items())
        ranked.append({**record, "_ability": ability})
    return sorted(ranked, key=lambda row: (-row["_ability"], int(row["horse_number"])))


def evaluate(groups: list[pd.DataFrame], signal: str, alpha: float) -> tuple[dict, dict]:
    metrics, details = [], {}
    for rows in groups:
        ranked = rank_race(rows, signal, alpha)
        picks = [int(row["horse_number"]) for row in ranked]
        names = {int(row["horse_number"]): row["horse_name"] for row in ranked}
        positions = {int(row["horse_number"]): int(row["finish_pos"]) for row in ranked}
        actual = [horse for horse, position in positions.items() if position <= 3]
        metric = race_metrics(picks, actual, actual_pos=positions, field_size=len(rows))
        metrics.append(metric)
        race = int(ranked[0]["race_number"])
        details[str(race)] = {
            "top2_hits": metric["top2_hits"],
            "top5_capture": metric["top3_capture_at5"],
            "top2": [{"horse": h, "name": names[h], "finish": positions[h]} for h in picks[:2]],
            "rank3": {
                "horse": picks[2], "name": names[picks[2]], "finish": positions[picks[2]]
            },
        }
    summary = summarize_races(metrics)
    distribution = Counter(row["top2_hits"] for row in metrics)
    comp = summary["competitiveness"]
    return {
        "races": len(metrics),
        "zero_hit": distribution[0],
        "one_hit": distribution[1],
        "two_hit": distribution[2],
        "top2_total_hits": sum(row["top2_hits"] for row in metrics),
        "top3_capture_at5": comp["mean_top3_capture_at5"],
        "top3_all_within_top5": comp["top3_all_within_top5"]["rate"],
        "ndcg_at5": comp["mean_ndcg_at5"],
        "winner_in_top5": summary["rates"]["winner_in_top5"],
    }, details


def main() -> int:
    frame = pd.read_csv(DATASET)
    feature_data = json.loads(FEATURES.read_text(encoding="utf-8"))
    records = []
    for race, horses in feature_data["races"].items():
        for horse, values in horses.items():
            records.append({"race_number": int(race), "horse_number": int(horse), **values})
    features = pd.DataFrame(records)
    frame = frame.merge(features, on=["race_number", "horse_number"], how="left", suffixes=("", "_hq"))
    groups = [rows.copy() for _, rows in frame.groupby("race_number", sort=True)]

    results = {
        "coverage": {
            "runners": int(frame["sectional_normalized_samples"].fillna(0).gt(0).sum()),
            "total": int(len(frame)),
        },
        "candidates": {},
    }
    details = {}
    specs = [("baseline", "combo", 0.0)]
    for signal in ("l400", "total", "combo"):
        for alpha in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
            specs.append((f"{signal}_{alpha:.2f}", signal, alpha))
    for name, signal, alpha in specs:
        metrics, race_detail = evaluate(groups, signal, alpha)
        results["candidates"][name] = metrics
        details[name] = race_detail

    baseline = details["baseline"]
    for name, race_detail in details.items():
        if name == "baseline":
            continue
        rescues, harms, changes = 0, 0, []
        for race, before in baseline.items():
            after = race_detail[race]
            if before["rank3"]["finish"] <= 3 and any(
                pick["horse"] == before["rank3"]["horse"] for pick in after["top2"]
            ):
                rescues += 1
            if after["top2_hits"] < before["top2_hits"]:
                harms += 1
            if before["top2"] != after["top2"]:
                changes.append({"race": int(race), "before": before, "after": after})
        results["candidates"][name]["rank3_to_top2_rescues"] = rescues
        results["candidates"][name]["harmful_top2_replacements"] = harms
        results["candidates"][name]["changed_races"] = changes

    JSON_OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 2026-07-15 Real-Context Normalized Sectional Gate",
        "",
        (
            f"- Coverage: {results['coverage']['runners']}/{results['coverage']['total']} runners."
        ),
        "- Each past run uses its own venue/distance/class reference delta from the frozen pre-race Facts snapshot.",
        "",
        "| candidate | zero | one | two | top2 hits | capture@5 | NDCG@5 | R3 rescues | harms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in results["candidates"].items():
        lines.append(
            f"| {name} | {row['zero_hit']} | {row['one_hit']} | {row['two_hit']} | "
            f"{row['top2_total_hits']} | {row['top3_capture_at5']:.3f} | "
            f"{row['ndcg_at5']:.3f} | {row.get('rank3_to_top2_rescues', 0)} | "
            f"{row.get('harmful_top2_replacements', 0)} |"
        )
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
