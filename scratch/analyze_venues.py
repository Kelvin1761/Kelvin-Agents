import os
import json
import pandas as pd

def get_venue_comparison():
    base_dir = r'archive race analysis/hkjc results 2025 26'
    all_data = []
    
    # Track config mappings to simplify
    # ST: A, A+3, B, B+2, C, C+3
    # HV: A, B, C, C+3
    
    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path): continue
        
        # We need to be careful with double-saved files for the same date
        # Strategy: Load both ST and HV if they exist, but deduplicate by (date, race_no)
        # If the JSON contains "跑馬地" in the track info, it's HV.
        
        day_results = {} # (race_no) -> info
        
        for f in sorted(os.listdir(folder_path)): # Process files
            if not f.endswith('.json'): continue
            
            with open(os.path.join(folder_path, f), 'r', encoding='utf-8') as jf:
                try:
                    data = json.load(jf)
                    for r_no, r_info in data.items():
                        # Determine real venue from track description or filename
                        track_desc = r_info.get('track', '')
                        # HV track names usually don't have "Sha Tin" and if the filename said HV, we trust it IF it matches a typical HV race count or distance.
                        # Actually, a better way: check distance. HV has 1000, 1200, 1650, 1800, 2200.
                        # ST has 1000, 1200, 1400, 1600, 1800, 2000, 2400.
                        # 1650 is EXCLUSIVELY HV. 1400/1600 are EXCLUSIVELY ST.
                        dist = r_info.get('distance', '')
                        venue = 'UNKNOWN'
                        if '1650' in dist: venue = 'HV'
                        elif '1400' in dist or '1600' in dist: venue = 'ST'
                        elif '跑馬地' in f or 'Happy Valley' in f: venue = 'HV'
                        else: venue = 'ST'
                        
                        if r_no not in day_results:
                            day_results[r_no] = (venue, r_info)
                        else:
                            # If we already have it, and the new one is HV, overwrite if the old one was ST but likely wrong
                            if venue == 'HV' and day_results[r_no][0] == 'ST':
                                day_results[r_no] = (venue, r_info)

                except: continue
        
        for r_no, (venue, r_info) in day_results.items():
            dist = r_info.get('distance', '')
            for res in r_info.get('results', []):
                all_data.append({
                    'date': folder,
                    'race_no': r_no,
                    'venue': venue,
                    'trainer': res.get('trainer'),
                    'jockey': res.get('jockey'),
                    'win': 1 if res.get('pos') == '1' else 0,
                    'place': 1 if res.get('pos') in ['1','2','3'] else 0,
                    'draw': int(res.get('draw', 0)) if res.get('draw') and res.get('draw').isdigit() else 0,
                    'dist': dist,
                    'odds': float(res.get('win_odds', 0)) if res.get('win_odds') else 0
                })

    df = pd.DataFrame(all_data)
    if df.empty: return "No data found."
    
    # 1. Trainer Venue Mastery
    tr_venue = df.groupby(['trainer', 'venue']).agg(W=('win','sum'), S=('win','count')).reset_index()
    tr_venue['WR'] = (tr_venue['W'] / tr_venue['S'] * 100).round(1)
    
    # Pivot to compare
    pivot = tr_venue.pivot(index='trainer', columns='venue', values=['W', 'WR', 'S']).fillna(0)
    
    # Find Specialists (HV WR > ST WR and at least 5 wins at HV)
    hv_spec = pivot[pivot[('W', 'HV')] >= 5].sort_values(('WR', 'HV'), ascending=False).head(10)
    st_spec = pivot[pivot[('W', 'ST')] >= 10].sort_values(('WR', 'ST'), ascending=False).head(10)
    
    # 2. Draw Bias Comparison (1200m)
    draw_1200 = df[df['dist'].str.contains('1200')].groupby(['venue', 'draw'])['win'].mean() * 100
    draw_pivot = draw_1200.unstack().round(1)
    
    return {
        'hv_spec': hv_spec,
        'st_spec': st_spec,
        'draw_pivot': draw_pivot
    }

if __name__ == "__main__":
    res = get_venue_comparison()
    if isinstance(res, dict):
        print("HV SPECIALISTS:")
        print(res['hv_spec'].to_string())
        print("\nST SPECIALISTS:")
        print(res['st_spec'].to_string())
        print("\nDRAW BIAS 1200m:")
        print(res['draw_pivot'].to_string())
