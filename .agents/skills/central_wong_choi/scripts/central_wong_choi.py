#!/usr/bin/env python3
"""Central Wong Choi read-only status and scoped release CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
SHARED_SKILLS = REPO_ROOT / ".agents" / "skills"
sys.path.insert(0, str(SHARED_SKILLS))

from shared_wong_choi.central_status import collect_status, render_telegram  # noqa: E402
from shared_wong_choi.release_approval import approve_release  # noqa: E402
from shared_wong_choi.release_activation import activate_release  # noqa: E402
from shared_wong_choi.release_manager import (  # noqa: E402
    DEFAULT_STATE_ROOT,
    ReleaseError,
    prepare_release,
)
from shared_wong_choi.model_registry import bootstrap_current_models  # noqa: E402
from shared_wong_choi.reliability import collect_reliability, run_restore_drill  # noqa: E402


DEFAULT_CONTROL_ROOT = DEFAULT_STATE_ROOT.parent


def _production_roots() -> dict[str, Path]:
    values = {}
    for domain in ("au", "hkjc", "tennis", "nba"):
        raw = os.environ.get(f"WC_{domain.upper()}_PRODUCTION_ROOT")
        if raw:
            values[domain] = Path(raw)
    return values


def current_status(repo: Path, state_root: Path) -> dict:
    return collect_status(
        repo,
        state_root,
        production_roots=_production_roots(),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(os.environ.get("WC_PRIMARY_REPO_ROOT", REPO_ROOT)),
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT", DEFAULT_CONTROL_ROOT)),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "git", "models", "evidence", "slo"):
        command = sub.add_parser(name)
        command.add_argument("--json", action="store_true")
    release = sub.add_parser("release")
    release.add_argument("--path", action="append", required=True)
    release.add_argument("--message", required=True)
    release.add_argument("--dry-run", action="store_true")
    release.add_argument("--allow-unrelated", action="store_true")
    release.add_argument("--activation-base")
    release.add_argument("--no-notify", action="store_true")
    release.add_argument("--json", action="store_true")
    approve = sub.add_parser("approve")
    approve.add_argument("--commit", required=True)
    approve.add_argument("--actor", required=True)
    approve.add_argument("--dry-run", action="store_true")
    approve.add_argument("--no-notify", action="store_true")
    approve.add_argument("--activate", action="store_true")
    approve.add_argument("--json", action="store_true")
    bootstrap = sub.add_parser("bootstrap-models")
    bootstrap.add_argument("--commit", required=True)
    bootstrap.add_argument("--actor", required=True)
    bootstrap.add_argument("--json", action="store_true")
    restore = sub.add_parser("restore-drill")
    restore.add_argument("--destination", type=Path, required=True)
    restore.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = args.repo.expanduser().resolve()
    state_root = args.state_root.expanduser().resolve()
    if args.command == "release":
        try:
            result = prepare_release(
                repo,
                paths=args.path,
                message=args.message,
                state_root=state_root / "releases",
                dry_run=args.dry_run,
                notify=not args.no_notify,
                allow_unrelated=args.allow_unrelated,
                activation_base=args.activation_base,
            )
        except ReleaseError as exc:
            result = {"status": "blocked", "error": str(exc)}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") != "push_failed" else 1
    if args.command == "approve":
        try:
            result = approve_release(
                repo,
                state_root,
                selector=args.commit,
                actor=args.actor,
                notify=not args.no_notify,
                dry_run=args.dry_run,
            )
        except ReleaseError as exc:
            result = {"status": "blocked", "error": str(exc)}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        if args.activate and not args.dry_run:
            try:
                result["activation_result"] = activate_release(
                    repo,
                    state_root,
                    selector=args.commit,
                    actor=args.actor,
                    production_roots=_production_roots(),
                    notify=not args.no_notify,
                )
            except ReleaseError as exc:
                result["activation_result"] = {
                    "status": "blocked",
                    "error": str(exc),
                }
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "bootstrap-models":
        result = bootstrap_current_models(
            state_root / "evidence",
            code_commit=args.commit,
            approval_id=args.actor,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "restore-drill":
        result = run_restore_drill(state_root, args.destination)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "pass" else 1
    if args.command == "slo":
        result = collect_reliability(state_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "pass" else 1

    status = current_status(repo, state_root)
    views = {
        "status": status,
        "git": status["git"],
        "models": {
            name: value["model_release"] for name, value in status["domains"].items()
        },
        "evidence": status["evidence"],
        "slo": status["reliability"],
    }
    value = views[args.command]
    if args.json or args.command != "status":
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_telegram(status))
    return 0 if status["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
