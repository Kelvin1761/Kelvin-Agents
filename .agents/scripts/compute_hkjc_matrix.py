import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import re
import argparse

def parse_md(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    # Find context for each horse
    horse_blocks = text.split("### 【No.")[1:]
    
    horses = []
    for block in horse_blocks:
        # Extract horse number and name
        match = re.search(r'^(\d+)】(.*?)\s*\|', block)
        if not match: continue
        num = int(match.group(1))
        name = match.group(2).strip()
        
        # Extract Math
        math_match = re.search(r'矩陣算術:.*核心✅=(\d+).*半核心✅=(\d+).*輔助✅=(\d+).*總❌=(\d+).*核心❌=(\d+)', block)
        if not math_match: continue
        core_str = int(math_match.group(1))
        semi_str = int(math_match.group(2))
        aux_str = int(math_match.group(3))
        tot_cross = int(math_match.group(4))
        core_cross = int(math_match.group(5))
        
        # Extract Final Grade
        grade_match = re.search(r'⭐ \*\*最終評級:\*\* `\[(.*?)\]`', block)
        grade = grade_match.group(1) if grade_match else "C"
        
        # Extract Stability
        stab_match = re.search(r'穩定指數:`\[(.*?)\]`', block)
        stability = stab_match.group(1) if stab_match else "中"
        
        # Extract Core Logic
        logic_match = re.search(r'> - \*\*核心邏輯:\*\* (.*?)$', block, re.MULTILINE)
        logic = logic_match.group(1).strip() if logic_match else ""
        
        # Extract Danger Reason
        risk_match = re.search(r'> - \*\*最大失敗風險:\*\* (.*?)$', block, re.MULTILINE)
        risk = risk_match.group(1).strip() if risk_match else ""
        
        # Extract Jockey and Trainer
        jt_match = re.search(r'騎師:(.*?)\s*/\s*練馬師:(.*?)\s*\|', block)
        jockey = jt_match.group(1).strip() if jt_match else ""
        trainer = jt_match.group(2).strip() if jt_match else ""
        
        # Distance (try to find from Top table)
        dist_match = re.search(r'距離: (\d+)m', text[:1000])
        dist = dist_match.group(1) + "m" if dist_match else "1200m"
        
        horses.append({
            'num': num, 'name': name, 'grade': grade,
            'core_str': core_str, 'semi_str': semi_str, 'aux_str': aux_str,
            'core_cross': core_cross, 'tot_cross': tot_cross, 'stability': stability,
            'logic': logic, 'risk': risk, 'jockey': jockey, 'trainer': trainer, 'dist': dist
        })

    # Sort horses: Grade S -> D
    grades = ['S', 'S-', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D']
    def grade_key(h):
        try: return grades.index(h['grade'])
        except ValueError: return 99
    
    ranked = sorted(horses, key=lambda h: (grade_key(h), -h['core_str'], h['tot_cross']))
    
    return ranked, text

def build_tables(ranked, race_id):
    lines = []
    lines.append('## [第三部分] 🏆 全場最終決策\n\n### Top 4 精選\n')
    lines.append('| 排名 | 馬號 | 馬名 | 評級 | 一句話核心邏輯 |')
    lines.append('|:----:|:----:|:----:|:----:|:---|')
    
    emojis = ['🥇', '🥈', '🥉', '4️⃣']
    for i, h in enumerate(ranked[:4]):
        e = emojis[i] if i < 4 else i+1
        short_logic = h['logic'][:50] + ("..." if len(h['logic'])>50 else "")
        lines.append(f"| {e} #{i+1} | {h['num']} | {h['name']} | {h['grade']} | {short_logic} |")
        
    lines.append('\n### 危險名單 (輸掉長敗嘅馬)\n')
    lines.append('| 馬號 | 馬名 | 評級 | 危險理由 |')
    lines.append('|:----:|:----:|:----:|:---|')
    dangers = [h for h in ranked if h['grade'].startswith('D') or h['grade'] == 'C-']
    for h in dangers:
        lines.append(f"| {h['num']} | {h['name']} | {h['grade']} | {h['risk']} |")
        
    lines.append('\n### 全場信心矩陣\n')
    lines.append('| 馬號 | 馬名 | 評級 | 核心✅ | 半核心✅ | 輔助✅ | 核心❌ | 穩定指數 |')
    lines.append('|:----:|:----:|:----:|:------:|:--------:|:------:|:------:|:--------:|')
    for h in sorted(ranked, key=lambda x: x['num']):
        lines.append(f"| {h['num']} | {h['name']} | {h['grade']} | {h['core_str']} | {h['semi_str']} | {h['aux_str']} | {h['core_cross']} | {h['stability']} |")
        
    lines.append('\n## [第四部分] 分析陷阱\n\n[FILL — 由 LLM 填充]\n')
    lines.append('\n## [第五部分] 📊 數據庫匯出 (CSV)\n```csv')
    lines.append('場次,距離,騎師,練馬師,馬號,馬名,評級')
    for h in sorted(ranked, key=lambda x: x['num']):
        lines.append(f"{race_id},{h['dist']},{h['jockey']},{h['trainer']},{h['num']},{h['name']},{h['grade']}")
    lines.append('```')
    
    return '\n'.join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--race_id", required=True)
    args = parser.parse_args()
    
    ranked, original_text = parse_md(args.input)
    if not ranked:
        print("No horses parsed!")
        return
        
    new_verdict = build_tables(ranked, args.race_id)
    
    # Replace existing Third Part
    new_text = re.sub(r'## \[第三部分\].*?(?=## \[第六部分\]|\Z)', new_verdict + "\n", original_text, flags=re.DOTALL)
    
    with open(args.input, 'w', encoding='utf-8') as f:
        f.write(new_text)
    
    print("Fixed generated verdict using Python computation!")

if __name__ == '__main__':
    main()
