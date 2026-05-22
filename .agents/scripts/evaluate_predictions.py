#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from racing_observability import attach_results_and_evaluate


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach local race results and build evaluation_summary.json")
    parser.add_argument("meeting_dir", help="Meeting directory containing racing_run_log.jsonl")
    parser.add_argument("--platform", required=True, choices=["HKJC", "AU"], help="Racing platform")
    parser.add_argument("--run-id", help="Optional run id to evaluate")
    parser.add_argument("--scoring-profile", default="baseline", help="Scoring profile label for the evaluation event")
    parser.add_argument("--json", action="store_true", help="Print evaluation JSON")
    args = parser.parse_args()

    evaluation = attach_results_and_evaluate(
        Path(args.meeting_dir).resolve(),
        args.platform,
        run_id=args.run_id,
        scoring_profile=args.scoring_profile,
    )
    if not evaluation:
        raise SystemExit(1)

    if args.json:
        print(json.dumps(evaluation, ensure_ascii=False, indent=2))
        return

    summary_path = Path(args.meeting_dir).resolve() / "evaluation_summary.json"
    print(f"✅ Evaluation summary written: {summary_path}")


if __name__ == "__main__":
    main()
