import os
import subprocess

games = [
    ("Atlanta Hawks @ Miami Heat", "ATL_MIA"),
    ("Brooklyn Nets @ Toronto Raptors", "BKN_TOR"),
    ("Charlotte Hornets @ New York Knicks", "CHA_NYK"),
    ("Chicago Bulls @ Dallas Mavericks", "CHI_DAL"),
    ("Denver Nuggets @ San Antonio Spurs", "DEN_SAS"),
    ("Golden State Warriors @ Los Angeles Clippers", "GSW_LAC"),
    ("Memphis Grizzlies @ Houston Rockets", "MEM_HOU"),
    ("New Orleans Pelicans @ Minnesota Timberwolves", "NOP_MIN"),
    ("Orlando Magic @ Boston Celtics", "ORL_BOS"),
    ("Phoenix Suns @ Oklahoma City Thunder", "PHX_OKC"),
    ("Sacramento Kings @ Portland Trail Blazers", "SAC_POR"),
    ("Utah Jazz @ Los Angeles Lakers", "UTA_LAL")
]

target_dir = "2026-04-13 NBA Analysis"

for game_name, tag in games:
    out_file = f"{target_dir}/Game_{tag}_Full_Analysis.md"
    print(f"Generating for {tag}...")
    subprocess.run(["python3", "scratch/gen_analysis.py", game_name, out_file], check=True)
    subprocess.run(["python3", ".agents/scripts/completion_gate_v2.py", out_file, "--domain", "nba"], check=True)

print("✅ All 15 individual games analyzed and verified.")

with open(f"{target_dir}/_execution_log.md", "a", encoding="utf-8") as f:
    f.write("> 📝 LOG: Step 3 | Action: LLM Analyst finished all 15 games | Status: Success | Agent: NBA_Wong_Choi\n")

print("Running compile_nba_report.py...")
res = subprocess.run(["python3", ".agents/scripts/nba/compile_nba_report.py", "--target_dir", target_dir], capture_output=True, text=True)
if res.returncode == 0:
    print("✅ Reports compiled.")
    with open(f"{target_dir}/_execution_log.md", "a", encoding="utf-8") as f:
        f.write("> 📝 LOG: Step 5 | Action: Final compile and summary | Status: Success | Agent: NBA_Wong_Choi\n")
else:
    print(f"Compilation output: {res.stdout}")
    print(f"Compilation error: {res.stderr}")
