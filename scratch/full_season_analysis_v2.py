import os
import json
import pandas as pd
import base64
import subprocess

def get_stats():
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
            results = r_info.get('results', [])
            for idx, res in enumerate(results):
                margin = 0
                if idx > 0: # Get margin for the horse behind
                    # But we want to know if the WINNER won by a lot
                    pass 
                
                win_by_3 = False
                if idx == 0 and len(results) > 1:
                    m_str = results[1].get('margin', '')
                    m_val = 0
                    if not m_str or any(x in m_str.lower() for x in ['nose','short','neck','head']): m_val = 0.1
                    else:
                        try:
                            if '+' in m_str: m_val = sum(float(x) for x in m_str.split('+'))
                            else: m_val = float(m_str)
                        except: m_val = 0
                    if m_val >= 3: win_by_3 = True

                all_data.append({
                    'date': folder, 'race_no': r_no, 'venue': venue,
                    'trainer': res.get('trainer'), 'jockey': res.get('jockey'),
                    'win': 1 if res.get('pos') == '1' else 0,
                    'place': 1 if res.get('pos') in ['1','2','3'] else 0,
                    'draw': int(res.get('draw', 0)) if res.get('draw','').isdigit() else 0,
                    'dist': dist, 'cls': cls, 'horse': res.get('horse_name', '').strip(),
                    'odds': float(res.get('win_odds', 0)) if res.get('win_odds') else 0,
                    'win_by_3': win_by_3
                })
    return pd.DataFrame(all_data)

def render_report(df):
    report = []
    report.append('# 📊 2025/2026 香港賽馬季度深度統計分析報告 (V2.0)')
    report.append(f'> **數據更新日期**: 2026-05-11 | **總計頭馬**: {len(df[df["win"]==1])} 場')
    report.append('\n---')

    # 1. Venue Mastery
    report.append('\n## 🏟\ufe0f 場地對比：沙田 vs 跑馬地')
    vt = df.groupby(['trainer', 'venue']).agg(W=('win','sum'), S=('win','count')).reset_index()
    vt['WR'] = (vt['W'] / vt['S'] * 100).round(1)
    hv_top = vt[vt['venue']=='HV'].sort_values('W', ascending=False).head(5)
    st_top = vt[vt['venue']=='ST'].sort_values('W', ascending=False).head(5)
    report.append('\n### 🏆 場地最強練馬師')
    report.append('| 跑馬地 HV | 勝出 | 勝率 | 沙田 ST | 勝出 | 勝率 |')
    report.append('| :--- | :--- | :--- | :--- | :--- | :--- |')
    for i in range(5):
        h = hv_top.iloc[i] if i < len(hv_top) else None
        s = st_top.iloc[i] if i < len(st_top) else None
        h_str = f'| {h.trainer} | {h.W} | {h.WR}%' if h is not None else '| - | - | -'
        s_str = f'| {s.trainer} | {s.W} | {s.WR}% |' if s is not None else '| - | - | - |'
        report.append(h_str + s_str)

    # 2. Draw Bias (1200m)
    report.append('\n### 📏 1200m 檔位勝率對比')
    draw_stats = df[df['dist'].str.contains('1200')].groupby(['venue', 'draw'])['win'].mean() * 100
    dp = draw_stats.unstack().round(1).fillna(0)
    report.append('\n| 場地 | 1\u6a94 | 2\u6a94 | 3\u6a94 | 4\u6a94 | 8\u6a94 | 12\u6a94 | 14\u6a94 |')
    report.append('| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |')
    for v in ['ST', 'HV']:
        if v in dp.index:
            r = dp.loc[v]
            report.append(f'| {v} | {r.get(1,0)}% | {r.get(2,0)}% | {r.get(3,0)}% | {r.get(4,0)}% | {r.get(8,0)}% | {r.get(12,0)}% | {r.get(14,0)}% |')

    # 3. Partnerships
    report.append('\n## 🤝 黄金拍檔 ROI 排行 (市場盲點)')
    pt = df.groupby(['jockey', 'trainer']).agg(W=('win','sum'), S=('win','count'), 
                                              ROI=('odds', lambda x: (x[df.loc[x.index, "win"]==1].sum() / len(x)).round(2))).reset_index()
    pt = pt[pt['S'] >= 10].sort_values('ROI', ascending=False).head(10)
    report.append('\n| 組合 | 出賽 | 頭馬 | 勝率 | ROI |')
    report.append('| :--- | :--- | :--- | :--- | :--- |')
    for _, r in pt.iterrows():
        report.append(f'| {r.jockey} x {r.trainer} | {r.S} | {r.W} | {(r.W/r.S*100):.1f}% | **{r.ROI}** |')

    # 4. Repeat Winners
    report.append('\n## 🔄 本季常勝軍 (Repeat Winners)')
    rw = df[df['win']==1].groupby('horse').size().sort_values(ascending=False)
    rw = rw[rw >= 2]
    report.append('\n| 馬匹 | 勝出次數 | 最強搭檔 | 主要場地 |')
    report.append('| :--- | :---: | :--- | :--- |')
    for h_name, count in rw.head(10).items():
        h_df = df[(df['horse']==h_name) & (df['win']==1)]
        report.append(f'| {h_name} | {count} | {h_df["jockey"].mode()[0]} | {h_df["venue"].mode()[0]} |')

    # 5. Big Margin Analysis
    report.append('\n## 📊 大勝分析 (Win by 3+ Lengths)')
    bw = df[df['win_by_3']==True]
    if not bw.empty:
        report.append('\n### 🚀 擅長大勝的馬房/騎師')
        report.append('| 類別 | 名稱 | 大勝次數 | 代表馬 |')
        report.append('| :--- | :--- | :---: | :--- |')
        t_top = bw['trainer'].value_counts().idxmax()
        t_count = bw['trainer'].value_counts().max()
        t_horse = bw[bw['trainer']==t_top]['horse'].iloc[0]
        report.append(f'| 練馬師 | {t_top} | {t_count} | {t_horse} |')
        j_top = bw['jockey'].value_counts().idxmax()
        j_count = bw['jockey'].value_counts().max()
        j_horse = bw[bw['jockey']==j_top]['horse'].iloc[0]
        report.append(f'| 騎師 | {j_top} | {j_count} | {j_horse} |')

    report.append('\n---')
    report.append('\n*數據來源：HKJC 2025/2026 賽季賽果 | 生成時間：2026-05-11*')
    
    return '\n'.join(report)

if __name__ == "__main__":
    df = get_stats()
    if not df.empty:
        content = render_report(df)
        b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        target = r'archive race analysis/hkjc results 2025 26/season_deep_stats.md'
        subprocess.run([
            'python', '.agents/scripts/safe_file_writer.py',
            '--target', target, '--mode', 'overwrite', '--content', b64
        ], check=True)
        print("Report updated successfully.")
