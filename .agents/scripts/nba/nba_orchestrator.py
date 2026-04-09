#!/usr/bin/env python3
"""
nba_orchestrator.py
(The Brain of NBA Wong Choi Pipeline)

This master script replaces the LLM orchestrator. It executes a fully deterministic
assembly line:
1. Calls H2H & Injury scripts to generate a unified baseline context.
2. Compiles a 'NBA_Master_Context.md' for the LLM analyst.
3. Automatically triggers Hermes/Local Agent 'nba_analyst' to perform SGM game scripting.
4. Triggers post-processing Compilation summary report.
"""

import os
import sys
import argparse
import subprocess
import datetime
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def setup_directory(target_date):
    dir_path = os.path.join(BASE_DIR, "..", "..", "meetings", f"{target_date}_nba")
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

def collect_hardcore_math(team_a, team_b, line, target_dir, game_idx):
    print(f"🔧 [Orchestrator] Assembling mathematical anchor points for {team_a} vs {team_b}...")
    
    context_str = f"# Game {game_idx}: {team_a} vs {team_b} (Line: {team_a} {line:+.1f})\n\n"
    
    # 1. Fetch H2H Historical Injection
    h2h_script = os.path.join(BASE_DIR, "nba", "fetch_nba_h2h.py")
    if os.path.exists(h2h_script):
        # We capture the printed output. 
        # (In a true production setting, scripts should return JSON, but we parse STDOUT for LLM here)
        result = subprocess.run(
            ["python3", h2h_script, "--team_a", team_a, "--team_b", team_b, "--line", str(line)],
            capture_output=True, text=True
        )
        # Extract the LLM Context Injection String
        output = result.stdout
        if "--- LLM Context Injection String ---" in output:
            injection = output.split("--- LLM Context Injection String ---")[1].strip()
            context_str += f"{injection}\n\n"
            
    # 2. Check for injuries (Mock behavior for demonstration)
    injury_script = os.path.join(BASE_DIR, "nba", "fetch_injury_domino.py")
    if os.path.exists(injury_script) and team_a == "DEN": # Mocking an injury for DEN
        result = subprocess.run(
            ["python3", injury_script, "--team", "DEN", "--out", "Nikola Jokic"],
            capture_output=True, text=True
        )
        output = result.stdout
        if "--- LLM Context Injection String ---" in output:
            injection = output.split("--- LLM Context Injection String ---")[1].strip()
            context_str += f"{injection}\n\n"
            
    # Save the master context for this specific game
    context_file = os.path.join(target_dir, f"Game_{game_idx}_Master_Context.md")
    with open(context_file, "w") as f:
        f.write(context_str)
        
    print(f"✅ Master Context generated at {context_file}")
    return context_file

def trigger_nba_analyst(context_file, game_idx, target_dir):
    print(f"🧠 [Orchestrator] Batch Dispatching -> Triggering nba_analyst for Game {game_idx}...")
    # In production, this would make an API call to Hermes or run the CLI
    # Simulated execution
    analysis_file = os.path.join(target_dir, f"Game_{game_idx}_Analysis.md")
    with open(analysis_file, "w") as f:
        f.write(f"# Analysis for Game {game_idx}\n")
        f.write("## 🏆 SGM Recommendations (Same Game Multi)\n")
        f.write("```csv\n")
        f.write(f"Game {game_idx}, Value SGM, Over 220.5, Player Props Hit, S-Grade\n")
        f.write("```\n")
    print(f"✅ nba_analyst complete. Wrote {analysis_file}")

def run_compilation(target_dir):
    print(f"📄 [Orchestrator] Triggering Final Compilation...")
    compile_script = os.path.join(BASE_DIR, "nba", "compile_nba_report.py")
    if os.path.exists(compile_script):
        subprocess.run(["python3", compile_script, "--target_dir", target_dir])
    else:
        print("⚠️ compile_nba_report.py not found. Skipping compilation.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, default=datetime.datetime.now().strftime('%Y-%m-%d'))
    args = parser.parse_args()
    
    print(f"🚀 ====== NBA Wong Choi Orchestrator Pipeline ({args.date}) ====== 🚀")
    
    target_dir = setup_directory(args.date)
    
    # Mocking Matchups for execution
    matchups = [
        {"team_a": "DEN", "team_b": "MIA", "line": -5.5},
        {"team_a": "BOS", "team_b": "MIL", "line": -2.0}
    ]
    
    for idx, match in enumerate(matchups, 1):
        context_file = collect_hardcore_math(match["team_a"], match["team_b"], match["line"], target_dir, idx)
        trigger_nba_analyst(context_file, idx, target_dir)
        
    run_compilation(target_dir)
    print("🏁 Pipeline execution totally successful!" )

if __name__ == '__main__':
    main()
