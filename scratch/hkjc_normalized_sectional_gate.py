#!/usr/bin/env python3
"""Outcome-blind gate for HKJC class/course-normalized L400 evidence."""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ENGINE = (
    ROOT / ".agents" / "skills" / "hkjc_racing"
    / "hkjc_wong_choi_auto" / "scripts" / "au_racing_engine"
)
SHARED = ROOT / ".agents" / "skills" / "shared_racing"
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(SHARED))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402


INPUTS = [
    ROOT / "scratch" / "hkjc_ranking_dataset_current.csv",
    ROOT / "scratch" / "hkjc_ranking_dataset_2026_07_15_current.csv",
]
REF_PATH = ROOT / ".agents" / "scripts" / "hkjc_reference_sectionals.json"
JSON_OUT = ROOT / "scratch" / "hkjc_normalized_sectional_gate.json"
REPORT_OUT = ROOT / "scratch" / "hkjc_normalized_sectional_gate_report.md"


def class_key(value: object) -> str:
    text = str(value or "").strip()
    direct = {
        "第一班": "C1", "第二班": "C2", "第三班": "C3",
        "第四班": "C4", "第五班": "C5",
        "一級賽": "G", "二級賽": "G", "三級賽": "G",
        "分級賽": "G", "新馬賽": "GR", "新馬": "GR",
        "GR": "GR", "G": "G",
    }
    if text.upper() in {f"C{n}" for n in range(1, 6)}:
        return text.upper()
    if text in direct:
        return direct[text]
    match = re.search(r"(?:CLASS|C)\s*([1-5])", text, re.I)
    if match:
        return f"C{match.group(1)}"
    if re.search(r"(?:GROUP|GRADE|G)\s*[123]", text, re.I):
        return "G"
    if re.fullmatch(r"[1-5]", text):
        return f"C{text}"
    return ""


def venue_key(row: pd.Series) -> str:
    venue = str(row.get("venue") or "")
    if "AWT" in venue or "全天候" in venue:
        return "sha_tin_awt"
    if "跑馬地" in venue:
        return "happy_valley_turf"
    return "sha_tin_turf"


def reference_l400(row: pd.Series, refs: dict) -> float | None:
    try:
        distance = str(int(float(row.get("distance_num"))))
    except (TypeError, ValueError):
        return None
    cls = class_key(row.get("race_class"))
    record = (
        refs.get("venues", {})
        .get(venue_key(row), {})
        .get(distance, {})
        .get(cls, {})
    )
    sections = record.get("sections", [])
    return float(sections[-1]) if sections else None


def relative_scores(rows: pd.DataFrame, column: str) -> dict[int, float]:
    values = {
        int(row.horse_number): float(getattr(row, column))
        for row in rows.itertuples()
        if not pd.isna(getattr(row, column))
    }
    output = {}
    for row in rows.itertuples():
        horse = int(row.horse_number)
        if horse not in values or len(values) < 2:
            output[horse] = 60.0
            continue
        value = values[horse]
        others = [other for other_horse, other in values.items() if other_horse != horse]
        better_than = sum(other > value for other in others)  # lower delta is faster
        ties = sum(other == value for other in others)
        output[horse] = 45.0 + 30.0 * (better_than + 0.5 * ties) / len(others)
    return output


def score_race(rows: pd.DataFrame, alpha: float) -> list[dict]:
    relative = relative_scores(rows, "normalized_l400_delta")
    ranked = []
    for record in rows.to_dict("records"):
        matrices = {
            name: float(record.get(f"matrix_{name}", 60.0) or 60.0)
            for name in MATRIX_WEIGHTS
        }
        horse = int(record["horse_number"])
        matrices["sectional"] = (
            (1.0 - alpha) * matrices["sectional"] + alpha * relative[horse]
        )
        ability = sum(matrices[name] * weight for name, weight in MATRIX_WEIGHTS.items())
        ranked.append({**record, "_ability": ability})
    return sorted(ranked, key=lambda row: (-row["_ability"], int(row["horse_number"])))


def evaluate(groups: list[pd.DataFrame], alpha: float) -> tuple[dict, dict]:
    race_rows, details = [], {}
    for rows in groups:
        ranked = score_race(rows, alpha)
        picks = [int(row["horse_number"]) for row in ranked]
        positions = {int(row["horse_number"]): int(row["finish_pos"]) for row in ranked}
        actual = [horse for horse, pos in positions.items() if pos <= 3]
        metric = race_metrics(picks, actual, actual_pos=positions, field_size=len(ranked))
        race_rows.append(metric)
        key = f"{ranked[0]['date']} R{int(ranked[0]['race_number'])}"
        details[key] = {
            "top2_hits": metric["top2_hits"],
            "top2": picks[:2],
            "rank3": picks[2] if len(picks) >= 3 else None,
            "actual_top3": sorted(actual),
        }
    summary = summarize_races(race_rows)
    distribution = Counter(row["top2_hits"] for row in race_rows)
    competitiveness = summary["competitiveness"]
    return {
        "races": len(race_rows),
        "zero_hit": distribution[0],
        "one_hit": distribution[1],
        "two_hit": distribution[2],
        "top2_total_hits": sum(row["top2_hits"] for row in race_rows),
        "top3_capture_at5": competitiveness["mean_top3_capture_at5"],
        "top3_all_within_top5": competitiveness["top3_all_within_top5"]["rate"],
        "ndcg_at5": competitiveness["mean_ndcg_at5"],
        "winner_in_top5": summary["rates"]["winner_in_top5"],
        "mrr": summary["mrr"],
    }, details


def main() -> int:
    refs = json.loads(REF_PATH.read_text(encoding="utf-8"))
    frames = []
    for path in INPUTS:
        frame = pd.read_csv(path)
        frame["source"] = path.stem
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    data["reference_l400"] = data.apply(lambda row: reference_l400(row, refs), axis=1)
    data["normalized_l400_delta"] = data["raw_l400"] - data["reference_l400"]
    data["meeting_key"] = data["date"].astype(str)

    dates = sorted(data.loc[data["source"].eq(INPUTS[0].stem), "date"].astype(str).unique())
    cut = max(1, math.floor(len(dates) * 0.70))
    split_dates = {
        "development": set(dates[:cut]),
        "temporal_holdout": set(dates[cut:]),
        "all_archive": set(dates),
        "2026_07_15": set(
            data.loc[data["source"].eq(INPUTS[1].stem), "date"].astype(str).unique()
        ),
    }
    results = {
        "coverage": {
            "runners": int(data["normalized_l400_delta"].notna().sum()),
            "total_runners": int(len(data)),
            "rate": float(data["normalized_l400_delta"].notna().mean()),
        },
        "splits": {},
    }
    alphas = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30)
    details_by_split = {}
    for split, allowed_dates in split_dates.items():
        subset = data[data["date"].astype(str).isin(allowed_dates)]
        groups = [
            rows.copy()
            for _, rows in subset.groupby(["source", "date", "race_number"], sort=True)
        ]
        results["splits"][split] = {}
        details_by_split[split] = {}
        for alpha in alphas:
            metrics, details = evaluate(groups, alpha)
            key = f"{alpha:.2f}"
            results["splits"][split][key] = metrics
            details_by_split[split][key] = details

    # Explicitly count desired 3rd→Top2 rescues and harmful blind replacements.
    for split in ("temporal_holdout", "all_archive", "2026_07_15"):
        baseline = details_by_split[split]["0.00"]
        for alpha in alphas[1:]:
            key = f"{alpha:.2f}"
            candidate = details_by_split[split][key]
            rescues = harms = 0
            for race, before in baseline.items():
                after = candidate[race]
                if before["rank3"] in before["actual_top3"] and before["rank3"] in after["top2"]:
                    rescues += 1
                if (
                    before["top2_hits"] > after["top2_hits"]
                    and set(before["top2"]) != set(after["top2"])
                ):
                    harms += 1
            results["splits"][split][key]["rank3_to_top2_rescues"] = rescues
            results["splits"][split][key]["harmful_top2_replacements"] = harms

    JSON_OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# HKJC Normalized Sectional Gate",
        "",
        (
            f"- Coverage: {results['coverage']['runners']}/{results['coverage']['total_runners']} "
            f"({results['coverage']['rate']:.1%}) runners"
        ),
        "- Signal: raw L400 minus exact HKJC venue/distance/class reference L400; no cross-class fallback.",
        "",
    ]
    for split, table in results["splits"].items():
        lines.extend([
            f"## {split}",
            "",
            "| alpha | races | zero | one | two | top2 hits | capture@5 | NDCG@5 | winner@5 | R3 rescues | harms |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for alpha, row in table.items():
            lines.append(
                f"| {alpha} | {row['races']} | {row['zero_hit']} | {row['one_hit']} | "
                f"{row['two_hit']} | {row['top2_total_hits']} | {row['top3_capture_at5']:.3f} | "
                f"{row['ndcg_at5']:.3f} | {row['winner_in_top5']:.3f} | "
                f"{row.get('rank3_to_top2_rescues', 0)} | {row.get('harmful_top2_replacements', 0)} |"
            )
        lines.append("")
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
