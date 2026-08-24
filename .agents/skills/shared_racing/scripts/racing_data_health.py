#!/usr/bin/env python3
"""Cross-platform meeting alignment and data-coverage gate.

The scanner deliberately reads only pre-race artifacts.  Result files are not
inputs, preventing the daily validation layer from becoming a leakage path.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# scripts -> shared_racing -> skills -> .agents -> repository root
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import is_materialized_file

# ⚠️ 呢個 set 一定要用 Logic 檔**真正**嘅 key 名。2026-08-21 之前 AU 呢行寫住
# {"speed","form","class","pace","weight","draw"} —— 六個名一個都唔存在（真名係
# `form_score` / `pace_map_score` 等），所以 MISSING_FEATURES 對**每匹馬**都會觸發，
# `deploy_allowed` 永遠 False。冇人發現，因為只有 hkjc_orchestrator 會叫呢個掃描；
# AU 主流程從來冇接 —— 而接落去就會 block 100% AU deploy。
#
# AU 用 `ABILITY_FEATURE_KEYS`（真正入 ability 嘅十個）。唔用全部 18 個：另外 8 個
# 係顯示／中間量，其中一個缺失唔代表評分壞咗，會製造噪音。
EXPECTED_FEATURES = {
    "au": {
        "form_score", "performance_quality_score", "pace_figure_score",
        "trial_score", "pace_map_score", "jockey_score", "trainer_score",
        "jockey_horse_fit_score", "rating_score", "track_score",
    },
    "hkjc": {
        "form_score",
        "speed_score",
        "class_score",
        "jockey_score",
        "trainer_score",
        "draw_score",
        "distance_score",
        "track_going_score",
        "weight_score",
        "consistency_score",
        "risk_score",
        "confidence_score",
    },
}


def _race_number(path: Path) -> int | None:
    match = re.search(r"Race[_ ](\d+)", path.name, re.I)
    return int(match.group(1)) if match else None


def _finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _horse_number_key(value: Any) -> tuple[int, str]:
    match = re.search(r"\d+", str(value))
    return (int(match.group()) if match else 9999, str(value))


def _find_facts_candidates(meeting_dir: Path, race_number: int) -> list[Path]:
    return sorted([
        path for path in meeting_dir.glob("*Facts.md")
        if _race_number(path) == race_number and is_materialized_file(path)
    ])


def _facts_numbers(path: Path | None) -> set[str]:
    if not path or not path.exists():
        return set()
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = (
        r"^###\s+馬號\s+(\d+)\b",
        r"^###\s+(?:馬匹|Horse)\s*#?\s*(\d+)\b",
        r"^##\s*#(\d+)\b",
    )
    values: set[str] = set()
    for pattern in patterns:
        values.update(re.findall(pattern, text, re.M | re.I))
    return values


def _normalize_horse_name(value: Any) -> str:
    text = re.sub(r"\s*[（(][A-Z]\d+[)）]\s*$", "", str(value or "").strip())
    return re.sub(r"[^\w\u3400-\u9fff]", "", text, flags=re.UNICODE).casefold()


# Facts / Racecard 會喺馬名後面加註解括號 —— AU 係「Family Of League (檔位 11)」
# 或者「Family Of League (11)」。Logic 只存純馬名，所以逐字比會**每匹都唔夾**，
# 就係 2026-08-21 見到嘅 FACTS_NAME_MISMATCH / SOURCE_NAME_MISMATCH 全中。
# 只剝走睇落係註解嘅括號（內含數字或者「檔位」），唔會誤剝真係名字一部分嘅括號。
_NAME_ANNOTATION = re.compile(r"[（(]\s*(?:檔位\s*)?\d+\s*[)）]\s*$")


def _strip_name_annotation(value: str) -> str:
    return _NAME_ANNOTATION.sub("", str(value or "")).strip()


def _facts_runner_names(path: Path | None) -> dict[str, str]:
    if not path or not is_materialized_file(path):
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    pairs = re.findall(r"^###\s+馬號\s+(\d+)\s+—\s*([^|\n]+)", text, re.M)
    if not pairs:
        pairs = re.findall(r"^###\s+(?:馬匹|Horse)\s*#?\s*(\d+)\s+([^|\n]+)", text, re.M | re.I)
    return {number: _strip_name_annotation(name) for number, name in pairs}


def _source_runner_numbers(
    meeting_dir: Path, race_number: int, platform: str
) -> tuple[set[str], list[Path]]:
    patterns = ("*Racecard.md", "*排位表.md") if platform == "hkjc" else ("*Racecard.md",)
    candidates = sorted({
        path
        for pattern in patterns
        for path in meeting_dir.glob(pattern)
        if _race_number(path) == race_number and is_materialized_file(path)
    })
    if len(candidates) != 1:
        return set(), candidates
    text = candidates[0].read_text(encoding="utf-8", errors="replace")
    # AU Racecard keeps withdrawals as numbered rows, for example
    # ``5. Beiwacht - status:Scratched``.  Logic/Facts correctly omit those
    # runners, so counting the raw numbered row creates a false alignment
    # failure and blocks an otherwise healthy meeting.
    if platform == "au":
        text = "\n".join(
            line for line in text.splitlines()
            if "status:scratched" not in line.replace(" ", "").casefold()
        )
    values = set(re.findall(r"馬號:\s*(\d+)\b", text))
    if not values:
        values.update(re.findall(r"^\s*\[?(\d{1,2})\]?\s*[.|)]\s+", text, re.M))
    return values, candidates


def _source_runner_names(path: Path | None) -> dict[str, str]:
    if not path or not is_materialized_file(path):
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.findall(r"^馬號:\s*(\d+).*?(?=^馬號:\s*\d+|\Z)", text, re.M | re.S)
    names: dict[str, str] = {}
    if blocks:
        for match in re.finditer(r"^馬號:\s*(\d+).*?(?=^馬號:\s*\d+|\Z)", text, re.M | re.S):
            block = match.group(0)
            name_match = re.search(r"^馬名:\s*([^\n]+)", block, re.M)
            number_match = re.search(r"^馬號:\s*(\d+)", block, re.M)
            if name_match and number_match:
                names[number_match.group(1)] = _strip_name_annotation(name_match.group(1))
        return names
    return {
        number: _strip_name_annotation(name)
        for number, name in re.findall(r"^\s*\[?(\d{1,2})\]?\s*[.)]\s*([^\n]+)", text, re.M)
        if "status:scratched" not in name.replace(" ", "").casefold()
    }


def _hkjc_coverage(auto: dict) -> float | None:
    """Measure how many public HKJC features have a real pre-race source."""
    provenance = auto.get("score_provenance")
    if not isinstance(provenance, dict):
        return None
    covered = sum(
        1
        for key in EXPECTED_FEATURES["hkjc"]
        if str(provenance.get(key) or "").strip() not in {"", "missing_neutral"}
    )
    return round(covered / len(EXPECTED_FEATURES["hkjc"]) * 100.0, 2)


def _csv_runner_count(path: Path) -> int | None:
    if not is_materialized_file(path):
        return None
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except (OSError, csv.Error, UnicodeError):
        return None


def scan_meeting(platform: str, meeting_dir: Path) -> dict:
    platform = platform.lower()
    if platform not in EXPECTED_FEATURES:
        raise ValueError(f"Unsupported platform: {platform}")
    meeting_dir = meeting_dir.resolve()
    issues: list[dict] = []
    race_reports: list[dict] = []
    expected_races: int | None = None
    readiness_path = meeting_dir / "Extraction_Readiness.json"
    if platform == "hkjc" and is_materialized_file(readiness_path):
        try:
            readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
            expected_races = int(readiness.get("expected_races") or 0) or None
            if readiness.get("status") != "ready":
                issues.append({
                    "severity": "error",
                    "code": "SOURCE_NOT_READY",
                    "message": (
                        f"racecards={readiness.get('racecards_ready', 0)}/"
                        f"{expected_races or '?'}; formguides="
                        f"{readiness.get('formguides_ready', 0)}/{expected_races or '?'}; "
                        f"starter_pdf={readiness.get('starter_pdf_ready', False)}"
                    ),
                })
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            issues.append({
                "severity": "error",
                "code": "INVALID_EXTRACTION_READINESS",
                "message": str(exc),
            })
    logic_paths = sorted(
        (
            path
            for path in meeting_dir.glob("Race_*_Logic.json")
            if is_materialized_file(path)
        ),
        key=lambda path: (_race_number(path) or 999, path.name),
    )
    if not logic_paths:
        issues.append({"severity": "error", "code": "NO_LOGIC", "message": "冇 Race_X_Logic.json"})
    elif expected_races is not None and len(logic_paths) != expected_races:
        issues.append({
            "severity": "error",
            "code": "INCOMPLETE_RACE_SET",
            "message": f"Logic races={len(logic_paths)} expected={expected_races}",
        })

    seen_races: set[int] = set()
    coverage_values: list[float] = []
    total_horses = 0
    for logic_path in logic_paths:
        race_number = _race_number(logic_path)
        if race_number is None:
            continue
        if race_number in seen_races:
            issues.append({"severity": "error", "code": "DUPLICATE_RACE", "race": race_number, "message": "重複 race number"})
            continue
        seen_races.add(race_number)
        race_issues: list[dict] = []
        try:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            race_issues.append({"severity": "error", "code": "INVALID_LOGIC", "message": str(exc)})
            logic = {}
        horses = logic.get("horses") if isinstance(logic, dict) else None
        if not isinstance(horses, dict) or not horses:
            race_issues.append({"severity": "error", "code": "NO_HORSES", "message": "Logic 冇馬匹資料"})
            horses = {}
        numbers = {str(value) for value in horses}
        total_horses += len(horses)
        facts_paths = _find_facts_candidates(meeting_dir, race_number)
        facts_path = facts_paths[0] if len(facts_paths) == 1 else None
        facts_numbers = _facts_numbers(facts_path)
        facts_names = _facts_runner_names(facts_path)
        source_numbers, source_paths = _source_runner_numbers(
            meeting_dir, race_number, platform
        )
        source_names = _source_runner_names(source_paths[0]) if len(source_paths) == 1 else {}
        if len(facts_paths) > 1:
            race_issues.append({
                "severity": "error",
                "code": "AMBIGUOUS_FACTS",
                "message": ", ".join(path.name for path in facts_paths),
            })
        elif not facts_path:
            race_issues.append({"severity": "error", "code": "MISSING_FACTS", "message": "搵唔到 Facts.md"})
        elif facts_numbers and facts_numbers != numbers:
            race_issues.append({
                "severity": "error", "code": "FACTS_LOGIC_MISMATCH",
                "message": f"Facts={sorted(facts_numbers, key=_horse_number_key)} Logic={sorted(numbers, key=_horse_number_key)}",
            })
        if not source_paths:
            race_issues.append({
                "severity": "error",
                "code": "MISSING_RACECARD",
                "message": "搵唔到唯一 pre-race Racecard／排位表",
            })
        elif len(source_paths) > 1:
            race_issues.append({
                "severity": "error",
                "code": "AMBIGUOUS_RACECARD",
                "message": ", ".join(path.name for path in source_paths),
            })
        elif not source_numbers:
            race_issues.append({
                "severity": "error",
                "code": "EMPTY_RACECARD_RUNNERS",
                "message": source_paths[0].name,
            })
        elif source_numbers != numbers:
            race_issues.append({
                "severity": "error", "code": "SOURCE_LOGIC_MISMATCH",
                "message": f"Racecard={sorted(source_numbers, key=_horse_number_key)} Logic={sorted(numbers, key=_horse_number_key)}",
            })

        ranks: list[int] = []
        names: list[str] = []
        horse_coverages: list[float] = []
        for number, horse in horses.items():
            if not isinstance(horse, dict):
                race_issues.append({"severity": "error", "code": "INVALID_HORSE", "horse": number, "message": "horse row 唔係 object"})
                continue
            name = str(horse.get("horse_name") or horse.get("name") or "").strip()
            if not name:
                race_issues.append({"severity": "error", "code": "MISSING_NAME", "horse": number, "message": "冇馬名"})
            elif name.casefold() in names:
                race_issues.append({"severity": "error", "code": "DUPLICATE_NAME", "horse": number, "message": name})
            names.append(name.casefold())
            normalized_name = _normalize_horse_name(name)
            if number in facts_names and normalized_name != _normalize_horse_name(facts_names[number]):
                race_issues.append({
                    "severity": "error",
                    "code": "FACTS_NAME_MISMATCH",
                    "horse": number,
                    "message": f"Facts={facts_names[number]} Logic={name}",
                })
            if number in source_names and normalized_name != _normalize_horse_name(source_names[number]):
                race_issues.append({
                    "severity": "error",
                    "code": "SOURCE_NAME_MISMATCH",
                    "horse": number,
                    "message": f"Racecard={source_names[number]} Logic={name}",
                })
            auto = horse.get("python_auto")
            if not isinstance(auto, dict):
                race_issues.append({"severity": "error", "code": "MISSING_AUTO", "horse": number, "message": "冇 python_auto"})
                continue
            if not _finite_number(auto.get("ability_score")):
                race_issues.append({"severity": "error", "code": "INVALID_SCORE", "horse": number, "message": "ability_score 非數值"})
            rank = auto.get("rank")
            try:
                ranks.append(int(rank))
            except (TypeError, ValueError):
                race_issues.append({"severity": "error", "code": "INVALID_RANK", "horse": number, "message": f"rank={rank!r}"})
            features = auto.get("feature_scores")
            if not isinstance(features, dict):
                race_issues.append({"severity": "error", "code": "NO_FEATURES", "horse": number, "message": "冇 feature_scores"})
            else:
                missing_features = sorted(EXPECTED_FEATURES[platform] - set(features))
                if missing_features:
                    race_issues.append({"severity": "error", "code": "MISSING_FEATURES", "horse": number, "message": ", ".join(missing_features)})
                invalid_features = [key for key, value in features.items() if not _finite_number(value)]
                if invalid_features:
                    race_issues.append({"severity": "error", "code": "INVALID_FEATURES", "horse": number, "message": ", ".join(sorted(invalid_features))})
            coverage = auto.get("data_coverage")
            if isinstance(coverage, dict) and _finite_number(coverage.get("coverage_pct")):
                horse_coverages.append(float(coverage["coverage_pct"]))
            elif platform == "au":
                race_issues.append({"severity": "warning", "code": "NO_COVERAGE", "horse": number, "message": "冇 data_coverage.coverage_pct"})
            else:
                derived_coverage = _hkjc_coverage(auto)
                if derived_coverage is None:
                    race_issues.append({
                        "severity": "error",
                        "code": "NO_PROVENANCE",
                        "horse": number,
                        "message": "冇 score_provenance，無法核實 HKJC 資料覆蓋",
                    })
                else:
                    horse_coverages.append(derived_coverage)

        if ranks and sorted(ranks) != list(range(1, len(horses) + 1)):
            race_issues.append({"severity": "error", "code": "RANK_NOT_PERMUTATION", "message": f"ranks={sorted(ranks)} runners={len(horses)}"})
        analysis_path = meeting_dir / f"Race_{race_number}_Auto_Analysis.md"
        csv_path = meeting_dir / f"Race_{race_number}_Auto_Scoring.csv"
        if not is_materialized_file(analysis_path):
            race_issues.append({"severity": "error", "code": "MISSING_ANALYSIS", "message": analysis_path.name})
        csv_count = _csv_runner_count(csv_path)
        if csv_count is None:
            race_issues.append({"severity": "error", "code": "MISSING_SCORING_CSV", "message": csv_path.name})
        elif csv_count != len(horses):
            race_issues.append({"severity": "error", "code": "CSV_RUNNER_MISMATCH", "message": f"CSV={csv_count} Logic={len(horses)}"})
        race_coverage = round(sum(horse_coverages) / len(horse_coverages), 2) if horse_coverages else None
        if race_coverage is not None:
            coverage_values.append(race_coverage)
            if race_coverage < 70:
                race_issues.append({"severity": "warning", "code": "LOW_COVERAGE", "message": f"平均 coverage {race_coverage:.1f}%"})
        for item in race_issues:
            issues.append({"race": race_number, **item})
        race_reports.append({
            "race": race_number,
            "runners": len(horses),
            "facts_file": facts_path.name if facts_path else None,
            "source_alignment_checked": bool(source_numbers),
            "facts_alignment_checked": bool(facts_numbers),
            "coverage_pct": race_coverage,
            "status": "error" if any(i["severity"] == "error" for i in race_issues) else ("warning" if race_issues else "ok"),
            "issues": race_issues,
        })

    errors = sum(item["severity"] == "error" for item in issues)
    warnings = sum(item["severity"] == "warning" for item in issues)
    status = "error" if errors else ("warning" if warnings else "ok")
    return {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": platform,
        "meeting_dir": str(meeting_dir),
        "meeting": meeting_dir.name,
        "expected_races": expected_races,
        "status": status,
        "deploy_allowed": errors == 0,
        "summary": {
            "races": len(race_reports),
            "horses": total_horses,
            "errors": errors,
            "warnings": warnings,
            "average_coverage_pct": round(sum(coverage_values) / len(coverage_values), 2) if coverage_values else None,
        },
        "races": race_reports,
        "issues": issues,
    }


def status_line(report: dict) -> str:
    icon = {"ok": "✅", "warning": "⚠️", "error": "❌"}[report["status"]]
    summary = report["summary"]
    coverage = summary.get("average_coverage_pct")
    coverage_text = f"｜coverage {coverage:.1f}%" if coverage is not None else ""
    return (
        f"{icon} Data health {report['meeting']}：{summary['races']}場／{summary['horses']}匹"
        f"｜{summary['errors']} errors／{summary['warnings']} warnings{coverage_text}"
    )


def render_markdown(report: dict) -> str:
    lines = [
        f"# Data Health — {report['meeting']}", "",
        f"- 平台：{report['platform'].upper()}",
        f"- 狀態：**{report['status'].upper()}**",
        f"- 允許部署：{'是' if report['deploy_allowed'] else '否'}",
        f"- 摘要：{status_line(report)}", "",
        "## Race coverage", "",
        "| Race | Runners | Coverage | Status |",
        "|---:|---:|---:|---|",
    ]
    for race in report["races"]:
        coverage = "—" if race["coverage_pct"] is None else f"{race['coverage_pct']:.1f}%"
        lines.append(f"| {race['race']} | {race['runners']} | {coverage} | {race['status']} |")
    lines.extend(["", "## Issues", ""])
    if not report["issues"]:
        lines.append("- 冇發現 alignment、coverage 或 scoring output 問題。")
    else:
        for issue in report["issues"]:
            race = f"R{issue['race']} " if issue.get("race") else ""
            horse = f"馬{issue['horse']} " if issue.get("horse") else ""
            lines.append(f"- [{issue['severity'].upper()}] {race}{horse}{issue['code']}：{issue['message']}")
    lines.extend(["", "> 本報告只讀 pre-race artifacts；賽果不會進入呢個 gate。", ""])
    return "\n".join(lines)


def write_report(report: dict, output_json: Path | None = None, output_md: Path | None = None) -> None:
    output_json = output_json or Path(report["meeting_dir"]) / "Data_Health.json"
    output_md = output_md or Path(report["meeting_dir"]) / "Data_Health.md"
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(render_markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan Wong Choi meeting data alignment and coverage")
    parser.add_argument("--platform", required=True, choices=sorted(EXPECTED_FEATURES))
    parser.add_argument("--meeting-dir", required=True, type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--no-fail", action="store_true", help="Report errors but return exit 0")
    args = parser.parse_args(argv)
    report = scan_meeting(args.platform, args.meeting_dir)
    write_report(report, args.output_json, args.output_md)
    print(status_line(report))
    if report["issues"]:
        for issue in report["issues"]:
            print(json.dumps(issue, ensure_ascii=False, sort_keys=True))
    return 0 if report["deploy_allowed"] or args.no_fail else 2


if __name__ == "__main__":
    raise SystemExit(main())
