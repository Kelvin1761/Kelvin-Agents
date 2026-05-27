#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re

from unified_reflector_core import run_unified_reflector


HK_VENUES = {
    "sha tin": "ShaTin",
    "shatin": "ShaTin",
    "sha_tin": "ShaTin",
    "happy valley": "HappyValley",
    "happyvalley": "HappyValley",
}

AU_VENUES = (
    "randwick",
    "flemington",
    "rosehill",
    "rosehill gardens",
    "doomben",
    "eagle farm",
    "caulfield",
    "cranbourne",
    "warwick farm",
    "canterbury",
    "ballarat",
    "hawkesbury",
    "pakenham",
    "geelong",
    "sandown",
    "gosford",
    "sale",
    "gold coast",
)


def _extract_request_parts(request: str) -> dict:
    text = " ".join(request.split())
    lower = text.lower()

    platform = None
    if re.search(r"\b(hkjc|hong kong|hk)\b", lower) or any(token in lower for token in HK_VENUES):
        platform = "hkjc"
    elif re.search(r"\b(au|australia|australian|racenet)\b", lower) or any(token in lower for token in AU_VENUES):
        platform = "au"

    date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    race_match = re.search(r"\brace\s*(\d{1,2})\b", lower)
    url_match = re.search(r"https?://\S+", text)

    venue = None
    for key, value in HK_VENUES.items():
        if key in lower:
            venue = value
            platform = platform or "hkjc"
            break
    if venue is None:
        for token in AU_VENUES:
            if token in lower:
                venue = token.title() if token != "rosehill gardens" else "Rosehill Gardens"
                platform = platform or "au"
                break

    meeting = None
    if platform == "hkjc" and date_match and venue:
        meeting = f"{date_match.group(1)}_{venue}"
    elif platform == "au" and date_match and venue:
        meeting = f"{date_match.group(1)} {venue}"

    return {
        "platform": platform,
        "meeting": meeting,
        "race": int(race_match.group(1)) if race_match else None,
        "results_url": url_match.group(0) if url_match else None,
        "date": date_match.group(1) if date_match else None,
        "venue": venue,
    }


def _merge_request_args(args: argparse.Namespace) -> argparse.Namespace:
    request_text = " ".join(args.request or []).strip()
    if not request_text:
        return args

    parsed = _extract_request_parts(request_text)
    if not args.platform:
        args.platform = parsed["platform"]
    if not args.meeting and not args.meeting_dir:
        args.meeting = parsed["meeting"]
    if not args.results_url:
        args.results_url = parsed["results_url"]
    if parsed["race"] is not None and not args.races:
        args.races = [parsed["race"]]
    return args


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified AU / HKJC race reflector workflow")
    parser.add_argument("--platform", choices=("au", "hkjc"))
    parser.add_argument("--meeting", help="Meeting folder name or unique substring under the archive root")
    parser.add_argument("--meeting-dir", help="Explicit meeting directory path")
    parser.add_argument("--results-file", help="Use an existing results file instead of extracting")
    parser.add_argument("--results-url", help="Result website URL used for extraction when no local results file exists")
    parser.add_argument("--race", dest="races", action="append", type=int, help="Reflect a specific race number; repeat for multiple races")
    parser.add_argument("--report-path", help="Optional markdown output path")
    parser.add_argument("--force-extract", action="store_true", help="Force results extraction even if a local results file already exists")
    parser.add_argument("--skip-backtest", action="store_true", help="Skip archive backtest / candidate testing")
    parser.add_argument("--json", action="store_true", help="Print the final summary as JSON")
    parser.add_argument("request", nargs="*", help="Optional freeform request, e.g. reflect HKJC Sha Tin 2026-05-20 race 3")
    args = parser.parse_args()
    args = _merge_request_args(args)

    if not args.platform:
        raise SystemExit("❌ 請提供 `--platform`，或者用 freeform request 包含 HKJC / AU。")
    if not args.meeting and not args.meeting_dir:
        raise SystemExit("❌ 請提供 `--meeting` / `--meeting-dir`，或者喺 freeform request 入面包含日期 + 場地。")

    summary = run_unified_reflector(
        platform=args.platform,
        meeting_ref=args.meeting,
        meeting_dir=args.meeting_dir,
        results_file=args.results_file,
        results_url=args.results_url,
        target_races=args.races,
        report_path=args.report_path,
        force_extract=args.force_extract,
        skip_backtest=args.skip_backtest,
    )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("\n🏁 Unified race reflector complete")
        print(f"- Platform: {summary['platform']}")
        print(f"- Meeting: {summary['meeting_dir']}")
        print(f"- Results: {summary['results_file']}")
        print(f"- Report: {summary['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
