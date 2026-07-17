#!/usr/bin/env python3
"""Step-3 deterministic forensics for strict HKJC Top-2 zero-hit races.

The classifier is intentionally conservative.  It uses only sectional/speed,
form line, class, distance, risk, confidence and missing/neutral evidence.  It
does not rescore or re-rank any horse.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "scratch" / "hkjc_zero_one_hit_manifest.json"
DEFAULT_ARCHIVE = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_reflector"
    / "artifacts"
    / "hkjc_ranking_dataset.csv"
)

SIGNALS = ("speed", "formline", "class_context", "distance_context", "risk", "confidence")
CONTEXT_SIGNALS = ("speed", "formline", "class_context", "distance_context")
SIGNAL_LABELS = {
    "speed": "段速",
    "formline": "form line",
    "class_context": "班次context",
    "distance_context": "路程context",
    "risk": "風險分",
    "confidence": "信心分",
}
PRIMARY_LABELS = {
    "speed": "段速辨識不足",
    "formline": "form line辨識不足",
    "class_context": "班次context辨識不足",
    "distance_context": "路程context辨識不足",
}


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 60.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def horse_row(
    *,
    number: int,
    name: str,
    rank: int,
    score: float,
    features: dict[str, Any],
    matrices: dict[str, Any],
    provenance: dict[str, Any] | None,
) -> dict[str, Any]:
    values = {
        "speed": as_float(features.get("speed_score")),
        "formline": as_float(matrices.get("form_line")),
        "class_context": as_float(features.get("class_score")),
        "distance_context": as_float(features.get("distance_score")),
        "risk": as_float(features.get("risk_score")),
        "confidence": as_float(features.get("confidence_score")),
    }
    neutral_count = sum(abs(values[key] - 60.0) < 1e-9 for key in CONTEXT_SIGNALS)
    explicit_missing = None
    if provenance is not None:
        def missing(key: str) -> bool:
            return "missing" in str(provenance.get(key) or "").lower()

        formline_missing = missing("formline_strength_score") and missing("margin_trend_score")
        explicit_missing = sum(
            (
                missing("speed_score"),
                formline_missing,
                missing("class_score"),
                missing("distance_score"),
            )
        )
    return {
        "number": number,
        "name": name,
        "rank": rank,
        "score": round(score, 4),
        **values,
        "neutral_context_count": neutral_count,
        "explicit_missing_context_count": explicit_missing,
    }


def archive_horses(path: Path) -> dict[tuple[str, int], dict[int, dict[str, Any]]]:
    races: defaultdict[tuple[str, int], dict[int, dict[str, Any]]] = defaultdict(dict)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            meeting = str(row.get("meeting_name") or Path(str(row.get("meeting") or "")).name)
            race_number = as_int(row.get("race_number"))
            number = as_int(row.get("horse_number"))
            if not meeting or race_number <= 0 or number <= 0:
                continue
            features = {
                "speed_score": row.get("feat_speed_score"),
                "class_score": row.get("feat_class_score"),
                "distance_score": row.get("feat_distance_score"),
                "risk_score": row.get("feat_risk_score"),
                "confidence_score": row.get("feat_confidence_score"),
            }
            matrices = {"form_line": row.get("matrix_form_line")}
            races[(meeting, race_number)][number] = horse_row(
                number=number,
                name=str(row.get("horse_name") or ""),
                rank=as_int(row.get("current_live_rank"), 999),
                score=as_float(row.get("current_live_rank_score"), as_float(row.get("current_live_ability"))),
                features=features,
                matrices=matrices,
                provenance=None,
            )
    return dict(races)


def logic_horses(path: Path) -> dict[int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = {}
    for horse_key, raw in (payload.get("horses") or {}).items():
        auto = raw.get("python_auto") if isinstance(raw.get("python_auto"), dict) else {}
        if not auto:
            continue
        number = as_int(horse_key)
        features = auto.get("feature_scores") if isinstance(auto.get("feature_scores"), dict) else {}
        matrices = auto.get("matrix_scores") if isinstance(auto.get("matrix_scores"), dict) else {}
        provenance = auto.get("score_provenance") if isinstance(auto.get("score_provenance"), dict) else {}
        rows[number] = horse_row(
            number=number,
            name=str(raw.get("horse_name") or ""),
            rank=as_int(auto.get("rank"), 999),
            score=as_float(auto.get("rank_score"), as_float(auto.get("ability_score"))),
            features=features,
            matrices=matrices,
            provenance=provenance,
        )
    return rows


def mean_signal(horses: list[dict[str, Any]], signal: str) -> float:
    return statistics.mean(float(row[signal]) for row in horses)


def group_snapshot(horses: list[dict[str, Any]]) -> dict[str, Any]:
    out = {key: round(mean_signal(horses, key), 3) for key in SIGNALS}
    out["neutral_context_count"] = round(
        statistics.mean(row["neutral_context_count"] for row in horses), 3
    )
    explicit = [row["explicit_missing_context_count"] for row in horses if row["explicit_missing_context_count"] is not None]
    out["explicit_missing_context_count"] = round(statistics.mean(explicit), 3) if explicit else None
    return out


def difference(left: dict[str, Any], right: dict[str, Any], keys: tuple[str, ...]) -> dict[str, float]:
    return {key: round(float(left[key]) - float(right[key]), 3) for key in keys}


def rank3_case(
    record: dict[str, Any], horses: dict[int, dict[str, Any]], model_top3: list[dict[str, Any]]
) -> tuple[str, list[str], dict[str, Any]]:
    rank2, rank3 = model_top3[1], model_top3[2]
    deltas = difference(rank3, rank2, SIGNALS)
    secondary: list[str] = []
    context_support = sorted(
        ((key, deltas[key]) for key in CONTEXT_SIGNALS if deltas[key] >= 5.0),
        key=lambda item: (-item[1], item[0]),
    )
    secondary.extend(f"{SIGNAL_LABELS[key]}支持第三選（+{value:.1f}）" for key, value in context_support[:2])
    if len(secondary) < 2 and deltas["risk"] >= 8.0:
        secondary.append(f"第三選風險分較高（+{deltas['risk']:.1f}）")
    if len(secondary) < 2 and deltas["confidence"] >= 8.0:
        secondary.append(f"第三選信心分較高（+{deltas['confidence']:.1f}）")
    score_gap = round(rank2["score"] - rank3["score"], 3)
    rank3_actual_finish = next(
        row["finish"] for row in record["actual_top3"] if row["number"] == rank3["number"]
    )
    if not secondary and score_gap <= 0.5:
        secondary.append(f"第二／第三選分差極近（{score_gap:.2f}）")
    return (
        "第三選排序／上限壓低",
        secondary[:2],
        {
            "comparison": "rank3_minus_rank2",
            "score_gap_rank2_rank3": score_gap,
            "rank3_actual_finish": rank3_actual_finish,
            "signal_deltas": deltas,
            "rank2": rank2,
            "rank3": rank3,
        },
    )


def full_miss_case(
    record: dict[str, Any], model_top3: list[dict[str, Any]], actual_top3: list[dict[str, Any]]
) -> tuple[str, list[str], dict[str, Any]]:
    model = group_snapshot(model_top3)
    actual = group_snapshot(actual_top3)
    deltas = difference(actual, model, SIGNALS)
    context_support = sorted(
        ((key, deltas[key]) for key in CONTEXT_SIGNALS if deltas[key] >= 5.0),
        key=lambda item: (-item[1], item[0]),
    )
    neutral_delta = round(actual["neutral_context_count"] - model["neutral_context_count"], 3)
    explicit_missing_delta = None
    if actual["explicit_missing_context_count"] is not None and model["explicit_missing_context_count"] is not None:
        explicit_missing_delta = round(
            actual["explicit_missing_context_count"] - model["explicit_missing_context_count"], 3
        )
    false_confidence_delta = round(model["confidence"] - actual["confidence"], 3)
    false_risk_delta = round(model["risk"] - actual["risk"], 3)
    neutral_signal = neutral_delta >= 1.0 or (
        explicit_missing_delta is not None and explicit_missing_delta >= 1.0
    )
    uncertainty_signal = false_confidence_delta >= 8.0 or false_risk_delta >= 8.0

    if context_support:
        primary_key = context_support[0][0]
        primary = PRIMARY_LABELS[primary_key]
    elif neutral_signal:
        primary = "資料缺失／中性60壓低上限"
    elif uncertainty_signal:
        primary = "不確定性失準"
    else:
        primary = "未解釋／整體辨識失敗"

    secondary: list[str] = []
    for key, value in context_support:
        label = PRIMARY_LABELS[key]
        if label != primary and len(secondary) < 2:
            secondary.append(f"{label}（+{value:.1f}）")
    if neutral_signal and primary != "資料缺失／中性60壓低上限" and len(secondary) < 2:
        secondary.append(f"中性／缺失context較多（+{max(neutral_delta, explicit_missing_delta or 0):.1f}）")
    if uncertainty_signal and primary != "不確定性失準" and len(secondary) < 2:
        secondary.append(
            f"模型不確定性分辨失準（信心差{false_confidence_delta:+.1f}；風險差{false_risk_delta:+.1f}）"
        )
    return (
        primary,
        secondary[:2],
        {
            "comparison": "actual_top3_minus_model_top3",
            "model_top3_mean": model,
            "actual_top3_mean": actual,
            "signal_deltas": deltas,
            "neutral_context_delta": neutral_delta,
            "explicit_missing_context_delta": explicit_missing_delta,
            "model_minus_actual_confidence": false_confidence_delta,
            "model_minus_actual_risk": false_risk_delta,
        },
    )


def classify(
    records: list[dict[str, Any]], archive: dict[tuple[str, int], dict[int, dict[str, Any]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = []
    errors = []
    logic_cache: dict[str, dict[int, dict[str, Any]]] = {}
    for record in records:
        if not record.get("valid") or record.get("top2_hits") != 0:
            continue
        if record["dataset"] == "archive":
            horses = archive.get((record["meeting"], record["race_number"]), {})
        else:
            logic_path = str(record["source"]).split(" | ", 1)[0]
            if logic_path not in logic_cache:
                logic_cache[logic_path] = logic_horses(Path(logic_path))
            horses = logic_cache[logic_path]
        pick_numbers = [row["number"] for row in record["picks"]]
        actual_numbers = [row["number"] for row in record["actual_top3"]]
        missing = [number for number in pick_numbers + actual_numbers if number not in horses]
        if missing:
            errors.append(
                {"meeting": record["meeting"], "race": record["race_number"], "missing_horses": sorted(set(missing))}
            )
            continue
        model_top3 = [horses[number] for number in pick_numbers]
        actual_top3 = [horses[number] for number in actual_numbers]
        if record["third_pick_hit"]:
            primary, secondary, evidence = rank3_case(record, horses, model_top3)
            case_type = "第三選已入前三"
        else:
            primary, secondary, evidence = full_miss_case(record, model_top3, actual_top3)
            case_type = "模型頭三全失"
        cases.append(
            {
                "dataset": record["dataset"],
                "meeting": record["meeting"],
                "race_number": record["race_number"],
                "case_type": case_type,
                "primary_cause": primary,
                "secondary_causes": secondary,
                "model_top3": [f"#{row['number']} {row['name']}" for row in model_top3],
                "actual_top3": [f"#{row['number']} {row['name']}" for row in actual_top3],
                "evidence": evidence,
            }
        )
    return cases, errors


def summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rank3_cases = [row for row in cases if row["case_type"] == "第三選已入前三"]
    full_misses = [row for row in cases if row["case_type"] == "模型頭三全失"]
    unresolved = [row for row in full_misses if row["primary_cause"] == "未解釋／整體辨識失敗"]
    rank3_support = {
        key: sum(row["evidence"]["signal_deltas"][key] >= 5.0 for row in rank3_cases)
        for key in CONTEXT_SIGNALS
    }
    rank3_strong_context = sum(
        any(row["evidence"]["signal_deltas"][key] >= 5.0 for key in CONTEXT_SIGNALS)
        for row in rank3_cases
    )
    rank3_close_gap = sum(
        row["evidence"]["score_gap_rank2_rank3"] <= 0.5 for row in rank3_cases
    )
    rank3_identifiable = sum(
        row["evidence"]["score_gap_rank2_rank3"] <= 0.5
        or any(row["evidence"]["signal_deltas"][key] >= 5.0 for key in CONTEXT_SIGNALS)
        for row in rank3_cases
    )
    full_mean_delta = {
        key: round(statistics.mean(row["evidence"]["signal_deltas"][key] for row in full_misses), 3)
        if full_misses else 0.0
        for key in SIGNALS
    }
    unresolved_mean_delta = {
        key: round(statistics.mean(row["evidence"]["signal_deltas"][key] for row in unresolved), 3)
        if unresolved else 0.0
        for key in SIGNALS
    }
    return {
        "cases": len(cases),
        "case_type": dict(Counter(row["case_type"] for row in cases)),
        "primary_cause": dict(Counter(row["primary_cause"] for row in cases)),
        "by_dataset": {
            dataset: {
                "cases": len(rows),
                "case_type": dict(Counter(row["case_type"] for row in rows)),
                "primary_cause": dict(Counter(row["primary_cause"] for row in rows)),
            }
            for dataset in sorted({row["dataset"] for row in cases})
            for rows in [[row for row in cases if row["dataset"] == dataset]]
        },
        "rank3_case_diagnostics": {
            "actual_finish": dict(Counter(str(row["evidence"]["rank3_actual_finish"]) for row in rank3_cases)),
            "score_gap_le_0_5": rank3_close_gap,
            "score_gap_le_1_0": sum(row["evidence"]["score_gap_rank2_rank3"] <= 1.0 for row in rank3_cases),
            "score_gap_le_2_0": sum(row["evidence"]["score_gap_rank2_rank3"] <= 2.0 for row in rank3_cases),
            "strong_context_any": rank3_strong_context,
            "strong_context_or_close_gap": rank3_identifiable,
            "no_strong_context_and_not_close": len(rank3_cases) - rank3_identifiable,
            "strong_context_support": rank3_support,
        },
        "full_miss_diagnostics": {
            "cases": len(full_misses),
            "unresolved": len(unresolved),
            "unresolved_rate": round(len(unresolved) / len(full_misses) * 100, 1) if full_misses else 0.0,
            "actual_minus_model_mean_delta": full_mean_delta,
            "unresolved_actual_minus_model_mean_delta": unresolved_mean_delta,
        },
    }


def write_outputs(cases: list[dict[str, Any]], errors: list[dict[str, Any]], output_prefix: Path) -> None:
    stats = summary(cases)
    payload = {
        "method": {
            "context_primary_threshold": 5.0,
            "uncertainty_threshold": 8.0,
            "neutral_or_missing_dimension_threshold": 1.0,
            "maximum_secondary_causes": 2,
            "descriptive_only": True,
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
    fields = [
        "dataset", "meeting", "race_number", "case_type", "primary_cause", "secondary_causes",
        "model_top3", "actual_top3", "evidence",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in cases:
            writer.writerow(
                {
                    **row,
                    "secondary_causes": json.dumps(row["secondary_causes"], ensure_ascii=False),
                    "model_top3": json.dumps(row["model_top3"], ensure_ascii=False),
                    "actual_top3": json.dumps(row["actual_top3"], ensure_ascii=False),
                    "evidence": json.dumps(row["evidence"], ensure_ascii=False, separators=(",", ":")),
                }
            )

    lines = [
        "# HKJC Wong Choi Step 3 — 0 Hit逐場覆盤",
        "",
        "## 方法鎖定",
        "",
        "- 只處理Step 1嚴格有效樣本中的Top 2零hit場次。",
        "- 第三選已入前三先分類為排序／上限壓低；其餘比較實際前三與模型頭三的允許訊號平均差。",
        "- Context平均差至少5分、不確定性差至少8分、中性／缺失差至少一個維度才可成為原因。",
        "- 每場一個主因、最多兩個副因；未達閾值列為未解釋。",
        "- 不使用賠率、市場、場地狀況、檔位或第4至第7名tie-break。",
        "",
        "## 總覽",
        "",
        f"- 已分類：{stats['cases']}場",
        f"- 分類錯誤／缺資料：{len(errors)}場",
    ]
    for label, count in sorted(stats["case_type"].items()):
        lines.append(f"- {label}: {count}場")
    lines.extend(["", "## 主因分布", ""])
    for label, count in sorted(stats["primary_cause"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {label}: {count}場（{count / stats['cases'] * 100:.1f}%）")
    rank3_diag = stats["rank3_case_diagnostics"]
    full_diag = stats["full_miss_diagnostics"]
    lines.extend(
        [
            "",
            "## 第三選排序／上限壓低診斷",
            "",
            f"- 實際頭馬／第二／第三：{rank3_diag['actual_finish'].get('1', 0)}／{rank3_diag['actual_finish'].get('2', 0)}／{rank3_diag['actual_finish'].get('3', 0)}場",
            f"- 第二／第三選分差≤0.5：{rank3_diag['score_gap_le_0_5']}場；≤1.0：{rank3_diag['score_gap_le_1_0']}場；≤2.0：{rank3_diag['score_gap_le_2_0']}場",
            f"- 至少一項context優勢≥5：{rank3_diag['strong_context_any']}場",
            f"- 強context或近分至少一項可辨識：{rank3_diag['strong_context_or_close_gap']}場",
            f"- 冇強context亦非近分：{rank3_diag['no_strong_context_and_not_close']}場",
        ]
    )
    for key, count in sorted(rank3_diag["strong_context_support"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {SIGNAL_LABELS[key]}優勢≥5：{count}場")
    mean_delta_text = "、".join(
        f"{SIGNAL_LABELS[key]} {value:+.1f}" for key, value in full_diag["actual_minus_model_mean_delta"].items()
    )
    lines.extend(
        [
            "",
            "## 模型頭三全失診斷",
            "",
            f"- Full miss：{full_diag['cases']}場；未解釋：{full_diag['unresolved']}場（{full_diag['unresolved_rate']}%）",
            f"- 實際前三減模型頭三的整體平均差：{mean_delta_text}",
            "- 負數代表實際前三在現有訊號反而較低；呢類場次唔能夠靠簡單提高該訊號權重解決。",
        ]
    )
    lines.extend(["", "## 時段分布", ""])
    for dataset, data in stats["by_dataset"].items():
        causes = "；".join(f"{key} {value}" for key, value in sorted(data["primary_cause"].items(), key=lambda item: (-item[1], item[0])))
        lines.append(f"- {dataset}: {data['cases']}場；{causes}")
    lines.extend(["", "## 逐場證據", ""])
    for row in cases:
        deltas = row["evidence"].get("signal_deltas") or {}
        delta_text = "、".join(f"{SIGNAL_LABELS[key]} {value:+.1f}" for key, value in deltas.items())
        secondary = "；".join(row["secondary_causes"]) if row["secondary_causes"] else "無"
        lines.extend(
            [
                f"### {row['meeting']} R{row['race_number']} — {row['case_type']}",
                "",
                f"- 主因：{row['primary_cause']}",
                f"- 副因：{secondary}",
                f"- 模型頭三：{'、'.join(row['model_top3'])}",
                f"- 實際前三：{'、'.join(row['actual_top3'])}",
                f"- 訊號差：{delta_text}",
                "",
            ]
        )
    lines.extend(["## Step 3狀態", "", "0 hit原因分類完成；尚未覆盤1 hit、建立跨時段錯誤矩陣、測試候選規則或改正式模型。"])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "report": str(report_path), "summary": stats, "errors": errors}, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output-prefix", type=Path, default=ROOT / "scratch" / "hkjc_zero_hit_forensics")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases, errors = classify(manifest["records"], archive_horses(args.archive))
    write_outputs(cases, errors, args.output_prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
