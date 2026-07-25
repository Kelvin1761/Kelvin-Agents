#!/usr/bin/env python3
"""Export and optionally apply results-backed NBA/Tennis settlements.

Only records produced by the native Tennis settlement tables or NBA Reflector
Results Brief are submitted.  The Cloudflare endpoint matches them to user
bets by immutable source recommendation ID and applies the user's own odds and
stake.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


DASHBOARD_DIR = Path(__file__).resolve().parent
REPO_ROOT = DASHBOARD_DIR.parent
BACKEND_DIR = DASHBOARD_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.settlement_exporter import (  # noqa: E402
    export_nba_settlements,
    export_tennis_settlements,
)


def _latest_nba_results_dir(repo_root: Path) -> Optional[Path]:
    candidates = [
        path
        for path in repo_root.glob("????-??-?? NBA Analysis")
        if path.is_dir() and any(path.glob("Results_Brief_*.json"))
    ]
    return sorted(candidates, reverse=True)[0] if candidates else None


def build_settlement_batch(
    repo_root: Path,
    target_date: Optional[str] = None,
    tennis_db: Optional[Path] = None,
    nba_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    repo_root = Path(repo_root)
    tennis_path = Path(tennis_db) if tennis_db else repo_root / "tennis-wong-choi" / "tennis_wc.db"
    nba_path = Path(nba_dir) if nba_dir else _latest_nba_results_dir(repo_root)
    tennis = export_tennis_settlements(tennis_path, target_date)
    nba = (
        export_nba_settlements(nba_path)
        if nba_path
        else {
            "sport": "nba",
            "validation_status": "unavailable",
            "settlements": [],
            "warnings": ["nba_results_brief_not_found"],
        }
    )
    settlements: List[Dict[str, Any]] = []
    settlements.extend(tennis.get("settlements") or [])
    settlements.extend(nba.get("settlements") or [])
    return {
        "settlements": settlements,
        "sources": {"tennis": tennis, "nba": nba},
        "summary": {
            "total": len(settlements),
            "tennis": len(tennis.get("settlements") or []),
            "nba": len(nba.get("settlements") or []),
        },
    }


def apply_batch(payload: Dict[str, Any], endpoint: str, token: str = "") -> Dict[str, Any]:
    request_payload = json.dumps({"settlements": payload.get("settlements") or []}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "wongchoi-settlement-exporter/1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(endpoint, data=request_payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"settlement endpoint HTTP {error.code}: {detail}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Tennis match_date filter (YYYY-MM-DD)")
    parser.add_argument("--tennis-db", type=Path)
    parser.add_argument("--nba-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verbose", action="store_true", help="Print the full proposal payload")
    parser.add_argument("--apply", action="store_true", help="POST verified proposals to the dashboard")
    parser.add_argument(
        "--endpoint",
        default=os.environ.get(
            "WC_SETTLEMENT_ENDPOINT",
            "https://wongchoi-dashboard.pages.dev/api/settlements",
        ),
    )
    args = parser.parse_args()

    payload = build_settlement_batch(
        REPO_ROOT,
        target_date=args.date,
        tennis_db=args.tennis_db,
        nba_dir=args.nba_dir,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    if args.verbose:
        print(rendered)
    else:
        print(json.dumps(payload["summary"], ensure_ascii=False))

    if not args.apply:
        return 0
    if not payload["settlements"]:
        print("ℹ️ 未有可安全自動結算嘅新賽果。")
        return 0
    result = apply_batch(payload, args.endpoint, os.environ.get("WC_SYNC_TOKEN", ""))
    if args.verbose:
        print(json.dumps({"apply_result": result}, ensure_ascii=False, indent=2))
    else:
        print(
            json.dumps(
                {
                    "success": result.get("success"),
                    "applied": len(result.get("applied") or []),
                    "skipped": len(result.get("skipped") or []),
                },
                ensure_ascii=False,
            )
        )
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
