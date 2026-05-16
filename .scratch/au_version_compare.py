#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
ARCHIVE_ROOT = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing"
OUTPUT_MD = ARCHIVE_ROOT / "AU_Engine_Version_Comparison.md"
OUTPUT_JSON = ARCHIVE_ROOT / "AU_Engine_Version_Comparison.json"

METRICS_SCRIPT = SCRIPT_DIR / "au_version_metrics.py"
MAINLINE_ENGINE_DIR = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"
SHADOW_ENGINE_DIR = SCRIPT_DIR / "shadow_engine"


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def delta_pp(new: float, old: float) -> str:
    delta = (new - old) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f}pp"


def delta_count(new: int, old: int) -> str:
    delta = new - old
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta}"


def run_metrics(engine_dir: Path, label: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(METRICS_SCRIPT), "--engine-dir", str(engine_dir), "--label", label],
        cwd=str(PROJECT_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def build_metric_row(label: str, legacy: dict, trial: dict, rate_key: str | None = None, count_key: str | None = None) -> str:
    if rate_key:
        old = legacy["rates"][rate_key]
        new = trial["rates"][rate_key]
        return f"| {label} | {pct(old)} | {pct(new)} | {delta_pp(new, old)} |"
    if count_key:
        old = legacy[count_key]
        new = trial[count_key]
        return f"| {label} | {old} | {new} | {delta_count(new, old)} |"
    raise ValueError("Either rate_key or count_key is required")


def build_report(legacy: dict, trial: dict) -> str:
    lines = [
        "# AU Engine Version Comparison",
        "",
        f"- Sample races: **{legacy['races']}**",
        f"- Sample horses: **{legacy['horses']}**",
        f"- Legacy engine: **{legacy['label']}**",
        f"- Trial engine: **{trial['label']}**",
        "",
        "## Recommended Scoreboard",
        "",
        "| 指標 | 原始 (Legacy/Mainline) | 優化後 (SIP-AU-V22 / Shadow) | 改善幅度 |",
        "|---|---:|---:|---:|",
        build_metric_row("🏆 Gold (3/3)", legacy, trial, rate_key="gold_3of3"),
        build_metric_row("✅ Good (Top1+Top2 入前三)", legacy, trial, rate_key="good_top2"),
        build_metric_row("⚠️ Pass (2/3)", legacy, trial, rate_key="pass_2of3"),
        build_metric_row("🥇 Champion", legacy, trial, rate_key="champion"),
        "",
        "## Metric Crosswalk",
        "",
        "| 指標 | Legacy/Mainline | SIP-AU-V22 / Shadow | 改善幅度 |",
        "|---|---:|---:|---:|",
        build_metric_row("Top3 Contains Winner", legacy, trial, rate_key="top3_contains_winner"),
        build_metric_row("Top3 Place Precision", legacy, trial, rate_key="top3_place_precision"),
        build_metric_row("0-hit", legacy, trial, rate_key="zero_hit"),
        "",
        "## Notes",
        "",
        "- `Good` 固定指 Top 1 + Top 2 picks 同時跑入實際前三。",
        "- `Pass (2/3)` 指 Top 3 picks 入面至少 2 隻跑入實際前三。",
        "- 如果之後要用 `SIP-AU-V22` 做正式發布，建議先決定官方到底用邊個 Good 定義，避免報告同實驗表口徑打架。",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    legacy = run_metrics(MAINLINE_ENGINE_DIR, "Legacy/Mainline")
    trial = run_metrics(SHADOW_ENGINE_DIR, "SIP-AU-V22 / Shadow")

    OUTPUT_JSON.write_text(json.dumps({"legacy": legacy, "trial": trial}, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(build_report(legacy, trial), encoding="utf-8")

    print(f"Comparison written: {OUTPUT_MD}")
    print(f"JSON written: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
