import os
import json
import re
from collections import defaultdict
from datetime import datetime

CACHE_PATH = 'scratch/horse_metadata_cache.json'
SEASONS = [
    'archive race analysis/hkjc results 2025 26',
    'archive race analysis/hkjc results 2024 25'
]

def load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def analyze_advanced_v5():
    metadata = load_cache()
    stats = {
        'debut': {
            'total': 0,
            'winners': 0,
            'import_type': defaultdict(lambda: {'total': 0, 'wins': 0}),
            'origin': defaultdict(lambda: {'total': 0, 'wins': 0}),
            'dam_sire': defaultdict(lambda: {'total': 0, 'wins': 0}),
            'sire': defaultdict(lambda: {'total': 0, 'wins': 0})
        }
    }

    horse_first_date = {} 
    all_races = []

    # Collect data
    for season in SEASONS:
        if not os.path.exists(season): continue
        for root, _, files in os.walk(season):
            date_str = os.path.basename(root)
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            except: continue
            for file in files:
                if file.endswith('_全日賽果.json'):
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        try:
                            day_data = json.load(f)
                            for r in day_data.values():
                                r['date_obj'] = date_obj
                                all_races.append(r)
                        except: pass

    all_races.sort(key=lambda x: x['date_obj'])

    for race in all_races:
        for h in race.get('results', []):
            h_name = h['horse_name']
            id_match = re.search(r'\(([A-Z]\d+)\)', h_name)
            if not id_match: continue
            hid = id_match.group(1)

            if hid not in horse_first_date:
                horse_first_date[hid] = race['date_obj']
                stats['debut']['total'] += 1
                is_win = (h.get('pos') == '1')
                if is_win: stats['debut']['winners'] += 1
                
                meta = metadata.get(hid, {})
                imp = meta.get('import_type', 'Unknown')
                ori = meta.get('origin', 'Unknown')
                ds = meta.get('dam_sire', 'Unknown')
                s = meta.get('sire', 'Unknown')
                
                if imp != 'Unknown':
                    stats['debut']['import_type'][imp]['total'] += 1
                    if is_win: stats['debut']['import_type'][imp]['wins'] += 1
                
                if ori != 'Unknown':
                    stats['debut']['origin'][ori]['total'] += 1
                    if is_win: stats['debut']['origin'][ori]['wins'] += 1
                
                if ds != 'Unknown':
                    stats['debut']['dam_sire'][ds]['total'] += 1
                    if is_win: stats['debut']['dam_sire'][ds]['wins'] += 1
                    
                if s != 'Unknown':
                    stats['debut']['sire'][s]['total'] += 1
                    if is_win: stats['debut']['sire'][s]['wins'] += 1

    # Convert to sorted lists for report easy consumption
    stats['debut']['origin_rank'] = sorted(stats['debut']['origin'].items(), key=lambda x: x[1]['wins'], reverse=True)
    stats['debut']['import_rank'] = sorted(stats['debut']['import_type'].items(), key=lambda x: x[1]['wins'], reverse=True)
    stats['debut']['sire_rank'] = sorted(stats['debut']['sire'].items(), key=lambda x: x[1]['wins'], reverse=True)[:10]
    stats['debut']['dam_sire_rank'] = sorted(stats['debut']['dam_sire'].items(), key=lambda x: x[1]['wins'], reverse=True)[:10]

    with open('scratch/v5_debut_deep_stats.json', 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"✅ V5 Deep Debut Analysis Complete. Processed {stats['debut']['total']} debutants.")

if __name__ == '__main__':
    analyze_advanced_v5()
