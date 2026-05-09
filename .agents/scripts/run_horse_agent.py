#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _die(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _instruction_block(args, backend: str) -> str:
    return f"""
RACING HORSE AGENT INSTRUCTION
backend={backend}
domain={args.domain}
target_dir={args.target_dir}
race={args.race}
horse={args.horse}
workcard={args.workcard}
logic_json={args.logic_json}

Execute manually:
1. Read the WorkCard only.
2. Update Logic.json horses.{args.horse} only.
3. Preserve locked fields and Python-computed fields.
4. Do not fabricate missing evidence.
5. Re-run LangGraph/orchestrator so Python validation checks the result.
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="External racing horse-agent bridge")
    parser.add_argument("--domain", choices=["au", "hkjc"], required=True)
    parser.add_argument("--target-dir", required=True)
    parser.add_argument("--race", type=int, required=True)
    parser.add_argument("--horse", type=int, required=True)
    parser.add_argument("--workcard", required=True)
    parser.add_argument("--logic-json", required=True)
    args = parser.parse_args()

    for path_name in ("target_dir", "workcard", "logic_json"):
        path = Path(getattr(args, path_name))
        if not path.exists():
            _die(f"{path_name} does not exist: {path}")

    workcard_text = Path(args.workcard).read_text(encoding="utf-8")
    if not workcard_text.strip():
        _die(f"WorkCard is empty: {args.workcard}")

    with open(args.logic_json, "r", encoding="utf-8") as f:
        logic = json.load(f)
    horse_entry = logic.get("horses", {}).get(str(args.horse))
    if not isinstance(horse_entry, dict):
        _die(f"Logic.json missing horses.{args.horse}")
    for locked in ("_locked", "_validation_nonce", "horse_name"):
        if locked not in horse_entry:
            _die(f"Logic.json horses.{args.horse} missing locked field: {locked}")

    backend = os.environ.get("HORSE_AGENT_BACKEND", "manual").strip().lower()
    if backend not in {"antigravity", "codex", "manual"}:
        _die(f"Unsupported HORSE_AGENT_BACKEND={backend!r}")

    print(_instruction_block(args, backend))
    print("\nNo real callable backend is implemented yet. Refusing to fake analysis.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
