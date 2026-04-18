import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
import json
import re
import argparse
import base64
import subprocess
import tempfile
import shutil

# Import shared qualitative rating engine v2 (replaces deprecated grading_engine)
from rating_engine_v2 import compute_base_grade, compute_weighted_score, apply_fine_tune, parse_matrix_scores

# Convert numeric rating to letter grade
def num_to_grade(val):
    """Convert a numeric string rating to a letter grade. Pass-through if already a letter."""
    try:
        n = float(val)
    except (ValueError, TypeError):
        return val  # Already a letter grade
    # Mapping: >=90=S, >=85=S-, >=80=A+, >=75=A, >=70=A-, >=65=B+, >=60=B, >=55=B-, >=50=C+, >=45=C, >=40=C-, >=30=D, <30=E
    thresholds = [
        (90, 'S'), (85, 'S-'), (80, 'A+'), (75, 'A'), (70, 'A-'),
        (65, 'B+'), (60, 'B'), (55, 'B-'), (50, 'C+'), (45, 'C'),
        (40, 'C-'), (30, 'D'),
    ]
    for threshold, grade in thresholds:
        if n >= threshold:
            return grade
    return 'E'

def inject_horse_data(horse_chunk, data):
    ab = data.get('analytical_breakdown', {})
    
    cores = [data.get('matrix', {}).get('stability', {}).get('score', '➖'), data.get('matrix', {}).get('speed_mass', {}).get('score', '➖')]
    semis = [data.get('matrix', {}).get('eem', {}).get('score', '➖'), data.get('matrix', {}).get('trainer_jockey', {}).get('score', '➖')]
    auxs = [data.get('matrix', {}).get('scenario', {}).get('score', '➖'), 
            data.get('matrix', {}).get('freshness', {}).get('score', '➖'), 
            data.get('matrix', {}).get('formline', {}).get('score', '➖'), 
            data.get('matrix', {}).get('class_advantage', {}).get('score', '➖'), 
            data.get('matrix', {}).get('forgiveness_bonus', {}).get('score', '➖')]
            
    hkjc_schema = {
        'stability': 'core', 'speed_mass': 'core',
        'eem': 'semi', 'trainer_jockey': 'semi',
        'scenario': 'aux', 'freshness': 'aux', 'formline': 'aux',
        'class_advantage': 'aux', 'forgiveness_bonus': 'aux'
    }
    core_pass, semi_pass, aux_pass, core_fail, total_fail = parse_matrix_scores(data.get('matrix', {}), hkjc_schema)

    uh_trig = "觸發" if data.get('underhorse', {}).get('triggered', False) else "未觸發"
    uh_cond = data.get('underhorse', {}).get('condition', '')
    uh_reason = data.get('underhorse', {}).get('reason', '')
    
    replacements = [
        (r'- \*\*走勢趨勢 \(Step 10\.3\+\):\*\* \[FILL\]', f"- **走勢趨勢 (Step 10.3+):** {ab.get('trend_analysis', '')}"),
        (r'- \*\*隱藏賽績 \(Step 6\+12\):\*\* \[FILL\]', f"- **隱藏賽績 (Step 6+12):** {ab.get('hidden_form', '')}"),
        (r'- \*\*贏馬回落風險 / 穩定性 \(Step 5\):\*\* \[FILL\]', f"- **贏馬回落風險 / 穩定性 (Step 5):** {ab.get('stability_risk', '')}"),
        (r'- \*\*級數評估 \(Step 8\.1\):\*\* \[FILL\]', f"- **級數評估 (Step 8.1):** {ab.get('class_assessment', '')}"),
        (r'- \*\*路程場地適性 \(Step 2\):\*\* \[FILL\]', f"- **路程場地適性 (Step 2):** {ab.get('track_distance_suitability', '')}"),
        (r'- \*\*引擎距離 \(Step 2\.6\):\*\* \[FILL\]', f"- **引擎距離 (Step 2.6):** {ab.get('engine_distance', '')}"),
        (r'- \*\*配備變動 \(Step 6\):\*\* \[FILL\]', f"- **配備變動 (Step 6):** {ab.get('gear_changes', '')}"),
        (r'- \*\*部署與練馬師訊號 \(Step 8\.2\):\*\* \[FILL\]', f"- **部署與練馬師訊號 (Step 8.2):** {ab.get('trainer_signal', '')}"),
        (r'- \*\*人馬/騎練配搭 \(Step 2\.5\):\*\* \[FILL\]', f"- **人馬/騎練配搭 (Step 2.5):** {ab.get('jockey_fit', '')}"),
        (r'- \*\*步速段速 \(Step 0\+10\):\*\* \[FILL\]', f"- **步速段速 (Step 0+10):** {ab.get('pace_adaptation', '')}"),
        (r'- \*\*競賽事件 / 馬匹特性:\*\* \[FILL\]', f"- **競賽事件 / 馬匹特性:** {data.get('forgiveness_archive', {}).get('factors', '無')}"),
        (r'- \*\*綜合結論:\*\* `\[FILL\]`', f"- **綜合結論:** `{data.get('evidence_step_0_14', '')}`"),
        
        (r'- \*\*逐場寬恕判定:\*\* `\[JSON Array.*?\]`', f"- **逐場寬恕判定:** `['見因素分析']`"),
        
        (r'- 穩定性 \[核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 穩定性 [核心]: `{cores[0]}` | 理據: `{data.get('matrix', {}).get('stability', {}).get('reasoning', '')}`"),
        (r'- 段速質量 \[核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 段速質量 [核心]: `{cores[1]}` | 理據: `{data.get('matrix', {}).get('speed_mass', {}).get('reasoning', '')}`"),
        (r'- EEM 潛力 \[半核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- EEM 潛力 [半核心]: `{semis[0]}` | 理據: `{data.get('matrix', {}).get('eem', {}).get('reasoning', '')}`"),
        (r'- 練馬師訊號 \[半核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 練馬師訊號 [半核心]: `{semis[1]}` | 理據: `{data.get('matrix', {}).get('trainer_jockey', {}).get('reasoning', '')}`"),
        (r'- 情境適配 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 情境適配 [輔助]: `{auxs[0]}` | 理據: `{data.get('matrix', {}).get('scenario', {}).get('reasoning', '')}`"),
        (r'- 路程/新鮮度 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 路程/新鮮度 [輔助]: `{auxs[1]}` | 理據: `{data.get('matrix', {}).get('freshness', {}).get('reasoning', '')}`"),
        (r'- 賽績線 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 賽績線 [輔助]: `{auxs[2]}` | 理據: `{data.get('matrix', {}).get('formline', {}).get('reasoning', '')}`"),
        (r'- 級數優勢 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 級數優勢 [輔助]: `{auxs[3]}` | 理據: `{data.get('matrix', {}).get('class_advantage', {}).get('reasoning', '')}`"),
        (r'- 寬恕加分: `\[FILL\].*?` \| 理據: `\[FILL\]`', f"- 寬恕加分: `{auxs[4]}` | 理據: `{data.get('matrix', {}).get('forgiveness_bonus', {}).get('reasoning', '')}`"),
        
        (r'\*\*🔢 矩陣算術:\*\* 核心✅=\[FILL\] \| 半核心✅=\[FILL\] \| 輔助✅=\[FILL\] \(含寬恕加分\) \| 總❌=\[FILL\] \| 核心❌=\[FILL\] → 查表命中行=\[FILL\]', 
         f"**🔢 矩陣算術:** 核心✅={core_pass} | 半核心✅={semi_pass} | 輔助✅={aux_pass} (含寬恕加分) | 總❌={total_fail} | 核心❌={core_fail} → 查表命中行={compute_weighted_score(core_pass, semi_pass, aux_pass, core_fail, total_fail)}"),
        
        (r'\*\*14\.2 基礎評級:\*\* `\[FILL\]` \| `\[FILL\]`', f"**14.2 基礎評級:** `{compute_base_grade(core_pass, semi_pass, aux_pass, core_fail, total_fail)}` | `{compute_weighted_score(core_pass, semi_pass, aux_pass, core_fail, total_fail)}`"),
        (r'\*\*14\.2B 微調:\*\* `\[FILL\]` \| `\[FILL\]`', f"**14.2B 微調:** `{data.get('fine_tune', {}).get('direction', '-')}` | `{data.get('fine_tune', {}).get('trigger', '-')}`"),
        (r'\*\*14\.3 覆蓋:\*\* `\[FILL\]`', f"**14.3 覆蓋:** `{data.get('override', {}).get('rule', '-')}`"),
        
        (r'> - \*\*核心邏輯:\*\* \[呢匹馬.*?\]', f"> - **核心邏輯:** {data.get('core_logic', '')}"),
        (r'> - \*\*最大競爭優勢:\*\* \[明確列出\]', f"> - **最大競爭優勢:** {data.get('advantages', '')}"),
        (r'> - \*\*最大失敗風險:\*\* \[若為A-或以上必須寫,否則明確寫「無」\]', f"> - **最大失敗風險:** {data.get('disadvantages', '')}"),
        
        (r'\*\*⭐ 最終評級:\*\* `\[FILL\]`', f"**⭐ 最終評級:** `{apply_fine_tune(compute_base_grade(core_pass, semi_pass, aux_pass, core_fail, total_fail), data.get('fine_tune', {{}}).get('direction', ''))}`"),
        
        (r'🐴⚡ \*\*冷門馬訊號 \(Underhorse Signal\):\*\* `\[觸發 / 未觸發\]`\n(?:若觸發,必須列明:\n- \*\*受惠條件:\*\* `\[.*?\]`\n- \*\*理由:\*\* \[.*?\])?', 
         f"🐴⚡ **冷門馬訊號 (Underhorse Signal):** `{uh_trig}`" + (f"\n若觸發,必須列明:\n- **受惠條件:** `{uh_cond}`\n- **理由:** {uh_reason}" if uh_trig == '觸發' else ""))
    ]
    
    for pattern, repl in replacements:
        # replace any literal backslashes if needed, though raw strings handle some
        horse_chunk = re.sub(pattern, repl.replace('\\', '\\\\'), horse_chunk, count=1, flags=re.DOTALL)
        
    return horse_chunk

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', required=True)
    parser.add_argument('--json', required=True)
    parser.add_argument('--batch0', default=None)
    parser.add_argument('--safe-writer', required=True)
    args = parser.parse_args()
    
    with open(args.target, 'r', encoding='utf-8') as f:
        text = f.read()
        
    with open(args.json, 'r', encoding='utf-8') as f:
        payload = json.load(f)
        
    # Replace Batch 0 if provided (Base64 string)
    if args.batch0:
        b0_text = base64.b64decode(args.batch0).decode('utf-8')
        # Simple replace block for batch 0
        text = re.sub(r'## \[第一部分\] 🗺️ 戰場全景.*?\*\*🏃 步速瀑布推演 \(Step 0 結論\):\*\*.*?\n---', b0_text + "\n---", text, flags=re.DOTALL)
        
    horses = re.split(r'(\*\*【No\.\d+】.*?\*\*)', text)
    
    for str_idx, content in enumerate(horses):
        m = re.match(r'\*\*【No\.(\d+)】', content)
        if m:
            h_id = m.group(1)
            if h_id in payload:
                # The actual payload content is in horses[str_idx+1] ideally, but `re.split` with capture group 
                # returns: [everything_before, capture, everything_between, capture, ...]
                # Wait, re.split with '(...)' puts the capture group AND the stuff after it as separate items?
                # Actually, \*\*【No.X】 is in the capture group, so it alternates.
                pass
                
    # Better split logic
    chunks = text.split('**【No.')
    new_chunks = [chunks[0]]
    horse_data = payload.get('horses', payload)
    for chunk in chunks[1:]:
        h_id = chunk.split('】')[0]
        if h_id in horse_data:
            chunk = inject_horse_data(chunk, horse_data[h_id])
        new_chunks.append(chunk)

    final_text = '**【No.'.join(new_chunks)
    
    # Check off batch label
    # E.g. ✅ 批次完成:3/14
    batch_num_match = re.search(r'✅ 批次完成:(\d+)/', final_text)
    if batch_num_match:
        current_num = int(batch_num_match.group(1))
        # Just prefix with BATCH_QA_RECEIPT if we injected
        new_label = f"🔒 BATCH_QA_RECEIPT\n✅ 批次完成:{current_num}\n" 
        # For simplicity, we just leave it unless asked.
        
    tmp_path = os.path.join(tempfile.gettempdir(), "injected_output.md")
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(final_text)
        
    # Run safe_file_writer
    b64_content = base64.b64encode(final_text.encode('utf-8')).decode('utf-8')
    python_cmd = "python3" if shutil.which("python3") else "python"
    subprocess.run([python_cmd, args.safe_writer, "--target", args.target, "--mode", "overwrite", "--content", b64_content], check=True)
    print("Injection complete!")

if __name__ == '__main__':
    main()
