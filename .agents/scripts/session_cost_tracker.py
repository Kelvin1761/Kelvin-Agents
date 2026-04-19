#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
Session Cost Tracker for Wong Choi Analysis Pipeline
Inspired by ECC cost-aware-llm-pipeline concept.

Tracks token usage, batch efficiency, and estimated costs per analysis session.
Supports all three domains: AU Racing, HKJC Racing, NBA.

Usage:
    python3 .agents/scripts/session_cost_tracker.py "{TARGET_DIR}" --domain au --batch-size 3
    python3 .agents/scripts/session_cost_tracker.py "{TARGET_DIR}" --domain hkjc --batch-size 3
    python3 .agents/scripts/session_cost_tracker.py "{TARGET_DIR}" --domain nba
"""

import argparse
import os
import re
import json
import csv
from pathlib import Path
from datetime import datetime


# --- Constants ---
# Token estimation: ~1.5 tokens per CJK character, ~0.75 tokens per English word
CJK_TOKEN_RATIO = 1.5
EN_TOKEN_RATIO = 0.75

# Cost estimates (USD per 1M tokens) — approximate for Gemini/Claude mixed usage
COST_TABLE = {
    "input_per_1m": 3.00,   # Approximate blended input cost
    "output_per_1m": 15.00, # Approximate blended output cost
}


def count_tokens_estimate(text: str) -> dict:
    """Estimate token count from text content."""
    cjk_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
    en_words = len(re.findall(r'[a-zA-Z]+', text))
    total_chars = len(text)
    
    est_tokens = int(cjk_chars * CJK_TOKEN_RATIO + en_words * EN_TOKEN_RATIO)
    
    return {
        "total_chars": total_chars,
        "cjk_chars": cjk_chars,
        "en_words": en_words,
        "est_tokens": est_tokens,
    }


def scan_au_hkjc(target_dir: str, batch_size: int, domain: str) -> dict:
    """Scan AU or HKJC analysis directory for cost metrics."""
    p = Path(target_dir)
    
    # Find all Analysis.md files
    analysis_files = list(p.glob("*Analysis.md")) + list(p.glob("*Analysis.txt"))
    # Also check Race Analysis subdirectory
    analysis_files += list(p.glob("Race Analysis/*Analysis.md"))
    analysis_files += list(p.glob("Race Analysis/*Analysis.txt"))
    
    if not analysis_files:
        return {"error": "No Analysis files found in target directory."}
    
    total_races = len(analysis_files)
    total_tokens = 0
    total_chars = 0
    race_details = []
    most_expensive = {"race": "", "tokens": 0}
    
    for f in sorted(analysis_files):
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        
        stats = count_tokens_estimate(text)
        total_tokens += stats["est_tokens"]
        total_chars += stats["total_chars"]
        
        # Count batches by looking for BATCH_QA_RECEIPT markers
        batch_count = len(re.findall(r'BATCH_QA_RECEIPT', text))
        # Count horses by looking for rating patterns
        horse_count = len(re.findall(r'⭐\s*(?:最終評級|Final)', text))
        
        race_name = f.stem
        race_info = {
            "race": race_name,
            "horses": horse_count,
            "batches": batch_count,
            "chars": stats["total_chars"],
            "est_tokens": stats["est_tokens"],
        }
        race_details.append(race_info)
        
        if stats["est_tokens"] > most_expensive["tokens"]:
            most_expensive = {"race": race_name, "tokens": stats["est_tokens"]}
    
    # Calculate batch efficiency
    total_batches = sum(r["batches"] for r in race_details)
    total_horses = sum(r["horses"] for r in race_details)
    avg_batches_per_race = round(total_batches / total_races, 1) if total_races > 0 else 0
    
    # Estimate cost
    # Output tokens ≈ analysis content; Input tokens ≈ 2x output (SKILL.md + resources + formguide)
    est_output_tokens = total_tokens
    est_input_tokens = total_tokens * 2
    est_cost = (est_input_tokens / 1_000_000 * COST_TABLE["input_per_1m"] +
                est_output_tokens / 1_000_000 * COST_TABLE["output_per_1m"])
    
    # Session splits
    session_splits = (total_races + 3) // 4  # Every 4 races = 1 session
    
    return {
        "domain": domain.upper(),
        "target_dir": target_dir,
        "timestamp": datetime.now().isoformat(),
        "total_races": total_races,
        "total_horses": total_horses,
        "total_batches": total_batches,
        "batch_size": batch_size,
        "avg_batches_per_race": avg_batches_per_race,
        "session_splits": session_splits,
        "total_chars": total_chars,
        "est_input_tokens": est_input_tokens,
        "est_output_tokens": est_output_tokens,
        "est_total_tokens": est_input_tokens + est_output_tokens,
        "est_cost_usd": round(est_cost, 2),
        "most_expensive_race": most_expensive["race"],
        "most_expensive_tokens": most_expensive["tokens"],
        "race_details": race_details,
    }


def scan_nba(target_dir: str) -> dict:
    """Scan NBA analysis directory for cost metrics."""
    p = Path(target_dir)
    
    # Find analysis files
    game_files = list(p.glob("Game_*_Full_Analysis.*"))
    report_files = list(p.glob("NBA_Analysis_Report.*"))
    all_files = game_files + report_files
    
    if not all_files:
        return {"error": "No NBA analysis files found in target directory."}
    
    total_games = len(game_files)
    total_tokens = 0
    total_chars = 0
    game_details = []
    most_expensive = {"game": "", "tokens": 0}
    
    for f in sorted(all_files):
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        
        stats = count_tokens_estimate(text)
        total_tokens += stats["est_tokens"]
        total_chars += stats["total_chars"]
        
        # Count legs/combos
        leg_count = len(re.findall(r'Leg \d+', text))
        combo_count = len(re.findall(r'Combo \d+|組合 \d+', text))
        
        game_name = f.stem
        game_info = {
            "game": game_name,
            "legs": leg_count,
            "combos": combo_count,
            "chars": stats["total_chars"],
            "est_tokens": stats["est_tokens"],
        }
        game_details.append(game_info)
        
        if stats["est_tokens"] > most_expensive["tokens"]:
            most_expensive = {"game": game_name, "tokens": stats["est_tokens"]}
    
    est_output_tokens = total_tokens
    est_input_tokens = total_tokens * 2
    est_cost = (est_input_tokens / 1_000_000 * COST_TABLE["input_per_1m"] +
                est_output_tokens / 1_000_000 * COST_TABLE["output_per_1m"])
    
    return {
        "domain": "NBA",
        "target_dir": target_dir,
        "timestamp": datetime.now().isoformat(),
        "total_games": total_games,
        "total_chars": total_chars,
        "est_input_tokens": est_input_tokens,
        "est_output_tokens": est_output_tokens,
        "est_total_tokens": est_input_tokens + est_output_tokens,
        "est_cost_usd": round(est_cost, 2),
        "most_expensive_game": most_expensive["game"],
        "most_expensive_tokens": most_expensive["tokens"],
        "game_details": game_details,
    }


def format_report(data: dict) -> str:
    """Format the cost report for terminal output."""
    if "error" in data:
        return f"❌ {data['error']}"
    
    domain = data["domain"]
    lines = [
        f"",
        f"📊 SESSION COST REPORT ({domain})",
        f"{'=' * 50}",
        f"📅 Timestamp: {data['timestamp']}",
        f"📁 Directory: {data['target_dir']}",
        f"",
    ]
    
    if domain in ("AU", "HKJC"):
        lines += [
            f"🏇 Total Races: {data['total_races']}",
            f"🐴 Total Horses: {data['total_horses']}",
            f"📦 Total Batches: {data['total_batches']}",
            f"📏 Batch Size: {data['batch_size']}",
            f"📊 Avg Batches/Race: {data['avg_batches_per_race']}",
            f"🔀 Session Splits: {data['session_splits']}",
            f"",
        ]
    else:  # NBA
        lines += [
            f"🏀 Total Games: {data['total_games']}",
            f"",
        ]
    
    lines += [
        f"📝 Total Characters: {data['total_chars']:,}",
        f"🔢 Est. Input Tokens: ~{data['est_input_tokens']:,}",
        f"🔢 Est. Output Tokens: ~{data['est_output_tokens']:,}",
        f"🔢 Est. Total Tokens: ~{data['est_total_tokens']:,}",
        f"💰 Est. Cost: ${data['est_cost_usd']:.2f} USD",
        f"",
    ]
    
    if domain in ("AU", "HKJC"):
        lines.append(f"🔥 Most Expensive Race: {data['most_expensive_race']} (~{data['most_expensive_tokens']:,} tokens)")
    else:
        lines.append(f"🔥 Most Expensive Game: {data['most_expensive_game']} (~{data['most_expensive_tokens']:,} tokens)")
    
    lines.append(f"{'=' * 50}")
    
    return "\n".join(lines)


def save_csv(data: dict, target_dir: str):
    """Append cost report to CSV history file."""
    csv_path = Path(target_dir) / "_cost_history.csv"
    is_new = not csv_path.exists()
    
    row = {
        "timestamp": data.get("timestamp", ""),
        "domain": data.get("domain", ""),
        "total_items": data.get("total_races", data.get("total_games", 0)),
        "total_chars": data.get("total_chars", 0),
        "est_total_tokens": data.get("est_total_tokens", 0),
        "est_cost_usd": data.get("est_cost_usd", 0),
    }
    
    try:
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if is_new:
                writer.writeheader()
            writer.writerow(row)
        print(f"📝 Cost history saved to: {csv_path}")
    except Exception as e:
        print(f"⚠️ Could not save CSV: {e}")


def main():
    parser = argparse.ArgumentParser(description="Wong Choi Session Cost Tracker")
    parser.add_argument("target_dir", type=str, help="Path to analysis target directory")
    parser.add_argument("--domain", type=str, choices=["au", "hkjc", "nba"], required=True,
                        help="Analysis domain")
    parser.add_argument("--batch-size", type=int, default=3,
                        help="Batch size used in session (AU/HKJC only)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    if not os.path.isdir(args.target_dir):
        print(f"❌ Directory not found: {args.target_dir}")
        return
    
    # Scan based on domain
    if args.domain in ("au", "hkjc"):
        data = scan_au_hkjc(args.target_dir, args.batch_size, args.domain)
    else:
        data = scan_nba(args.target_dir)
    
    # Output
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(format_report(data))
    
    # Save CSV history
    if "error" not in data:
        save_csv(data, args.target_dir)


if __name__ == "__main__":
    main()
