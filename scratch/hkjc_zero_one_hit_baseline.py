#!/usr/bin/env python3
"""Step-2 HKJC Wong Choi 0/1-hit descriptive baseline.

Consumes the strict Step-1 manifest and reports where 0/1-hit races cluster.
This script is descriptive only: it neither rescales features nor changes ranks.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


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


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalise_venue(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "跑馬地" in text or "happy" in text:
        return "跑馬地"
    if "沙田" in text or "sha" in text:
        return "沙田"
    return "未知"


def normalise_class(value: Any) -> str:
    text = str(value or "").strip()
    if text in {"1", "2", "3", "4", "5"}:
        return f"第{text}班"
    chinese = {"第一班": 1, "第二班": 2, "第三班": 3, "第四班": 4, "第五班": 5}
    for label, number in chinese.items():
        if label in text:
            return f"第{number}班"
    match = re.search(r"(?:CLASS|C)\s*([1-5])", text.upper())
    if match:
        return f"第{match.group(1)}班"
    if any(token in text.upper() for token in ("GROUP", "GR", "一級賽", "二級賽", "三級賽")):
        return "級際／表列"
    return "未知"


def parse_distance(value: Any) -> int:
    match = re.search(r"(\d{3,4})", str(value or ""))
    return int(match.group(1)) if match else 0


def distance_bucket(distance: int) -> str:
    if distance <= 0:
        return "未知"
    if distance <= 1000:
        return "1000米"
    if distance <= 1200:
        return "1200米"
    if distance <= 1400:
        return "1400米"
    if distance <= 1650:
        return "1600／1650米"
    if distance <= 1800:
        return "1800米"
    return "2000米或以上"


def field_bucket(size: int) -> str:
    if size <= 0:
        return "未知"
    if size <= 9:
        return "9匹或以下"
    if size <= 11:
        return "10–11匹"
    if size <= 14:
        return "12–14匹"
    return "15匹或以上"


def score_bucket(value: float | None) -> str:
    if value is None:
        return "未知"
    if value <= 60:
        return "≤60"
    if value < 70:
        return "60–<70"
    if value < 80:
        return "70–<80"
    return "≥80"


def gap_bucket(value: float | None) -> str:
    if value is None:
        return "未知"
    if value <= 0.5:
        return "≤0.5"
    if value <= 1.0:
        return ">0.5–1.0"
    if value <= 2.0:
        return ">1.0–2.0"
    return ">2.0"


def archive_lookup(path: Path) -> dict[tuple[str, int], dict[str, Any]]:
    grouped: defaultdict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            meeting = str(row.get("meeting_name") or Path(str(row.get("meeting") or "")).name)
            race_number = as_int(row.get("race_number"))
            if meeting and race_number > 0:
                grouped[(meeting, race_number)].append(row)

    lookup = {}
    for key, rows in grouped.items():
        first = rows[0]
        ranked = {}
        for row in rows:
            rank = as_int(row.get("current_live_rank"))
            if rank in (1, 2, 3):
                ranked[rank] = {
                    "confidence": as_float(row.get("feat_confidence_score")),
                    "risk": as_float(row.get("feat_risk_score")),
                }
        race_class = normalise_class(first.get("race_class"))
        if race_class == "未知":
            race_class = normalise_class(first.get("race_class_label") or first.get("race_class_num"))
        lookup[key] = {
            "venue": normalise_venue(first.get("venue")),
            "race_class": race_class,
            "distance": as_int(first.get("distance_num"), parse_distance(first.get("distance"))),
            "field_size": as_int(first.get("field_size"), len(rows)),
            "ranked": ranked,
        }
    return lookup


def logic_metadata(logic_path: Path) -> dict[str, Any]:
    payload = json.loads(logic_path.read_text(encoding="utf-8"))
    race = payload.get("race_analysis") if isinstance(payload.get("race_analysis"), dict) else {}
    ranked = {}
    for raw in (payload.get("horses") or {}).values():
        auto = raw.get("python_auto") if isinstance(raw.get("python_auto"), dict) else {}
        rank = as_int(auto.get("rank"))
        if rank not in (1, 2, 3):
            continue
        features = auto.get("feature_scores") if isinstance(auto.get("feature_scores"), dict) else {}
        ranked[rank] = {
            "confidence": as_float(features.get("confidence_score")),
            "risk": as_float(features.get("risk_score")),
        }
    return {
        "venue": normalise_venue(race.get("venue")),
        "race_class": normalise_class(race.get("race_class")),
        "distance": parse_distance(race.get("distance")),
        "field_size": len(race.get("field_horse_names") or payload.get("horses") or {}),
        "ranked": ranked,
    }


def is_direct_challenger_opportunity(record: dict[str, Any]) -> bool:
    if record["top2_hits"] == 0:
        return bool(record["third_pick_hit"])
    if record["top2_hits"] != 1 or not record["third_pick_hit"]:
        return False
    actual = {row["number"] for row in record["actual_top3"]}
    return record["picks"][0]["number"] in actual and record["picks"][1]["number"] not in actual


def enrich(records: list[dict[str, Any]], archive: dict[tuple[str, int], dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    logic_cache: dict[str, dict[str, Any]] = {}
    for record in records:
        if not record.get("valid"):
            continue
        if record["dataset"] == "archive":
            metadata = archive.get((record["meeting"], record["race_number"]), {})
        else:
            logic_path = str(record["source"]).split(" | ", 1)[0]
            if logic_path not in logic_cache:
                logic_cache[logic_path] = logic_metadata(Path(logic_path))
            metadata = logic_cache[logic_path]
        ranked_meta = metadata.get("ranked") or {}
        score1, score2, score3 = (record["picks"][index]["score"] for index in range(3))
        row = {
            **record,
            "venue": metadata.get("venue", "未知"),
            "race_class": metadata.get("race_class", "未知"),
            "distance": as_int(metadata.get("distance")),
            "field_size": as_int(metadata.get("field_size"), record.get("field_finishers", 0)),
            "rank1_confidence": (ranked_meta.get(1) or {}).get("confidence"),
            "rank2_confidence": (ranked_meta.get(2) or {}).get("confidence"),
            "rank3_confidence": (ranked_meta.get(3) or {}).get("confidence"),
            "rank2_risk": (ranked_meta.get(2) or {}).get("risk"),
            "rank3_risk": (ranked_meta.get(3) or {}).get("risk"),
            "gap_rank1_rank2": round(score1 - score2, 4),
            "gap_rank2_rank3": round(score2 - score3, 4),
            "direct_challenger_opportunity": is_direct_challenger_opportunity(record),
        }
        row.update(
            {
                "distance_bucket": distance_bucket(row["distance"]),
                "field_bucket": field_bucket(row["field_size"]),
                "rank2_confidence_bucket": score_bucket(row["rank2_confidence"]),
                "rank2_risk_bucket": score_bucket(row["rank2_risk"]),
                "gap12_bucket": gap_bucket(row["gap_rank1_rank2"]),
                "gap23_bucket": gap_bucket(row["gap_rank2_rank3"]),
            }
        )
        enriched.append(row)
    return enriched


def metric_row(dimension: str, bucket: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    races = len(records)
    hits = Counter(row["top2_hits"] for row in records)
    direct = sum(row["direct_challenger_opportunity"] for row in records)
    return {
        "dimension": dimension,
        "bucket": bucket,
        "races": races,
        "sample_flag": "stable" if races >= 15 else "small",
        "zero_hit": hits[0],
        "zero_hit_rate": round(hits[0] / races * 100, 1) if races else 0.0,
        "one_hit": hits[1],
        "one_hit_rate": round(hits[1] / races * 100, 1) if races else 0.0,
        "two_hit": hits[2],
        "two_hit_rate": round(hits[2] / races * 100, 1) if races else 0.0,
        "zero_or_one_rate": round((hits[0] + hits[1]) / races * 100, 1) if races else 0.0,
        "winner_top2_rate": round(sum(row["winner_in_top2"] for row in records) / races * 100, 1) if races else 0.0,
        "third_pick_hit_rate": round(sum(row["third_pick_hit"] for row in records) / races * 100, 1) if races else 0.0,
        "direct_challenger_opportunities": direct,
        "direct_challenger_rate": round(direct / races * 100, 1) if races else 0.0,
    }


def aggregate(records: list[dict[str, Any]], dimension: str, getter: Callable[[dict[str, Any]], str]) -> list[dict[str, Any]]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(getter(record))].append(record)
    return [metric_row(dimension, bucket, rows) for bucket, rows in sorted(groups.items())]


DIMENSIONS: list[tuple[str, Callable[[dict[str, Any]], str]]] = [
    ("時段", lambda row: row["dataset"]),
    ("賽日", lambda row: row["meeting"]),
    ("場地", lambda row: row["venue"]),
    ("班次", lambda row: row["race_class"]),
    ("路程", lambda row: row["distance_bucket"]),
    ("馬數", lambda row: row["field_bucket"]),
    ("第二選信心分", lambda row: row["rank2_confidence_bucket"]),
    ("第二選風險分", lambda row: row["rank2_risk_bucket"]),
    ("第一／第二選分差", lambda row: row["gap12_bucket"]),
    ("第二／第三選分差", lambda row: row["gap23_bucket"]),
    ("時段×第二選信心分", lambda row: f"{row['dataset']}｜{row['rank2_confidence_bucket']}"),
    ("時段×第一／第二選分差", lambda row: f"{row['dataset']}｜{row['gap12_bucket']}"),
    ("時段×第二／第三選分差", lambda row: f"{row['dataset']}｜{row['gap23_bucket']}"),
]


def write_outputs(records: list[dict[str, Any]], output_prefix: Path) -> None:
    aggregates = []
    for dimension, getter in DIMENSIONS:
        aggregates.extend(aggregate(records, dimension, getter))
    overall = metric_row("全體", "全體", records)
    stable = [row for row in aggregates if row["sample_flag"] == "stable" and row["dimension"] != "賽日"]
    worst_zero = sorted(stable, key=lambda row: (-row["zero_hit_rate"], -row["races"]))[:8]
    lowest_two = sorted(stable, key=lambda row: (row["two_hit_rate"], -row["races"]))[:8]
    challenger = sorted(stable, key=lambda row: (-row["direct_challenger_rate"], -row["races"]))[:8]
    missing = Counter()
    for row in records:
        for field in ("venue", "race_class", "distance", "field_size", "rank2_confidence", "rank2_risk"):
            value = row.get(field)
            if value in (None, 0, "未知"):
                missing[field] += 1

    payload = {
        "method": {
            "descriptive_only": True,
            "minimum_stable_bucket": 15,
            "excluded": ["odds", "market", "going", "draw", "rank4_to_rank7_tiebreak"],
        },
        "overall": overall,
        "missing_metadata": dict(missing),
        "aggregates": aggregates,
        "stable_watchlists": {
            "highest_zero_hit_rate": worst_zero,
            "lowest_two_hit_rate": lowest_two,
            "highest_direct_challenger_rate": challenger,
        },
    }
    json_path = output_prefix.with_suffix(".json")
    csv_path = output_prefix.with_suffix(".csv")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(overall))
        writer.writeheader()
        writer.writerow(overall)
        writer.writerows(aggregates)

    by_dimension: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in aggregates:
        by_dimension[row["dimension"]].append(row)
    lines = [
        "# HKJC Wong Choi Step 2 — 0／1 Hit 基線圖",
        "",
        "## 方法",
        "",
        "- 使用Step 1嚴格有效樣本；只做描述統計，不調參、不重排。",
        "- 主要指標是Top 2實際入前三的0／1／2 hit分布。",
        "- 少於15場的bucket標為小樣本，只作提示。",
        "- 不使用賠率、市場、場地狀況、檔位或第4至第7名tie-break。",
        "",
        "## 全體",
        "",
        f"- 有效賽事：{overall['races']}",
        f"- 0 hit：{overall['zero_hit']}（{overall['zero_hit_rate']}%）",
        f"- 1 hit：{overall['one_hit']}（{overall['one_hit_rate']}%）",
        f"- 2 hit：{overall['two_hit']}（{overall['two_hit_rate']}%）",
        f"- 頭馬在模型Top 2：{overall['winner_top2_rate']}%",
        f"- 可直接研究第三選升第二位的事後機會：{overall['direct_challenger_opportunities']}（{overall['direct_challenger_rate']}%）",
        "",
    ]
    for dimension in ("時段", "場地", "班次", "路程", "馬數", "第二選信心分", "第二選風險分", "第一／第二選分差", "第二／第三選分差", "時段×第二選信心分", "時段×第一／第二選分差", "時段×第二／第三選分差"):
        lines.extend([f"## {dimension}", "", "| Bucket | 場數 | 0 hit | 1 hit | 2 hit | 頭馬Top 2 | 第三選直接機會 | 樣本 |", "|---|---:|---:|---:|---:|---:|---:|---|"])
        for row in by_dimension[dimension]:
            lines.append(
                f"| {row['bucket']} | {row['races']} | {row['zero_hit_rate']}% | {row['one_hit_rate']}% | "
                f"{row['two_hit_rate']}% | {row['winner_top2_rate']}% | {row['direct_challenger_rate']}% | "
                f"{'足夠' if row['sample_flag'] == 'stable' else '小'} |"
            )
        lines.append("")
    lines.extend(["## 穩定樣本觀察名單", "", "以下只係Step 3優先檢查次序，不代表因果或修正規則。", "", "### 0 hit較高", ""])
    for row in worst_zero:
        lines.append(f"- {row['dimension']}／{row['bucket']}: {row['zero_hit_rate']}%（n={row['races']}）")
    lines.extend(["", "### 2 hit較低", ""])
    for row in lowest_two:
        lines.append(f"- {row['dimension']}／{row['bucket']}: {row['two_hit_rate']}%（n={row['races']}）")
    lines.extend(["", "### 第三選直接升格機會較集中", ""])
    for row in challenger:
        lines.append(f"- {row['dimension']}／{row['bucket']}: {row['direct_challenger_rate']}%（n={row['races']}）")
    lines.extend(["", "## 資料完整度", ""])
    if missing:
        for field, count in sorted(missing.items()):
            lines.append(f"- {field}: {count}場缺失／未知")
    else:
        lines.append("- 所有本步所需metadata完整。")
    lines.extend(["", "## Step 2狀態", "", "基線分群完成；尚未作逐場原因分類、候選規則測試或正式模型改動。"])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "report": str(report_path), "overall": overall, "missing": dict(missing)}, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output-prefix", type=Path, default=ROOT / "scratch" / "hkjc_zero_one_hit_baseline")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    records = enrich(manifest["records"], archive_lookup(args.archive))
    write_outputs(records, args.output_prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
