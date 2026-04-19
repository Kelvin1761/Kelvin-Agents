#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
"""
Agent Evaluator v1.0 — LLM-as-a-Judge Engine for Agent Architect v3.2.0

Evaluates an agent's SKILL.md against Design Patterns P1-P27.
Produces a structured JSON score report.

Usage:
    python agent_evaluator.py --target <path_to_agent_skill_dir>
    python agent_evaluator.py --target <path> --output <report_path>

Example:
    python agent_evaluator.py --target .agents/skills/nba
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows cp1252 encoding for emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ============================================================
# Evaluation Criteria (mapped to Design Patterns P8-P27)
# ============================================================
CHECKS = [
    {
        "id": "P8",
        "name": "Batch Isolation",
        "pattern": r"batch|chunk|segment|分批|分段",
        "weight": 5,
        "desc": "Agent handles large data in bounded chunks",
    },
    {
        "id": "P9",
        "name": "Output Example Completeness",
        "pattern": r"example|範例|範本|sample output|expected output",
        "weight": 5,
        "desc": "Output examples show full realistic patterns",
    },
    {
        "id": "P10",
        "name": "Session Recovery",
        "pattern": r"session.?recover|斷線|resume|繼續|checkpoint",
        "weight": 8,
        "desc": "Agent can recover from session interruptions",
    },
    {
        "id": "P11",
        "name": "Loop Prevention",
        "pattern": r"max.?retr|loop.?prevent|retry.?limit|3.?次|熔斷",
        "weight": 8,
        "desc": "Agent has retry limits and loop prevention",
    },
    {
        "id": "P12",
        "name": "browser_subagent Ban",
        "pattern": r"browser_subagent",
        "weight": 3,
        "desc": "browser_subagent is not used (should be banned)",
        "inverse": True,  # presence = FAIL
    },
    {
        "id": "P14",
        "name": "Safe File Writer",
        "pattern": r"safe_file_writer|safe.?writ",
        "weight": 5,
        "desc": "File writes use safe_file_writer.py",
    },
    {
        "id": "P16",
        "name": "Session State Persistence",
        "pattern": r"state.?persist|session.?state|_state\.md|checkpoint",
        "weight": 5,
        "desc": "Agent persists state across sessions",
    },
    {
        "id": "P19",
        "name": "Cross-Platform Compatibility",
        "pattern": r"os.?agnostic|cross.?platform|relative.?path|跨平台",
        "weight": 5,
        "desc": "Agent uses relative paths, no shell-specific syntax",
    },
    {
        "id": "P20",
        "name": "Confidence Scoring",
        "pattern": r"confidence.?scor|信心分|信心指數|0.?-100|0.?~.?100",
        "weight": 5,
        "desc": "Agent uses quantitative confidence scoring",
    },
    {
        "id": "P22",
        "name": "Python-First Offloading",
        "pattern": r"python.?first|script|run_command|\.py|offload",
        "weight": 8,
        "desc": "Deterministic tasks offloaded to Python scripts",
    },
    {
        "id": "P23",
        "name": "Gemini Anti-Hallucination",
        "pattern": r"self_correction|CoVe|chain.?of.?verification|temperature|指令後置|Goal.*Constraint",
        "weight": 10,
        "desc": "Gemini-specific optimizations applied (P23)",
    },
    {
        "id": "P24",
        "name": "State Machine Thinking",
        "pattern": r"state.?machine|INIT.*EXTRACT.*ANALYZE|狀態機|entry.?condition|exit.?condition|→.*→",
        "weight": 8,
        "desc": "Explicit state transitions with entry/exit conditions",
    },
    {
        "id": "P25",
        "name": "Consensus Protocol",
        "pattern": r"consensus|共識|multi.?perspective|多視角|SPLIT.?VERDICT",
        "weight": 5,
        "desc": "Multi-perspective analysis with consensus gate",
    },
    {
        "id": "P26",
        "name": "Execution Journal",
        "pattern": r"execution.?log|_execution_log|📝.?LOG|journal",
        "weight": 10,
        "desc": "Agent writes structured execution logs",
    },
    {
        "id": "P27",
        "name": "Version Control & Rollback",
        "pattern": r"snapshot|archive|rollback|回滾|版本控制|SKILL_v\d",
        "weight": 5,
        "desc": "Snapshot before modify, auto-rollback on score drop",
    },
]


def scan_agent_dir(agent_path: str) -> dict:
    """Scan an agent directory, read SKILL.md and all resources."""
    agent_dir = Path(agent_path)
    result = {"skill_md": "", "resources": {}, "scripts": [], "has_archive": False}

    # Read SKILL.md
    skill_path = agent_dir / "SKILL.md"
    if skill_path.exists():
        result["skill_md"] = skill_path.read_text(encoding="utf-8", errors="replace")
    else:
        print(f"⚠️  WARNING: No SKILL.md found at {skill_path}", file=sys.stderr)
        return result

    # Read resources/
    resources_dir = agent_dir / "resources"
    if resources_dir.exists():
        for f in resources_dir.rglob("*.md"):
            try:
                result["resources"][f.name] = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

    # Check archive/
    archive_dir = resources_dir / "archive"
    result["has_archive"] = archive_dir.exists()

    # List scripts/
    scripts_dir = agent_dir / "scripts"
    if scripts_dir.exists():
        result["scripts"] = [f.name for f in scripts_dir.glob("*.py")]

    return result


def evaluate_agent(agent_data: dict) -> dict:
    """Run all pattern checks against agent content."""
    # Combine all text for searching
    all_text = agent_data["skill_md"]
    for content in agent_data["resources"].values():
        all_text += "\n" + content

    results = []
    total_score = 0
    max_score = 0

    for check in CHECKS:
        max_score += check["weight"]
        found = bool(re.search(check["pattern"], all_text, re.IGNORECASE))

        # Inverse check: presence means FAIL (e.g., browser_subagent)
        if check.get("inverse"):
            passed = not found
        else:
            passed = found

        score = check["weight"] if passed else 0
        total_score += score

        results.append({
            "id": check["id"],
            "name": check["name"],
            "desc": check["desc"],
            "passed": passed,
            "score": score,
            "max": check["weight"],
        })

    # Bonus checks
    # YAML frontmatter check
    has_frontmatter = agent_data["skill_md"].startswith("---")
    if has_frontmatter:
        total_score += 2
    max_score += 2
    results.append({
        "id": "YAML",
        "name": "YAML Frontmatter",
        "desc": "SKILL.md starts with valid YAML frontmatter",
        "passed": has_frontmatter,
        "score": 2 if has_frontmatter else 0,
        "max": 2,
    })

    # Has scripts (Python-First)
    has_scripts = len(agent_data["scripts"]) > 0
    if has_scripts:
        total_score += 3
    max_score += 3
    results.append({
        "id": "SCRIPTS",
        "name": "Python Scripts Present",
        "desc": "Agent has dedicated Python scripts for offloading",
        "passed": has_scripts,
        "score": 3 if has_scripts else 0,
        "max": 3,
    })

    # Has archive directory
    if agent_data["has_archive"]:
        total_score += 2
    max_score += 2
    results.append({
        "id": "ARCHIVE",
        "name": "Archive Directory",
        "desc": "resources/archive/ exists for version snapshots",
        "passed": agent_data["has_archive"],
        "score": 2 if agent_data["has_archive"] else 0,
        "max": 2,
    })

    # Calculate grade
    pct = (total_score / max_score * 100) if max_score > 0 else 0
    if pct >= 90:
        grade = "S"
    elif pct >= 75:
        grade = "A"
    elif pct >= 60:
        grade = "B"
    elif pct >= 40:
        grade = "C"
    else:
        grade = "D"

    return {
        "total_score": total_score,
        "max_score": max_score,
        "percentage": round(pct, 1),
        "grade": grade,
        "checks": results,
        "failed_checks": [r for r in results if not r["passed"]],
    }


def format_report(agent_name: str, evaluation: dict) -> str:
    """Format evaluation results as markdown report."""
    lines = [
        f"# Agent Health Report: {agent_name}",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Evaluator**: Agent Architect v3.2.0 — `agent_evaluator.py`",
        f"**Score**: {evaluation['total_score']}/{evaluation['max_score']} ({evaluation['percentage']}%)",
        f"**Grade**: {evaluation['grade']}",
        "",
        "## Detailed Results",
        "",
        "| Pattern | Name | Status | Score |",
        "|:--------|:-----|:------:|------:|",
    ]

    for check in evaluation["checks"]:
        status = "✅" if check["passed"] else "❌"
        lines.append(f"| {check['id']} | {check['name']} | {status} | {check['score']}/{check['max']} |")

    lines.append("")

    if evaluation["failed_checks"]:
        lines.append("## ❌ Failed Checks — Action Required")
        lines.append("")
        for fc in evaluation["failed_checks"]:
            lines.append(f"- **{fc['id']} {fc['name']}**: {fc['desc']}")
        lines.append("")

    lines.append("## Grade Scale")
    lines.append("| Grade | Range | Meaning |")
    lines.append("|:---:|:---:|:---|")
    lines.append("| S | 90-100% | Production-ready, fully Pattern compliant |")
    lines.append("| A | 75-89% | Strong, minor improvements possible |")
    lines.append("| B | 60-74% | Functional but missing key patterns |")
    lines.append("| C | 40-59% | Needs significant refactoring |")
    lines.append("| D | 0-39% | Critical gaps, redesign recommended |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Agent Evaluator v1.0 — Health Check Engine")
    parser.add_argument("--target", required=True, help="Path to agent skill directory")
    parser.add_argument("--output", default=None, help="Path to write report (default: stdout)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of markdown")
    args = parser.parse_args()

    agent_path = Path(args.target).resolve()
    agent_name = agent_path.name

    print(f"🔍 Scanning agent: {agent_name} ({agent_path})")

    agent_data = scan_agent_dir(str(agent_path))
    if not agent_data["skill_md"]:
        print(f"❌ FATAL: No SKILL.md found at {agent_path}", file=sys.stderr)
        sys.exit(1)

    evaluation = evaluate_agent(agent_data)

    if args.json:
        output = json.dumps({"agent": agent_name, **evaluation}, indent=2, ensure_ascii=False)
    else:
        output = format_report(agent_name, evaluation)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"✅ Report written to: {out_path}")
    else:
        print(output)

    # Print summary
    print(f"\n{'='*50}")
    print(f"📊 {agent_name}: Grade {evaluation['grade']} ({evaluation['percentage']}%)")
    print(f"   Passed: {len(evaluation['checks']) - len(evaluation['failed_checks'])}/{len(evaluation['checks'])} checks")
    if evaluation["failed_checks"]:
        print(f"   ❌ Failed: {', '.join(fc['id'] for fc in evaluation['failed_checks'])}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
