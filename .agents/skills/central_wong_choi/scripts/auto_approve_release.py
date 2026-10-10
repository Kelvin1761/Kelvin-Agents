#!/usr/bin/env python3
"""Resume an immutable queued release under the user's delegated approval."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.release_automation import auto_approve_release  # noqa: E402
from shared_wong_choi.release_manager import ReleaseError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--state-root", type=Path, default=Path(os.environ.get(
        "WONGCHOI_CONTROL_STATE_ROOT", Path.home() / "WongChoiData/WongChoiControl")))
    parser.add_argument("--commit", required=True)
    parser.add_argument("--expected-result", action="append", default=[])
    parser.add_argument("--no-notify", action="store_true")
    args = parser.parse_args()
    try:
        result = auto_approve_release(
            args.repo.expanduser().resolve(), args.state_root.expanduser().resolve(),
            selector=args.commit, notify=not args.no_notify,
            expected_results=tuple(args.expected_result),
        )
    except ReleaseError as exc:
        result = {"automation_status": "blocked", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["automation_status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
