#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
Session State Manager for Wong Choi Pipelines
Usage: 
  python session_state_manager.py --target_dir "/path/to/meeting" --action read
  python session_state_manager.py --target_dir "/path/to/meeting" --action update --key "completed_races" --value "1,2,3"

Allows LLM agents to offload state tracking to a robust JSON file, 
preventing token wastage on re-scanning directories upon session resume.
"""

import argparse
import os
import json

def get_state_path(target_dir):
    return os.path.join(target_dir, '_session_state.json')

def load_state(target_dir):
    state_path = get_state_path(target_dir)
    if os.path.exists(state_path):
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_state(target_dir, data):
    state_path = get_state_path(target_dir)
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def main():
    parser = argparse.ArgumentParser(description="Manage Session State for LLM Pipelines.")
    parser.add_argument('--target_dir', type=str, required=True, help="Directory containing the session file.")
    parser.add_argument('--action', type=str, choices=['read', 'update'], required=True, help="Action to perform.")
    parser.add_argument('--key', type=str, help="State dictionary key to update.")
    parser.add_argument('--value', type=str, help="Value to set for the key.")

    args = parser.parse_args()

    state = load_state(args.target_dir)

    if args.action == 'read':
        if not state:
            print("STATE: EMPTY")
        else:
            for k, v in state.items():
                print(f"[{k}]: {v}")
    elif args.action == 'update':
        if not args.key or args.value is None:
            print("Error: --key and --value required for update action.")
            exit(1)
        
        # If value is a comma-separated list, convert to actual python list
        val = args.value
        if ',' in val:
            val = [x.strip() for x in val.split(',')]
            
        state[args.key] = val
        save_state(args.target_dir, state)
        print(f"✅ State updated: {args.key} = {val}")

if __name__ == '__main__':
    main()
