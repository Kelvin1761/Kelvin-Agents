import os
import json
import pandas as pd

def generate_full_report():
    base_dir = r'archive race analysis/hkjc results 2025 26'
    all_data = []
    
    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path): continue
        
        day_results = {}
        files = [f for f in os.listdir(folder_path) if f.endswith('.json')]
        for f in sorted(files):
            with open(os.path.join(folder_path, f), 'r', encoding='utf-8') as jf:
                try:
                    data = json.load(jf)
                    for r_no, r_info in data.items():
                        dist = r_info.get('distance', '')
                        venue = 'HV' if '1650' in dist or '\u8dd1\u99ac\u5730' in f else 'ST'
                        if r_no not in day_results or venue == 'HV':
                            day_results[r_no] = (venue, r_info)
                except: continue
        
        for r_no, (venue, r_info) in day_results.items():
            dist = r_info.get('distance', '')
            cls = r_info.get('class_info', '')
            for res in r_info.get('results', []):
                all_data.append({
                    'date': folder, 'race_no': r_no, 'venue': venue,
                    'trainer': res.get('trainer'), 'jockey': res.get('jockey'),
                    'win': 1 if res.get('pos') == '1' else 0,
                    'place': 1 if res.get('pos') in ['1','2','3'] else 0,
                    'draw': int(res.get('draw', 0)) if res.get('draw','').isdigit() else 0,
                    'dist': dist, 'cls': cls, 'horse': res.get('horse', ''),
                    'odds': float(res.get('win_odds', 0)) if res.get('win_odds') else 0
                })

    df = pd.DataFrame(all_data)
    if df.empty: return

    report = []
    report.append('# 📊 2025/2026 \u9999\u6e2f\u8cfd\u99ac\u5b63\u5ea6\u6df1\u5ea6\u6578\u64da\u5206\u6790\u5831\u544a')
    report.append(f'> **\u6578\u64da\u66f4\u65b0\u65e5\u671f**: 2026-05-11 | **\u6db5\u84cb\u8cfd\u4e8b**: {len(df[df["win"]==1])} \u5834')

    # 1. Venue Comparison
    report.append('\n## 🏟\ufe0f \u5834\u5730\u5c0d\u6bd4\uff1a\u6c99\u7530 vs \u8dd1\u99ac\u5730')
    vt = df.groupby(['trainer', 'venue']).agg(W=('win','sum'), S=('win','count')).reset_index()
    vt['WR'] = (vt['W'] / vt['S'] * 100).round(1)
    hv_top = vt[vt['venue']=='HV'].sort_values('W', ascending=False).head(10)
    st_top = vt[vt['venue']=='ST'].sort_values('W', ascending=False).head(10)
    
    report.append('\n### 🏆 \u5834\u5730\u7df4\u99ac\u5e2b\u9738\u4e3b')
    report.append('| \u8dd1\u99ac\u5730 HV | \u52dd\u51fa | \u52dd\u7387 | \u6c99\u7530 ST | \u52dd\u51fa | \u52dd\u7387 |')
    report.append('| :--- | :--- | :--- | :--- | :--- | :--- |')
    for i in range(10):
        h = hv_top.iloc[i] if i < len(hv_top) else None
        s = st_top.iloc[i] if i < len(st_top) else None
        h_str = f'| {h.trainer} | {h.W} | {h.WR}%' if h is not None else '| - | - | -'
        s_str = f'| {s.trainer} | {s.W} | {s.WR}% |' if s is not None else '| - | - | - |'
        report.append(h_str + s_str)

    # 2. Partnership ROI (Combined)
    report.append('\n## 🤝 \u9ec4\u91d1\u62cd\u6a94 (Top Partnerships)')
    pt = df.groupby(['jockey', 'trainer']).agg(W=('win','sum'), S=('win','count'), 
                                              ROI=('odds', lambda x: (x[df.loc[x.index, "win"]==1].sum() / len(x)).round(2))).reset_index()
    pt = pt[pt['S'] >= 10].sort_values('W', ascending=False).head(15)
    report.append('\n| \u62cd\u6a94 | \u52dd\u51fa | \u52dd\u7387 | ROI |')
    report.append('| :--- | :--- | :--- | :--- |')
    for _, r in pt.iterrows():
        report.append(f'| {r.jockey} x {r.trainer} | {r.W} | {(r.W/r.S*100):.1f}% | {r.ROI} |')

    # 3. Repeat Winners
    report.append('\n## 🔄 \u91cd\u8907\u52dd\u51fa\u99ac\u5339 (Repeat Winners)')
    rw = df[df['win']==1].groupby('horse').size().sort_values(ascending=False)
    rw = rw[rw >= 2]
    report.append('\n| \u99ac\u5339 | \u52dd\u51fa | \u5e38\u99ac\u9a0e\u5e2b | \u5834\u5730\u504f\u597d |')
    report.append('| :--- | :--- | :--- | :--- |')
    for h_name, count in rw.head(15).items():
        h_df = df[(df['horse']==h_name) & (df['win']==1)]
        j_mode = h_df['jockey'].mode()[0]
        v_mode = h_df['venue'].mode()[0]
        report.append(f'| {h_name} | {count} | {j_mode} | {v_mode} |')

    # 4. Draw Bias 1200m
    report.append('\n## 📏 \u6a94\u4f4d\u504f\u597d (1200m Draw Bias)')
    draw_stats = df[df['dist'].str.contains('1200')].groupby(['venue', 'draw'])['win'].mean() * 100
    dp = draw_stats.unstack().round(1).fillna(0)
    report.append('\n| \u5834\u5730 | 1\u6a94 | 2\u6a94 | 3\u6a94 | 4\u6a94 | 5\u6a94 | 6\u6a94 | 7\u6a94 | 8\u6a94 | 9\u6a94 | 10\u6a94 | 11\u6a94 | 12\u6a94 |')
    report.append('| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |')
    for venue in ['ST', 'HV']:
        if venue in dp.index:
            row = dp.loc[venue]
            vals = [str(row.get(i, 0)) + '%' for i in range(1, 13)]
            report.append(f'| {venue} | ' + ' | '.join(vals) + ' |')

    # Save
    content = '\n'.join(report)
    with open('scratch/report_temp.md', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Report generated to scratch/report_temp.md")

if __name__ == "__main__":
    generate_full_report()
