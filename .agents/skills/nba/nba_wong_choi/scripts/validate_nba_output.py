"""NBA publication firewall (CLI + the dashboard's import path).

The checks live in nba_engine.publish: report/sidecar binding, live SGM quote >= 2.0 bound
to the legs, offered milestone overs, current availability and roster. This file keeps
the path and `validate_file` signature the dashboard exporter loads.

usage: python3 validate_nba_output.py <Game_*_Full_Analysis.md | directory> [--odds <json>]
exit 0 = all pass, 1 = any blocked.
"""
import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from nba_engine.publish import validate  # noqa: E402


def find_odds_json(report_path):
    match = re.search(r"Game_([A-Z]+_[A-Z]+)_Full_Analysis", os.path.basename(report_path))
    path = match and os.path.join(os.path.dirname(report_path), f"Sportsbet_Odds_{match.group(1)}.json")
    return path if path and os.path.exists(path) else None


def validate_file(filepath, odds_json_path=None, *, now=None):
    passed, blocks = validate(filepath, odds_json_path or find_odds_json(filepath), now=now)
    return {"file": filepath, "passed": passed, "blocks": blocks, "warnings": [], "total_issues": len(blocks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--odds")
    args = parser.parse_args()
    files = ([args.path] if os.path.isfile(args.path)
             else sorted(glob.glob(os.path.join(args.path, "Game_*_Full_Analysis.md"))))
    if not files:
        print(f"no Game_*_Full_Analysis.md at {args.path}")
        return 2
    blocked = False
    for path in files:
        result = validate_file(path, args.odds)
        blocked |= not result["passed"]
        print(f"{'✅ PASS' if result['passed'] else '❌ BLOCKED'} {os.path.basename(path)}")
        for block in result["blocks"]:
            print(f"   {block}")
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
