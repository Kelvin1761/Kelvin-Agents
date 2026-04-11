import sys
import json
import re
import os
import argparse
import base64
import subprocess

def inject_horse_data(horse_chunk, data):
    # Map the JSON keys to the exact Markdown lines with [FILL]
    replacements = [
        (r'- \*\*走勢趨勢 \(Step 10\.3\+\):\*\* \[FILL\]', f"- **走勢趨勢 (Step 10.3+):** {data['trend']}"),
        (r'- \*\*隱藏賽績 \(Step 6\+12\):\*\* \[FILL\]', f"- **隱藏賽績 (Step 6+12):** {data['hidden']}"),
        (r'- \*\*贏馬回落風險 / 穩定性 \(Step 5\):\*\* \[FILL\]', f"- **贏馬回落風險 / 穩定性 (Step 5):** {data['risk']}"),
        (r'- \*\*級數評估 \(Step 8\.1\):\*\* \[FILL\]', f"- **級數評估 (Step 8.1):** {data['class']}"),
        (r'- \*\*路程場地適性 \(Step 2\):\*\* \[FILL\]', f"- **路程場地適性 (Step 2):** {data['distance_apt']}"),
        (r'- \*\*引擎距離 \(Step 2\.6\):\*\* \[FILL\]', f"- **引擎距離 (Step 2.6):** {data['engine']}"),
        (r'- \*\*配備變動 \(Step 6\):\*\* \[FILL\]', f"- **配備變動 (Step 6):** {data['gear']}"),
        (r'- \*\*部署與練馬師訊號 \(Step 8\.2\):\*\* \[FILL\]', f"- **部署與練馬師訊號 (Step 8.2):** {data['trainer']}"),
        (r'- \*\*人馬/騎練配搭 \(Step 2\.5\):\*\* \[FILL\]', f"- **人馬/騎練配搭 (Step 2.5):** {data['jockey']}"),
        (r'- \*\*步速段速 \(Step 0\+10\):\*\* \[FILL\]', f"- **步速段速 (Step 0+10):** {data['pace']}"),
        (r'- \*\*競賽事件 / 馬匹特性:\*\* \[FILL\]', f"- **競賽事件 / 馬匹特性:** {data['event']}"),
        (r'- \*\*綜合結論:\*\* `\[FILL\]`', f"- **綜合結論:** `{data['formline_conclusion']}`"),
        
        # Forgive array
        (r'- \*\*逐場寬恕判定:\*\* `\[JSON Array.*?\]`', f"- **逐場寬恕判定:** `{data['forgive_list']}`"),
        
        # Matrix
        (r'- 穩定性 \[核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 穩定性 [核心]: `{data['matrix']['stability']['value']}` | 理據: `{data['matrix']['stability']['reason']}`"),
        (r'- 段速質量 \[核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 段速質量 [核心]: `{data['matrix']['sectional']['value']}` | 理據: `{data['matrix']['sectional']['reason']}`"),
        (r'- EEM 潛力 \[半核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- EEM 潛力 [半核心]: `{data['matrix']['eem']['value']}` | 理據: `{data['matrix']['eem']['reason']}`"),
        (r'- 練馬師訊號 \[半核心\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 練馬師訊號 [半核心]: `{data['matrix']['trainer_sig']['value']}` | 理據: `{data['matrix']['trainer_sig']['reason']}`"),
        (r'- 情境適配 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 情境適配 [輔助]: `{data['matrix']['scenario']['value']}` | 理據: `{data['matrix']['scenario']['reason']}`"),
        (r'- 路程/新鮮度 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 路程/新鮮度 [輔助]: `{data['matrix']['freshness']['value']}` | 理據: `{data['matrix']['freshness']['reason']}`"),
        (r'- 賽績線 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 賽績線 [輔助]: `{data['matrix']['formline']['value']}` | 理據: `{data['matrix']['formline']['reason']}`"),
        (r'- 級數優勢 \[輔助\]: `\[FILL\]` \| 理據: `\[FILL\]`', f"- 級數優勢 [輔助]: `{data['matrix']['class_adv']['value']}` | 理據: `{data['matrix']['class_adv']['reason']}`"),
        (r'- 寬恕加分: `\[FILL\].*?` \| 理據: `\[FILL\]`', f"- 寬恕加分: `{data['matrix']['forgiveness']['value']}` | 理據: `{data['matrix']['forgiveness']['reason']}`"),
        
        # Math
        (r'\*\*🔢 矩陣算術:\*\* 核心✅=\[FILL\] \| 半核心✅=\[FILL\] \| 輔助✅=\[FILL\] \(含寬恕加分\) \| 總❌=\[FILL\] \| 核心❌=\[FILL\] → 查表命中行=\[FILL\]', 
         f"**🔢 矩陣算術:** 核心✅={data['math']['core_pass']} | 半核心✅={data['math']['semi_pass']} | 輔助✅={data['math']['aux_pass']} (含寬恕加分) | 總❌={data['math']['total_fail']} | 核心❌={data['math']['core_fail']} → 查表命中行={data['math']['hit_row']}"),
        
        (r'\*\*14\.2 基礎評級:\*\* `\[FILL\]` \| `\[FILL\]`', f"**14.2 基礎評級:** `{data['math']['base_rating']}` | `{data['math']['base_reason']}`"),
        (r'\*\*14\.2B 微調:\*\* `\[FILL\]` \| `\[FILL\]`', f"**14.2B 微調:** `{data['math']['adj_rating']}` | `{data['math']['adj_reason']}`"),
        (r'\*\*14\.3 覆蓋:\*\* `\[FILL\]`', f"**14.3 覆蓋:** `{data['math']['override']}`"),
        
        # Conclusion
        (r'> - \*\*核心邏輯:\*\* \[呢匹馬.*?\]', f"> - **核心邏輯:** {data['core_logic']}"),
        (r'> - \*\*最大競爭優勢:\*\* \[明確列出\]', f"> - **最大競爭優勢:** {data['adv']}"),
        (r'> - \*\*最大失敗風險:\*\* \[若為A-或以上必須寫,否則明確寫「無」\]', f"> - **最大失敗風險:** {data['risk_factor']}"),
        
        (r'\*\*⭐ 最終評級:\*\* `\[FILL\]`', f"**⭐ 最終評級:** `{data['final_rating']}`"),
        
        # Underhorse
        (r'🐴⚡ \*\*冷門馬訊號 \(Underhorse Signal\):\*\* `\[觸發 / 未觸發\]`\n(?:若觸發,必須列明:\n- \*\*受惠條件:\*\* `\[.*?\]`\n- \*\*理由:\*\* \[.*?\])?', 
         f"🐴⚡ **冷門馬訊號 (Underhorse Signal):** `{data['underhorse_signal']}`" + (f"\n若觸發,必須列明:\n- **受惠條件:** `{data['underhorse_condition']}`\n- **理由:** {data['underhorse_reason']}" if data['underhorse_signal'] == '觸發' else ""))
    ]
    
    for pattern, repl in replacements:
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
    for chunk in chunks[1:]:
        h_id = chunk.split('】')[0]
        if h_id in payload:
            chunk = inject_horse_data(chunk, payload[h_id])
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
        
    tmp_path = "/tmp/injected_output.md"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(final_text)
        
    # Run safe_file_writer
    b64_content = base64.b64encode(final_text.encode('utf-8')).decode('utf-8')
    subprocess.run(["python3", args.safe_writer, "--target", args.target, "--mode", "overwrite", "--content", b64_content], check=True)
    print("Injection complete!")

if __name__ == '__main__':
    main()
