#!/usr/bin/env python3
"""Measure Sportsbet raw-field coverage and current transport gaps from cache."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AU_RACING = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(AU_RACING))

from claw_sportsbet_form import (  # noqa: E402
    parse_race,
    parse_runner_blocks,
    run_line,
    to_text,
)


OLD_INRUN = re.compile(
    r"In running\s+(?:Settled\s+(?P<settled>\w+),\s*)?"
    r"800m\s+(?P<p800>\w+),\s*400m\s+(?P<p400>\w+)",
    re.I,
)
RAW_RUN = re.compile(r"Finished\s+\d+\s*/\s*\d+", re.I)
RAW_WIN_TIME = re.compile(r"Winning Time\s+\d{1,2}:\d{2}\.\d{3}", re.I)


def _pct(value: int, total: int) -> float:
    return round(100.0 * value / total, 2) if total else 0.0


def audit_cache(cache_dir: Path, *, limit: int | None = None) -> dict:
    counts = Counter()
    errors = Counter()
    files = sorted(cache_dir.glob("*.html"))
    if limit:
        files = files[:limit]

    for index, path in enumerate(files, 1):
        try:
            html = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors[type(exc).__name__] += 1
            continue
        counts["cache_files"] += 1
        is_race = 'id="full-form"' in html and "Finished" in html
        is_person = (
            not is_race
            and "Career" in html
            and ("Yearly Breakdown" in html or "Monthly Breakdown" in html)
        )
        if is_person:
            counts["person_pages"] += 1
            for heading, key in (
                ("Yearly Breakdown", "person_yearly_pages"),
                ("Monthly Breakdown", "person_monthly_pages"),
                ("Track Conditions", "person_going_pages"),
                ("Distance", "person_distance_pages"),
                ("Barrier", "person_barrier_pages"),
                ("Field Size", "person_field_size_pages"),
                ("Spells", "person_spell_pages"),
            ):
                if heading in html:
                    counts[key] += 1
            continue
        if not is_race:
            counts["other_pages"] += 1
            continue

        counts["race_pages"] += 1
        text = re.sub(r"\s+", " ", to_text(html))
        counts["raw_runs"] += len(RAW_RUN.findall(text))
        counts["raw_in_running"] += len(re.findall(r"\bIn running\b", text, re.I))
        counts["old_rigid_in_running"] += len(OLD_INRUN.findall(text))
        counts["raw_in_running_1200"] += len(re.findall(
            r"In running\s+.*?1200m\s+\d+(?:st|nd|rd|th)", text, re.I,
        ))
        counts["raw_winning_time"] += len(RAW_WIN_TIME.findall(text))
        counts["raw_foaled"] += len(re.findall(r"\bFoaled:\s*\d{2}/\d{2}/\d{4}", text))
        counts["raw_sire"] += len(re.findall(r"\bSire:\s*[^|\n]{2,80}", text))
        counts["raw_gear"] += len(re.findall(
            r'class="runner-comment".*?\bGear Changes:', html, re.I | re.S,
        ))
        try:
            parsed = parse_race(html)
            blocks = parse_runner_blocks(html, include_runs=False)
        except Exception as exc:  # noqa: BLE001 - audit records, never hides
            errors[f"parse:{type(exc).__name__}"] += 1
            continue
        runs = parsed["runs"]
        counts["parsed_runs"] += len(runs)
        for run in runs:
            position = run.get("pos")
            field = run.get("field")
            if position and field:
                counts["parsed_finish"] += 1
                if 1 <= int(position) <= int(field):
                    counts["valid_finish"] += 1
                if "finish:" in run_line(run)[0]:
                    counts["finish_token_transport"] += 1
                if run.get("is_trial") and int(position) > 3:
                    counts["non_top3_trial_finish"] += 1
            else:
                counts["missing_finish"] += 1
        counts["new_any_in_running"] += sum(
            any(run.get(key) for key in ("settled", "p1200", "p800", "p400"))
            for run in runs
        )
        for key in ("settled", "p1200", "p800", "p400", "winning_time"):
            counts[f"parsed_{key}"] += sum(bool(run.get(key)) for run in runs)
        counts["parsed_race_class_pages"] += bool(
            parsed["meta"].get("race_class")
        )
        counts["runner_blocks"] += len(blocks)
        block_by_name = {
            str(block.get("name") or "").strip().casefold(): block
            for block in blocks
            if str(block.get("name") or "").strip()
        }
        for overview in parsed.get("overview", {}).values():
            if overview.get("scratched"):
                counts["scratched_overview_runners"] += 1
                continue
            counts["active_overview_runners"] += 1
            block = block_by_name.get(
                str(overview.get("name") or "").strip().casefold()
            )
            if not block:
                counts["active_runner_missing_block"] += 1
                continue
            counts["active_runner_block_matched"] += 1
            counts["active_runner_barrier_present"] += block.get("barrier") is not None
            counts["active_runner_weight_present"] += bool(
                (block.get("stats") or {}).get("Weight")
            )
        for key in ("foaled", "sire", "dam", "breeder", "colours", "gear_changes"):
            counts[f"profile_{key}"] += sum(
                bool((block.get("profile") or {}).get(key)) for block in blocks
            )
        if index % 250 == 0:
            print(f"Scanned {index}/{len(files)} cache files", flush=True)

    result = dict(counts)
    result["errors"] = dict(errors)
    result["coverage"] = {
        "raw_run_parse_rate": _pct(result.get("parsed_runs", 0), result.get("raw_runs", 0)),
        "old_rigid_in_running_rate_of_raw": _pct(
            result.get("old_rigid_in_running", 0), result.get("raw_in_running", 0),
        ),
        "new_in_running_rate_of_raw": _pct(
            result.get("new_any_in_running", 0), result.get("raw_in_running", 0),
        ),
        "winning_time_transport_rate": _pct(
            result.get("parsed_winning_time", 0), result.get("raw_winning_time", 0),
        ),
        "runner_sire_rate": _pct(
            result.get("profile_sire", 0), result.get("runner_blocks", 0),
        ),
        "runner_gear_change_rate": _pct(
            result.get("profile_gear_changes", 0), result.get("runner_blocks", 0),
        ),
        "race_class_page_rate": _pct(
            result.get("parsed_race_class_pages", 0), result.get("race_pages", 0),
        ),
        "finish_transport_rate": _pct(
            result.get("finish_token_transport", 0), result.get("parsed_finish", 0),
        ),
        "active_runner_block_match_rate": _pct(
            result.get("active_runner_block_matched", 0),
            result.get("active_overview_runners", 0),
        ),
        "active_runner_barrier_rate": _pct(
            result.get("active_runner_barrier_present", 0),
            result.get("active_overview_runners", 0),
        ),
        "active_runner_weight_rate": _pct(
            result.get("active_runner_weight_present", 0),
            result.get("active_overview_runners", 0),
        ),
    }
    return result


def render_markdown(report: dict) -> str:
    cov = report["coverage"]
    person = report.get("person_pages", 0)
    lines = [
        "# AU Sportsbet Raw Field Audit",
        "",
        f"- Cache files: **{report.get('cache_files', 0)}**",
        f"- Race pages / person pages / other: **{report.get('race_pages', 0)} / "
        f"{person} / {report.get('other_pages', 0)}**",
        f"- Historical runs raw / parsed: **{report.get('raw_runs', 0)} / "
        f"{report.get('parsed_runs', 0)}** ({cov['raw_run_parse_rate']:.2f}%)",
        "",
        "## Extraction recovery",
        "",
        "| Field | Raw | Old parser | New parser | New/raw |",
        "|---|---:|---:|---:|---:|",
        f"| Any in-running checkpoint | {report.get('raw_in_running', 0)} | "
        f"{report.get('old_rigid_in_running', 0)} | {report.get('new_any_in_running', 0)} | "
        f"{cov['new_in_running_rate_of_raw']:.2f}% |",
        f"| 1200m checkpoint | {report.get('raw_in_running_1200', 0)} | 0 | "
        f"{report.get('parsed_p1200', 0)} | "
        f"{_pct(report.get('parsed_p1200', 0), report.get('raw_in_running_1200', 0)):.2f}% |",
        f"| Winning time | {report.get('raw_winning_time', 0)} | 0 | "
        f"{report.get('parsed_winning_time', 0)} | "
        f"{cov['winning_time_transport_rate']:.2f}% |",
        f"| Sire | {report.get('raw_sire', 0)} | 0 | {report.get('profile_sire', 0)} | "
        f"{cov['runner_sire_rate']:.2f}% of runners |",
        f"| Gear changes | {report.get('raw_gear', 0)} | 0 | "
        f"{report.get('profile_gear_changes', 0)} | "
        f"{_pct(report.get('profile_gear_changes', 0), report.get('raw_gear', 0)):.2f}% |",
        "",
        "## Runner and finish alignment",
        "",
        f"- Active overview runners matched to a profile block: "
        f"**{report.get('active_runner_block_matched', 0)} / "
        f"{report.get('active_overview_runners', 0)}** "
        f"({cov['active_runner_block_match_rate']:.2f}%)",
        f"- Active runner barrier / weight coverage: "
        f"**{cov['active_runner_barrier_rate']:.2f}% / "
        f"{cov['active_runner_weight_rate']:.2f}%**",
        f"- Parsed finish rows transported with `finish:N/M`: "
        f"**{report.get('finish_token_transport', 0)} / "
        f"{report.get('parsed_finish', 0)}** ({cov['finish_transport_rate']:.2f}%)",
        f"- Valid finish bounds / missing finish rows: "
        f"**{report.get('valid_finish', 0)} / {report.get('missing_finish', 0)}**",
        f"- Non-top-3 trial placings now preserved: "
        f"**{report.get('non_top3_trial_finish', 0)}**",
        "",
        "## Person-profile data present but not safe for historical backfill",
        "",
        "| Context table | Cached pages containing table | Current use |",
        "|---|---:|---|",
        f"| Distance | {report.get('person_distance_pages', 0)} / {person} | not structured |",
        f"| Barrier | {report.get('person_barrier_pages', 0)} / {person} | not structured |",
        f"| Field size | {report.get('person_field_size_pages', 0)} / {person} | not structured |",
        f"| Spells | {report.get('person_spell_pages', 0)} / {person} | not structured |",
        f"| Monthly trend | {report.get('person_monthly_pages', 0)} / {person} | not structured |",
        "",
        "## Decision",
        "",
        "- In-running checkpoint 係 confirmed parser bug，已修正同 transport。",
        "- Winning time 係 race-level，要先做 track + distance + going 滾動標準化，"
        "未驗證前唔直接入分。",
        "- Pedigree / gear 已保留；gear 只 report，唔用「轉配 = 加分」shortcut。",
        "- 騎練 profile 嘅路程、欄位、馬群大小最有機會解釋 favourite miss，"
        "但 profile 會滾動更新；應從今日起存 versioned captured_at snapshot，"
        "唔可將現時頁面回填舊賽果。",
    ]
    if report.get("errors"):
        lines.extend(["", f"- Parse/read errors: `{report['errors']}`"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir", type=Path,
        default=AU_RACING / ".sportsbet_cache",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--output-json", type=Path,
        default=Path("/private/tmp/au_sportsbet_raw_field_audit.json"),
    )
    parser.add_argument(
        "--output-md", type=Path,
        default=Path("/private/tmp/au_sportsbet_raw_field_audit.md"),
    )
    args = parser.parse_args()
    report = audit_cache(args.cache_dir, limit=args.limit)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    print(args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
