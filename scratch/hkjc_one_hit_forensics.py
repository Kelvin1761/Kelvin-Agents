#!/usr/bin/env python3
"""Step-4 deterministic forensics for strict HKJC Top-2 one-hit races."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from hkjc_zero_hit_forensics import (
    CONTEXT_SIGNALS,
    DEFAULT_ARCHIVE,
    DEFAULT_MANIFEST,
    SIGNAL_LABELS,
    SIGNALS,
    archive_horses,
    difference,
    logic_horses,
)


ROOT = Path(__file__).resolve().parents[1]

HELPFUL = "有幫助：1→2"
HARMFUL = "有傷害：1→0"
NEUTRAL_BOTH_HIT = "無hit變化：第二及第三選皆中"
NEUTRAL_BOTH_MISS = "無hit變化：第二及第三選皆失"


def load_race_horses(
    record: dict[str, Any],
    archive: dict[tuple[str, int], dict[int, dict[str, Any]]],
    logic_cache: dict[str, dict[int, dict[str, Any]]],
) -> dict[int, dict[str, Any]]:
    if record["dataset"] == "archive":
        return archive.get((record["meeting"], record["race_number"]), {})
    logic_path = str(record["source"]).split(" | ", 1)[0]
    if logic_path not in logic_cache:
        logic_cache[logic_path] = logic_horses(Path(logic_path))
    return logic_cache[logic_path]


def classify_status(rank2_hit: bool, rank3_hit: bool) -> str:
    if not rank2_hit and rank3_hit:
        return HELPFUL
    if rank2_hit and not rank3_hit:
        return HARMFUL
    if rank2_hit and rank3_hit:
        return NEUTRAL_BOTH_HIT
    return NEUTRAL_BOTH_MISS


def describe_support(deltas: dict[str, float], score_gap: float) -> list[str]:
    support = sorted(
        ((key, deltas[key]) for key in CONTEXT_SIGNALS if deltas[key] >= 5.0),
        key=lambda item: (-item[1], item[0]),
    )
    labels = [f"{SIGNAL_LABELS[key]}支持第三選（+{value:.1f}）" for key, value in support[:2]]
    if len(labels) < 2 and deltas["risk"] >= 8.0:
        labels.append(f"第三選風險分較高（+{deltas['risk']:.1f}）")
    if len(labels) < 2 and deltas["confidence"] >= 8.0:
        labels.append(f"第三選信心分較高（+{deltas['confidence']:.1f}）")
    if not labels and score_gap <= 0.5:
        labels.append(f"第二／第三選分差極近（{score_gap:.2f}）")
    return labels[:2]


def analyse(
    records: list[dict[str, Any]],
    archive: dict[tuple[str, int], dict[int, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = []
    errors = []
    logic_cache: dict[str, dict[int, dict[str, Any]]] = {}
    for record in records:
        if not record.get("valid") or record.get("top2_hits") != 1:
            continue
        horses = load_race_horses(record, archive, logic_cache)
        pick_numbers = [row["number"] for row in record["picks"]]
        missing = [number for number in pick_numbers if number not in horses]
        if missing:
            errors.append(
                {"meeting": record["meeting"], "race": record["race_number"], "missing_horses": missing}
            )
            continue
        rank1, rank2, rank3 = [horses[number] for number in pick_numbers]
        actual_set = {row["number"] for row in record["actual_top3"]}
        finish = {row["number"]: row["finish"] for row in record["actual_top3"]}
        rank1_hit = rank1["number"] in actual_set
        rank2_hit = rank2["number"] in actual_set
        rank3_hit = rank3["number"] in actual_set
        status = classify_status(rank2_hit, rank3_hit)
        deltas = difference(rank3, rank2, SIGNALS)
        score_gap = round(rank2["score"] - rank3["score"], 3)
        cases.append(
            {
                "dataset": record["dataset"],
                "meeting": record["meeting"],
                "race_number": record["race_number"],
                "promotion_outcome": status,
                "rank1_hit": rank1_hit,
                "rank2_hit": rank2_hit,
                "rank3_hit": rank3_hit,
                "rank2_winner": finish.get(rank2["number"]) == 1,
                "rank3_winner": finish.get(rank3["number"]) == 1,
                "score_gap_rank2_rank3": score_gap,
                "signal_deltas": deltas,
                "supporting_evidence": describe_support(deltas, score_gap),
                "rank1": f"#{rank1['number']} {rank1['name']}",
                "rank2": f"#{rank2['number']} {rank2['name']}",
                "rank3": f"#{rank3['number']} {rank3['name']}",
                "actual_top3": [
                    f"{row['finish']}. #{row['number']} {row['name']}" for row in record["actual_top3"]
                ],
            }
        )
    return cases, errors


CONDITIONS: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
    ("第二／第三選分差≤0.5", lambda row: row["score_gap_rank2_rank3"] <= 0.5),
    ("第二／第三選分差≤1.0", lambda row: row["score_gap_rank2_rank3"] <= 1.0),
    ("任一context優勢≥5", lambda row: any(row["signal_deltas"][key] >= 5.0 for key in CONTEXT_SIGNALS)),
    ("段速優勢≥5", lambda row: row["signal_deltas"]["speed"] >= 5.0),
    ("form line優勢≥5", lambda row: row["signal_deltas"]["formline"] >= 5.0),
    ("班次context優勢≥5", lambda row: row["signal_deltas"]["class_context"] >= 5.0),
    ("路程context優勢≥5", lambda row: row["signal_deltas"]["distance_context"] >= 5.0),
    ("風險分優勢≥8", lambda row: row["signal_deltas"]["risk"] >= 8.0),
    ("信心分優勢≥8", lambda row: row["signal_deltas"]["confidence"] >= 8.0),
]


def mean_deltas(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {
        key: round(statistics.mean(row["signal_deltas"][key] for row in rows), 3) if rows else 0.0
        for key in SIGNALS
    }


def build_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = Counter(row["promotion_outcome"] for row in cases)
    by_dataset = {}
    for dataset in sorted({row["dataset"] for row in cases}):
        rows = [row for row in cases if row["dataset"] == dataset]
        by_dataset[dataset] = {
            "cases": len(rows),
            "outcomes": dict(Counter(row["promotion_outcome"] for row in rows)),
            "rank2_winners": sum(row["rank2_winner"] for row in rows),
            "rank3_winners": sum(row["rank3_winner"] for row in rows),
        }
    outcome_deltas = {
        outcome: mean_deltas([row for row in cases if row["promotion_outcome"] == outcome])
        for outcome in (HELPFUL, HARMFUL, NEUTRAL_BOTH_HIT, NEUTRAL_BOTH_MISS)
    }
    conditions = []
    for name, predicate in CONDITIONS:
        triggered = [row for row in cases if predicate(row)]
        counts = Counter(row["promotion_outcome"] for row in triggered)
        decisive = counts[HELPFUL] + counts[HARMFUL]
        conditions.append(
            {
                "condition": name,
                "triggers": len(triggered),
                "helpful": counts[HELPFUL],
                "harmful": counts[HARMFUL],
                "neutral_both_hit": counts[NEUTRAL_BOTH_HIT],
                "neutral_both_miss": counts[NEUTRAL_BOTH_MISS],
                "net_top3_hits": counts[HELPFUL] - counts[HARMFUL],
                "helpful_share_of_decisive": round(counts[HELPFUL] / decisive * 100, 1) if decisive else None,
            }
        )
    return {
        "cases": len(cases),
        "outcomes": dict(outcomes),
        "rank2_winners": sum(row["rank2_winner"] for row in cases),
        "rank3_winners": sum(row["rank3_winner"] for row in cases),
        "by_dataset": by_dataset,
        "outcome_mean_rank3_minus_rank2": outcome_deltas,
        "single_condition_diagnostics": conditions,
    }


def write_outputs(cases: list[dict[str, Any]], errors: list[dict[str, Any]], output_prefix: Path) -> None:
    stats = build_summary(cases)
    payload = {
        "method": {
            "comparison": "swap original rank2 for original rank3 while keeping rank1",
            "descriptive_only": True,
            "single_conditions_are_not_candidate_rules": True,
            "excluded": ["odds", "market", "going", "draw", "rank4_to_rank7_tiebreak"],
        },
        "summary": stats,
        "errors": errors,
        "cases": cases,
    }
    json_path = output_prefix.with_suffix(".json")
    csv_path = output_prefix.with_suffix(".csv")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = list(cases[0]) if cases else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in cases:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                    if isinstance(value, (dict, list)) else value
                    for key, value in row.items()
                }
            )

    lines = [
        "# HKJC Wong Choi Step 4 — 1 Hit逐場覆盤",
        "",
        "## 方法鎖定",
        "",
        "- 只處理Step 1嚴格有效樣本中的Top 2一hit場次。",
        "- 固定第一選，只比較保留第二選或升格第三選。",
        "- 單一訊號表只作分辨力診斷，唔係候選規則。",
        "- 不使用賠率、市場、場地狀況、檔位或第4至第7名tie-break。",
        "",
        "## 結果分布",
        "",
        f"- 已覆盤：{stats['cases']}場；錯誤／缺資料：{len(errors)}場",
    ]
    for label in (HELPFUL, HARMFUL, NEUTRAL_BOTH_HIT, NEUTRAL_BOTH_MISS):
        count = stats["outcomes"].get(label, 0)
        lines.append(f"- {label}: {count}場（{count / stats['cases'] * 100:.1f}%）")
    lines.extend(
        [
            f"- 第二選頭馬：{stats['rank2_winners']}場",
            f"- 第三選頭馬：{stats['rank3_winners']}場",
            "",
            "## 時段分布",
            "",
        ]
    )
    for dataset, data in stats["by_dataset"].items():
        outcomes = "；".join(f"{key} {value}" for key, value in data["outcomes"].items())
        lines.append(f"- {dataset}: {data['cases']}場；{outcomes}")
    lines.extend(["", "## 第三選減第二選平均差", "", "| 結果 | 段速 | form line | 班次 | 路程 | 風險分 | 信心分 |", "|---|---:|---:|---:|---:|---:|---:|"])
    for outcome in (HELPFUL, HARMFUL, NEUTRAL_BOTH_HIT, NEUTRAL_BOTH_MISS):
        delta = stats["outcome_mean_rank3_minus_rank2"][outcome]
        lines.append(
            f"| {outcome} | {delta['speed']:+.1f} | {delta['formline']:+.1f} | {delta['class_context']:+.1f} | "
            f"{delta['distance_context']:+.1f} | {delta['risk']:+.1f} | {delta['confidence']:+.1f} |"
        )
    lines.extend(["", "## 單一訊號分辨力", "", "| 條件 | 觸發 | 有幫助 | 有傷害 | 中性 | 淨hit | 決定性個案成功比 |", "|---|---:|---:|---:|---:|---:|---:|"])
    for row in stats["single_condition_diagnostics"]:
        neutral = row["neutral_both_hit"] + row["neutral_both_miss"]
        share = "—" if row["helpful_share_of_decisive"] is None else f"{row['helpful_share_of_decisive']}%"
        lines.append(
            f"| {row['condition']} | {row['triggers']} | {row['helpful']} | {row['harmful']} | {neutral} | "
            f"{row['net_top3_hits']:+d} | {share} |"
        )
    lines.extend(["", "## 逐場證據", ""])
    for row in cases:
        delta_text = "、".join(f"{SIGNAL_LABELS[key]} {value:+.1f}" for key, value in row["signal_deltas"].items())
        support = "；".join(row["supporting_evidence"]) if row["supporting_evidence"] else "無"
        lines.extend(
            [
                f"### {row['meeting']} R{row['race_number']} — {row['promotion_outcome']}",
                "",
                f"- 第一／第二／第三選：{row['rank1']}／{row['rank2']}／{row['rank3']}",
                f"- 實際前三：{'、'.join(row['actual_top3'])}",
                f"- 第二／第三選分差：{row['score_gap_rank2_rank3']:.2f}",
                f"- 訊號差：{delta_text}",
                f"- 第三選支持：{support}",
                "",
            ]
        )
    lines.extend(["## Step 4狀態", "", "1 hit交換風險覆盤完成；尚未建立跨時段錯誤矩陣、候選組合規則、shadow test或改正式模型。"])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "report": str(report_path), "summary": stats, "errors": errors}, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output-prefix", type=Path, default=ROOT / "scratch" / "hkjc_one_hit_forensics")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases, errors = analyse(manifest["records"], archive_horses(args.archive))
    write_outputs(cases, errors, args.output_prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
