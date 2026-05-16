import os
import json
import re
from collections import defaultdict
from datetime import datetime

SEASONS = [
    'archive race analysis/hkjc results 2025 26',
    'archive race analysis/hkjc results 2024 25'
]

def analyze_advanced():
    stats = {
        'venues': {
            '沙田': {'total_races': 0, 'leader_wins': 0, 'closer_wins': 0, 'mid_wins': 0},
            '跑馬地': {'total_races': 0, 'leader_wins': 0, 'closer_wins': 0, 'mid_wins': 0}
        },
        'sire_stats': defaultdict(int),
        'debut_stats': {
            'total': 0,
            'winners': 0,
            'top3': 0,
            'trainer_debut_wins': defaultdict(int),
            'sire_debut_wins': defaultdict(int)
        },
        'jockey_incidents': defaultdict(int)
    }

    horse_first_date = {} 
    all_races = []

    # Collect all data
    for season_path in SEASONS:
        if not os.path.exists(season_path): continue
        for root, dirs, files in os.walk(season_path):
            date_str = os.path.basename(root)
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            except: continue
            
            for file in files:
                if file.endswith('_全日賽果.json'):
                    venue = '沙田' if '沙田' in file else '跑馬地'
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        try:
                            day_data = json.load(f)
                            for race_no, race in day_data.items():
                                race['date_obj'] = date_obj
                                race['venue'] = venue
                                all_races.append(race)
                        except: pass

    # Sort races by date
    all_races.sort(key=lambda x: x['date_obj'])

    luck_keywords = ['受困', '無路可上', '勒避', '受擠碰', '走外疊', '望空', '受阻', '不平衡', '擠迫']

    for race in all_races:
        venue = race['venue']
        
        # Result mapping for incidents
        horse_to_jockey = {h['horse_name']: h['jockey'] for h in race.get('results', [])}
        
        # Winner info
        if race.get('results'):
            winner = race['results'][0]
            pos_str = winner.get('running_positions', '')
            # Split by space
            positions = pos_str.split()
            if positions:
                try:
                    first_pos = int(positions[0])
                    stats['venues'][venue]['total_races'] += 1
                    if first_pos <= 2: stats['venues'][venue]['leader_wins'] += 1
                    elif first_pos >= 8: stats['venues'][venue]['closer_wins'] += 1
                    else: stats['venues'][venue]['mid_wins'] += 1
                except: pass
            
            # Winner Sire
            sire_match = re.search(r'父系\s*[:：]\s*(.+)', race.get('bloodline', ''))
            winner_sire = sire_match.group(1).strip() if sire_match else 'Unknown'
            if winner_sire != 'Unknown':
                stats['sire_stats'][winner_sire] += 1

        # Track Debutants
        for h in race.get('results', []):
            h_name = h['horse_name']
            if h_name not in horse_first_date:
                horse_first_date[h_name] = race['date_obj']
                stats['debut_stats']['total'] += 1
                
                if h.get('pos') == '1':
                    stats['debut_stats']['winners'] += 1
                    stats['debut_stats']['trainer_debut_wins'][h.get('trainer', 'Unknown')] += 1
                    # Extract sire for this horse if winner
                    sire_match = re.search(r'父系\s*[:：]\s*(.+)', race.get('bloodline', ''))
                    h_sire = sire_match.group(1).strip() if (h.get('pos') == '1' and sire_match) else 'Unknown'
                    if h_sire != 'Unknown':
                        stats['debut_stats']['sire_debut_wins'][h_sire] += 1
                if h.get('pos') in ['1', '2', '3']:
                    stats['debut_stats']['top3'] += 1

        # Incidents
        for inc in race.get('incident_report', []):
            comment = inc.get('comment', '')
            if any(kw in comment for kw in luck_keywords):
                h_name = inc.get('horse_name')
                jockey = horse_to_jockey.get(h_name, 'Unknown')
                if jockey != 'Unknown':
                    stats['jockey_incidents'][jockey] += 1

    with open('scratch/advanced_analysis_results.json', 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Advanced Analysis (v4 - Bugfix) Complete.")
