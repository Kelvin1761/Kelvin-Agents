import json
import os

def gen_final_report():
    try:
        with open('scratch/advanced_analysis_results.json', 'r', encoding='utf-8') as f:
            stats = json.load(f)
    except:
        print("Error: analysis results not found.")
        return

    report = f"""# 🏆 HKJC 賽季深度大數據分析報告 (2024-2026)
> 本報告由 Antigravity AI 自動生成。涵蓋 2024/25 及 2025/26 兩個賽季，專注於挖掘市場盲點與高價值統計。

---

## 🆕 初出馬 (Debut Horse) 專項分析
> **核心數據**：初出馬總數 {stats['debut_stats']['total']} 匹 | 勝出 {stats['debut_stats']['winners']} 匹 | **平均勝率 {stats['debut_stats']['winners']/max(1, stats['debut_stats']['total']):.1%}**

### 🐎 初出即勝大師 (Top Debut Trainers)
哪些練馬師最擅長準備新馬一出即勝？
"""
    top_trainers = sorted(stats['debut_stats']['trainer_debut_wins'].items(), key=lambda x: x[1], reverse=True)[:5]
    for trainer, wins in top_trainers:
        report += f"- **{trainer}**: {wins} 場初出冠軍\n"

    report += """
### 🧬 新馬最強父系 (Top Debut Sires)
哪些父系的子嗣在港首戰最為強悍？
"""
    top_debut_sires = sorted(stats['debut_stats']['sire_debut_wins'].items(), key=lambda x: x[1], reverse=True)[:5]
    for sire, wins in top_debut_sires:
        if sire != 'Unknown':
            report += f"- **{sire}**: {wins} 場初出冠軍\n"

    report += """
---

## 🧬 全賽季父系 (Overall Sire) 排名
"""
    top_sires = sorted(stats['sire_stats'].items(), key=lambda x: x[1], reverse=True)[:10]
    for sire, wins in top_sires:
        report += f"- **{sire}**: 累計 {wins} 場頭馬\n"

    report += """
---

## 🏟️ 場地與走位偏差 (Venue Bias)
### 沙田 (Sha Tin)
"""
    st = stats['venues']['沙田']
    total_st = max(1, st['leader_wins'] + st['mid_wins'] + st['closer_wins'])
    report += f"- 領放/前速馬勝率: {st['leader_wins']/total_st:.1%}\n"
    report += f"- 居中馬勝率: {st['mid_wins']/total_st:.1%}\n"
    report += f"- 後追馬勝率: {st['closer_wins']/total_st:.1%}\n"

    report += """
### 跑馬地 (Happy Valley)
"""
    hv = stats['venues']['跑馬地']
    total_hv = max(1, hv['leader_wins'] + hv['mid_wins'] + hv['closer_wins'])
    report += f"- 領放/前速馬勝率: {hv['leader_wins']/total_hv:.1%}\n"
    report += f"- 居中馬勝率: {hv['mid_wins']/total_hv:.1%}\n"
    report += f"- 後追馬勝率: {hv['closer_wins']/total_hv:.1%}\n"

    report += """
---

## 🛠️ 數據法醫：受難馬與騎士 (Incident Tracking)
記錄最多「受阻、受困、無路可上」的騎師排名（反映走位風險）：
"""
    top_jockeys = sorted(stats['jockey_incidents'].items(), key=lambda x: x[1], reverse=True)[:10]
    for jockey, count in top_jockeys:
        report += f"- **{jockey}**: 累計 {count} 次意外記錄\n"

    report += "\n*備註：以上數據包含 2024-2026 跨賽季統計，持續自動更新中。*"

    with open('archive race analysis/hkjc results 2025 26/season_deep_stats.md', 'w', encoding='utf-8') as f:
        f.write(report)
    print("✅ Final Report Updated Successfully.")

if __name__ == '__main__':
    gen_final_report()
