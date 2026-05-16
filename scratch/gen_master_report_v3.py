import os
import json
import pandas as pd
import base64
import subprocess
from datetime import datetime

def get_full_data():
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
                        # Reliable venue detection
                        venue = 'HV' if '1650' in dist or '\u8dd1\u99ac\u5730' in f else 'ST'
                        if r_no not in day_results or venue == 'HV':
                            day_results[r_no] = (venue, r_info)
                except: continue
        
        for r_no, (venue, r_info) in day_results.items():
            dist = r_info.get('distance', '')
            cls = r_info.get('class_info', '')
            results = r_info.get('results', [])
            for idx, res in enumerate(results):
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
                    'win_by_3': win_by_3,
                    'weight': int(res.get('declared_weight', 0)) if res.get('declared_weight','').isdigit() else 0
                })
    return pd.DataFrame(all_data)

def render_master(df):
    report = []
    report.append('# 📊 2025/2026 香港賽馬季度全方位深度數據分析報告 (Professional Edition)')
    report.append(f'> **數據更新日期**: 2026-05-11 | **總計賽事**: {len(df[df["win"]==1])} 場 | **總出賽人次**: {len(df)}')
    report.append('\n---')

    # 1. Jockey Rankings
    report.append('\n## 🏆 騎師排行榜 (Jockey Rankings)')
    j_stats = df.groupby('jockey').agg(W=('win','sum'), S=('win','count'), P=('place','sum'), ROI=('odds', lambda x: (x[df.loc[x.index, "win"]==1].sum() / len(x)).round(2))).reset_index()
    j_stats['WR'] = (j_stats['W'] / j_stats['S'] * 100).round(1)
    j_stats['PR'] = (j_stats['P'] / j_stats['S'] * 100).round(1)
    j_stats = j_stats.sort_values('W', ascending=False).head(15)
    report.append('\n| 排名 | 騎師 | 頭馬 | 出賽 | 上名 | 勝率 | 上名率 | 獨贏ROI |')
    report.append('| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |')
    for i, (_, r) in enumerate(j_stats.iterrows(), 1):
        roi_str = f'**{r.ROI}**' if r.ROI >= 1.0 else f'{r.ROI}'
        report.append(f'| {i} | **{r.jockey}** | {int(r.W)} | {int(r.S)} | {int(r.P)} | {r.WR}% | {r.PR}% | {roi_str} |')

    # 2. Trainer Rankings
    report.append('\n## 🏇 練馬師排行榜 (Trainer Rankings)')
    t_stats = df.groupby('trainer').agg(W=('win','sum'), S=('win','count'), P=('place','sum')).reset_index()
    t_stats['WR'] = (t_stats['W'] / t_stats['S'] * 100).round(1)
    t_stats['PR'] = (t_stats['P'] / t_stats['S'] * 100).round(1)
    t_stats = t_stats.sort_values('W', ascending=False).head(15)
    report.append('\n| 排名 | 練馬師 | 頭馬 | 出賽 | 上名 | 勝率 | 上名率 |')
    report.append('| :---: | :--- | :---: | :---: | :---: | :---: | :---: |')
    for i, (_, r) in enumerate(t_stats.iterrows(), 1):
        report.append(f'| {i} | **{r.trainer}** | {int(r.W)} | {int(r.S)} | {int(r.P)} | {r.WR}% | {r.PR}% |')

    # 3. Venue Mastery
    report.append('\n## 🏟\ufe0f 場地對比：沙田 vs 跑馬地')
    vt = df.groupby(['trainer', 'venue']).agg(W=('win','sum'), S=('win','count')).reset_index()
    vt['WR'] = (vt['W'] / vt['S'] * 100).round(1)
    hv_top = vt[vt['venue']=='HV'].sort_values('W', ascending=False).head(10)
    st_top = vt[vt['venue']=='ST'].sort_values('W', ascending=False).head(10)
    report.append('\n### 🏆 場地最強練馬師')
    report.append('| 跑馬地 HV | 勝出 | 勝率 | 沙田 ST | 勝出 | 勝率 |')
    report.append('| :--- | :--- | :--- | :--- | :--- | :--- |')
    for i in range(10):
        h = hv_top.iloc[i] if i < len(hv_top) else None
        s = st_top.iloc[i] if i < len(st_top) else None
        h_str = f'| {h.trainer} | {h.W} | {h.WR}%' if h is not None else '| - | - | -'
        s_str = f'| {s.trainer} | {s.W} | {s.WR}% |' if s is not None else '| - | - | - |'
        report.append(h_str + s_str)

    # 4. Market Efficiency
    report.append('\n## 📉 市場效率分析 (Market Efficiency)')
    bins = [0, 2, 5, 10, 20, 50, 100, 1000]
    labels = ['1-2\u500d', '2-5\u500d', '5-10\u500d', '10-20\u500d', '20-50\u500d', '50-100\u500d', '100\u500d\u4ee5\u4e0a']
    df['odds_bin'] = pd.cut(df['odds'], bins=bins, labels=labels)
    m_eff = df.groupby('odds_bin').agg(S=('win','count'), W=('win','sum')).reset_index()
    m_eff['Actual_WR'] = (m_eff['W'] / m_eff['S'] * 100).round(1)
    report.append('\n| 賠率區間 | 實際勝率 | 出賽人次 | 結論 |')
    report.append('| :--- | :---: | :---: | :--- |')
    for _, r in m_eff.iterrows():
        note = '\u672c\u5b63\u96f6\u52dd\u51fa' if r.W == 0 else '\u5408\u7406'
        report.append(f'| {r.odds_bin} | {r.Actual_WR}% | {int(r.S)} | {note} |')

    # 5. Draw Bias 1200m
    report.append('\n## 📏 1200m 檔位勝率對比')
    draw_stats = df[df['dist'].str.contains('1200')].groupby(['venue', 'draw'])['win'].mean() * 100
    dp = draw_stats.unstack().round(1).fillna(0)
    report.append('\n| 場地 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 12 | 14 |')
    report.append('| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |')
    for v in ['ST', 'HV']:
        if v in dp.index:
            r = dp.loc[v]
            vals = [str(r.get(i,0))+'%' for i in [1,2,3,4,5,6,7,8,12,14]]
            report.append(f'| {v} | ' + ' | '.join(vals) + ' |')

    # 6. Repeat Winners
    report.append('\n## 🔄 本季常勝軍 (Repeat Winners)')
    rw = df[df['win']==1].groupby('horse').size().sort_values(ascending=False)
    rw = rw[rw >= 2]
    report.append('\n| 馬匹 | 勝出 | 專屬騎師 | 場地 |')
    report.append('| :--- | :---: | :--- | :--- |')
    for h_name, count in rw.head(10).items():
        h_df = df[(df['horse']==h_name) & (df['win']==1)]
        report.append(f'| {h_name} | {count} | {h_df["jockey"].mode()[0]} | {h_df["venue"].mode()[0]} |')

    # 7. Big Margin
    report.append('\n## 🚀 大勝專門戶 (Win by 3+ Lengths)')
    bw = df[df['win_by_3']==True]
    report.append('\n| 類別 | 名稱 | 大勝場數 |')
    report.append('| :--- | :--- | :---: |')
    if not bw.empty:
        t_top = bw['trainer'].value_counts().head(3)
        for t, c in t_top.items(): report.append(f'| \u7df4\u99ac\u5e2b | {t} | {c} |')
        j_top = bw['jockey'].value_counts().head(3)
        for j, c in j_top.items(): report.append(f'| \u9a0e\u5e2b | {j} | {c} |')

    # 8. Weight Impact
    report.append('\n## ⚖\ufe0f 體重對勝率影響')
    bins_w = [0, 1050, 1100, 1150, 1200, 1300, 1500]
    labels_w = ['<1050', '1050-1100', '1100-1150', '1150-1200', '1200-1300', '1300+']
    df['weight_bin'] = pd.cut(df['weight'], bins=bins_w, labels=labels_w)
    w_eff = df.groupby('weight_bin').agg(S=('win','count'), W=('win','sum')).reset_index()
    w_eff['WR'] = (w_eff['W'] / w_eff['S'] * 100).round(1)
    report.append('\n| 體重 (磅) | 勝率 | 人次 |')
    report.append('| :--- | :---: | :---: |')
    for _, r in w_eff.iterrows():
        report.append(f'| {r.weight_bin} | {r.WR}% | {int(r.S)} |')

    report.append('\n---')
    report.append('\n*報告最後更新：2026-05-11 | 數據來源：HKJC 2025/2026 賽季 | 專業統計模式*')
    
    return '\n'.join(report)

if __name__ == "__main__":
    df = get_full_data()
    if not df.empty:
        content = render_master(df)
        b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        target = r'archive race analysis/hkjc results 2025 26/season_deep_stats.md'
        subprocess.run([
            'python', '.agents/scripts/safe_file_writer.py',
            '--target', target, '--mode', 'overwrite', '--content', b64
        ], check=True)
        print("Master Report Updated and Merged.")
