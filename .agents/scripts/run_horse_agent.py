#!/usr/bin/env python3
"""
run_horse_agent.py — Autopilot Bridge Script
==============================================
Command-line bridge for autopilot mode.
Reads a WorkCard + Logic.json, prepares instruction payload for
the configured agent backend, then dispatches or prints instructions.

Exit codes:
  0 = Agent completed successfully
  1 = Fatal error (missing files, invalid data)
  2 = No agent backend configured / manual output required
"""
import os
import sys
import json
import argparse


def validate_paths(args):
    """Validate all required paths exist."""
    errors = []
    if not os.path.isdir(args.target_dir):
        errors.append(f"target-dir not found: {args.target_dir}")
    if not os.path.exists(args.workcard):
        errors.append(f"workcard not found: {args.workcard}")
    if not os.path.exists(args.logic_json):
        errors.append(f"logic-json not found: {args.logic_json}")
    return errors


def build_instruction(args, workcard_content, logic_data):
    """Build the instruction payload for the agent."""
    horse_key = str(args.horse)
    h_entry = logic_data.get('horses', {}).get(horse_key, {})
    h_name = h_entry.get('horse_name', '?')

    instruction = f"""# Agent Task: Analyse Horse #{args.horse} ({h_name})

## Context
- Domain: {args.domain}
- Race: {args.race}
- Horse: #{args.horse} ({h_name})
- Target: {args.logic_json} → horses.{args.horse}

## Instructions
1. Read the WorkCard at: {args.workcard}
2. Read all referenced analyst resources (05_forensic_analysis.md, 03_engine_pace_context.md, etc.)
3. Fill ALL [FILL] fields in the horse entry for horse #{args.horse}
4. Write core_logic with ~100 chars of data-anchored Cantonese analysis
5. Fill all 7 matrix dimensions with scores and reasoning
6. Save the updated Logic.json

## Locked Fields (DO NOT MODIFY)
- horse_name, jockey, trainer, weight, barrier
- last_6_finishes, days_since_last, season_stats
- raw_L400, _validation_nonce

## Quality Requirements
- core_logic must cite actual data (dates, L400 times, margins, positions)
- Matrix reasoning must reference specific evidence
- No generic phrases: 具備一定競爭力, 值得留意, 近期走勢平穩, 有望爭勝
- No placeholders: [FILL], [AUTO], TODO, placeholder, dummy, 待補
"""
    return instruction


def main():
    parser = argparse.ArgumentParser(description="Autopilot Bridge — Horse Agent Dispatcher")
    parser.add_argument("--domain", choices=["hkjc", "au"], required=True)
    parser.add_argument("--target-dir", required=True)
    parser.add_argument("--race", type=int, required=True)
    parser.add_argument("--horse", type=int, required=True)
    parser.add_argument("--workcard", required=True)
    parser.add_argument("--logic-json", required=True)
    parser.add_argument("--allow-manual-output", action="store_true",
                        help="Print instructions and exit 0 instead of 2 when no backend")
    args = parser.parse_args()

    # 1. Validate paths
    errors = validate_paths(args)
    if errors:
        for e in errors:
            print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Read WorkCard
    with open(args.workcard, 'r', encoding='utf-8') as f:
        workcard_content = f.read()

    # 3. Read Logic.json
    with open(args.logic_json, 'r', encoding='utf-8') as f:
        logic_data = json.load(f)

    # 4. Confirm horse entry exists
    horse_key = str(args.horse)
    h_entry = logic_data.get('horses', {}).get(horse_key, {})
    if not h_entry:
        print(f"❌ Horse {args.horse} not found in {args.logic_json}", file=sys.stderr)
        sys.exit(1)

    # 5. Confirm locked fields exist
    locked_fields = ['horse_name', '_validation_nonce']
    for field in locked_fields:
        if field not in h_entry:
            print(f"⚠️ Missing locked field '{field}' for horse {args.horse}", file=sys.stderr)

    # 6. Build instruction
    instruction = build_instruction(args, workcard_content, logic_data)

    # 7. Dispatch to backend
    backend = os.environ.get("HORSE_AGENT_BACKEND", "").lower()

    if backend == "antigravity":
        print("🤖 Backend: Antigravity")
        print("=" * 60)
        print(instruction)
        print("=" * 60)
        if not args.allow_manual_output:
            print("\n⚠️ Antigravity backend requires manual execution. Use --allow-manual-output to suppress this exit code.")
            sys.exit(2)
        sys.exit(0)

    elif backend == "codex":
        print("🤖 Backend: Codex")
        print("=" * 60)
        print(instruction)
        print("=" * 60)
        if not args.allow_manual_output:
            print("\n⚠️ Codex backend requires manual execution. Use --allow-manual-output to suppress this exit code.")
            sys.exit(2)
        sys.exit(0)

    else:
        # No backend configured
        print("=" * 60)
        print("⚠️ HORSE_AGENT_BACKEND not set or unrecognised.")
        print(f"   Supported values: antigravity, codex")
        print(f"   Current value: '{backend or '(not set)'}' ")
        print("=" * 60)
        print("\nInstruction payload for manual execution:")
        print(instruction)
        sys.exit(2)


if __name__ == "__main__":
    main()
