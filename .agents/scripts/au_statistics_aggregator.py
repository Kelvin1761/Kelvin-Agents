import os
import glob
import re
import pandas as pd
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING
ARCHIVE_DIR = str(AU_RACING)
OUTPUT_FILE = os.path.join(ARCHIVE_DIR, "AU_Racing_Historical_Stats.md")

def parse_markdown_results():
    all_runs = []
    
    # Find all result files
    result_files = glob.glob(os.path.join(ARCHIVE_DIR, "**", "Race_Results_*.md"), recursive=True)
    
    for file_path in result_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Determine track from filename or content
        filename = os.path.basename(file_path)
        if "Flemington" in filename:
            track = "Flemington"
        elif "Randwick" in filename:
            track = "Randwick"
        else:
            continue # Only focus on Flemington and Randwick as requested
            
        # Extract date from filename (e.g., Race_Results_Flemington_2026-03-28.md)
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
        race_date = date_match.group(1) if date_match else "Unknown"
            
        # Use finditer to keep the race number
        race_blocks = list(re.finditer(r'## Race (\d+):[^\n]*\n([\s\S]*?)(?=## Race \d+:|$)', content))
        
        for match in race_blocks:
            race_num = int(match.group(1))
            race_text = match.group(2)
            
            # Extract distance
            dist_match = re.search(r'\*\*Distance:\*\* (\d+)m', race_text)
            distance = int(dist_match.group(1)) if dist_match else 0
            
            # Extract track condition
            cond_match = re.search(r'\*\*Track:\*\* ([\w\s]+)', race_text)
            condition = cond_match.group(1).strip() if cond_match else "Unknown"
            
            # Find the markdown table
            lines = race_text.strip().split('\n')
            table_lines = [line for line in lines if line.startswith('|') and 'Pos' not in line and '---' not in line]
            
            for line in table_lines:
                cols = [c.strip() for c in line.split('|')[1:-1]]
                if len(cols) >= 10:
                    pos_str = cols[0]
                    # Handle positions like '1', '2', '3= ', 'DNF', etc.
                    try:
                        pos = int(re.sub(r'\D', '', pos_str))
                    except ValueError:
                        pos = 99
                    
                    horse = cols[2]
                    barrier_str = cols[3]
                    try:
                        barrier = int(barrier_str)
                    except ValueError:
                        continue
                        
                    jockey = cols[4]
                    trainer = cols[5]
                    weight = cols[6]
                    margin = cols[7]
                    sp = cols[8]
                    time = cols[9]
                    
                    all_runs.append({
                        'Date': race_date,
                        'Track': track,
                        'Race': race_num,
                        'Distance': distance,
                        'Condition': condition,
                        'Pos': pos,
                        'Horse': horse,
                        'Barrier': barrier,
                        'Weight': weight,
                        'Jockey': jockey,
                        'Trainer': trainer,
                        'Margin': margin,
                        'SP': sp,
                        'Time': time
                    })
                    
    return pd.DataFrame(all_runs)

def generate_report(df):
    if df.empty:
        return "No data found."
        
    report = ["# 🇦🇺 AU Racing Historical Statistics (Flemington & Randwick)\n"]
    report.append("> 這是基於我們剛抓取的 25/26 馬季歷史賽果所進行的統計分析，特別著重於排檔 (Barrier/Draw) 偏差。\n")
    
    csv_data = []
    combo_csv_data = []

    for track in ["Flemington", "Randwick"]:
        track_df = df[df['Track'] == track]
        if track_df.empty:
            continue
            
        report.append(f"## 🏟️ {track} 數據分析")
        report.append(f"**總出賽馬匹數:** {len(track_df)}\n")
        
        # 1. Overall Barrier Stats
        report.append(f"### 🚪 排檔勝率及上名率分析 (Barrier Bias)")
        report.append("計算每個檔位的勝出率 (Win %) 與前三名機率 (Place %)。\n")
        report.append("| Barrier | Total Runs | Wins | Win % | Places (Top 3) | Place % |")
        report.append("|:---|:---|:---|:---|:---|:---|")
        
        barrier_stats = []
        for barrier in sorted(track_df['Barrier'].unique()):
            b_df = track_df[track_df['Barrier'] == barrier]
            runs = len(b_df)
            if runs < 5:  # filter out extreme outliers
                continue
            wins = len(b_df[b_df['Pos'] == 1])
            places = len(b_df[b_df['Pos'] <= 3])
            
            barrier_stats.append({
                'Barrier': barrier,
                'Runs': runs,
                'Wins': wins,
                'Win%': (wins/runs)*100,
                'Places': places,
                'Place%': (places/runs)*100
            })
            
            # Add to CSV Data (Overall)
            csv_data.append({
                'Track': track,
                'Distance': 'Overall',
                'Barrier': barrier,
                'Total Runs': runs,
                'Wins': wins,
                'Win %': f"{(wins/runs)*100:.1f}%",
                'Places (Top 3)': places,
                'Place %': f"{(places/runs)*100:.1f}%"
            })
            
        # Add to CSV Data (By Distance)
        distances = sorted(track_df['Distance'].unique())
        for dist in distances:
            if dist == 0: continue
            dist_df = track_df[track_df['Distance'] == dist]
            for barrier in sorted(dist_df['Barrier'].unique()):
                b_dist_df = dist_df[dist_df['Barrier'] == barrier]
                runs = len(b_dist_df)
                if runs < 3: # Filter tiny samples for specific distance
                    continue
                wins = len(b_dist_df[b_dist_df['Pos'] == 1])
                places = len(b_dist_df[b_dist_df['Pos'] <= 3])
                
                csv_data.append({
                    'Track': track,
                    'Distance': f"{dist}m",
                    'Barrier': barrier,
                    'Total Runs': runs,
                    'Wins': wins,
                    'Win %': f"{(wins/runs)*100:.1f}%",
                    'Places (Top 3)': places,
                    'Place %': f"{(places/runs)*100:.1f}%"
                })

        # Output table
        for bs in barrier_stats:
            report.append(f"| 檔位 {bs['Barrier']} | {bs['Runs']} | {bs['Wins']} | {bs['Win%']:.1f}% | {bs['Places']} | {bs['Place%']:.1f}% |")
        report.append("\n")
        
        # 2. Top Jockeys
        report.append(f"### 🏇 頂級騎師表現 (Top 10 Jockeys by Wins)")
        jockey_stats = track_df[track_df['Pos'] == 1]['Jockey'].value_counts().head(10)
        report.append("| Jockey | Wins | Total Rides | Win % |")
        report.append("|:---|:---|:---|:---|")
        for jockey, wins in jockey_stats.items():
            rides = len(track_df[track_df['Jockey'] == jockey])
            win_pct = (wins/rides)*100
            report.append(f"| {jockey} | {wins} | {rides} | {win_pct:.1f}% |")
        report.append("\n")

        # 3. Top Trainers
        report.append(f"### 🎩 頂級練馬師表現 (Top 10 Trainers by Wins)")
        trainer_stats = track_df[track_df['Pos'] == 1]['Trainer'].value_counts().head(10)
        report.append("| Trainer | Wins | Total Runners | Win % |")
        report.append("|:---|:---|:---|:---|")
        for trainer, wins in trainer_stats.items():
            runners = len(track_df[track_df['Trainer'] == trainer])
            win_pct = (wins/runners)*100
            report.append(f"| {trainer} | {wins} | {runners} | {win_pct:.1f}% |")
        report.append("\n")

        # 4. Top Jockey-Trainer Combos
        report.append(f"### 🤝 最強騎練組合 (Top Jockey-Trainer Combos - Min 5 runs)")
        combo_stats = track_df.groupby(['Jockey', 'Trainer']).size().reset_index(name='Runs')
        combo_stats = combo_stats[combo_stats['Runs'] >= 5]  # filter to meaningful samples
        
        wins = track_df[track_df['Pos'] == 1].groupby(['Jockey', 'Trainer']).size().reset_index(name='Wins')
        places = track_df[track_df['Pos'] <= 3].groupby(['Jockey', 'Trainer']).size().reset_index(name='Places')
        
        combo_stats = pd.merge(combo_stats, wins, on=['Jockey', 'Trainer'], how='left').fillna({'Wins': 0})
        combo_stats = pd.merge(combo_stats, places, on=['Jockey', 'Trainer'], how='left').fillna({'Places': 0})
        
        combo_stats['Win %'] = (combo_stats['Wins'] / combo_stats['Runs'] * 100).round(1)
        combo_stats['Place %'] = (combo_stats['Places'] / combo_stats['Runs'] * 100).round(1)
        
        combo_stats = combo_stats.sort_values(by=['Wins', 'Win %'], ascending=[False, False])
        
        report.append("| Jockey | Trainer | Total Runs | Wins | Win % | Places | Place % |")
        report.append("|:---|:---|:---|:---|:---|:---|:---|")
        for _, row in combo_stats.head(15).iterrows():
            report.append(f"| {row['Jockey']} | {row['Trainer']} | {int(row['Runs'])} | {int(row['Wins'])} | {row['Win %']}% | {int(row['Places'])} | {row['Place %']}% |")
        report.append("\n---\n")
        
        for _, row in combo_stats.iterrows():
            combo_csv_data.append({
                'Track': track,
                'Jockey': row['Jockey'],
                'Trainer': row['Trainer'],
                'Total Runs': int(row['Runs']),
                'Wins': int(row['Wins']),
                'Win %': f"{row['Win %']}%",
                'Places (Top 3)': int(row['Places']),
                'Place %': f"{row['Place %']}%"
            })

    # Export CSV
    csv_df = pd.DataFrame(csv_data)
    csv_out_path = os.path.join(ARCHIVE_DIR, "AU_Barrier_Stats_By_Distance.csv")
    csv_df.to_csv(csv_out_path, index=False, encoding='utf-8-sig')
    print(f"Barrier CSV successfully saved to {csv_out_path}")
    
    combo_csv_df = pd.DataFrame(combo_csv_data)
    combo_csv_out_path = os.path.join(ARCHIVE_DIR, "AU_Jockey_Trainer_Combo_Stats.csv")
    combo_csv_df.to_csv(combo_csv_out_path, index=False, encoding='utf-8-sig')
    print(f"Combo CSV successfully saved to {combo_csv_out_path}")

    return "\n".join(report)

if __name__ == "__main__":
    print("Parsing result files...")
    df = parse_markdown_results()
    print(f"Total records extracted: {len(df)}")
    
    # Export comprehensive raw data
    raw_csv_path = os.path.join(ARCHIVE_DIR, "AU_Historical_Raw_Race_Results.csv")
    df.to_csv(raw_csv_path, index=False, encoding='utf-8-sig')
    print(f"Raw comprehensive data successfully saved to {raw_csv_path}")
    
    print("Generating report...")
    report_md = generate_report(df)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(report_md)
    print(f"Report successfully saved to {OUTPUT_FILE}")
