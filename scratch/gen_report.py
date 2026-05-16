import json
import os

def gen_report():
    if os.path.exists('scratch/v5_debut_deep_stats.json'):
        with open('scratch/v5_debut_deep_stats.json', 'r', encoding='utf-8') as f:
            deep_data = json.load(f)
    else:
        deep_data = {}

    report = "# 🏁 香港賽馬會 (HKJC) 賽季深度分析報告 (2024-2026)\n\n"
    report += "> 本報告整合了 2024/25 及 2025/26 賽季的所有數據，重點分析場地偏差、新馬表現及血統基因。\n\n"

    report += "## 🏟️ 1. 場地與檔位偏差 (Venue & Draw Bias)\n"
    report += "| 賽地 | 跑道 | 最佳檔位 (1-4檔勝率) | 備註 |\n"
    report += "| --- | --- | --- | --- |\n"
    report += "| 沙田 | 全天候 (泥地) | 高 | 內檔優勢極大 |\n"
    report += "| 快活谷 | 草地 | 中高 | 1, 2 檔極具威脅 |\n\n"

    report += "## 🐎 2. 初出馬深度分析 (Debut Horse Intelligence)\n"
    debut = deep_data.get('debut', {})
    total = debut.get('total', 0)
    winners = debut.get('winners', 0)
    win_rate = (winners / total * 100) if total > 0 else 0
    
    report += f"- **總初出馬匹**: {total}\n"
    report += f"- **首戰即勝馬匹**: {winners} (勝率: {win_rate:.2f}%)\n\n"

    report += "### 🌍 出生地對比 (Origin Adaptation)\n"
    report += "| 出生地 | 總數 | 頭馬 | 勝率 | 評價 |\n"
    report += "| --- | --- | --- | --- | --- |\n"
    for ori, s in debut.get('origin_rank', []):
        wr = (s['wins']/s['total']*100) if s['total'] > 0 else 0
        report += f"| {ori} | {s['total']} | {s['wins']} | {wr:.1f}% | {'適應快' if wr > 10 else '需時適應'} |\n"
    
    report += "\n### 🚢 進口類別分析 (Import Category)\n"
    report += "| 類別 | 總數 | 頭馬 | 勝率 | 戰略建議 |\n"
    report += "| --- | --- | --- | --- | --- |\n"
    for imp, s in debut.get('import_rank', []):
        wr = (s['wins']/s['total']*100) if s['total'] > 0 else 0
        report += f"| {imp} | {s['total']} | {s['wins']} | {wr:.1f}% | {'即插即用' if wr > 10 else '次仗留意'} |\n"

    report += "\n### 🧬 血統影響 (Sire & Dam Sire Influence)\n"
    report += "- **最強初出父系 (Sire)**: \n"
    for s, st in debut.get('sire_rank', []):
        if st['wins'] > 0:
            report += f"  - {s} ({st['wins']} 首戰頭馬)\n"
    
    report += "\n- **最強初出外祖父 (Dam Sire)**: \n"
    for s, st in debut.get('dam_sire_rank', []):
        if st['wins'] > 0:
            report += f"  - {s} ({st['wins']} 首戰頭馬)\n"

    with open('archive race analysis/hkjc results 2025 26/season_deep_stats.md', 'w', encoding='utf-8') as f:
        f.write(report)
    print("✅ Final Report Re-generated.")

if __name__ == '__main__':
    gen_report()
